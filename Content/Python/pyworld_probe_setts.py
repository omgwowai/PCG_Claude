# pyworld_probe_setts.py -- READ-ONLY: the setts (W6's street pavers) near a point against the ground under them:
# for each instance of {"mesh": name} (default the street pavers) within `radius` of {"at": [x, y]}, its top (the
# mesh's own top, scaled, over its pivot) and the ground traced at its centre with W6's actor ignored. Prints JSON.
import json
import math

import unreal

args = globals().get("mcp_args") or {}
X, Y = args.get("at", [24934.0, -30104.0])
R = float(args.get("radius", 1500.0))
MESH = args.get("mesh", "SM_Plaza_Square_E")
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
w6 = next(a for a in eas.get_all_level_actors() if "PyWorld_W06" in [str(t) for t in a.get_editor_property("tags")])
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def ground(x, y):
    res = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, 500000.0), unreal.Vector(x, y, -500000.0),
                                                 unreal.TraceTypeQuery.ECC_VISIBILITY, True, [w6],
                                                 unreal.DrawDebugTrace.NONE, True)
    hit = res[-1] if isinstance(res, tuple) else res
    parts = hit.to_tuple() if hit is not None else None
    return (float(parts[4].z), str(parts[9].get_name()) if parts[9] else None) if parts and parts[0] else (None, None)


out, bounds = [], None
for c in w6.get_components_by_class(unreal.InstancedStaticMeshComponent):
    sm = c.get_editor_property("static_mesh")
    if sm is None or sm.get_name() != MESH:
        continue
    b = sm.get_bounding_box()
    bounds = [[round(b.min.x, 1), round(b.min.y, 1), round(b.min.z, 1)], [round(b.max.x, 1), round(b.max.y, 1), round(b.max.z, 1)]]
    for i in range(c.get_instance_count()):
        t = c.get_instance_transform(i, True)
        p = t.translation
        if math.hypot(p.x - X, p.y - Y) > R:
            continue
        r = t.rotation.rotator()
        # the slab's top at its centre, and the worst of a 3 x 3 grid over its top (corners, edge middles, centre)
        cx = t.transform_location(unreal.Vector(0.5 * (b.min.x + b.max.x), 0.5 * (b.min.y + b.max.y), b.max.z))
        g, what = ground(cx.x, cx.y)
        worst = None
        for fx in (0.02, 0.5, 0.98):
            for fy in (0.02, 0.5, 0.98):
                q = t.transform_location(unreal.Vector(b.min.x + fx * (b.max.x - b.min.x), b.min.y + fy * (b.max.y - b.min.y), b.max.z))
                gq, _w = ground(q.x, q.y)
                if gq is not None and (worst is None or gq - q.z > worst):
                    worst = gq - q.z
        out.append({"pivot": [round(p.x), round(p.y), round(p.z)], "rot": [round(r.pitch, 1), round(r.yaw, 1), round(r.roll, 1)],
                    "scale": [round(t.scale3d.x, 2), round(t.scale3d.y, 2), round(t.scale3d.z, 2)],
                    "top_centre": round(cx.z, 1), "ground": None if g is None else round(g, 1), "hit": what,
                    "grid_ground_over_top": None if worst is None else round(worst, 1)})
over = [d["ground"] - d["top_centre"] for d in out if d["ground"] is not None]
grid = [d["grid_ground_over_top"] for d in out if d["grid_ground_over_top"] is not None]
print(json.dumps({"mesh": MESH, "bounds": bounds, "n": len(out),
                  "ground_over_top_max": round(max(over), 1) if over else None,
                  "ground_over_top_n_over_2cm": sum(1 for v in over if v > 2.0),
                  "grid_over_top_max": round(max(grid), 1) if grid else None,
                  "grid_n_over_5cm": sum(1 for v in grid if v > 5.0),
                  "sample": sorted(out, key=lambda d: -(d["grid_ground_over_top"] or -1e9))[:6]}))
