# pcg_sa_rotprobe.py — settle how to build an unreal.Rotator with a known pitch/yaw,
# and prove which construction the viewport actually honours.
#
# Why: the stage 1 capture came out as pure sky. The camera's computed pose was right on
# paper (centre (-9485.1, 6937.0, 0.0), loc (56662.6, 6937.0, 41333.7), i.e. 78000 cm out
# and 41333.7 up, which is centre + 78000*sin(32) in Z), but the earlier signature probe
# had already printed the tell:
#
#   unreal.Rotator(1.0, 2.0, 3.0) -> {pitch: 2.0, yaw: 3.0, roll: 1.0}
#
# i.e. the positional order is (roll, pitch, yaw). pcg_sa_shape/pcg_sa_run pass
# (pitch, yaw, roll), so the stage 1 camera was built as pitch=180, yaw=0: straight up.
# This script tests each candidate construction AND reads the viewport back, so the fix is
# verified against the viewport rather than against a struct repr.
#
# Read-only with respect to the level: it moves the editor viewport camera, nothing else.

import gc
import json

TARGET = "/Game/PCGArea/L_SmallArea18"


def main():
    import unreal

    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    out = {}

    cur = str(les.get_current_level())
    if TARGET.split("/")[-1] not in cur:
        return {"abort": "not on %s (current: %s)" % (TARGET, cur)}

    # Distinct values so a swap is unmistakable.
    P, Y, R = -32.0, 180.0, 0.0

    out["positional_pyr"] = str(unreal.Rotator(P, Y, R))
    try:
        out["keyword_pyr"] = str(unreal.Rotator(pitch=P, yaw=Y, roll=R))
    except Exception as ex:
        out["keyword_pyr"] = "ERR " + str(ex)[:120]
    try:
        out["keyword_rpy"] = str(unreal.Rotator(roll=R, pitch=P, yaw=Y))
    except Exception as ex:
        out["keyword_rpy"] = "ERR " + str(ex)[:120]
    try:
        r = unreal.Rotator()
        r.set_editor_property("pitch", P)
        r.set_editor_property("yaw", Y)
        r.set_editor_property("roll", R)
        out["set_editor_property"] = str(r)
    except Exception as ex:
        out["set_editor_property"] = "ERR " + str(ex)[:120]
    try:
        out["positional_rpy"] = str(unreal.Rotator(R, P, Y))
    except Exception as ex:
        out["positional_rpy"] = "ERR " + str(ex)[:120]

    # --- ground truth: what does the viewport report after each apply? ---
    loc = unreal.Vector(56662.6, 6937.0, 41333.7)
    key = les.get_active_viewport_config_key()
    truth = {}

    def apply_and_read(tag, rot):
        try:
            les.set_level_viewport_camera_info(loc, rot, key)
            got = les.get_level_viewport_camera_info()
            # get_level_viewport_camera_info returns (location, rotation) or a struct;
            # report both the raw repr and, if unpackable, the rotation only.
            try:
                _, grot = got
                truth[tag] = str(grot)
            except Exception:
                truth[tag] = str(got)
        except Exception as ex:
            truth[tag] = "ERR %s: %s" % (type(ex).__name__, str(ex)[:120])

    apply_and_read("apply_positional_PYR", unreal.Rotator(P, Y, R))
    apply_and_read("apply_set_editor_property", _mk(P, Y, R, unreal))
    out["viewport_round_trip"] = truth

    # What the FIXED construction should look like, for the report.
    out["want_pitch"] = P
    out["want_yaw"] = Y
    return out


def _mk(p, y, r, unreal):
    rot = unreal.Rotator()
    rot.set_editor_property("pitch", p)
    rot.set_editor_property("yaw", y)
    rot.set_editor_property("roll", r)
    return rot


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
