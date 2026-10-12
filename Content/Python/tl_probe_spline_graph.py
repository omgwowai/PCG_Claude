# tl_probe_spline_graph.py -- READ-ONLY on assets. Generate (phase "gen") or read
# (phase "read") PCG_TL_SplineBuilding on the actor labelled TLPROBE_Spline in
# the current level, and compare the edge stream (segments abc) against
# Tools/tl_kit/corner_math.py. Args: {"phase": "gen" | "read"}
#
# Fix round 1 (I1): the original comparison only checked "every predicted
# triple appears somewhere in the output" (want subset-of got, by (level,
# length, grammar) membership, ignoring which edge the row actually came
# from). That is one-directional and position-blind: a wrong graph that
# mislabels a vertex's convexity could add extra/wrong rows while every
# genuinely-convex edge still happens to supply a triple from the wanted set,
# and the check would still report mismatches == []. This version:
#   (1) also reports got - want as "unexpected" (not just want - got as
#       "missing"), so an extra/wrong row fails the probe;
#   (2) asserts the set of levels present is exactly {0,1,2,3,4} and
#       n_rows > 0;
#   (3) checks per-level multiplicity: for each level, the row count must
#       equal (number of footprint edges) x (number of distinct storey Z
#       values seen at that level) -- the repeat count is read from the data
#       itself (distinct rounded $Position.Z per level) and reported, not
#       assumed;
#   (4) compares PER EDGE, not by (level, length, grammar) multiset
#       membership: each row's segment start vertex is recovered from
#       $Position - Forward * SegLen/2 (Forward from the row's own rotation)
#       and matched to a footprint vertex, which identifies exactly which
#       edge (pts[i] -> pts[i+1]) the row belongs to. want/got are then
#       compared as (level, edge_index, length, grammar) tuples -- two edges
#       of equal length but different expected grammar (e.g. a convex vs. an
#       adjacent concave corner's edges) can no longer be confused for one
#       another the way multiset membership could.
import json
import sys

sys.path.insert(0, "E:/PCG_Claude/Tools/tl_kit")
import importlib
import corner_math
importlib.reload(corner_math)

args = mcp_args or {}
LABEL = "TLPROBE_Spline"
START_MATCH_TOL_CM = 2.0   # recovered start vertex vs. footprint vertex


def actor():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    return next((a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL), None)


def footprint(a):
    sc = a.get_component_by_class(unreal.SplineComponent)
    return [tuple(sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD).to_tuple()[:2])
            for i in range(sc.get_number_of_spline_points())]


def read_rows(comp):
    """All generated points' relevant attributes plus world transform (needed
    to recover each row's segment start vertex)."""
    coll = comp.get_generated_graph_output()
    rows = []
    MA = unreal.PCGMetadataAccessorHelpers
    for td in coll.get_editor_property("tagged_data"):
        # Measured (Task 7): get_generated_graph_output()'s tagged_data wraps
        # its data in a PCGDataPtrWrapper, not the real PCGData -- one more
        # get_editor_property("data") unwraps it. The unwrapped
        # PCGPointArrayData has no get_points()/const_metadata(); go through
        # to_point_data() (deprecated but still the only Python-reachable
        # conversion) to reach a PCGPointData with both.
        wrapper = td.get_editor_property("data")
        d = wrapper.get_editor_property("data") if hasattr(wrapper, "get_editor_property") else wrapper
        if not isinstance(d, unreal.PCGBasePointData):
            continue
        pd = d if hasattr(d, "get_points") else d.to_point_data()
        md = pd.mutable_metadata() if hasattr(pd, "mutable_metadata") else pd.const_metadata()
        for pt in pd.get_points():
            t = pt.get_editor_property("transform")
            fwd = t.rotation.rotator().get_forward_vector()
            seglen = MA.get_double_attribute(pt, md, "SegLen")
            pos = t.translation
            rows.append({
                "lv": MA.get_integer32_attribute(pt, md, "LevelNumber"),
                "len": round(seglen, 2),
                "g": MA.get_string_attribute(pt, md, "FloorGrammar"),
                "scale": round(MA.get_double_attribute(pt, md, "ShortScale"), 4),
                "prev": round(MA.get_double_attribute(pt, md, "PreviousAngle"), 3),
                "pos_z": round(float(pos.z), 2),
                "start_xy": (round(float(pos.x) - float(fwd.x) * seglen / 2.0, 1),
                             round(float(pos.y) - float(fwd.y) * seglen / 2.0, 1)),
            })
    return rows


