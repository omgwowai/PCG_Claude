# tl_probe_spline_building.py -- acceptance probe for the spline building
# (docs/superpowers/plans/2026-10-12-tl-spline-building.md Task 11, Step 2).
# Reads EVERY test building in /Game/Map/Lvl_TL_Spline (the labels in
# BUILDING_HEIGHTS) from the spawned ISM instances' world transforms, and checks
# them against Tools/tl_kit/corner_math.py and the TL kit spec.
#
# Args: {"phase": "read" | "gen_reverse" | "read_reverse" | "gen_bdf" | "read_bdf",
#        "full": true}  (read returns a compact view unless full; every phase
#        writes its complete result to Saved/tl11/probe_<phase>.json)
#   read          A1-A3, A5, A6 (+ storey stacks), Review Focus 1 and 4 on every
#                 building; also writes TL_L's instance snapshot (Focus 2 baseline),
#                 so run it with TL_L's spline in its ORIGINAL order.
#   gen_reverse   sets TL_L's spline to the reverse of the order the read phase
#                 recorded and regenerates (keeps the component's graph and its
#                 Height override -- never set_graph, which resets Height to
#                 the graph default 5000). {"restore": true} puts the recorded
#                 order back. {"step": "cleanup"} then {"step": "generate"} in
#                 two calls proves the later read is fresh output.
#   read_reverse  Review Focus 2: TL_L's instances vs the baseline snapshot.
#   gen_bdf       A4: spawns TLPROBE_Bdf, a PCGVolume running
#                 /Game/PCG/TL/PCG_TL_Building_BDF with WingA = WingB = 6000 x 3000.
#   read_bdf      A4: TL_Rect's L1 runs vs TLPROBE_Bdf's; destroys TLPROBE_Bdf.
# Generation is asynchronous: every gen_* phase is read in a LATER call.
#
# UObjects are only held in function locals (traps.md 40).
import collections
import json
import math
import os
import re
import sys

TOOLS = "E:/PCG_Claude/Tools/tl_kit"
sys.path.insert(0, TOOLS)
import importlib
import corner_math
import kit_common
importlib.reload(kit_common)
importlib.reload(corner_math)

args = mcp_args or {}
PHASE = args.get("phase", "read")
GRAPH_PATH = "/Game/PCG/TL/PCG_TL_SplineBuilding"
BDF_GRAPH = "/Game/PCG/TL/PCG_TL_Building_BDF"
BDF_LABEL = "TLPROBE_Bdf"
SNAP_DIR = "E:/PCG_Claude/Saved/tl11"

# Requested Height per building -- must match tl_spline_level.BUILDINGS.
BUILDING_HEIGHTS = {"TL_Hex": 3000.0, "TL_Pent": 3000.0, "TL_L": 3000.0,
                    "TL_Rect": 3000.0, "TL_Low": 1000.0, "TL_Tilt": 3000.0}

PIER_TOL_CM = 0.05      # A1
YAW_TOL_DEG = 0.01      # A2 / A3
SCALE_TOL = 1e-4        # A2
LINE_TOL_CM = 0.05      # A6 module ends on the facade line / abutting
Z_TOL_CM = 0.05

# ---- independent data: the kit spec (widths, storey heights) and TL's BDF row
SPEC = json.load(open(TOOLS + "/tl_kit_spec.json"))
WIDTH = {(p["level"], p["part"]): p["width_m"] * 100.0 for p in SPEC["parts"]}
LEVEL_H = {int(k): v["height_m"] * 100.0 for k, v in SPEC["levels"].items()}
LEVEL_H[0] = kit_common.FOUNDATION_LEVEL_HEIGHT_CM   # LV0 is 0.5 cm in the grammar
VERTICAL_GRAMMAR = "[LV0][LV1][LV2]*[LV3][LV4]"      # tl_make_bdf.TL_BDF["VerticalGrammar"]

SYM_PART = {"EL": "EndPier_01", "ER": "EndPier_01", "EAL": "EndPierAcute_01",
            "EAR": "EndPierAcute_01", "W1": "Wall_01", "E1": "Entrance_01",
            "P1": "Column_01", "P2": "Column_02", "FS2": "Foundation_01"}


def sym_part(sym, lv):
    if sym == "WS1":   # the level's filler; L4 has no Wall_02 and stretches Wall_01
        return "Wall_02" if (lv, "Wall_02") in WIDTH else "Wall_01"
    return SYM_PART[sym]


# ------------------------------------------------------------------ models
def storey_stack(height):
    """Expected (level, base z) list for a building of `height`, from
    VERTICAL_GRAMMAR and the spec's level heights: fixed levels once, the
    `*` level as many whole times as fit (non-scalable levels, so no stretch)."""
    toks = re.findall(r"\[LV(\d)\]([*+]?)", VERTICAL_GRAMMAR)
    fixed = sum(LEVEL_H[int(l)] for l, r in toks if r != "*")
    reps = {}
    for l, r in toks:
        if r:
            n = int(math.floor((height - fixed) / LEVEL_H[int(l)] + 1e-9))
            reps[int(l)] = max(n + (1 if r == "+" else 0), 1 if r == "+" else 0)
    out, z = [], 0.0
    for l, r in toks:
        lv = int(l)
        for _ in range(reps.get(lv, 1) if r else 1):
            out.append((lv, z))
            z += LEVEL_H[lv]
    return {"fixed_cm": fixed, "repeats": reps, "storeys": out, "top": z,
            "fits": height >= fixed}


