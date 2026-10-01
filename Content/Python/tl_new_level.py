# Content/Python/tl_new_level.py
# Task 10, Steps 1+2: create a NEW level (template-copied from the CitySample
# demo level) and generate a TL building in it via the SGD route proven by
# Task 6 (tl_verify_sgd.py).
#
# Run tl_new_level_read.py as a SEPARATE call afterwards: generation is async,
# so reading get_generated_graph_output() / ISM instances in this same call
# would see an empty/stale state with no error (same discipline as every other
# PCG script in this project).
#
# --- Why the demo level is the template, not a blank level (hard constraint 1,
#     measured and documented in task-10-brief.md): the demo level's terrain is
#     a /Script/MeshPartition.MeshPartition actor that later pipeline stages
#     project onto; a blank level has none and produces nothing, silently. We
#     follow this literally even though the SGD harness graph used below does
#     NOT itself need terrain (Bldg_SGD_level, its native home, has zero
#     MeshPartition actors and still produces full facades -- see tl_verify_sgd.py)
#     -- the brief's hard constraint is unconditional, and deviating from an
#     explicit hard constraint on the acceptance task is not worth the risk.
#
# --- Why SGD, not BDF (route decision, see the task-10 report for the full
#     writeup): BDF (Assign_CitySampleBuildings fed by LoadCitySampleData) is
#     the brief's literal first choice, but it is UNPROVEN standalone in a
#     fresh level -- it is normally driven by the full 18-stage pipeline's
#     district/lot data, which a bare new level does not have. SGD_TL_A via the
#     Assign_ShapeGrammarDefinition mechanism is the route Task 6 already
#     proved end-to-end (162 TL instances across 10 distinct mesh paths, exact
#     floor-to-floor deltas). Reproducing that proven mechanism in a new level
#     is a stronger bet for the acceptance task than a first-ever standalone
#     BDF attempt. This script follows that preference.
#
# --- How a pre-configured PCGVolume gets from Bldg_SGD_level into a level
#     templated off the DEMO level (they are different assets, and you cannot
#     have two unrelated "current" levels open for editing at once):
#     EditorLevelUtils.add_level_to_world() can stream ANY level package in as
#     a sublevel of the current world without replacing it. Measured in this
#     session: after add_level_to_world(), the engine auto-switches "current
#     level for new actors" to the newly streamed sublevel -- but
#     EditorLevelLibrary.set_current_level_by_name() can switch it straight
#     back to the persistent (target) level. EditorActorSubsystem.duplicate_actor()
#     places its duplicate in whichever level is CURRENT at the moment of the
#     call (confirmed: duplicating PCGVolume_SGD_CHA while current="Bldg_SGD_level"
#     put the duplicate in Bldg_SGD_level; switching current back to the target
#     level first put the duplicate in the TARGET level instead, as desired).
#     The sublevel is then removed again (remove_level_from_world) -- the
#     graph asset itself (PCG_Bldg_SGD_test) is a content asset independent of
#     the level, so the duplicate keeps working with Bldg_SGD_level unloaded.
#
# --- Placement: the probe volume is placed at (0, 0, 50000) -- 500 m straight
#     up, deliberately floating clear of whatever terrain/buildings the demo
#     level template already carries at ground level. The SGD harness graph
#     synthesizes its own closed footprint spline in-graph (CreateSplineShape_Footprint,
#     from Width/Length graph parameters) and does not read or need ground
#     contact -- proven by Bldg_SGD_level having zero terrain actors at all.
#     Floating avoids any risk of colliding with or being confused for the
#     demo level's own city content; a screenshot (secondary evidence) will
#     show an isolated building, which is expected, not a defect.
#
# GLOBAL DISCIPLINE: no UObject may survive this script. Everything lives
# inside functions; module level holds only JSON/constants. See pcg_sa_level.py
# for the same pattern and why purge_uobject_globals() runs first.

import gc
import json
import re

TEMPLATE = "/CitySamplePCG/Levels/L_CitySamplePCG_Demo"
TARGET = "/Game/Map/Lvl_TL_Building"
SGD_LEVEL = "/CitySamplePCG/PCG/DataAssets/Buildings/Bldg_SGD_level"
SOURCE_LABEL = "PCGVolume_SGD_CHA"
VOLUME_LABEL = "TL_Building_Volume"
SGD_TL_PATH = "/Game/PCG/DataAssets/Buildings/TL/SGD_TL_A"
SPAWN_LOC = (0.0, 0.0, 50000.0)


def _holds_uobject(val, ue):
    """True if val is, or contains, an unreal wrapper that could pin a world."""
    if isinstance(val, (ue.Object, ue.StructBase)):
        return True
    if isinstance(val, (list, tuple, set)):
        return any(_holds_uobject(v, ue) for v in val)
    if isinstance(val, dict):
        return any(_holds_uobject(v, ue) for v in val.values())
    return False


def purge_uobject_globals():
    """Drop anything left in the module globals that could pin a world."""
    import unreal
    dropped = []
    for name, val in list(globals().items()):
        if name.startswith("__") or callable(val) or isinstance(val, type):
            continue
        try:
            if _holds_uobject(val, unreal):
                del globals()[name]
                dropped.append(name)
        except Exception:
            continue
    gc.collect()
    return dropped


