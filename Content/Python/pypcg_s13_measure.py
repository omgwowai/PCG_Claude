import gc
import json
import math
import os
import random
import sys
import time

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())

# pypcg_s13_measure.py -- the generator of Tools/pypcg/data/s13_official_measurements.json (docs/pypcg/stages/
# s13.md section 6): stage 13's Python against the OFFICIAL graph's own intermediate data.
#   {"step": "gen"}      build /Game/PyPCG/Probe/PCG_T18Tap -- the official nodes upstream of the taps below plus
#                        one AddTag per tap, from the official IR snapshot -- put it on the stage-13 volume
#                        (shipped overrides and seed) and generate. Restore afterwards (V2 gen official / restore).
#   {"step": "measure"}  (a later call, the tap graph generated) read the taps and the terrain; run the stage's
#                        own functions on the RECORDED inputs of Saved/Reports/v2/s13/slim_42.run.json (and, for
#                        the plaza node, on the tapped official fitting outputs) with the editor's booleans; compare
#                        step by step; add the stage-14 matched-draw records (V2 files); write the data file.
#   {"step": "dump", "label": name}  (the volume holding pypcg_v1_editor.py's assign oracle) write the tapped
#                        Assign_Assets inputs and outputs to Saved/Reports/v2/s13/oracle_taps_<name>.json, for
#                        Tools/pypcg/s13_assign_rows.py (the random-range rows).
GRAPH = "/Game/PyPCG/Probe/PCG_T18Tap"
STAGE = 13
OUT = os.path.join(_REPO, "Tools", "pypcg", "data", "s13_official_measurements.json")
RUN = os.path.join(_REPO, "Saved", "Reports", "v2", "s13", "slim_42.run.json")
V2 = os.path.join(_REPO, "Saved", "Reports", "v2", "s13")
TAPS = {
    "T_reserved": ["Subgraph_4", "Selected"], "T_unbuild": ["Subgraph_5", "Selected"],
    "T_skirt": ["Subgraph_36", "Selected"], "T_under": ["Subgraph_50", "Selected"],
    "T_smallc": ["Subgraph_29", "Selected"], "T_medc": ["Subgraph_18", "Selected"],
    "T_split_sel": ["Subgraph_10", "Selected"], "T_split_uns": ["Subgraph_10", "Unselected"],
    "T_cull_sel": ["Subgraph_0", "Selected"], "T_cull_uns": ["Subgraph_0", "Unselected"],
    "T_fit_res": ["Subgraph_9", "Out"], "T_fit_hw": ["Subgraph_54", "Out"], "T_fit_sc": ["Subgraph_32", "Out"],
    "T_fit_mc": ["Subgraph_25", "Out"], "T_fit_skirt": ["Subgraph_37", "Out"],
    "T_undiv": ["Subgraph_8", "Out"], "T_smallpark": ["Subgraph_58", "Out"], "T_treeareas": ["Subgraph_24", "Out"],
    "T_scatter": ["Subgraph_1", "Out"], "T_treeproj": ["Subgraph_19", "Out"], "T_tex1": ["Subgraph_27", "Out"],
    "T_tilefill": ["Subgraph_34", "Out"], "T_tileproj": ["Subgraph_49", "Out"], "T_tiles": ["Gather_1", "Out"],
    "T_hwproj": ["Subgraph_57", "Out"], "T_terrain": ["Subgraph_15", "Out"],
    "T_plaza_res": ["Subgraph_2", "Out"], "T_plaza_mc": ["Subgraph_23", "Out"], "T_plaza_sc": ["Subgraph_31", "Out"],
    "T_plaza_hw": ["Subgraph_53", "Out"], "T_plaza_skirt": ["Subgraph_38", "Out"],
    "T_plaza_proj": ["Subgraph_20", "Out"], "T_birch_in": ["AttributeMathsOp_2", "Out"],
    "T_birch_diff": ["Subgraph_56", "Out"], "T_cast1": ["AttributeCast_1", "Out"], "T_trees73": ["Subgraph_73", "Out"],
    "T_plaza_final": ["Gather_3", "Out"],
}
PLAZA_ORDER = ("T_plaza_res", "T_plaza_mc", "T_plaza_sc", "T_plaza_hw", "T_plaza_skirt")


