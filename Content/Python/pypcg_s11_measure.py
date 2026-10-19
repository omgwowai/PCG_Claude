# pypcg_s11_measure.py -- stage 11 (Task 20): tap the OFFICIAL PCG_3_3_1_Buildings' intermediate data on the
# stage-11 volume of the demo level, for Tools/pypcg/s11_measure_offline.py and the s11.md measurements.
# {"step": "gen", "graph": "a", "taps": {name: [node, pin]}, "extract": {name: [node, pin, selector]},
#  "nodes": {name: [class, settings, [node, pin]]}}
#     builds /Game/PyPCG/Probe/PCG_T20Tap_<graph> (the official nodes upstream of the taps, one AddTag per tap,
#     an ExtractAttribute per extract, any extra node) from the official IR snapshot, puts it on the stage-11
#     volume (shipped overrides and seed) and generates. Restore afterwards (gen official / restore).
# {"step": "read", "label": name}  reads every tap -> Saved/t20/tap_<label>.json: polygons as raw per-vertex
#     world xyz, the data's transform and the ToPoint vertices (`vp`); splines as control points, transform
#     and local points with rotations (`sp`); param data as rows.
# The taps behind s11.md 6 (labels a and e) and the oracle switch are listed in s11.md 6.1.
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
STAGE = 11


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


def gen(args):
    from pypcg import build as B, census, ir as _ir, stages
    taps = args.get("taps") or {}
    extracts = args.get("extract") or {}
    graph = "/Game/PyPCG/Probe/PCG_T20Tap_%s" % args.get("graph", "a")
    off = _ir.load(os.path.join(_REPO, "Tools", "pypcg", "official_ir", stages.name(STAGE) + ".json"))
    keep = set()
    for node, _pin in taps.values():
        keep |= _upstream(off["nodes"], node)
    for node, _pin, _sel in extracts.values():
        keep |= _upstream(off["nodes"], node)
    extras = args.get("nodes") or {}
    for _cls, _set, (node, _pin) in extras.values():
        keep |= _upstream(off["nodes"], node)
    keep.discard("DefaultInputNode")
    keep.discard("DefaultOutputNode")
    by = {x["name"]: x for x in off["nodes"]}
    nodes = [_io_node("DefaultInputNode", by["DefaultInputNode"]["settings"]["Seed"], "In")]
    for name in sorted(keep):
        x = json.loads(json.dumps(by[name]))
        x["inputs"] = [{"label": p["label"], "edges": [e for e in p["edges"] if e[0] in keep]}
                       for p in x.get("inputs", [])]
        x["inputs"] = [p for p in x["inputs"] if p["edges"]]
        x["pos"] = None
        for field in ("settings", "overrides", "pin_defaults"):
            if field in x:
                x[field] = _ir.node_refs_to_names(x[field], off["graph"])
        if name in (args.get("set") or {}):
            x["overrides"] = dict(x.get("overrides") or {}, **args["set"][name])
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
    for tag, (cls, settings, (node, pin)) in extras.items():
        e = _node(tag + "_n", cls, settings)
        e["inputs"] = [{"label": "In", "edges": [[node, pin]]}]
        nodes.append(e)
        t = _node(tag, "PCGAddTagSettings", {"TagsToAdd": tag})
        t["inputs"] = [{"label": "In", "edges": [[tag + "_n", "Out"]]}]
        nodes.append(t)
        tags.append(tag)
    out = _io_node("DefaultOutputNode", by["DefaultOutputNode"]["settings"]["Seed"], "Out")
    out["inputs"] = [{"label": "Out", "edges": [[t, "Out"] for t in tags]}]
    nodes.append(out)
    ir = {"schema": off["schema"], "graph": stages.name(STAGE) + "_T20Tap", "graph_props": {},
          "params": [p for p in off["params"]], "comment_boxes": [], "nodes": nodes, "sites": []}
    diffs = B.build_slim(ir, graph, save=True)
    if diffs:
        return {"abort": "tap graph differs", "diffs": [str(x) for x in diffs[:5]]}
    pc = census.component(STAGE)
    state = json.load(open(os.path.join(_REPO, "Saved", "Reports", "v2", "_state.json"), encoding="utf-8"))
    shipped = state.get(stages.name(STAGE), {})
    pc.set_graph(unreal.EditorAssetLibrary.load_asset(graph))
    if shipped.get("overrides"):
        census.apply_overrides(pc, shipped["overrides"])
    for k, v in (args.get("params") or {}).items():
        census.apply_overrides(pc, {k: v})
    pc.set_editor_property("seed", int(args.get("component_seed", shipped.get("seed", 42))))
    pc.activate(True)
    if args.get("no_generate"):
        return {"graph": graph, "nodes": len(nodes), "taps": len(tags)}
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