BOUNDARY_CM = 1e-6      # an edge this close to a whole-module boundary may expand either way


def expand_edge(plan, lv, slack=0.0):
    """Part multiset for one storey edge (corner_math.edge_plan), following
    PCGSubdivisionBase::Subdivide: the fixed modules once ('+' groups once),
    then one more of each repeat group per pass, in order, while its size is
    not greater than what remains; the remainder goes to the scalable filler.
    The engine compares exactly (no tolerance); `slack` shifts the remaining
    length so the caller can ask what the other side of a boundary gives."""
    if plan["short"]:
        return collections.Counter({sym_part(plan["symbol"], lv): 1}), 0.0
    toks = re.findall(r"\[([^\]]+)\]([+*]?)", plan["grammar"])
    fixed, reps = [], []
    for body, r in toks:
        syms = body.split(",")
        if r:
            reps.append(syms)
        if r != "*":
            fixed.extend(syms)
    w = lambda s: WIDTH[(lv, sym_part(s, lv))]
    rem = plan["length"] - sum(w(s) for s in fixed) + slack
    counts = collections.Counter(sym_part(s, lv) for s in fixed)
    added = True
    while added and reps:
        added = False
        for syms in reps:
            gw = sum(w(s) for s in syms)
            if gw <= rem:
                rem -= gw
                counts.update(sym_part(s, lv) for s in syms)
                added = True
    return counts, rem


def expansions(plan, lv):
    """The model's expansion, plus the alternative one when the edge length is
    within BOUNDARY_CM of a whole-module boundary (a floating-point tie the
    model cannot call: e.g. the hexagon's 3000 cm edges are 2999.9999999999995
    after cos/sin, one 200 cm foundation piece short of 15)."""
    base, _ = expand_edge(plan, lv)
    alts = [base]
    for sl in (BOUNDARY_CM, -BOUNDARY_CM):
        c, _ = expand_edge(plan, lv, sl)
        if c not in alts:
            alts.append(c)
    return alts


# ------------------------------------------------------------------ reading
def actors():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    return {a.get_actor_label(): a for a in eas.get_all_level_actors()}


def footprint3(a):
    sc = a.get_component_by_class(unreal.SplineComponent)
    return [sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD).to_tuple()
            for i in range(sc.get_number_of_spline_points())]


def parse_mesh(name):
    m = re.match(r"SM_BLDG_TL_L0(\d)_A_(.+)_N1$", name)
    return (int(m.group(1)), m.group(2)) if m else (None, None)


def instances(a):
    """Every ISM instance of actor a: mesh name, kit level/part, world transform
    pieces, and the mesh's local box (for run extents)."""
    out = []
    for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None:
            continue
        name = sm.get_name()
        lv, part = parse_mesh(name)
        box = sm.get_bounding_box()
        for k in range(c.get_instance_count()):
            t = c.get_instance_transform(k, True)
            r = t.rotation.rotator()
            rec = {"mesh": name, "lv": lv, "part": part,
                   "pos": t.translation.to_tuple(), "yaw": r.yaw, "pitch": r.pitch, "roll": r.roll,
                   "scale": t.scale3d.to_tuple()}
            if part is not None and not part.startswith("Fan"):
                y0 = 0.0 if part.startswith("EndPier") else box.min.y
                y1 = 150.0 if part.startswith("EndPier") else box.max.y
                rec["p0"] = t.transform_location(unreal.Vector(0.0, y0, 0.0)).to_tuple()
                rec["p1"] = t.transform_location(unreal.Vector(0.0, y1, 0.0)).to_tuple()
                rec["run"] = (y1 - y0)
            out.append(rec)
    return out


def dynmesh_boxes(a):
    res = []
    for d in a.get_components_by_class(unreal.DynamicMeshComponent):
        o, e, _ = unreal.SystemLibrary.get_component_bounds(d)
        res.append([round(v, 2) for v in o.to_tuple() + e.to_tuple()])
    return sorted(res)


# ------------------------------------------------------------------ geometry
def dist_pt_line(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    L = math.hypot(ax, ay)
    t = ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / L
    d = abs((p[0] - a[0]) * ay - (p[1] - a[1]) * ax) / L
    return d, t


def nearest_vertex(p, pts):
    best = min(range(len(pts)), key=lambda i: math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]))
    return best, math.hypot(p[0] - pts[best][0], p[1] - pts[best][1])


