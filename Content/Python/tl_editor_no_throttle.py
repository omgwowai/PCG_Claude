# tl_editor_no_throttle.py -- stop the editor throttling when its window is
# not in the foreground, so queued high-res screenshots get rendered. This is
# the per-user editor preference UEditorPerformanceSettings
# .bThrottleCPUWhenNotForeground; the class is not exposed to Python under its
# own name, so it is reached through its CDO via find_object.
# Args: {"throttle": false}
import json

args = mcp_args or {}


def main():
    cdo = unreal.find_object(None, "/Script/UnrealEd.Default__EditorPerformanceSettings")
    if cdo is None:
        return {"error": "EditorPerformanceSettings CDO not found"}
    # bitfield UPROPERTYs are not reachable by snake_case name; try the
    # spellings the Python reflection layer might use, then the console route.
    names = [n for n in dir(cdo) if "throttl" in n.lower() or "background" in n.lower()]
    out = {"candidates": names}
    for nm in ("b_throttle_cpu_when_not_foreground", "throttle_cpu_when_not_foreground",
               "bThrottleCPUWhenNotForeground", "use_less_cpu_when_in_background"):
        try:
            out["before"] = cdo.get_editor_property(nm)
            cdo.set_editor_property(nm, bool(args.get("throttle", False)))
            out["after"] = cdo.get_editor_property(nm)
            out["name"] = nm
            break
        except Exception as e:
            out.setdefault("tried", []).append("%s: %s" % (nm, str(e)[:80]))
    return out


mcp_result = json.loads(json.dumps(main(), default=str))
