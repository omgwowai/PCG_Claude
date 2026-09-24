# pcg_sa_capprobe.py — read-only. Hunt for a SYNCHRONOUS screen-capture path.
#
# Why: `AutomationLibrary.take_high_res_screenshot` returns an AutomationEditorTask that
# never completes in this session. Nine attempts, two landings, and the mechanism is still
# unmeasured: the two landings happened under different conditions, realtime has been set
# on and off, filenames have been spent and fresh, and the pending-task ids (`_3`, `_6`,
# `_7`) keep incrementing. Chasing the async path further is guesswork.
#
# traps.md #12 records a `CaptureViewport` that returns base64 and needs a complete
# annotations object — a CitySample-side tool, so it may not exist here. This probe checks
# every plausible synchronous alternative in the editor's `unreal` module directly, and
# reports the full member list of anything that looks capable, so a working call can be
# written from measured signatures rather than memory.
#
# It captures nothing and mutates nothing.

import gc
import json


def main():
    import unreal

    out = {}

    # 1. anything in the module whose NAME suggests screenshot/preview capture
    names = dir(unreal)
    out["module_names_with_capture"] = sorted(
        n for n in names
        if any(k in n.lower() for k in ("capture", "screenshot", "thumbnail", "preview")))
    out["module_names_with_render"] = sorted(
        n for n in names if "render" in n.lower() and "target" in n.lower())

    # 2. members of the classes we already know about
    for cls_name in ("AutomationLibrary", "SystemLibrary", "KismetRenderingLibrary",
                     "RenderTargetLibrary", "EditorAssetLibrary", "LevelEditorSubsystem",
                     "EditorActorSubsystem", "EditorLevelLibrary",
                     "EditorScreenshotUtils", "ThumbnailTools", "EditorLoadingAndSavingUtils"):
        cls = getattr(unreal, cls_name, None)
        if cls is None:
            out["has_" + cls_name] = False
            continue
        try:
            mem = [m for m in dir(cls) if not m.startswith("_")]
        except Exception as ex:
            out["members_" + cls_name] = "ERR " + str(ex)[:80]
            continue
        hits = [m for m in mem
                if any(k in m.lower() for k in ("capture", "screenshot", "thumbnail",
                                                "render_target", "draw", "export"))]
        out["members_" + cls_name] = {"count": len(mem), "hits": hits}

    # 3. scan every class in the module for a member literally named like a capture call.
    #    Cheap enough at this size, and it is how a synchronous path would be found.
    found = {}
    scanned = 0
    for n in names:
        cls = getattr(unreal, n, None)
        if not isinstance(cls, type):
            continue
        nm = getattr(cls, "__name__", "")
        if not nm or not nm[0].isupper():
            continue
        scanned += 1
        try:
            mem = dir(cls)
        except Exception:
            continue
        hits = [m for m in mem
                if m.lower() in ("capture_viewport", "capture_viewport_base64",
                                 "capture_screenshot", "take_screenshot",
                                 "take_high_res_screenshot", "screenshot",
                                 "render_thumbnail", "get_render_target")]
        if hits:
            found[n] = hits
    out["classes_scanned"] = scanned
    out["classes_with_capture_members"] = found

    # 4. signatures for anything promising, so a call can be written from fact
    sigs = {}
    for cls_name, meths in found.items():
        cls = getattr(unreal, cls_name, None)
        for m in meths:
            try:
                sigs["%s.%s" % (cls_name, m)] = str(getattr(cls, m).__doc__)[:400]
            except Exception as ex:
                sigs["%s.%s" % (cls_name, m)] = "ERR " + str(ex)[:80]
    out["signatures"] = sigs

    # 5. is the render thread actually advancing? frame counter over this call.
    for probe in ("get_frame_count", "get_time_seconds", "get_delta_time"):
        try:
            out["frame_" + probe] = str(getattr(unreal.SystemLibrary, probe)())
        except Exception as ex:
            out["frame_" + probe] = "ERR " + str(ex)[:60]
    return out


try:
    RESULT = {"ok": True, "data": main()}
except Exception as exc:
    RESULT = {"ok": False, "error": "%s: %s" % (type(exc).__name__, str(exc)[:300])}

try:
    mcp_result = json.loads(json.dumps(RESULT, default=str))
except Exception as se:
    mcp_result = {"ok": False, "serialization_failed": str(se)[:200]}

if __name__ == "__main__":
    print(json.dumps(mcp_result, ensure_ascii=False, default=str)[:60000])
del RESULT
gc.collect()
