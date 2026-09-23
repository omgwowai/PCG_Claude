# pcg_area_step3_volume.py
# Step 3: finalise the graph's coordinate space, fix the road overlap, spawn the
# PCGVolume, size its brush, hang the graph on it, and GENERATE.
#
# CORRECTED after the first run of this script produced a SILENT ZERO (41 points
# expected, 0 produced, no error). Root cause, read out of the engine source:
#
#   UPCGComponent::GenerateInternal bails on
#     if (IsGenerating() || !GetSubsystem() || !ShouldGenerate(...))
#         return InvalidPCGTaskId;
#   and UPCGComponent::ShouldGenerate() requires
#     bActivated && GetGraph() && GetSubsystem()
#
# A PCGVolume that was spawned moments earlier in the same script is not yet
# activated, so generate_local() returned an invalid task id and generated
# nothing - without raising. The fix is the explicit activate() below, which is
# also what the project's known-good pcg_scatter_cube.py does.
#
# Two other corrections applied here:
#
#  1) coordinate_space LOCAL_COMPONENT -> WORLD.
#     A PCGVolume cannot have its BrushComponent.brush read or written from
#     Python (it is protected) and there is no unreal.CubeBuilder constructor,
#     but the instanced CubeBuilder object IS reachable via
#     get_editor_property("brush_builder"). Sizing the brush explicitly means
#     the actor scale no longer has to be abused to cover the area, so extents
#     can be absolute world units. Under LOCAL_COMPONENT (the default) any actor
#     scale would multiply the grid extents.
#
#  2) roadsY z offset 10 -> 5.
#     Both road clusters centred at z=10 with 20-unit thickness put two coplanar
#     top faces exactly at z=20, four times over at the intersections. Dropping
#     roadsY makes its top 15, so the X roads stay visibly on top.
#
# Node identity is by MEASURED PROPERTY (grid extents), not by array order.

import json

R = {}
def S(x):
    return str(x)

GRAPH_PATH = "/Game/PCGArea/PCG_SmallArea_3x3"
g = unreal.load_asset(GRAPH_PATH)
if g is None:
    R["fatal"] = "graph missing"
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit("graph missing")

nodes = list(g.get_editor_property("nodes"))
R["node_count"] = len(nodes)
R["edge_count_before"] = len(g.get_all_edges())

# ---- 1. identify the four grid nodes by their measured extents ----
grids = []
for n in nodes:
    try:
        st = n.get_settings()
    except Exception:
        continue
    if st is None:
        continue
    if st.get_class().get_name() != "PCGCreatePointsGridSettings":
        continue
    e = st.get_editor_property("grid_extents")
    grids.append((n, st, (e.x, e.y, e.z)))
R["grid_nodes_found"] = len(grids)
R["grid_extents_before"] = [list(gg[2]) for gg in grids]

R["coord_space_changes"] = {}
for n, st, e in grids:
    try:
        st.set_editor_property("coordinate_space", unreal.PCGCoordinateSpace.WORLD)
        R["coord_space_changes"][S(e)] = S(st.get_editor_property("coordinate_space"))
    except Exception as ex:
        R["coord_space_changes"][S(e)] = "ERR %s: %s" % (type(ex).__name__, S(ex)[:120])

# ---- 2. roadsY (scale_min 6 x 60) gets the lower z offset ----
# Identified by the TransformPoints node's own scale, which is unique to that
# cluster. Do NOT try to walk PCGEdge for this: its get_output_node() /
# get_input_node() are named against intuition (measured: for the edge
# Spawner.Out -> Output.In, get_output_node() returns the OUTPUT node).
R["roadsY_fix"] = "not found"
for n in nodes:
    try:
        st = n.get_settings()
    except Exception:
        continue
    if st is None or st.get_class().get_name() != "PCGTransformPointsSettings":
        continue
    sm = st.get_editor_property("scale_min")
    if abs(sm.x - 6) < 0.01 and abs(sm.y - 60) < 0.01:
        try:
            st.set_editor_property("offset_min", unreal.Vector(0.0, 0.0, 5.0))
            st.set_editor_property("offset_max", unreal.Vector(0.0, 0.0, 5.0))
            R["roadsY_fix"] = "OK -> %s" % S(st.get_editor_property("offset_min"))
        except Exception as ex:
            R["roadsY_fix"] = "ERR %s: %s" % (type(ex).__name__, S(ex)[:120])
        break

