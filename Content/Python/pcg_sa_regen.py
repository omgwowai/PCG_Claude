# Content/Python/pcg_sa_regen.py — shed every stage's debug cubes, in ONE call.
#
# args: {"debug_nodes": 0}   # 0 = clear flags and generate nothing flagged
#
# WHY THIS EXISTS
#
# `finish` cleared all 60 debug flags, but clearing a flag does not delete geometry that was
# already generated: each flagged node owns an InstancedStaticMeshComponent full of
# /PCG/DebugObjects/PCG_Cube, and those components survive until their graph is regenerated.
# So the first save captured the cubes: 507 MB across 194 external actors, largest single
# file 288 MB. Two problems with that:
#
#   1. GitHub refuses any single file over 100 MB, so the level could not be committed as the
#      user asked ("关卡与外部 Actor 都入库").
#   2. A deliverable area should not be mostly debug visualisation. The debug evidence lives
#      in the 36 captures, which are already on disk; the level itself should be the clean
#      region.
#
# Regenerating each stage with debug_nodes=0 does both: `phase_gen` clears every flag on the
# graph first, so the debug components go, and then generates the stage's real geometry again.
# One call rather than 18 because `generate_local` returns immediately and the work proceeds
# on worker threads; the caller then waits and verifies.
#
# GLOBAL DISCIPLINE: no UObject survives this script — module level holds only constants.

import gc
import json
import sys

TARGET = "/Game/PCGArea/L_SmallArea18"


def main():
    import unreal
    d = unreal.Paths.project_content_dir() + "Python"
    if d not in sys.path:
        sys.path.insert(0, d)
    sys.modules.pop("pcg_sa_run", None)
    import pcg_sa_run as run

    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    cur = str(les.get_current_level())
    if TARGET.split("/")[-1] not in cur:
        return {"abort": "not on %s (current: %s)" % (TARGET, cur)}

    fired, failed = [], []
    for n in range(1, 19):
        try:
            info = run.run("gen", n, 0, "computed", 60000.0)
            if info.get("fired"):
                fired.append({"stage": n, "graph": info.get("graph"),
                              "cleared": info.get("cleared_flags"),
                              "flagged": info.get("flagged")})
            else:
                failed.append({"stage": n, "info": info})
        except Exception as ex:
            failed.append({"stage": n, "error": "%s: %s" % (type(ex).__name__,
                                                           str(ex)[:160])})
    return {"fired": len(fired), "failed": failed, "stages": fired}


if __name__ == "__main__":
    try:
        _a = mcp_args if isinstance(mcp_args, dict) else {}
    except NameError:
        _a = {}
    try:
        E = {"ok": True, "data": main()}
    except Exception as exc:
        E = {"ok": False, "error": "%s: %s" % (type(exc).__name__, str(exc)[:300])}
    if E.get("ok"):
        d = E["data"]
        if d.get("abort"):
            line = "ABORT %s" % d["abort"]
        else:
            ns = [s["cleared"] for s in d.get("stages", [])]
            line = ("regen fired=%s failed=%s | flags_cleared_total=%s"
                    % (d.get("fired"), len(d.get("failed") or []), sum(ns)))
    else:
        line = "ERROR " + E.get("error", "")
    print(line)
    mcp_result = {"ok": E.get("ok"), "line": line}
    del E, _a
    gc.collect()
