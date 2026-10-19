# pypcg_s10_measure.py -- stage 10 (Task 17): the measurements behind docs/pypcg/stages/s10.md, taken against
# the OFFICIAL graph on the demo level's stage-10 volume. One bridge call per step; nothing is saved but the
# tap graph asset (/Game/PyPCG/Probe/PCG_T17Tap) and files under Saved/Reports/v2/s10/.
#   {"step": "gen"}                 build the tap graph (the official nodes upstream of 13 taps, from the IR
#                                   snapshot) and generate it on the stage-10 volume -- restore the volume
#                                   afterwards (`pypcg_compare_stage.py` gen official, or restore)
#   {"step": "read"}                every tap -> Saved/Reports/v2/s10/tap_official.json
#   {"step": "tiles", "budget": n}  (tap graph generated) the port's fill on the OFFICIAL ground pieces and its
#                                   terrain fit on the OFFICIAL fill, point for point -> tilecmp.json
#   {"step": "pieces"}              the port's buildable pieces from the recorded run's inputs (Saved/PyPCG/runs
#                                   /s10.json) against the official ones -> pieces.json
#   {"step": "nontile"}             the port's sidewalk / corner / railing values from the recorded inputs
#                                   -> nontile_outputs.json (compared offline with tap_official.json)
#   {"step": "corners", "as": name} the volume's spawned corner instances -> corners_<name>.json
# Distilled into Tools/pypcg/data/s10_official_measurements.json.
import gc
import json
import os
import sys
import time

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
_OUT = os.path.join(_REPO, "Saved", "Reports", "v2", "s10")
GRAPH = "/Game/PyPCG/Probe/PCG_T17Tap"
# tap name -> (official node, its output pin)
TAPS = {"T_tiles": ("Subgraph_40", "Out"), "T_cornersA": ("Branch_1", "Output A"),
        "T_landmark": ("Subgraph_46", "Out"), "T_lotsegs": ("Subgraph_8", "Out"),
        "T_lmsegs": ("Subgraph_4", "Out"), "T_rail": ("Subgraph_19", "Out"), "T_ground": ("Subgraph_10", "Out"),
        "T_bound": ("Subgraph_49", "Out"), "T_city": ("Subgraph_23", "Out"), "T_fill": ("Subgraph_9", "Out"),
        "T_terrain": ("Subgraph_39", "Out"), "T_artery": ("AttributeMathsOp_1", "Out"),
        "T_pieces": ("Subgraph_22", "Out")}


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


def _tag_node(name):
    return {"name": name, "class": "PCGAddTagSettings", "title": "", "settings": {"Seed": 0, "TagsToAdd": name},
            "comment": "", "bubble_visible": False, "bubble_pinned": False, "inputs": [], "pin_defaults": [],
            "getter_param": "", "pos": None}


def gen():
    from pypcg import build as B, census, ir as _ir, stages
    off = _ir.load(os.path.join(_REPO, "Tools", "pypcg", "official_ir", stages.name(10) + ".json"))
    keep = set()
    for node, _pin in TAPS.values():
        keep |= _upstream(off["nodes"], node)
    keep.discard("DefaultInputNode")
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
        nodes.append(x)
    for tag, (node, pin) in TAPS.items():
        t = _tag_node(tag)
        t["inputs"] = [{"label": "In", "edges": [[node, pin]]}]
        nodes.append(t)
    out = _io_node("DefaultOutputNode", by["DefaultOutputNode"]["settings"]["Seed"], "Out")
    out["inputs"] = [{"label": "Out", "edges": [[t, "Out"] for t in TAPS]}]
    nodes.append(out)
    ir = {"schema": off["schema"], "graph": stages.name(10) + "_T17Tap", "graph_props": {},
          "params": list(off["params"]), "comment_boxes": [], "nodes": nodes, "sites": []}
    diffs = B.build_slim(ir, GRAPH, save=True)
    if diffs:
        return {"abort": "tap graph differs", "diffs": [str(x) for x in diffs[:5]]}
    pc = census.component(10)
    state = json.load(open(os.path.join(_REPO, "Saved", "Reports", "v2", "_state.json"), encoding="utf-8"))
    shipped = state.get(stages.name(10), {})
    pc.set_graph(unreal.EditorAssetLibrary.load_asset(GRAPH))
    if shipped.get("overrides"):
        census.apply_overrides(pc, shipped["overrides"])
    if "seed" in shipped:
        pc.set_editor_property("seed", int(shipped["seed"]))
    pc.activate(True)
    pc.generate_local(True)
    return {"graph": GRAPH, "nodes": len(nodes), "restore_required": True}


