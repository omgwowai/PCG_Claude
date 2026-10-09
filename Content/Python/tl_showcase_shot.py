# tl_showcase_shot.py -- documentation captures in Lvl_TL_Showcase.
# Shows/hides the showcase building's generated components by category (and
# optionally clips storeys above a height), points the viewport and queues
# one high-res screenshot. The file lands ~1 min later in
# Saved/Screenshots/WindowsEditor. Names must be unique per editor session.
#
# Args: {"name": str, "cam": [x,y,z], "look": [x,y,z],
#        "show": ["L00","L01","L02","L03","L04","props","rooftop","roof"] (default all),
#        "max_z": cm (hide module instances whose pivot is above; optional),
#        "fov": deg, "w": px, "h": px}
import json
import math

args = mcp_args or {}
LABEL = "TL_Showcase_Building"
ALL = ["L00", "L01", "L02", "L03", "L04", "props", "rooftop", "roof"]


def category(name, path):
    if "/Game/Building/TL/" in path:
        for lv in ("L00", "L01", "L02", "L03", "L04"):
            if "_%s_" % lv in name:
                return lv
    if path.startswith("/Game/Prop/BLDG/"):
        return "props"
    return "rooftop"


def main():
    show = set(args.get("show", ALL))
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = next((a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL), None)
    if vol is None:
        return {"error": "no volume"}
    vis = {}
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None:
            continue
        cat = category(sm.get_name(), sm.get_path_name())
        on = cat in show
        c.set_visibility(on, False)
        vis[cat] = on
    for dc in vol.get_components_by_class(unreal.DynamicMeshComponent):
        dc.set_visibility("roof" in show, False)
    vis["roof"] = "roof" in show
    # the foundation hangs below the ground plane; hide the floor to show it
    floor = next((a for a in eas.get_all_level_actors() if a.get_actor_label() == "Floor"), None)
    if floor is not None:
        floor.static_mesh_component.set_visibility(not args.get("hide_floor", False), False)
    vis["floor"] = not args.get("hide_floor", False)

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
    return {"fired": args["name"], "valid": bool(t and t.is_valid_task()), "visible": vis}


mcp_result = json.loads(json.dumps(main(), default=str))
