# Content/Python/tl_new_level_read.py
# Task 10, Step 3 (+ Step 4 save): read back what tl_new_level.py generated,
# in a SEPARATE call from the one that triggered generate_local() -- PCG
# generation is asynchronous; reading in the same call sees an empty/stale
# collection with no error (same discipline as every other PCG script here).
#
# Unlike tl_verify_sgd_read.py (Task 6), this script does NOT clean up the
# probe actor and DOES save the level at the end: "the point is a persisted
# level with a visible building" (task-10-brief.md Step 3), and Step 4 asks
# for the level to be saved so it persists. Content/Map/ is gitignored, so the
# level itself is not a committed artifact -- these two scripts are what make
# it reproducible.
#
# Four numeric readings, per the brief's Step 3 (exact wording echoed in each
# block below): (1) ISM instance count: a building is many instances, not
# one; (2) distinct TL mesh path count -- the load-bearing "did it assemble"
# check, must be > 1; (3) total bounds (facade-only, via per-instance WORLD
# pivot transforms -- get_actor_bounds() is contaminated by the PCGVolume's
# own brush, proven wrong in Task 6, see tl_verify_sgd_read.py header);
# (4) observed level count from L00..L03 kit-folder tags in the mesh paths,
# plus per-level floor Z / within-level spread / floor-to-floor deltas.
#
# GLOBAL DISCIPLINE: no UObject may survive this script (see tl_new_level.py
# header for the measured CheckForWorldGCLeaks() abort this avoids).

import gc
import json
import re

VOLUME_LABEL = "TL_Building_Volume"
TARGET = "/Game/Map/Lvl_TL_Building"
CONFIGURED_WIDTH = 4100.0
CONFIGURED_LENGTH = 4500.0
# TL mesh kit folders are named Kit_Bldg_TL_L0/L1/L2/L3 (Task 3); tolerate
# both the one- and two-digit forms ("_L0_"/"_L00_") the way Task 6's reader
# did for CHA's own kit ("_L2_A"/"_L02_A").
LEVEL_RE = re.compile(r'_L0?(\d)[_/]')
EXPECTED_FLOOR_DELTA = {("1", "2"): 500.0, ("2", "3"): 300.0}
FLOOR_DELTA_TOLERANCE = 40.0
HALF_OFFSET_SUSPECTS = [
    (162.5, "half wall width (325cm wall / 2)"),
    (250.0, "half L1 level height (500cm / 2)"),
    (150.0, "half L2/L3 level height (300cm / 2)"),
]
HALF_OFFSET_TOLERANCE = 20.0


def _holds_uobject(val, ue):
    if isinstance(val, (ue.Object, ue.StructBase)):
        return True
    if isinstance(val, (list, tuple, set)):
        return any(_holds_uobject(v, ue) for v in val)
    if isinstance(val, dict):
        return any(_holds_uobject(v, ue) for v in val.values())
    return False


def purge_uobject_globals():
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


