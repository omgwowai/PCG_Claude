# tl_probe_roof_clearance.py -- READ-ONLY. For every spline building in
# /Game/Map/Lvl_TL_Spline, how close each rooftop assembly instance comes to
# the facade line, in plan. The roof deck is inset ROOF_INSET_CM from the
# facade line and the rooftop fill is fitted to that deck, while the parapet
# behind the facade is 30 cm of brick (34 cm under the L4 coping), so an
# assembly nearer than that to the facade line sits in the parapet.
# Args: {"wall_cm": 34.0}
import json
import math

args = mcp_args or {}
LEVEL = "/Game/Map/Lvl_TL_Spline."
WALL_CM = float(args.get("wall_cm", 34.0))
ROOFTOP_PREFIXES = ("SM_roof_", "SM_Constrash", "SM_Plane_NN")


def inside_distance(poly, x, y):
    """Distance of (x, y) to the nearest polygon edge segment, positive inside
    and negative outside (even-odd test, so concave footprints work)."""
    n = len(poly)
    best = 1e18
    inside = False
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
        if (ay > y) != (by > y) and x < ax + (y - ay) * dx / dy:
            inside = not inside
    return best if inside else -best


def main():
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not w.get_path_name().startswith(LEVEL):
        return {"error": "current world is %s" % w.get_path_name()}
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    R = {"wall_cm": WALL_CM, "buildings": {}}
    for a in eas.get_all_level_actors():
        if not a.get_actor_label().startswith("TL_"):
            continue
        sc = a.get_component_by_class(unreal.SplineComponent)
        if sc is None:
            continue
        poly = []
        for i in range(sc.get_number_of_spline_points()):
            p = sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD)
            poly.append((p.x, p.y))
        worst = None
        n_inst = 0
        n_in_wall = 0
        per_mesh = {}
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            if sm is None or not sm.get_name().startswith(ROOFTOP_PREFIXES):
                continue
            if sm.get_name().startswith("SM_Plane_NN"):
                continue        # the deck's own plane, not an assembly
            bb = sm.get_bounding_box()
            lo, hi = bb.min, bb.max
            corners = [unreal.Vector(x, y, lo.z) for x in (lo.x, hi.x) for y in (lo.y, hi.y)]
            for k in range(c.get_instance_count()):
                t = c.get_instance_transform(k, True)
                d = min(inside_distance(poly, q.x, q.y)
                        for q in (t.transform_location(v) for v in corners))
                n_inst += 1
                if d < WALL_CM:
                    n_in_wall += 1
                    per_mesh[sm.get_name()] = per_mesh.get(sm.get_name(), 0) + 1
                if worst is None or d < worst[0]:
                    worst = (round(d, 2), sm.get_name())
        R["buildings"][a.get_actor_label()] = {
            "rooftop_instances": n_inst, "closest_to_facade_cm": worst,
            "instances_within_wall": n_in_wall, "by_mesh": per_mesh}
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
