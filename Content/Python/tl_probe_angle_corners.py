# tl_probe_angle_corners.py -- THROWAWAY PROBE. What the BDF route does with TL at
# non-right-angle corners today. Duplicates Epic's Building_Staggered_HexagonShape
# example (60 deg turns) into /Game/PCG/TL/_Probe_Hex, restricts both Assign calls
# to TL, and runs it on a temporary PCGVolume "TLPROBE_Hex" placed away from the
# showcase building. Never saves the level. {"clear": true} deletes the actor and
# the scratch graph.
import json

args = mcp_args or {}
SRC = "/CitySamplePCG/Examples/Building/Building_Staggered_HexagonShape"
DST = "/Game/PCG/TL/_Probe_Hex"
LABEL = "TLPROBE_Hex"
ORIGIN = unreal.Vector(30000.0, 0.0, 0.0)


def _override(node, pairs):
    inst = node.get_settings().get_editor_property("subgraph_instance")
    for k, v in pairs.items():
        if isinstance(v, bool):
            unreal.PCGGraphParametersHelpers.set_bool_parameter(inst, k, v)
        else:
            unreal.PCGGraphParametersHelpers.set_string_parameter(inst, k, v)


def main():
    EAL = unreal.EditorAssetLibrary
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not w.get_path_name().startswith("/Game/Map/Lvl_TL_Showcase."):
        return {"error": "current world is %s" % w.get_path_name()}
    for a in eas.get_all_level_actors():
        if a.get_actor_label() == LABEL:
            eas.destroy_actor(a)
    if args.get("clear"):
        ok = EAL.delete_asset(DST) if EAL.does_asset_exist(DST) else True
        return {"cleared": True, "asset_deleted": ok}
    if not EAL.does_asset_exist(DST):
        EAL.duplicate_asset(SRC, DST)
    g = EAL.load_asset(DST)
    for n in g.get_editor_property("nodes"):
        if n.get_name() in ("AssignBase", "AssignSecond"):
            _override(n, {"BuildingsStyles": "TL", "Foundation": True})
        if n.get_name() == "Subgraph_0":
            inst = n.get_settings().get_editor_property("subgraph_instance")
            unreal.PCGGraphParametersHelpers.set_bool_parameter(inst, "AtWorldOrigin", False)
    EAL.save_loaded_asset(g)
    vol = eas.spawn_actor_from_class(unreal.PCGVolume, ORIGIN)
    vol.set_actor_label(LABEL)
    vol.set_actor_scale3d(unreal.Vector(80.0, 80.0, 80.0))
    brush = vol.get_component_by_class(unreal.BrushComponent)
    if brush is not None:
        brush.set_visibility(False)
    comp = vol.get_component_by_class(unreal.PCGComponent)
    comp.set_graph(g)
    unreal.SystemLibrary.execute_console_command(None, "pcg.FlushCache")
    comp.cleanup_local(True)
    comp.activate(True)
    comp.generate_local(True)
    return {"spawned": LABEL, "graph": DST}


mcp_result = json.loads(json.dumps(main(), default=str))
