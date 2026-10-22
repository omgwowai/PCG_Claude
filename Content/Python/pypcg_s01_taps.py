# pypcg_s01_taps.py -- stage 1 (Task 24): the official graph and the slim graph, each as a TAP graph, generated on a
# SPAWNED probe actor with the stage-1 volume's transform, so nothing is written to the terrain and the stage-1
# volume is untouched. This is the comparison behind s01.md 6 (every written point bit for bit); it needs no engine
# booleans and no stage volume.
#   {"variant": "official"}                 -> /Game/PyPCG/Probe/PCG_T24Tap, the official graph's 16 taps
#   {"variant": "slim"}                     -> /Game/PyPCG/Probe/PCG_T24SlimTap, the slim graph's six outputs (with
#                                              WriteMeshTerrain_0 and the output node removed)
#   {"read": true, "out": "E:/PCG_Claude/Saved/t24/tap_a.json", "fields": ["loc", "attrs"]}
#                                           -> every tap as {tag: [item]}; a later call (trap 38)
#   {"remove": true}                        -> destroy the probe actor
# The taps share their tag names between the two variants (tNN_ official, vNN_ slim), so `pypcg_s01_compare.py`
# lines them up. Then `pypcg_compare_stage.py {"phase": "restore"}` / a `gen official` is good hygiene: only the
# spawned probe actor was ever given a graph, and it is destroyed by {"remove": true}.
import json
import os
import sys

import unreal

for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]

LABEL = "T24_TapProbe"
OFFICIAL_PATH = "/Game/PyPCG/Probe/PCG_T24Tap"
SLIM_PATH = "/Game/PyPCG/Probe/PCG_T24SlimTap"
OFFICIAL_TAPS = (("ExtractMeshTerrainPoints_0", "Out", "t01_extract"),
                 ("SpatialNoise_Hills", "Out", "t02_noise"),
                 ("Subgraph_1", "Out", "t03_bounds"),
                 ("TraceBoundFootprint_TerrainShaping1", "Out", "t04_footprint"),
                 ("Subgraph_2", "Out", "t05_expand"),
                 ("Subgraph_0", "Out", "t06_square"),
                 ("GetActorData_TerrainShaping1", "Out", "t07_circle_raw"),
                 ("Subgraph_6", "Out", "t08_circle"),
                 ("ComposeExclusion_SquareMinusCircle", "Out", "t09_annulus"),
                 ("FlattenProject_AroundCircle", "Out", "t10_flat_annulus"),
                 ("Subgraph_3", "Out", "t11_city_raw"),
                 ("AttributeMathsOp_2", "Out", "t12_city_z0"),
                 ("Subgraph_4", "Out", "t13_city_up"),
                 ("Subgraph_5", "Out", "t14_city_proj"),
                 ("AttributeMathsOp_1", "Out", "t15_ratio"),
                 ("AttributeMathsOp_0", "Out", "t16_lerp"))
SLIM_TAPS = (("s01_terrain", "FlattenArea", "v09_annulus"), ("s01_terrain", "CityFlatZone", "v13_city_up"),
             ("Hills Noise", "Out", "v02_noise"), ("Flatten Around Circle (Falloff)", "Out", "v10_flat_annulus"),
             ("Project City Flat Zone", "Out", "v14_city_proj"), ("s01_terrain_blend", "Terrain", "v16_lerp"))


def _io(name, seed, pins):
    return {"name": name, "class": "PCGGraphInputOutputSettings", "title": "", "settings": {"Seed": seed, "Pins": pins},
            "comment": "", "bubble_visible": False, "bubble_pinned": False, "inputs": [], "pin_defaults": [],
            "getter_param": "", "pos": None}


def _pin(label):
    return {"Label": label, "PinStatus": "Normal", "Tooltip": "", "Usage": "Normal", "bAllowMultipleConnections": True,
            "bAllowMultipleData": True, "bInvisiblePin": False,
            "AllowedTypes": {"CustomSubtype": -1, "Ids": [{"Struct": "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfo'"}]}}


