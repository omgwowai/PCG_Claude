# pcg_sa_shottest.py — discriminate why a second capture wrote nothing.
#
# Measured context: the FIRST capture of sa_stage_01_..._debug.png at 13:37 landed
# (1378514 bytes, with a matching log line). Two later captures, one of them after the
# camera fix, returned `valid: True` and wrote no file at all — no new log line, and no
# PNG anywhere under Saved/Screenshots.
#
# Three candidate causes, and this script separates them:
#   A. reusing an existing filename is refused (removed the file first, so unlikely)
#   B. captures are dead for this editor session after ~15 hours and many script calls,
#      so even a brand-new name will not land
#   C. the viewport needs the game view / realtime state, and something changed it
#
# It fires ONE capture to a name that has never existed, and reports the viewport and
# automation state alongside. The file's existence is checked by the NEXT call, because
# the write happens on a later frame.
#
# No UObject is stored at module level.

import gc
import json
import os

NAME = "sa_probe_capture_test.png"


def main():
    import unreal

    out = {}
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ses = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    out["current_level"] = str(les.get_current_level())

    # --- viewport / game view state ---
    for name, fn in (("editor_get_game_view", lambda: les.editor_get_game_view()),
                     ("get_allows_cinematic_control", lambda: les.get_allows_cinematic_control()),
                     ("get_viewport_config_keys", lambda: les.get_viewport_config_keys()),
                     ("get_active_viewport_config_key", lambda: les.get_active_viewport_config_key()),
                     ("is_in_play_in_editor", lambda: les.is_in_play_in_editor())):
        try:
            out[name] = str(fn())
        except Exception as ex:
            out[name] = "ERR %s: %s" % (type(ex).__name__, str(ex)[:100])

    # A viewport that stopped redrawing would explain a capture that reports valid and
    # writes nothing: the automation screenshot needs a rendered frame to photograph.
    # Try to nudge it back, and report whether the calls were accepted.
    try:
        out["set_viewport_realtime"] = str(les.editor_set_viewport_realtime(True))
    except Exception as ex:
        out["set_viewport_realtime"] = "ERR %s: %s" % (type(ex).__name__, str(ex)[:100])
    try:
        out["invalidate_viewports"] = str(les.editor_invalidate_viewports())
    except Exception as ex:
        out["invalidate_viewports"] = "ERR %s: %s" % (type(ex).__name__, str(ex)[:100])

    # --- automation surface ---
    AL = unreal.AutomationLibrary
    out["automation_members"] = sorted(m for m in dir(AL) if not m.startswith("_"))[:40]
    try:
        out["has_take_high_res"] = hasattr(AL, "take_high_res_screenshot")
    except Exception:
        pass

    # --- where would it write, and is that dir writable / existing? ---
    saved = unreal.Paths.project_saved_dir()
    shotdir = os.path.join(saved, "Screenshots", "WindowsEditor")
    out["shotdir"] = shotdir
    out["shotdir_exists"] = os.path.isdir(shotdir)
    out["shotdir_writable"] = os.access(shotdir, os.W_OK) if os.path.isdir(shotdir) else None
    out["shotdir_count"] = len(os.listdir(shotdir)) if os.path.isdir(shotdir) else None
    target = os.path.join(shotdir, NAME)
    out["target"] = target
    out["target_exists_before"] = os.path.exists(target)

    # --- fire ONE capture to a never-used name ---
    try:
        t = AL.take_high_res_screenshot(
            1600, 900, NAME, None, False, False, force_game_view=False)
        out["fired"] = NAME
        out["task_valid"] = str(t.is_valid_task()) if t else None
        out["task_repr"] = str(t)[:200]
    except Exception as ex:
        out["fire_err"] = "%s: %s" % (type(ex).__name__, str(ex)[:200])

    # --- does anything appear synchronously? (it should not) ---
    out["target_exists_immediately"] = os.path.exists(target)
    return out


try:
    RESULT = {"ok": True, "data": main()}
except Exception as exc:
    RESULT = {"ok": False, "error": "%s: %s" % (type(exc).__name__, str(exc)[:300])}

try:
    mcp_result = json.loads(json.dumps(RESULT, default=str))
except Exception as se:
    mcp_result = {"ok": False, "serialization_failed": str(se)[:200]}

print(json.dumps(mcp_result, ensure_ascii=False, default=str))
del RESULT
gc.collect()