# ---- 3. spawn the volume ----
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
existing = [a for a in eas.get_all_level_actors()
            if a.get_class().get_name() == "PCGVolume"]
R["existing_pcgvolumes"] = len(existing)
for a in existing:
    try:
        eas.destroy_actor(a)
    except Exception as e:
        R.setdefault("destroy_errs", []).append(S(e)[:100])

vol = eas.spawn_actor_from_class(unreal.PCGVolume,
                                 unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
if vol is None:
    R["fatal"] = "spawn_actor_from_class returned None"
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit("volume spawn failed")
R["volume_spawned"] = True
try:
    vol.set_actor_label("PCGVolume_SmallArea_3x3")
    R["label"] = vol.get_actor_label()
except Exception as e:
    R["label"] = "ERR %s" % S(e)[:100]

# actor scale stays 1: the brush defines coverage, and the grids are WORLD-space
try:
    vol.set_actor_scale3d(unreal.Vector(1.0, 1.0, 1.0))
    R["volume_scale"] = S(vol.get_actor_scale3d())
except Exception as e:
    R["volume_scale"] = "ERR %s" % S(e)[:120]

# size the brush so it wraps the 6600x6600 ground and the tallest building.
# CubeBuilder's x/y/z are FULL sizes: x=6600 gives local bounds +-3300.
B = {}
try:
    bb = vol.get_editor_property("brush_builder")
    B["builder_class"] = bb.get_class().get_name()
    for p, v in (("x", 6600.0), ("y", 6600.0), ("z", 1800.0)):
        bb.set_editor_property(p, v)
    B["readback"] = [S(bb.get_editor_property(p)) for p in ("x", "y", "z")]
    B["local_bounds_after"] = S(vol.get_actor_local_bounds_pcg())
except Exception as e:
    B["err"] = "%s: %s" % (type(e).__name__, S(e)[:180])
R["brush"] = B

# ---- 4. hang the graph, ACTIVATE, then generate ----
pc = None
try:
    pc = vol.pcg_component
    R["pcg_component"] = S(pc)
except Exception as e:
    R["pcg_component"] = "ERR %s" % S(e)[:120]

if pc is not None:
    try:
        pc.set_graph(unreal.load_asset(GRAPH_PATH))
        R["graph_on_component"] = S(pc.get_graph())
    except Exception as e:
        R["graph_on_component"] = "ERR %s: %s" % (type(e).__name__, S(e)[:150])
    try:
        pc.set_editor_property("seed", 4242)
        R["seed"] = S(pc.get_editor_property("seed"))
    except Exception as e:
        R["seed"] = "ERR %s" % S(e)[:100]

    # THE FIX: without this, ShouldGenerate() returns false and generate_local()
    # silently does nothing (see the header comment).
    try:
        pc.activate(True)
        R["activate"] = "called"
        R["activated"] = S(pc.get_editor_property("activated"))
    except Exception as e:
        R["activate"] = "ERR %s: %s" % (type(e).__name__, S(e)[:150])

    try:
        pc.generate_local(True)
        R["generate_local"] = "called"
    except Exception as e:
        R["generate_local"] = "ERR %s: %s" % (type(e).__name__, S(e)[:200])

    if not R.get("activated") == "True":
        R["warning"] = "component not activated - generation will be a silent zero"

# ---- 5. save ----
try:
    R["graph_saved"] = unreal.EditorAssetLibrary.save_asset(GRAPH_PATH)
except Exception as e:
    R["graph_saved"] = "ERR %s" % S(e)[:120]
try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    R["level_saved"] = S(les.save_current_level())
except Exception as e:
    R["level_saved"] = "ERR %s: %s" % (type(e).__name__, S(e)[:150])

R["next"] = "read results in a SEPARATE call (generation is async)"
print("step3: grids=%d coordspace=%d roadsY=%s activated=%s gen=%s" % (
    len(grids), len(R["coord_space_changes"]), R["roadsY_fix"],
    R.get("activated"), R.get("generate_local")))
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