def _probe(spawn=False):
    from pypcg import census
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        try:
            if str(a.get_actor_label()) == LABEL:
                return a.get_component_by_class(unreal.PCGComponent)
        except Exception:
            continue
    if not spawn:
        raise RuntimeError("no tap probe actor; build a variant first")
    t = census.volume(1).get_actor_transform()          # the stage-1 volume's transform, and its scale
    a = eas.spawn_actor_from_class(unreal.PCGVolume, t.translation, t.rotation.rotator())
    a.set_actor_label(LABEL)
    a.set_actor_scale3d(t.scale3d)
    return a.get_component_by_class(unreal.PCGComponent)


def _generate(path, taps):
    from pypcg import census
    pc = _probe(spawn=True)
    pc.set_graph(unreal.EditorAssetLibrary.load_asset(path))
    vol = census.component(1)
    values = dict(census.overrides(vol))               # the demo's CityFlatness 0.6000000238418579, HillsHeight 7001
    census.apply_overrides(pc, values)
    pc.set_editor_property("seed", int(vol.get_editor_property("seed")))
    pc.set_editor_property("regenerate_in_editor", False)
    pc.activate(True)
    pc.generate_local(True)
    return {"graph": path, "taps": len(taps), "overrides": values}


def build_official(args):
    from pypcg import build as B, extract, ir as _ir, stages
    off = extract.export(unreal.EditorAssetLibrary.load_asset(stages.official_path(1)))
    by = {x["name"]: x for x in off["nodes"]}
    keep = set()
    todo = [t[0] for t in OFFICIAL_TAPS]
    while todo:                                        # every node upstream of a tap
        k = todo.pop()
        if k in keep or k not in by:
            continue
        keep.add(k)
        for p in by[k].get("inputs", []):
            todo += [e[0] for e in p["edges"]]
    keep.discard("DefaultOutputNode")
    nodes = [_io("DefaultInputNode", by["DefaultInputNode"]["settings"]["Seed"], [_pin("In")])]
    for name in sorted(keep):
        x = json.loads(json.dumps(by[name]))
        x["inputs"] = [{"label": p["label"], "edges": [e for e in p["edges"] if e[0] in keep]}
                       for p in x.get("inputs", [])]
        x["inputs"] = [p for p in x["inputs"] if p["edges"]]
        x["pos"] = None
        for field in ("settings", "overrides", "pin_defaults"):
            if field in x:
                x[field] = _ir.node_refs_to_names(x[field], off["graph"])
        nodes.append(x)
    edges = []
    for node, pin_name, tag in OFFICIAL_TAPS:
        nodes.append({"name": "Tap_" + tag, "class": "PCGAddTagSettings", "title": "",
                      "settings": {"Seed": 0, "TagsToAdd": tag}, "comment": "", "bubble_visible": False,
                      "bubble_pinned": False, "inputs": [{"label": "In", "edges": [[node, pin_name]]}],
                      "pin_defaults": [], "getter_param": "", "pos": None})
        edges.append(["Tap_" + tag, "Out"])
    out = _io("DefaultOutputNode", by["DefaultOutputNode"]["settings"]["Seed"], [_pin("Out")])
    out["inputs"] = [{"label": "Out", "edges": edges}]
    nodes.append(out)
    ir = {"schema": off["schema"], "graph": "PCG_T24Tap", "graph_props": {}, "params": list(off["params"]),
          "comment_boxes": [], "nodes": nodes, "sites": []}
    diffs = B.build_slim(ir, OFFICIAL_PATH, save=True)
    if diffs:
        return {"abort": [str(d) for d in diffs[:5]]}
    return _generate(OFFICIAL_PATH, OFFICIAL_TAPS)


