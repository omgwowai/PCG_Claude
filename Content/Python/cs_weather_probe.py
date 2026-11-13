# Read-only probe: list the sky / light / fog / cloud / post-process / camera actors of the
# current level and dump the editor properties of their atmosphere-related components.
# args: {"classes": [...optional component class names...], "max_props": 400}
import unreal

_COMPONENT_CLASSES = [
    "DirectionalLightComponent", "SkyAtmosphereComponent", "SkyLightComponent",
    "VolumetricCloudComponent", "ExponentialHeightFogComponent", "LocalFogVolumeComponent",
    "PostProcessComponent",
]


def _jsonable(v):
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v[:16]]
    if isinstance(v, unreal.Object):
        try:
            return v.get_path_name()
        except Exception:
            return str(v)
    return str(v)


def _dump(obj, limit):
    out = {}
    for name in dir(obj):
        if name.startswith("_") or len(out) >= limit:
            continue
        try:
            val = obj.get_editor_property(name)
        except Exception:
            continue
        if callable(val):
            continue
        out[name] = _jsonable(val)
    return out


def _run(args):
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = eas.get_all_level_actors()
    wanted = args.get("classes") or _COMPONENT_CLASSES
    limit = int(args.get("max_props", 400))
    found = []
    cams = []
    for a in actors:
        cls = a.get_class().get_name()
        if "CameraActor" in cls:
            loc, rot = a.get_actor_location(), a.get_actor_rotation()
            cams.append({"label": a.get_actor_label(), "class": cls,
                         "loc": [round(loc.x), round(loc.y), round(loc.z)],
                         "rot": [round(rot.pitch, 2), round(rot.yaw, 2), round(rot.roll, 2)]})
        comps = []
        for cname in wanted:
            ucls = getattr(unreal, cname, None)
            if ucls is None:
                continue
            for c in a.get_components_by_class(ucls):
                comps.append({"component": c.get_name(), "class": cname,
                              "props": _dump(c, limit) if args.get("props", True) else {}})
        if comps:
            loc, rot = a.get_actor_location(), a.get_actor_rotation()
            found.append({"label": a.get_actor_label(), "class": cls, "path": a.get_path_name(),
                          "hidden_ed": a.is_temporarily_hidden_in_editor(),
                          "loc": [round(loc.x), round(loc.y), round(loc.z)],
                          "rot": [round(rot.pitch, 3), round(rot.yaw, 3), round(rot.roll, 3)],
                          "components": comps})
    return {"world": world.get_path_name(), "actor_count": len(actors), "sky_actors": found,
            "cameras": cams}


def _main(args):
    res = _run(args)
    out = args.get("out")
    if out:
        import json, os
        path = os.path.join(unreal.Paths.project_saved_dir(), out)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)
        return {"written": os.path.abspath(path), "actors": [a["label"] for a in res["sky_actors"]]}
    return res


mcp_result = _main(globals().get("mcp_args") or {})