# ---- gen ----------------------------------------------------------------------------------------------
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


def gen(args):
    from pypcg import build as B, census, ir as _ir, stages
    off = _ir.load(os.path.join(_REPO, "Tools", "pypcg", "official_ir", stages.name(STAGE) + ".json"))
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
    ir = {"schema": off["schema"], "graph": stages.name(STAGE) + "_T18Tap", "graph_props": {},
          "params": [p for p in off["params"]], "comment_boxes": [], "nodes": nodes, "sites": []}
    diffs = B.build_slim(ir, GRAPH, save=True)
    if diffs:
        return {"abort": "tap graph differs", "diffs": [str(x) for x in diffs[:5]]}
    pc = census.component(STAGE)
    state = json.load(open(os.path.join(_REPO, "Saved", "Reports", "v2", "_state.json"), encoding="utf-8"))
    shipped = state.get(stages.name(STAGE), {})
    pc.set_graph(unreal.EditorAssetLibrary.load_asset(GRAPH))
    if shipped.get("overrides"):
        census.apply_overrides(pc, shipped["overrides"])
    if "seed" in shipped:
        pc.set_editor_property("seed", int(shipped["seed"]))
    pc.activate(True)
    pc.generate_local(True)
    return {"graph": GRAPH, "nodes": len(nodes), "taps": len(TAPS), "restore_required": True}


# ---- measure ------------------------------------------------------------------------------------------
def _cent(p):
    n = len(p.outer)
    return (sum(q[0] for q in p.outer) / n, sum(q[1] for q in p.outer) / n) if n else (0.0, 0.0)


def _match(mine, theirs, tol_m2=0.05):
    """Pairs by area (0.05 m2) and the nearest centroid; (pairs, unmatched mine, unmatched theirs)."""
    from pypcg import geo
    left = list(range(len(theirs)))
    pairs, um = [], []
    for i, p in enumerate(mine):
        a, c = geo.area_m2(p), _cent(p)
        cands = [j for j in left if abs(geo.area_m2(theirs[j]) - a) <= tol_m2]
        if not cands:
            um.append(i)
            continue
        j = min(cands, key=lambda k: math.dist(_cent(theirs[k]), c))
        left.remove(j)
        pairs.append((i, j))
    return pairs, um, left


def _same_ring(a, b):
    """Same vertices in the same cyclic order, starting anywhere (the start vertex reported apart)."""
    if len(a) != len(b) or not a:
        return False
    for s in range(len(b)):
        if all(math.dist(a[k], b[(k + s) % len(b)]) < 1e-6 for k in range(len(a))):
            return True
    return False


def _cmp(name, mine, theirs):
    from pypcg import geo
    pairs, um, ut = _match(mine, theirs)
    start, same_ring, maxd = 0, 0, 0.0
    for i, j in pairs:
        a, b = mine[i], theirs[j]
        if a.outer and b.outer and math.dist(a.outer[0], b.outer[0]) < 1e-6:
            start += 1
        if _same_ring(a.outer, b.outer):
            same_ring += 1
        if len(a.outer) == len(b.outer):
            maxd = max(maxd, max(math.dist(p, q) for p, q in zip(a.outer, b.outer)))
    return {"step": name, "port": len(mine), "official": len(theirs), "matched_area_centroid": len(pairs),
            "same_vertices_any_start": same_ring, "same_start_vertex": start,
            "max_vertex_diff_cm_same_count": maxd,
            "area_port_m2": round(sum(geo.area_m2(p) for p in mine), 3),
            "area_official_m2": round(sum(geo.area_m2(p) for p in theirs), 3),
            "degenerate_port": sum(1 for p in mine if geo.area_m2(p) < 0.01),
            "degenerate_official": sum(1 for p in theirs if geo.area_m2(p) < 0.01),
            "unmatched_port_m2": sorted(round(geo.area_m2(mine[k]), 4) for k in um)[:10],
            "unmatched_official_m2": sorted(round(geo.area_m2(theirs[k]), 4) for k in ut)[:10]}


def _hist(items):
    h = {}
    for p in items:
        for a in p.attrs.get("Asset") or []:
            h[str(a)] = h.get(str(a), 0) + 1
    return h


