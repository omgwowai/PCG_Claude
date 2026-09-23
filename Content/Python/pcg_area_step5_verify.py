# pcg_area_step5_verify.py
# Step 5: prove the 41 points became 41 MESH INSTANCES, and size the volume's
# brush to cover the built area.
#
# Why instance counts and not point counts: a point count only proves the graph
# evaluated. InstancedStaticMeshComponent instance counts prove the spawner
# actually produced geometry, which is the thing being delivered.
#
# Brush sizing: CubeBuilder's x/y/z are FULL sizes (setting x=3300 produced
# local bounds +-1650), so 6600 x 6600 x 1800 gives +-3300 x +-3300 x +-900,
# which wraps the ground plane and the 36 buildings with margin.

import json

R = {}
def S(x):
    return str(x)

GRAPH_PATH = "/Game/PCGArea/PCG_SmallArea_3x3"
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

vol = None
for a in eas.get_all_level_actors():
    if a.get_class().get_name() == "PCGVolume":
        vol = a
        break
if vol is None:
    R["fatal"] = "no PCGVolume"
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit("no volume")

R["label"] = S(vol.get_actor_label())
R["actor_scale"] = S(vol.get_actor_scale3d())
R["local_bounds_before"] = S(vol.get_actor_local_bounds_pcg())

# ---- 1. count spawned instances (the real proof of geometry) ----
comps = []
total_instances = 0
try:
    for c in vol.get_components_by_class(unreal.PrimitiveComponent):
        cn = c.get_class().get_name()
        e = {"name": S(c.get_name()), "class": cn}
        n = None
        try:
            n = c.get_instance_count()
        except Exception:
            pass
        e["instance_count"] = n
        try:
            m = c.get_editor_property("static_mesh")
            e["mesh"] = S(m.get_name()) if m else None
        except Exception:
            e["mesh"] = None
        if n:
            total_instances += n
        comps.append(e)
except Exception as e:
    R["components_err"] = "%s: %s" % (type(e).__name__, S(e)[:200])
R["primitive_components"] = comps
R["ism_component_count"] = len([c for c in comps if c["instance_count"] is not None])
R["total_instances"] = total_instances

# ---- 2. size the brush to cover the area ----
B = {}
try:
    bb = vol.get_editor_property("brush_builder")
    for p, v in (("x", 6600.0), ("y", 6600.0), ("z", 1800.0)):
        bb.set_editor_property(p, v)
    B["readback"] = [S(bb.get_editor_property(p)) for p in ("x", "y", "z")]
    B["local_bounds_after"] = S(vol.get_actor_local_bounds_pcg())
    B["world_bounds_after"] = S(vol.get_actor_bounds_pcg())
except Exception as e:
    B["err"] = "%s: %s" % (type(e).__name__, S(e)[:180])
R["brush"] = B

# ---- 3. persist ----
try:
    R["graph_saved"] = unreal.EditorAssetLibrary.save_asset(GRAPH_PATH)
except Exception as e:
    R["graph_saved"] = "ERR %s" % S(e)[:100]
try:
    R["graph_exists"] = unreal.EditorAssetLibrary.does_asset_exist(GRAPH_PATH)
except Exception as e:
    R["graph_exists"] = "ERR %s" % S(e)[:100]
try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    R["level_saved"] = S(les.save_current_level())
except Exception as e:
    R["level_saved"] = "ERR %s: %s" % (type(e).__name__, S(e)[:150])

print("step5: ism_components=%d total_instances=%d (expected 41)" % (
    R["ism_component_count"], R["total_instances"]))
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
