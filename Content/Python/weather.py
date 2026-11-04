import gc
import json
import os
import sys

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
# {"defer": true} runs the phase on the next editor tick and writes its result to Saved/Reports/weather/deferred.json;
# read that file on a later call.
REPORTS = os.path.join(_REPO, "Saved", "Reports", "weather")


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True, default=str)


def phase_assets(args):
    import weather_assets
    return weather_assets.run(_REPO)


def phase_lab(args):
    import weather_lab
    return weather_lab.build(force=bool(args.get("force")))


PHASES = {"assets": phase_assets, "lab": phase_lab}
# Phases that run deferred even without {"defer": true}. assets imports the star map through Interchange, whose
# synchronous wait pumps the game-thread task queue; inside the bridge's own game-thread task that trips TaskGraph's
# RecursionGuard and kills the editor (Controller Ruling 26). A Slate post-tick callback runs outside the task graph.
# lab creates or opens a level and saves it, which may pump the task queue the same way (Controller Ruling 28).
ALWAYS_DEFER = {"assets", "lab"}
DEFERRED = os.path.join(REPORTS, "deferred.json")


def _defer(phase, args):
    """Run a long phase on the next editor tick (a long bridge call loses its reply: traps.md 88)."""
    _save(DEFERRED, {"phase": phase, "state": "queued"})
    handle = {}

    def tick(_dt):
        unreal.unregister_slate_post_tick_callback(handle["h"])
        try:
            _save(DEFERRED, {"phase": phase, "state": "done", "result": PHASES[phase](args)})
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
    return PHASES[phase](args)


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