def _keyset(items):
    s = {}
    for p in items:
        for i in range(len(p)):
            k = (str(p.attrs["Asset"][i]), round(p.loc[i][0], 3), round(p.loc[i][1], 3), round(p.loc[i][2], 3))
            s[k] = s.get(k, 0) + 1
    return s


def _down():
    """Stage 14 under the official upstream twice, and under the port's seed 7913 (whose draws publish the
    official five lots) before and after the host forwarded the lots' own data objects."""
    def load(name):
        p = os.path.join(V2, name + ".json")
        return json.load(open(p, encoding="utf-8"))["instances"]["per_mesh"] if os.path.exists(p) else None
    o1, o2 = load("down_14_official"), load("down_14_official_2")
    out = {}
    for name in ("down_14_official_2", "down_14_match_7913", "down_14_match_7913_forwarded"):
        m = load(name)
        if m is None or o1 is None:
            continue
        diff = {k.rsplit("/", 1)[-1]: [o1.get(k, 0), m.get(k, 0)] for k in set(o1) | set(m) if o1.get(k, 0) != m.get(k, 0)}
        out[name] = {"total": sum(m.values()), "official_total": sum(o1.values()), "meshes_differing": diff}
    return out


def measure(args):
    from pypcg import census, geo
    from pypcg.geo import areas as A
    from pypcg.geo import assets as AS
    from pypcg.stages import s13_leftover_lots as S
    from pypcg.stages import s13_leftover_plazas as P
    from pypcg.ue import convert
    from pypcg.ue.ops import Ops
    from pypcg.ue.terrain import Terrain
    ops = Ops()
    pc = census.component(STAGE)
    g = pc.get_graph()
    if g is None or not g.get_path_name().startswith(GRAPH):
        return {"abort": "volume does not hold the tap graph"}
    taps, terrain = {}, None
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        tags = [str(t) for t in td.get_editor_property("tags")]
        tap = next((t for t in tags if t in TAPS), None)
        if tap is None:
            continue
        d = td.get_editor_property("data").get_editor_property("data")
        if tap == "T_terrain":
            terrain = Terrain(d)
            continue
        try:
            taps.setdefault(tap, []).append(convert.from_pcg(d))
        except TypeError:
            pass
    off = {k: [v for v in vals if isinstance(v, geo.Polygon)] for k, vals in taps.items()}
    rec = json.load(open(RUN, encoding="utf-8"))
    inputs = {}
    for pin, items in rec["inputs"].items():
        vals = []
        for v, t in items:
            try:
                vals.append((geo.from_json(v), frozenset(t)))
            except ValueError:
                pass
        inputs[pin] = vals
    src = S.read(inputs)
    out = {"_": "Generated by Content/Python/pypcg_s13_measure.py (see its header), 2026-10-19: stage 13's Python "
                "against the official graph's own intermediate data on the demo level (component seed 42); "
                "inputs as recorded by the slim run of seed 42.",
           "areas": [], "tiles": {}, "trees": {}, "plazas": {}, "downstream_stage14": _down()}
    for k, tap in (("reserved", "T_reserved"), ("unbuildable", "T_unbuild"), ("skirt", "T_skirt"),
                   ("under", "T_under"), ("small_yards", "T_smallc"), ("medium_yards", "T_medc")):
        out["areas"].append(_cmp("read " + k, src[k], off[tap]))
    out["areas"].append(_cmp("undividable (Subgraph_8)", S.undividable(src, ops), off["T_undiv"]))
    out["areas"].append(_cmp("small park (Subgraph_58)", S.small_park(src, ops), off["T_smallpark"]))
    csel, uns = off["T_cull_sel"], off["T_split_uns"]
    out["areas"].append(_cmp("setback reserved, in frame (Subgraph_13/9)", S.setback(csel, ops), off["T_fit_res"]))
    world = [S.lift(p, S.PLAZA_LIFT_CM) for p in A.contract(csel, S.PLAZA_SETBACK_CM, ops, union=False)]
    out["areas"].append(_cmp("setback reserved, in the world", world, off["T_fit_res"]))
    for k, tap, nodes in (("under", "T_fit_hw", "52/54"), ("small_yards", "T_fit_sc", "30/32"),
                          ("medium_yards", "T_fit_mc", "21/25")):
        out["areas"].append(_cmp("setback %s, in frame (Subgraph_%s)" % (k, nodes), S.setback(src[k], ops), off[tap]))
        world = [S.lift(p, S.PLAZA_LIFT_CM) for p in A.contract(src[k], S.PLAZA_SETBACK_CM, ops, union=False)]
        out["areas"].append(_cmp("setback %s, in the world" % k, world, off[tap]))
    out["areas"].append(_cmp("skirt lift (Subgraph_37)", [S.lift(p, S.PLAZA_LIFT_CM) for p in src["skirt"]],
                             off["T_fit_skirt"]))
    ta = A.exclusion(uns + src["unbuildable"] + S.undividable(src, ops), src["highway"], ops)
    out["areas"].append(_cmp("tree areas, official split (Subgraph_24)", ta, off["T_treeareas"]))
    # ---- tiles: the fill and the terrain fit on the official kept lots ----
    fills = taps.get("T_tilefill", [])
    mine = [S.tile_points(p) for p in csel]
    t = {"sets_port": [len(p) for p in mine], "sets_official": [len(p) for p in fills]}
    if [len(p) for p in mine] == [len(p) for p in fills]:
        dmax, exact = 0.0, 0
        for a, b in zip(mine, fills):
            for i in range(len(b)):
                dd = max(abs(a.loc[i][0] - b.loc[i][0]), abs(a.loc[i][1] - b.loc[i][1]))
                dmax, exact = max(dmax, dd), exact + (dd == 0.0)
        t.update(fill_xy_max_cm=dmax, fill_xy_exact=exact)
        proj = [S.project(S.tile_points(p), terrain) for p in csel]
        offp = taps.get("T_tileproj", [])
        dl = dq = 0.0
        for a, b in zip(proj, offp):
            for i in range(len(b)):
                dl = max(dl, max(abs(a.loc[i][k] - b.loc[i][k]) for k in range(3)))
                qa, qb = AS.quat_of(*a.rot[i]), b.quat[i]
                dq = max(dq, min(max(abs(x - y) for x, y in zip(qa, qb)), max(abs(x + y) for x, y in zip(qa, qb))))
        t.update(fit_loc_max_cm=dl, fit_quat_max=dq)
    out["tiles"] = t
    # ---- trees: the official scatter, fitted by the port's projector ----
    sc, tp = taps.get("T_scatter", []), taps.get("T_treeproj", [])
    dl = dq = 0.0
    n = 0
    for a, b in zip(sc, tp):
        for i in range(len(b)):
            res = geo.ground.project_tile(a.loc[i], a.rot[i], a.bounds_min[i], a.bounds_max[i], terrain)
            if res is None:
                continue
            n += 1
            dl = max(dl, max(abs(res[0][k] - b.loc[i][k]) for k in range(3)))
            qa, qb = AS.quat_of(*res[1]), b.quat[i]
            dq = max(dq, min(max(abs(x - y) for x, y in zip(qa, qb)), max(abs(x + y) for x, y in zip(qa, qb))))
    port_pts = sum(len(locs) for locs in [geo.ground.fill_random(p, S.TREES_PER_M2, random.Random(s)) for s, p in
                                     enumerate(off["T_treeareas"] + off["T_smallpark"])])
    out["trees"] = {"official_scatter_points": sum(len(p) for p in sc), "official_scatter_sets": len(sc),
                    "port_scatter_points_one_draw": port_pts, "fit_points": n, "fit_loc_max_cm": dl, "fit_quat_max": dq,
                    "texture_write_output_points": sum(len(p) for p in taps.get("T_tex1", []))}
    # ---- the plaza node on the official fitting outputs ----
    highways = src["highway"]
    items = [p for k in PLAZA_ORDER for p in taps.get(k, [])]
    t0 = time.perf_counter()
    proj = [P.project(p, terrain) for p in items]
    offp = taps.get("T_plaza_proj", [])
    pz = {"items": len(items), "points": sum(len(p) for p in items)}
    if [len(p) for p in proj] == [len(p) for p in offp]:
        dl = dq = 0.0
        exact = dens = 0
        for a, b in zip(proj, offp):
            for i in range(len(b)):
                d = max(abs(a.loc[i][k] - b.loc[i][k]) for k in range(3))
                dl, exact = max(dl, d), exact + (d == 0.0)
                qa, qb = AS.quat_of(*a.rot[i]), b.quat[i]
                dq = max(dq, min(max(abs(x - y) for x, y in zip(qa, qb)), max(abs(x + y) for x, y in zip(qa, qb))))
                dens += a.density[i] != b.density[i]
        pz["projection"] = {"loc_max_cm": dl, "loc_exact": exact, "quat_max": dq, "density_differs": dens}
    parts = [P.split(p) for p in proj]
    pz["birches"] = [sum(len(s[0]) for s in parts), sum(len(p) for p in taps.get("T_birch_in", []))]
    tiles = P.highway_tiles(highways, terrain)
    offt = taps.get("T_hwproj", [])
    pz["highway_tiles"] = {"port": len(tiles), "official": sum(len(p) for p in offt),
                           "on_terrain_port": sum(1 for x in tiles if x[5] > 0),
                           "on_terrain_official": sum(1 for p in offt for x in p.density if x > 0)}
    pts, notes = P.plazas(items, highways, terrain, False, random.Random(42), ops.assets)
    pz["seconds"] = round(time.perf_counter() - t0, 2)
    trees = [p for p in pts if any("BlackAlder" in str(a) for a in (p.attrs.get("Asset") or [])[:1])]
    rest = [p for p in pts if p not in trees]
    off_rest = taps.get("T_cast1", [])
    hm, ho = _hist(rest), _hist(off_rest)
    km, ko = _keyset(rest), _keyset(off_rest)
    pz.update(birches_left=[sum(len(p) for p in trees), sum(len(p) for p in taps.get("T_birch_diff", [])),
                            sum(len(p) for p in taps.get("T_trees73", []))],
              rest_points=[sum(len(p) for p in rest), sum(len(p) for p in off_rest)],
              rest_meshes_differing={k: [hm.get(k, 0), ho.get(k, 0)] for k in set(hm) | set(ho) if hm.get(k, 0) != ho.get(k, 0)},
              rest_same_mesh_and_position_mm=sum(min(v, ko.get(k, 0)) for k, v in km.items()),
              final_points=[sum(len(p) for p in pts), sum(len(p) for p in taps.get("T_plaza_final", []))], notes=notes)
    out["plazas"] = pz
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return {"written": OUT, "tiles": out["tiles"], "trees": out["trees"],
            "plazas": {k: v for k, v in pz.items() if k != "notes"},
            "areas": [[r["step"], r["port"], r["official"], r["same_vertices_any_start"], r["same_start_vertex"]]
                      for r in out["areas"]]}


