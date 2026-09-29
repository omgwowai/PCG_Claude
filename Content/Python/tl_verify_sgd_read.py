# tl_verify_sgd_read.py -- PHASE B: read what the TL facade spawned, then clean up.
#
# Two independent readings, because they can disagree in a way that matters:
#   * output-pin point/tagged-data count  -> what the graph piped out
#   * ISM instance count                  -> what geometry actually landed
# A spawn-type graph can report 0 tagged data and still have spawned thousands
# of instances. Geometry is what the acceptance test cares about, so instances
# win as the primary evidence; the output pin is secondary corroboration.
#
# Height/orientation check: rather than guess at a static-mesh-bounds API,
# this uses the PROBE ACTOR's overall bounding box (get_actor_bounds), which
# is always available and directly answers the brief's Step 4 question --
# upright TL facade should read tall in Z (order of the building height) and
# thin in X (the 0.30 m facade depth). If MeshForwardAxis were wrong, the
# facade would read tall in X/Y and thin in Z instead ("lying flat").

import gc
import json

PROBE_LABEL = "TL_SGD_Probe_Volume"

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
spawn = {"components": [], "total_instances": 0, "meshes": {}}
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
    spawn["total_instances"] = total
    spawn["meshes"] = meshes
    spawn["distinct_mesh_count"] = len(meshes)
    spawn["tl_mesh_instances"] = sum(
        v for k, v in meshes.items() if "/Game/Building/TL/" in k)
except Exception as e:
    spawn["fatal"] = "%s: %s" % (type(e).__name__, e)
R["spawned"] = spawn

# ---------- reading 3: is the facade upright, not lying flat? ---------------
# NOTE: this actor's bounds cover the WHOLE assembled building (all 4 walls of
# a ~41x45m footprint), not one wall panel, so X/Y will legitimately exceed Z
# for a real building that is wider than it is tall -- comparing Z against X/Y
# here would be comparing the wrong things (this was tried and produced a
# false "not upright" reading on a correctly-assembled 21 m-tall building; kept
# out on purpose). The real "lying flat" failure mode described in the brief
# is a facade whose height collapses to near the mesh's own thickness (order
# of centimeters), so the honest check is an absolute floor on Z, not a
# comparison to X/Y.
extent = {}
try:
    origin, box_extent = target.get_actor_bounds(False)
    extent["origin"] = [round(float(origin.x), 1), round(float(origin.y), 1), round(float(origin.z), 1)]
    extent["full_size_xyz"] = [round(float(box_extent.x) * 2, 1),
                                round(float(box_extent.y) * 2, 1),
                                round(float(box_extent.z) * 2, 1)]
    x, y, z = extent["full_size_xyz"]
    extent["upright"] = z > 800.0  # several stories tall, nowhere near "flat" (~cm)
except Exception as e:
    extent["fatal"] = "%s: %s" % (type(e).__name__, e)
R["extent"] = extent

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