def _tapped():
    from pypcg import census
    pc = census.component(10)
    g = pc.get_graph()
    if g is None or not g.get_path_name().startswith(GRAPH):
        raise RuntimeError("the stage-10 volume does not hold the tap graph")
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        tags = [str(t) for t in td.get_editor_property("tags")]
        tap = next((t for t in tags if t in TAPS), None)
        if tap is not None:
            yield tap, tags, td.get_editor_property("data").get_editor_property("data")


def read():
    from pypcg import geo
    from pypcg.ue import convert
    out, counts = {}, {}
    for tap, tags, d in _tapped():
        counts[tap] = counts.get(tap, 0) + 1
        rec = {"class": d.get_class().get_name(), "tags": [t for t in tags if t != tap]}
        if tap != "T_terrain":
            v = convert.from_pcg(d)
            if isinstance(v, geo.Points):
                rec.update(kind="points", n=len(v), loc=[list(p) for p in v.loc],
                           quat=[list(q) for q in (v.quat or [])], rot=[list(r) for r in v.rot])
            elif isinstance(v, geo.ParamSet):
                rec.update(kind="params", values=v.values, types=v.types)
            else:
                rec.update(geo.to_json(v))
        out.setdefault(tap, []).append(rec)
    os.makedirs(_OUT, exist_ok=True)
    json.dump(out, open(os.path.join(_OUT, "tap_official.json"), "w", encoding="utf-8"))
    return {"counts": counts}


def tiles():
    from pypcg.geo import assets as AS, ground as G
    from pypcg.stages import s10_ground as S
    from pypcg.ue import convert
    from pypcg.ue.terrain import Terrain
    terrain, fills, tiled, grounds = None, [], [], []
    for tap, _tags, d in _tapped():
        if tap == "T_terrain":
            terrain = Terrain(d)
        elif tap == "T_fill":
            fills.append(convert.points_of(d))
        elif tap == "T_tiles":
            tiled.append(convert.points_of(d))
        elif tap == "T_ground":
            grounds.append(convert.from_pcg(d))
    R = {"pieces": len(grounds)}
    st = {"pieces_equal": 0, "pieces_differ": 0, "points": 0, "loc_exact": 0, "loc_max": 0.0, "yaw_max": 0.0,
          "box_and_steepness_exact": 0}
    for poly, off in zip(grounds, fills):
        locs, yaw = G.fill_uniform(poly.outer, poly.z, S.TILE_EXTENT_CM)
        if len(locs) != len(off):
            st["pieces_differ"] += 1
            continue
        st["pieces_equal"] += 1
        for i, p in enumerate(locs):
            st["points"] += 1
            st["loc_max"] = max(st["loc_max"], max(abs(p[a] - off.loc[i][a]) for a in range(3)))
            st["loc_exact"] += tuple(p) == tuple(off.loc[i])
            st["yaw_max"] = max(st["yaw_max"], abs((yaw - off.rot[i][1] + 180.0) % 360.0 - 180.0),
                                abs(off.rot[i][0]), abs(off.rot[i][2]))
            st["box_and_steepness_exact"] += (tuple(off.bounds_min[i]) == (-150.0,) * 3
                                               and tuple(off.bounds_max[i]) == (150.0,) * 3
                                               and off.steepness[i] == 1.0)
    R["fill"] = st
    pr = {"points": 0, "loc_exact": 0, "z_max": 0.0, "xy_max": 0.0, "quat_max": 0.0, "rot_max_deg": 0.0}
    budget = int((mcp_args or {}).get("budget", 20000))
    t0 = time.perf_counter()
    for off_fill, off_tile in zip(fills, tiled):
        for i in range(len(off_fill)):
            if pr["points"] >= budget:
                break
            loc = (off_fill.loc[i][0], off_fill.loc[i][1], off_fill.loc[i][2] + S.TILE_LIFT_CM)
            res = G.project_tile(loc, off_fill.rot[i], off_fill.bounds_min[i], off_fill.bounds_max[i], terrain)
            if res is None:
                continue
            l2, r2 = res
            ol, qo = off_tile.loc[i], off_tile.quat[i]
            pr["points"] += 1
            pr["xy_max"] = max(pr["xy_max"], abs(l2[0] - ol[0]), abs(l2[1] - ol[1]))
            pr["z_max"] = max(pr["z_max"], abs(l2[2] - ol[2]))
            pr["loc_exact"] += tuple(l2) == tuple(ol)
            q2 = AS.quat_of(*r2)
            pr["quat_max"] = max(pr["quat_max"], min(max(abs(a - b) for a, b in zip(q2, qo)),
                                                     max(abs(a + b) for a, b in zip(q2, qo))))
            pr["rot_max_deg"] = max(pr["rot_max_deg"], max(abs((r2[a] - off_tile.rot[i][a] + 180.0) % 360.0 - 180.0)
                                                           for a in range(3)))
        if pr["points"] >= budget:
            break
    pr["seconds"] = round(time.perf_counter() - t0, 2)
    R["project"] = pr
    R["official_tilt_max_deg"] = max(max(abs(r[0]), abs(r[2])) for t in tiled for r in t.rot) if tiled else None
    json.dump(R, open(os.path.join(_OUT, "tilecmp.json"), "w"), indent=1, default=str)
    return R