def worst(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return max(vals) if vals else None


# ------------------------------------------------------------------ checks
def check_building(label, a):
    H = unreal.PCGGraphParametersHelpers
    comp = a.get_component_by_class(unreal.PCGComponent)
    eff_h = H.get_double_parameter(comp.graph_instance, "Height")
    graph = comp.get_graph()
    p3 = footprint3(a)
    base_z = p3[0][2]
    pts = corner_math.clean([(p[0], p[1]) for p in p3])
    cls = corner_math.classify(pts)
    inst = instances(a)
    kit = [r for r in inst if r["part"] is not None]
    walls = [r for r in kit if not r["part"].startswith("Fan")]
    fans = [r for r in kit if r["part"].startswith("Fan")]
    stack = storey_stack(eff_h)
    R = {"height_requested": BUILDING_HEIGHTS[label], "height_effective": eff_h,
         "graph": graph.get_path_name() if graph else None,
         "n_instances": len(inst), "n_kit": len(kit), "n_fans": len(fans),
         "footprint_clean": [[round(x, 3) for x in p] for p in pts],
         "interior_deg": [round(180 - abs(c["turn"]) if c["convex"] else 180 + abs(c["turn"]), 3) for c in cls],
         "acute_vertices": [i for i, c in enumerate(cls) if c["acute"]],
         "stack_model": {"repeats": stack["repeats"], "top": stack["top"], "fits": stack["fits"]}}
    R["height_ok"] = abs(eff_h - BUILDING_HEIGHTS[label]) < 1e-6

    # ---- storeys: expected bases per level (independent) vs distinct Z found
    exp_bases = collections.defaultdict(list)
    for lv, z in stack["storeys"]:
        exp_bases[lv].append(base_z + z)
    got_bases = collections.defaultdict(set)
    for r in walls:
        z = r["pos"][2] - (LEVEL_H[0] / 2.0 if r["lv"] == 0 else 0.0)   # L0 meshes sit at the slot centre
        got_bases[r["lv"]].add(round(z, 2))
    fan_bases = collections.defaultdict(set)
    for r in fans:
        fan_bases[r["lv"]].add(round(r["pos"][2], 2))
    st_rows = []
    for lv in range(5):
        e = [round(z, 2) for z in exp_bases.get(lv, [])]
        g = sorted(got_bases.get(lv, set()))
        f = sorted(fan_bases.get(lv, set()))
        ok = len(e) == len(g) == len(f) and all(abs(x - y) <= Z_TOL_CM for x, y in zip(e, g)) \
            and all(abs(x - y) <= Z_TOL_CM for x, y in zip(e, f))
        st_rows.append({"lv": lv, "n_expected": len(e), "n_walls": len(g), "n_fans": len(f), "ok": ok,
                        "expected_z": e[:3] + (["..."] if len(e) > 3 else []),
                        "walls_z": g[:3] + (["..."] if len(g) > 3 else [])})
    R["storeys"] = {"pass": all(r["ok"] for r in st_rows), "levels": st_rows,
                    "stack": "+".join("L%d" % lv for lv, _ in stack["storeys"])}

    def storey_of(r):
        z = r["pos"][2] - (LEVEL_H[0] / 2.0 if (r["lv"] == 0 and not r["part"].startswith("Fan")) else 0.0)
        return (r["lv"], round(z, 1))

    # ---- A1 / A5: piers
    a1, a5 = [], []
    for r in walls:
        if not r["part"].startswith("EndPier"):
            continue
        v0, d0 = nearest_vertex(r["p0"], pts)
        v1, d1 = nearest_vertex(r["p1"], pts)
        v, d = (v0, d0) if d0 <= d1 else (v1, d1)
        a1.append({"d": d, "vertex": v, "storey": storey_of(r)})
        is_acute_mesh = r["part"] == "EndPierAcute_01"
        a5.append({"vertex": v, "mesh_acute": is_acute_mesh, "vertex_acute": cls[v]["acute"],
                   "ok": is_acute_mesh == cls[v]["acute"]})
    R["A1"] = {"pass": bool(a1) and worst(a1, "d") <= PIER_TOL_CM, "n_piers": len(a1),
               "worst_cm": worst(a1, "d")}
    bad5 = [x for x in a5 if not x["ok"]]
    R["A5"] = {"pass": bool(a5) and not bad5, "n_piers": len(a5),
               "n_acute_piers": sum(1 for x in a5 if x["mesh_acute"]), "bad": bad5[:6]}

    # ---- A2 / A3: fans per storey and vertex
    model = {i: corner_math.fan(pts, i) for i in range(len(pts))}
    s_area = 1.0 if corner_math.signed_area(pts) > 0 else -1.0
    groups, off_vertex = collections.defaultdict(list), []
    pivot_d = 0.0
    for r in fans:
        v, d = nearest_vertex(r["pos"], pts)
        if d > 1.0:
            off_vertex.append(r)
            continue
        pivot_d = max(pivot_d, d)
        groups[(storey_of(r), v)].append(r)
    a2_rows, a3_rows = [], []
    for (st, v), fs in sorted(groups.items()):
        want = model[v]
        kinds = sorted({"front" if f["part"] == "FanFront_01" else "back" for f in fs})
        row = {"storey": st, "vertex": v, "n_got": len(fs), "n_want": len(want), "kinds": kinds}
        ok = len(fs) == len(want) and want and kinds == [want[0]["kind"]]
        if ok:
            # nearest match on the circle (each model slice claims its closest instance)
            free = list(fs)
            matched = []
            for s in want:
                j = min(range(len(free)), key=lambda q: abs(corner_math.wrap(free[q]["yaw"] - s["yaw"])))
                matched.append(free.pop(j))
            dyaw = max(abs(corner_math.wrap(f["yaw"] - s["yaw"])) for f, s in zip(matched, want))
            dsx = max(abs(f["scale"][0] - s["sx"]) for f, s in zip(matched, want))
            dsy = max(abs(f["scale"][1] - s["sy"]) for f, s in zip(matched, want))
            dsz = max(abs(f["scale"][2] - 1.0) for f in matched)
            tilt = max(max(abs(f["pitch"]), abs(f["roll"])) for f in matched)
            row.update(dyaw=dyaw, dsx=dsx, dsy=dsy, dsz=dsz, tilt=tilt)
            ok = dyaw <= YAW_TOL_DEG and max(dsx, dsy, dsz) <= SCALE_TOL and tilt <= YAW_TOL_DEG
            # A3 from the measured yaws, ordered along the sweep (model index k)
            prev, cur, nxt = pts[v - 1], pts[v], pts[(v + 1) % len(pts)]
            na = corner_math.exterior_normal_deg(prev, cur, s_area)
            nb = corner_math.exterior_normal_deg(cur, nxt, s_area)
            sweep = corner_math.wrap(nb - na)
            sg = 1.0 if sweep > 0 else -1.0
            ya = [f["yaw"] for f in matched]
            aa = [s["a"] for s in want]
            steps = [abs(corner_math.wrap(ya[k + 1] - ya[k] - sg * (aa[k] + aa[k + 1])))
                     for k in range(len(ya) - 1)]
            first = abs(corner_math.wrap(ya[0] - sg * aa[0] - na))
            last = abs(corner_math.wrap(ya[-1] + sg * aa[-1] - nb))
            e3 = max(steps + [first, last])
            a3_rows.append({"storey": st, "vertex": v, "err": e3, "first": first, "last": last,
                            "max_step": max(steps) if steps else 0.0})
        row["ok"] = bool(ok)
        a2_rows.append(row)
    want_groups = {((lv, round(base_z + z, 1)), v) for lv, z in stack["storeys"] for v in model if model[v]}
    missing = sorted(want_groups - set(groups))
    bad2 = [r for r in a2_rows if not r["ok"]]
    R["A2"] = {"pass": bool(a2_rows) and not bad2 and not missing and not off_vertex
               and pivot_d <= PIER_TOL_CM,
               "n_groups": len(a2_rows), "n_slices": len(fans),
               "worst_dyaw": worst(a2_rows, "dyaw"), "worst_dscale": max(
                   [max(r.get("dsx", 0), r.get("dsy", 0), r.get("dsz", 0)) for r in a2_rows] or [None]),
               "worst_pivot_cm": pivot_d, "n_off_vertex": len(off_vertex),
               "missing": missing[:6], "bad": bad2[:6],
               "model_per_vertex": [{"v": i, "n": len(m), "kind": m[0]["kind"] if m else None,
                                     "a": round(m[0]["a"], 4) if m else None} for i, m in model.items()]}
    R["A3"] = {"pass": bool(a3_rows) and worst(a3_rows, "err") <= YAW_TOL_DEG,
               "n_groups": len(a3_rows), "worst_deg": worst(a3_rows, "err"),
               "worst_first_last": max([max(r["first"], r["last"]) for r in a3_rows] or [None])}

    # ---- A6: per storey edge, part multiset vs edge_plan, and the run coverage
    n = len(pts)
    per_edge = collections.defaultdict(list)
    unassigned = []
    for r in walls:
        best = None
        for i in range(n):
            p0, p1 = pts[i], pts[(i + 1) % n]
            d0, t0 = dist_pt_line(r["p0"], p0, p1)
            d1, t1 = dist_pt_line(r["p1"], p0, p1)
            L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            if max(d0, d1) < 2.0 and -1.0 <= min(t0, t1) and max(t0, t1) <= L + 1.0:
                if best is None or max(d0, d1) < best[1]:
                    best = (i, max(d0, d1), min(t0, t1), max(t0, t1))
        if best is None:
            unassigned.append({"mesh": r["mesh"], "p0": r["p0"], "p1": r["p1"]})
            continue
        per_edge[(storey_of(r), best[0])].append((r["part"], best[1], best[2], best[3], r))
    a6_rows = []
    boundary = []
    off_line = 0.0
    for lv, z in stack["storeys"]:
        st = (lv, round(base_z + z, 1))
        for i in range(n):
            plan = corner_math.edge_plan(pts, i, lv)
            alts = expansions(plan, lv)
            mods = per_edge.get((st, i), [])
            got = collections.Counter(m[0] for m in mods)
            want = got if got in alts else alts[0]
            if got in alts[1:]:
                boundary.append({"storey": st, "edge": i, "len": plan["length"],
                                 "model": dict(alts[0]), "placed": dict(got)})
            off_line = max([off_line] + [m[1] for m in mods])
            iv = sorted((m[2], m[3]) for m in mods)
            gaps = [abs(iv[k + 1][0] - iv[k][1]) for k in range(len(iv) - 1)]
            cover = max(gaps + ([abs(iv[0][0]), abs(iv[-1][1] - plan["length"])] if iv else [1e9]))
            ok = got == want and cover <= LINE_TOL_CM
            row = {"storey": st, "edge": i, "len": round(plan["length"], 2),
                   "rule": plan["grammar"] or "[%s] short" % plan["symbol"],
                   "ok": ok, "cover_err": cover}
            if got != want:
                row["got"] = dict(got)
                row["want"] = dict(want)
            a6_rows.append(row)
    bad6 = [r for r in a6_rows if not r["ok"]]
    R["A6"] = {"pass": bool(a6_rows) and not bad6 and not unassigned and off_line <= LINE_TOL_CM
               and R["storeys"]["pass"],
               "n_storey_edges": len(a6_rows), "n_bad": len(bad6), "bad": bad6[:6],
               "worst_cover_cm": worst(a6_rows, "cover_err"), "worst_off_line_cm": off_line,
               "n_unassigned": len(unassigned), "unassigned": unassigned[:4],
               "n_boundary_ties": len(boundary), "boundary_ties": boundary[:4],
               "storey_count_pass": R["storeys"]["pass"]}
    return R


def snapshot(a):
    rows = []
    for r in instances(a):
        rows.append([r["mesh"]] + [round(v, 3) for v in r["pos"]] +
                    [corner_math.wrap(r["yaw"]), r["pitch"], r["roll"]] + list(r["scale"]))
    return {"spline": [list(p) for p in footprint3(a)], "rows": rows, "dyn": dynmesh_boxes(a)}


def compare_snap(A, B):
    by = collections.defaultdict(lambda: ([], []))
    for r in A["rows"]:
        by[r[0]][0].append(r)
    for r in B["rows"]:
        by[r[0]][1].append(r)
    worst_pos, worst_yaw, worst_scale, count_diff, unmatched = 0.0, 0.0, 0.0, {}, 0
    cat = collections.Counter()
    for mesh, (ra, rb) in by.items():
        if len(ra) != len(rb):
            count_diff[mesh] = [len(ra), len(rb)]
        free = list(rb)
        for x in ra:
            if not free:
                unmatched += 1
                continue
            j = min(range(len(free)), key=lambda q: (free[q][1] - x[1]) ** 2 + (free[q][2] - x[2]) ** 2 +
                    (free[q][3] - x[3]) ** 2)
            y = free.pop(j)
            dp = math.sqrt(sum((y[k] - x[k]) ** 2 for k in (1, 2, 3)))
            dyw = max(abs(corner_math.wrap(y[4] - x[4])), abs(y[5] - x[5]), abs(y[6] - x[6]))
            ds = max(abs(y[k] - x[k]) for k in (7, 8, 9))
            if dp > LINE_TOL_CM or dyw > YAW_TOL_DEG or ds > SCALE_TOL:
                cat[mesh] += 1
            worst_pos, worst_yaw, worst_scale = max(worst_pos, dp), max(worst_yaw, dyw), max(worst_scale, ds)
    return {"n_a": len(A["rows"]), "n_b": len(B["rows"]), "count_diff": count_diff,
            "n_unmatched": unmatched, "worst_pos_cm": worst_pos, "worst_rot_deg": worst_yaw,
            "worst_scale": worst_scale, "meshes_with_diffs": dict(cat),
            "dyn_equal": A["dyn"] == B["dyn"], "dyn_a": A["dyn"], "dyn_b": B["dyn"]}


def n_instances(a):
    return sum(c.get_instance_count() for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent))