def dump(args):
    from pypcg import census, geo
    from pypcg.ue import convert
    pc = census.component(STAGE)
    out = {}
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        tags = [str(t) for t in td.get_editor_property("tags")]
        tap = next((t for t in tags if t.startswith("AssignIn_") or t.startswith("AssignOut_")), None)
        if tap is None:
            continue
        d = td.get_editor_property("data").get_editor_property("data")
        if isinstance(d, unreal.PCGBasePointData):
            out.setdefault(tap, []).append(geo.to_json(convert.points_of(d)))
    path = os.path.join(V2, "oracle_taps_%s.json" % args["label"])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"graph": pc.get_graph().get_path_name(), "taps": out}, fh)
    return {"written": path, "taps": {k: [len(x.get("loc") or []) for x in v] for k, v in out.items() if k.startswith("AssignOut_")}}


try:
    _a = mcp_args or {}
    _steps = {"gen": gen, "dump": dump}
    from pypcg import level as _level
    # Final review I2: the tap graph goes onto the stage-13 volume, so only the demo's volume may get it.
    mcp_result = _level.require(_level.DEMO, "pypcg_s13_measure.py") or \
        json.loads(json.dumps(_steps.get(_a.get("step"), measure)(_a), default=str))
except Exception as _exc:
    import traceback
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600]), "tb": traceback.format_exc()[-1500:]}
gc.collect()
