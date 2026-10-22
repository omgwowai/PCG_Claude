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
#   finish {"dry_run"?, "allow_unmeasured"?: [stage]}
#                                compare passes, write census, save level          (Task 28)
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


def phase_assign():
    from pypcg import census, stages
    from pypcg.profiles import town
    saved = _load(OVERRIDES, {})
    out, town_skipped = {}, {}
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
        # Final review I6: skipping the template's own keys (dropped debug / partition / merged seed
        # parameters, ruling N5) is allowed; skipping one the TOWN asked for is not -- a misspelt key in
        # town.COMPONENT_OVERRIDES would otherwise fall back to the graph default in silence.
        mine = {k: res["skipped"][k] for k in town.COMPONENT_OVERRIDES.get(s[1], {}) if k in res["skipped"]}
        if mine:
            town_skipped[s[1]] = mine
    _save(OVERRIDES, saved)
    bad = sorted(label for label, r in out.items() if not r["overrides_ok"])
    result = {"ok": not town_skipped and not bad, "town_overrides_skipped": town_skipped,
              "overrides_not_ok": bad, "stages": out}
    if town_skipped:
        result["abort"] = "town overrides not applied (misspelt or missing parameter): %s" % town_skipped
    elif bad:
        result["abort"] = "overrides did not read back on %s" % bad
    return result


SHOT = "pt_stage_%02d_%s_p%d.png"
TERRAIN_SAMPLES = {"inner": [(0, 0), (20000, 10000), (-20000, -10000), (10000, -25000), (-25000, 20000)],
                   "outer": [(75000, 0), (-75000, 0), (0, 70000), (0, -70000)]}
LOG = os.path.join(_REPO, "Saved", "Logs", "PCG_Claude.log")


def _pass_file(k):
    return os.path.join(REPORTS, "pypcg_town_pass%d.json" % k)


def _trace_z(x, y, errors):
    """Ground height under (x, y): the first visibility hit from above (ruling T27c: 5.8 returns a bare
    HitResult whose fields are protected and has no break_hit_result -- traps.md 51; the pattern of
    pypcg_probe_node.py). None on a miss. An exception is also None, but its text goes to `errors`, which
    phase_read keeps next to terrain_raw, so a broken trace (an API change) does not read as "no ground"."""
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
    except Exception as exc:
        errors.append("(%s, %s) %s: %s" % (x, y, type(exc).__name__, str(exc)[:200]))
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
    """cleanup_local on every volume, or with {"from": s} on stages s..18 only (a restart mid-run).

    Ruling T28b: first turn regenerate_in_editor off on EVERY town volume (not only the cleaned ones).
    `assign` leaves it on, and then any edit makes the volumes regenerate on their own and out of order."""
    from pypcg import census, stages
    regen_off = 0
    for v in census.volumes():
        pc = v.get_component_by_class(unreal.PCGComponent)
        if pc.get_editor_property("regenerate_in_editor"):
            pc.set_editor_property("regenerate_in_editor", False)
            regen_off += 1
    if "from" in args:
        vols = [census.volume(s[0]) for s in stages.STAGES if s[0] >= int(args["from"])]
    else:
        vols = census.volumes()
    for v in vols:
        v.get_component_by_class(unreal.PCGComponent).cleanup_local(True)
    still_on = [str(v.get_actor_label()) for v in census.volumes()
                if v.get_component_by_class(unreal.PCGComponent).get_editor_property("regenerate_in_editor")]
    return {"cleaned": len(vols), "labels": sorted(str(v.get_actor_label()) for v in vols),
            "regenerate_in_editor_turned_off": regen_off, "regenerate_in_editor_still_on": still_on}


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
        errors = []
        z = {key: [_trace_z(x, y, errors) for x, y in pts] for key, pts in TERRAIN_SAMPLES.items()}
        rec["terrain_raw"] = z
        rec["terrain_errors"] = errors
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
            "terrain_errors": rec.get("terrain_errors"),
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


