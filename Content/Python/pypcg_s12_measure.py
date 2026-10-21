# pypcg_s12_measure.py -- stage 12 (Task 21): tap the OFFICIAL PCG_3_3_2_Rooftops' intermediate data on the
# stage-12 volume of the demo level, for Tools/pypcg/s12_measure_offline.py and the s12.md measurements.
# {"step": "gen", "graph": "a", "taps": {name: [node, pin]}, "extract": {name: [node, pin, selector]}}
#     builds /Game/PyPCG/Probe/PCG_T21Tap_<graph> (the official nodes upstream of the taps, one AddTag per tap,
#     an ExtractAttribute per extract) from the official IR snapshot, puts it on the stage-12 volume (shipped
#     overrides and seed) and generates. Restore afterwards (gen official / restore).
#     {"step": "gen", "slim": true, ...} taps the SLIM graph's description instead (pypcg.graphs.s12_rooftops,
#     official profile): the same node names as the slim build, so the Python nodes' outputs and the kept fill
#     nodes' outputs can be read side by side with the official ones.
# {"step": "read", "label": name}  reads every tap -> Saved/t21/tap_<label>.json: polygons as raw per-vertex
#     world xyz, the data's transform and the ToPoint vertices (`vp`); splines as control points, transform and
#     rotations (`sp`); points as every column, the engine quaternions and every attribute; param data as rows.
import gc
import json
import os
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
STAGE = 12
OUT_DIR = os.path.join(_REPO, "Saved", "t21")


def _upstream(nodes, name):
    by = {x["name"]: x for x in nodes}
    seen, todo = set(), [name]
    while todo:
        k = todo.pop()
        if k in seen or k not in by:
            continue
        seen.add(k)
        for p in by[k].get("inputs", []):
            todo += [e[0] for e in p["edges"]]
    return seen


def _io_node(name, seed, label):
    pin = {"Label": label, "PinStatus": "Normal", "Tooltip": "", "Usage": "Normal",
           "bAllowMultipleConnections": True, "bAllowMultipleData": True, "bInvisiblePin": False,
           "AllowedTypes": {"CustomSubtype": -1,
                            "Ids": [{"Struct": "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfo'"}]}}
    return {"name": name, "class": "PCGGraphInputOutputSettings", "title": "",
            "settings": {"Seed": seed, "Pins": [pin], "bHasAddedDefaultPin": True}, "comment": "",
            "bubble_visible": False, "bubble_pinned": False, "inputs": [], "pin_defaults": [],
            "getter_param": "", "pos": None}


def _node(name, cls, settings):
    s = {"Seed": 0}
    s.update(settings)
    return {"name": name, "class": cls, "title": "", "settings": s,
            "comment": "", "bubble_visible": False, "bubble_pinned": False, "inputs": [], "pin_defaults": [],
            "getter_param": "", "pos": None}


def _source_ir(slim):
    from pypcg import ir as _ir, stages
    if not slim:
        return _ir.load(os.path.join(_REPO, "Tools", "pypcg", "official_ir", stages.name(STAGE) + ".json"))
    from pypcg import graphs
    from pypcg.profiles import official as prof
    return graphs.graph(STAGE).to_ir(prof)


def gen(args):
    from pypcg import build as B, census, ir as _ir, stages
    taps = args.get("taps") or {}
    extracts = args.get("extract") or {}
    slim = bool(args.get("slim"))
    graph = "/Game/PyPCG/Probe/PCG_T21Tap_%s" % args.get("graph", "a")
    off = _source_ir(slim)
    keep = set()
    for node, _pin in taps.values():
        keep |= _upstream(off["nodes"], node)
    for node, _pin, _sel in extracts.values():
        keep |= _upstream(off["nodes"], node)
    keep.discard("DefaultInputNode")
    keep.discard("DefaultOutputNode")
    by = {x["name"]: x for x in off["nodes"]}
    nodes = [_io_node("DefaultInputNode", (by["DefaultInputNode"].get("settings") or {}).get("Seed", 0), "In")]
    for name in sorted(keep):
        x = json.loads(json.dumps(by[name]))
        x["inputs"] = [{"label": p["label"], "edges": [e for e in p["edges"] if e[0] in keep]}
                       for p in x.get("inputs", [])]
        x["inputs"] = [p for p in x["inputs"] if p["edges"]]
        x["pos"] = None
        if not slim:
            for field in ("settings", "overrides", "pin_defaults"):
                if field in x:
                    x[field] = _ir.node_refs_to_names(x[field], off["graph"])
        nodes.append(x)
    tags = []
    for tag, (node, pin) in taps.items():
        t = _node(tag, "PCGAddTagSettings", {"TagsToAdd": tag})
        t["inputs"] = [{"label": "In", "edges": [[node, pin]]}]
        nodes.append(t)
        tags.append(tag)
    for tag, (node, pin, sel) in extracts.items():
        e = _node(tag + "_x", "PCGExtractAttributeSettings", {"InputSource": "PCGBegin(%s)PCGEnd" % sel})
        e["inputs"] = [{"label": "In", "edges": [[node, pin]]}]
        nodes.append(e)
        t = _node(tag, "PCGAddTagSettings", {"TagsToAdd": tag})
        t["inputs"] = [{"label": "In", "edges": [[tag + "_x", "Out"]]}]
        nodes.append(t)
        tags.append(tag)
    out = _io_node("DefaultOutputNode", (by["DefaultOutputNode"].get("settings") or {}).get("Seed", 0), "Out")
    out["inputs"] = [{"label": "Out", "edges": [[t, "Out"] for t in tags]}]
    nodes.append(out)
    ir = {"schema": off["schema"], "graph": stages.name(STAGE) + "_T21Tap", "graph_props": {},
          "params": [p for p in off["params"]], "comment_boxes": [], "nodes": nodes, "sites": []}
    diffs = B.build_slim(ir, graph, save=True)
    if diffs:
        return {"abort": "tap graph differs", "diffs": [str(x) for x in diffs[:5]]}
    pc = census.component(STAGE)
    state = json.load(open(os.path.join(_REPO, "Saved", "Reports", "v2", "_state.json"), encoding="utf-8"))
    shipped = state.get(stages.name(STAGE), {})
    pc.set_graph(unreal.EditorAssetLibrary.load_asset(graph))
    if shipped.get("overrides") and not slim:
        census.apply_overrides(pc, shipped["overrides"])
    pc.set_editor_property("seed", int(args.get("component_seed", shipped.get("seed", 42))))
    pc.activate(True)
    pc.generate_local(True)
    return {"graph": graph, "nodes": len(nodes), "taps": len(tags), "restore_required": True}