def regen(a, step=None):
    """Clean up and regenerate WITHOUT touching the component's graph (a
    set_graph would reset the Height override to the graph default).
    cleanup_local is deferred (measured: the instances are still there in the
    same call), so to PROVE a later read sees fresh output run it as two
    calls: step "cleanup", then step "generate", which reports the instance
    count it found (0 = the old output is gone) before generating."""
    comp = a.get_component_by_class(unreal.PCGComponent)
    R = {"instances_at_call": n_instances(a)}
    comp.activate(True)
    if step in (None, "cleanup"):
        comp.cleanup_local(True)
    if step in (None, "generate"):
        comp.generate_local(True)
    return R


def phase_gen_reverse():
    """Set TL_L's spline to the REVERSE of the order the read phase recorded
    (or back to that order with {"restore": true}) and regenerate."""
    A = actors()
    a = A["TL_L"]
    sc = a.get_component_by_class(unreal.SplineComponent)
    base = [tuple(p) for p in json.load(open(SNAP_DIR + "/TL_L_read.json"))["spline"]]
    order = base if args.get("restore") else list(reversed(base))
    step = args.get("step")
    if step != "generate":
        sc.clear_spline_points(False)
        for p in order:
            sc.add_spline_point(unreal.Vector(*p), unreal.SplineCoordinateSpace.WORLD, False)
        for i in range(len(order)):
            sc.set_spline_point_type(i, unreal.SplinePointType.LINEAR, False)
        sc.set_closed_loop(True, False)
        sc.update_spline()
    comp = a.get_component_by_class(unreal.PCGComponent)
    h = unreal.PCGGraphParametersHelpers.get_double_parameter(comp.graph_instance, "Height")
    if abs(h - BUILDING_HEIGHTS["TL_L"]) > 1e-6:
        raise RuntimeError("TL_L Height override is %r, not %r" % (h, BUILDING_HEIGHTS["TL_L"]))
    R = regen(a, step)
    now = footprint3(a)
    R.update(fired=step != "cleanup", step=step, height_effective=h, order="original" if args.get("restore") else "reversed",
             spline_now=[[round(v, 1) for v in p] for p in now],
             signed_area=corner_math.signed_area([(p[0], p[1]) for p in now]))
    return R


