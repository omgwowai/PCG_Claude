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

# pypcg_s14_measure.py -- the generator of Tools/pypcg/data/s14_official_measurements.json (docs/pypcg/stages/
# s14.md section 6): stage 14's Python against the OFFICIAL graph's own intermediate data.
#   {"step": "gen"}      build /Game/PyPCG/Probe/PCG_T19Tap -- the official nodes upstream of the taps below, one
#                        AddTag per tap, and for every spline tap a native GetSplineControlPoints so the control
#                        points' own transforms (rotation included, trap 63) are read too -- put it on the stage-14
#                        volume (shipped overrides and seed) and generate. Restore afterwards (V2 gen official).
#   {"step": "dump"}     (a later call, the tap graph generated) write every tap to Saved/t19/taps.json.
#   {"step": "measure"}  run the stage's own functions on the tapped official INPUT with the editor's booleans
#                        and compare every step with its tap, write the data file (needs only taps.json).
#   {"step": "finish"}   (the tap graph generated on the volume) `s14_parkings_finish` on the tapped official points
#                        and the tapped terrain against the official Gather_0 output; merged into the data file.
GRAPH = "/Game/PyPCG/Probe/PCG_T19Tap"
STAGE = 14
TAPS_JSON = os.path.join(_REPO, "Saved", "t19", "taps.json")
OUT = os.path.join(_REPO, "Tools", "pypcg", "data", "s14_official_measurements.json")
TAPS = {
    "T_in": ["Subgraph_0", "Out"], "T_terrain": ["Subgraph_1", "Out"],
    "T_outer": ["Subgraph_29", "Out"], "T_outerseg": ["Subgraph_36", "Out"], "T_inner": ["Subgraph_33", "Out"],
    "T_grid_areas": ["Subgraph_32", "Areas"], "T_grid_lines": ["Subgraph_32", "Subdividing_splines"],
    "T_aisle": ["Subgraph_30", "Out"], "T_central": ["Subgraph_35", "Subdividing_splines"],
    "T_central_areas": ["Subgraph_35", "Areas"],
    "T_outer_trunc": ["Subgraph_43", "Out"], "T_outer_res": ["Subgraph_44", "Out"],
    "T_inner_res": ["Subgraph_45", "Out"], "T_rowA": ["Subgraph_46", "Out"], "T_rowB": ["Subgraph_47", "Out"],
    "T_expand": ["Subgraph_56", "Out"], "T_median": ["Subgraph_55", "Subdividing_splines"],
    "T_median_areas": ["Subgraph_55", "Areas"], "T_outline": ["Subgraph_57", "Out"],
    "T_med_trunc": ["Subgraph_63", "Out"], "T_medA": ["Subgraph_66", "Out"], "T_medB": ["Subgraph_67", "Out"],
    "T_medBrev": ["Subgraph_68", "Out"], "T_arrowpts": ["Subgraph_65", "Out"], "T_arrows": ["Subgraph_8", "Out"],
    "T_bseg": ["Subgraph_59", "Out"], "T_bres": ["Subgraph_58", "Out"], "T_border": ["Subgraph_60", "Out"],
    "T_outer_cut": ["Subgraph_61", "Out"], "T_outer_res2": ["Subgraph_62", "Out"],
    "T_stallseg": ["Subgraph_38", "Out"], "T_stallctr": ["Subgraph_40", "Out"],
    "T_linepts": ["Subgraph_52", "Out"], "T_lines": ["Subgraph_7", "Out"],
    "T_occ_sel": ["Subgraph_48", "Selected"], "T_occ_uns": ["Subgraph_48", "Unselected"],
    "T_rev_sel": ["Subgraph_49", "Selected"], "T_rev_uns": ["Subgraph_49", "Unselected"],
    "T_fwd": ["Subgraph_4", "Out"], "T_rev": ["Subgraph_5", "Out"],
    "T_tilefill": ["Subgraph_10", "Out"], "T_tiles": ["Subgraph_11", "Out"],
    "T_barrier": ["Subgraph_53", "Out"], "T_fence": ["Subgraph_54", "Out"],
    "T_proj": ["Subgraph_3", "Out"], "T_lift": ["Subgraph_9", "Out"], "T_final": ["Gather_0", "Out"],
}
SPLINE_TAPS = ("T_outerseg", "T_grid_lines", "T_central", "T_outer_trunc", "T_outer_res", "T_inner_res", "T_rowA",
               "T_rowB", "T_median", "T_med_trunc", "T_medA", "T_medB", "T_medBrev", "T_bseg", "T_bres", "T_border",
               "T_outer_cut", "T_outer_res2", "T_stallseg")
