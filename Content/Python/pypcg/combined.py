"""PCG_PyCity: the 18 slim stage graphs merged into ONE PCG graph that one volume runs (docs/pypcg-guide.md §13).

Every stage keeps its own nodes -- the Python Data Processor node(s) that hold the stage's logic, the scene
reads and the native generation nodes -- and its own parameters, renamed `SNN_<name>` and grouped under the
category `NN <Stage>`, so the component's Details panel adjusts any stage the traditional way (graph
instance overrides). The control regions stay level actors read the traditional way: tag reads (City,
Arteries, Terrain_shaping_1, HighRise, USER_SPLINE, LAKE, FOREST_EXCLUSION), actor references (the landmark
park spline and the two highway splines) and, for stages 4 and 5, the tower and park footprint volumes,
which become plain control actors read by tag instead of being the volume the graph runs on.

What merging changes, and nothing else:
  - A `Get_ActorDataByRef` that read another STAGE volume's generated output becomes a Gather fed by that
    stage's output edges (what the volume's Output node received). Tags travel with the data, so the
    downstream tag filters are untouched.
  - Stages 4 and 5's `Get Self` reads the footprint control actor by tag (`CONTROL_TAGS`).
  - The mesh terrain is one shared resource that the 18 volumes used in stage order. One graph has no stage
    order, only data edges, so every terrain query of stage N waits (Execution Dependency) on every terrain
    write of the stages before N, and every write of stage N waits on every query of the stages before N:
    each query sees exactly the writes it saw in the 18-volume run (`TERRAIN_GET` / `TERRAIN_WRITE`).
No unreal import: the description is checked offline (Tools/pypcg/tests/test_combined.py).
"""
import copy
import re

from pypcg import dsl, graphs, ir as _ir, stages
from pypcg.profiles import official

NAME = "PCG_PyCity"
ASSET = "/Game/PyPCG/City/" + NAME
REF = "Get_ActorDataByRef"
TERRAIN_GET = "Get_MeshTerrain"
TERRAIN_WRITE = "Write_MeshTerrain"
DEP_PIN = "Execution Dependency"

# role -> the stage whose volume it names; the remaining roles (LandmarkPark, HighwaySpline2/3) are
# control actors and stay actor references.
STAGE_ROLES = {role: next(s[0] for s in stages.STAGES if s[1] == label)
               for role, label in official.ROLE_LABELS.items() if label in stages.names()}

# Stages 4 and 5 read their own volume's transform (stage_api.volume_point). Merged, the graph runs on
# one volume, so the footprint volumes stay in the level as control actors carrying these tags.
CONTROL_TAGS = {4: "PyCity_MainTowerFootprint", 5: "PyCity_CentralParkFootprint"}


def short(n):
    """'Roads' for PCG_3_1_2_Roads, 'MainTower_Visuals' for PCG_4_1_MainTower_Visuals."""
    return re.sub(r"^PCG_(\d+_)+", "", stages.name(n))


def pname(n, name):
    return "S%02d_%s" % (n, name)


def category(n):
    return "%02d %s" % (n, short(n))


def _alias(rec):
    return _ir.alias_of(rec["subgraph"]) if rec.get("subgraph") else None


def _rename_param(p, n):
    q = dsl.P(pname(n, p.name), p.ir["type"], p.ir["value"])
    q.ir = dict(copy.deepcopy(p.ir))
    q.ir["name"] = pname(n, p.name)
    q.ir["category"] = category(n) + ("|" + p.ir["category"] if p.ir.get("category") else "")
    return q


def _actor_selector(tag):
    # The whole struct, as the exporter writes it back (measured 2026-10-22): a partial struct reads
    # back with the rest filled in and fails the structural check.
    return {"Mode": "GetSinglePoint",
            "ActorSelector": {"ActorFilter": "AllWorldActors", "bMustOverlapSelf": False, "bIncludeChildren": False,
                              "IncludeIsolatedActors": "Ignore", "bDisableFilter": False, "ActorSelection": "ByTag",
                              "ActorSelectionTag": tag, "ActorSelectionClass": "None",
                              "ActorReferenceSelector": "PCGBegin(@Last)PCGEnd", "bSelectMultiple": False,
                              "bIgnoreSelfAndChildren": False}}