def level_inventory(eas, ue):
    """Actor/PCGVolume/spline counts for whatever is current -- used to report
    what the template copy brought over, before anything else is touched."""
    actors = eas.get_all_level_actors()
    pcg_count = 0
    spline_count = 0
    meshpartition_count = 0
    for a in actors:
        cn = a.get_class().get_name()
        if cn == "PCGVolume":
            pcg_count += 1
        if "MeshPartition" in cn:
            meshpartition_count += 1
        if a.get_components_by_class(ue.SplineComponent):
            spline_count += 1
    return {"actor_count": len(actors), "pcgvolume_count": pcg_count,
            "spline_actor_count": spline_count,
            "meshpartition_actor_count": meshpartition_count}


def fatal(R, msg, ue, eas, dup_actor=None):
    """Report a fatal condition and, if a probe actor was already duplicated
    into the target level, destroy it so a failed run leaves no residue."""
    R["fatal"] = msg
    if dup_actor is not None:
        try:
            c2 = dup_actor.get_component_by_class(ue.PCGComponent)
            if c2:
                try:
                    c2.cleanup_local(True)
                except Exception:
                    pass
            eas.destroy_actor(dup_actor)
            R["fatal_cleanup"] = "orphan probe actor destroyed"
        except Exception as e:
            R["fatal_cleanup"] = "FAILED to destroy orphan probe actor: %s: %s" % (
                type(e).__name__, e)
    return R


def create_or_reuse_level(R, les, ael):
    """Step 1: template-copy the demo level, or reuse it if it already exists."""
    if ael.does_asset_exist(TARGET):
        R["level_creation"] = "reused_existing"
        import unreal
        unreal.EditorLevelLibrary.load_level(TARGET)
        return True

    ok = False
    attempts = []
    try:
        ok = bool(les.new_level_from_template(TARGET, TEMPLATE))
        attempts.append({"path": "new_level_from_template", "ok": ok})
    except Exception as ex:
        attempts.append({"path": "new_level_from_template",
                         "error": "%s: %s" % (type(ex).__name__, str(ex)[:200])})
    if not ok:
        try:
            import unreal
            world = unreal.EditorLoadingAndSavingUtils.new_map_from_template(TEMPLATE, False)
            saved = bool(unreal.EditorLoadingAndSavingUtils.save_map(world, TARGET)) if world else False
            attempts.append({"path": "new_map_from_template+save_map", "ok": saved})
            ok = saved
        except Exception as ex:
            attempts.append({"path": "new_map_from_template+save_map",
                             "error": "%s: %s" % (type(ex).__name__, str(ex)[:200])})
    R["level_creation"] = "freshly_created" if ok else "FAILED"
    R["level_creation_attempts"] = attempts
    return ok


