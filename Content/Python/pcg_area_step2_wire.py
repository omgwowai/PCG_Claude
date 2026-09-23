# pcg_area_step2_wire.py
# Step 2: rebuild the 3x3-area graph deterministically, set the corrected
# parameters, WIRE IT, and verify the wiring by edge count.
#
# Why rebuild instead of patching the step-1 graph: node order inside
# graph.nodes is not a documented contract, so identifying "the roadsX grid
# node" by array position would be a guess. Rebuilding in one script keeps a
# live Python handle on every node, so no identification is needed.
#
# Edges are added with the pin labels READ BACK in step 1 (node-classes.md 0.4:
# a wrong label makes add_edge fail silently while still returning a node):
#   CreatePointsGrid."Out"  -> TransformPoints."In"
#   TransformPoints."Out"   -> StaticMeshSpawner."In"
#   StaticMeshSpawner."Out" -> output node."Out"      (its input pin is "Out")
#
# Geometry (cm; the area is 60m x 60m = +-3000):
#   ground   : 1 point at origin, Plane scaled 66  -> 6600 x 6600
#   roadsX   : 2 points at (0, +-1000), Cube 6000 x 600 x 20, z 0..20
#   roadsY   : 2 points at (+-1000, 0), Cube 600 x 6000 x 20, z 0..20
#   buildings: 36 points, 6x6 lattice, spacing 1000, footprint 600, z random
# Streets at x,y = +-1000 split the 6x6 lattice into 3x3 blocks of 2x2.
# Mesh fact used throughout: every BasicShapes mesh is 100 units at scale 1,
# so scale N gives N*100 units (measured: Cube box_extent 50, Plane 50/50/0).

import json

R = {}
def S(x):
    return str(x)

GRAPH_PATH = "/Game/PCGArea/PCG_SmallArea_3x3"
g = unreal.load_asset(GRAPH_PATH)
if g is None:
    R["fatal"] = "graph not found at " + GRAPH_PATH
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit("graph missing")

# ---- clear: start from an empty graph ----
removed = 0
fails = 0
for n in list(g.get_editor_property("nodes")):
    try:
        g.remove_node(n)
        removed += 1
    except Exception:
        fails += 1
R["nodes_removed"] = removed
R["nodes_remove_failed"] = fails
R["nodes_after_clear"] = len(g.get_editor_property("nodes"))
R["edges_after_clear"] = len(g.get_all_edges())

out_node = g.get_output_node()
R["output_node_name"] = out_node.get_name()


def add(clsname):
    cls = unreal.load_class(None, "/Script/PCG." + clsname)
    node, st = g.add_node_of_type(cls)
    return node, st


def set_mesh(sset, mesh_path):
    sel = sset.get_editor_property("mesh_selector_parameters")
    entry = unreal.PCGMeshSelectorWeightedEntry()
    desc = entry.get_editor_property("descriptor")
    desc.set_editor_property("static_mesh", unreal.load_asset(mesh_path))
    entry.set_editor_property("weight", 1.0)
    sel.set_editor_property("mesh_entries", [entry])
    sset.set_editor_property("synchronous_load", True)
    return len(sel.get_editor_property("mesh_entries"))


def build(key, extents, cell, mesh, scale_min, scale_max, off_min, off_max,
          expected):
    gn, gs = add("PCGCreatePointsGridSettings")
    tn, ts = add("PCGTransformPointsSettings")
    sn, ss = add("PCGStaticMeshSpawnerSettings")

    gs.set_editor_property("grid_extents", unreal.Vector(*extents))
    gs.set_editor_property("cell_size", unreal.Vector(*cell))
    gs.set_editor_property("set_points_bounds", True)
    gs.set_editor_property("cull_points_outside_volume", False)
    gs.set_editor_property("coordinate_space", unreal.PCGCoordinateSpace.LOCAL_COMPONENT)
    gs.set_editor_property("point_position", unreal.PCGPointPosition.CELL_CENTER)

    ts.set_editor_property("offset_min", unreal.Vector(*off_min))
    ts.set_editor_property("offset_max", unreal.Vector(*off_max))
    ts.set_editor_property("absolute_offset", False)
    ts.set_editor_property("rotation_min", unreal.Rotator(0, 0, 0))
    ts.set_editor_property("rotation_max", unreal.Rotator(0, 0, 0))
    ts.set_editor_property("absolute_rotation", True)
    ts.set_editor_property("scale_min", unreal.Vector(*scale_min))
    ts.set_editor_property("scale_max", unreal.Vector(*scale_max))
    ts.set_editor_property("absolute_scale", True)
    ts.set_editor_property("uniform_scale", False)
    ts.set_editor_property("recompute_seed", False)

    entries = set_mesh(ss, mesh)

    info = {
        "key": key,
        "expected_points": expected,
        "mesh_entries": entries,
        "readback": {
            "grid_extents": S(gs.get_editor_property("grid_extents")),
            "cell_size": S(gs.get_editor_property("cell_size")),
            "coordinate_space": S(gs.get_editor_property("coordinate_space")),
            "uniform_scale": S(ts.get_editor_property("uniform_scale")),
            "absolute_scale": S(ts.get_editor_property("absolute_scale")),
            "absolute_rotation": S(ts.get_editor_property("absolute_rotation")),
            "scale_min": S(ts.get_editor_property("scale_min")),
            "scale_max": S(ts.get_editor_property("scale_max")),
            "offset_min": S(ts.get_editor_property("offset_min")),
            "offset_max": S(ts.get_editor_property("offset_max")),
            "synchronous_load": S(ss.get_editor_property("synchronous_load")),
        },
        "edges": {},
    }
    return (gn, gs, tn, ts, sn, ss), info