def build_slim(args):
    from pypcg import build as B, graphs, stage_api
    from pypcg.profiles import official as prof
    ir = graphs.graph(1).to_ir(prof)
    by_title = {(n.get("title") or "").replace("Python: ", ""): n["name"] for n in ir["nodes"]}
    write = by_title["Write Mesh Terrain"]
    ir["nodes"] = [n for n in ir["nodes"] if n["name"] != write]
    out = next(n for n in ir["nodes"] if n["name"] == "DefaultOutputNode")
    edges = []
    for title, pin, tag in SLIM_TAPS:
        ir["nodes"].append({"name": "Tap_" + tag, "class": "PCGAddTagSettings", "title": "",
                            "settings": {"TagsToAdd": tag}, "comment": "", "bubble_visible": False,
                            "bubble_pinned": False, "inputs": [{"label": "In", "edges": [[by_title[title], pin]]}],
                            "pin_defaults": [], "getter_param": "", "pos": None})
        edges.append(["Tap_" + tag, "Out"])
    out["inputs"] = [{"label": "Out", "edges": edges}]
    diffs = B.build_slim(ir, SLIM_PATH, save=True)
    if diffs:
        return {"abort": [str(d) for d in diffs[:5]]}
    res = _generate(SLIM_PATH, SLIM_TAPS)
    res["nodes"] = len(ir["nodes"])
    return res


def full(value, cls, cap):
    """A tap as plain JSON: a point set's columns up to `cap` points, else its bbox and count."""
    from pypcg import geo
    if value is None:
        return {"class": cls, "kind": "none"}
    if hasattr(value, "height"):
        return {"class": cls, "kind": "Terrain"}
    if isinstance(value, geo.Points):
        n = len(value)
        d = {"class": cls, "kind": "points", "n": n, "types": dict(value.types), "bbox": _bbox(value.loc)}
        if n <= cap:
            for c in geo.Points.COLUMNS:
                d[c] = [list(x) if isinstance(x, tuple) else x for x in getattr(value, c)]
            d["attrs"] = {k: [list(x) if isinstance(x, tuple) else x for x in col] for k, col in value.attrs.items()}
            if value.quat:
                d["quat"] = [list(q) for q in value.quat]
        return d
    j = geo.to_json(value)
    j["class"] = cls
    return j


def _bbox(pts):
    if not pts:
        return None
    return [[min(p[k] for p in pts) for k in range(3)], [max(p[k] for p in pts) for k in range(3)]]


def read(args):
    from pypcg.ue import convert
    pc = _probe()
    cap = int(args.get("cap", 400000))
    rows = {}
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        tags = [str(t) for t in td.get_editor_property("tags")]
        keep = [t for t in tags if len(t) > 4 and t[0] in "tuvw" and t[1:3].isdigit() and t[3] == "_"]
        if args.get("only"):
            keep = [t for t in keep if any(t.startswith(p) for p in args["only"])]
        if not keep:
            continue
        d = td.get_editor_property("data").get_editor_property("data")
        try:
            j = full(convert.from_pcg(d), d.get_class().get_name(), cap)
        except Exception as e:          # noqa: BLE001 -- report, never fail the read
            j = {"class": d.get_class().get_name(), "error": "%s: %s" % (type(e).__name__, e)}
        if args.get("fields") and j.get("kind") == "points":
            j = {k: v for k, v in j.items() if k in args["fields"] or k in ("class", "kind", "n", "types", "bbox")}
        j["tags"] = tags
        for t in keep:
            rows.setdefault(t, []).append(j)
    path = args["out"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    return {"written": path, "taps": {k: [(x.get("kind"), x.get("n"), x.get("class")) for x in v][:12]
                                     for k, v in rows.items()}}


def remove(args):
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        try:
            if str(a.get_actor_label()) == LABEL:
                return {"removed": eas.destroy_actor(a)}
        except Exception:
            continue
    return {"removed": False}


def main(args):
    from pypcg import level
    # Final review I2: the probe actor is spawned into the current level at the stage-1 volume's transform;
    # the measurements behind s01.md were taken on the demo, and nowhere else may receive the actor.
    refused = level.require(level.DEMO, "pypcg_s01_taps.py")
    if refused:
        return refused
    if args.get("read"):
        return read(args)
    if args.get("remove"):
        return remove(args)
    return {"slim": build_slim, "official": build_official}[args.get("variant", "official")](args)


try:
    mcp_result = json.loads(json.dumps(main(mcp_args or {}), default=str))
except Exception as _exc:                     # noqa: BLE001 -- the bridge reports, the probe does not raise
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
