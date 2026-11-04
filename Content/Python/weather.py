import gc
import json
import os
import sys
import time

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
for _p in (_PY, os.path.join(_REPO, "Tools", "weather")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
# The bridge keeps sys.modules between calls; drop weather_assets, weather_ref and the other weather_* modules so edits
# to them take effect.
for _m in [m for m in sys.modules if m.startswith("weather_")]:
    del sys.modules[_m]

# weather.py -- the seasonal weather system in the editor (docs/superpowers/specs/2026-11-02-seasonal-weather-design.md,
# plan docs/superpowers/plans/2026-11-02-seasonal-weather-m0.md), one phase per call:
#   assets                        generate the plugin assets under /SeasonalWeather (weather_assets.py): MPC_Weather,
#                                 T_WeatherStars + M_WeatherStars, the 12 look data assets and the two StateTrees; saved
#                                 only when both StateTrees compile. Always deferred (ALWAYS_DEFER)
#   lab {"force": bool}           the lab level /Game/Weather/L_WeatherLab (weather_lab.py): opens it, or creates it with
#                                 new_level, or with force rebuilds its WeatherLab actors, and saves what it built.
#                                 Refuses while a big level is open (traps.md 79/83), and before a level switch while a
#                                 map has unsaved changes. Always deferred (ALWAYS_DEFER)
#   set {...}                     any of SET_KEYS, applied in that order: season and day (day 0 by default; a day alone
#                                 keeps the season), hour, type with blend (default true), time_scale, paused,
#                                 run_in_editor, override (FWeatherOverride fields in snake_case, merged onto the
#                                 current override); then apply_now(). Returns record()
#   advance {"hours": h}          the clock h game hours on, then apply_now(). Returns record()
#   state                         record(): the subsystem's state JSON plus the actors block, the sky actors' values
#                                 read back through the domain's references
#   shot {"camera": c, "tag": t}  move the viewport to the lab camera WeatherCam_<c> (c defaults to overview), then fire
#                                 Saved/Screenshots/WindowsEditor/weather_<c>_<t>.png in game view, without the editor
#                                 icons, SHOT_DELAY_S later; the engine restores the view state after the capture. One
#                                 per call; the write is asynchronous, so judge it from disk on a later call. Until the
#                                 capture is processed (about SHOT_DELAY_S, at most SHOT_TIMEOUT_S), SHOT_PENDING names
#                                 it and set, advance, scenario and shot refuse (FENCED): wait about 10 s after a shot
#   scenario {"name": n}          run the steps of Tools/weather/scenarios.json's scenario n (set / advance / record),
#                                 check the records against thresholds.json (weather_ref.scenario.run_checks) and write
#                                 the records and results to Saved/Reports/weather/<n>.json. Returns {"name", "passed",
#                                 "failed", "report"}
# Every phase but assets and lab (ANY_MAP) refuses unless the lab is the current map.
# {"defer": true} runs the phase on the next editor tick and writes its result to Saved/Reports/weather/deferred.json;
# read that file on a later call.
REPORTS = os.path.join(_REPO, "Saved", "Reports", "weather")

SET_KEYS = ("season", "day", "hour", "type", "blend", "time_scale", "paused", "run_in_editor", "override")
# FWeatherOverride's Python field names -> their names in the state JSON's "override" block (weather_params.json
# override_defaults), from which set reads the current override it merges onto.
OVERRIDE_FIELDS = {"precip_mm_per_hour": "precip_mm_h", "snow_fraction": "snow_fraction",
                   "temperature_c": "temperature_c", "humidity": "humidity", "wind_direction_deg": "wind_dir_deg",
                   "wind_speed_mps": "wind_speed_m_s", "thunder_potential": "thunder_potential",
                   "cloud_cover": "cloud_cover"}
ACTOR_KEYS = ("sun_lux", "sun_pitch", "moon_lux", "sky_light", "fog_density", "white_temp", "saturation")
CAMERA_PREFIX = "WeatherCam_"   # the lab's camera actors (weather_lab.LAYOUT)
# Seconds of game-view frames before a shot's capture: the first frame after the switch to game view comes out
# under-exposed with an unsettled band (measured on the overcast shot); 5 s were enough there, and the night adapts
# furthest.
SHOT_DELAY_S = 8.0
# A fired shot's marker {"file", "started"}: written when the shot is fired, removed once its capture is processed.
# Module state does not survive a bridge call (the weather_* modules are dropped, and every script shares __main__), so
# the fence lives on disk. A marker older than SHOT_TIMEOUT_S is stale: ignored and replaced.
SHOT_PENDING = os.path.join(REPORTS, "shot_pending.json")
SHOT_TIMEOUT_S = 60.0
FENCED = {"set", "advance", "scenario", "shot"}   # phases that would change what a pending shot photographs


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True, default=str)


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _weather():
    """(the editor world's weather subsystem or None, the editor world)."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    return unreal.WeatherBlueprintLibrary.get_weather_subsystem(world), world


NO_WEATHER = {"abort": "the editor world has no weather subsystem (is the SeasonalWeather plugin loaded?); nothing was "
                       "changed"}


def _actors(world):
    """The actors block of a record: the sky actors' values, read back through the references of the level's weather
    domain (never by label); None where the domain or a reference is missing."""
    out = dict.fromkeys(ACTOR_KEYS)
    domains = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.WeatherDomain)
    if not domains:
        return out
    ref = domains[0].get_editor_property   # the first in actor-iterator order, the one the subsystem drives
    sun, moon, sky, fog, post = (ref(p) for p in ("sun", "moon", "sky_light", "height_fog", "post_process"))
    if sun:
        out["sun_lux"] = sun.get_editor_property("light_component").get_editor_property("intensity")
        out["sun_pitch"] = sun.get_actor_rotation().pitch
    if moon:
        out["moon_lux"] = moon.get_editor_property("light_component").get_editor_property("intensity")
    if sky:
        out["sky_light"] = sky.get_editor_property("light_component").get_editor_property("intensity")
    if fog:
        out["fog_density"] = fog.get_editor_property("component").get_editor_property("fog_density")
    if post:
        settings = post.get_editor_property("settings")
        out["white_temp"] = settings.get_editor_property("white_temp")
        out["saturation"] = settings.get_editor_property("color_saturation").x
    return out


def record(sub, world):
    """The subsystem's state JSON, parsed, plus the actors block."""
    rec = json.loads(sub.get_state_json())
    rec["actors"] = _actors(world)
    return rec


