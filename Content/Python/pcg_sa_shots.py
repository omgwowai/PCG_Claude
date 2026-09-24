# Content/Python/pcg_sa_shots.py
# Capture + teardown for the small-area run. Imports the runner rather than
# copying it, so the volume/instance logic has exactly one definition.
#
# args: {"phase": "shot_debug" | "shot_geom" | "finish" | "census",
#        "stage": 1..18,
#        "max_debug_shown": 3,
#        "target_cm": 60000}
#
# TWO KINDS OF PICTURE, and why they differ:
#   debug    - isolated: only this stage's volume is visible, and only the first
#              max_debug_shown debug-cube components. This is the evidence that
#              THIS stage's flagged nodes produced data.
#   geometry - cumulative: volumes 1..stage visible with all real geometry, every
#              debug cube hidden. The difference between consecutive geometry
#              shots is what each stage added to the city.
# The 09-23 run's manual visibility toggling was the fragile part; it is the same
# primitive here, just applied with the two rules above.
#
# ONE SHOT PER CALL, ALWAYS. take_high_res_screenshot writes on a later frame, so a
# second call in the same script overwrites the first.
#
# GLOBAL DISCIPLINE: no UObject survives this script — module level holds only
# constants and functions.

import gc
import json
import os
import sys

TARGET = "/Game/PCGArea/L_SmallArea18"
SHOT_DIR = "Screenshots/WindowsEditor"
CENSUS = "Reports/sa_census.json"

# Stages whose graphs emit data rather than instanced geometry: a zero instance
# count is correct for these, not a failure. Same values as pcg_sa_run.DATA_ONLY;
# defined here too so this module does not depend on the runner's import side
# effects for a constant.
DATA_ONLY = (1, 4, 5, 6)


def ensure_import_path():
    import unreal
    cdir = unreal.Paths.project_content_dir() + "Python"
    if cdir not in sys.path:
        sys.path.insert(0, cdir)
    # The bridge execs every script in the SAME persistent __main__ namespace, so
    # sys.modules survives across calls (measured 2026-09-24 by pcg_sa_hostprobe.py,
    # which saw globals from every script so far in one dict). A plain
    # `import pcg_sa_run` therefore returns a module cached from an earlier call and
    # the capture script would silently run stale runner code after any edit to it.
    # Dropping the cached module makes the import read the current source.
    sys.modules.pop("pcg_sa_run", None)
    import pcg_sa_run
    return pcg_sa_run


def visible_set(run, eas, show_upto, hide_debug=True, only_vol=None,
                max_debug_shown=3):
    """Show exactly the components the rule asks for; return what was done."""
    shown = 0
    hidden = 0
    for v in run.all_volumes(eas):
        label = str(v.get_actor_label())
        try:
            idx = run.ORDER.index(label) + 1
        except ValueError:
            idx = 0
        keep_volume = (only_vol is not None and v == only_vol) or \
                      (only_vol is None and 0 < idx <= show_upto)
        real = [(c, n, m) for c, n, m in run.comps(v) if not m.startswith(run.DEBUG_CUBE)]
        dbg = [(c, n, m) for c, n, m in run.comps(v) if m.startswith(run.DEBUG_CUBE)]
        for c, _n, _m in real:
            try:
                c.set_visibility(keep_volume, True)
                shown += 1 if keep_volume else 0
                hidden += 0 if keep_volume else 1
            except Exception:
                pass
        dbg.sort(key=lambda e: -e[1])
        for i, (c, _n, _m) in enumerate(dbg):
            want = (keep_volume and only_vol is not None and not hide_debug
                    and i < max_debug_shown)
            try:
                c.set_visibility(want, True)
                shown += 1 if want else 0
                hidden += 0 if want else 1
            except Exception:
                pass
    return {"shown": shown, "hidden": hidden}


def fire(name):
    import unreal
    try:
        t = unreal.AutomationLibrary.take_high_res_screenshot(
            1600, 900, name, None, False, False, force_game_view=False)
        return {"fired": name, "valid": str(t.is_valid_task()) if t else None}
    except Exception as ex:
        return {"fired": name, "shot_err": "%s: %s" % (type(ex).__name__, str(ex)[:180])}


def shot_path(name):
    import unreal
    return os.path.join(unreal.Paths.project_saved_dir(), SHOT_DIR, name)


def run_order():
    return ["PCG_1_1_Terrain", "PCG_1_2_BG_Buildings", "PCG_1_3_BG_Mountains",
            "PCG_2_1_MainTower_Footprint", "PCG_2_2_CentralPark_Footprint",
            "PCG_3_1_1_Districts", "PCG_3_1_2_Roads", "PCG_3_1_3_Highways",
            "PCG_3_1_4_Lots", "PCG_3_2_1_Ground", "PCG_3_2_2_LeftOverLots",
            "PCG_3_2_3_Parkings", "PCG_3_3_1_Buildings", "PCG_3_3_2_Rooftops",
            "PCG_4_1_MainTower_Visuals", "PCG_4_2_CentralPark_Visuals",
            "PCG_5_1_CityEdge", "PCG_5_2_OuterForest"]


def update_census(stage, graph, real_n, dbg_n):
    import unreal
    p = os.path.join(unreal.Paths.project_saved_dir(), CENSUS)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    data = {}
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            data = {}
    data.setdefault("order", run_order())
    data.setdefault("real_instances", {})
    data.setdefault("debug_instances", {})
    data["real_instances"][str(stage)] = int(real_n)
    data["debug_instances"][str(stage)] = int(dbg_n)
    data["_level"] = TARGET
    data["_note"] = ("real = non-debug instanced geometry; debug = PCG debug cubes "
                     "under /PCG/DebugObjects/")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    return p


