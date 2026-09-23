# pcg_area_step1_build.py
# Step 1 of the 3x3 small-area build (E:\PCG_Claude).
#
# Creates the PCG graph, adds every node, sets every parameter, and REPORTS ALL
# REAL PIN LABELS. It deliberately adds NO edges: node-classes.md 0.4 records
# that add_edge fails SILENTLY (and returns a truthy node) when the pin label is
# wrong, so step 2 wires using only the labels printed here.
#
# Structure:
#   Ground    CreatePointsGrid -> TransformPoints -> StaticMeshSpawner(Plane)
#   RoadsX    CreatePointsGrid -> TransformPoints -> StaticMeshSpawner(Cube)
#   RoadsY    CreatePointsGrid -> TransformPoints -> StaticMeshSpawner(Cube)
#   Buildings CreatePointsGrid -> TransformPoints -> StaticMeshSpawner(Cube)
#
# Expected point counts come from the measured formula in tooling.md 3.3:
#   count = (2*ext.x/cell.x) * (2*ext.y/cell.y) * (2*ext.z/cell.z)
# (extents are FULL width; Z counts as layers).
#
# Also probes, in the same round trip, how a PCGVolume can be given real bounds
# in this project: no unreal.CubeBuilder exists, so a freshly spawned PCGVolume
# may have an empty brush and zero bounds, which would break generation.

import json

R = {}
def S(x):
    return str(x)

def ts(obj, prop, val):
    try:
        obj.set_editor_property(prop, val)
    except Exception as e:
        return "SET-ERR %s: %s" % (type(e).__name__, S(e)[:130])
    try:
        return "OK -> " + S(obj.get_editor_property(prop))
    except Exception as e:
        return "READ-ERR %s" % type(e).__name__

def pin_labels(node, which):
    try:
        pins = node.get_editor_property(which)
    except Exception as e:
        return ["<err %s>" % e]
    out = []
    for p in pins:
        try:
            out.append(S(p.get_editor_property("properties").get_editor_property("label")))
        except Exception:
            out.append("<noread>")
    return out

def expected_points(e, c):
    return int(2 * e[0] / c[0]) * int(2 * e[1] / c[1]) * int(2 * e[2] / c[2])

def add(clsname):
    cls = unreal.load_class(None, "/Script/PCG." + clsname)
    node, st = g.add_node_of_type(cls)
    return node, st

def set_mesh(sset, mesh_path):
    try:
        sel = sset.get_editor_property("mesh_selector_parameters")
        entry = unreal.PCGMeshSelectorWeightedEntry()
        desc = entry.get_editor_property("descriptor")
        desc.set_editor_property("static_mesh", unreal.load_asset(mesh_path))
        entry.set_editor_property("weight", 1.0)
        sel.set_editor_property("mesh_entries", [entry])
        n = len(sel.get_editor_property("mesh_entries"))
        return "entries=%d; synchronous_load %s" % (n, ts(sset, "synchronous_load", True))
    except Exception as e:
        return "ERR %s: %s" % (type(e).__name__, S(e)[:150])

print("step1: creating graph")
GRAPH_NAME = "PCG_SmallArea_3x3"
PKG = "/Game/PCGArea"
GRAPH_PATH = PKG + "/" + GRAPH_NAME

at = unreal.AssetToolsHelpers.get_asset_tools()
R["existed_before"] = unreal.EditorAssetLibrary.does_asset_exist(GRAPH_PATH)
if R["existed_before"]:
    g = unreal.load_asset(GRAPH_PATH)
    n_removed = 0
    try:
        for n in list(g.get_editor_property("nodes")):
            try:
                g.remove_node(n); n_removed += 1
            except Exception:
                pass
    except Exception:
        pass
    R["nodes_removed_for_rebuild"] = n_removed
else:
    g = at.create_asset(GRAPH_NAME, PKG, unreal.PCGGraph, unreal.PCGGraphFactory())
if g is None:
    R["fatal"] = "create_asset returned None (trap 15)"
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit("create_asset returned None")
R["graph_class"] = g.get_class().get_name()
R["graph_path"] = g.get_path_name()

