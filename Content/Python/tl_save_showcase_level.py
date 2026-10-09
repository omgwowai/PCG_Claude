# tl_save_showcase_level.py -- save the current level, but only if it is
# /Game/Map/Lvl_TL_Showcase. Restores visibility of everything first, so the
# saved level is never left with a documentation cutaway applied.
import json

LABEL = "TL_Showcase_Building"


def main():
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    path = w.get_path_name()
    if not path.startswith("/Game/Map/Lvl_TL_Showcase."):
        return {"saved": False, "reason": "current world is %s" % path}
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if a.get_actor_label() == LABEL:
            for c in a.get_components_by_class(unreal.PrimitiveComponent):
                if c.get_class().get_name() != "BrushComponent":
                    c.set_visibility(True, False)
        if a.get_actor_label() == "Floor":
            a.static_mesh_component.set_visibility(True, False)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    return {"saved": bool(les.save_current_level()), "world": path}


mcp_result = json.loads(json.dumps(main(), default=str))