def _plausibility():
    """spec 5.2: compare the town's densities with the official city's, from the V2 records of stages 6
    and 11 (the official city's area and building count) and 6/7 (its road length).

    Road length is the length of the road SPLINES the two stages publish: stage 6's artery / collector /
    local road splines (stage 7's items are polygons and the terrain, length 0). Summing stage 7 alone, as
    first drafted, gives 0 on both sides and the road check silently skips."""
    from pypcg import town_checks
    d = os.path.join(_REPO, "Saved", "Reports", "v2")

    def road_m(items):
        return sum(it["length_m"] for it in items if it.get("kind") == "spline")

    off6 = _load(os.path.join(d, "s06", "official.json"), {"items": []})["items"]
    off7 = _load(os.path.join(d, "s07", "official.json"), {"items": []})["items"]
    official_area = sum(it["area_m2"] for it in off6)
    official_roads = road_m(off6) + road_m(off7)
    official_bldgs = sum(1 for it in _load(os.path.join(d, "s11", "official.json"), {"items": []})["items"])
    p1 = _load(_pass_file(1), {})
    t6 = p1.get("6", {}).get("record", {"items": []})["items"]
    t7 = p1.get("7", {}).get("record", {"items": []})["items"]
    town_area = sum(it["area_m2"] for it in t6)
    town_bldgs = sum(1 for it in p1.get("11", {}).get("record", {"items": []})["items"])
    town_roads = road_m(t6) + road_m(t7)
    town = {"area_m2": town_area, "buildings": town_bldgs, "road_m": town_roads}
    official = {"area_m2": official_area, "buildings": official_bldgs, "road_m": official_roads}
    dens = {}
    for key in ("buildings", "road_m"):
        # A zero area (stage 6 or its V2 record empty) has no density; town_checks.plausibility fails it.
        t = town[key] / (town_area / 1e6) if town_area > 0 else None
        o = official[key] / (official_area / 1e6) if official_area > 0 else None
        dens[key + "_per_km2"] = {"town": t, "official": o, "ratio": t / o if t is not None and o else None}
    return {"failures": town_checks.plausibility(town, official), "town": town, "official": official,
            "density": dens}


# Ruling T28a: native nodes recorded as varying run to run. A pass-2 difference in one of these stages,
# within its band, is "native run-to-run variation" and does not block the save; anything else does.
#   stage 7   trap 58: three official gens 286 378 / 286 232 / 286 371 (span 146; one mesh 15 apart)
#   stage 10  trap 77: one gen +11 vehicles each with a twin, one mesh -2 (net 20, per-mesh 24)
#   stage 11  task-20 report: oracle runs 28 net, 111 per-mesh absolute (NYA_L3_E)
# band = (max |net total difference|, max sum over meshes of |per-mesh difference|)
NATIVE_BANDS = {7: (146, 146), 10: (22, 24), 11: (28, 111)}


def _mesh_diff(a, b):
    pa, pb = a["instances"]["per_mesh"], b["instances"]["per_mesh"]
    diff = {m: [pa.get(m, 0), pb.get(m, 0)] for m in sorted(set(pa) | set(pb)) if pa.get(m, 0) != pb.get(m, 0)}
    return diff, sum(abs(x - y) for x, y in diff.values())


def _items_same(a, b):
    from pypcg import v2
    return v2.same({"items": a["items"], "instances": {"per_mesh": {}}},
                   {"items": b["items"], "instances": {"per_mesh": {}}})


def _save_refusal():
    """Final review I2: the town is saved only when every PCG volume in it is a stage volume holding a
    /Game/PyPCG/Town/ graph. A probe graph or probe volume left by a script run on the wrong level must
    never be persisted into the deliverable."""
    from pypcg import level, stages
    problems = level.save_problems(level.pcg_volume_graphs(), stages.names())
    return {"abort": "not saving L_PyTown: " + "; ".join(problems), "saved": False} if problems else None