R["enum_PCGCoordinateSpace"] = [x for x in dir(unreal.PCGCoordinateSpace) if not x.startswith("_")]
R["enum_PCGPointPosition"] = [x for x in dir(unreal.PCGPointPosition) if not x.startswith("_")]

N = {}

def cluster(key, extents, cell, tp_sets, mesh_path):
    gn, gs = add("PCGCreatePointsGridSettings")
    tn, tset = add("PCGTransformPointsSettings")
    sn, sset = add("PCGStaticMeshSpawnerSettings")
    info = {
        "key": key,
        "extents": list(extents), "cell": list(cell),
        "expected_points": expected_points(extents, cell),
        "grid_params": {}, "tp_params": {},
    }
    info["grid_params"]["grid_extents"] = ts(gs, "grid_extents", unreal.Vector(*extents))
    info["grid_params"]["cell_size"] = ts(gs, "cell_size", unreal.Vector(*cell))
    info["grid_params"]["set_points_bounds"] = ts(gs, "set_points_bounds", True)
    info["grid_params"]["cull_points_outside_volume"] = ts(gs, "cull_points_outside_volume", False)
    info["grid_params"]["coordinate_space"] = ts(gs, "coordinate_space", unreal.PCGCoordinateSpace.LOCAL_COMPONENT)
    info["grid_params"]["point_position"] = ts(gs, "point_position", unreal.PCGPointPosition.CELL_CENTER)
    for p, v in tp_sets.items():
        if "rotation" in p:
            val = unreal.Rotator(*v) if isinstance(v, tuple) else v
        elif isinstance(v, tuple):
            val = unreal.Vector(*v)
        else:
            val = v
        info["tp_params"][p] = ts(tset, p, val)
    info["mesh"] = set_mesh(sset, mesh_path)
    info["tp_dir_sample"] = [m for m in dir(tset) if not m.startswith("_")][:80]
    info["pins"] = {
        "grid_in": pin_labels(gn, "input_pins"), "grid_out": pin_labels(gn, "output_pins"),
        "tp_in": pin_labels(tn, "input_pins"), "tp_out": pin_labels(tn, "output_pins"),
        "spawn_in": pin_labels(sn, "input_pins"), "spawn_out": pin_labels(sn, "output_pins"),
    }
    N[key] = (gn, tn, sn)
    return info

TP_ZERO_ROT = {"rotation_min": (0, 0, 0), "rotation_max": (0, 0, 0), "absolute_rotation": True}

R["clusters"] = []
R["clusters"].append(cluster(
    "ground", (50, 50, 50), (100, 100, 100),
    dict({"absolute_scale": True, "uniform_scale": False,
          "scale_min": (66, 66, 1), "scale_max": (66, 66, 1),
          "offset_min": (0, 0, 0), "offset_max": (0, 0, 0)}, **TP_ZERO_ROT),
    "/Engine/BasicShapes/Plane.Plane"))
R["clusters"].append(cluster(
    "roadsX", (50, 4000, 50), (100, 2000, 100),
    dict({"absolute_scale": True, "uniform_scale": False,
          "scale_min": (66, 6, 0.1), "scale_max": (66, 6, 0.1),
          "offset_min": (0, 0, 5), "offset_max": (0, 0, 5)}, **TP_ZERO_ROT),
    "/Engine/BasicShapes/Cube.Cube"))
R["clusters"].append(cluster(
    "roadsY", (4000, 50, 50), (2000, 100, 100),
    dict({"absolute_scale": True, "uniform_scale": False,
          "scale_min": (6, 66, 0.1), "scale_max": (6, 66, 0.1),
          "offset_min": (0, 0, 4.5), "offset_max": (0, 0, 4.5)}, **TP_ZERO_ROT),
    "/Engine/BasicShapes/Cube.Cube"))
