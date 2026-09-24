# pcg_sa_convprobe.py — measure the spline world<->local conversion instead of
# reasoning about it. Two rewrites of pcg_sa_shape.py failed on the same +/-1921 cm
# error because I predicted what `set_location_at_spline_point(..., WORLD)` does.
# This pins it down from four readings of one point.
#
# It deliberately mutates one spline point and one actor location on the derived
# level. That level is reset from the template afterwards, so the mutation is
# throwaway — but it is a mutation, not a read-only probe.
#
# Readings, for CityShape's point 0:
#   before            local, world, actor loc
#   after move +1000x local, world, actor loc
#   after setting world to a known value   local, world
#   after move +2000x                      local, world
#
# From those four the storage rule is unambiguous:
#   if local is unchanged by a move and world moves by the delta, then
#   world = T * local and writing WORLD stores inverse(T) * world.
# The last two readings show what happens when T changes AFTER a WORLD write,
# which is the case that keeps biting.

import gc
import json

TARGET = "/Game/PCGArea/L_SmallArea18"


def vec(v):
    return [round(float(v.x), 4), round(float(v.y), 4), round(float(v.z), 4)]


def main():
    import unreal

    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    WORLD = unreal.SplineCoordinateSpace.WORLD
    LOCAL = unreal.SplineCoordinateSpace.LOCAL

    cur = str(les.get_current_level())
    if TARGET.split("/")[-1] not in cur:
        return {"abort": "not on %s (current: %s)" % (TARGET, cur)}

    actor = None
    for a in eas.get_all_level_actors():
        try:
            tags = [str(t) for t in a.get_editor_property("tags")]
        except Exception:
            tags = []
        if "City" in tags and a.get_components_by_class(unreal.SplineComponent):
            actor = a
            break
    if actor is None:
        return {"abort": "no spline actor tagged City"}

    sc = actor.get_components_by_class(unreal.SplineComponent)[0]
    out = {"actor": str(actor.get_actor_label())}

    # component transform, to confirm rotation 1 / scale 1
    try:
        t = sc.get_world_transform()
        tr = t.translation
        s = t.scale3d
        r = t.rotation
        out["comp_world_transform"] = {
            "translation": [round(float(tr.x), 3), round(float(tr.y), 3), round(float(tr.z), 3)],
            "scale3d": [round(float(s.x), 6), round(float(s.y), 6), round(float(s.z), 6)],
            "quat": [round(float(r.x), 6), round(float(r.y), 6),
                     round(float(r.z), 6), round(float(r.w), 6)],
        }
    except Exception as ex:
        out["comp_world_transform"] = "ERR " + str(ex)[:120]

    def snap(tag):
        return {
            tag + "_actor_loc": vec(actor.get_actor_location()),
            tag + "_p0_local": vec(sc.get_location_at_spline_point(0, LOCAL)),
            tag + "_p0_world": vec(sc.get_location_at_spline_point(0, WORLD)),
        }

    out.update(snap("before"))

    base = actor.get_actor_location()
    # --- move 1: +1000 on X ---
    actor.set_actor_location(unreal.Vector(base.x + 1000.0, base.y, base.z), False, False)
    out.update(snap("after_move1"))
    out["move1_delta"] = [1000.0, 0.0, 0.0]

    # --- write a known WORLD value ---
    target_world = [12345.0, 6789.0, 0.0]
    sc.set_location_at_spline_point(
        0, unreal.Vector(target_world[0], target_world[1], target_world[2]), WORLD, False)
    out["wrote_world"] = target_world
    out.update(snap("after_world_write"))
    out["write_error"] = [round(out["after_world_write_p0_world"][i] - target_world[i], 4)
                          for i in range(3)]

    # --- move 2: another +1000 on X, WITHOUT touching the point ---
    actor.set_actor_location(unreal.Vector(base.x + 2000.0, base.y, base.z), False, False)
    out.update(snap("after_move2"))
    out["point_shifted_by_move2"] = [
        round(out["after_move2_p0_world"][i] - out["after_world_write_p0_world"][i], 4)
        for i in range(3)]

    # --- equivalence test: scale local vs write world ---
    # local_before_scaled = scale * local_before, with the actor at its moved
    # position, must equal the transform of the original world point.
    out["hypothesis_local_scaling"] = {
        "local_before": out["before_p0_local"],
        "note": "local is what a point stores; if world = T * local then scaling local "
                "by s and moving T by the similarity reproduces the transform exactly",
    }
    return out


try:
    RESULT = {"ok": True, "data": main()}
except Exception as exc:
    RESULT = {"ok": False, "error": "%s: %s" % (type(exc).__name__, str(exc)[:300])}

try:
    mcp_result = json.loads(json.dumps(RESULT, default=str))
except Exception as se:
    mcp_result = {"ok": False, "serialization_failed": str(se)[:200]}

print(json.dumps(mcp_result, ensure_ascii=False, default=str))
del RESULT
gc.collect()
