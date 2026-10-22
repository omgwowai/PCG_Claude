import gc
import json
import os
import sys
import time

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
# The bridge keeps sys.modules between calls; drop pypcg so edits to it take effect.
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())

# pyworld.py -- the PyWorld valley (docs/superpowers/specs/2026-10-22-pyworld-video-pipeline-design.md), one phase
# per call, every phase but build/make only in /Game/PyPCG/L_PyWorld:
#   build {"stages": "all"|[n]}   describe -> /Game/PyPCG/World/PCGW_*, structural check, save on 0 diffs
#   make                          create L_PyWorld as a copy of L_PyCity (or open it)
#   layout                        drop the city's volumes and controls, reuse one spline as the valley axis, MPD_Basic,
#                                 spawn the control points and the nine volumes
#   assign                        graphs on the volumes, on-demand generation, seed 42
#   reset {"from": n}             cleanup_local on W9 .. Wn
#   gen {"stage": n, "pass": k}   generate one stage (refuses if an earlier one is not generated)
#   read {"stage": n, "pass": k}  run record Summary + instances + log -> acceptance (pypcg.world.checks)
#   tops                          grammar wall tops per height group, from W6's instances
#   shot {"stage": n}|{"view"}    one screenshot (top / wide / valley / street)
#   check                         W10: intrusions, crossings, connectivity, grades, grounding
#   compare                       pass 1 against pass 2, instances per mesh per stage
#   save                          save L_PyWorld (only its own volumes and graphs)
REPORTS = os.path.join(_REPO, "Saved", "Reports")
RUNS = os.path.join(_REPO, "Saved", "PyPCG", "runs")
LOG = os.path.join(_REPO, "Saved", "Logs", "PCG_Claude.log")
CITY_TAGS = {"City", "Arteries", "Highway", "HighRise", "LandmarkPark", "USER_SPLINE", "LAKE", "FOREST_EXCLUSION",
             "Terrain_shaping_1", "PyCity_MainTowerFootprint", "PyCity_CentralParkFootprint"}
VIEWS = {"top": ((0.0, 0.0, 2000.0), 100000.0, 0.0, 88.0, 1.25), "wide": ((0.0, 0.0, 2000.0), 100000.0, -60.0, 32.0, 1.7),
         "valley": ((0.0, -20000.0, 2000.0), 90000.0, -95.0, 16.0, 1.5),
         "street": ((14000.0, -30000.0, 2600.0), 9000.0, -120.0, 9.0, 1.6)}


def _load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True, default=str)


def _report(name):
    return os.path.join(REPORTS, "pyworld_%s.json" % name)


def _require(what):
    from pypcg import level, world as W
    return level.require(W.LEVEL, "pyworld.py " + what)


def _eas():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _les():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def _tags(a):
    return {str(t) for t in a.get_editor_property("tags")}


def _volume(n):
    from pypcg import world as W
    for a in _eas().get_all_level_actors():
        if W.volume_tag(n) in _tags(a):
            return a
    raise RuntimeError("no volume tagged %s; run layout" % W.volume_tag(n))


def _pc(n):
    return _volume(n).get_component_by_class(unreal.PCGComponent)


def _log_size():
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


def _log_since(offset):
    try:
        with open(LOG, "rb") as fh:
            fh.seek(offset)
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return {}
    errors = [ln[-300:] for ln in lines if "LogPCG: Error" in ln or "LogPython: Error" in ln]
    return {"errors": len(errors), "first_errors": errors[:6], "pypcg": [ln[-200:] for ln in lines if "PyPCG w" in ln][-4:],
            "crash": any("Crash in runnable thread" in ln for ln in lines)}


