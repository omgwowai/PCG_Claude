# tl_verify_sgd_read.py -- PHASE B: read what the TL facade spawned, then clean up.
#
# Two independent readings, because they can disagree in a way that matters:
#   * output-pin point/tagged-data count  -> what the graph piped out
#   * ISM instance count                  -> what geometry actually landed
# A spawn-type graph can report 0 tagged data and still have spawned thousands
# of instances. Geometry is what the acceptance test cares about, so instances
# win as the primary evidence; the output pin is secondary corroboration.
#
# --- Fixes from the Task 6 review (2026-09-29), both Critical/Important:
#
# Critical 2: the old "upright" check used `target.get_actor_bounds(False)` --
# the WHOLE ACTOR's bounds, which includes the PCGVolume's own brush geometry,
# not just the ISM facade components already correctly isolated in reading 2.
# Proof this was wrong: it reported `full_size_xyz = [5000, 5000, 2100.5]` --
# X and Y were both exactly 5000, matching NEITHER Width=4100 nor Length=4500
# configured on the probe, meaning the volume's brush (not the facade) was
# dominating the measurement. If X/Y weren't footprint-derived, Z wasn't
# facade-height-derived either -- that check could have reported "upright:
# true" even with a flat-lying facade (a wrong MeshForwardAxis), which is
# exactly the failure mode this task exists to catch.
#
# Investigation for the fix (throwaway probes tl_probe_task6h.py/i.py, folded
# in here then deleted): `PrimitiveComponent.get_local_bounds()` was tried
# first and rejected -- on PCGVolume_SGD_CHA it returned the STATIC MESH's own
# single-instance bounds (e.g. a Wall component with 16 instances and a Wall
# component with 34 instances both reported the identical local-bounds X
# extent), i.e. it does NOT account for the instance array's positions at all,
# so it is useless for measuring how far apart 16 or 246 placed instances
# actually span. `get_world_transform()` on the same component additionally
# returned a puzzling non-uniform `scale3d: (25, 25, 10)` with identity
# translation/rotation, which would have poisoned any local-bounds x
# component-transform composition anyway.
# What DOES work and sidesteps both problems: `get_instance_transform(i,
# world_space=True)` on each ISM component -- confirmed via its own docstring
# ("Instance is returned in local space of this component unless bWorldSpace
# is set") to return the fully-resolved WORLD-space transform for instance i
# directly, with scale reading back as a plain 1.0 and translations landing at
# sane, actor-local-relative world coordinates. So the fix unions per-INSTANCE
# world pivot positions (every instance of every ISM component already
# enumerated in reading 2), not per-component local bounds -- this is both
# more correct (no unexplained component scale to reconcile) and reuses the
# exact same data Important 4 needs.
#
# Important 4: the brief's Step 4 anticipated that instance counts alone might
# be inconclusive and asked for a per-instance transform manifest. This is now
# done in the same enumeration pass as the extent fix: every instance's world
# Z is bucketed by building level (parsed from its mesh path, e.g.
# ".../Kit_Bldg_TL_L2_A/..." or "..._L02_A_..." -> level "2"; the NY-borrowed
# foundation mesh parses to level "0"), and reading 4 below reports each
# level's floor Z, the within-level Z spread (should be ~0 -- all of a level's
# modules should sit at the same floor), and the floor-to-floor deltas between
# consecutive TL levels compared against the grammar's known level heights
# (L1=500cm, L2=300cm carries the L1->L2 and L2->L3 deltas respectively). A
# within-level spread landing near half a wall width (162.5cm) or half a level
# height (250/150cm) is flagged explicitly -- that is the numeric signature of
# a wrong PivotOffset, which is the actual thing Critical 2's old check could
# not have caught.
#
# Both readings are PIVOT-based, not mesh-edge/mesh-top based, so they
# necessarily run a bit short of the true outer footprint (pivots sit inset
# from the outer face by roughly half a wall thickness) and short on total
# roof height by about one level's worth (a level's pivot sits at ITS OWN
# floor, not its ceiling -- there is no pivot at the very top of the topmost
# level to measure against). Both gaps are reported as explicit deltas/notes
# rather than silently corrected for, per the review's instruction that "the
# measurement must decide it, not me."

import gc
import json
import re

PROBE_LABEL = "TL_SGD_Probe_Volume"
CONFIGURED_WIDTH = 4100.0   # inherited from CHA -- see tl_verify_sgd.py header
CONFIGURED_LENGTH = 4500.0
LEVEL_RE = re.compile(r'_L0?(\d)_A')
# floor(to_level) - floor(from_level) should equal from_level's OWN height,
# since a level's floor sits directly atop the level below it.
EXPECTED_FLOOR_DELTA = {("1", "2"): 500.0, ("2", "3"): 300.0}
FLOOR_DELTA_TOLERANCE = 40.0
HALF_OFFSET_SUSPECTS = [
    (162.5, "half wall width (325cm wall / 2)"),
    (250.0, "half L1 level height (500cm / 2)"),
    (150.0, "half L2/L3 level height (300cm / 2)"),
]
HALF_OFFSET_TOLERANCE = 20.0

