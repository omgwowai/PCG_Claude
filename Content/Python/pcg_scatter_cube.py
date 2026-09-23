# pcg_scatter_cube.py — canonical TWO-PHASE example, stage A: build + generate.
#
# This is the working reference for the pattern the skill insists on:
#   * stage A (this file) creates a graph, configures it, generates, and STOPS
#   * stage B (pcg_scatter_read.py) reads the result in a SEPARATE MCP call
#
# Why two files: PCG generation is asynchronous. Reading
# get_generated_graph_output() in the same call as generate_local() returns an
# empty collection, silently. See references/node-classes.md §0.6.
#
# Run:
#   run_unreal_script(script_path="pcg_scatter_cube.py")
#   run_unreal_script(script_path="pcg_scatter_read.py")   # <- required 2nd call
#
# Idempotent: reuse of a just-deleted asset name can return None, so it uses a
# timestamped name and cleans up all its own PCGVolumes first.

import json
import time

R = {}
STAMP = int(time.time()) % 1000000
NAME = "PCG_Scatter_%d" % STAMP
GRAPH = "/Game/PCGTest/" + NAME
MESH = "/Engine/BasicShapes/Cube.Cube"

EAL = unreal.EditorAssetLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# ---------- 0. clear any previous run's actors ---------------------------
killed = []
for a in eas.get_all_level_actors():
    try:
        if a.get_class().get_name() == "PCGVolume":
            c = a.get_component_by_class(unreal.PCGComponent)
            if c:
                try:
                    c.cleanup_local(True)
                except Exception:
                    pass
            eas.destroy_actor(a)
            killed.append(a.get_name())
    except Exception:
        continue
R["prior_actors_destroyed"] = killed

# ---------- 1. create the graph ------------------------------------------
at = unreal.AssetToolsHelpers.get_asset_tools()
g = at.create_asset(NAME, "/Game/PCGTest",
                    unreal.PCGGraph, unreal.PCGGraphFactory())
if g is None:
    R["fatal"] = "create_asset returned None"
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit
R["graph"] = GRAPH

# ---------- 2. Create Points Grid ----------------------------------------
# NOTE: GridExtents is the FULL width, and Z counts as layers:
#   (2*1000/100) * (2*1000/100) * (2*100/100) = 20 * 20 * 2 = 800
grid, gset = g.add_node_of_type(
    unreal.load_class(None, "/Script/PCG.PCGCreatePointsGridSettings"))
for prop, val in (("cell_size", unreal.Vector(100.0, 100.0, 100.0)),
                  ("grid_extents", unreal.Vector(1000.0, 1000.0, 100.0)),
                  ("cull_points_outside_volume", False),
                  ("set_points_bounds", True)):
    try:
        gset.set_editor_property(prop, val)
    except Exception as e:
        R.setdefault("config_errors", {})[prop] = "%s: %s" % (type(e).__name__, e)

# ---------- 3. Static Mesh Spawner: give it a mesh ------------------------
# MEASURED PATH (the obvious guesses all fail):
#   settings.mesh_selector_parameters -> a PCGMeshSelectorWeighted OBJECT
#   that object's own property is `mesh_entries` (a TArray of
#   PCGMeshSelectorWeightedEntry)
#   each entry has `weight` and `descriptor` (a PCGSoftISMComponentDescriptor)
#   and the descriptor's `static_mesh` is what you set.
spawner, sset = g.add_node_of_type(
    unreal.load_class(None, "/Script/PCG.PCGStaticMeshSpawnerSettings"))
mesh_ok = None
try:
    sel = sset.get_editor_property("mesh_selector_parameters")
    entry = unreal.PCGMeshSelectorWeightedEntry()
    desc = entry.get_editor_property("descriptor")
    desc.set_editor_property("static_mesh", unreal.load_asset(MESH))
    entry.set_editor_property("weight", 1.0)
    sel.set_editor_property("mesh_entries", [entry])
    mesh_ok = str(sel.get_editor_property("mesh_entries"))
except Exception as e:
    mesh_ok = "%s: %s" % (type(e).__name__, e)
R["mesh_entries"] = mesh_ok

try:
    sset.set_editor_property("synchronous_load", True)   # else MCP sees nothing
    R["synchronous_load"] = True
except Exception as e:
    R["synchronous_load"] = "%s: %s" % (type(e).__name__, e)

# ---------- 4. wire grid -> spawner -> output ----------------------------
def wire(a, b, to_label):
    """add_edge returns the To node even when it creates NOTHING. Verify."""
    before = len(g.get_all_edges())
    try:
        g.add_edge(a, "Out", b, to_label)
    except Exception as e:
        return "raised %s" % type(e).__name__
    if len(g.get_all_edges()) > before:
        return "OK"
    for p in b.get_editor_property("input_pins"):
        try:
            lbl = str(p.get_editor_property("properties").get_editor_property("label"))
        except Exception:
            continue
        b2 = len(g.get_all_edges())
        try:
            g.add_edge(a, "Out", b, lbl)
        except Exception:
            continue
        if len(g.get_all_edges()) > b2:
            return "OK via %r" % lbl
    return "FAILED - no edge created"

R["edge_grid_to_spawner"] = wire(grid, spawner, "In")
R["edge_spawner_to_output"] = wire(spawner, g.get_output_node(), "Out")
R["total_edges"] = len(g.get_all_edges())
EAL.save_asset(GRAPH)

# ---------- 5. volume + generate -----------------------------------------
vol = eas.spawn_actor_from_class(unreal.PCGVolume,
                                 unreal.Vector(0.0, 0.0, 0.0),
                                 unreal.Rotator(0.0, 0.0, 0.0))
try:
    bb = vol.get_editor_property("brush_builder")
    bb.set_editor_property("x", 1500.0)
    bb.set_editor_property("y", 1500.0)
    bb.set_editor_property("z", 500.0)
    R["brush"] = "set"
except Exception as e:
    R["brush"] = "%s: %s" % (type(e).__name__, e)

comp = vol.get_component_by_class(unreal.PCGComponent)
comp.set_editor_property("seed", 42)
comp.set_graph(g)
try:
    comp.activate(True)
except Exception:
    pass
try:
    comp.generate_local(True)
    R["generate_local"] = "OK"
except Exception as e:
    R["generate_local"] = "%s: %s" % (type(e).__name__, e)

R["next"] = "run pcg_scatter_read.py in a SEPARATE call"
print(json.dumps(R, indent=1, default=str))
mcp_result = R
