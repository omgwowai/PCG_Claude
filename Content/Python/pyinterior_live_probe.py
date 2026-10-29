# pyinterior_live_probe.py -- probe: does a notified edit of a house's footprint spline (what dragging a point in the
# viewport sends on mouse release) make its PCG component regenerate by itself? Moves the outline to {"points": [[x, y], ...]}
# (local cm) without calling generate, then re-sets the spline curves with ALWAYS notification. Read the log for the house's
# next run; restore the outline with pyinterior.py shape. Measured 2026-10-28: with Regenerate In Editor on, the house re-ran
# by itself on the new outline (12 x 8 m -> ThreeBed 96 m2), no cache flush needed (traps 114-116).
import math

args = mcp_args or {}
name = args.get("house", "House_03_TwoBed")
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
a = next(x for x in eas.get_all_level_actors() if str(x.get_actor_label()) == name)
sc = a.get_component_by_class(unreal.SplineComponent)
pc = a.get_component_by_class(unreal.PCGComponent)
loc, yaw = a.get_actor_location(), math.radians(a.get_actor_rotation().yaw)
ex, ey = (-math.sin(yaw), math.cos(yaw)), (-math.cos(yaw), -math.sin(yaw))
pts = [unreal.Vector(loc.x + x * ex[0] + y * ey[0], loc.y + x * ex[1] + y * ey[1], loc.z) for x, y in args["points"]]
sc.set_spline_points(pts, unreal.SplineCoordinateSpace.WORLD, False)
for i in range(len(pts)):
    sc.set_spline_point_type(i, unreal.SplinePointType.LINEAR, False)
sc.set_closed_loop(True, False)
sc.update_spline()
R = {"regenerate_in_editor": bool(pc.get_editor_property("regenerate_in_editor"))}
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