def _set_problems(args):
    """Why `args` is not a valid set ([] when it is), so that a bad set changes nothing. `phase` and `defer` are the
    driver's own keys."""
    from weather_ref.params import SEASONS, WEATHER_TYPES
    allowed = SET_KEYS + ("phase", "defer")
    out = ["unknown key %r (keys: %s)" % (k, ", ".join(SET_KEYS)) for k in args if k not in allowed]
    for key, names in (("season", SEASONS), ("type", WEATHER_TYPES)):
        if key in args and args[key] not in names:
            out.append("%s %r is not one of %s" % (key, args[key], ", ".join(names)))
    if "blend" in args and "type" not in args:
        out.append("blend goes with type")
    out += ["%s %r is not a number" % (k, args[k]) for k in ("day", "hour", "time_scale")
            if k in args and not _number(args[k])]
    out += ["%s %r is not true or false" % (k, args[k]) for k in ("blend", "paused", "run_in_editor")
            if k in args and not isinstance(args[k], bool)]
    override = args.get("override", {})
    if not isinstance(override, dict):
        return out + ["override %r is not an object of override fields" % (override,)]
    for k, v in override.items():
        if k not in OVERRIDE_FIELDS:
            out.append("override field %r is unknown (fields: %s)" % (k, ", ".join(OVERRIDE_FIELDS)))
        elif not _number(v):
            out.append("override %s %r is not a number" % (k, v))
    return out


def _apply_set(sub, args):
    """The keys of a valid set in SET_KEYS order, then apply_now()."""
    from weather_assets import enum_member
    if "season" in args or "day" in args:
        season = args.get("season") or json.loads(sub.get_state_json())["calendar"]["season"]
        sub.set_season(getattr(unreal.WeatherSeason, enum_member(season)), int(args.get("day", 0)))
    if "hour" in args:
        sub.set_time_of_day(float(args["hour"]))
    if "type" in args:
        sub.set_weather_type(getattr(unreal.WeatherType, enum_member(args["type"])), args.get("blend", True))
    if "time_scale" in args:
        sub.set_time_scale(float(args["time_scale"]))
    if "paused" in args:
        sub.set_paused(args["paused"])
    if "run_in_editor" in args:
        sub.set_run_in_editor(args["run_in_editor"])
    if "override" in args:
        current = json.loads(sub.get_state_json())["override"]
        override = unreal.WeatherOverride()
        for field, key in OVERRIDE_FIELDS.items():
            override.set_editor_property(field, float(args["override"].get(field, current[key])))
        sub.set_override(override)
    sub.apply_now()


def _apply_advance(sub, hours):
    sub.advance_game_time(float(hours))
    sub.apply_now()


def phase_assets(args):
    import weather_assets
    return weather_assets.run(_REPO)


def phase_lab(args):
    import weather_lab
    return weather_lab.build(force=bool(args.get("force")))


