# pyinterior_live_probe.py -- probe: does a notified edit of a house's footprint spline (what dragging a point in the
# viewport sends on mouse release) make its PCG component regenerate by itself? Moves the outline of floor {"floor": k}
# (0 the ground; the spline whose height reads as that floor) to {"points": [[x, y], ...]} (local cm) without calling
# generate, then re-sets the spline curves with ALWAYS notification. {"add": true} first adds a new spline component (what
# the Details panel's Add does) and lifts it to floor k -- does a house pick up a floor drawn that way by itself? Read the
# log for the house's next run; restore with pyinterior.py shape. Measured 2026-10-28: with Regenerate In Editor on, the
# house re-ran by itself on the new outline (12 x 8 m -> ThreeBed 96 m2), no cache flush needed (traps 114-116).
import math

args = mcp_args or {}
name = args.get("house", "House_03_TwoBed")
k = int(args.get("floor", 0))
H = 300.0                                                     # WallHeight 270 + the 30 cm slab (storeys.floor_height)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
a = next(x for x in eas.get_all_level_actors() if str(x.get_actor_label()) == name)
pc = a.get_component_by_class(unreal.PCGComponent)
loc, yaw = a.get_actor_location(), math.radians(a.get_actor_rotation().yaw)
R = {"regenerate_in_editor": bool(pc.get_editor_property("regenerate_in_editor"))}


def floor_of(sc):
    n = sc.get_number_of_spline_points()
    z = sum(sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD).z for i in range(n)) / max(n, 1)
    return int(round((z - loc.z) / H))


if args.get("add"):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = sds.k2_gather_subobject_data_for_instance(a)
    res = sds.add_new_subobject(unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=unreal.SplineComponent,
                                                             blueprint_context=None))
    data = unreal.SubobjectDataBlueprintFunctionLibrary.get_data(res[0] if isinstance(res, tuple) else res)
    sc = unreal.SubobjectDataBlueprintFunctionLibrary.get_object(data)
    R["added"] = sc.get_class().get_name()
else:
    sc = next(s for s in a.get_components_by_class(unreal.SplineComponent) if floor_of(s) == k)
ex, ey = (-math.sin(yaw), math.cos(yaw)), (-math.cos(yaw), -math.sin(yaw))
pts = [unreal.Vector(loc.x + x * ex[0] + y * ey[0], loc.y + x * ex[1] + y * ey[1], loc.z + k * H) for x, y in args["points"]]
sc.set_spline_points(pts, unreal.SplineCoordinateSpace.WORLD, False)
for i in range(len(pts)):
    sc.set_spline_point_type(i, unreal.SplinePointType.LINEAR, False)
sc.set_closed_loop(True, False)
sc.update_spline()
R["floor"] = floor_of(sc)
R["splines"] = sorted(floor_of(s) for s in a.get_components_by_class(unreal.SplineComponent))
try:
    a.modify()
    sc.modify()
    # re-setting the same value notifies only with ALWAYS (DEFAULT notifies on an actual change)
    sc.set_editor_property("spline_curves", sc.get_editor_property("spline_curves"),
                           unreal.PropertyAccessChangeNotifyMode.ALWAYS)
    R["notified"] = True
except Exception as ex:
    R["notified"] = "%s: %s" % (type(ex).__name__, str(ex)[:300])
mcp_result = R
