# tl_make_bdf_test_graph.py -- make /Game/PCG/TL/PCG_TL_Building_BDF: a copy of
# Epic's Building_Staggered_LShape example (BDF route: LoadCitySampleData ->
# Assign_CitySampleBuildings, plus the planar roof mesh) with both Assign calls
# restricted to TL. The SGD route that Lvl_TL_Building uses never reads the
# Props group or RoofData, so this is the single-building test for the props,
# the roof and the foundation. The L shape also gives an interior corner.
# Epic's example is only read, never modified.
import json

SRC = "/CitySamplePCG/Examples/Building/Building_Staggered_LShape"
DEST_DIR = "/Game/PCG/TL"
DEST_NAME = "PCG_TL_Building_BDF"
DEST = DEST_DIR + "/" + DEST_NAME
ASSIGN = "Assign_CitySampleBuildings"


def main():
    EAL = unreal.EditorAssetLibrary
    H = unreal.PCGGraphParametersHelpers
    R = {"errors": []}
    if not EAL.does_directory_exist(DEST_DIR):
        EAL.make_directory(DEST_DIR)
    g = EAL.load_asset(DEST) if EAL.does_asset_exist(DEST) else EAL.duplicate_asset(SRC, DEST)
    if g is None:
        return {"errors": ["could not create %s" % DEST]}
    done = []
    shapes = []
    for n in g.get_editor_property("nodes"):
        s = n.get_settings()
        if s is None or "Subgraph" not in s.get_class().get_name():
            continue
        inst = s.get_editor_property("subgraph_instance")
        sg = inst.get_editor_property("graph") if inst else None
        if sg is not None and sg.get_path_name().endswith("Create_Spline_Shape"):
            # Epic's example builds at the world origin; build at the volume.
            H.set_bool_parameter(inst, "AtWorldOrigin", False)
            shapes.append(n.get_name())
            continue
        if sg is None or not sg.get_path_name().endswith(ASSIGN):
            continue
        H.set_string_parameter(inst, "BuildingsStyles", "TL")
        H.set_bool_parameter(inst, "Foundation", True)
        done.append({"node": n.get_name(),
                     "styles": H.get_string_parameter(inst, "BuildingsStyles"),
                     "foundation": H.get_bool_parameter(inst, "Foundation")})
    R["assign_calls"] = done
    R["shape_nodes_local"] = shapes
    if len(done) != 2:
        R["errors"].append("expected 2 Assign calls, found %d" % len(done))
    R["saved"] = EAL.save_asset(DEST, only_if_is_dirty=False)
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
