# cs_wx_status.py -- READ-ONLY health check before / during the weather batch: current level, editor memory, the
# render cvars the weather look depends on, the helper actors, and the batch / shot status files.
import importlib
import time

import unreal

import cs_wx_lib as lib

importlib.reload(lib)

CVARS = ["r.Lumen.HardwareRayTracing", "r.RDG.AsyncCompute", "r.VolumetricRenderTarget.Mode", "r.HighResScreenshotDelay",
         "r.ScreenPercentage", "r.Nanite.Foliage"]


def _main():
    w = lib.world()
    out = {"world": w.get_path_name() if w else None, "mem": lib.process_memory_gb(),
           "cvars": {n: lib.cvar_get(n) for n in CVARS}}
    labels = ["CS_SkyCam", "CS_ClearSky_PPV", "SM_SkySphere"]
    found = {a.get_actor_label(): True for a in lib.actors() if a.get_actor_label() in labels or
             a.get_actor_label().startswith("CS_WX_")}
    out["actors"] = sorted(found)
    out["n_actors"] = len(lib.actors())
    for name, path in (("batch", lib.os.path.join(lib.REPORT_DIR, "batch_status.json")), ("shots", lib.SHOT_STATUS)):
        st = lib.load_json(path, {})
        out[name] = {k: st.get(k) for k in ("state", "current", "todo", "done", "errors", "error", "reason", "queue")
                     if k in st}
        if "heartbeat" in st:
            out[name]["age_s"] = round(time.time() - st["heartbeat"], 1)
    return out


mcp_result = _main()