def _trace_z(x, y):
    """Ground height under (x, y): the first visibility hit from above (traps.md 51), None on a miss."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    res = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, 500000.0), unreal.Vector(x, y, -500000.0),
                                                 unreal.TraceTypeQuery.ECC_VISIBILITY, True, [],
                                                 unreal.DrawDebugTrace.NONE, True)
    hit = res[-1] if isinstance(res, tuple) else res
    if hit is None:
        return None
    parts = hit.to_tuple()
    return float(parts[4].z) if parts[0] else None


def phase_build(args):
    from pypcg import build, compare, world as W
    from pypcg.world import graphs
    wanted = [s[0] for s in W.STAGES] if args.get("stages", "all") == "all" else [int(n) for n in args["stages"]]
    rows = []
    for n in wanted:
        ir = graphs.graph(n).to_ir(None)
        diffs = build.build_slim(ir, W.asset(n), save=bool(args.get("save", True)))
        rows.append({"stage": n, "asset": W.asset(n), "nodes": len(ir["nodes"]), "diffs": len(diffs),
                     "first": compare.format_diffs(diffs, 10)})
    _save(_report("build"), rows)
    return rows


def phase_make(args):
    from pypcg import level, world as W
    if level.current_map() == level.DEMO:
        return {"abort": "the demo is current; open another level first"}
    dirty = [str(p.get_name()) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    if dirty:
        return {"abort": "unsaved maps %s; not switching levels" % dirty}
    ael = unreal.EditorAssetLibrary
    if ael.does_asset_exist(W.LEVEL):
        ok, how = bool(_les().load_level(W.LEVEL)), "load_level"
    else:
        ok, how = bool(_les().new_level_from_template(W.LEVEL, W.TEMPLATE)), "new_level_from_template"
    return {"how": how, "ok": ok, "current": level.current_map(), "gate": level.current_map() == W.LEVEL}


def _write_spline(actor, pts):
    sc = actor.get_component_by_class(unreal.SplineComponent)
    sc.set_spline_points([unreal.Vector(*p) for p in pts], unreal.SplineCoordinateSpace.WORLD, False)
    sc.set_closed_loop(False, False)
    for i in range(len(pts)):
        sc.set_spline_point_type(i, unreal.SplinePointType.CURVE, False)
    sc.update_spline()
    back = [sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD) for i in range(sc.get_number_of_spline_points())]
    if len(back) != len(pts):
        return 1e9
    return round(max(abs(a.x - b[0]) + abs(a.y - b[1]) + abs(a.z - b[2]) for a, b in zip(back, pts)), 4)


def phase_layout(args):
    from pypcg import world as W
    from pypcg.world import layout as L
    refused = _require("layout")
    if refused:
        return refused
    eas = _eas()
    actors = eas.get_all_level_actors()
    valley = next((a for a in actors if str(a.get_actor_label()) == L.TAG_VALLEY), None) or \
        next((a for a in actors if str(a.get_actor_label()) == "CityShape"), None)
    if valley is None:
        return {"abort": "no spline actor (CityShape or PyWorld_Valley) to reuse for the valley axis"}
    out = {"destroyed": [], "spawned": []}
    for a in list(actors):
        if a == valley:
            continue
        tags = _tags(a)
        if a.get_component_by_class(unreal.PCGComponent) is not None or tags & CITY_TAGS or \
                any(t.startswith("PyWorld_") for t in tags):
            label = str(a.get_actor_label())
            if eas.destroy_actor(a):
                out["destroyed"].append(label)
    valley.set_actor_label(L.TAG_VALLEY)
    valley.set_editor_property("tags", [L.TAG_VALLEY])
    valley.set_actor_location(unreal.Vector(0.0, 0.0, 0.0), False, False)
    out["valley_error_cm"] = _write_spline(valley, L.valley_points())
    mp = next((a for a in eas.get_all_level_actors() if a.get_class().get_name() == "MeshPartition"), None)
    out["mpd"] = None
    if mp is not None and args.get("mpd", True):
        try:
            before = mp.get_editor_property("mega_mesh_definition")
            mp.set_editor_property("mega_mesh_definition", unreal.EditorAssetLibrary.load_asset(W.MPD_BASIC))
            after = mp.get_editor_property("mega_mesh_definition")
            out["mpd"] = {"before": before.get_path_name() if before else None, "after": after.get_path_name() if after else None}
        except Exception as ex:
            out["mpd"] = {"error": "%s: %s" % (type(ex).__name__, str(ex)[:300])}

    def point(label, tag, x, y, scale=1.0):
        a = eas.spawn_actor_from_class(unreal.TargetPoint, unreal.Vector(x, y, 0.0), unreal.Rotator())
        a.set_actor_label(label)
        a.set_editor_property("tags", [tag])
        a.set_actor_scale3d(unreal.Vector(scale, scale, 1.0))
        a.set_folder_path("PyWorld/Controls")
        out["spawned"].append(label)
    for name, x, y, r in L.LOCATIONS:
        point(name, L.TAG_LOCATION, x, y, r / 10000.0)
    for name, x, y in L.RIVER_ENDS:
        point(name, L.TAG_RIVER_END, x, y)
    for name, x, y in L.ROAD_EXITS:
        point(name, L.TAG_EXIT, x, y)
    for n, label, _m, _t in W.STAGES:
        vol = eas.spawn_actor_from_class(unreal.PCGVolume, unreal.Vector(0.0, 0.0, 0.0), unreal.Rotator())
        vol.set_actor_label(label)
        vol.set_editor_property("tags", [W.volume_tag(n)])
        vol.set_folder_path("PyWorld/Volumes")
        bb = vol.get_editor_property("brush_builder")
        for k, v in (("x", 300000.0), ("y", 300000.0), ("z", 100000.0)):
            bb.set_editor_property(k, v)
        pc = vol.get_component_by_class(unreal.PCGComponent)
        pc.set_editor_property("regenerate_in_editor", False)
        out["spawned"].append(label)
    carriers = {}
    for a in eas.get_all_level_actors():
        for t in _tags(a):
            carriers.setdefault(t, []).append(str(a.get_actor_label()))
    out["tags"] = {t: sorted(v) for t, v in carriers.items() if t.startswith("PyWorld_")}
    out["ok"] = len(out["tags"].get(L.TAG_LOCATION, [])) == len(L.LOCATIONS) and \
        all(len(out["tags"].get(W.volume_tag(n), [])) == 1 for n, _l, _m, _t in W.STAGES) and out["valley_error_cm"] < 1.0
    return out


def phase_assign(args):
    from pypcg import census, world as W
    refused = _require("assign")
    if refused:
        return refused
    out = {}
    for n, _l, _m, _t in W.STAGES:
        pc = _pc(n)
        pc.set_editor_property("regenerate_in_editor", False)
        pc.set_graph(unreal.EditorAssetLibrary.load_asset(W.asset(n)))
        try:
            pc.set_editor_property("generation_trigger", unreal.PCGComponentGenerationTrigger.GENERATE_ON_DEMAND)
        except Exception as ex:
            out["trigger_error"] = str(ex)[:200]
        pc.set_editor_property("seed", 42)
        res = census.apply_overrides(pc, (args.get("overrides") or {}).get(str(n), {}))
        out[n] = {"graph": pc.get_graph().get_path_name(), "skipped": res["skipped"]}
    return out


def phase_reset(args):
    from pypcg import world as W
    refused = _require("reset")
    if refused:
        return refused
    start = int(args.get("from", 1))
    for n in range(len(W.STAGES), start - 1, -1):
        pc = _pc(n)
        pc.set_editor_property("regenerate_in_editor", False)
        pc.activate(True)
        pc.cleanup_local(True)
    return {"cleaned": list(range(start, len(W.STAGES) + 1))}


def phase_gen(args):
    from pypcg import stage_api, world as W
    refused = _require("gen")
    if refused:
        return refused
    n, k = int(args["stage"]), int(args.get("pass", 1))
    pc = _pc(n)
    g = pc.get_graph()
    if g is None or g.get_path_name().split(".")[0] != W.asset(n):
        return {"abort": "W%02d does not hold %s (run assign)" % (n, W.asset(n))}
    missing = [m for m in range(1, n) if not _pc(m).get_editor_property("generated")]
    if missing and not args.get("force"):
        return {"abort": "earlier stages not generated: %s" % missing}
    os.environ[stage_api.RECORD_ENV] = "1"
    _save(_report("w%02d_gen" % n), {"gen_at": time.time(), "log_offset": _log_size(), "pass": k})
    pc.activate(True)
    pc.generate_local(True)
    return {"stage": n, "pass": k, "graph": g.get_path_name()}


def phase_read(args):
    from pypcg import census
    from pypcg.world import checks, layout as L
    refused = _require("read")
    if refused:
        return refused
    n, k = int(args["stage"]), int(args.get("pass", 1))
    gen = _load(_report("w%02d_gen" % n), {})
    path = os.path.join(RUNS, "w%02d.json" % n)
    rec = _load(path, {})
    fresh = os.path.exists(path) and os.path.getmtime(path) >= gen.get("gen_at", 0)
    summary = None
    for item in (rec.get("outputs") or {}).get("Summary", []):
        summary = item[0].get("values")
    inst = census.instances(_volume(n))
    extra = {"instances": inst["total"]}
    if n == 1:
        errs = []
        for y in range(-90000, 90001, 30000):
            z = _trace_z(L.axis_x(y), float(y))
            if z is not None:
                errs.append(abs(z - L.floor_z(y)))
        extra["traced_floor_err_cm"] = max(errs) if errs else None
    fails = checks.accept(n, summary, extra)
    log = _log_since(gen.get("log_offset", 0))
    out = {"stage": n, "pass": k, "fresh_record": fresh, "seconds": rec.get("seconds"), "notes": rec.get("notes"),
           "summary": summary, "extra": extra, "meshes": len(inst["per_mesh"]),
           "since_gen_s": round(time.time() - gen["gen_at"], 1) if "gen_at" in gen else None,
           "generated": bool(_pc(n).get_editor_property("generated")), "log": log, "failures": fails,
           "pass_ok": bool(fresh and not fails and not log.get("crash"))}
    book = _load(_report("pass%d" % k), {})
    book[str(n)] = dict(out, per_mesh=inst["per_mesh"])
    _save(_report("pass%d" % k), book)
    return out


def phase_tops(args):
    """Wall top above the pad per height group: each grammar instance's top (mesh bounds x scale) is given to the
    nearest W6 building; the median per group is what rules.WALL_TOP should hold."""
    from pypcg import census
    from pypcg.ue import convert
    refused = _require("tops")
    if refused:
        return refused
    pc = _pc(6)
    buildings = []
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        if "Building" in [str(t) for t in td.get_editor_property("tags")]:
            v = convert.from_pcg(td.get_editor_property("data").get_editor_property("data"))
            for i in range(len(v)):
                buildings.append((v.loc[i], v.attrs["Group"][i]))
    tops = {}
    for c in _volume(6).get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None or "/PCGPrimitives/Meshes/" not in sm.get_path_name():
            continue
        zmax = sm.get_bounding_box().max.z
        for i in range(c.get_instance_count()):
            t = c.get_instance_transform(i, True)
            x, y, z = t.translation.x, t.translation.y, t.translation.z + zmax * t.scale3d.z
            if not buildings:
                break
            loc, group = min(buildings, key=lambda b: (b[0][0] - x) ** 2 + (b[0][1] - y) ** 2)
            key = (round(loc[0]), round(loc[1]))
            tops.setdefault(group, {}).setdefault(key, []).append(z - loc[2])
    out = {}
    for group, per in tops.items():
        vals = sorted(max(v) for v in per.values())
        out[group] = {"buildings": len(vals), "median_top_cm": vals[len(vals) // 2] if vals else None,
                      "min": vals[0] if vals else None, "max": vals[-1] if vals else None}
    _save(_report("tops"), out)
    return out


def phase_shot(args):
    for m in ("pcg_sa_shots", "pcg_sa_geom"):
        sys.modules.pop(m, None)
    import pcg_sa_geom as G
    import pcg_sa_shots as S
    refused = _require("shot")
    if refused:
        return refused
    view = args.get("view", "wide")
    centre, radius, az, elev, mult = VIEWS[view]
    if "centre" in args:                       # a close-up: {"view": "street", "centre": [x, y, z], "radius": cm}
        centre, radius = tuple(args["centre"]), float(args.get("radius", radius))
        az, elev = float(args.get("az", az)), float(args.get("elev", elev))
    loc, rot = G.orbit_camera(list(centre), radius, az, elev, mult, min_height=centre[2] + 800.0)
    les = _les()
    from pypcg import world as W
    for n, _l, _m, _t in W.STAGES:          # the 3 km volume boxes draw an orange wireframe across the sky
        brush = _volume(n).get_component_by_class(unreal.BrushComponent)
        if brush is not None:
            brush.set_visibility(False, False)
    les.set_level_viewport_camera_info(unreal.Vector(*loc), unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]),
                                       les.get_active_viewport_config_key())
    name = "pyworld_w%02d_%s.png" % (int(args["stage"]), view) if "stage" in args else "pyworld_%s.png" % view
    if args.get("tag"):
        name = name.replace(".png", "_%s.png" % args["tag"])
    return {"fired": S.fire(name, les)}


def _outputs(n):
    from pypcg.ue import convert
    items = []
    for td in _pc(n).get_generated_graph_output().get_editor_property("tagged_data"):
        try:
            v = convert.from_pcg(td.get_editor_property("data").get_editor_property("data"))
        except TypeError:
            continue
        items.append((v, frozenset(str(t) for t in td.get_editor_property("tags"))))
    return items


def phase_check(args):
    from pypcg.geo import Points
    from pypcg.stages.w03_river import river_rows
    from pypcg.stages.w04_roads import road_rows
    from pypcg.stages.w05_bridges import bridge_rows
    from pypcg.world import checks, rules, scatter, points as WP
    refused = _require("check")
    if refused:
        return refused
    up = [it for n in (2, 3, 4, 5, 6) for it in _outputs(n)]
    roads, river = road_rows(up), river_rows(up)
    nodes = [(r["loc"][0], r["loc"][1], max(r.get("Radius", 0.0), 1500.0))
             for v, t in up if isinstance(v, Points) and t & {"Location", "RoadExit"} for r in WP.rows_of(v)]
    trees = [p for v, t in _outputs(7) if isinstance(v, Points) and "Tree" in t for p in v.loc]
    out = {"intrusions": checks.intrusions(trees, scatter.upstream_exclusions(up)),
           "crossings": checks.crossings(roads, river), "bridges": len(bridge_rows(up)),
           "connected": checks.roads_connected(roads, nodes), "grades": checks.max_grades(roads)}
    tree_meshes = {m for spec in rules.BIOMES.values() if spec["kind"] == "Tree" for ms, _w, _s in spec["species"] for m in ms}
    sink = {m: spec["sink"] for spec in rules.BIOMES.values() for ms, _w, _s in spec["species"] for m in ms}
    from pypcg import world as W
    lamp = W.MESH["Lamp"].split(".")[0]
    errors, sampled = [], 0
    for n in (7, 8):
        for c in _volume(n).get_components_by_class(unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            path = sm.get_path_name() if sm else ""
            full = path if "." in path else path
            key = next((m for m in tree_meshes if m.split(".")[0] == path.split(".")[0]), None)
            if key is None and path.split(".")[0] != lamp:
                continue
            count = c.get_instance_count()
            for i in range(0, count, max(1, count // 150)):
                t = c.get_instance_transform(i, True).translation
                z = _trace_z(t.x, t.y)
                if z is None:
                    continue
                sampled += 1
                err = abs(t.z + (sink[key] if key else 0.0) - z)
                if err > 30.0:
                    errors.append([path.rsplit("/", 1)[-1], round(t.x), round(t.y), round(err, 1)])
    out["grounding"] = {"sampled": sampled, "over_30cm": len(errors), "first": errors[:10]}
    out["ok"] = (sum(out["intrusions"].values()) == 0 and out["crossings"] == out["bridges"] and out["connected"]
                 and out["grades"].get("Main", 0.0) <= 0.10 + 1e-6 and out["grades"].get("Secondary", 0.0) <= 0.14 + 1e-6
                 and not errors)
    _save(_report("check"), out)
    return out


def phase_compare(args):
    a, b = _load(_report("pass1"), {}), _load(_report("pass2"), {})
    out = {}
    for n in sorted(set(a) | set(b), key=int):
        pa, pb = a.get(n, {}).get("per_mesh", {}), b.get(n, {}).get("per_mesh", {})
        diff = {m: [pa.get(m, 0), pb.get(m, 0)] for m in set(pa) | set(pb) if pa.get(m, 0) != pb.get(m, 0)}
        out[n] = {"instances": [sum(pa.values()), sum(pb.values())], "differing_meshes": len(diff),
                  "first": dict(list(diff.items())[:5])}
    out["identical"] = all(v["differing_meshes"] == 0 for v in out.values() if isinstance(v, dict))
    _save(_report("compare"), out)
    return out


def phase_save(args):
    from pypcg import census, world as W
    refused = _require("save")
    if refused:
        return refused
    graphs = {}
    for a in census.volumes():
        g = a.get_component_by_class(unreal.PCGComponent).get_graph()
        graphs[str(a.get_actor_label())] = g.get_path_name() if g else None
    bad = {k: v for k, v in graphs.items() if not (v and v.startswith(W.ASSET_DIR))}
    if bad or len(graphs) != len(W.STAGES):
        return {"abort": "refusing to save: PCG actors %s" % graphs, "saved": False}
    for a in census.volumes():
        a.modify()
    saved = bool(_les().save_current_level())
    folder = os.path.join(_REPO, "Content", "__ExternalActors__", "PyPCG", "L_PyWorld")
    sizes = []
    for root, _d, files in os.walk(folder):
        sizes += [os.path.getsize(os.path.join(root, f)) for f in files]
    return {"saved": saved, "files": len(sizes), "largest_mb": round(max(sizes) / 1e6, 1) if sizes else 0.0,
            "total_mb": round(sum(sizes) / 1e6, 1)}


PHASES = {"build": phase_build, "make": phase_make, "layout": phase_layout, "assign": phase_assign,
          "reset": phase_reset, "gen": phase_gen, "read": phase_read, "tops": phase_tops, "shot": phase_shot,
          "check": phase_check, "compare": phase_compare, "save": phase_save}
DEFERRED = _report("deferred")


def _defer(phase, args):
    """Run a long phase on the next editor tick (a long bridge call loses its reply: traps.md 88)."""
    _save(DEFERRED, {"phase": phase, "state": "queued"})
    handle = {}

    def tick(_dt):
        unreal.unregister_slate_post_tick_callback(handle["h"])
        try:
            _save(DEFERRED, {"phase": phase, "state": "done", "result": PHASES[phase](args)})
        except Exception as exc:
            _save(DEFERRED, {"phase": phase, "state": "error", "error": "%s: %s" % (type(exc).__name__, str(exc)[:800])})
        gc.collect()
    handle["h"] = unreal.register_slate_post_tick_callback(tick)
    return {"deferred": phase, "result_file": DEFERRED}


def run(args):
    phase = args.get("phase")
    if phase not in PHASES:
        return {"abort": "unknown phase %r; phases: %s" % (phase, sorted(PHASES))}
    if args.get("defer"):
        return _defer(phase, {k: v for k, v in args.items() if k != "defer"})
    return PHASES[phase](args)


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