def phase_read():
    A = actors()
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    R = {"world": w.get_path_name(), "buildings": {}}
    for label in BUILDING_HEIGHTS:
        if label not in A:
            R["buildings"][label] = {"error": "missing"}
            continue
        R["buildings"][label] = check_building(label, A[label])
    B = R["buildings"]
    # Review Focus 1: TL_Tilt (one vertex 50 cm up) -- every storey one Z, the
    # same Zs as the flat TL_Rect of the same Height.
    tilt, rect = B.get("TL_Tilt", {}), B.get("TL_Rect", {})
    f1_same = [r["expected_z"] == s["expected_z"] and r["walls_z"] == s["walls_z"]
               for r, s in zip(tilt.get("storeys", {}).get("levels", []), rect.get("storeys", {}).get("levels", []))]
    R["Focus1"] = {"pass": bool(tilt) and tilt["storeys"]["pass"] and all(f1_same),
                   "tilt_levels": tilt.get("storeys", {}).get("levels")}
    low = B.get("TL_Low", {})
    lv = {r["lv"]: r["n_walls"] for r in low.get("storeys", {}).get("levels", [])}
    R["Focus4"] = {"pass": lv.get(1, 0) > 0 and lv.get(4, 0) > 0, "walls_storeys_per_level": lv,
                   "stack": low.get("storeys", {}).get("stack"), "top_cm": low.get("stack_model", {}).get("top")}
    pent = B.get("TL_Pent", {})
    R["Focus3_pent"] = {"pass": all(pent.get(k, {}).get("pass") for k in ("A1", "A2", "A3", "A5", "A6")),
                        "interior_deg": pent.get("interior_deg"), "acute_vertices": pent.get("acute_vertices")}
    for k in ("A1", "A2", "A3", "A5", "A6"):
        rows = {lab: b[k] for lab, b in B.items() if k in b}
        R[k] = {"pass": bool(rows) and all(v["pass"] for v in rows.values())}
    R["summary"] = {k: R[k]["pass"] for k in ("A1", "A2", "A3", "A5", "A6", "Focus1", "Focus4", "Focus3_pent")}
    # Focus 2 baseline
    os.makedirs(SNAP_DIR, exist_ok=True)
    snap = snapshot(A["TL_L"])
    with open(SNAP_DIR + "/TL_L_read.json", "w") as f:
        json.dump(snap, f)
    R["focus2_baseline_rows"] = len(snap["rows"])
    return R