def _transform(d):
    try:
        t = d.get_transform()
    except Exception:
        return None
    q = t.rotation
    return {"t": [t.translation.x, t.translation.y, t.translation.z], "q": [q.x, q.y, q.z, q.w],
            "s": [t.scale3d.x, t.scale3d.y, t.scale3d.z]}


def _points(d):
    from pypcg.ue import convert
    p = convert.points_of(d)
    cols = {c: [list(x) if isinstance(x, tuple) else x for x in getattr(p, c)] for c in p.COLUMNS}
    return {"n": len(p), "types": dict(p.types), "cols": cols, "quat": [list(q) for q in (p.quat or [])],
            "attrs": {k: list(v) for k, v in p.attrs.items()}}


def read(args):
    from pypcg import census
    from pypcg.ue import convert
    L = unreal.PyPCGToolsLibrary
    pc = census.component(STAGE)
    g = pc.get_graph()
    if g is None or "/PyPCG/Probe/PCG_T21" not in g.get_path_name():
        return {"abort": "volume does not hold a tap graph: %s" % (g.get_path_name() if g else None)}
    out, counts = {}, {}
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        tags = [str(t) for t in td.get_editor_property("tags")]
        tap = next((t for t in tags if t.startswith("T_") or t.startswith("X_")), None)
        if tap is None:
            continue
        d = td.get_editor_property("data").get_editor_property("data")
        cls = d.get_class().get_name()
        rec = {"class": cls, "tags": [t for t in tags if t != tap]}
        if isinstance(d, unreal.PCGPolygon2DData):
            rec["raw"] = json.loads(L.polygon2d_to_json(d))
            rec["xf"] = _transform(d)
            rec["vp"] = [[v.x, v.y, v.z] for v in (d.get_location_at_distance(i, 0.0, True)
                                                   for i in range(d.get_num_segments()))]
        elif isinstance(d, unreal.PCGSplineData):
            rec["raw"] = json.loads(L.spline_data_to_json(d, 1.0))
            rec["xf"] = _transform(d)
            rec["sp"] = [[[sp.position.x, sp.position.y, sp.position.z],
                          [sp.rotation.pitch, sp.rotation.yaw, sp.rotation.roll], int(sp.type.value)]
                         for sp in d.get_spline_points()]
        elif isinstance(d, unreal.PCGParamData):
            md = d.const_metadata()
            try:
                n = max(1, int(md.get_local_item_count()))
            except Exception:
                n = 1
            rec["rows"] = [convert.entry_values(md, k) for k in range(n)]
        elif isinstance(d, unreal.PCGBasePointData):
            rec["points"] = _points(d)
        else:
            rec["unreadable"] = True
        out.setdefault(tap, []).append(rec)
        counts[tap] = counts.get(tap, 0) + 1
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "tap_%s.json" % args.get("label", "official"))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    return {"written": path, "counts": counts,
            "points": {k: sum(r.get("points", {}).get("n", 0) for r in v) for k, v in out.items()
                       if any("points" in r for r in v)}}


try:
    _a = mcp_args or {}
    from pypcg import level as _level
    # Final review I2: the tap graph goes onto the stage-12 volume, so only the demo's volume may get it.
    mcp_result = _level.require(_level.DEMO, "pypcg_s12_measure.py") or \
        json.loads(json.dumps(gen(_a) if _a.get("step") == "gen" else read(_a), default=str))
except Exception as _exc:
    import traceback
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600]), "tb": traceback.format_exc()[-1500:]}
gc.collect()
