# pcg_area_probe.py — reconnaissance before building the small area.
#
# Read-only. Answers three questions the build script depends on:
#   1. which static meshes exist in this project (it is a bare third-person
#      template, so the engine BasicShapes set is likely all there is)
#   2. what properties TransformPoints actually exposes, and which of them take
#      (scale_min, scale_max, offset, absolute_scale, rotation_*)
#   3. the same for the StaticMeshSpawner, to re-confirm the mesh path
#
# Per the skill: probe, do not guess. Every property name this script cannot set
# is reported as a failure rather than silently assumed.

import json

R = {}

# ---------- 1. what meshes are available? --------------------------------
def ls(path, recursive=True):
    try:
        return sorted(unreal.EditorAssetLibrary.list_assets(
            path, recursive=recursive, include_folder=False))
    except Exception as e:
        return ["<err %s>" % e]

basic = ls("/Engine/BasicShapes", recursive=False)
R["engine_basicshapes"] = [p.split(".")[0].split("/")[-1] for p in basic]

R["engine_basic_shapes_short"] = basic

# Any project-side meshes at all?
game_meshes = []
for p in ls("/Game", recursive=True):
    low = p.lower()
    if low.endswith("_staticmesh") or "staticmesh" in low:
        game_meshes.append(p)
R["game_staticmesh_count"] = len(game_meshes)
R["game_staticmesh_sample"] = game_meshes[:25]

# Load and confirm the ones we intend to use
want = ["/Engine/BasicShapes/Cube.Cube",
        "/Engine/BasicShapes/Plane.Plane",
        "/Engine/BasicShapes/Cylinder.Cylinder",
        "/Engine/BasicShapes/Sphere.Sphere",
        "/Engine/BasicShapes/Cone.Cone"]
loaded = {}
for w in want:
    try:
        a = unreal.load_asset(w)
        loaded[w] = (a.get_class().get_name() if a else None)
    except Exception as e:
        loaded[w] = "ERR %s" % type(e).__name__
R["load_checks"] = loaded

# Bounds of Cube and Plane so we can reason about scale numerically
bounds = {}
for w in ("/Engine/BasicShapes/Cube.Cube", "/Engine/BasicShapes/Plane.Plane"):
    try:
        m = unreal.load_asset(w)
        b = m.get_bounds()
        bounds[w] = {"min": [b.min.x, b.min.y, b.min.z],
                     "max": [b.max.x, b.max.y, b.max.z],
                     "box_extent": [b.box_extent.x, b.box_extent.y, b.box_extent.z]}
    except Exception as e:
        bounds[w] = "ERR %s: %s" % (type(e).__name__, e)
R["mesh_bounds"] = bounds

# ---------- 2. TransformPoints property surface ---------------------------
R["tp_dir"] = [m for m in dir(unreal.PCGTransformPointsSettings) if not m.startswith("_")]

tp_tests = {}
tp = unreal.PCGTransformPointsSettings()
for prop, val in (
    ("offset_min", unreal.Vector(0.0, 0.0, 10.0)),
    ("offset_max", unreal.Vector(0.0, 0.0, 10.0)),
    ("scale_min", unreal.Vector(3.0, 3.0, 20.0)),
    ("scale_max", unreal.Vector(5.0, 5.0, 20.0)),
    ("absolute_scale", True),
    ("uniform_scale", False),
    ("rotation_min", unreal.Rotator(0.0, 0.0, 0.0)),
    ("rotation_max", unreal.Rotator(0.0, 0.0, 0.0)),
    ("absolute_rotation", True),
):
    try:
        tp.set_editor_property(prop, val)
        tp_tests[prop] = "OK"
    except Exception as e:
        tp_tests[prop] = "%s: %s" % (type(e).__name__, str(e)[:110])
R["transformpoints_set"] = tp_tests

tp_read = {}
for prop in ("offset_min", "offset_max", "scale_min", "scale_max",
             "absolute_scale", "uniform_scale"):
    try:
        tp_read[prop] = str(tp.get_editor_property(prop))
    except Exception as e:
        tp_read[prop] = type(e).__name__
R["transformpoints_readback"] = tp_read

# ---------- 3. StaticMeshSpawner: re-confirm the mesh path ---------------
sp_tests = {}
sp = unreal.PCGStaticMeshSpawnerSettings()
try:
    sel = sp.get_editor_property("mesh_selector_parameters")
    sp_tests["selector_class"] = sel.get_class().get_name()
    entry = unreal.PCGMeshSelectorWeightedEntry()
    desc = entry.get_editor_property("descriptor")
    desc.set_editor_property("static_mesh", unreal.load_asset("/Engine/BasicShapes/Cube.Cube"))
    entry.set_editor_property("weight", 1.0)
    sel.set_editor_property("mesh_entries", [entry])
    sp_tests["mesh_entries"] = str(sel.get_editor_property("mesh_entries"))
except Exception as e:
    sp_tests["mesh_path"] = "%s: %s" % (type(e).__name__, e)
try:
    sp.set_editor_property("synchronous_load", True)
    sp_tests["synchronous_load"] = "OK"
except Exception as e:
    sp_tests["synchronous_load"] = type(e).__name__
R["spawner"] = sp_tests

# ---------- 4. what is the current level? --------------------------------
lvl = {}
try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    lvl["current"] = str(les.get_current_level())
    lvl["has_new_level"] = hasattr(les, "new_level")
except Exception as e:
    lvl["err"] = "%s: %s" % (type(e).__name__, e)
R["level"] = lvl

print(json.dumps(R, indent=1, default=str))
mcp_result = R