def run(phase, stage, max_debug_shown, target_cm):
    import unreal
    run_mod = ensure_import_path()
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    cur = str(les.get_current_level())
    if TARGET.split("/")[-1] not in cur:
        return {"abort": "not on %s (current: %s)" % (TARGET, cur)}

    if phase == "finish":
        out = {}
        cleared = 0
        for label in run_order():
            v = run_mod.vol_by_label(eas, label)
            if v is None:
                continue
            try:
                g = v.pcg_component.get_graph()
                for nd in g.get_editor_property("nodes"):
                    st = nd.get_settings()
                    if st is not None and st.get_editor_property("debug"):
                        st.set_editor_property("debug", False)
                        cleared += 1
            except Exception:
                continue
        out["debug_flags_cleared"] = cleared
        out["restored"] = visible_set(run_mod, eas, 18, hide_debug=True,
                                      only_vol=None)["shown"]
        # Only the derived level is saved, never a graph asset and never the demo
        # level it was copied from.
        try:
            out["saved"] = bool(les.save_current_level())
        except Exception as ex:
            out["save_err"] = "%s: %s" % (type(ex).__name__, str(ex)[:200])
        try:
            dirty = unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
            out["still_dirty_map_packages"] = sorted(str(p.get_name()) for p in dirty)
        except Exception as ex:
            out["dirty_err"] = str(ex)[:120]
        out["epic_touched"] = [p for p in out.get("still_dirty_map_packages", [])
                               if "CitySamplePCG" in p]
        return out

    if phase == "census":
        out = {"stages": {}}
        for i, label in enumerate(run_order(), start=1):
            v = run_mod.vol_by_label(eas, label)
            if v is None:
                out["stages"][str(i)] = {"graph": label, "err": "no volume"}
                continue
            real_n, dbg_n, real_c, dbg_c = run_mod.counted(v)
            gen = None
            try:
                gen = bool(v.pcg_component.get_editor_property("generated"))
            except Exception:
                pass
            out["stages"][str(i)] = {"graph": label, "generated": gen,
                                     "real_instances": real_n,
                                     "debug_instances": dbg_n,
                                     "real_components": real_c,
                                     "debug_components": dbg_c,
                                     "suspect_zero": bool(
                                         real_n == 0 and i not in DATA_ONLY)}
            update_census(i, label, real_n, dbg_n)
        return out

    if stage is None:
        return {"abort": "phase %s needs a stage" % phase}
    s = int(stage)
    label = run_order()[s - 1]
    vol = run_mod.vol_by_label(eas, label)
    if vol is None:
        return {"abort": "no volume labelled %s" % label}

    # the camera is re-applied on every capture: visibility changes do not move the
    # view, but a previous stage's camera may still be set, and a wrong camera is
    # the single easiest way to produce an unreadable frame.
    cam = run_mod.phase_apply_camera(eas, les, s, "computed", float(target_cm))

    if phase == "shot_debug":
        vis = visible_set(run_mod, eas, 0, hide_debug=False, only_vol=vol,
                          max_debug_shown=int(max_debug_shown))
        name = "sa_stage_%02d_%s_debug.png" % (s, label)
        r = fire(name)
        r.update({"stage": s, "graph": label, "kind": "debug", "vis": vis,
                  "cam": cam})
        p = shot_path(name)
        r["exists"] = os.path.exists(p)
        r["bytes"] = os.path.getsize(p) if r["exists"] else 0
        return r

    if phase == "shot_geom":
        vis = visible_set(run_mod, eas, s, hide_debug=True, only_vol=None)
        real_n, dbg_n, real_c, dbg_c = run_mod.counted(vol)
        name = "sa_stage_%02d_%s_geometry.png" % (s, label)
        r = fire(name)
        r.update({"stage": s, "graph": label, "kind": "geometry", "vis": vis,
                  "cam": cam, "real_instances": real_n, "debug_instances": dbg_n,
                  "real_components": real_c, "debug_components": dbg_c,
                  "suspect_zero": bool(real_n == 0 and s not in DATA_ONLY)})
        p = shot_path(name)
        r["exists"] = os.path.exists(p)
        r["bytes"] = os.path.getsize(p) if r["exists"] else 0
        r["census"] = update_census(s, label, real_n, dbg_n)
        return r

    return {"abort": "unknown phase %s" % phase}


# Guarded main block: the bridge runs this with __name__ == "__main__" (measured by
# pcg_sa_hostprobe.py), while an `import pcg_sa_shots` would skip it. Without the guard an
# importing script would execute a capture as a side effect. pcg_sa_run.py had exactly that
# bug and printed a stray result object into this script's stdout.
if __name__ == "__main__":
    try:
        _args = mcp_args if isinstance(mcp_args, dict) else {}
    except NameError:
        _args = {}

    try:
        RESULT = {"ok": True, "data": run(str(_args.get("phase", "census")),
                                         _args.get("stage", None),
                                         int(_args.get("max_debug_shown", 3)),
                                         float(_args.get("target_cm", 60000.0)))}
    except Exception as _exc:
        RESULT = {"ok": False, "error": "%s: %s" % (type(_exc).__name__, str(_exc)[:400])}

    try:
        mcp_result = json.loads(json.dumps(RESULT, default=str))
    except Exception as _se:
        mcp_result = {"ok": False, "serialization_failed": str(_se)[:200]}

    print(json.dumps(mcp_result, ensure_ascii=False, default=str)[:200000])
    del RESULT, _args
    gc.collect()
