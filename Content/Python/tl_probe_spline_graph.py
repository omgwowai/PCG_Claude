# tl_probe_spline_graph.py -- READ-ONLY on assets. Generate (phase "gen") or read
# (phase "read") PCG_TL_SplineBuilding on the actor labelled TLPROBE_Spline in
# the current level, and compare the edge stream (segments abc) against
# Tools/tl_kit/corner_math.py. Args: {"phase": "gen" | "read"}
import json
import sys

sys.path.insert(0, "E:/PCG_Claude/Tools/tl_kit")
import importlib
import corner_math
importlib.reload(corner_math)

args = mcp_args or {}
LABEL = "TLPROBE_Spline"


def actor():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    return next((a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL), None)


def footprint(a):
    sc = a.get_component_by_class(unreal.SplineComponent)
    return [tuple(sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD).to_tuple()[:2])
            for i in range(sc.get_number_of_spline_points())]


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
        if hasattr(d, "get_points"):
            pd = d
        else:
            pd = d.to_point_data()
        md = pd.mutable_metadata() if hasattr(pd, "mutable_metadata") else pd.const_metadata()
        for pt in pd.get_points():
            rows.append({"lv": MA.get_integer32_attribute(pt, md, "LevelNumber"),
                         "len": round(MA.get_double_attribute(pt, md, "SegLen"), 2),
                         "g": MA.get_string_attribute(pt, md, "FloorGrammar"),
                         "scale": round(MA.get_double_attribute(pt, md, "ShortScale"), 4),
                         "prev": round(MA.get_double_attribute(pt, md, "PreviousAngle"), 3)})
    pts = corner_math.clean(footprint(a))
    want = sorted((lv, round(corner_math.edge_plan(pts, i, lv)["length"], 2),
                   corner_math.edge_plan(pts, i, lv)["grammar"] or "[%s]" % corner_math.edge_plan(pts, i, lv)["symbol"])
                  for lv in sorted({r["lv"] for r in rows}) for i in range(len(pts)))
    got = sorted((r["lv"], r["len"], r["g"]) for r in rows)
    bad = [w for w in want if w not in got]
    return {"n_rows": len(rows), "n_want": len(want), "mismatches": bad[:20], "sample": rows[:6]}


mcp_result = json.loads(json.dumps(main(), default=str))
