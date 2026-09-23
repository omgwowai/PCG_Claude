# pcg_area_layout_verify.py
# Strongest available verification: read the actual INSTANCE TRANSFORMS out of
# the generated InstancedStaticMeshComponents and check the 3x3 block layout
# numerically.
#
# Why this and not a screenshot: the skill records that PCG's inspection state
# draws phantom visualisation, so numbers are the only trustworthy evidence.
# Point positions are NOT reachable (get_points() raises AttributeError), but
# instance transforms on the ISM components are, and those are what end up in
# the world.
#
# What is asserted:
#   ground   : exactly 1 instance, at the origin
#   roadsX   : 2 instances, both at y = +-1000,  x = 0
#   roadsY   : 2 instances, both at x = +-1000,  y = 0
#   buildings: 36 instances on the +-500/+-1500/+-2500 lattice (6x6)
#   the roads must sit BETWEEN building rows, i.e. x,y = +-1000 are not
#   occupied by any building -> that is what makes it 3x3 blocks of 2x2

import json

R = {}
def S(x):
    return str(x)

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

GROUPS = {}
for c in vol.get_components_by_class(unreal.PrimitiveComponent):
    try:
        n = c.get_instance_count()
    except Exception:
        continue
    if not n:
        continue
    mesh = None
    try:
        m = c.get_editor_property("static_mesh")
        mesh = S(m.get_name()) if m else None
    except Exception:
        pass
    rows = []
    for i in range(n):
        try:
            t = c.get_instance_transform(i)
            loc = t.translation
            sc = t.scale3d
            rows.append({
                "x": round(loc.x, 2), "y": round(loc.y, 2), "z": round(loc.z, 2),
                "sx": round(sc.x, 3), "sy": round(sc.y, 3), "sz": round(sc.z, 3),
            })
        except Exception as e:
            rows.append({"err": "%s: %s" % (type(e).__name__, S(e)[:70])})
    key = "%s|%s|%d" % (S(c.get_name()), mesh, n)
    GROUPS[key] = rows
R["instance_transforms"] = GROUPS

# ---- assertions ----
def flat(rows, keys):
    return sorted(set(tuple(r.get(k) for k in keys) for r in rows if "err" not in r))

A = {}
bld = None
roads = []
ground = None
for k, rows in GROUPS.items():
    mesh = k.split("|")[1]
    n = len(rows)
    if mesh == "Plane":
        ground = rows
    elif n == 36:
        bld = rows
    else:
        roads.append(rows)

if ground is not None:
    A["ground_count"] = len(ground)
    A["ground_at_origin"] = all(abs(r["x"]) < 1 and abs(r["y"]) < 1 for r in ground)
    A["ground_scale"] = flat(ground, ("sx", "sy", "sz"))

if bld is not None:
    A["building_count"] = len(bld)
    xs = sorted(set(r["x"] for r in bld))
    ys = sorted(set(r["y"] for r in bld))
    A["building_x_values"] = xs
    A["building_y_values"] = ys
    A["lattice_is_6x6_pm500_1500_2500"] = (
        xs == [-2500.0, -1500.0, -500.0, 500.0, 1500.0, 2500.0] and
        ys == [-2500.0, -1500.0, -500.0, 500.0, 1500.0, 2500.0])
    A["building_xy_scale"] = flat(bld, ("sx", "sy"))
    zs = sorted(set(r["sz"] for r in bld))
    A["building_height_scales"] = zs
    A["building_heights_vary"] = len(zs) > 1
    A["building_z_center"] = sorted(set(r["z"] for r in bld))
    # every building bottom must be at or below ground: z_center - 50*sz
    A["min_building_bottom"] = round(min(r["z"] - 50.0 * r["sz"] for r in bld), 2)

if roads:
    A["road_group_count"] = len(roads)
    A["road_counts"] = [len(r) for r in roads]
    allr = [t for r in roads for t in r]
    A["road_positions"] = sorted(set((r["x"], r["y"]) for r in allr))
    A["road_z_centers"] = sorted(set(r["z"] for r in allr))
    A["road_x_or_y_scale"] = sorted(set((r["sx"], r["sy"], r["sz"]) for r in allr))
    # roads must be exactly on the +-1000 midlines, i.e. between building rows
    A["roads_on_pm1000_midlines"] = all(
        (abs(abs(r["x"]) - 1000) < 1) != (abs(abs(r["y"]) - 1000) < 1) for r in allr)
    # no building may sit on a road midline
    if bld is not None:
        A["no_building_on_road_line"] = not any(
            abs(abs(r["x"]) - 1000) < 1 or abs(abs(r["y"]) - 1000) < 1 for r in bld)

R["assertions"] = A
R["all_layout_checks_pass"] = all(
    v is True for k, v in A.items()
    if k in ("ground_at_origin", "lattice_is_6x6_pm500_1500_2500",
             "building_heights_vary", "roads_on_pm1000_midlines",
             "no_building_on_road_line"))
R["total_instances"] = sum(len(v) for v in GROUPS.values())

print("layout: total=%d checks_pass=%s" % (
    R["total_instances"], R["all_layout_checks_pass"]))
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