def phase_set(args):
    problems = _set_problems(args)
    if problems:
        return {"abort": "set: %s; nothing was changed" % "; ".join(problems)}
    sub, world = _weather()
    if sub is None:
        return NO_WEATHER
    _apply_set(sub, args)
    return record(sub, world)


def phase_advance(args):
    if not _number(args.get("hours")):
        return {"abort": "advance needs hours, a number of game hours; nothing was changed"}
    sub, world = _weather()
    if sub is None:
        return NO_WEATHER
    _apply_advance(sub, args["hours"])
    return record(sub, world)


def phase_state(args):
    sub, world = _weather()
    if sub is None:
        return NO_WEATHER
    return record(sub, world)


def _pending_shot():
    """(file name, seconds since it was fired) of a shot whose capture is still pending, or None when there is none or
    its marker is stale (SHOT_TIMEOUT_S) or unreadable."""
    try:
        with open(SHOT_PENDING, encoding="utf-8") as fh:
            marker = json.load(fh)
        age = time.time() - float(marker["started"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return (marker.get("file"), age) if 0.0 <= age < SHOT_TIMEOUT_S else None


def _hold_until_captured(task, claimed):
    """Write the pending marker and keep the capture task alive until the engine has processed its screenshot, or
    SHOT_TIMEOUT_S has passed; then drop the marker. The engine guards the UAutomationEditorTask only inside the C++
    call, and a task collected before its capture restores the editor view early (FScreenshotTakenState's destructor),
    so this self-unregistering Slate post-tick callback (the _defer pattern) holds the Python reference meanwhile. It
    uses only names bound here: other bridge scripts share __main__ and may rebind module globals while it waits."""
    started, path, timeout = time.time(), SHOT_PENDING, SHOT_TIMEOUT_S
    clock, load, remove = time.time, json.load, os.remove
    unregister = unreal.unregister_slate_post_tick_callback
    _save(path, {"file": claimed, "started": started})
    handle = {}

    def tick(_dt):
        try:
            if not task.is_task_done() and clock() - started < timeout:
                return
        except Exception:
            pass                          # a task that cannot answer is finished with
        h = handle.pop("h", None)
        if h is not None:
            unregister(h)
        try:
            with open(path, encoding="utf-8") as fh:
                ours = load(fh).get("started") == started   # a later shot may have replaced a stale marker
            if ours:
                remove(path)
        except (OSError, ValueError, AttributeError):
            pass
    handle["h"] = unreal.register_slate_post_tick_callback(tick)


def _fire_in_game_view(name, les):
    """One 1600 x 900 capture like pcg_sa_shots.fire, under a name from its ledger, but in game view so that the editor
    icons are hidden (Controller Ruling 32). With force_game_view the engine switches the viewport to game view only
    when it is not in it, captures SHOT_DELAY_S later, and switches it back once the screenshot is processed
    (AutomationBlueprintFunctionLibrary.cpp, FScreenshotTakenState::UnlockViewport), so the view state is restored after
    the capture. A valid task is held until then (_hold_until_captured)."""
    sys.modules.pop("pcg_sa_shots", None)
    import pcg_sa_shots
    game_view_before = bool(les.editor_get_game_view())
    les.editor_invalidate_viewports()
    claimed = pcg_sa_shots.claim_name(name)
    task = unreal.AutomationLibrary.take_high_res_screenshot(1600, 900, claimed, None, False, False,
                                                             delay=SHOT_DELAY_S, force_game_view=True)
    valid = bool(task and task.is_valid_task())
    if valid:
        _hold_until_captured(task, claimed)
    return {"requested": name, "claimed": claimed, "varied": claimed != name, "fired": claimed, "valid": valid,
            "game_view_before": game_view_before, "delay_s": SHOT_DELAY_S, "pending": SHOT_PENDING if valid else None}


def phase_shot(args):
    camera, tag = str(args.get("camera", "overview")), args.get("tag")
    if not tag:
        return {"abort": "shot needs a tag: the picture is weather_<camera>_<tag>.png; nothing was fired"}
    label = CAMERA_PREFIX + camera
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    cameras = {str(a.get_actor_label()): a for a in eas.get_all_level_actors() if isinstance(a, unreal.CameraActor)}
    if label not in cameras:   # found by label: a camera is not part of the domain
        return {"abort": "no camera %s (cameras: %s); nothing was fired" % (label, ", ".join(sorted(cameras)))}
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    cam = cameras[label]
    les.set_level_viewport_camera_info(cam.get_actor_location(), cam.get_actor_rotation(),
                                       les.get_active_viewport_config_key())
    return {"fired": _fire_in_game_view("weather_%s_%s.png" % (camera, tag), les), "camera": label}


def _step_hours(value):
    """An advance step's game hours: a number, or the advance phase's arguments {"hours": h}."""
    return value.get("hours") if isinstance(value, dict) else value


def _step_problems(name, sc, thresholds):
    """Why scenario `name` (`sc`) cannot run ([] when it can): weather_ref.scenario.problems on it alone, plus its set
    and advance values."""
    from weather_ref import scenario as SC
    out = SC.problems({"scenarios": {name: sc}}, thresholds)
    for i, step in enumerate(sc.get("steps") or []):
        if isinstance(step, dict) and "set" in step:
            value = step["set"]
            out += ["%s: steps[%d] set: %s" % (name, i, p)
                    for p in (_set_problems(value) if isinstance(value, dict) else ["%r is not an object" % (value,)])]
        elif isinstance(step, dict) and "advance" in step and not _number(_step_hours(step["advance"])):
            out.append("%s: steps[%d] advance %r is not a number of game hours" % (name, i, step["advance"]))
    return out


def phase_scenario(args):
    from weather_ref import scenario as SC
    name = args.get("name")
    scenarios = SC.load_scenarios()["scenarios"]
    if name not in scenarios:
        return {"abort": "no scenario %r (scenarios: %s); nothing was changed" % (name, ", ".join(sorted(scenarios)))}
    sc, thresholds = scenarios[name], SC.load_thresholds()
    problems = _step_problems(name, sc, thresholds)
    if problems:
        return {"abort": "%s; nothing was changed" % "; ".join(problems)}
    sub, world = _weather()
    if sub is None:
        return NO_WEATHER
    records = {}
    for step in sc["steps"]:
        (key, value), = step.items()
        if key == "set":
            _apply_set(sub, value)
        elif key == "advance":
            _apply_advance(sub, _step_hours(value))
        else:
            records[value] = record(sub, world)
    out = SC.run_checks(sc["checks"], records, thresholds)
    report = os.path.join(REPORTS, "%s.json" % name)
    _save(report, {"name": name, "milestone": sc.get("milestone"), "passed": out["passed"], "failed": out["failed"],
                   "results": out["results"], "records": records})
    return {"name": name, "passed": out["passed"], "failed": out["failed"], "report": report}


PHASES = {"assets": phase_assets, "lab": phase_lab, "set": phase_set, "advance": phase_advance, "state": phase_state,
          "shot": phase_shot, "scenario": phase_scenario}
# Phases that run with any map open: assets writes plugin assets only, and lab opens or creates the lab itself, behind
# its own big-level refusal (Controller Ruling 12).
ANY_MAP = {"assets", "lab"}
# Phases that run deferred even without {"defer": true}. assets imports the star map through Interchange, whose
# synchronous wait pumps the game-thread task queue; inside the bridge's own game-thread task that trips TaskGraph's
# RecursionGuard and kills the editor (Controller Ruling 26). A Slate post-tick callback runs outside the task graph.
# lab creates or opens a level and saves it, which may pump the task queue the same way (Controller Ruling 28).
ALWAYS_DEFER = {"assets", "lab"}
DEFERRED = os.path.join(REPORTS, "deferred.json")


def _call(phase, args):
    """The phase; or its refusal when it needs the lab and the lab is not the current map, or when it would change what
    a pending shot photographs."""
    if phase not in ANY_MAP:
        from pypcg import level
        from weather_lab import LEVEL
        refused = level.require(LEVEL, "weather.py %s" % phase)
        if refused:
            return refused
    if phase in FENCED:
        pending = _pending_shot()
        if pending:
            name, age = pending
            return {"abort": "a shot is still being captured (%s, %d s ago); call again" % (name, int(age))}
    return PHASES[phase](args)


def _defer(phase, args):
    """Run a long phase on the next editor tick (a long bridge call loses its reply: traps.md 88)."""
    _save(DEFERRED, {"phase": phase, "state": "queued"})
    handle = {}

    def tick(_dt):
        unreal.unregister_slate_post_tick_callback(handle["h"])
        try:
            _save(DEFERRED, {"phase": phase, "state": "done", "result": _call(phase, args)})
        except Exception as exc:
            _save(DEFERRED, {"phase": phase, "state": "error", "error": "%s: %s" % (type(exc).__name__, str(exc)[:800])})
        gc.collect()
    handle["h"] = unreal.register_slate_post_tick_callback(tick)
    return {"deferred": phase, "result_file": DEFERRED}


def run(args):
    phase = args.get("phase")
    if phase not in PHASES:
        return {"abort": "unknown phase %r; phases: %s" % (phase, sorted(PHASES))}
    if args.get("defer") or phase in ALWAYS_DEFER:
        return _defer(phase, {k: v for k, v in args.items() if k != "defer"})
    return _call(phase, args)


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