def run():
    import unreal
    R = {}
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ael = unreal.EditorAssetLibrary

    R["current_before"] = str(les.get_current_level())

    if not create_or_reuse_level(R, les, ael):
        R["gate"] = {"pass": False, "reason": "level creation failed"}
        return R

    R["current_after_create"] = str(les.get_current_level())
    R["on_target"] = TARGET.split("/")[-1] in R["current_after_create"]

    # Step 1 report: what the template copy brought over, BEFORE touching
    # anything else (Bldg_SGD_level is not streamed in yet).
    R["template_inventory"] = level_inventory(eas, unreal)

    # idempotency guard: if a previous run already created and generated our
    # volume, do not duplicate a second one -- reconfigure/regenerate the one
    # that is already there.
    existing = None
    for a in eas.get_all_level_actors():
        try:
            if a.get_actor_label() == VOLUME_LABEL:
                existing = a
                break
        except Exception:
            continue

    if existing is not None:
        R["volume_source"] = "reused_existing_probe_actor"
        dup = existing
    else:
        # ---------- stream in Bldg_SGD_level long enough to duplicate its
        # pre-configured PCGVolume_SGD_CHA (see header for why this is the
        # only Python-reachable way to get the override bookkeeping) --------
        streaming = None
        try:
            world = unreal.EditorLevelLibrary.get_editor_world()
            streaming = unreal.EditorLevelUtils.add_level_to_world(
                world, SGD_LEVEL, unreal.LevelStreamingAlwaysLoaded)
            R["sgd_level_streamed"] = streaming is not None
        except Exception as ex:
            R["sgd_level_stream_err"] = "%s: %s" % (type(ex).__name__, ex)
            return fatal(R, "could not stream in Bldg_SGD_level", unreal, eas)

        if streaming is None:
            return fatal(R, "add_level_to_world returned None for Bldg_SGD_level",
                        unreal, eas)

        # switch current-level-for-new-actors back to the TARGET persistent
        # level before duplicating, so the duplicate lands there, not in the
        # sublevel (measured in this session's exploration -- see header).
        persistent_name = TARGET.split("/")[-1]
        try:
            unreal.EditorLevelLibrary.set_current_level_by_name(persistent_name)
        except Exception as ex:
            R["set_current_level_err"] = "%s: %s" % (type(ex).__name__, ex)
        R["current_before_duplicate"] = str(les.get_current_level())

        source = None
        for a in eas.get_all_level_actors():
            try:
                if a.get_actor_label() == SOURCE_LABEL:
                    source = a
                    break
            except Exception:
                continue

        if source is None:
            try:
                unreal.EditorLevelUtils.remove_level_from_world(streaming.get_loaded_level())
            except Exception:
                pass
            return fatal(R, "source volume not found: %s" % SOURCE_LABEL, unreal, eas)

        dup = eas.duplicate_actor(source, offset=unreal.Vector(0.0, 0.0, 0.0))
        if dup is None:
            try:
                unreal.EditorLevelUtils.remove_level_from_world(streaming.get_loaded_level())
            except Exception:
                pass
            return fatal(R, "duplicate_actor returned None", unreal, eas)

        dup_level = dup.get_typed_outer(unreal.Level)
        R["dup_landed_in_target"] = bool(dup_level and persistent_name in str(
            dup_level.get_path_name()))

        dup.set_actor_label(VOLUME_LABEL)
        dup.set_actor_location(unreal.Vector(*SPAWN_LOC), False, False)
        R["volume_source"] = "duplicated_from_%s" % SOURCE_LABEL

        # done with the sublevel now -- the graph asset itself is independent
        # of Bldg_SGD_level being loaded (confirmed by Task 6's own script,
        # which never touches Bldg_SGD_level beyond reading the source actor).
        try:
            removed = unreal.EditorLevelUtils.remove_level_from_world(streaming.get_loaded_level())
            R["sgd_level_sublevel_removed"] = bool(removed)
        except Exception as ex:
            R["sgd_level_sublevel_remove_err"] = "%s: %s" % (type(ex).__name__, ex)

    comp = dup.get_component_by_class(unreal.PCGComponent)
    if comp is None:
        return fatal(R, "volume actor has no PCGComponent", unreal, eas, dup_actor=dup)

    loc = dup.get_actor_location()
    R["volume_location"] = [round(float(loc.x), 1), round(float(loc.y), 1), round(float(loc.z), 1)]

    # wipe any content that rode along with the duplicate so every instance
    # counted by the read script is attributable to this run's TL generation.
    try:
        comp.cleanup_local(True)
        R["pre_cleanup"] = "OK"
    except Exception as e:
        R["pre_cleanup"] = "%s: %s" % (type(e).__name__, e)

    # ---------- override ShapeGrammarDefinition -> SGD_TL_A (Task 6 recipe) --
    gi = comp.graph_instance
    po = gi.get_editor_property("parameters_overrides")
    bag = po.get_editor_property("parameters")

    before = bag.export_text()
    R["bag_before"] = before

    sgd = ael.load_asset(SGD_TL_PATH)
    if sgd is None:
        return fatal(R, "could not load SGD_TL_A at %s" % SGD_TL_PATH, unreal, eas, dup_actor=dup)
    sgd_path = sgd.get_path_name()
    R["sgd_path"] = sgd_path

    m = re.search(r'ShapeGrammarDefinition="([^"]*)"', before)
    if not m:
        return fatal(R, "ShapeGrammarDefinition field not found in bag: %r" % before,
                    unreal, eas, dup_actor=dup)
    R["old_sgd_in_bag"] = m.group(1)

    new_text = before[:m.start(1)] + sgd_path + before[m.end(1):]
    import_ok = bag.import_text(new_text)
    R["import_text_result"] = str(import_ok)

    po.set_editor_property("parameters", bag)
    gi.set_editor_property("parameters_overrides", po)

    after = gi.get_editor_property("parameters_overrides").get_editor_property(
        "parameters").export_text()
    R["bag_after"] = after
    R["sgd_set_correctly"] = sgd_path in after

    if not R["sgd_set_correctly"]:
        return fatal(R, "SGD swap did not take effect -- refusing to generate "
                        "(would silently re-verify CHA instead of TL)",
                    unreal, eas, dup_actor=dup)

    # ---------- generate. activate(True) is REQUIRED -- skipping it is a
    # silent zero. Do NOT read the result in this call; that is
    # tl_new_level_read.py's job, run as a separate call. ------------------
    comp.activate(True)
    comp.generate_local(True)
    R["generated"] = True
    R["note"] = ("generation fired asynchronously; run tl_new_level_read.py as "
                 "a SEPARATE call to read results, then save the level")

    R["gate"] = {"pass": True}
    return R


try:
    _dropped = purge_uobject_globals()
    RESULT = {"ok": True, "dropped_globals": _dropped, "data": run()}
except Exception as _exc:
    RESULT = {"ok": False, "error": "%s: %s" % (type(_exc).__name__, str(_exc)[:500])}

try:
    mcp_result = json.loads(json.dumps(RESULT, default=str))
except Exception as _se:
    mcp_result = {"ok": False, "serialization_failed": str(_se)[:200]}

print(json.dumps(mcp_result, ensure_ascii=False, default=str)[:200000])
del RESULT
gc.collect()
