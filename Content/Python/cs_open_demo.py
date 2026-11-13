# cs_open_demo.py -- open the City Sample demo level, from the editor's startup map only (/Game/ThirdPerson/Lvl_ThirdPerson).
# Refuses while a map package is dirty, so nothing is ever saved. From the demo or another big level, restart the editor
# instead: switching away from a big level can crash it (CLAUDE.md traps 79 / 83).
import json

import unreal

DEMO = "/CitySamplePCG/Levels/L_CitySamplePCG_Demo"
STARTUP = "/Game/ThirdPerson/Lvl_ThirdPerson"


def _world_name():
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    return w.get_path_name() if w else ""


def _main():
    name = _world_name()
    if name.startswith(DEMO + "."):
        return {"already": name}
    if not name.startswith(STARTUP + "."):
        return {"refused": "current level is %s, not the startup map: restart the editor (runbook R4)" % name}
    dirty = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    if dirty:
        return {"refused": "dirty map packages", "dirty": dirty}
    ok = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(DEMO)
    return {"loaded": bool(ok), "level": _world_name()}


mcp_result = json.loads(json.dumps(_main(), default=str))