R["clusters"].append(cluster(
    "buildings", (3000, 3000, 50), (1000, 1000, 100),
    dict({"absolute_scale": True, "uniform_scale": False,
          "scale_min": (6, 6, 6), "scale_max": (6, 6, 26),
          "offset_min": (0, 0, 310), "offset_max": (0, 0, 310)}, **TP_ZERO_ROT),
    "/Engine/BasicShapes/Cube.Cube"))

R["expected_total_points"] = sum(c["expected_points"] for c in R["clusters"])

# ---- OUTPUT NODE: what pin does it expose? ----
out = None
try:
    out = g.get_output_node()
    R["output_node"] = {
        "name": out.get_name(),
        "settings": out.get_settings().get_class().get_name() if out.get_settings() else None,
        "in": pin_labels(out, "input_pins"),
        "out": pin_labels(out, "output_pins"),
    }
except Exception as e:
    R["output_node"] = "<err %s: %s>" % (type(e).__name__, S(e)[:160])
try:
    R["input_node"] = S(g.get_input_node())
except Exception as e:
    R["input_node"] = "<err %s>" % type(e).__name__
R["node_count"] = len(g.get_editor_property("nodes"))
R["edge_count"] = len(g.get_all_edges())

# ---- PCGVolume bounds capability probe ----
V = {}
V["names_with_Builder"] = [c for c in dir(unreal) if "Builder" in c]
V["names_with_ActorFactory"] = [c for c in dir(unreal) if "ActorFactory" in c]
V["names_with_Volume"] = [c for c in dir(unreal) if "Volume" in c]
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
V["has_duplicate_actor"] = hasattr(eas, "duplicate_actor")
try:
    for a in eas.get_all_level_actors():
        cn = a.get_class().get_name()
        if cn == "PostProcessVolume":
            bc = a.get_editor_property("brush_component")
            V["ppv_brush_type"] = S(type(bc.get_editor_property("brush")).__name__)
            V["ppv_brush_is_none"] = (bc.get_editor_property("brush") is None)
            o, e2 = a.get_actor_bounds(False, False)
            V["ppv_actor_bounds_origin"] = [o.x, o.y, o.z]
            V["ppv_actor_bounds_extent"] = [e2.x, e2.y, e2.z]
            V["ppv_local_bounds_pcg"] = S(a.get_actor_local_bounds_pcg())
            V["ppv_brush_builder_type"] = S(type(a.get_editor_property("brush_builder")).__name__)
except Exception as e:
    V["ppv_err"] = "%s: %s" % (type(e).__name__, S(e)[:160])

# spawn a throwaway PCGVolume (origin, scale 1) and ask it for its bounds
tmp = None
try:
    tmp = eas.spawn_actor_from_class(unreal.PCGVolume, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    V["spawned"] = tmp is not None
    if tmp:
        V["tmp_local_bounds_pcg"] = S(tmp.get_actor_local_bounds_pcg())
        V["tmp_actor_bounds_pcg"] = S(tmp.get_actor_bounds_pcg())
        o, e2 = tmp.get_actor_bounds(False, False)
        V["tmp_actor_bounds_extent"] = [e2.x, e2.y, e2.z]
        V["tmp_brush_builder_type"] = S(type(tmp.get_editor_property("brush_builder")).__name__)
        V["tmp_brush_none"] = (tmp.get_editor_property("brush_component").get_editor_property("brush") is None)
        V["tmp_pcg_component"] = S(tmp.pcg_component)
except Exception as e:
    V["tmp_err"] = "%s: %s" % (type(e).__name__, S(e)[:160])
if tmp:
    try:
        eas.destroy_actor(tmp)
        V["tmp_destroyed"] = True
    except Exception as e:
        V["tmp_destroyed"] = "ERR %s" % S(e)[:100]
R["volume_probe"] = V

try:
    R["saved"] = unreal.EditorAssetLibrary.save_asset(GRAPH_PATH)
except Exception as e:
    R["saved"] = "ERR %s" % S(e)[:120]

print("step1: done, nodes=%d edges=%d expected_points=%d" % (
    R["node_count"], R["edge_count"], R["expected_total_points"]))
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
