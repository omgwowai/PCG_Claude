# tl_shot.py -- point the level viewport at a target and queue one screenshot.
# The file lands a minute or two later under Saved/Screenshots/WindowsEditor;
# check for it in a later call. Names must be new: the automation layer refuses
# a name it has written before, even after the file is deleted.
#
# Args: {"name": str, "cam": [x,y,z], "look": [x,y,z]}   (world cm)
import json
import math

args = mcp_args or {}


def main():
    name = args["name"]
    cam = unreal.Vector(*args["cam"])
    look = unreal.Vector(*args["look"])
    d = look - cam
    yaw = math.degrees(math.atan2(d.y, d.x))
    pitch = math.degrees(math.atan2(d.z, math.hypot(d.x, d.y)))
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    ues.set_level_viewport_camera_info(cam, unreal.Rotator(pitch=pitch, yaw=yaw, roll=0.0))
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    les.editor_invalidate_viewports()
    t = unreal.AutomationLibrary.take_high_res_screenshot(1600, 900, name, None, False, False,
                                                         force_game_view=True)
    return {"fired": name, "valid": bool(t and t.is_valid_task()),
            "dir": unreal.Paths.project_saved_dir() + "Screenshots/WindowsEditor"}


mcp_result = json.loads(json.dumps(main(), default=str))
