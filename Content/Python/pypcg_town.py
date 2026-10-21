import gc
import json
import os
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
# The bridge keeps sys.modules between calls; drop pypcg so edits to it take effect.
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())

# pypcg_town.py -- run the 18 stages in the town level (spec 5). One phase per call.
#   assign                       volumes -> /Game/PyPCG/Town/*, keep their overrides + the town's
#   reset                        cleanup_local on every volume                     (Task 27)
#   gen {"stage"}                activate + generate_local(True)                   (Task 27)
#   read {"stage","pass"}        census + acceptance for that stage                (Task 27)
#   shot {"stage","pass"}        one screenshot of the town so far                 (Task 27)
#   overview {"view"}            top / street / wide                               (Task 27)
#   landed                       list the pt_* screenshots on disk                 (Task 27)
#   finish                       compare passes, save level, write census          (Task 28)
LEVEL = "L_PyTown"
REPORTS = os.path.join(_REPO, "Saved", "Reports")
OVERRIDES = os.path.join(REPORTS, "pypcg_town_component_overrides.json")


def _load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True)


def _current_map():
    """The current map's short name; the current ULevel itself is always named PersistentLevel."""
    lvl = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).get_current_level()
    return lvl.get_path_name().split(":", 1)[0].rsplit(".", 1)[-1] if lvl else ""


def phase_assign():
    from pypcg import census, stages
    from pypcg.profiles import town
    saved = _load(OVERRIDES, {})
    out = {}
    for s in stages.STAGES:
        v = census.volume(s[0])
        pc = v.get_component_by_class(unreal.PCGComponent)
        if s[1] not in saved:                       # the template copy's own overrides, recorded once
            saved[s[1]] = census.overrides(pc)
        pc.set_graph(unreal.EditorAssetLibrary.load_asset("/Game/PyPCG/Town/" + s[1]))
        wanted = dict(saved[s[1]])
        wanted.update(town.COMPONENT_OVERRIDES.get(s[1], {}))
        res = census.apply_overrides(pc, wanted)
        back = census.overrides(pc)
        out[s[1]] = {"graph": pc.get_graph().get_path_name(),
                     "overrides_ok": all(back.get(k) == val for k, val in wanted.items() if k not in res["skipped"]),
                     "skipped": res["skipped"], "overrides": back}
    _save(OVERRIDES, saved)
    return out


SHOT = "pt_stage_%02d_%s_p%d.png"
TERRAIN_SAMPLES = {"inner": [(0, 0), (20000, 10000), (-20000, -10000), (10000, -25000), (-25000, 20000)],
                   "outer": [(75000, 0), (-75000, 0), (0, 70000), (0, -70000)]}
LOG = os.path.join(_REPO, "Saved", "Logs", "PCG_Claude.log")


def _pass_file(k):
    return os.path.join(REPORTS, "pypcg_town_pass%d.json" % k)


def _trace_z(x, y):
    """Ground height under (x, y): the first visibility hit from above (ruling T27c: 5.8 returns a bare
    HitResult whose fields are protected and has no break_hit_result -- traps.md 51; the pattern of
    pypcg_probe_node.py)."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    try:
        res = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, 500000.0), unreal.Vector(x, y, -500000.0),
                                                     unreal.TraceTypeQuery.ECC_VISIBILITY, True, [],
                                                     unreal.DrawDebugTrace.NONE, True)
        hit = res[-1] if isinstance(res, tuple) else res
        if hit is None:
            return None
        parts = hit.to_tuple()
        return float(parts[4].z) if parts[0] else None
    except Exception:
        return None


def _log_size():
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


def _log_since(offset):
    """The editor log's PCG errors and Python stage lines written since `offset` (traps.md 54, 66, 71)."""
    try:
        with open(LOG, "rb") as fh:
            fh.seek(offset)
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return {}
    lines = text.splitlines()
    errors = [ln[-300:] for ln in lines if "LogPCG: Error" in ln or "LogPython: Error" in ln]
    return {"pcg_errors": len(errors), "first_errors": errors[:6],
            "not_loaded": sum("could not be loaded" in ln for ln in lines),
            "pypcg_lines": [ln[-200:] for ln in lines if "PyPCG s" in ln][:20],
            "crash": any("Crash in runnable thread" in ln for ln in lines)}


def _union(boxes):
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    n = min(len(b[0]) for b in boxes)       # v2 item boxes are 2D, component boxes 3D
    return [[min(b[0][i] for b in boxes) for i in range(n)], [max(b[1][i] for b in boxes) for i in range(n)]]


def _component_bounds(actor):
    """The world bounds of the volume's non-debug instanced meshes (what the stage placed)."""
    from pypcg import census
    boxes = []
    for c in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if (sm and sm.get_path_name().startswith(census.DEBUG_MESH)) or c.get_instance_count() == 0:
            continue
        origin, ext, _r = unreal.SystemLibrary.get_component_bounds(c)
        boxes.append([[origin.x - ext.x, origin.y - ext.y, origin.z - ext.z],
                      [origin.x + ext.x, origin.y + ext.y, origin.z + ext.z]])
    return _union(boxes)


def phase_reset(args):
    """cleanup_local on every volume, or with {"from": s} on stages s..18 only (a restart mid-run)."""
    from pypcg import census, stages
    if "from" in args:
        vols = [census.volume(s[0]) for s in stages.STAGES if s[0] >= int(args["from"])]
    else:
        vols = census.volumes()
    for v in vols:
        v.get_component_by_class(unreal.PCGComponent).cleanup_local(True)
    return {"cleaned": len(vols), "labels": sorted(str(v.get_actor_label()) for v in vols)}