def read(args):
    from pypcg import census, geo
    from pypcg.ue import convert
    L = unreal.PyPCGToolsLibrary
    pc = census.component(STAGE)
    g = pc.get_graph()
    if g is None or "/PyPCG/Probe/PCG_T20" not in g.get_path_name():
        return {"abort": "volume does not hold a tap graph: %s" % (g.get_path_name() if g else None)}
    out, counts = {}, {}
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        tags = [str(t) for t in td.get_editor_property("tags")]
        tap = next((t for t in tags if t.startswith("T_")), None)
        if tap is None:
            continue
        d = td.get_editor_property("data").get_editor_property("data")
        cls = d.get_class().get_name()
        rec = {"class": cls, "tags": [t for t in tags if t != tap]}
        if isinstance(d, unreal.PCGPolygon2DData):
            rec["raw"] = json.loads(L.polygon2d_to_json(d))
            rec["xf"] = _transform(d)
            vp = []
            for i in range(d.get_num_segments()):
                v = d.get_location_at_distance(i, 0.0, True)
                vp.append([v.x, v.y, v.z])
            rec["vp"] = vp
        elif isinstance(d, unreal.PCGSplineData):
            rec["raw"] = json.loads(L.spline_data_to_json(d, 1.0))
            rec["xf"] = _transform(d)
            rec["sp"] = [[[sp.position.x, sp.position.y, sp.position.z],
                          [sp.rotation.pitch, sp.rotation.yaw, sp.rotation.roll]] for sp in d.get_spline_points()]
        elif isinstance(d, unreal.PCGParamData):
            md = d.const_metadata()
            rows = []
            n = md.get_item_count_for_child() if hasattr(md, "get_item_count_for_child") else 1
            try:
                n = max(1, int(md.get_local_item_count()))
            except Exception:
                pass
            for k in range(n):
                rows.append(convert.entry_values(md, k))
            rec["rows"] = rows
        else:
            try:
                v = convert.from_pcg(d)
                rec["v"] = geo.to_json(v)
            except TypeError:
                rec["unreadable"] = True
        out.setdefault(tap, []).append(rec)
        counts[tap] = counts.get(tap, 0) + 1
    path = os.path.join(_REPO, "Saved", "t20", "tap_%s.json" % args.get("label", "official"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    return {"written": path, "counts": counts}


try:
    _a = mcp_args or {}
    if _a.get("step") == "oracle":
        # {"step": "oracle", "on": bool}: the official Write_Noise draws (Tools/pypcg/data/s11_official_noise.json)
        # for the slim graph's next generations in this editor process (s11_buildings.ORACLE_ENV); off again after
        _path = os.path.join(_REPO, "Tools", "pypcg", "data", "s11_official_noise.json")
        if _a.get("on"):
            os.environ["PYPCG_S11_ORACLE"] = _path
        else:
            os.environ.pop("PYPCG_S11_ORACLE", None)
        mcp_result = {"PYPCG_S11_ORACLE": os.environ.get("PYPCG_S11_ORACLE")}
    else:
        mcp_result = json.loads(json.dumps(gen(_a) if _a.get("step") == "gen" else read(_a), default=str))
except Exception as _exc:
    import traceback
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600]), "tb": traceback.format_exc()[-1500:]}
gc.collect()
