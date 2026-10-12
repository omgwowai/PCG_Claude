# tl_probe_spline_counts.py -- READ-ONLY. Instances per mesh on TLPROBE_Spline.
# Task 9: also checks every corner-fan instance against corner_math.fan.
# Args: {"fans": true} adds the fan check (default true).
#
# The fan check reads the spawned ISM instances themselves (world transforms),
# not the graph's attributes, so it verifies what was actually placed:
#   - every fan instance sits on a footprint vertex (XY within 0.5 cm);
#   - per (storey z, vertex) group: the instance count equals len(fan(pts, i))
#     and the mesh kind (FanFront / FanBack) equals the model's kind;
#   - sorted per-instance yaw, sx, sy equal the model's slices
#     (yaw <= 0.01 deg, scale <= 1e-4, design doc A2);
#   - an identity rotation or unit scale where the model wants otherwise is a
#     failure by construction (it would not match).
import json
import math
import sys

sys.path.insert(0, "E:/PCG_Claude/Tools/tl_kit")
import importlib
import corner_math
importlib.reload(corner_math)

args = mcp_args or {}
LABEL = args.get("label", "TLPROBE_Spline")
VERT_TOL_CM = 0.5
YAW_TOL_DEG = 0.01
SCALE_TOL = 1e-4



def probe_actor():
    # looked up inside functions only: a module-level UObject would stay alive
    # in the bridge's persistent namespace and block later asset deletes.
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    return next(x for x in eas.get_all_level_actors() if x.get_actor_label() == LABEL)


def mesh_counts(a):
    out = {}
    for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm:
            out[sm.get_name()] = out.get(sm.get_name(), 0) + c.get_instance_count()
    return out


def level_of(mesh_name):
    # SM_BLDG_TL_L0<n>_A_...
    i = mesh_name.find("_L0")
    return int(mesh_name[i + 3]) if i >= 0 else -1


def fan_check(a):
    sc = a.get_component_by_class(unreal.SplineComponent)
    pts = corner_math.clean([sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD).to_tuple()[:2]
                             for i in range(sc.get_number_of_spline_points())])
    model = {i: corner_math.fan(pts, i) for i in range(len(pts))}
    inst = []
    for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if not sm or "_Fan" not in sm.get_name():
            continue
        kind = "front" if "FanFront" in sm.get_name() else "back"
        for k in range(c.get_instance_count()):
            t = c.get_instance_transform(k, True)
            r = t.rotation.rotator()
            inst.append({"mesh": sm.get_name(), "lv": level_of(sm.get_name()), "kind": kind,
                         "x": t.translation.x, "y": t.translation.y, "z": round(t.translation.z, 1),
                         "yaw": r.yaw, "pitch": r.pitch, "roll": r.roll,
                         "sx": t.scale3d.x, "sy": t.scale3d.y, "sz": t.scale3d.z})
    groups, off_vertex = {}, []
    for f in inst:
        vi = next((i for i, p in enumerate(pts)
                   if math.hypot(f["x"] - p[0], f["y"] - p[1]) <= VERT_TOL_CM), None)
        if vi is None:
            off_vertex.append(f)
            continue
        groups.setdefault((f["lv"], f["z"], vi), []).append(f)

    problems, rows = [], []
    for (lv, z, vi), fs in sorted(groups.items()):
        want = model[vi]
        got_yaw = sorted(corner_math.wrap(f["yaw"]) for f in fs)
        want_yaw = sorted(s["yaw"] for s in want)
        kinds = sorted({f["kind"] for f in fs})
        row = {"lv": lv, "z": z, "vertex": vi, "n_got": len(fs), "n_want": len(want),
               "kind_got": kinds, "kind_want": want[0]["kind"] if want else None}
        ok = len(fs) == len(want) and kinds == [want[0]["kind"]]
        if ok:
            dyaw = max(abs(corner_math.wrap(g - w)) for g, w in zip(got_yaw, want_yaw))
            dsx = max(abs(f["sx"] - want[0]["sx"]) for f in fs)
            dsy = max(abs(f["sy"] - want[0]["sy"]) for f in fs)
            dsz = max(abs(f["sz"] - 1.0) for f in fs)
            tilt = max(max(abs(f["pitch"]), abs(f["roll"])) for f in fs)
            row.update(max_dyaw=round(dyaw, 6), max_dsx=dsx, max_dsy=dsy, max_dsz=dsz, max_tilt=tilt,
                       yaw_got_first_last=[round(got_yaw[0], 4), round(got_yaw[-1], 4)],
                       yaw_want_first_last=[round(want_yaw[0], 4), round(want_yaw[-1], 4)])
            ok = dyaw <= YAW_TOL_DEG and dsx <= SCALE_TOL and dsy <= SCALE_TOL and dsz <= SCALE_TOL \
                and tilt <= YAW_TOL_DEG
        row["ok"] = ok
        rows.append(row)
        if not ok:
            problems.append(row)

    # every (storey, model vertex) that should have a fan has one
    storeys = sorted({(lv, z) for (lv, z, _) in groups})
    missing = [{"lv": lv, "z": z, "vertex": vi} for (lv, z) in storeys
               for vi, w in model.items() if w and (lv, z, vi) not in groups]
    per_level = {}
    for f in inst:
        d = per_level.setdefault(f["lv"], {"front": 0, "back": 0})
        d[f["kind"]] += 1
    storeys_per_level = {}
    for (lv, z) in storeys:
        storeys_per_level[lv] = storeys_per_level.get(lv, 0) + 1
    return {
        "n_fan_instances": len(inst),
        "per_level_front_back": {str(k): v for k, v in sorted(per_level.items())},
        "storeys_per_level": {str(k): v for k, v in sorted(storeys_per_level.items())},
        "per_storey_front_back": {str(lv): {k: per_level[lv][k] // storeys_per_level[lv] for k in ("front", "back")}
                                  for lv in sorted(per_level)},
        "model_per_storey": {"front": sum(len(w) for w in model.values() if w and w[0]["kind"] == "front"),
                             "back": sum(len(w) for w in model.values() if w and w[0]["kind"] == "back")},
        "model_corners": [{"vertex": i, "n": len(w), "kind": w[0]["kind"] if w else None,
                           "yaw_first_last": [round(w[0]["yaw"], 4), round(w[-1]["yaw"], 4)] if w else None,
                           "sx": round(w[0]["sx"], 6) if w else None, "sy": round(w[0]["sy"], 6) if w else None}
                          for i, w in model.items()],
        "n_off_vertex": len(off_vertex), "off_vertex_sample": off_vertex[:5],
        "n_groups": len(rows), "n_problems": len(problems), "problems": problems[:10],
        "missing_groups": missing[:10], "n_missing_groups": len(missing),
        "groups_sample": rows[:8],
        "ok": bool(inst) and not problems and not off_vertex and not missing,
    }


def main():
    a = probe_actor()
    out = mesh_counts(a)
    R = {"label": LABEL, "meshes": out, "total": sum(out.values())}
    if args.get("fans", True):
        R["fans"] = fan_check(a)
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
