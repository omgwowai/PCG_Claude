#!/usr/bin/env python
"""The contract of one stage's port, read from its official IR snapshot (plan Task 7, ruling N6).

    python Tools/pypcg/port_brief.py 6            -> docs/pypcg/stages/s06-brief.md (overwrites)
    python Tools/pypcg/port_brief.py all --stdout

Classifies every official node:
  param  user-parameter getters
  input  scene reads: Get_ActorData, Get_ActorDataByRef, Get_MeshTerrain, Extract_MeshTerrainPoints,
         LoadDataAsset, LoadCitySampleData, and named reroutes that only carry them
  gen    engine generation nodes kept as nodes (spec 2.4)
  drop   debug and partitioned branches (spec E7, E8): Debug_PrimitiveData, GridPartition,
         LoopSpawnActorPerData, and everything reachable only through the debug or partitioned
         side of a Branch on a Debug*/Partitioned parameter
  python everything else -- what the Python stage computes
and lists the output tags, the tags downstream stages filter on, and the demo level's overrides.
"""
import collections
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "Content", "Python"))

from pypcg import ir as pir, stages  # noqa: E402

GEN = {"Spawn_Assets", "StaticMeshSpawner", "PCGStaticMeshSpawnerSettings", "Assign_ShapeGrammarDefinition",
       "Assign_CitySampleBuildings", "Fill_Areas_WithFittingAssets_with_Corrective", "Create_Mesh_Planar",
       "Create_Mesh_Extrude", "Write_MeshTerrain", "Crosswalks", "Assign_Rule", "SetComplexBuildings",
       "AssignBuildingShape", "LoopCreatePlanarMeshActorPerData", "LoopCreateExtrudedMeshActorPerData"}
INPUT = {"Get_ActorData", "Get_ActorDataByRef", "Get_MeshTerrain", "Extract_MeshTerrainPoints",
         "PCGLoadDataAssetSettings", "LoadCitySampleData"}
ALWAYS_DROP = {"Debug_PrimitiveData", "GridPartition", "LoopSpawnActorPerData"}
PARAM = {"PCGUserParameterGetSettings", "PCGGenericUserParameterGetSettings"}
CARRIERS = {"PCGRerouteSettings", "PCGNamedRerouteDeclarationSettings", "PCGNamedRerouteUsageSettings"}
TAG_WRITERS = {"PCGAddTagSettings": "TagsToAdd"}
DEMO_OVERRIDES = os.path.join(REPO, "Tools", "pypcg", "data", "demo_overrides.json")


def kind(n):
    return pir.alias_of(n["subgraph"]) if n.get("subgraph") else n["class"]


def load(n):
    return pir.load(os.path.join(REPO, "Tools", "pypcg", "official_ir", stages.name(n) + ".json"))


def _param_of(n):
    if n["class"] == "PCGUserParameterGetSettings":
        return n.get("getter_param") or ""
    return (n.get("settings") or {}).get("PropertyPath", "")


def _is_switch(name):
    low = name.lower()
    return "debug" in low or low == "partitioned"


def edges(ir):
    """(outs, ins): outs[src] = [(dst, label, src_pin)], ins[dst] = [(src, label, src_pin)]; named
    reroute usages read their declaration through its node_ref."""
    graph = ir.get("graph", "")
    outs, ins = collections.defaultdict(list), collections.defaultdict(list)
    for n in ir["nodes"]:
        for p in n.get("inputs", []):
            for src, pin in p["edges"]:
                outs[src].append((n["name"], p["label"], pin))
                ins[n["name"]].append((src, p["label"], pin))
        if n["class"] == "PCGNamedRerouteUsageSettings":
            ref = pir.node_refs_to_names((n.get("settings") or {}).get("Declaration"), graph)
            if isinstance(ref, dict) and ref.get("node_ref"):
                outs[ref["node_ref"]].append((n["name"], "In", "Out"))
                ins[n["name"]].append((ref["node_ref"], "In", "Out"))
    return outs, ins


