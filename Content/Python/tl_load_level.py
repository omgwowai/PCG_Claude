# tl_load_level.py -- load a level by path (default: the CitySample PCG demo).
# Never saves anything. Run on its own call; generation and reads go in later calls.
#
# Every run_unreal_script call shares one globals() dict. A UObject left there by
# an earlier script pins the current world, and the level switch then aborts in
# CheckForWorldGCLeaks(), so those globals are dropped first.
import gc
import json


def _holds_uobject(val):
    if isinstance(val, (unreal.Object, unreal.StructBase)):
        return True
    if isinstance(val, (list, tuple, set)):
        return any(_holds_uobject(v) for v in val)
    if isinstance(val, dict):
        return any(_holds_uobject(v) for v in val.values())
    return False


def purge_uobject_globals():
    dropped = []
    for name, val in list(globals().items()):
        if name.startswith("__") or callable(val) or isinstance(val, type):
            continue
        try:
            if _holds_uobject(val):
                del globals()[name]
                dropped.append(name)
        except Exception:
            continue
    gc.collect()
    return dropped


def main(level):
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    R = {"requested": level, "purged_globals": purge_uobject_globals()}
    R["loaded"] = les.load_level(level)
    w = unreal.EditorLevelLibrary.get_editor_world()
    R["world"] = w.get_path_name() if w else None
    return R


mcp_result = json.loads(json.dumps(
    main((mcp_args or {}).get("level", "/CitySamplePCG/Levels/L_CitySamplePCG_Demo")),
    default=str))
