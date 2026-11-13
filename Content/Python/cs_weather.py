# cs_weather.py -- static weather presets for the City Sample demo level (/CitySamplePCG/Levels/L_CitySamplePCG_Demo),
# applied in memory on top of the 10:00 clear look (cs_clear_sky.py). The presets are data: cs_weather_presets.py.
#
# Phases (one per call):
#   apply   {"phase": "apply", "preset": "fog", "set": {"Section.prop": v}, "cloud": {"Param": v}, "ppv": {...},
#            "sun": [elev, azim]}      every managed property is set (preset value, else the 10:00 value, else the
#                                      level's original), so presets never leak into each other; "preset": "base" = 10:00
#   state   {"phase": "state"}         the applied preset and the current values of everything managed
#   cams    {"phase": "cams"}          spawn / move the CS_WX_* comparison cameras of cs_weather_presets.CAMERAS
#   shoot   {"phase": "shoot", "preset": "fog", "tag": "v1", "only": ["CS_SkyCam"]}
#                                      queue the preset's shots: Saved/Screenshots/WindowsEditor/wx_<preset>_<cam>_<tag>.png
#   restore {"phase": "restore", "to": "base" | "original"}
#                                      base = the 10:00 look; original = the level as it was before cs_clear_sky.py
#                                      (cs_clear_sky snapshot + this script's own snapshot), helper cameras deleted
# Presets are resolved by cs_wx_resolve.py (shared with the cloud director); BottomKm follows the cloud layer's bottom.
# The art-directed weathers (cs_weather_art.py, merged into P.PRESETS, order P.ART_ORDER) run through the same phases;
# a preset with "night_sky" gets the star dome CS_WX_NightSky (MI_CS_NightSky from cs_sky_assets.py nightsky), every
# other preset removes it. The cloud material's LayerKm always follows the component's layer height.
# Never saves the level; turns editor autosave off in memory (the demo level is Epic content, CLAUDE.md trap 78).
import gc
import importlib
import json
import os
import sys
import time

import unreal

import cs_weather_presets as P
import cs_wx_lib as lib
import cs_wx_resolve as R

importlib.reload(lib)
importlib.reload(P)
importlib.reload(R)

SNAP_CLEAR = os.path.join(lib.SAVED, "Reports", "cs_weather", "original_state.json")
SNAP_EXTRA = os.path.join(lib.REPORT_DIR, "original_extra.json")
STATE = os.path.join(lib.REPORT_DIR, "current.json")
PPV_LABEL = "CS_ClearSky_PPV"
HIDE_LABELS = ["SM_SkySphere"]
NIGHT_LABEL = "CS_WX_NightSky"
NIGHT_MI = "/Game/CitySampleSky/MI_CS_NightSky"
NIGHT_MESH = "/Engine/EngineSky/SM_SkySphere"
NIGHT_RADIUS_CM = 5.0e6                       # the dome's scale is this over the mesh's bounding-sphere radius
EXTRA_DELETE = ["CS_RayCam", "CS_WX_Map", NIGHT_LABEL, "CS_MOTION_Cam"]   # CS_MOTION_Cam: the cloud director's recording camera
SECTIONS = ["DirectionalLightComponent", "SkyAtmosphereComponent", "SkyLightComponent", "VolumetricCloudComponent",
            "ExponentialHeightFogComponent"]


def _snapshot_extras(extra_keys=()):
    """Records, before anything is changed, the original value of every managed property cs_clear_sky.py does not
    snapshot (keys already recorded are kept: a key is recorded the first time it becomes managed)."""
    snap = lib.load_json(SNAP_EXTRA, {"components": {}, "cvars": {}})
    clear = lib.load_json(SNAP_CLEAR, {"components": {}, "cvars": {}})
    changed = False
    for section, props in R.managed(extra_keys).items():
        actor, comp = lib.component(section)
        if comp is None:
            continue
        for prop in sorted(props):
            if prop in clear["components"].get(section, {}) or prop in snap["components"].get(section, {}):
                continue
            snap["components"].setdefault(section, {})[prop] = lib.enc(comp.get_editor_property(prop))
            changed = True
    for name in P.BASE_CVARS:
        if name not in clear["cvars"] and name not in snap["cvars"]:
            snap["cvars"][name] = lib.cvar_get(name)
            changed = True
    if lib.THROTTLE not in snap.setdefault("editor", {}):
        snap["editor"][lib.THROTTLE] = bool(lib.perf_cdo().get_editor_property(lib.THROTTLE))
        changed = True
    if changed:
        lib.save_json(SNAP_EXTRA, snap)
    return snap