def phase_read_reverse():
    A = actors()
    base = json.load(open(SNAP_DIR + "/TL_L_read.json"))
    now = snapshot(A["TL_L"])
    reversed_ok = [list(map(lambda v: round(v, 3), p)) for p in reversed(base["spline"])] == \
        [list(map(lambda v: round(v, 3), p)) for p in now["spline"]]
    cmp = compare_snap(base, now)
    kit_only = compare_snap({"rows": [r for r in base["rows"] if r[0].startswith("SM_BLDG_TL_")], "dyn": base["dyn"]},
                            {"rows": [r for r in now["rows"] if r[0].startswith("SM_BLDG_TL_")], "dyn": now["dyn"]})
    comp = A["TL_L"].get_component_by_class(unreal.PCGComponent)
    h = unreal.PCGGraphParametersHelpers.get_double_parameter(comp.graph_instance, "Height")
    ok = (reversed_ok and not cmp["count_diff"] and not cmp["n_unmatched"] and not cmp["meshes_with_diffs"]
          and cmp["dyn_equal"])
    return {"Focus2": {"pass": ok, "spline_is_reversed": reversed_ok, "height_effective": h,
                       "all_instances": cmp, "kit_only": kit_only}}


# ------------------------------------------------------------------ A4
def phase_gen_bdf():
    A = actors()
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if BDF_LABEL in A:
        eas.destroy_actor(A[BDF_LABEL])
    origin = unreal.Vector(*args.get("origin", [40000.0, 0.0, 0.0]))
    vol = eas.spawn_actor_from_class(unreal.PCGVolume, origin)
    vol.set_actor_label(BDF_LABEL)
    vol.set_actor_scale3d(unreal.Vector(80.0, 80.0, 80.0))
    comp = vol.get_component_by_class(unreal.PCGComponent)
    comp.set_graph(unreal.EditorAssetLibrary.load_asset(BDF_GRAPH))
    H = unreal.PCGGraphParametersHelpers
    gi = comp.get_editor_property("graph_instance")
    for n, v in (("WingALength", 6000.0), ("WingAWidth", 3000.0), ("WingBLength", 6000.0), ("WingBWidth", 3000.0)):
        H.set_double_parameter(gi, n, v)
    params = {n: H.get_double_parameter(gi, n) for n in
              ("BaseLayerHeight", "SecondLayerHeight", "WingAWidth", "WingALength", "WingBWidth", "WingBLength")}
    comp.activate(True)
    comp.cleanup_local(True)
    comp.generate_local(True)
    return {"fired": True, "params": params}


A4_PARTS = ("Wall_01", "Wall_02", "Column_01", "Entrance_01")     # W1 / WS1 / P1 / E1