def _recorded_inputs():
    from pypcg import geo
    rec = json.load(open(os.path.join(_REPO, "Saved", "PyPCG", "runs", "s10.json"), encoding="utf-8"))
    return {pin: [(geo.from_json(v), frozenset(t)) for v, t in items]
            for pin, items in rec["inputs"].items() if pin != "MeshTerrain"}


def pieces():
    from pypcg import geo
    from pypcg.geo import areas as A, ground as G
    from pypcg.stages import s10_ground as S
    from pypcg.ue.ops import Ops
    tap = json.load(open(os.path.join(_OUT, "tap_official.json"), encoding="utf-8"))
    src = S.read(_recorded_inputs())
    ops = Ops()
    p2 = A.exclusion(A.exclusion(src["lots"], src["undividable"] + src["small_park"], ops), src["reserved"], ops)
    p3 = A.expand(p2, S.GROUND_EXPAND_CM, ops)
    off = [geo.from_json(v) for v in tap["T_pieces"]]
    offf = [v["n"] for v in tap["T_fill"]]

    def degenerate(polys):
        return [i for i, p in enumerate(polys) if A.area_cm2(p) / 1e4 < 1e-6]

    mine_deg, off_deg = degenerate(p2), degenerate(off)
    mine_fill = [len(G.fill_uniform(p.outer, p.z, S.TILE_EXTENT_CM)[0]) for p in p3]
    official_ground = [geo.from_json(v) for v in tap["T_ground"]]
    R = {"port_pieces": len(p2), "official_pieces": len(off),
         "port_area_m2": sum(A.area_cm2(p) for p in p2) / 1e4, "official_area_m2": sum(A.area_cm2(p) for p in off) / 1e4,
         "port_degenerate": len(mine_deg), "official_degenerate": len(off_deg),
         "port_tiles": sum(mine_fill), "official_tiles": sum(offf),
         "port_tiles_on_degenerate": sum(mine_fill[i] for i in mine_deg),
         "official_tiles_on_degenerate": sum(offf[i] for i in off_deg),
         "port_fill_on_official_ground": sum(len(G.fill_uniform(p.outer, p.z, S.TILE_EXTENT_CM)[0])
                                             for p in official_ground)}
    json.dump(R, open(os.path.join(_OUT, "pieces.json"), "w"), indent=1)
    return R


def nontile():
    from pypcg import geo
    from pypcg.stages import s10_ground as S
    from pypcg.ue.ops import Ops
    src = S.read(_recorded_inputs())
    ops = Ops()
    bound = S.boundary(src, ops)
    segs, corners = S.sidewalks(src, ops, bound)
    out = {"outputs": {"SidewalkSegments": [[geo.to_json(s), []] for s in segs],
                       "CornerShapes": [[geo.to_json(c), []] for c in corners],
                       "RailingZones": [[geo.to_json(r), []] for r in S.railings(src, ops)]}}
    json.dump(out, open(os.path.join(_OUT, "nontile_outputs.json"), "w"))
    return {"boundary": [(len(p), c) for p, c, _z, _y in bound], "segments": len(segs), "corners": len(corners)}


def corners():
    from pypcg import census
    name = (mcp_args or {}).get("as", "x")
    out = {}
    for c in census.volume(10).get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        path = sm.get_path_name() if sm else ""
        if "Sidewalk_Corner" not in path:
            continue
        rows = out.setdefault(path.rsplit(".", 1)[-1], [])
        for i in range(c.get_instance_count()):
            t = c.get_instance_transform(i, True)
            rows.append([round(t.translation.x, 3), round(t.translation.y, 3), round(t.translation.z, 3),
                         round(t.rotation.rotator().yaw, 3)])
    json.dump({"graph": census.component(10).get_graph().get_path_name(), "meshes": out},
              open(os.path.join(_OUT, "corners_%s.json" % name), "w"))
    return {k: len(v) for k, v in out.items()}


STEPS = {"gen": gen, "read": read, "tiles": tiles, "pieces": pieces, "nontile": nontile, "corners": corners}

try:
    mcp_result = json.loads(json.dumps(STEPS[(mcp_args or {}).get("step", "read")](), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
