# tl_save_tl_level.py -- save the current level, but only if it is
# /Game/Map/Lvl_TL_Building (never the demo level or any shipped level).
import json


def main():
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    path = w.get_path_name() if w else None
    if not path or not path.startswith("/Game/Map/Lvl_TL_Building."):
        return {"saved": False, "reason": "current world is %s" % path}
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    return {"saved": bool(les.save_current_level()), "world": path}


mcp_result = json.loads(json.dumps(main(), default=str))