def facades(inst_rows, lv):
    """Group the lowest storey's level-lv wall modules by facade: travel
    direction (the module's local +Y in the world) and across-facade offset
    (along the exterior normal, local +X). Returns a list of
    {"dir": (dx, dy), "across": cm, "mods": [(part, t0, t1)] sorted by t0},
    t measured along dir in world cm."""
    rows = [r for r in inst_rows if r["lv"] == lv and r.get("part") in A4_PARTS]
    if not rows:
        return []
    z0 = min(r["pos"][2] for r in rows)
    groups = collections.defaultdict(list)
    for r in rows:
        if abs(r["pos"][2] - z0) > Z_TOL_CM:
            continue
        dx, dy = r["p1"][0] - r["p0"][0], r["p1"][1] - r["p0"][1]
        L = math.hypot(dx, dy)
        dx, dy = dx / L, dy / L
        across = r["p0"][0] * dy - r["p0"][1] * dx
        key = (round(math.degrees(math.atan2(dy, dx)), 1), round(across, 1))
        groups[key].append((r["part"], r["p0"][0] * dx + r["p0"][1] * dy, r["p1"][0] * dx + r["p1"][1] * dy,
                            (dx, dy), across))
    out = []
    for key, ms in groups.items():
        ms.sort(key=lambda m: m[1])
        out.append({"key": key, "dir": ms[0][3], "across": sum(m[4] for m in ms) / len(ms),
                    "mods": [(m[0], m[1], m[2]) for m in ms]})
    return out