def classify(ir):
    nodes = {n["name"]: n for n in ir["nodes"]}
    outs, ins = edges(ir)
    cls = {}
    for name, n in nodes.items():
        k = kind(n)
        if name in pir.IO_NODES:
            cls[name] = "io"
        elif n["class"] in PARAM:
            cls[name] = "param"
        elif k in ALWAYS_DROP:
            cls[name] = "drop"
        elif k in INPUT:
            cls[name] = "input"
        elif k in GEN:
            cls[name] = "gen"
    # Debug / partition switches: a Branch whose bOutputToB comes from a Debug*/Partitioned getter.
    # Its B side is dropped; the Branch itself becomes a pass-through and is dropped too.
    dropped_side = set()
    for name, n in nodes.items():
        if n["class"] != "PCGBranchSettings":
            continue
        ctl = [s for s, label, _ in ins[name] if label == "bOutputToB"]
        if ctl and all(nodes[s]["class"] in PARAM and _is_switch(_param_of(nodes[s])) for s in ctl):
            cls[name] = "drop"
            for s in ctl:
                cls[s] = "drop"
            dropped_side.update((name, d) for d, label, pin in outs[name] if pin == "Output B")
    # Nodes all of whose inputs come from dropped nodes or dropped Branch sides are dropped.
    changed = True
    while changed:
        changed = False
        for name in nodes:
            if cls.get(name) in ("io", "param", "drop", "input"):
                continue
            src = [(s, pin) for s, label, pin in ins[name] if label not in ("Execution Dependency",)]
            if src and all(cls.get(s) == "drop" and nodes[s]["class"] != "PCGBranchSettings"
                           or (s, name) in dropped_side for s, _ in src):
                if cls.get(name) != "drop":
                    cls[name] = "drop"
                    changed = True
    # Getters that feed only dropped nodes are dropped (their parameters go: spec E7/E8).
    for name, n in nodes.items():
        if cls.get(name) == "param" and outs[name] and all(cls.get(d) == "drop" for d, _, _ in outs[name]):
            cls[name] = "drop"
    # Reroutes that only carry scene reads count as inputs; the rest is Python.
    for name, n in nodes.items():
        if name not in cls and n["class"] in CARRIERS:
            srcs = [s for s, _, _ in ins[name]]
            if srcs and all(cls.get(s) == "input" for s in srcs):
                cls[name] = "carrier"
    for name in nodes:
        cls.setdefault(name, "python")
    return cls


def _tag_of(n):
    st, ov = n.get("settings") or {}, n.get("overrides") or {}
    if n["class"] in TAG_WRITERS:
        return st.get(TAG_WRITERS[n["class"]], "")
    if kind(n) == "Write_Tag":
        return ov.get("CustomTags") or ov.get("Tag") or json.dumps(ov)
    return None


def output_tags(ir):
    """[(node feeding the output, its title, tags)]: for each node wired to the output (through
    reroutes, Gather and Merge), the tags written by the nearest AddTag / Write_Tag nodes upstream
    of it (tags travel with the data)."""
    nodes = {n["name"]: n for n in ir["nodes"]}
    _, ins = edges(ir)
    feeders, seen, todo = [], set(), [s for s, _, _ in ins[pir.OUT_NODE]]
    while todo:
        s = todo.pop()
        if s in seen:
            continue
        seen.add(s)
        if nodes[s]["class"] in CARRIERS | {"PCGGatherSettings", "PCGMergeSettings"}:
            todo += [x for x, _, _ in ins[s]]
        else:
            feeders.append(s)
    out = []
    for f in sorted(feeders):
        tags, seen, todo = [], set(), [f]
        while todo:
            x = todo.pop()
            if x in seen:
                continue
            seen.add(x)
            t = _tag_of(nodes[x])
            if t is not None:
                tags.append(t)
                continue
            todo += [s for s, label, _ in ins[x] if label != "Execution Dependency"]
        out.append((f, nodes[f].get("title", ""), sorted(set(tags)) or ["(no tag)"]))
    return out


def consumers(n_stage):
    """[(reader stage, filter)] for every downstream graph that reads this stage by actor reference."""
    from pypcg.profiles import official
    role_paths = {official.ROLES[r] for r in ROLE_OF_STAGE.get(n_stage, [])}
    found = []
    for m, *_ in stages.STAGES:
        ir = load(m)
        nodes = {n["name"]: n for n in ir["nodes"]}
        outs, _ = edges(ir)
        for n in ir["nodes"]:
            refs = (n.get("overrides") or {}).get("ActorReferences") if kind(n) == "Get_ActorDataByRef" else None
            refs = refs if isinstance(refs, list) else [refs] if refs else []
            if not role_paths.intersection(refs):
                continue
            todo, seen = [n["name"]], set()
            while todo:
                x = todo.pop()
                if x in seen:
                    continue
                seen.add(x)
                for d, label, _ in outs[x]:
                    dn = nodes[d]
                    st, ov = dn.get("settings") or {}, dn.get("overrides") or {}
                    if dn["class"] == "PCGFilterByTagSettings":
                        found.append((m, "FilterByTag %r" % st.get("SelectedTags")))
                    elif kind(dn) == "Filter_Tags":
                        found.append((m, "Filter_Tags %r" % ov.get("FilteredInputTags")))
                    elif dn["class"] in CARRIERS | {"PCGFilterByTypeSettings", "PCGGatherSettings", "PCGMergeSettings"}:
                        todo.append(d)
                    else:
                        found.append((m, "%s (%s) via %s" % (kind(dn), dn.get("title", ""), label)))
    return sorted(set(found))