def build(stage_numbers=None):
    numbers = list(stage_numbers or [s[0] for s in stages.STAGES])
    parts = {n: graphs.graph(n) for n in numbers}
    params = [_rename_param(p, n) for n in numbers for p in parts[n]._params]
    g = dsl.Graph(NAME, params=params, description=__doc__.strip().split("\n\n")[0])
    outputs = {}                  # stage -> [[node, pin], ...] its Output node received
    terrain = {"get": {}, "write": {}}
    report = {"refs_rewired": [], "refs_kept": [], "self_reads": [], "dropped": []}
    for n in numbers:
        part = parts[n]
        prefix = "s%02d_" % n
        getters = {rec["name"]: rec["getter_param"] for rec in part._nodes if rec.get("getter_param")}
        io = {_ir.IN_NODE, _ir.OUT_NODE}
        outputs[n] = []           # a stage may publish nothing (14 Parkings: only spawned instances)

        def src_of(edge):
            node, pin = edge
            if node == _ir.IN_NODE:
                raise ValueError("stage %d reads its graph input node, which a merged graph cannot feed" % n)
            if node in getters and pin.lower() == getters[node].lower():
                pin = pname(n, getters[node])
            return [prefix + node, pin]

        for rec in part._nodes:
            if rec["name"] == _ir.OUT_NODE:
                for p in rec["inputs"]:
                    outputs.setdefault(n, []).extend(src_of(e) for e in p["edges"])
            if rec["name"] in io:
                continue
            new = copy.deepcopy(rec)
            new["name"] = prefix + rec["name"]
            new["step"] = "%s | %s" % (category(n), rec["step"]) if rec.get("step") else category(n)
            new["inputs"] = [{"label": p["label"], "edges": [src_of(e) for e in p["edges"]]} for p in rec["inputs"]]
            if rec.get("getter_param"):
                new["getter_param"] = pname(n, rec["getter_param"])
                new["title"] = new["getter_param"]
            elif rec.get("title"):
                new["title"] = "[%02d] %s" % (n, rec["title"])
            alias = _alias(rec)
            if alias == REF:
                roles = rec["overrides"]["ActorReferences"].names
                if all(r in STAGE_ROLES for r in roles):
                    if any(p["edges"] for p in rec["inputs"]):
                        raise ValueError("stage %d: %s has wired inputs; cannot turn it into a Gather" % (n, rec["title"]))
                    ups = [STAGE_ROLES[r] for r in roles]
                    missing = [u for u in ups if u not in outputs]
                    if missing:
                        raise ValueError("stage %d reads stage(s) %s, which are not merged before it" % (n, missing))
                    new.update({"class": "PCGGatherSettings", "settings": {}, "inputs": [
                        {"label": "In", "edges": [list(e) for u in ups for e in outputs[u]]}]})
                    for k in ("subgraph", "overrides", "pin_defaults"):
                        new.pop(k, None)
                    report["refs_rewired"].append([n, rec["title"], ups])
                elif any(r in STAGE_ROLES for r in roles):
                    raise ValueError("stage %d: %s mixes stage and control roles %s" % (n, rec["title"], roles))
                else:
                    report["refs_kept"].append([n, rec["title"], roles])
            if rec["class"] == _ir.SELF_NODE:
                if n not in CONTROL_TAGS:
                    raise ValueError("stage %d reads its own volume; give it a control tag in CONTROL_TAGS" % n)
                new["settings"] = _actor_selector(CONTROL_TAGS[n])
                new["title"] = "[%02d] Get %s (control actor)" % (n, CONTROL_TAGS[n])
                report["self_reads"].append([n, CONTROL_TAGS[n]])
            if alias == TERRAIN_GET:
                terrain["get"].setdefault(n, []).append(new["name"])
            elif alias == TERRAIN_WRITE:
                terrain["write"].setdefault(n, []).append(new["name"])
            g._nodes.append(new)

    by_name = {rec["name"]: rec for rec in g._nodes}

    def depend(target, sources):
        if not sources:
            return
        rec = by_name[target]
        entry = next((p for p in rec["inputs"] if p["label"] == DEP_PIN), None)
        if entry is None:
            entry = {"label": DEP_PIN, "edges": []}
            rec["inputs"].append(entry)
        for s in sources:
            if [s, "Out"] not in entry["edges"]:
                entry["edges"].append([s, "Out"])

    for n in numbers:
        earlier = [m for m in numbers if m < n]
        for node in terrain["get"].get(n, []):
            depend(node, [w for m in earlier for w in terrain["write"].get(m, [])])
        for node in terrain["write"].get(n, []):
            depend(node, [q for m in earlier for q in terrain["get"].get(m, [])])

    for n in numbers:
        for node, pin in outputs.get(n, []):
            g.output._rec["inputs"] = g.output._rec["inputs"] or [{"label": "Out", "edges": []}]
            g.output._rec["inputs"][0]["edges"].append([node, pin])
    g.report = report
    g.terrain = terrain
    g.stage_outputs = outputs
    return g


