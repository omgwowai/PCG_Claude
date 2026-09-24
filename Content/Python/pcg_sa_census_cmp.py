# Content/Python/pcg_sa_census_cmp.py — census, compared against a baseline, in ONE line.
#
# args: {"baseline": "Tools/data/stage_census_smallarea.json",
#        "expect_debug_zero": true}
#
# WHY THIS EXISTS: the plain `census` phase returns the full per-stage JSON, which is ~4 KB
# per call. With the run's remaining calls plus a repair re-run still to come, that adds up
# in a session whose context is the scarce resource. This returns the same information as a
# single line plus a short delta list, and it answers the two questions that actually matter
# after a regeneration:
#
#   1. did any stage LOSE real content versus the baseline? (the concurrent-batch failure
#      mode: stages reading upstream data mid-rebuild)
#   2. is the level clean of debug visualisation now? (the shedding goal)
#
# GLOBAL DISCIPLINE: module level holds only constants and functions.

import gc
import json
import os
import sys

SHOT_DIR = "Screenshots/WindowsEditor"
SHOT_NAMES = "Reports/sa_shot_names.json"


def _abs(path):
    import unreal
    if os.path.isabs(path):
        return path
    return os.path.join(unreal.Paths.project_dir(), path)


def main(baseline_path, expect_debug_zero):
    import unreal
    d = unreal.Paths.project_content_dir() + "Python"
    if d not in sys.path:
        sys.path.insert(0, d)
    sys.modules.pop("pcg_sa_run", None)
    sys.modules.pop("pcg_sa_shots", None)
    import pcg_sa_run as run
    import pcg_sa_shots as shots

    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if "L_SmallArea18" not in str(les.get_current_level()):
        return {"abort": "wrong level"}

    base = {}
    bp = _abs(baseline_path)
    if os.path.exists(bp):
        with open(bp, encoding="utf-8") as fh:
            base = json.load(fh)
    base_real = {int(k): v for k, v in base.get("real_instances", {}).items()}
    base_dbg = {int(k): v for k, v in base.get("debug_instances", {}).items()}

    live, deltas, dbg_left, suspect = {}, [], [], []
    for i, label in enumerate(shots.run_order(), start=1):
        vol = run.vol_by_label(eas, label)
        if vol is None:
            suspect.append(i)
            continue
        rn, dn, rc, dc = run.counted(vol)
        live[i] = {"real": rn, "dbg": dn, "real_c": rc, "dbg_c": dc}
        if i in base_real and rn != base_real[i]:
            deltas.append([i, base_real[i], rn, rn - base_real[i]])
        if dn:
            dbg_left.append([i, dn])
        if rn == 0 and i not in (1, 4, 5, 6):
            suspect.append(i)

    return {
        "stages": len(live),
        "real_total": sum(v["real"] for v in live.values()),
        "dbg_total": sum(v["dbg"] for v in live.values()),
        "deltas_vs_baseline": deltas,
        "stages_with_debug_left": dbg_left,
        "suspect_zero": suspect,
        "expect_debug_zero": bool(expect_debug_zero),
        "debug_ok": (not dbg_left) if expect_debug_zero else True,
        "per_stage": live,
    }


if __name__ == "__main__":
    try:
        _a = mcp_args if isinstance(mcp_args, dict) else {}
    except NameError:
        _a = {}
    try:
        E = {"ok": True, "data": main(str(_a.get("baseline",
                                                 "Tools/data/stage_census_smallarea.json")),
                                      bool(_a.get("expect_debug_zero", True)))}
    except Exception as exc:
        E = {"ok": False, "error": "%s: %s" % (type(exc).__name__, str(exc)[:300])}
    if E.get("ok"):
        r = E["data"]
        if r.get("abort"):
            line = "ABORT %s" % r["abort"]
        else:
            bits = ["census stages=%s real_total=%s dbg_total=%s"
                    % (r["stages"], format(r["real_total"], ","),
                       format(r["dbg_total"], ","))]
            d = r["deltas_vs_baseline"]
            bits.append("deltas=%s" % ("none" if not d else
                                       " ".join("s%d %+d" % (x[0], x[3]) for x in d)))
            bits.append("debug_left=%s" % ("0" if not r["stages_with_debug_left"]
                                           else r["stages_with_debug_left"]))
            bits.append("suspect=%s" % (r["suspect_zero"] or "none"))
            bits.append("debug_ok=%s" % r["debug_ok"])
            line = " | ".join(bits)
    else:
        line = "ERROR " + E.get("error", "")
    print(line)
    mcp_result = {"ok": E.get("ok"), "line": line}
    del E, _a
    gc.collect()
