# Content/Python/pcg_sa_drive.py — one stage per call, terse output, late-landing aware.
#
# args: {"stage": 1..18,
#        "phase": "debug" | "geom" | "finish",
#        "verify_from": 0}      # also verify stages <= this many back
#
# WHY ONE STAGE PER CALL AND WHY THIS SCRIPT EXISTS
#
# The capture path is asynchronous with a LATENCY OF MINUTES, measured 2026-09-24:
#
#   14:12  sa_stage_01_..._debug_r3.png   landed  1,830,989 bytes
#   14:14  sa_ctl_1790230483.png          landed  1,922,728 bytes
#
# Both had been recorded as failures because their `exists` check ran in the same call
# that queued them, and the follow-up wait was only 60-90 s. So this script NEVER judges
# a capture by its own call's result: it reports what it queued, and verification of
# earlier stages happens on the NEXT call, by which time the file has had a minute or
# more to appear.
#
# TWO CALLS PER STAGE, because the two kinds of picture need different visibility and a
# capture photographs whatever visibility is current when it finally renders:
#   phase=debug : gen(stage) then isolate to this stage and show a few debug cubes
#   phase=geom  : cumulative volumes 1..stage, all debug hidden
# Running them in one call would give two identical frames.
#
# OUTPUT IS ONE LINE. Each call would otherwise return kilobytes of JSON, and there are
# ~40 calls left; the full detail is written to Saved/Reports/sa_drive_log.jsonl instead.

import gc
import json
import os
import sys

TARGET = "/Game/PCGArea/L_SmallArea18"


def _mod(name):
    import unreal
    d = unreal.Paths.project_content_dir() + "Python"
    if d not in sys.path:
        sys.path.insert(0, d)
    sys.modules.pop(name, None)          # globals persist; cached modules go stale
    return __import__(name)


def _log_line(entry):
    """Append the full detail to a jsonl so stdout can stay tiny."""
    import unreal
    p = os.path.join(unreal.Paths.project_saved_dir(), "Reports", "sa_drive_log.jsonl")
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        pass


def _verify(run, shots, eas, upto):
    """Which of stages 1..upto have both captures on disk. Read-only."""
    have = {}
    for n in range(1, upto + 1):
        label = shots.run_order()[n - 1]
        row = {}
        for kind in ("debug", "geometry"):
            p = shots.shot_path(shots.shot_name(n, label, kind))
            if not os.path.exists(p):
                p = shots.shot_path("sa_stage_%02d_%s_%s_r2.png" % (n, label, kind))
            row[kind] = os.path.getsize(p) if os.path.exists(p) else 0
        have[n] = row
    return have


