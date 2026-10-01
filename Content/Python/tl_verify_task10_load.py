# tl_verify_task10_load.py — PHASE A: load the new level, touch nothing else.
#
# Level switching has a measured trap: a UObject held in a Python global pins the
# old world and the next switch aborts inside CheckForWorldGCLeaks(). So: only
# JSON at module top level, every UObject inside a function, clear + gc first.

import gc
import json

R = {}
args = mcp_args or {}
LEVEL = args.get("level", "/Game/Map/Lvl_TL_Building")


def clear_stale():
    """Null out leftover UObject references from earlier calls, then GC."""
    g = globals()
    for k in list(g.keys()):
        if k.startswith("_") or k in ("R", "args", "LEVEL"):
            continue
        try:
            v = g[k]
        except Exception:
            continue
        if hasattr(v, "get_class") or hasattr(v, "get_path_name"):
            g[k] = None
    gc.collect()


def run():
    EAL = unreal.EditorAssetLibrary
    R["level_exists"] = EAL.does_asset_exist(LEVEL)
    if not R["level_exists"]:
        return
    clear_stale()
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    try:
        ok = les.load_level(LEVEL)
        R["load_level_ok"] = bool(ok)
    except Exception as e:
        R["load_error"] = "%s: %s" % (type(e).__name__, e)
        return
    # record which level is current, and how many actors it has
    try:
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors = eas.get_all_level_actors()
        R["actor_count"] = len(actors)
        labels = []
        for a in actors:
            try:
                lab = a.get_actor_label()
            except Exception:
                continue
            if "TL" in lab or "PCGVolume" in lab:
                labels.append(lab)
        R["notable_actors"] = sorted(labels)[:20]
    except Exception as e:
        R["actor_err"] = "%s: %s" % (type(e).__name__, e)


run()
print(json.dumps(json.loads(json.dumps(R, default=str)), indent=1))
mcp_result = json.loads(json.dumps(R, default=str))