R = {}
args = mcp_args or {}
KEEP = bool(args.get("keep", False))
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

target = None
for a in eas.get_all_level_actors():
    try:
        if a.get_actor_label() == PROBE_LABEL:
            target = a
            break
    except Exception:
        continue

if target is None:
    R["fatal"] = "probe volume not found - run tl_verify_sgd.py first"
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit

comp = target.get_component_by_class(unreal.PCGComponent)

# ---------- reading 1: the output pin (secondary evidence) ------------------
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

# ---------- reading 2: what geometry landed (primary evidence) --------------
# Also collects every instance's WORLD-space pivot transform in the same pass
# (all_points for reading 3, level_z for reading 4) -- see header for why
# get_instance_transform(i, world_space=True) is the right accessor and
# get_local_bounds()/get_world_transform() are not.
spawn = {"components": [], "total_instances": 0, "meshes": {}}
all_points = []     # (x, y, z) world pivot translation, one per instance
level_z = {}        # level tag ("0".."3" or "unknown") -> [z, ...]
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
    spawn["tl_mesh_instances"] = sum(
        v for k, v in meshes.items() if "/Game/Building/TL/" in k)
    spawn["instances_sampled_for_transforms"] = len(all_points)
except Exception as e:
    spawn["fatal"] = "%s: %s" % (type(e).__name__, e)
R["spawned"] = spawn

# ---------- reading 3: facade-only extent (Critical 2 fix) ------------------
extent = {}
try:
    if not all_points:
        raise RuntimeError("no instance transforms sampled - cannot compute "
                            "facade-only bounds")
    xs = [p[0] for p in all_points]
    ys = [p[1] for p in all_points]
    zs = [p[2] for p in all_points]
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    span_z = max(zs) - min(zs)
    extent["method"] = ("union of ALL ISM instance pivot world-transforms "
                         "(replaces get_actor_bounds(), which included the "
                         "PCGVolume brush and was proven wrong -- see header)")
    extent["min_xyz"] = [round(min(xs), 1), round(min(ys), 1), round(min(zs), 1)]
    extent["max_xyz"] = [round(max(xs), 1), round(max(ys), 1), round(max(zs), 1)]
    extent["pivot_span_xyz"] = [round(span_x, 1), round(span_y, 1), round(span_z, 1)]
    extent["configured_width"] = CONFIGURED_WIDTH
    extent["configured_length"] = CONFIGURED_LENGTH
    extent["delta_x_vs_width"] = round(span_x - CONFIGURED_WIDTH, 1)
    extent["delta_x_vs_length"] = round(span_x - CONFIGURED_LENGTH, 1)
    extent["delta_y_vs_width"] = round(span_y - CONFIGURED_WIDTH, 1)
    extent["delta_y_vs_length"] = round(span_y - CONFIGURED_LENGTH, 1)
    extent["note"] = ("pivot span legitimately runs a bit short of the outer "
                       "footprint/roofline (see header) -- reading 4 "
                       "reconciles Z against the known per-level heights")
    # nowhere near the mesh-thickness-order collapse (~cm) a flat-lying facade
    # would produce; comfortably below the ~800-1100cm span the grammar
    # predicts for L1-L3, so this remains a meaningful floor, not a coincidence
    extent["upright"] = span_z > 300.0
except Exception as e:
    extent["fatal"] = "%s: %s" % (type(e).__name__, e)
R["extent"] = extent

# ---------- reading 4: per-level pivot stacking (Important 4 fix) -----------
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

    flags = []
    for lvl, info in per_level.items():
        spread = info["within_level_spread"]
        for suspect, label in HALF_OFFSET_SUSPECTS:
            if abs(spread - suspect) <= HALF_OFFSET_TOLERANCE:
                flags.append(
                    "level %s: within-level Z spread %.1f cm is suspiciously "
                    "close to %s -- possible wrong PivotOffset" % (lvl, spread, label))
    levels["suspicious_offset_flags"] = flags

    numeric_order = [k for k in order if k.isdigit()]
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

# ---------- cleanup: never leave the probe, never save the level -----------
cl = {}
if not KEEP:
    try:
        comp.cleanup_local(True)
        cl["cleanup_local"] = "OK"
    except Exception as e:
        cl["cleanup_local"] = type(e).__name__
    try:
        eas.destroy_actor(target)
        cl["actor_removed"] = True
    except Exception as e:
        cl["actor_removed"] = "%s: %s" % (type(e).__name__, e)
    cl["level_saved"] = False  # deliberately NOT saved - test residue stays out
else:
    cl["skipped"] = "args.keep is true"
R["cleanup"] = cl

print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
del R
gc.collect()