CLUSTERS = [
    # key,       extents,             cell,                mesh,          scale_min,        scale_max,       off_min,      off_max,     expected
    ("ground",   (50, 50, 50),        (100, 100, 100),     "Plane.Plane", (66, 66, 1),      (66, 66, 1),     (0, 0, 0),    (0, 0, 0),   1),
    ("roadsX",   (50, 2000, 50),      (100, 2000, 100),    "Cube.Cube",   (60, 6, 0.2),     (60, 6, 0.2),    (0, 0, 10),   (0, 0, 10),  2),
    ("roadsY",   (2000, 50, 50),      (2000, 100, 100),    "Cube.Cube",   (6, 60, 0.2),     (6, 60, 0.2),    (0, 0, 10),   (0, 0, 10),  2),
    ("buildings", (3000, 3000, 50),   (1000, 1000, 100),   "Cube.Cube",   (6, 6, 6),        (6, 6, 26),      (0, 0, 300),  (0, 0, 300), 36),
]

R["clusters"] = []
built = []
for (key, ext, cell, mesh, smin, smax, omin, omax, exp) in CLUSTERS:
    nodes, info = build(key, ext, cell, "/Engine/BasicShapes/" + mesh,
                        smin, smax, omin, omax, exp)
    built.append((key, nodes))
    R["clusters"].append(info)
R["expected_total_points"] = sum(c["expected_points"] for c in R["clusters"])

# ---- wire, verifying every edge ----
def wire(label, from_node, from_pin, to_node, to_pin, container):
    before = len(g.get_all_edges())
    g.add_edge(from_node, from_pin, to_node, to_pin)
    after = len(g.get_all_edges())
    ok = after > before
    container["%s: %s -> %s" % (label, from_pin, to_pin)] = (
        "edge_created" if ok else "SILENT FAIL (edges %d -> %d)" % (before, after))
    return ok

all_ok = True
for key, (gn, gs, tn, ts, sn, ss) in built:
    ok1 = wire(key, gn, "Out", tn, "In", R["clusters"][[c["key"] for c in R["clusters"]].index(key)]["edges"])
    ok2 = wire(key, tn, "Out", sn, "In", R["clusters"][[c["key"] for c in R["clusters"]].index(key)]["edges"])
    ok3 = wire(key, sn, "Out", out_node, "Out", R["clusters"][[c["key"] for c in R["clusters"]].index(key)]["edges"])
    all_ok = all_ok and ok1 and ok2 and ok3

R["all_edges_ok"] = all_ok
R["node_count"] = len(g.get_editor_property("nodes"))
R["edge_count"] = len(g.get_all_edges())
R["expected_edge_count"] = len(CLUSTERS) * 3

# ---- independent check: read each node's pins and ask is_connected ----
pl = {}
try:
    for key, (gn, gs, tn, ts, sn, ss) in built:
        bits = []
        for nm, nd in (("grid", gn), ("tp", tn), ("spawn", sn)):
            for direction in ("output_pins", "input_pins"):
                for p in nd.get_editor_property(direction):
                    try:
                        lab = S(p.get_editor_property("properties").get_editor_property("label"))
                        con = S(p.get_editor_property("is_connected"))
                    except Exception:
                        continue
                    if direction == "output_pins" or lab in ("In", "Out", "PrimaryInput"):
                        bits.append("%s.%s[%s]=%s" % (nm, direction[:3], lab, con))
        pl[key] = bits
except Exception as e:
    pl["err"] = "%s: %s" % (type(e).__name__, S(e)[:200])
R["pin_connections"] = pl

try:
    R["saved"] = unreal.EditorAssetLibrary.save_asset(GRAPH_PATH)
except Exception as e:
    R["saved"] = "ERR %s" % S(e)[:150]

print("step2: nodes=%d edges=%d (expected %d) all_ok=%s saved=%s" % (
    R["node_count"], R["edge_count"], R["expected_edge_count"], all_ok, R["saved"]))
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