def run():
    import unreal
    R = {}
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

    R["current_level"] = str(les.get_current_level())
    R["on_target"] = TARGET.split("/")[-1] in R["current_level"]
    if not R["on_target"]:
        R["fatal"] = ("current level is not %s -- run tl_new_level.py first, "
                       "or this reader is pointed at the wrong level" % TARGET)
        return R

    target = None
    for a in eas.get_all_level_actors():
        try:
            if a.get_actor_label() == VOLUME_LABEL:
                target = a
                break
        except Exception:
            continue

    if target is None:
        R["fatal"] = "probe volume '%s' not found -- run tl_new_level.py first" % VOLUME_LABEL
        return R

    comp = target.get_component_by_class(unreal.PCGComponent)
    if comp is None:
        R["fatal"] = "probe actor has no PCGComponent"
        return R

    # ---------- reading 0: output pin (secondary corroboration) -------------
    out = {}
    try:
        coll = comp.get_generated_graph_output()
        items = coll.get_editor_property("tagged_data")
        out["tagged_count"] = len(items)
        tot = 0
        for it in items:
            wrap = it.get_editor_property("data")
            d = wrap.get_editor_property("data")
            if d:
                try:
                    tot += d.get_num_points()
                except Exception:
                    pass
        out["total_points"] = tot
    except Exception as e:
        out["fatal"] = "%s: %s" % (type(e).__name__, e)
    R["output_pin"] = out

    # ---------- reading 1+2: ISM instance count + distinct TL mesh paths ----
    spawn = {"components": [], "total_instances": 0, "meshes": {}}
    all_points = []
    level_z = {}
    try:
        total = 0
        meshes = {}
        for c in target.get_components_by_class(unreal.PrimitiveComponent):
            n = 0
            try:
                n = c.get_instance_count()
            except Exception:
                pass
            if not n:
                continue
            total += n
            try:
                mp = c.get_editor_property("static_mesh")
                path = mp.get_path_name() if mp else "<none>"
            except Exception:
                path = "<err>"
            meshes[path] = meshes.get(path, 0) + n
            spawn["components"].append({
                "comp": c.get_name(), "class": c.get_class().get_name(), "instances": n})

            lvl_match = LEVEL_RE.search(path)
            level_tag = lvl_match.group(1) if lvl_match else "unknown"
            for i in range(n):
                try:
                    t = c.get_instance_transform(i, True)  # world_space=True
                    loc = t.translation
                    px, py, pz = float(loc.x), float(loc.y), float(loc.z)
                except Exception:
                    continue
                all_points.append((px, py, pz))
                level_z.setdefault(level_tag, []).append(pz)

        spawn["total_instances"] = total
        spawn["meshes"] = meshes
        spawn["distinct_mesh_count"] = len(meshes)
        spawn["tl_mesh_paths"] = [k for k in meshes if "/TL/" in k or "_TL_" in k]
        spawn["distinct_tl_mesh_count"] = len(spawn["tl_mesh_paths"])
        spawn["tl_mesh_instances"] = sum(
            v for k, v in meshes.items() if k in spawn["tl_mesh_paths"])
        spawn["non_tl_mesh_instances"] = total - spawn["tl_mesh_instances"]
        spawn["instances_sampled_for_transforms"] = len(all_points)
        # the load-bearing check, verbatim from the brief: "the count of
        # distinct parts must be greater than one"
        spawn["ASSEMBLY_CHECK_distinct_tl_parts_gt_1"] = spawn["distinct_tl_mesh_count"] > 1
    except Exception as e:
        spawn["fatal"] = "%s: %s" % (type(e).__name__, e)
    R["spawned"] = spawn

    # ---------- reading 3: facade-only extent via per-instance world pivots -
    extent = {}
    try:
        if not all_points:
            raise RuntimeError("no instance transforms sampled -- cannot compute bounds")
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        zs = [p[2] for p in all_points]
        span_x = max(xs) - min(xs)
        span_y = max(ys) - min(ys)
        span_z = max(zs) - min(zs)
        extent["method"] = ("union of ALL ISM instance pivot world-transforms, "
                             "NOT get_actor_bounds() (contaminated by the "
                             "PCGVolume brush -- see tl_verify_sgd_read.py)")
        extent["min_xyz"] = [round(min(xs), 1), round(min(ys), 1), round(min(zs), 1)]
        extent["max_xyz"] = [round(max(xs), 1), round(max(ys), 1), round(max(zs), 1)]
        extent["pivot_span_xyz"] = [round(span_x, 1), round(span_y, 1), round(span_z, 1)]
        extent["pivot_span_z_metres"] = round(span_z / 100.0, 2)
        extent["configured_width"] = CONFIGURED_WIDTH
        extent["configured_length"] = CONFIGURED_LENGTH
        extent["delta_x_vs_width"] = round(span_x - CONFIGURED_WIDTH, 1)
        extent["delta_y_vs_length"] = round(span_y - CONFIGURED_LENGTH, 1)
        extent["note"] = ("pivot span runs a bit short of the outer footprint/"
                           "roofline by design -- pivots sit inset from the "
                           "outer face and a level's pivot sits at its own "
                           "floor, not its ceiling (see tl_verify_sgd_read.py)")
        extent["upright"] = span_z > 300.0
    except Exception as e:
        extent["fatal"] = "%s: %s" % (type(e).__name__, e)
    R["extent"] = extent

    # ---------- reading 4: per-level floor stacking / observed level count --
    levels = {}
    try:
        if not level_z:
            raise RuntimeError("no per-level Z data sampled")

        def _sort_key(k):
            return (0, int(k)) if k.isdigit() else (1, k)

        order = sorted(level_z.keys(), key=_sort_key)
        per_level = {}
        for lvl in order:
            zs = level_z[lvl]
            per_level[lvl] = {
                "instance_count": len(zs),
                "floor_z": round(min(zs), 1),
                "max_z": round(max(zs), 1),
                "within_level_spread": round(max(zs) - min(zs), 1),
            }
        levels["per_level"] = per_level
        numeric_order = [k for k in order if k.isdigit()]
        levels["observed_level_count"] = len(numeric_order)
        levels["observed_levels"] = numeric_order

        flags = []
        for lvl, info in per_level.items():
            spread = info["within_level_spread"]
            for suspect, label in HALF_OFFSET_SUSPECTS:
                if abs(spread - suspect) <= HALF_OFFSET_TOLERANCE:
                    flags.append(
                        "level %s: within-level Z spread %.1f cm is suspiciously "
                        "close to %s -- possible wrong PivotOffset" % (lvl, spread, label))
        levels["suspicious_offset_flags"] = flags

        deltas = []
        for a, b in zip(numeric_order, numeric_order[1:]):
            d = per_level[b]["floor_z"] - per_level[a]["floor_z"]
            entry = {"from_level": a, "to_level": b, "floor_delta": round(d, 1)}
            exp = EXPECTED_FLOOR_DELTA.get((a, b))
            if exp is not None:
                entry["expected"] = exp
                entry["matches_expected"] = abs(d - exp) <= FLOOR_DELTA_TOLERANCE
            deltas.append(entry)
        levels["floor_deltas"] = deltas

        if len(numeric_order) >= 2:
            lo, hi = numeric_order[0], numeric_order[-1]
            levels["measured_floor_span_L%s_to_L%s" % (lo, hi)] = round(
                per_level[hi]["floor_z"] - per_level[lo]["floor_z"], 1)
    except Exception as e:
        levels["fatal"] = "%s: %s" % (type(e).__name__, e)
    R["levels"] = levels

    # ---------- plain verdict -------------------------------------------
    try:
        verdict_pass = (
            spawn.get("total_instances", 0) > 0
            and spawn.get("ASSEMBLY_CHECK_distinct_tl_parts_gt_1", False)
            and extent.get("upright", False)
            and levels.get("observed_level_count", 0) > 1
        )
        R["VERDICT"] = {
            "modules_assembled_into_a_building": bool(verdict_pass),
            "total_instances": spawn.get("total_instances", 0),
            "distinct_tl_mesh_count": spawn.get("distinct_tl_mesh_count", 0),
            "observed_level_count": levels.get("observed_level_count", 0),
            "pivot_span_z_metres": extent.get("pivot_span_z_metres"),
        }
    except Exception as e:
        R["VERDICT"] = {"error": "%s: %s" % (type(e).__name__, e)}

    # ---------- Step 4: save the level (and ONLY this level) ----------------
    # Deliberately do NOT touch the demo level or any other pre-existing
    # level; save_current_level only acts on whatever level is current, which
    # on_target already confirmed is Lvl_TL_Building.
    save = {}
    try:
        save["save_current_level_result"] = bool(les.save_current_level())
    except Exception as e:
        save["save_current_level_result"] = "%s: %s" % (type(e).__name__, e)
    R["save"] = save

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
