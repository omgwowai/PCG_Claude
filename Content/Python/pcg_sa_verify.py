# Content/Python/pcg_sa_verify.py
# Read-only. Assert the similarity transform actually landed, from the live spline
# components rather than from the transform's own report.
#
# args: {"target_cm": 60000, "tol_center": 200, "tol_size": 6}
#
# Why this exists as its own script: Task 3 Step 4 of the plan asks for an
# independent read-back, and the first apply's own `verify` block was wrong twice
# over (it compared a dry run against the predicted size, then it reported the
# double-apply as a centre error inside a report the transform itself produced).
# This one takes only the city's name to look for and the numbers to expect, and
# fails loudly if the geometry is not where it should be.
#
# The tolerance is 2 m on the centre: the CityShape spline is 453 hand-placed
# points across 19 actors, and the check is about the transform landing, not about
# sub-centimetre agreement.

import gc
import json

TARGET = "/Game/PCGArea/L_SmallArea18"

# Measured 2026-09-24 from the Task 2 inventory of the freshly copied level, i.e. the
# source state the transform starts from. The transform is a similarity about the
# city's own centre with dst == src, so this is where the centre must still be
# afterwards. Without this baseline there is nothing to check the centre against,
# which is how the first apply's 1921/1402 cm displacement got reported as an
# unexplained `center_ok: false` with no expected value beside it.
BASE_CITY_CENTER = [-9485.116, 6936.988, 0.0]
BASE_ASPECT = 1817.8 / 2130.1


def _holds_uobject(val, ue):
    if isinstance(val, (ue.Object, ue.StructBase)):
        return True
    if isinstance(val, (list, tuple, set)):
        return any(_holds_uobject(v, ue) for v in val)
    if isinstance(val, dict):
        return any(_holds_uobject(v, ue) for v in val.values())
    return False


def purge_uobject_globals():
    import unreal

    dropped = []
    for name, val in list(globals().items()):
        if name.startswith("__") or callable(val) or isinstance(val, type):
            continue
        try:
            if _holds_uobject(val, unreal):
                del globals()[name]
                dropped.append(name)
        except Exception:
            continue
    gc.collect()
    return dropped


def run(target_cm, tol_center, tol_size):
    import unreal
    import sys

    cdir = unreal.Paths.project_content_dir() + "Python"
    if cdir not in sys.path:
        sys.path.insert(0, cdir)
    import pcg_sa_geom as G

    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    cur = str(les.get_current_level())
    if TARGET.split("/")[-1] not in cur:
        return {"abort": "not on %s (current: %s)" % (TARGET, cur)}

    # CityShape points, and the per-actor picture the report needs.
    city_pts = []
    per_actor = []
    for a in eas.get_all_level_actors():
        comps = a.get_components_by_class(unreal.SplineComponent)
        if not comps:
            continue
        try:
            tags = [str(t) for t in a.get_editor_property("tags")]
        except Exception:
            tags = []
        pts = []
        for sc in comps:
            n = int(sc.get_number_of_spline_points())
            for i in range(n):
                p = sc.get_location_at_spline_point(
                    i, unreal.SplineCoordinateSpace.WORLD)
                pts.append([float(p.x), float(p.y), float(p.z)])
        lo = a.get_actor_location()
        per_actor.append({"label": str(a.get_actor_label()),
                          "components": len(comps), "points": len(pts),
                          "actor_loc": [round(float(lo.x), 1), round(float(lo.y), 1),
                                        round(float(lo.z), 1)],
                          "tags": tags})
        if "City" in tags:
            city_pts.extend(pts)

    if not city_pts:
        return {"abort": "no spline tagged 'City'"}

    mn, mx = G.bbox_of_points(city_pts)
    center = [(mn[i] + mx[i]) / 2.0 for i in range(3)]
    size_m = [round((mx[0] - mn[0]) / 100.0, 2), round((mx[1] - mn[1]) / 100.0, 2)]

    # The city was shrunk about ITS OWN centre with dst == src, so the expected
    # centre is the measured source centre and the expected long side is target_cm.
    long_side = max(size_m)
    out = {
        "city_points": len(city_pts),
        "city_bbox": [mn, mx],
        "city_center": [round(v, 1) for v in center],
        "city_center_expected": BASE_CITY_CENTER,
        "center_delta": [round(center[i] - BASE_CITY_CENTER[i], 1) for i in range(3)],
        "center_ok": all(abs(center[i] - BASE_CITY_CENTER[i]) <= tol_center
                         for i in range(2)),      # X/Y only: Z is a flat 0 plane
        "city_size_m": size_m,
        "expected_long_side_m": round(float(target_cm) / 100.0, 1),
        "long_side_ok": abs(long_side - float(target_cm) / 100.0) <= tol_size,
        "aspect_ok": abs((size_m[1] / size_m[0]) - BASE_ASPECT) < 0.05,
        "actors": sorted(per_actor, key=lambda e: e["label"]),
        "actors_with_splines": len(per_actor),
        "total_points": sum(e["points"] for e in per_actor),
        "total_components": sum(e["components"] for e in per_actor),
    }
    out["pass"] = bool(out["center_ok"] and out["long_side_ok"] and out["aspect_ok"]
                       and out["actors_with_splines"] == 19
                       and out["total_components"] == 85
                       and out["total_points"] == 453)
    return out


try:
    _args = mcp_args if isinstance(mcp_args, dict) else {}
except NameError:
    _args = {}

try:
    _dropped = purge_uobject_globals()
    RESULT = {"ok": True, "dropped_globals": _dropped,
              "data": run(_args.get("target_cm", 60000.0),
                          _args.get("tol_center", 200.0),
                          _args.get("tol_size", 6.0))}
except Exception as _exc:
    RESULT = {"ok": False, "error": "%s: %s" % (type(_exc).__name__, str(_exc)[:400])}

try:
    mcp_result = json.loads(json.dumps(RESULT, default=str))
except Exception as _se:
    mcp_result = {"ok": False, "serialization_failed": str(_se)[:200]}

print(json.dumps(mcp_result, ensure_ascii=False, default=str)[:200000])
del RESULT, _args
gc.collect()
