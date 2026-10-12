# tl_spline_shot.py -- A7 captures in /Game/Map/Lvl_TL_Spline (the spline
# building test level). Same body as tl_showcase_shot.py with the label filter
# removed: every test building stays visible. Points the viewport and queues
# ONE high-res screenshot; the file lands later in
# Saved/Screenshots/WindowsEditor (wait with Saved/wait_shot.sh). One capture
# per bridge call; names must be unique per editor session.
#
# Args: {"name": str, "cam": [x,y,z], "look": [x,y,z], "w": px, "h": px}
import json
import math

args = mcp_args or {}
LEVEL = "/Game/Map/Lvl_TL_Spline."


def main():
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not w.get_path_name().startswith(LEVEL):
        return {"error": "current world is %s" % w.get_path_name()}
    cam = unreal.Vector(*args["cam"])
    look = unreal.Vector(*args["look"])
    d = look - cam
    yaw = math.degrees(math.atan2(d.y, d.x))
    pitch = math.degrees(math.atan2(d.z, math.hypot(d.x, d.y)))
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    ues.set_level_viewport_camera_info(cam, unreal.Rotator(pitch=pitch, yaw=yaw, roll=0.0))
    les.editor_invalidate_viewports()
    t = unreal.AutomationLibrary.take_high_res_screenshot(
        int(args.get("w", 1600)), int(args.get("h", 900)), args["name"], None, False, False,
        force_game_view=True)
    return {"fired": args["name"], "valid": bool(t and t.is_valid_task()),
            "cam": list(args["cam"]), "look": list(args["look"])}


mcp_result = json.loads(json.dumps(main(), default=str))
