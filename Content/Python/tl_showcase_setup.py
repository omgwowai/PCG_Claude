# tl_showcase_setup.py -- populate /Game/Map/Lvl_TL_Showcase: a paved ground
# plane and one PCGVolume running /Game/PCG/TL/PCG_TL_Building_BDF (the final
# TL building: BDF route with foundation, facade props and roof). Fires
# generation; read results in a separate call. Only acts in Lvl_TL_Showcase.
# Args: {"base_h": cm, "second_h": cm, "ground_mat": path, "ground_scale": float}
import json

args = mcp_args or {}
LABEL = "TL_Showcase_Building"
GRAPH = "/Game/PCG/TL/PCG_TL_Building_BDF"


def main():
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not w.get_path_name().startswith("/Game/Map/Lvl_TL_Showcase."):
        return {"error": "current world is %s" % w.get_path_name()}
    EAL = unreal.EditorAssetLibrary
    H = unreal.PCGGraphParametersHelpers
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    R = {}
    actors = {a.get_actor_label(): a for a in eas.get_all_level_actors()}

    floor = actors.get("Floor")
    if floor is not None:
        s = float(args.get("ground_scale", 24.0))
        floor.set_actor_scale3d(unreal.Vector(s, s, 1.0))
        mat = EAL.load_asset(args.get("ground_mat", "/Game/Road/Material/MI/MI_Sidewalk_Plaza_A"))
        if mat is not None:
            floor.static_mesh_component.set_material(0, mat)
        R["floor"] = {"scale": s, "material": mat.get_path_name() if mat else None}

    vol = actors.get(LABEL)
    if vol is None:
        vol = eas.spawn_actor_from_class(unreal.PCGVolume, unreal.Vector(0, 0, 0))
        vol.set_actor_label(LABEL)
        R["created_volume"] = True
    vol.set_actor_location(unreal.Vector(0, 0, 0), False, False)
    vol.set_actor_scale3d(unreal.Vector(80.0, 80.0, 80.0))
    # the volume's own wireframe would show up in the documentation shots
    brush = vol.get_component_by_class(unreal.BrushComponent)
    if brush is not None:
        brush.set_visibility(False)
    comp = vol.get_component_by_class(unreal.PCGComponent)
    comp.set_graph(EAL.load_asset(GRAPH))
    gi = comp.get_editor_property("graph_instance")
    for name in ("BaseLayerHeight", "SecondLayerHeight"):
        key = {"BaseLayerHeight": "base_h", "SecondLayerHeight": "second_h"}[name]
        if key in args:
            H.set_double_parameter(gi, name, float(args[key]))
    R["params"] = {n: H.get_double_parameter(gi, n) for n in
                   ("BaseLayerHeight", "SecondLayerHeight", "WingAWidth", "WingALength",
                    "WingBWidth", "WingBLength")}
    # PCG caches subgraph results keyed on settings, not on the content of the
    # data assets they load, so an edited BDF_WithTL is not picked up until the
    # cache is flushed.
    unreal.SystemLibrary.execute_console_command(None, "pcg.FlushCache")
    comp.cleanup_local(True)
    comp.activate(True)
    comp.generate_local(True)
    R["graph"] = comp.get_graph().get_path_name()
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