# The role a stage's volume plays for the others (profiles/official.py ROLES).
ROLE_OF_STAGE = {1: ["Terrain"], 4: ["MainTower"], 5: ["CentralParkFootprint"], 6: ["Districts"], 7: ["Roads"],
                 8: ["Highways"], 9: ["Lots"], 11: ["Buildings"], 13: ["ParkingFootprint"], 14: ["Parkings"]}


def brief(n):
    ir = load(n)
    cls = classify(ir)
    nodes = {x["name"]: x for x in ir["nodes"]}
    counts = collections.Counter(cls.values())
    lines = ["# Stage %d %s -- port contract (generated by Tools/pypcg/port_brief.py)" % (n, stages.name(n)), "",
             "Official nodes: %d (excluding input/output). %s" % (len(nodes) - 2, ", ".join(
                 "%s %d" % (k, counts[k]) for k in ("param", "input", "carrier", "gen", "drop", "python"))), ""]
    lines += ["## Parameters", "", "| Name | Type | Graph default | Demo override | Kept |", "|---|---|---|---|---|"]
    demo = {}
    if os.path.exists(DEMO_OVERRIDES):
        demo = json.load(open(DEMO_OVERRIDES, encoding="utf-8")).get(stages.name(n), {})
    used = {_param_of(x).lower() for name, x in nodes.items() if cls[name] == "param"}
    for p in ir["params"]:
        kept = p["name"].lower() in used and not _is_switch(p["name"])
        lines.append("| %s | %s | %s | %s | %s |" % (p["name"], p["type"], json.dumps(p.get("value"))[:60],
                                                     json.dumps(demo.get(p["name"], "")), "yes" if kept else "dropped"))
    for title, k in (("Scene reads (keep these, by name)", "input"), ("Generation nodes (keep these, by name)", "gen")):
        lines += ["", "## " + title, "", "| Node | Kind | Title | Overrides | Fed by |", "|---|---|---|---|---|"]
        _, ins = edges(ir)
        for name in sorted(x for x in cls if cls[x] == k):
            x = nodes[name]
            ov = dict(x.get("overrides") or {})
            if "ActorReferences" in ov:
                ov["ActorReferences"] = "roles " + str(_roles(ov["ActorReferences"]))
            feeds = sorted({"%s<-%s(%s)" % (label, s, cls.get(s, "?")) for s, label, _ in ins[name]})
            lines.append("| %s | %s | %s | %s | %s |" % (name, kind(x), x.get("title", ""),
                                                         json.dumps(ov, ensure_ascii=False)[:160], ", ".join(feeds)[:200]))
    lines += ["", "## Output tags", ""] + ["- %s (%s, %s): %s" % (s, kind(nodes[s]), title, ", ".join("`%s`" % t for t in tags))
                                          for s, title, tags in output_tags(ir)]
    lines += ["", "## Downstream readers of this stage", ""] + (["- stage %d: %s" % c for c in consumers(n)] or ["- none"])
    lines += ["", "## Into Python (%d nodes; read their internals under Saved/graph_dumps or with export_graph_ir)" % counts["python"], ""]
    by_kind = collections.Counter(kind(nodes[x]) for x in cls if cls[x] == "python")
    lines += ["- %s x%d" % kv for kv in sorted(by_kind.items(), key=lambda kv: -kv[1])]
    lines += ["", "## Dropped (%d nodes)" % counts["drop"], ""]
    lines += ["- %s %s %r" % (x, kind(nodes[x]), nodes[x].get("title", "")) for x in sorted(c for c in cls if cls[c] == "drop")]
    return "\n".join(lines) + "\n", counts


def _roles(paths):
    from pypcg.profiles import official
    rev = {p: r for r, p in official.ROLES.items()}
    paths = paths if isinstance(paths, list) else [paths]
    return [rev.get(p, p) for p in paths]


def main(argv):
    which = argv[0] if argv else "all"
    wanted = [s[0] for s in stages.STAGES] if which == "all" else [int(which)]
    total = collections.Counter()
    for n in wanted:
        text, counts = brief(n)
        total.update(counts)
        if "--stdout" in argv:
            print(text)
        else:
            path = os.path.join(REPO, "docs", "pypcg", "stages", "s%02d-brief.md" % n)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            print("wrote", path, dict(counts))
    print("total", dict(total))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
