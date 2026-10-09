# tl_place_bdf_volume.py -- add (or reuse) a PCGVolume in Lvl_TL_Building that
# runs /Game/PCG/TL/PCG_TL_Building_BDF, then fire generation. Only acts in
# Lvl_TL_Building. Read results in a separate call (generation is async).
# Args: {"loc": [x, y, z], "extent": cm}
import json

args = mcp_args or {}
LABEL = "TL_Building_BDF_Volume"
GRAPH = "/Game/PCG/TL/PCG_TL_Building_BDF"


def main():
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not w.get_path_name().startswith("/Game/Map/Lvl_TL_Building."):
        return {"error": "current world is %s" % w.get_path_name()}
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = next((a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL), None)
    loc = unreal.Vector(*args.get("loc", [0.0, 0.0, 0.0]))
    created = vol is None
    if vol is None:
        vol = eas.spawn_actor_from_class(unreal.PCGVolume, loc)
        vol.set_actor_label(LABEL)
    ext = float(args.get("extent", 8000.0))
    vol.set_actor_location(loc, False, False)
    vol.set_actor_scale3d(unreal.Vector(ext / 100.0, ext / 100.0, ext / 100.0))
    comp = vol.get_component_by_class(unreal.PCGComponent)
    comp.set_graph(unreal.EditorAssetLibrary.load_asset(GRAPH))
    comp.cleanup_local(True)
    comp.activate(True)
    comp.generate_local(True)
    return {"created": created, "loc": loc.to_tuple(), "graph": comp.get_graph().get_path_name()}


mcp_result = json.loads(json.dumps(main(), default=str))