def phase_finish(args):
    from pypcg import stages, v2
    # Final review I6: "unmeasured" passes only for the stages listed in args["allow_unmeasured"] (stage 1's
    # terrain is the only check that can be unmeasured). The town as saved had none: in
    # Tools/data/pypcg_town_census.json (2026-10-21) all 18 stages are "ok" in both passes.
    allow = {int(s) for s in args.get("allow_unmeasured", [])}
    plaus = _plausibility()
    p1, p2 = _load(_pass_file(1), {}), _load(_pass_file(2), {})
    rows, same_all, variation, blocking = [], True, [], []
    for s in stages.STAGES:
        a, b = p1.get(str(s[0])), p2.get(str(s[0]))
        same = bool(a and b and v2.same(a["record"], b["record"]))
        row_var = None
        if a and b and not same:
            diff, absdiff = _mesh_diff(a["record"], b["record"])
            net = b["record"]["instances"]["total"] - a["record"]["instances"]["total"]
            band = NATIVE_BANDS.get(s[0])
            items_same = _items_same(a["record"], b["record"])
            within = bool(band and items_same and abs(net) <= band[0] and absdiff <= band[1])
            row_var = {"stage": s[0], "graph": s[1], "pass1": a["record"]["instances"]["total"],
                       "pass2": b["record"]["instances"]["total"], "net": net, "per_mesh_abs": absdiff,
                       "items_same": items_same, "band": band, "within_band": within,
                       "differing_meshes": diff,
                       "label": "native run-to-run variation" if within else "NOT within a recorded native band"}
            (variation if within else blocking).append(row_var)
        elif not (a and b):
            blocking.append({"stage": s[0], "graph": s[1], "missing": [k for k, v in (("pass1", a), ("pass2", b)) if not v]})
        same_all = same_all and same
        rows.append({"stage": s[0], "graph": s[1], "title": s[3],
                     "instances": a and a["record"]["instances"]["total"],
                     "instances_pass2": b and b["record"]["instances"]["total"],
                     "status": a and a["verdict"]["status"], "status_pass2": b and b["verdict"]["status"],
                     "failures": a and a["verdict"]["failures"],
                     "notes": a and a["verdict"]["notes"], "params": a and a.get("params"),
                     "tags": a and sorted({t for it in a["record"]["items"] for t in it["tags"] if ":" not in t}),
                     "meshes": a and len(a["record"]["instances"]["per_mesh"]), "shot": a and a.get("shot"),
                     "deterministic": same, "variation": row_var})
    def passes(status, stage):
        return status == "ok" or (status == "unmeasured" and stage in allow)

    all_ok = all(passes(r["status"], r["stage"]) and passes(r["status_pass2"], r["stage"]) for r in rows)
    plausible = plaus["failures"] == []
    may_save = all_ok and not blocking and plausible
    census = {"_level": "/Game/PyPCG/L_PyTown",
              "_note": "pass 1 numbers; deterministic = pass 2 equals pass 1 in per-mesh instance counts, tag "
                       "counts and area / length totals (v2.same; positions are not compared); variation = "
                       "differences ruled native run-to-run variation (T28a); plausible = spec 5.2 densities",
              "all_ok": all_ok, "deterministic": same_all, "plausible": plausible,
              "deterministic_within_native_bands": not blocking, "allow_unmeasured": sorted(allow),
              "native_variation": variation, "blocking": blocking, "plausibility": plaus, "stages": rows}
    if not args.get("dry_run"):                     # a dry run reports; it never rewrites the committed census
        _save(os.path.join(_REPO, "Tools", "data", "pypcg_town_census.json"), census)
    saved = False
    if may_save and not args.get("dry_run"):
        refused = _save_refusal()
        if refused:
            return dict(refused, all_ok=all_ok, deterministic=same_all, plausible=plausible, may_save=may_save)
        saved = bool(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level())
    return {"all_ok": all_ok, "deterministic": same_all, "plausible": plausible, "may_save": may_save,
            "saved": saved, "dry_run": bool(args.get("dry_run")),
            "native_variation": variation, "blocking": blocking, "plausibility": plaus,
            "rows": [{k: r[k] for k in ("stage", "graph", "instances", "instances_pass2", "status", "status_pass2",
                                        "deterministic")} for r in rows]}


PHASES = {"assign": lambda a: phase_assign(), "reset": phase_reset, "gen": phase_gen,
          "read": phase_read, "shot": phase_shot, "overview": phase_overview, "landed": phase_landed,
          "finish": phase_finish}


def run(args):
    from pypcg import level
    refused = level.require(level.TOWN, "pypcg_town.py")       # the full package path (final review M14)
    if refused:
        return refused
    phase = args.get("phase")
    if phase not in PHASES:
        return {"abort": "unknown phase %r; phases: %s" % (phase, sorted(PHASES))}
    return PHASES[phase](args)


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