def phase_gen(args):
    import time
    from pypcg import census
    stage, k = int(args["stage"]), int(args.get("pass", 1))
    pc = census.component(stage)
    data = _load(_pass_file(k), {})
    data.setdefault(str(stage), {}).update(gen_at=time.time(), log_offset=_log_size())
    _save(_pass_file(k), data)
    pc.activate(True)
    pc.generate_local(True)
    return {"stage": stage, "graph": pc.get_graph().get_path_name()}


def phase_read(args):
    import time
    from pypcg import census, stages, town_checks
    from pypcg.profiles import official, town_layout
    stage, k = int(args["stage"]), int(args.get("pass", 1))
    data = _load(_pass_file(k), {})
    entry = data.setdefault(str(stage), {})
    rec = census.record(stage)
    rec["params"] = dict(census.overrides(census.component(stage)))
    rec["output_bounds"] = _union([it["bbox"] for it in rec["items"]])
    rec["component_bounds"] = _component_bounds(census.volume(stage))
    if stage == 1:
        z = {key: [_trace_z(x, y) for x, y in pts] for key, pts in TERRAIN_SAMPLES.items()}
        rec["terrain_raw"] = z
        if all(v is not None for vals in z.values() for v in vals):
            rec["terrain"] = z
    upstream = {}
    by_graph = {s[1]: s[0] for s in stages.STAGES}
    for role in town_checks.RULES[stage].get("upstream", {}):
        upstream[role] = census.record(by_graph[official.ROLE_LABELS[role]])
    verdict = town_checks.check(stage, rec, upstream, town_layout.city_bbox(20000))
    log = _log_since(entry.get("log_offset", 0))
    seconds = round(time.time() - entry["gen_at"], 1) if "gen_at" in entry else None
    reads = entry.get("reads", []) + [{"at": time.time(), "since_gen_s": seconds,
                                        "instances": rec["instances"]["total"], "items": len(rec["items"])}]
    entry.update(graph=stages.name(stage), record=rec, verdict=verdict, log=log, reads=reads)
    _save(_pass_file(k), data)
    return {"stage": stage, "pass": k, "instances": rec["instances"]["total"], "items": len(rec["items"]),
            "since_gen_s": seconds, "tags": sorted({t for it in rec["items"] for t in it["tags"] if ":" not in t}),
            "components": rec["instances"]["components"], "component_bounds": rec["component_bounds"],
            "output_bounds": rec["output_bounds"], "terrain": rec.get("terrain_raw"),
            "log": {kk: log.get(kk) for kk in ("pcg_errors", "not_loaded", "crash", "first_errors")}, **verdict}


def _shots_module():
    if _PY not in sys.path:
        sys.path.insert(0, _PY)
    for m in ("pcg_sa_shots", "pcg_sa_geom"):
        sys.modules.pop(m, None)
    import pcg_sa_geom as G
    import pcg_sa_shots as S
    return G, S


def _landed(S):
    d = os.path.dirname(S.shot_path("x.png"))
    if not os.path.isdir(d):
        return {}
    return {f: os.path.getsize(os.path.join(d, f)) for f in sorted(os.listdir(d)) if f.startswith("pt_")}


def phase_shot(args):
    from pypcg import stages
    from pypcg.profiles import town_layout
    G, S = _shots_module()
    promoted = S.promote_variants()
    stage, k = int(args["stage"]), int(args.get("pass", 1))
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    (x0, y0, _), (x1, y1, _) = town_layout.city_bbox()
    center, radius = [(x0 + x1) / 2, (y0 + y1) / 2, 0.0], 0.5 * max(x1 - x0, y1 - y0)
    loc, rot = G.orbit_camera(center, radius, -35, 38, 2.2, min_height=radius * 0.6)
    les.set_level_viewport_camera_info(unreal.Vector(*loc), unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]),
                                       les.get_active_viewport_config_key())
    info = S.fire(SHOT % (stage, stages.name(stage), k), les)
    data = _load(_pass_file(k), {})
    data.setdefault(str(stage), {})["shot"] = info.get("claimed")
    if "record" in data[str(stage)]:
        data[str(stage)]["params"] = data[str(stage)]["record"].get("params", {})
    _save(_pass_file(k), data)
    return {"fired": info, "promoted": promoted, "landed": _landed(S)}


OVERVIEWS = {"top": (0, 85, 2.0), "street": (-60, 8, 0.6), "wide": (20, 28, 3.0)}


def phase_overview(args):
    from pypcg.profiles import town_layout
    G, S = _shots_module()
    promoted = S.promote_variants()
    az, elev, mult = OVERVIEWS[args["view"]]
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    (x0, y0, _), (x1, y1, _) = town_layout.city_bbox()
    center, radius = [(x0 + x1) / 2, (y0 + y1) / 2, 0.0], 0.5 * max(x1 - x0, y1 - y0)
    loc, rot = G.orbit_camera(center, radius, az, elev, mult, min_height=1500.0)
    les.set_level_viewport_camera_info(unreal.Vector(*loc), unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]),
                                       les.get_active_viewport_config_key())
    return {"fired": S.fire("pt_overview_%s.png" % args["view"], les), "promoted": promoted, "landed": _landed(S)}


def phase_landed(args):
    _G, S = _shots_module()
    return {"promoted": S.promote_variants(), "landed": _landed(S)}


PHASES = {"assign": lambda a: phase_assign(), "reset": phase_reset, "gen": phase_gen,
          "read": phase_read, "shot": phase_shot, "overview": phase_overview, "landed": phase_landed}


def run(args):
    if _current_map() != LEVEL:
        return {"abort": "open /Game/PyPCG/%s first (current: %s)" % (LEVEL, _current_map())}
    phase = args.get("phase")
    if phase not in PHASES:
        return {"abort": "unknown phase %r; phases: %s" % (phase, sorted(PHASES))}
    return PHASES[phase](args)


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