CP = "CP_"          # the control-point tap of a spline tap: CP_<tap>


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


def _plain_node(name, cls, settings=None):
    return {"name": name, "class": cls, "title": "", "settings": dict({"Seed": 0}, **(settings or {})),
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
    outs = []
    for tag, (node, pin) in TAPS.items():
        t = _plain_node(tag, "PCGAddTagSettings", {"TagsToAdd": tag})
        t["inputs"] = [{"label": "In", "edges": [[node, pin]]}]
        nodes.append(t)
        outs.append(tag)
        if tag in SPLINE_TAPS:
            g = _plain_node("GSCP_" + tag, "PCGGetSplineControlPointsSettings")
            g["inputs"] = [{"label": "In", "edges": [[node, pin]]}]
            c = _plain_node(CP + tag, "PCGAddTagSettings", {"TagsToAdd": CP + tag})
            c["inputs"] = [{"label": "In", "edges": [["GSCP_" + tag, "Out"]]}]
            nodes += [g, c]
            outs.append(CP + tag)
    out = _io_node("DefaultOutputNode", by["DefaultOutputNode"]["settings"]["Seed"], "Out")
    out["inputs"] = [{"label": "Out", "edges": [[t, "Out"] for t in outs]}]
    nodes.append(out)
    ir = {"schema": off["schema"], "graph": stages.name(STAGE) + "_T19Tap", "graph_props": {},
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
    return {"graph": GRAPH, "nodes": len(nodes), "taps": len(outs), "restore_required": True}


# ---- dump ---------------------------------------------------------------------------------------------
def _taps(pc):
    from pypcg.ue import convert
    out = {}
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        tags = [str(t) for t in td.get_editor_property("tags")]
        tap = next((t for t in tags if t in TAPS or (t.startswith(CP) and t[len(CP):] in TAPS)), None)
        if tap is None:
            continue
        d = td.get_editor_property("data").get_editor_property("data")
        try:
            v = convert.from_pcg(d)
        except TypeError:
            v = None
        out.setdefault(tap, []).append((v, [t for t in tags if t != tap], d.get_class().get_name()))
    return out


def dump(args):
    from pypcg import census, geo
    from pypcg.geo import types as GT
    pc = census.component(STAGE)
    g = pc.get_graph()
    if g is None or g.get_path_name().split(".")[0] != GRAPH:
        return {"abort": "the stage-14 volume does not hold %s" % GRAPH}
    GT.MAX_RECORDED_POINTS = 10 ** 9
    taps = _taps(pc)
    doc = {}
    for tap, items in taps.items():
        rows = []
        for v, tags, cls in items:
            if v is None:
                rows.append({"kind": "none", "class": cls, "tags": tags})
            elif hasattr(v, "height"):
                rows.append({"kind": "surface", "class": cls, "tags": tags})
            else:
                rows.append(dict(geo.to_json(v), tags=tags, cls=cls))
        doc[tap] = rows
    os.makedirs(os.path.dirname(TAPS_JSON), exist_ok=True)
    with open(TAPS_JSON, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return {"written": TAPS_JSON, "taps": {k: [len(v), sum(r.get("n", 0) for r in v)] for k, v in sorted(doc.items())},
            "missing": sorted(set(TAPS) - set(doc))}


# ---- measure ------------------------------------------------------------------------------------------
def _from_taps():
    from pypcg import geo
    from pypcg.geo import areas as A
    from pypcg.geo import splines as SP
    doc = json.load(open(TAPS_JSON, encoding="utf-8"))

    def items(tap):
        return [geo.from_json(r) for r in doc[tap] if r["kind"] in ("polygon", "spline", "points")]

    def polys(tap):
        return [p for p in (v if isinstance(v, geo.Polygon) else A.area_of(v) for v in items(tap)) if p is not None]

    def paths(tap):
        return [[SP._xyz(q) for q in v.points] for v in items(tap)]
    return items, polys, paths


def _cmp_polys(mine, theirs):
    import math
    from pypcg import geo
    r = {"n": [len(mine), len(theirs)],
         "area_m2": [round(sum(geo.area_m2(p) for p in mine), 3), round(sum(geo.area_m2(p) for p in theirs), 3)]}
    if len(mine) == len(theirs):
        pairs = [(a, b) for a, b in zip(mine, theirs) if len(a.outer) == len(b.outer)]
        r["same_vertex_count"] = len(pairs)
        r["same_start_vertex"] = sum(1 for a, b in pairs if math.dist(a.outer[0], b.outer[0]) < 1e-3)
        d = [max(math.dist(p, q) for p, q in zip(a.outer, b.outer)) for a, b in pairs]
        r["max_vertex_diff_cm_same_count"] = max(d) if d else None
    return r


def _mid(path):
    from pypcg.geo import splines as SP
    return SP.center([path[0], path[-1]])[0]


def _cmp_paths(mine, theirs):
    """Item for item (allowing a reversed item) when the counts agree, plus an order-free match by midpoint."""
    import math
    r = {"n": [len(mine), len(theirs)], "points": [sum(len(p) for p in mine), sum(len(p) for p in theirs)]}
    if len(mine) == len(theirs):
        maxd, rev, npd = 0.0, 0, 0
        for a, b in zip(mine, theirs):
            if len(a) != len(b):
                npd += 1
                continue
            d = max(math.dist(p[:2], q[:2]) for p, q in zip(a, b))
            dr = max(math.dist(p[:2], q[:2]) for p, q in zip(a, reversed(b)))
            rev += dr < d
            maxd = max(maxd, min(d, dr))
        r.update(item_for_item_max_diff_cm=maxd, reversed=rev, point_count_differs=npd)
    left, unmatched = list(range(len(theirs))), 0
    for a in mine:
        ma = _mid(a)
        best = min(left, key=lambda i: math.dist(ma[:2], _mid(theirs[i])[:2]), default=None)
        if best is not None and math.dist(ma[:2], _mid(theirs[best])[:2]) < 5.0:
            left.remove(best)
        else:
            unmatched += 1
    r["unmatched_by_midpoint"] = [unmatched, len(left)]
    return r


def _cmp_points(mine, theirs):
    import math
    a = [p for s in mine for p in s.loc]
    b = [p for s in theirs for p in s.loc]
    r = {"n": [len(a), len(b)]}
    if len(a) == len(b) and a:
        r["max_diff_cm_in_order"] = max(math.dist(p, q) for p, q in zip(a, b))
    return r


def measure(args):
    import math
    import random
    from pypcg.geo import areas as A
    from pypcg.geo import splines as SP
    from pypcg.stages import s14_parkings as S
    from pypcg.ue.ops import Ops
    ops = Ops()
    items, polys, paths = _from_taps()
    lots = polys("T_in")
    st = {}
    # 1. each step on the TAPPED official upstream
    st["outer Subgraph_29"] = _cmp_polys(S.outer_areas(lots, ops), polys("T_outer"))
    st["inner Subgraph_33"] = _cmp_polys(S.inner_areas(polys("T_outer"), ops), polys("T_inner"))
    st["cells Subgraph_32"] = _cmp_polys(S.grid_cells(polys("T_inner"), ops), polys("T_grid_areas"))
    st["aisles Subgraph_30"] = _cmp_polys(S.aisles(polys("T_grid_areas"), ops), polys("T_aisle"))
    st["central lines Subgraph_35"] = _cmp_paths(S.central_lines(polys("T_aisle")), paths("T_central"))
    st["median expand Subgraph_56"] = _cmp_polys(A.follow_subjects(A.expand(lots, S.MEDIAN_EXPAND_CM, ops), lots),
                                                 polys("T_expand"))
    st["medians Subgraph_55"] = _cmp_paths(S.medians(lots, ops), paths("T_median"))
    st["median bands Subgraph_57"] = _cmp_polys(S.median_bands(paths("T_median"), ops), polys("T_outline"))
    st["outer runs Subgraph_36"] = _cmp_paths(S._runs(polys("T_outer")), paths("T_outerseg"))
    st["outer truncate Subgraph_43"] = _cmp_paths([SP.truncate(r, S.OUTER_TRUNC_CM, S.OUTER_TRUNC_CM)
                                                   for r in paths("T_outerseg")], paths("T_outer_trunc"))
    st["outer chord Subgraph_44"] = _cmp_paths([SP.chord(p) for p in paths("T_outer_trunc")], paths("T_outer_res"))
    st["outer cut Subgraph_61"] = _cmp_paths(S._cut(paths("T_outer_res"), polys("T_outline"), ops), paths("T_outer_cut"))
    st["outer resample Subgraph_62"] = _cmp_paths([x for x in (SP.resample_fit(p, S.SPACE_CM)
                                                               for p in paths("T_outer_cut")) if x], paths("T_outer_res2"))
    st["inner resample Subgraph_45"] = _cmp_paths([x for x in (SP.resample_fit(p, S.SPACE_CM)
                                                               for p in paths("T_central")) if x], paths("T_inner_res"))
    ra, rb = S.inner_rows(paths("T_central"))
    st["row A Subgraph_46"] = _cmp_paths(ra, paths("T_rowA"))
    st["row B Subgraph_47"] = _cmp_paths(rb, paths("T_rowB"))
    st["border runs Subgraph_59"] = _cmp_paths(S._runs(lots), paths("T_bseg"))
    st["border subdivide Subgraph_58"] = _cmp_paths([SP.subdivide(r, S.BORDER_SUBDIV) for r in paths("T_bseg")],
                                                    paths("T_bres"))
    st["border cut Subgraph_60"] = _cmp_paths(S._cut(paths("T_bres"), polys("T_outline"), ops), paths("T_border"))
    st["median truncate Subgraph_63"] = _cmp_paths([SP.truncate(p, S.MEDIAN_TRUNC_CM, S.MEDIAN_TRUNC_CM)
                                                    for p in paths("T_median")], paths("T_med_trunc"))
    sa, sb = S.arrow_lines(paths("T_median"))
    st["arrow side A Subgraph_66"] = _cmp_paths(sa, paths("T_medA"))
    st["arrow side B reversed Subgraph_68"] = _cmp_paths(sb, paths("T_medBrev"))
    rows = paths("T_rowA") + paths("T_rowB") + paths("T_outer_res2")
    st["space centres Subgraph_38/40"] = _cmp_points([S.space_centres(rows)], items("T_stallctr"))
    st["line points Subgraph_52"] = _cmp_points([S.control_points(p) for p in rows], items("T_linepts"))
    st["arrow points Subgraph_65"] = _cmp_points([S.control_points(p, S.ARROW_YAW)
                                                  for p in paths("T_medA") + paths("T_medBrev")], items("T_arrowpts"))
    st["tiles Subgraph_10/11"] = _cmp_points([S.tile_points(p) for p in lots], items("T_tiles"))
    # 2. end to end from the official lots alone
    out, notes = S.parkings({"ParkingFootprint": [(p, frozenset()) for p in lots]}, ops, S.Draws(random.Random(1)), None)
    o2 = S.outer_areas(lots, ops)
    i2 = S.inner_areas(o2, ops)

    def total(tap):
        return sum(len(p) for p in items(tap))
    e2e = {"notes": notes,
           "outer": _cmp_polys(o2, polys("T_outer")), "inner": _cmp_polys(i2, polys("T_inner")),
           "cells": _cmp_polys(S.grid_cells(i2, ops), polys("T_grid_areas")),
           "central lines": _cmp_paths(out["CentralLines"], paths("T_central")),
           "border": _cmp_paths(out["Border"], paths("T_border")),
           "official counts": {"spaces": total("T_stallctr"), "line points": total("T_linepts"),
                               "arrow points": total("T_arrowpts"), "tiles": total("T_tiles"),
                               "outer lines": len(paths("T_outer_res2")), "central lines": len(paths("T_central")),
                               "border runs": len(paths("T_border")), "occupied": total("T_occ_sel"),
                               "forward": total("T_fwd"), "reversed": total("T_rev"),
                               "barrier points": total("T_barrier"), "fence points": total("T_fence")}}

    # 3. the tie that moves lot 1's grid: the inner rectangle's two long edges, port and official
    def lens(r):
        return [repr(math.dist(r[i], r[(i + 1) % len(r)])) for i in range(len(r))]
    tie = {"port": lens(i2[1].outer), "official": lens(polys("T_inner")[1].outer)}
    doc = {"what": "Stage 14 Parkings: the port's steps against the official graph's own intermediates, tapped by "
                   "Content/Python/pypcg_s14_measure.py {step: gen / dump} on the demo level (component seed 42, the "
                   "official stage-13 upstream: 5 lots). 'steps' runs each Python step on the TAPPED official upstream "
                   "with the editor's booleans; 'end_to_end' runs the whole stage from the tapped lots. n = [port, "
                   "official]; distances in cm; 'reversed' counts items that match only end to start.",
           "date": "2026-10-20", "steps": st, "end_to_end": e2e, "inner_ring_1_edge_lengths": tie}
    if args.get("instances"):
        doc["instances"] = args["instances"]
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    return {"written": OUT, "e2e_notes": notes}


def finish(args):
    """`s14_parkings_finish` on the TAPPED official points (Subgraph_7, 53, 54, the tiles, the arrows, both car
    sets, in Subgraph_3's order) with the tapped terrain (the volume must hold the tap graph, generated), against
    the official `Gather_0` output point for point; merged into the data file under 'finish'."""
    import math
    import time
    from pypcg import census, geo
    from pypcg.geo import assets as AS
    from pypcg.stages import s14_parkings_finish as F
    pc = census.component(STAGE)
    g = pc.get_graph()
    if g is None or g.get_path_name().split(".")[0] != GRAPH:
        return {"abort": "the stage-14 volume does not hold %s" % GRAPH}
    taps = _taps(pc)
    surface = next((v for v, _t, _c in taps.get("T_terrain", []) if hasattr(v, "height")), None)
    items, _polys, _paths = _from_taps()
    order = ("T_lines", "T_barrier", "T_fence", "T_tiles", "T_arrows", "T_fwd", "T_rev")
    ins = [p for tap in order for p in items(tap)]
    t0 = time.perf_counter()
    mine, notes = F.finish(ins, surface)
    seconds = time.perf_counter() - t0
    theirs = items("T_final")
    r = {"items": [len(mine), len(theirs)], "points": [sum(len(p) for p in mine), sum(len(p) for p in theirs)],
         "notes": notes, "seconds": round(seconds, 2), "surface": type(surface).__name__}
    if [len(p) for p in mine] == [len(p) for p in theirs]:
        dl, dq, same_asset, exact_loc, n = 0.0, 0.0, 0, 0, 0
        for a, b in zip(mine, theirs):
            for j in range(len(b)):
                n += 1
                d = math.dist(a.loc[j], b.loc[j])
                dl = max(dl, d)
                exact_loc += a.loc[j] == b.loc[j]
                qa, qb = AS.quat_of(*a.rot[j]), tuple(b.quat[j]) if b.quat else AS.quat_of(*b.rot[j])
                dq = max(dq, min(max(abs(x - y) for x, y in zip(qa, qb)), max(abs(x + y) for x, y in zip(qa, qb))))
                same_asset += str(a.attrs.get("Asset", [None] * len(a))[j]) == str(b.attrs.get("Asset", [None] * len(b))[j])
        r.update(compared=n, max_loc_diff_cm=dl, loc_bit_exact=exact_loc, max_quat_diff=dq, same_asset=same_asset)
    doc = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    doc["finish"] = r
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    return r


def barriers(args):
    """Where the extra barrier is (fix round 1): the concrete-barrier modules of a slim run (its finish record's
    inputs, `Saved/Reports/v2/s14/<record>` or the live `Saved/PyPCG/runs/s14_finish.json`) and of the official
    tap, each module assigned to the nearest of ITS OWN graph's barrier lines (central lines, then border runs),
    the lines paired by midpoint. Collinear halves of one cut edge trade modules across the entrance gap, so each
    such pair is compared by its sum. Merged into the data file under 'barriers'."""
    import math
    from pypcg import geo
    from pypcg.geo import splines as SP
    from pypcg.stage_api import RUNS_DIR
    items, _polys, _paths = _from_taps()
    fin = json.load(open(os.path.join(RUNS_DIR, "s14_finish.json"), encoding="utf-8"))
    main = json.load(open(os.path.join(_REPO, "Saved", "Reports", "v2", "s14", args.get("record", "slim_42.run.json")),
                          encoding="utf-8"))
    if fin["params"] != main["params"]:
        return {"abort": "the finish record (%s) is not the run of %s" % (fin["params"], main["params"])}

    def bars(pts):
        return [p for p in pts if len(p) and any(k in str((p.attrs.get("Asset") or [""])[0])
                                                  for k in ("Concrete_Barrier", "sdsbo"))]
    port_bars = bars([geo.from_json(v) for v, _t in fin["inputs"]["Points"]])
    off_bars = bars(items("T_barrier"))
    lines = {"port": [[tuple(q) for q in geo.from_json(v).points] for pin in ("CentralLines", "Border")
                      for v, _t in main["outputs"][pin]],
             "official": [[tuple(q) for q in s.points] for tap in ("T_central", "T_border") for s in items(tap)]}
    n_central = {"port": len(main["outputs"]["CentralLines"]), "official": len(items("T_central"))}

    def dpath(pt, path):
        best = 1e18
        for a, b in zip(path, path[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = dx * dx + dy * dy
            t = 0.0 if L == 0 else max(0.0, min(1.0, ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / L))
            best = min(best, math.dist(pt, (a[0] + t * dx, a[1] + t * dy)))
        return best

    count = {}
    for name, bs in (("port", port_bars), ("official", off_bars)):
        c = [0] * len(lines[name])
        for p in bs:
            for q in p.loc:
                c[min(range(len(c)), key=lambda k: dpath(q[:2], lines[name][k]))] += 1
        count[name] = c

    def mid(p):
        return SP.center([p[0], p[-1]])[0][:2]
    pairs, used = [], set()
    for i, p in enumerate(lines["port"]):
        j = min((j for j in range(len(lines["official"])) if j not in used),
                key=lambda j: math.dist(mid(p), mid(lines["official"][j])))
        if math.dist(mid(p), mid(lines["official"][j])) < 5.0:
            used.add(j)
            pairs.append((i, j))
    # collinear halves of one cut edge: group matched border pairs whose port lines are collinear and end to end
    rows = []
    for i, j in pairs:
        kind = "central" if i < n_central["port"] else "border"
        rows.append({"kind": kind, "length_cm": [round(SP.length(lines["port"][i]), 3),
                                                 round(SP.length(lines["official"][j]), 3)],
                     "points": [len(lines["port"][i]), len(lines["official"][j])],
                     "modules": [count["port"][i], count["official"][j]], "port": i, "official": j})
    unmatched = {"port": [{"length_cm": round(SP.length(lines["port"][i]), 2), "modules": count["port"][i]}
                          for i in range(len(lines["port"])) if i not in {a for a, _b in pairs}],
                 "official": [{"length_cm": round(SP.length(lines["official"][j]), 2), "modules": count["official"][j]}
                              for j in range(len(lines["official"])) if j not in used]}
    differ = [r for r in rows if r["modules"][0] != r["modules"][1]]
    r = {"seed": main["params"], "modules": [sum(count["port"]), sum(count["official"])],
         "central_modules": [sum(count["port"][:n_central["port"]]), sum(count["official"][:n_central["official"]])],
         "border_modules": [sum(count["port"][n_central["port"]:]), sum(count["official"][n_central["official"]:])],
         "matched_lines_with_different_modules": differ, "unmatched": unmatched}
    doc = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    doc["barriers"] = r
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    return r


STEPS = {"gen": gen, "dump": dump, "measure": measure, "finish": finish, "barriers": barriers}

try:
    _a = mcp_args or {}
    from pypcg import level as _level
    # Final review I2: the tap graph goes onto the stage-14 volume, so only the demo's volume may get it.
    mcp_result = _level.require(_level.DEMO, "pypcg_s14_measure.py") or \
        json.loads(json.dumps(STEPS[_a.get("step", "dump")](_a), default=str))
except Exception as _exc:
    import traceback
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600]), "tb": traceback.format_exc()[-1500:]}
gc.collect()