def main(stage, phase, verify_from):
    import unreal
    run = _mod("pcg_sa_run")
    shots = _mod("pcg_sa_shots")
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

    cur = str(les.get_current_level())
    if TARGET.split("/")[-1] not in cur:
        return {"abort": "not on %s" % TARGET}

    entry = {"stage": stage, "phase": phase}
    # 1. a capture fired by an earlier call has had minutes to land; give it its name
    entry["promoted"] = shots.promote_variants()
    # 2. verify earlier stages by what is on disk, not by what was queued
    if verify_from:
        entry["on_disk"] = _verify(run, shots, eas, verify_from)

    if phase == "finish":
        # shots.run's stage argument is unused for finish; it clears every graph's debug
        # flag, restores visibility, and saves ONLY the derived level. It reports
        # epic_touched so a dirty CitySample package would be visible.
        entry["finish"] = shots.run("finish", 1, 3, 60000.0)
        _log_line(entry)
        return entry

    label = shots.run_order()[stage - 1]
    entry["graph"] = label

    if phase == "debug":
        # GUARD, mirroring the geom phase's: `gen` adds this stage's instanced components,
        # and new components are VISIBLE as soon as they exist, so generating stage N while
        # stage N-1's geometry frame is still pending would add stage N's geometry to that
        # picture. A capture photographs the visibility current when it RENDERS, which is
        # ~1-2 minutes after queueing (measured 2026-09-24), so this refuses to touch
        # anything until the previous stage's geometry frame is on disk. The caller retries.
        if stage > 1:
            prev_label = shots.run_order()[stage - 2]
            pname = shots.shot_name(stage - 1, prev_label, "geometry")
            if not any(os.path.exists(shots.shot_path(n))
                       for n in (pname, pname.replace(".png", "_r2.png"))):
                entry["wait"] = "previous geometry frame not on disk: %s" % pname
                _log_line(entry)
                return entry
        entry["gen"] = run.run("gen", stage, 4, "computed", 60000.0)
        vis = shots.visible_set(run, eas, 0, hide_debug=False,
                               only_vol=run.vol_by_label(eas, label), max_debug_shown=3)
        cam = run.phase_apply_camera(eas, les, stage, "computed", 60000.0)
        name = shots.shot_name(stage, label, "debug")
        entry["vis"] = vis
        entry["cam_mode"] = cam.get("mode")
        entry["fire"] = shots.fire(name, les)
    elif phase == "geom":
        # GUARD: a capture photographs the visibility that is current WHEN IT RENDERS, so
        # changing to cumulative visibility before the debug frame has rendered would make
        # both shots identical. Rather than pace this from the host with a poll per stage,
        # refuse to change anything until the debug frame is on disk; the caller retries.
        dbg_name = shots.shot_name(stage, label, "debug")
        dbg_ok = [n for n in (dbg_name, dbg_name.replace(".png", "_r2.png"))
                  if os.path.exists(shots.shot_path(n))]
        if not dbg_ok:
            entry["wait"] = "debug frame not on disk yet: %s" % dbg_name
            _log_line(entry)
            return entry
        entry["debug_frame"] = dbg_ok[0]
        vis = shots.visible_set(run, eas, stage, hide_debug=True, only_vol=None)
        cam = run.phase_apply_camera(eas, les, stage, "computed", 60000.0)
        real_n, dbg_n, real_c, dbg_c = run.counted(run.vol_by_label(eas, label))
        name = shots.shot_name(stage, label, "geometry")
        entry["vis"] = vis
        entry["cam_mode"] = cam.get("mode")
        entry["counts"] = {"real": real_n, "dbg": dbg_n,
                           "real_c": real_c, "dbg_c": dbg_c}
        entry["suspect_zero"] = bool(real_n == 0 and stage not in (1, 4, 5, 6))
        entry["fire"] = shots.fire(name, les)
        entry["census"] = shots.update_census(stage, label, real_n, dbg_n)
    else:
        return {"abort": "unknown phase %s" % phase}

    _log_line(entry)
    return entry


def summarise(e):
    """The one line this call prints."""
    if e.get("abort"):
        return "ABORT %s" % e["abort"]
    fired = (e.get("fire") or {}).get("fired")
    bits = ["stage=%s phase=%s" % (e.get("stage"), e.get("phase"))]
    if e.get("graph"):
        bits.append(e["graph"])
    if e.get("gen"):
        g = e["gen"]
        bits.append("gen[flagged=%s fired=%s]" % (g.get("flagged"), g.get("fired")))
    if e.get("counts"):
        c = e["counts"]
        bits.append("real=%s dbg=%s suspect_zero=%s"
                    % (c["real"], c["dbg"], e.get("suspect_zero")))
    if fired:
        bits.append("queued=%s" % fired)
    if e.get("wait"):
        bits.append("WAIT(%s)" % e["wait"])
    f = e.get("finish")
    if f:
        bits.append("saved=%s flags_cleared=%s epic_touched=%s"
                    % (f.get("saved"), f.get("debug_flags_cleared"),
                       f.get("epic_touched")))
    if e.get("promoted"):
        bits.append("promoted=%s" % len(e["promoted"]))
    on_disk = e.get("on_disk")
    if on_disk:
        missing = [n for n, r in sorted(on_disk.items())
                   if not (r["debug"] and r["geometry"])]
        done = len(on_disk) - len(missing)
        bits.append("on_disk=%d/%d" % (done, len(on_disk)))
        if missing:
            bits.append("missing=%s" % missing)
    return " | ".join(bits)


if __name__ == "__main__":
    try:
        _a = mcp_args if isinstance(mcp_args, dict) else {}
    except NameError:
        _a = {}
    try:
        E = {"ok": True, "data": main(int(_a.get("stage", 1)),
                                     str(_a.get("phase", "debug")),
                                     int(_a.get("verify_from", 0)))}
    except Exception as exc:
        E = {"ok": False, "error": "%s: %s" % (type(exc).__name__, str(exc)[:300])}
    print(summarise(E["data"]) if E.get("ok") else ("ERROR " + E.get("error", "")))
    try:
        mcp_result = {"ok": E.get("ok"), "line": summarise(E["data"]) if E.get("ok")
                      else E.get("error")}
    except Exception:
        mcp_result = {"ok": False}
    del E, _a
    gc.collect()