def match_edge_index(pts, xy, tol=START_MATCH_TOL_CM):
    for i, p in enumerate(pts):
        if ((xy[0] - p[0]) ** 2 + (xy[1] - p[1]) ** 2) ** 0.5 < tol:
            return i
    return None


def main():
    a = actor()
    if a is None:
        return {"error": "no %s actor; run tl_spline_level.py first" % LABEL}
    comp = a.get_component_by_class(unreal.PCGComponent)
    if args.get("phase") == "gen":
        comp.set_graph(unreal.EditorAssetLibrary.load_asset("/Game/PCG/TL/PCG_TL_SplineBuilding"))
        unreal.SystemLibrary.execute_console_command(None, "pcg.FlushCache")
        comp.activate(True)
        comp.cleanup_local(True)
        comp.generate_local(True)
        return {"fired": True}

    rows = read_rows(comp)
    pts = corner_math.clean(footprint(a))
    n_edges = len(pts)

    R = {"n_rows": len(rows), "sample": rows[:6]}

    # (2) levels present + non-empty
    levels_present = sorted({r["lv"] for r in rows})
    R["levels_present"] = levels_present
    R["levels_ok"] = (levels_present == [0, 1, 2, 3, 4]) and len(rows) > 0

    # (3) per-level multiplicity: rows == n_edges * distinct-Z-count, with the
    # repeat count read from the data (not assumed).
    storey_repeats = {}
    for lv in levels_present:
        zs = {r["pos_z"] for r in rows if r["lv"] == lv}
        storey_repeats[lv] = len(zs)
    R["storey_repeats"] = storey_repeats
    multiplicity = []
    multiplicity_ok = True
    for lv in levels_present:
        actual = sum(1 for r in rows if r["lv"] == lv)
        expected = n_edges * storey_repeats[lv]
        ok = actual == expected
        multiplicity_ok = multiplicity_ok and ok
        multiplicity.append({"lv": lv, "expected_rows": expected, "actual_rows": actual, "ok": ok})
    R["multiplicity"] = multiplicity
    R["multiplicity_ok"] = multiplicity_ok

    # (4) per-edge comparison via recovered start vertex, not multiset
    # membership by (level, length, grammar) alone.
    unmatched = []
    got_edges = set()
    for r in rows:
        i = match_edge_index(pts, r["start_xy"])
        if i is None:
            unmatched.append(r)
            continue
        got_edges.add((r["lv"], i, r["len"], r["g"]))
    R["unmatched_starts"] = unmatched[:20]
    R["n_unmatched_starts"] = len(unmatched)

    want_edges = set()
    for lv in levels_present:
        for i in range(n_edges):
            plan = corner_math.edge_plan(pts, i, lv)
            g = plan["grammar"] or "[%s]" % plan["symbol"]
            want_edges.add((lv, i, round(plan["length"], 2), g))

    missing = sorted(want_edges - got_edges)
    unexpected = sorted(got_edges - want_edges)
    R["n_want_edges"] = len(want_edges)
    R["n_got_edges"] = len(got_edges)
    R["missing"] = missing[:20]
    R["unexpected"] = unexpected[:20]

    R["ok"] = (R["levels_ok"] and R["multiplicity_ok"] and not missing and not unexpected
              and not unmatched)
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
