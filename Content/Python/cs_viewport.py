# cs_viewport.py -- drive the active level viewport for the City Sample clear-sky capture.
#   {"phase": "frame", "label": "CS_SkyCam"}   pilot the camera actor, game view + realtime on; returns viewport size
#   {"phase": "shot"}                          console `Shot`: grabs the next presented viewport frame (the live TSR /
#                                              cloud history is kept, unlike HighResShot, which re-renders one frame)
#   {"phase": "latest"}                        newest file in Saved/Screenshots/WindowsEditor
#   {"phase": "eject"}                         stop piloting, game view off
import glob
import os

import unreal


def _world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def _find(label):
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def _shots_dir():
    return os.path.abspath(os.path.join(unreal.Paths.project_saved_dir(), "Screenshots", "WindowsEditor"))


def _main(args):
    phase = args.get("phase", "frame")
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if phase == "frame":
        cam = _find(args.get("label", "CS_SkyCam"))
        if cam is None:
            return {"error": "camera not found"}
        les.pilot_level_actor(cam)
        les.editor_set_game_view(True)
        les.editor_set_viewport_realtime(True)
        size = ues.get_level_viewport_size()
        return {"piloting": les.get_pilot_level_actor().get_actor_label() if les.get_pilot_level_actor() else None,
                "game_view": les.editor_get_game_view(), "viewport": [size.x, size.y] if size else None}
    if phase == "shot":
        before = set(glob.glob(os.path.join(_shots_dir(), "*.png")))
        unreal.SystemLibrary.execute_console_command(_world(), "Shot")
        return {"requested": True, "existing": len(before)}
    if phase == "latest":
        files = sorted(glob.glob(os.path.join(_shots_dir(), "*.png")), key=os.path.getmtime)
        return {"latest": files[-1] if files else None}
    if phase == "eject":
        les.eject_pilot_level_actor()
        les.editor_set_game_view(False)
        return {"ejected": True}
    return {"abort": "unknown phase"}


mcp_result = _main(globals().get("mcp_args") or {})