def _ensure_mi(name):
    path = P.MI_DIR + "/" + name
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.EditorAssetLibrary.load_asset(path), False
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    mi = tools.create_asset(name, P.MI_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    unreal.MaterialEditingLibrary.set_material_instance_parent(mi, unreal.load_asset(P.MATERIAL))
    return mi, True


def _apply_cloud(mi_name, params, save=True):
    """Writes resolved cloud parameters (cs_wx_resolve: base + neutral + preset + overrides, LayerKm / BottomKm from the
    cloud layer) into the preset's material instance. save=False keeps the change in memory: a save opens a slow-task
    dialog that ticks Slate, which must not happen inside a Slate tick callback (phase_batch, the cloud director)."""
    mi, created = _ensure_mi(mi_name)
    mel = unreal.MaterialEditingLibrary
    for k, v in params.items():
        mel.set_material_instance_scalar_parameter_value(mi, k, float(v))
    mel.update_material_instance(mi)
    if save:
        unreal.EditorAssetLibrary.save_asset(P.MI_DIR + "/" + mi_name, only_if_is_dirty=False)
    return mi, created


def _night_sky(cfg, write_mi=True):
    """The star dome of the night weathers: an engine sky sphere scaled to NIGHT_RADIUS_CM with MI_CS_NightSky (unlit sky
    material: atmosphere + moon disk + star map); cfg {"StarIntensity": 2.0}. Without cfg the dome is removed: a
    sky material in the scene makes the SkyAtmosphere stop drawing its own sky pixels. write_mi=False leaves the saved
    MI_CS_NightSky asset alone (the cloud director drives the stars through its own MID and must not dirty assets)."""
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    dome = lib.find_label(NIGHT_LABEL)
    if not cfg:
        if dome is not None:
            eas.destroy_actor(dome)
            return "removed"
        return None
    mi = unreal.load_asset(NIGHT_MI)
    if mi is None:
        raise RuntimeError("%s missing: run cs_sky_assets.py {\"phase\": \"nightsky\"} first" % NIGHT_MI)
    if write_mi:
        mel = unreal.MaterialEditingLibrary
        for k, v in cfg.items():
            mel.set_material_instance_scalar_parameter_value(mi, k, float(v))
        mel.update_material_instance(mi)
    if dome is None:
        dome = eas.spawn_actor_from_object(unreal.load_asset(NIGHT_MESH), unreal.Vector(0.0, 0.0, 0.0))
        dome.set_actor_label(NIGHT_LABEL)
    smc = dome.static_mesh_component
    k = NIGHT_RADIUS_CM / smc.get_editor_property("static_mesh").get_bounds().sphere_radius
    dome.set_actor_scale3d(unreal.Vector(k, k, k))
    smc.set_collision_profile_name("NoCollision")
    smc.set_cast_shadow(False)
    smc.set_material(0, mi)
    return {"dome": NIGHT_LABEL, "scale": round(k, 2), "params": dict(cfg)}


def _apply_ppv(values):
    ppv = lib.find_label(PPV_LABEL)
    if ppv is None:
        ppv = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(
            unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
        ppv.set_actor_label(PPV_LABEL)
    ppv.set_editor_property("unbound", True)
    ppv.set_editor_property("priority", 10.0)
    s = ppv.get_editor_property("settings")
    for prop in R.managed_ppv():
        s.set_editor_property("override_" + prop, False)
    for prop, val in values.items():
        if prop == "auto_exposure_method":
            val = getattr(unreal.AutoExposureMethod, val)
        elif isinstance(val, list):
            val = unreal.Vector4(*val) if len(val) == 4 else unreal.LinearColor(*val)
        s.set_editor_property("override_" + prop, True)
        s.set_editor_property(prop, val)
    ppv.set_editor_property("settings", s)


def phase_apply(args):
    refused = lib.require_level()
    if refused:
        return refused
    if lib.shot_queue_busy():
        return {"refused": "a shot queue is running; wait for it (cs_weather_shots.py {\"status\": true})"}
    if not os.path.exists(SNAP_CLEAR):
        return {"abort": "no cs_clear_sky snapshot (%s): run cs_clear_sky.py apply once first" % SNAP_CLEAR}
    # the cloud director's tick would keep writing into what apply sets (final review): a manual apply stops a playing
    # director and refuses during a recording; the director's own applies pass by_director
    by_director = bool(args.get("by_director"))
    if not by_director and _director_recording():
        return {"refused": "the cloud director is recording; stop it first (cs_cloud_director.py {\"phase\": \"stop\"})"}
    director = None if by_director else _stop_director("apply")
    name = args.get("preset", "base")
    overrides = args.get("set") or {}
    extra = _snapshot_extras(overrides.keys())
    r = R.resolve(name, extra, {"set": overrides, "cloud": args.get("cloud"), "ppv": args.get("ppv"),
                                "sun": args.get("sun")})
    lib.autosave_cdo().set_editor_property("bAutoSaveEnable", False, unreal.PropertyAccessChangeNotifyMode.NEVER)
    # keep the viewports drawing while the editor is in the background, or queued HighResShots never fire
    lib.perf_cdo().set_editor_property(lib.THROTTLE, False, unreal.PropertyAccessChangeNotifyMode.NEVER)
    out = {"preset": name, "set": {}}
    if director:
        out["director"] = director
    with unreal.ScopedEditorTransaction("CS weather %s" % name):
        for section, vals in r["components"].items():
            actor, comp = lib.component(section)
            if comp is None:
                out["set"][section] = "missing"
                continue
            comp.modify()
            for prop in sorted(vals):
                comp.set_editor_property(prop, lib.value_for(comp, prop, vals[prop]))
            out["set"][section] = len(vals)
            if section == "DirectionalLightComponent":
                actor.set_actor_rotation(lib.sun_rotation(r["sun"][0], r["sun"][1]), False)
                out["sun"] = r["sun"]
        actor, cloud = lib.component("VolumetricCloudComponent")
        mi, created = _apply_cloud(r["mi"], r["cloud"], bool(args.get("save_mi", True)))
        cloud.set_editor_property("material", mi)
        out["cloud_mi"] = {"asset": mi.get_path_name(), "created": created, "LayerKm": r["cloud"]["LayerKm"],
                           "BottomKm": r["cloud"]["BottomKm"]}
        out["night_sky"] = _night_sky(r["night_sky"])
        _apply_ppv(r["ppv"])
        out["ppv"] = r["ppv"]
        for label in HIDE_LABELS:
            a = lib.find_label(label)
            if a is not None:
                for c in a.get_components_by_class(unreal.PrimitiveComponent):
                    c.modify()
                    c.set_visibility(False, True)
    for n_, v_ in r["cvars"].items():
        lib.cvar_set(n_, v_)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_invalidate_viewports()
    lib.save_json(STATE, {"preset": name, "overrides": {"set": overrides, "cloud": args.get("cloud"),
                                                         "ppv": args.get("ppv"), "sun": args.get("sun")}})
    return out


def phase_state(args):
    out = {"current": lib.load_json(STATE, {}), "components": {}}
    for section, props in R.managed().items():
        actor, comp = lib.component(section)
        if comp is None:
            continue
        out["components"][section] = {p_: lib.enc(comp.get_editor_property(p_)) for p_ in sorted(props)}
        if section == "DirectionalLightComponent":
            r = actor.get_actor_rotation()
            out["sun_rotation"] = [r.pitch, r.yaw, r.roll]
    actor, cloud = lib.component("VolumetricCloudComponent")
    out["cloud_material"] = cloud.get_editor_property("material").get_path_name()
    out["cvars"] = {n_: lib.cvar_get(n_) for n_ in P.BASE_CVARS}
    return out


def phase_cams(args):
    out = {}
    for label, c in P.CAMERAS.items():
        if c.get("existing"):
            out[label] = "existing" if lib.find_label(label) else "MISSING"
            continue
        rot = c.get("rot")
        if rot is None:
            pitch, yaw = lib.look_rotation(c["loc"], c["target"])
            rot = [pitch, yaw, 0.0]
        lib.helper_camera(label, c["loc"], rot, c["fov"], c["aspect"])
        out[label] = {"loc": c["loc"], "rot": [round(x, 3) for x in rot], "fov": c["fov"], "aspect": c["aspect"]}
    return out


def _short(label):
    return "hero" if label == "CS_SkyCam" else label.replace("CS_WX_", "").replace("CS_ART_", "").lower()


def phase_shoot(args):
    if _director_recording():          # UE keeps one pending HighResShot: a second request would replace the recorder's
        return {"refused": "the cloud director is recording; stop it first (cs_cloud_director.py {\"phase\": \"stop\"})"}
    name = args["preset"]
    p = R.preset(name)
    tag = args.get("tag", "v1")
    only = args.get("only")
    shots = []
    for label, _ref in p.get("shots", []) + [[c, None] for c in (args.get("extra") or [])]:
        if only and label not in only:
            continue
        shots.append({"name": "wx_%s_%s_%s" % (name, _short(label), tag), "camera": label,
                      "res": P.CAMERAS[label]["res"]})
    return lib.start_shot_queue(shots, int(args.get("settle", 30)))


def _holder_director():
    """The cloud director (cs_cloud_rt.py) held in its holder module, or None -- read without importing cs_cloud_rt, so
    restore works even if that module cannot load (final review)."""
    h = sys.modules.get("_cs_cloud_holder")
    return getattr(h, "director", None) if h is not None else None


def _director_recording():
    d = _holder_director()
    return d is not None and getattr(d, "handle", None) is not None and getattr(d, "job", None) is not None


def _stop_director(reason="restore"):
    """Stops the cloud director if one is held (ticking or not); None when there is none."""
    d = _holder_director()
    if d is None:
        return None
    try:
        return d.stop(reason=reason)
    except Exception as exc:
        return {"stop_error": "%s: %s" % (type(exc).__name__, exc)}


def phase_restore(args):
    director = _stop_director()          # its tick would keep writing into the components otherwise
    to = args.get("to", "base")
    if to == "base":
        out = phase_apply({"preset": "base"})
        out["director"] = director
        return out
    clear = lib.load_json(SNAP_CLEAR)
    extra = lib.load_json(SNAP_EXTRA, {"components": {}, "cvars": {}})
    if clear is None:
        return {"abort": "no snapshot at %s" % SNAP_CLEAR}
    out = {"restored": {}, "director": director}
    with unreal.ScopedEditorTransaction("CS weather restore"):
        for snap in (extra, clear):
            for section, props in snap["components"].items():
                actor, comp = lib.component(section)
                if comp is None:
                    continue
                comp.modify()
                for prop, val in props.items():
                    comp.set_editor_property(prop, lib.dec(val))
                out["restored"][section] = out["restored"].get(section, 0) + len(props)
        actor, _ = lib.component("DirectionalLightComponent")
        if "sun_rotation" in clear:
            actor.set_actor_rotation(lib.dec(clear["sun_rotation"]), False)
        for label, vis in clear.get("hide", {}).items():
            a = lib.find_label(label)
            if a is not None:
                for c, v in zip(a.get_components_by_class(unreal.PrimitiveComponent), vis):
                    c.modify()
                    c.set_visibility(bool(v), True)
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        labels = [PPV_LABEL, "CS_SkyCam"] + [k for k in P.CAMERAS if k != "CS_SkyCam"] + EXTRA_DELETE
        for label in labels:
            a = lib.find_label(label)
            if a is not None:
                eas.destroy_actor(a)
                out.setdefault("deleted", []).append(label)
    for snap in (clear, extra):
        for n_, v_ in snap.get("cvars", {}).items():
            lib.cvar_set(n_, int(v_) if float(v_).is_integer() else v_)
    # The values are the originals again, but the demo level's external actor packages are still dirty: turning autosave
    # back on now would write autosave copies of them (a crash-restore can put those over the real files, trap 78).
    # Clear their dirty flags first (cs_weather_reload_clean.py checks every value against the snapshots before it does).
    out["clean"] = _clean_level_packages()
    lib.autosave_cdo().set_editor_property("bAutoSaveEnable", bool(clear.get("autosave", True)),
                                           unreal.PropertyAccessChangeNotifyMode.NEVER)
    out["autosave"] = clear.get("autosave")
    throttle = bool(extra.get("editor", {}).get(lib.THROTTLE, True))
    lib.perf_cdo().set_editor_property(lib.THROTTLE, throttle, unreal.PropertyAccessChangeNotifyMode.NEVER)
    out[lib.THROTTLE] = throttle
    lib.save_json(STATE, {"preset": "original"})
    return out


def _clean_level_packages():
    import cs_weather_reload_clean as C
    importlib.reload(C)
    res = C._main({})
    return {"cleared": len(res.get("cleared", [])), "refused": res.get("refused"),
            "dirty_after": res.get("dirty_after", res.get("dirty_before"))}


def phase_run(args):
    """cams + apply + shoot in one call (the iteration loop of the tuning)."""
    cams = phase_cams(args)
    applied = phase_apply(args)
    if "abort" in applied or "refused" in applied:
        return applied
    return {"cams": len(cams), "apply": applied, "shoot": phase_shoot(args)}


BATCH = os.path.join(lib.REPORT_DIR, "batch_status.json")


def phase_batch(args):
    """Applies and shoots several presets one after another from a Slate tick (one bridge call):
    {"phase": "batch", "presets": ["base", "clear_noon", ...], "tag": "final", "extra": ["CS_SkyCam"],
     "settle": 60, "max_commit_gb": 64}.
    Progress in Saved/Reports/cs_weather2/batch_status.json, with the editor's memory after every preset. The tick is
    re-entrancy guarded and saves no assets (the material instances stay modified in memory only); the batch stops
    itself once the editor's private commit passes max_commit_gb."""
    if _director_recording():
        return {"refused": "the cloud director is recording; stop it first (cs_cloud_director.py {\"phase\": \"stop\"})"}
    if lib.shot_queue_busy():
        return {"refused": "a shot queue is running"}
    prev = lib.load_json(BATCH, {})
    if prev.get("state") == "running" and time.time() - prev.get("heartbeat", 0) < 60:
        return {"refused": "a batch is running", "status": prev}
    refused = lib.require_level()
    if refused:
        return refused
    cams = phase_cams(args)
    todo = args.get("presets") or ["base"] + P.ORDER
    todo = list(P.ART_ORDER) if todo == "art" else list(todo)
    max_commit = float(args.get("max_commit_gb", 64.0))
    st = {"state": "running", "todo": todo, "done": [], "current": None, "t0": time.time(), "errors": [],
          "heartbeat": time.time(), "mem_start": lib.process_memory_gb()}
    lib.save_json(BATCH, st)
    handle = {}
    last = {"save": 0.0}

    def stop(state, **extra):
        st["state"] = state
        st.update(extra)
        unreal.unregister_slate_post_tick_callback(handle["h"])

    def tick(_dt):
        changed = False
        try:
            if st["current"] is not None:
                ss = lib.shot_status()
                if ss.get("state") == "running":
                    return
                mem = lib.process_memory_gb()
                st["done"].append({"preset": st["current"], "shots": ss.get("done"), "errors": ss.get("errors"),
                                   "mem": mem, "t": round(time.time() - st["t0"], 1)})
                st["current"], changed = None, True
                if mem and mem["commit"] > max_commit:
                    stop("stopped", reason="editor private commit %.1f GB > %.1f GB" % (mem["commit"], max_commit))
                    return
            if not st["todo"]:
                stop("done")
            else:
                name = st["todo"].pop(0)
                st["current"], changed = name, True
                applied = phase_apply({"preset": name, "save_mi": False})
                if "abort" in applied or "refused" in applied:
                    st["errors"].append({name: applied})
                    st["current"] = None
                else:
                    extra = list(args.get("extra") or []) if name == "base" else []
                    queued = phase_shoot({"preset": name, "tag": args.get("tag", "final"), "extra": extra,
                                          "settle": int(args.get("settle", 60))})
                    if "queued" not in queued:
                        st["errors"].append({name: queued})
                        st["current"] = None
        except Exception as exc:
            stop("error", error="%s: %s" % (type(exc).__name__, exc))
            changed = True
        finally:
            now = time.time()
            if changed or now - last["save"] > 2.0:
                st["heartbeat"], last["save"] = now, now
                lib.save_json(BATCH, st)

    handle["h"] = unreal.register_slate_post_tick_callback(lib.guarded(tick))
    return {"batch": todo, "cams": cams, "status_file": BATCH, "mem": st["mem_start"]}


def phase_prefs(args):
    """{"phase": "prefs", "throttle": false} sets Editor Preferences > Performance > Use Less CPU when in Background in
    memory (not saved); without "throttle" it only reports the current value."""
    cdo = lib.perf_cdo()
    if "throttle" in args:
        cdo.set_editor_property(lib.THROTTLE, bool(args["throttle"]), unreal.PropertyAccessChangeNotifyMode.NEVER)
    return {lib.THROTTLE: bool(cdo.get_editor_property(lib.THROTTLE)), "mem": lib.process_memory_gb()}


PHASES = {"apply": phase_apply, "state": phase_state, "cams": phase_cams, "shoot": phase_shoot,
          "restore": phase_restore, "run": phase_run, "batch": phase_batch, "prefs": phase_prefs}


def _main(args):
    phase = args.get("phase", "state")
    if phase not in PHASES:
        return {"abort": "unknown phase %r" % phase}
    return json.loads(json.dumps(PHASES[phase](args), default=str))


if "mcp_args" in globals() or __name__ == "__main__":     # run by the bridge; cs_cloud_rt.py imports this module
    mcp_result = _main(globals().get("mcp_args") or {})
    gc.collect()
