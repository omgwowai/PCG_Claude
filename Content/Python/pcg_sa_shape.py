# Content/Python/pcg_sa_shape.py
# Task B: shrink the copied city with ONE similarity transform.
#
# args: {"target_cm": 60000,          # the city's longer horizontal side
#        "dst_center": null,          # null = keep the source centre (stay on terrain)
#        "dry_run": false}            # true = report the plan, change nothing
#
# WHAT MOVES: every SplineComponent's points (19 actors carry them, including 3
# PCGVolumes whose subdivision splines live on the volume itself), every
# CineCameraActor's location, and every PCGVolume's location.
#
# WHAT DOES NOT MOVE: lights, fog, sky, the water plane, the MeshPartition terrain
# actor (stage 1 reshapes it from the new CityShape), and the 200 cm brushes. The
# brushes are deliberately left alone: they are absolute 20 m generation bounds and
# a UObject similarity would scale their C++ collision-box representation, not their
# render geometry.
#
# THE CONVERSION RULE, MEASURED (Content/Python/pcg_sa_convprobe.py, 2026-09-24), with
# the component at identity rotation and scale 1:
#
#   world = local + actor_location          (so `local` is invariant when the actor moves)
#   set_location_at_spline_point(p, WORLD)  stores local = p - actor_location
#   a point written to WORLD is exact on read-back (write_error was [0,0,0])
#   moving the actor AFTER a write shifts that point's world by the delta
#
# Three earlier versions of this file got it wrong, all from reading world coordinates
# off an actor that had already been moved:
#   v1 (the plan's): move the actor, then read/write world points -> every point carried
#       the actor's displacement through the map, error = s * (L1 - L0).
#   v2: never move the spline actors -> never executed.
#   v3: all moves first, then all world writes, deduped -> same error as v1, for the same
#       reason: the reads happened after the moves.
# Measured error for CityShape was (-1921.2, 1401.6) cm, which equals
# 0.2816816 * (-6820.516, 4975.783) to 0.1 cm.
#
# v4 IS THEREFORE THREE PASSES IN THIS ORDER:
#   PASS 0  snapshot every spline's world points, before anything moves
#   PASS 1  move every actor's location exactly once (deduped by path, so the three
#           spline-carrying volumes cannot be moved twice)
#   PASS 2  write the mapped world points, with every transform already final
# Reading before moving and writing after moving is what the measured rule requires; any
# other order reintroduces the displacement.
#
# Point types and tangents are preserved by editing per point and scaling the tangents,
# rather than calling SetSplinePoints (which sets CurveAuto and discards custom tangents).
#
# OUTPUT IS DELIBERATELY SMALL: counts, the centre/size block, and the verify block. The
# earlier versions returned 45 actor records per call, which floods the session context.
#
# GLOBAL DISCIPLINE: no UObject survives this script.

import gc
import json

TARGET_CM = 60000.0
TARGET = "/Game/PCGArea/L_SmallArea18"

BASE_SPLINE_ACTORS = 19
BASE_SPLINE_COMPONENTS = 85
BASE_SPLINE_POINTS = 453


def vec(v):
    return [round(float(v.x), 3), round(float(v.y), 3), round(float(v.z), 3)]


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


def key_of(a):
    """Stable identity for de-duplication; labels are not guaranteed unique."""
    try:
        return str(a.get_path_name())
    except Exception:
        return str(a.get_actor_label())


