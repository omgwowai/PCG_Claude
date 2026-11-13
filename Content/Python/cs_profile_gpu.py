# cs_profile_gpu.py -- ProfileGPU captures for the cloud director's measurements (spec §8). The level viewport must be
# visible and realtime; each table lands in the log a frame or two after the command.
#   {}                                   one capture now; returns the editor log's line count before it, so that
#                                        Tools/cs_sky/parse_profilegpu.py --from-line <from_line> parses this run
#   {"n": 4, "settle": 240, "gap": 60, "view": [[x, y, z], [pitch, yaw, roll]], "label": "static"}
#                                        steady-state captures (Task 8 ruling: single frames vary +-4 ms, and a parameter
#                                        change makes the cloud shadow map dearer for a while): optionally moves the level
#                                        viewport, waits `settle` ticks, then captures every `gap` ticks; deferred, result
#                                        in Saved/Reports/cs_cloud_motion/gpu_captures.json for
#                                        Tools/cs_weather/perf_summary.py --captures
import json
import os

import unreal

LOG = os.path.abspath(os.path.join(unreal.Paths.project_log_dir(), "PCG_Claude.log"))
OUT = os.path.abspath(os.path.join(unreal.Paths.project_saved_dir(), "Reports", "cs_cloud_motion", "gpu_captures.json"))


def _lines():
    unreal.SystemLibrary.execute_console_command(None, "FLUSHLOG")
    with open(LOG, "rb") as f:
        return f.read().count(b"\n")


def _world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def _save(st):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)


def _steady(args):
    n, settle, gap = int(args.get("n", 4)), int(args.get("settle", 240)), int(args.get("gap", 60))
    if args.get("view"):
        loc, rot = args["view"]
        unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(
            unreal.Vector(*loc), unreal.Rotator(roll=rot[2], pitch=rot[0], yaw=rot[1]))
    st = {"state": "running", "label": args.get("label"), "log": LOG, "caps": []}
    handle, tick_n = {}, {"k": 0}

    def tick(_dt):
        tick_n["k"] += 1
        k = tick_n["k"] - settle
        if k > 0 and k % gap == 0:
            st["caps"].append({"from_line": _lines()})
            unreal.SystemLibrary.execute_console_command(_world(), "ProfileGPU")
            if len(st["caps"]) >= n:
                unreal.unregister_slate_post_tick_callback(handle["h"])
                st["state"] = "done"
            _save(st)

    _save(st)
    handle["h"] = unreal.register_slate_post_tick_callback(tick)
    return {"deferred": OUT, "n": n, "settle": settle, "gap": gap}


def _main(args):
    if int(args.get("n", 1)) > 1 or int(args.get("settle", 0)) > 0 or args.get("view"):
        return _steady(args)
    start = _lines()
    unreal.SystemLibrary.execute_console_command(_world(), "ProfileGPU")
    return {"from_line": start, "log": LOG}


mcp_result = _main(globals().get("mcp_args") or {})
