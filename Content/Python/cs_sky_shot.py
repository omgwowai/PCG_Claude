# cs_sky_shot.py -- queue one high-res screenshot of the current level through a camera actor.
# The capture lands a few frames later under Saved/Screenshots/WindowsEditor/<name>.png; check
# for the file in a later call (one capture per call: a second request supersedes the first).
#
# Args:
#   {"name": str, "camera": "<CameraActor label>"}               -- an existing camera
#   {"name": str, "loc": [x,y,z], "rot": [pitch,yaw,roll], "fov": deg}
#        -- moves (or spawns) the helper camera "CS_SkyCam" (or args["label"]) there
#   optional "res": [w, h] (default 1920x1080), "pilot": true leaves the viewport locked to it
import os
import unreal

_HELPER = "CS_SkyCam"


def _find(label):
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def _helper_camera(loc, rot, fov, aspect=None, label=_HELPER):
    cam = _find(label)
    if cam is None:
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        cam = eas.spawn_actor_from_class(unreal.CineCameraActor, unreal.Vector(*loc),
                                         unreal.Rotator(roll=rot[2], pitch=rot[0], yaw=rot[1]))
        cam.set_actor_label(label)
    cam.set_actor_location_and_rotation(unreal.Vector(*loc),
                                        unreal.Rotator(roll=rot[2], pitch=rot[0], yaw=rot[1]),
                                        False, False)
    comp = cam.get_cine_camera_component()
    fb = comp.get_editor_property("filmback")
    # aspect = width / height of the sensor; a portrait viewport wants aspect < 1 with the constraint off
    aspect = float(aspect) if aspect else 16.0 / 9.0
    fb.set_editor_property("sensor_width", 36.0)
    fb.set_editor_property("sensor_height", 36.0 / aspect)
    comp.set_editor_property("filmback", fb)
    comp.set_editor_property("constrain_aspect_ratio", False)
    # focal length for the requested horizontal FOV on a 36 mm sensor
    import math
    focal = 18.0 / math.tan(math.radians(fov) * 0.5)
    comp.set_editor_property("current_focal_length", focal)
    fs = comp.get_editor_property("focus_settings")
    fs.set_editor_property("focus_method", unreal.CameraFocusMethod.DISABLE)
    comp.set_editor_property("focus_settings", fs)
    return cam


def _main(args):
    name = args["name"]
    res = args.get("res", [1920, 1080])
    if "camera" in args:
        cam = _find(args["camera"])
        if cam is None:
            return {"error": "no camera labelled %s" % args["camera"]}
    else:
        cam = _helper_camera(args["loc"], args["rot"], float(args.get("fov", 70.0)), args.get("aspect"),
                             args.get("label", _HELPER))
    if args.get("no_shot"):
        loc, rot = cam.get_actor_location(), cam.get_actor_rotation()
        return {"camera": cam.get_actor_label(), "loc": [loc.x, loc.y, loc.z], "rot": [rot.pitch, rot.yaw, rot.roll]}
    loc, rot = cam.get_actor_location(), cam.get_actor_rotation()
    task = unreal.AutomationLibrary.take_high_res_screenshot(
        int(res[0]), int(res[1]), name, camera=cam, force_game_view=True)
    out = os.path.join(unreal.Paths.project_saved_dir(), "Screenshots", "WindowsEditor", name + ".png")
    return {"fired": name, "file": os.path.abspath(out), "valid": bool(task and task.is_valid_task()),
            "camera": cam.get_actor_label(), "loc": [loc.x, loc.y, loc.z],
            "rot": [rot.pitch, rot.yaw, rot.roll]}


mcp_result = _main(globals().get("mcp_args") or {})
