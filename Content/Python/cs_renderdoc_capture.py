# cs_renderdoc_capture.py -- one RenderDoc capture of the active level viewport (the City Sample clear-sky view).
#   {"phase": "prepare"}  capture-friendly cvars (originals saved): no async compute so every pass sits in order on the
#                         graphics queue, no callstacks, Lumen on software tracing (keeps DXR BLAS/TLAS out of the
#                         capture); call `capture` after the viewport has had a few seconds to reconverge
#   {"phase": "capture"}  runs `renderdoc.CaptureFrame` on the next Slate tick (the call draws the viewport once inside
#                         Begin/EndFrameCapture and writes Saved/RenderDocCaptures/*.rdc); result in
#                         Saved/Reports/cs_weather/capture_result.json
#   {"phase": "restore"}  puts the cvars back
import glob
import json
import os
import time

import unreal

REPORT_DIR = os.path.abspath(os.path.join(unreal.Paths.project_saved_dir(), "Reports", "cs_weather"))
STATE = os.path.join(REPORT_DIR, "capture_cvars.json")
RESULT = os.path.join(REPORT_DIR, "capture_result.json")
CAPTURES = os.path.abspath(os.path.join(unreal.Paths.project_saved_dir(), "RenderDocCaptures"))
CVARS = {
    "r.RDG.AsyncCompute": 0,
    "renderdoc.CaptureCallstacks": 0,
    "renderdoc.CaptureAllActivity": 0,
    "r.Lumen.HardwareRayTracing": 0,
    "r.RDG.Events": 3,
}


def _world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def _get(n):
    return unreal.SystemLibrary.get_console_variable_float_value(n)


def _set(n, v):
    unreal.SystemLibrary.execute_console_command(_world(), "%s %s" % (n, v))


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)


def _rdcs():
    return sorted(glob.glob(os.path.join(CAPTURES, "**", "*.rdc"), recursive=True))


def _main(args):
    phase = args.get("phase")
    if phase == "prepare":
        if not os.path.exists(STATE):
            _save(STATE, {n: _get(n) for n in CVARS})
        for n, v in CVARS.items():
            _set(n, v)
        return {"set": {n: _get(n) for n in CVARS}}
    if phase == "capture":
        before = _rdcs()
        _save(RESULT, {"state": "queued", "before": before})
        handle = {}

        def tick(_dt):
            unreal.unregister_slate_post_tick_callback(handle["h"])
            t0 = time.time()
            try:
                unreal.SystemLibrary.execute_console_command(_world(), "renderdoc.CaptureFrame")
                _save(RESULT, {"state": "fired", "seconds": round(time.time() - t0, 2), "before": before,
                               "after": _rdcs(), "time": time.strftime("%Y-%m-%d %H:%M:%S")})
            except Exception as exc:
                _save(RESULT, {"state": "error", "error": str(exc)[:500]})

        handle["h"] = unreal.register_slate_post_tick_callback(tick)
        return {"queued": True, "result_file": RESULT, "captures_dir": CAPTURES}
    if phase == "restore":
        if not os.path.exists(STATE):
            return {"abort": "nothing to restore"}
        with open(STATE, encoding="utf-8") as f:
            old = json.load(f)
        for n, v in old.items():
            _set(n, int(v) if float(v).is_integer() else v)
        os.remove(STATE)
        return {"restored": old}
    return {"abort": "unknown phase"}


mcp_result = _main(globals().get("mcp_args") or {})
