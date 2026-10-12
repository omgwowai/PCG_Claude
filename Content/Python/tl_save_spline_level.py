# tl_save_spline_level.py -- save the current level, but only if it is
# /Game/Map/Lvl_TL_Spline and it holds no TLPROBE_* actor (probe actors are
# scratch: a saved level must never contain one).
# docs/superpowers/plans/2026-10-12-tl-spline-building.md Task 11, Step 5.
import json

LEVEL = "/Game/Map/Lvl_TL_Spline."
PROBE_PREFIX = "TLPROBE_"


def main():
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    path = w.get_path_name()
    if not path.startswith(LEVEL):
        return {"saved": False, "reason": "current world is %s" % path}
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    labels = sorted(a.get_actor_label() for a in eas.get_all_level_actors())
    probes = [n for n in labels if n.startswith(PROBE_PREFIX)]
    if probes:
        return {"saved": False, "reason": "probe actors still in the level", "probes": probes}
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    return {"saved": bool(les.save_current_level()), "world": path, "actors": labels}


mcp_result = json.loads(json.dumps(main(), default=str))