def phase_read_bdf():
    """A4. Runs of W1/WS1/P1/E1 along a 6000 cm facade, measured from the
    facade's START VERTEX in both routes: for the spline building that is the
    footprint vertex; for the BDF route it is the pivot of the corner piece
    that starts the facade (same yaw as the walls) -- an origin that does not
    depend on the walls being compared. The BDF corner piece's slot [0, 150]
    is the spline route's end pier [0, 150]."""
    A = actors()
    if BDF_LABEL not in A:
        return {"error": "no %s; run phase gen_bdf first" % BDF_LABEL}
    bdf_inst = instances(A[BDF_LABEL])
    rect_inst = instances(A["TL_Rect"])
    pts = corner_math.clean([(p[0], p[1]) for p in footprint3(A["TL_Rect"])])
    R = {"n_bdf_instances": len(bdf_inst)}

    # spline route: every 6000 cm edge of TL_Rect
    sp = []
    for i in range(len(pts)):
        p0, p1 = pts[i], pts[(i + 1) % len(pts)]
        L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        if abs(L - 6000.0) > 0.01:
            continue
        d = ((p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L)
        across_v = p0[0] * d[1] - p0[1] * d[0]
        for f in facades(rect_inst, 1):
            if abs(f["dir"][0] - d[0]) < 1e-3 and abs(f["dir"][1] - d[1]) < 1e-3 and abs(f["across"] - across_v) < 5.0:
                origin = p0[0] * d[0] + p0[1] * d[1]
                sp.append({"edge": i, "across_offset_cm": f["across"] - across_v,
                           "runs": [(m[0], m[1] - origin, m[2] - origin) for m in f["mods"]]})
    # BDF route: every facade that has a start corner piece and 5700 cm of walls
    corners = [r for r in bdf_inst if r["lv"] == 1 and r.get("part", "") and r["part"].startswith("CornerEx")]
    bd = []
    for f in facades(bdf_inst, 1):
        covered = sum(m[2] - m[1] for m in f["mods"])
        if abs(covered - 5700.0) > 0.5:
            continue
        d = f["dir"]
        yaw = math.degrees(math.atan2(d[1], d[0])) - 90.0     # local +Y = d  ->  yaw = angle(d) - 90
        first = f["mods"][0][1]
        cand = []
        for c in corners:
            t = c["pos"][0] * d[0] + c["pos"][1] * d[1]
            ac = c["pos"][0] * d[1] - c["pos"][1] * d[0]
            if abs(corner_math.wrap(c["yaw"] - yaw)) < 1.0 and abs(ac - f["across"]) < 5.0 and 0 < first - t < 200.0                     and abs(c["pos"][2] - min(x["pos"][2] for x in corners)) < Z_TOL_CM:
                cand.append((t, ac))
        if len(cand) != 1:
            R.setdefault("facades_without_one_start_corner", []).append({"key": f["key"], "n": len(cand)})
            continue
        origin = cand[0][0]
        # the END vertex, from the next facade's corner piece (rotated 90 deg): its pivot along d
        ends = [c["pos"][0] * d[0] + c["pos"][1] * d[1] for c in corners
                if abs(corner_math.wrap(c["yaw"] - yaw)) > 1.0
                and abs((c["pos"][0] * d[1] - c["pos"][1] * d[0]) - f["across"]) < 5.0
                and 0 < c["pos"][0] * d[0] + c["pos"][1] * d[1] - f["mods"][-1][2] < 200.0]
        bd.append({"key": f["key"], "start_corner_across_cm": cand[0][1] - f["across"],
                   "facade_length_from_corner_pivots": (ends[0] - origin) if len(ends) == 1 else None,
                   "end_corner_pivot_across_cm": None if len(ends) != 1 else
                   [c["pos"][0] * d[1] - c["pos"][1] * d[0] - f["across"] for c in corners
                    if abs(corner_math.wrap(c["yaw"] - yaw)) > 1.0
                    and abs((c["pos"][0] * d[1] - c["pos"][1] * d[0]) - f["across"]) < 5.0
                    and 0 < c["pos"][0] * d[0] + c["pos"][1] * d[1] - f["mods"][-1][2] < 200.0][0],
                   "runs": [(m[0], m[1] - origin, m[2] - origin) for m in f["mods"]]})
    R["n_spline_facades"] = len(sp)
    R["n_bdf_facades"] = len(bd)
    pairs = []
    for b in bd:
        for q in sp:
            same = [m[0] for m in b["runs"]] == [m[0] for m in q["runs"]]
            w = max(max(abs(x[1] - y[1]), abs(x[2] - y[2])) for x, y in zip(b["runs"], q["runs"])) if same else None
            pairs.append({"bdf": b["key"], "spline_edge": q["edge"], "same_sequence": same, "worst_cm": w,
                          "n_runs": len(q["runs"])})
    R["pairs"] = pairs
    R["worst_cm"] = max([p["worst_cm"] for p in pairs if p["worst_cm"] is not None] or [None])
    R["pass"] = bool(pairs) and all(p["same_sequence"] and p["worst_cm"] <= PIER_TOL_CM for p in pairs)
    R["bdf_facades"] = [{k: v for k, v in b.items() if k != "runs"} for b in bd]
    R["spline_across_offset_cm"] = [q["across_offset_cm"] for q in sp]
    if bd and sp:
        R["bdf_runs_first_last"] = [bd[0]["runs"][0], bd[0]["runs"][-1]]
        R["spline_runs_first_last"] = [sp[0]["runs"][0], sp[0]["runs"][-1]]
        R["runs_bdf"] = [(m[0], round(m[1], 4), round(m[2], 4)) for m in bd[0]["runs"]]
        R["runs_spline"] = [(m[0], round(m[1], 4), round(m[2], 4)) for m in sp[0]["runs"]]
    if not args.get("keep"):
        comp = A[BDF_LABEL].get_component_by_class(unreal.PCGComponent)
        comp.cleanup_local(True)
        unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(A[BDF_LABEL])
        R["destroyed"] = BDF_LABEL not in actors()
    return {"A4": R}


def brief(R):
    """Compact view of a read result: per building one line per check with its
    worst value, and the details of anything that failed."""
    out = {"world": R["world"], "summary": R["summary"], "buildings": {}}
    for label, b in R["buildings"].items():
        if "error" in b:
            out["buildings"][label] = b
            continue
        row = {"height": b["height_effective"], "stack": b["storeys"]["stack"],
               "storeys_pass": b["storeys"]["pass"], "top_cm": b["stack_model"]["top"],
               "n_kit": b["n_kit"], "interior_deg": b["interior_deg"],
               "A1": [b["A1"]["pass"], b["A1"]["n_piers"], b["A1"]["worst_cm"]],
               "A2": [b["A2"]["pass"], b["A2"]["n_groups"], b["A2"]["n_slices"], b["A2"]["worst_dyaw"],
                      b["A2"]["worst_dscale"], b["A2"]["worst_pivot_cm"]],
               "A3": [b["A3"]["pass"], b["A3"]["n_groups"], b["A3"]["worst_deg"]],
               "A5": [b["A5"]["pass"], b["A5"]["n_piers"], b["A5"]["n_acute_piers"]],
               "A6": [b["A6"]["pass"], b["A6"]["n_storey_edges"], b["A6"]["n_bad"], b["A6"]["worst_cover_cm"],
                      b["A6"]["worst_off_line_cm"], b["A6"]["n_unassigned"], b["A6"]["n_boundary_ties"]]}
        fails = {}
        if not b["storeys"]["pass"]:
            fails["storeys"] = [r for r in b["storeys"]["levels"] if not r["ok"]]
        for k in ("A1", "A2", "A3", "A5", "A6"):
            if not b[k]["pass"]:
                fails[k] = b[k]
        if b["A6"]["n_boundary_ties"]:
            row["boundary_ties"] = b["A6"]["boundary_ties"]
        if fails:
            row["fails"] = fails
        out["buildings"][label] = row
    for k in ("Focus1", "Focus4", "Focus3_pent"):
        out[k] = R[k] if k != "Focus1" else {"pass": R[k]["pass"]}
    return out


def main():
    R = {"read": phase_read, "gen_reverse": phase_gen_reverse, "read_reverse": phase_read_reverse,
         "gen_bdf": phase_gen_bdf, "read_bdf": phase_read_bdf}[PHASE]()
    R = json.loads(json.dumps(R, default=str))
    os.makedirs(SNAP_DIR, exist_ok=True)
    with open("%s/probe_%s.json" % (SNAP_DIR, PHASE), "w") as f:
        json.dump(R, f, indent=1)
    if PHASE == "read" and not args.get("full"):
        R = brief(R)
    if PHASE == "read_bdf" and not args.get("full") and "A4" in R:
        R = {"A4": {k: v for k, v in R["A4"].items() if k not in ("runs_bdf", "runs_spline")}}
    return R


mcp_result = main()
