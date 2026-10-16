import gc
import json
import os
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]

# pypcg_probe_node.py -- run the host probe (stage 0) on a transient volume of the open level (Task 6).
# Args: {"phase": "spawn", "at": [x, y, z], "params": {...}} | {"phase": "read"} | {"phase": "remove"}
# The probe actor is never saved; remove it when done. One generation per call (traps.md 38): read
# in the call after spawn.
LABEL = "PyPCG_Probe"
GRAPH = "/Game/PyPCG/Probe/PCG_PyProbe"


def _actor():
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        if a.get_actor_label() == LABEL:
            return a
    return None


def phase_spawn(args):
    from pypcg import stage_api
    a = _actor()
    if a is None:
        x, y, z = args.get("at", [0.0, 0.0, 2000.0])
        a = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(unreal.PCGVolume, unreal.Vector(x, y, z))
        a.set_actor_label(LABEL)
        a.set_actor_scale3d(unreal.Vector(25.0, 25.0, 10.0))
    pc = a.get_component_by_class(unreal.PCGComponent)
    pc.set_editor_property("regenerate_in_editor", False)
    pc.set_graph(unreal.EditorAssetLibrary.load_asset(GRAPH))
    inst = pc.get_editor_property("graph_instance")
    for k, v in (args.get("params") or {}).items():
        err = unreal.PyPCGToolsLibrary.set_instance_parameter(inst, k, json.dumps({"v": v}))
        if err:
            raise RuntimeError("parameter %s: %s" % (k, err))
    os.environ[stage_api.RECORD_ENV] = "1"
    pc.activate(True)
    pc.generate_local(True)
    loc = a.get_actor_location()
    return {"spawned": LABEL, "at": [loc.x, loc.y, loc.z]}


def _trace_z(x, y):
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    res = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, 500000.0), unreal.Vector(x, y, -500000.0),
                                                 unreal.TraceTypeQuery.ECC_VISIBILITY, True, [],
                                                 unreal.DrawDebugTrace.NONE, True)
    hit = res[-1] if isinstance(res, tuple) else res        # 5.8: a bare HitResult, hit or miss
    if hit is None:
        return None
    # HitResult's fields are protected and GameplayStatics has no break_hit_result in Python;
    # to_tuple() gives (blocking, initial, time, distance, location, impact_point, ...).
    parts = hit.to_tuple()
    return float(parts[4].z) if parts[0] else None


def phase_read(args):
    from pypcg import geo, stage_api
    from pypcg.ue import convert
    a = _actor()
    if a is None:
        return {"abort": "no probe actor; run spawn first"}
    pc = a.get_component_by_class(unreal.PCGComponent)
    items = {}
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        d = td.get_editor_property("data").get_editor_property("data")           # traps.md 46
        tags = sorted(str(t) for t in td.get_editor_property("tags"))
        key = next((t for t in tags if t.startswith("PyProbe")), "?")
        items[key] = (d.get_class().get_name(), convert.from_pcg(d))
    loc = a.get_actor_location()
    s = float((args.get("params") or {}).get("Size", 5000.0))

    def get(key):
        return items.get(key, (None, None))

    checks = {}
    cls, area = get("PyProbeArea")
    checks["area_is_polygon2d"] = cls == "PCGPolygon2DData"
    checks["area_value"] = bool(area) and abs(geo.area_m2(area) - (4 * s * s - s * s / 4) / 1e4) < 0.01 and len(area.holes) == 1
    cls, line = get("PyProbeLine")
    checks["line_closed_spline"] = cls == "PCGSplineData" and bool(line) and line.closed and len(line.points) == 4
    _, pts = get("PyProbePoints")
    checks["points_and_attributes"] = (bool(pts) and len(pts) == 3 and pts.attrs.get("Mesh") == ["/Engine/BasicShapes/Cube.Cube"] * 3
                                       and pts.attrs.get("Weight") == [0.0, 0.5, 1.0] and abs(pts.rot[1][1] - 30.0) < 1e-3)
    _, par = get("PyProbeParams")
    checks["param_set"] = bool(par) and par.values == {"A": 1.5, "Name": "x"}
    _, rep = get("PyProbeReport")
    r = rep.values if rep else {}
    trace = _trace_z(loc.x, loc.y)
    checks["terrain_height_read"] = r.get("TerrainZ", -1e9) > -1e8
    if trace is not None:
        checks["terrain_matches_trace"] = abs(r.get("TerrainZ", -1e9) - trace) < 50.0
    checks["spline_read_with_polyline"] = r.get("SplineCount", 0) >= 1 and r.get("SplinePolyline", 0) > r.get("SplineControl", 0)
    checks["empty_pin_runs"] = r.get("EmptyCount") == 0
    checks["params_reach_stage"] = r.get("Label") == "probe" and r.get("Flag") is True
    run = json.load(open(os.path.join(stage_api.RUNS_DIR, "s00.json"), encoding="utf-8"))
    _, bench = get("PyProbeBench")
    return {"all_ok": all(checks.values()), "checks": checks, "report": r, "trace_z": trace,
            "seconds": run["seconds"], "bench_points": len(bench) if bench else 0,
            "classes": {k: v[0] for k, v in items.items()}}


def phase_remove(args):
    a = _actor()
    ok = bool(a) and unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(a)
    return {"removed": ok}


def run(args):
    return {"spawn": phase_spawn, "read": phase_read, "remove": phase_remove}[args.get("phase", "read")](args)


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