def run(target_cm, dst_center, dry_run):
    import unreal
    import sys

    cdir = unreal.Paths.project_content_dir() + "Python"
    if cdir not in sys.path:
        sys.path.insert(0, cdir)
    import pcg_sa_geom as G

    out = {"dry_run": bool(dry_run), "target_cm": float(target_cm)}
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    out["current_level"] = str(les.get_current_level())
    if TARGET.split("/")[-1] not in out["current_level"]:
        out["abort"] = "not on the derived level; open %s first" % TARGET
        return out

    # ---- collect ----
    spline_actors, volumes, cameras = [], [], []
    for a in eas.get_all_level_actors():
        cn = a.get_class().get_name()
        if cn == "CineCameraActor":
            cameras.append(a)
        if cn == "PCGVolume":
            volumes.append(a)
        if a.get_components_by_class(unreal.SplineComponent):
            spline_actors.append(a)

    # ---- PASS 0: snapshot world points, before anything moves ----
    # This is the pass the earlier versions were missing. Reading after the moves is
    # what corrupted the transform.
    snapshot = []
    for a in spline_actors:
        comps = []
        for sc in a.get_components_by_class(unreal.SplineComponent):
            n = int(sc.get_number_of_spline_points())
            pts, tans = [], []
            for i in range(n):
                p = sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD)
                pts.append([float(p.x), float(p.y), float(p.z)])
                try:
                    t = sc.get_tangent_at_spline_point(
                        i, unreal.SplineCoordinateSpace.WORLD)
                    tans.append([float(t.x), float(t.y), float(t.z)])
                except Exception:
                    tans.append(None)
            comps.append({"n": n, "closed": bool(sc.is_closed_loop()),
                          "points": pts, "tangents": tans})
        snapshot.append({"actor": a, "comps": comps})

    city_pts = []
    for a in spline_actors:
        try:
            tags = [str(t) for t in a.get_editor_property("tags")]
        except Exception:
            tags = []
        if "City" not in tags:
            continue
        for sc in a.get_components_by_class(unreal.SplineComponent):
            n = int(sc.get_number_of_spline_points())
            for i in range(n):
                p = sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD)
                city_pts.append([float(p.x), float(p.y), float(p.z)])
    if not city_pts:
        out["abort"] = "no spline tagged 'City' found; cannot derive the source bbox"
        return out

    mn, mx = G.bbox_of_points(city_pts)
    src_center = [(mn[i] + mx[i]) / 2.0 for i in range(3)]
    scale = G.scale_for_target((mn, mx), float(target_cm))
    dst = [float(v) for v in dst_center] if dst_center else list(src_center)

    out["scale"] = scale
    out["src_center"] = [round(v, 3) for v in src_center]
    out["dst_center"] = [round(v, 3) for v in dst]
    out["city_size_before_m"] = [round((mx[0] - mn[0]) / 100.0, 1),
                                 round((mx[1] - mn[1]) / 100.0, 1)]
    out["city_size_after_m"] = [round((mx[0] - mn[0]) * scale / 100.0, 1),
                                round((mx[1] - mn[1]) * scale / 100.0, 1)]

    # ---- PASS 1: move every actor's location exactly once ----
    movers = {}
    for a in spline_actors + volumes + cameras:
        movers[key_of(a)] = a
    moved = 0
    for k, a in movers.items():
        loc = a.get_actor_location()
        nl = G.map_point([loc.x, loc.y, loc.z], scale, src_center, dst)
        if not dry_run:
            a.set_actor_location(unreal.Vector(nl[0], nl[1], nl[2]), False, False)
        moved += 1
    out["movers"] = moved

    # ---- PASS 2: write the mapped world points, transforms now final ----
    written = 0
    for entry in snapshot:
        if dry_run:
            continue
        a = entry["actor"]
        for sc, comp in zip(a.get_components_by_class(unreal.SplineComponent),
                            entry["comps"]):
            for i, p in enumerate(comp["points"]):
                np_ = G.map_point(p, scale, src_center, dst)
                sc.set_location_at_spline_point(
                    i, unreal.Vector(np_[0], np_[1], np_[2]),
                    unreal.SplineCoordinateSpace.WORLD, False)
                t = comp["tangents"][i]
                if t is not None:
                    nt = G.map_tangent(t, scale)
                    sc.set_tangent_at_spline_point(
                        i, unreal.Vector(nt[0], nt[1], nt[2]),
                        unreal.SplineCoordinateSpace.WORLD, False)
                written += 1
            sc.update_spline()
    out["points_written"] = written

    counts = {"actors": len(snapshot),
              "components": sum(len(e["comps"]) for e in snapshot),
              "points": sum(c["n"] for e in snapshot for c in e["comps"])}
    out["counts"] = counts
    out["baseline_ok"] = (counts["actors"] == BASE_SPLINE_ACTORS
                          and counts["components"] == BASE_SPLINE_COMPONENTS
                          and counts["points"] == BASE_SPLINE_POINTS)
    out["cameras"] = len(cameras)
    out["volumes"] = len(volumes)

    # ---- PASS 3: read back where the city actually IS ----
    pts2 = []
    for a in spline_actors:
        try:
            tags = [str(t) for t in a.get_editor_property("tags")]
        except Exception:
            tags = []
        if "City" not in tags:
            continue
        for sc in a.get_components_by_class(unreal.SplineComponent):
            n = int(sc.get_number_of_spline_points())
            for i in range(n):
                p = sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD)
                pts2.append([float(p.x), float(p.y), float(p.z)])
    if pts2:
        mn2, mx2 = G.bbox_of_points(pts2)
        c2 = [(mn2[i] + mx2[i]) / 2.0 for i in range(3)]
        size2 = [round((mx2[0] - mn2[0]) / 100.0, 1),
                 round((mx2[1] - mn2[1]) / 100.0, 1)]
        expect = out["city_size_before_m"] if dry_run else out["city_size_after_m"]
        out["verify"] = {
            "mode": "dry_run (must be unchanged)" if dry_run else "applied",
            "center_after": [round(v, 1) for v in c2],
            "center_expected": [round(v, 1) for v in dst],
            "center_delta": [round(c2[i] - dst[i], 1) for i in range(3)],
            "size_after_m": size2,
            "size_expected_m": expect,
            "center_ok": all(abs(c2[i] - dst[i]) < 200.0 for i in range(3)),
            "size_ok": abs(size2[0] - expect[0]) < 6.0,
        }
    return out


try:
    _args = mcp_args if isinstance(mcp_args, dict) else {}
except NameError:
    _args = {}

try:
    _dropped = purge_uobject_globals()
    RESULT = {"ok": True, "dropped_globals": _dropped,
              "data": run(_args.get("target_cm", TARGET_CM),
                          _args.get("dst_center", None),
                          bool(_args.get("dry_run", False)))}
except Exception as _exc:
    RESULT = {"ok": False, "error": "%s: %s" % (type(_exc).__name__, str(_exc)[:400])}

try:
    mcp_result = json.loads(json.dumps(RESULT, default=str))
except Exception as _se:
    mcp_result = {"ok": False, "serialization_failed": str(_se)[:200]}

print(json.dumps(mcp_result, ensure_ascii=False, default=str)[:200000])
del RESULT, _args
gc.collect()