def banded_positions(ir, band_of, dx=480, dy=200, gap=3):
    """Offline half of the merged graph's layout: {node: (x, y)} plus {band: (x0, y0, x1, y1)}.
    Each band (a stage) is a horizontal strip laid out like a slim graph -- columns by longest path inside
    the band, rows in description order -- and the strips are stacked top to bottom in band order."""
    nodes = {n["name"]: n for n in ir["nodes"]}
    depth = {}

    def d(name, stack=()):
        if name not in depth:
            srcs = [e[0] for p in nodes[name].get("inputs", []) for e in p["edges"]
                    if e[0] in nodes and e[0] not in stack and band_of(e[0]) == band_of(name)]
            depth[name] = 1 + max((d(s, stack + (name,)) for s in srcs), default=-1)
        return depth[name]

    bands = []
    for n in ir["nodes"]:
        b = band_of(n["name"])
        if b is not None and b not in bands:
            bands.append(b)
    pos, boxes, y0 = {}, {}, 0
    for b in bands:
        rows = {}
        for n in ir["nodes"]:
            if band_of(n["name"]) != b:
                continue
            k = d(n["name"])
            i = rows.get(k, 0)
            rows[k] = i + 1
            pos[n["name"]] = (k * dx, y0 + i * dy)
        height = max(rows.values()) * dy
        boxes[b] = (-dx // 2, y0 - dy, (max(rows) + 1) * dx, y0 + height)
        y0 += height + gap * dy
    width = max(x for x, _ in pos.values()) if pos else 0
    for n in ir["nodes"]:
        if n["name"] not in pos:                         # the graph's input and output nodes
            pos[n["name"]] = (-2 * dx, 0) if n["name"] == _ir.IN_NODE else (width + 2 * dx, 0)
    return pos, boxes


def component_overrides(per_stage):
    """{graph name: {param: value}} (one volume's overrides per stage) -> the merged graph's names."""
    out = {}
    for s in stages.STAGES:
        for k, v in (per_stage.get(s[1]) or {}).items():
            out[pname(s[0], k)] = v
    return out


def band_of(node_name):
    """The stage a merged node belongs to ("s07_n52" -> 7); None for the graph's input/output nodes."""
    m = re.match(r"s(\d\d)_", node_name)
    return int(m.group(1)) if m else None


def positions(ir):
    return banded_positions(ir, band_of)


def titles():
    return {s[0]: "%02d  %s  %s" % (s[0], short(s[0]), s[3]) for s in stages.STAGES}
