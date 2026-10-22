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

# pypcg_city.py -- the whole city from ONE PCG graph on ONE volume (pypcg.combined, guide §13). One phase per call.
# Every phase but build takes {"profile": "city" | "small"} (default city): pypcg/profiles/<profile>.py names the
# level, the level it is copied from, the control layout and the volume's overrides.
#   city  -> /Game/PyPCG/L_PyCity       copy of L_PyTown, the town's control layout
#   small -> /Game/PyPCG/L_PyCitySmall  copy of L_PyCity, small_layout (~560 x 440 m)
#   build {"save"}        describe + write /Game/PyPCG/City/PCG_PyCity, structural check (0 diffs), save
#   make                  create the profile's level as a template copy of its TEMPLATE and open it
#   layout                keep one volume + the control actors (destroy other stage volumes, relabel the Terrain
#                         volume PCG_PyCity, footprint volumes -> tagged control actors with no graph), then write
#                         the layout's control splines, move the footprint actors and audit the tags
#   assign                PCG_PyCity -> the merged graph; the template's and the profile's overrides, renamed
#   reset                 cleanup_local on the volume (regenerate_in_editor off)
#   gen {"pass"}          activate + generate_local(True)
#   read {"pass"}         instances per mesh (city: against the 18-volume town), district areas, log
#   overview {"view"}     one screenshot: top / street / wide
#   save                  save the profile's level -- only it, only with the merged graph on its one volume
# Long phases (build, layout, read) take {"defer": true}: see _defer.
REPORTS = os.path.join(_REPO, "Saved", "Reports")
TOWN_OVERRIDES = os.path.join(REPORTS, "pypcg_town_component_overrides.json")
LOG = os.path.join(_REPO, "Saved", "Logs", "PCG_Claude.log")
PROFILES = ("city", "small")


def _load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True)


def _profile(args):
    import importlib
    name = args.get("profile", "city")
    if name not in PROFILES:
        raise ValueError("unknown profile %r; profiles: %s" % (name, PROFILES))
    return importlib.import_module("pypcg.profiles." + name)


def _pname(P):
    return P.__name__.rsplit(".", 1)[-1]


def _pass_file(k, P):
    tag = "" if _pname(P) == "city" else "_" + _pname(P)
    return os.path.join(REPORTS, "pypcg_city%s_pass%d.json" % (tag, k))


def _require(P, what):
    from pypcg import level
    return level.require(P.LEVEL, "pypcg_city.py %s (profile %s)" % (what, _pname(P)))


def _les():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def _volume():
    from pypcg import census
    from pypcg.profiles import city
    a = census.actor_by_label(city.VOLUME)
    if a is None:
        raise RuntimeError("no actor labelled %s in this level" % city.VOLUME)
    return a


def phase_build(args):
    from pypcg import build, combined, compare
    from pypcg.profiles import city
    g = combined.build()
    ir = g.to_ir(city)
    diffs = build.build_slim(ir, combined.ASSET, save=bool(args.get("save", True)),
                             layout=build.banded_layout(combined.positions, combined.titles()))
    out = {"asset": combined.ASSET, "nodes": len(ir["nodes"]), "params": len(ir["params"]),
           "diffs": len(diffs), "first": compare.format_diffs(diffs, 15), "sites": ir["sites"],
           "refs_rewired": len(g.report["refs_rewired"]), "refs_tagged": g.report["refs_tagged"],
           "terrain": g.terrain}
    _save(os.path.join(REPORTS, "pypcg_city_build.json"), out)      # the reply can be lost on a long call
    return out


def phase_make(args):
    from pypcg import level
    P = _profile(args)
    les = _les()
    ael = unreal.EditorAssetLibrary
    if level.current_map() == level.DEMO:
        return {"abort": "the demo is current; open L_PyTown or another level first"}
    dirty = [str(p.get_name()) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    if dirty:
        return {"abort": "unsaved maps %s; not switching levels" % dirty}
    if ael.does_asset_exist(P.LEVEL):
        ok = bool(les.load_level(P.LEVEL))
        how = "load_level"
    else:
        if not ael.does_asset_exist(P.TEMPLATE):
            return {"abort": "the template %s does not exist; make its profile first" % P.TEMPLATE}
        ok = bool(les.new_level_from_template(P.LEVEL, P.TEMPLATE))
        how = "new_level_from_template"
    return {"how": how, "ok": ok, "current": level.current_map(), "gate": level.current_map() == P.LEVEL}


def _write_spline(actor, spec):
    """Positions, closedness and point types in WORLD space, then the largest read-back error in cm
    (as pypcg_town_level._write_spline; set_spline_points resets point types, traps.md 27)."""
    sc = actor.get_component_by_class(unreal.SplineComponent)
    if sc is None:
        raise RuntimeError("%s has no SplineComponent" % actor.get_actor_label())
    pts = [unreal.Vector(*p) for p in spec["points"]]
    sc.set_spline_points(pts, unreal.SplineCoordinateSpace.WORLD, False)
    sc.set_closed_loop(bool(spec["closed"]), False)
    if spec["linear"]:
        for i in range(len(pts)):
            sc.set_spline_point_type(i, unreal.SplinePointType.LINEAR, False)
    sc.update_spline()
    back = [sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD)
            for i in range(sc.get_number_of_spline_points())]
    if len(back) != len(spec["points"]):
        return 1e9
    return round(max(abs(a.x - b[0]) + abs(a.y - b[1]) + abs(a.z - b[2]) for a, b in zip(back, spec["points"])), 4)


def phase_layout(args):
    from pypcg import census, combined, stages
    from pypcg.profiles import city
    P = _profile(args)
    refused = _require(P, "layout")
    if refused:
        return refused
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    keep = stages.name(1)                                   # the town's Terrain volume becomes PCG_PyCity
    controls = {stages.name(n): tag for n, tag in combined.CONTROL_TAGS.items()}
    out = {"destroyed": [], "controls": {}, "volume": None}
    for a in list(census.volumes()):
        label = str(a.get_actor_label())
        pc = a.get_component_by_class(unreal.PCGComponent)
        pc.set_editor_property("regenerate_in_editor", False)
        pc.activate(True)
        pc.cleanup_local(True)
        if label == keep or label == city.VOLUME:
            a.set_actor_label(city.VOLUME)
            out["volume"] = a.get_path_name()
        elif label in controls:
            pc.set_graph(None)
            tags = [str(t) for t in a.get_editor_property("tags")]
            if controls[label] not in tags:
                a.set_editor_property("tags", tags + [controls[label]])
            out["controls"][label] = {"tags": [str(t) for t in a.get_editor_property("tags")]}
        elif eas.destroy_actor(a):
            out["destroyed"].append(label)
    out["pcg_actors_left"] = sorted(str(a.get_actor_label()) for a in census.volumes())
    # The profile's control layout: splines, then the footprint actors, then the tags every tag read needs.
    out["splines"] = {}
    for label, spec in P.LAYOUT.SPLINES.items():
        a = census.actor_by_label(label)
        out["splines"][label] = _write_spline(a, spec) if a is not None else "missing"
    for label, move in getattr(P.LAYOUT, "CONTROL_MOVES", {}).items():
        a = census.actor_by_label(label)
        z = a.get_actor_location().z
        a.set_actor_location(unreal.Vector(move["xy"][0], move["xy"][1], z), False, False)
        if "yaw" in move:
            r = a.get_actor_rotation()
            a.set_actor_rotation(unreal.Rotator(pitch=r.pitch, yaw=move["yaw"], roll=r.roll), False)
    for label in controls:
        a = census.actor_by_label(label)
        loc = a.get_actor_location()
        out["controls"].setdefault(label, {})["at"] = [round(loc.x), round(loc.y), round(a.get_actor_rotation().yaw, 3)]
    carriers = {}
    for a in eas.get_all_level_actors():
        for t in [str(t) for t in a.get_editor_property("tags")]:
            carriers.setdefault(t, set()).add(str(a.get_actor_label()))
    wanted = {t: list(v) for t, v in getattr(P.LAYOUT, "TAGS", {}).items()}
    for n, tag in combined.CONTROL_TAGS.items():
        wanted.setdefault(tag, [stages.name(n)])
    out["tags"] = {t: {"expected": sorted(v), "carriers": sorted(carriers.get(t, ()))} for t, v in wanted.items()}
    bad_tags = [t for t, v in out["tags"].items() if v["expected"] != v["carriers"]]
    bad_splines = [k for k, v in out["splines"].items() if v == "missing" or v >= 0.5]
    out["problems"] = {"tags": bad_tags, "splines": bad_splines}
    out["ok"] = bool(out["volume"] and len(out["controls"]) == 2 and not bad_tags and not bad_splines
                     and out["pcg_actors_left"] == sorted([city.VOLUME] + list(controls)))
    return out


def phase_assign(args):
    from pypcg import census, combined
    P = _profile(args)
    refused = _require(P, "assign")
    if refused:
        return refused
    pc = _volume().get_component_by_class(unreal.PCGComponent)
    pc.set_editor_property("regenerate_in_editor", False)
    pc.set_graph(unreal.EditorAssetLibrary.load_asset(combined.ASSET))
    wanted = combined.component_overrides(_load(TOWN_OVERRIDES, {}))
    wanted.update(P.COMPONENT_OVERRIDES)
    res = census.apply_overrides(pc, wanted)
    back = census.overrides(pc)
    # The template's debug and partition switches are not parameters of the slim graphs (ruling N5); the
    # profile's own overrides must all land.
    lost = [k for k in P.COMPONENT_OVERRIDES if k in res["skipped"]]
    wrong = {k: [v, back.get(k)] for k, v in wanted.items() if k not in res["skipped"] and back.get(k) != v}
    return {"graph": pc.get_graph().get_path_name(), "seed": pc.get_editor_property("seed"),
            "set": len(res["set"]), "skipped": sorted(res["skipped"]), "profile_overrides_lost": lost,
            "mismatched": wrong, "profile_overrides": P.COMPONENT_OVERRIDES, "ok": not lost and not wrong}


def phase_reset(args):
    refused = _require(_profile(args), "reset")
    if refused:
        return refused
    pc = _volume().get_component_by_class(unreal.PCGComponent)
    pc.set_editor_property("regenerate_in_editor", False)
    pc.activate(True)
    pc.cleanup_local(True)
    return {"cleaned": True, "generated": bool(pc.get_editor_property("generated"))}


def _log_size():
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


def _log_since(offset):
    try:
        with open(LOG, "rb") as fh:
            fh.seek(offset)
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return {}
    lines = text.splitlines()
    errors = [ln[-300:] for ln in lines if "LogPCG: Error" in ln or "LogPython: Error" in ln]
    return {"pcg_errors": len(errors), "first_errors": errors[:8],
            "pypcg_lines": len([ln for ln in lines if "PyPCG s" in ln]),
            "pypcg_last": [ln[-160:] for ln in lines if "PyPCG s" in ln][-4:],
            "crash": any("Crash in runnable thread" in ln for ln in lines)}


def phase_gen(args):
    import time
    from pypcg import combined
    P = _profile(args)
    refused = _require(P, "gen")
    if refused:
        return refused
    k = int(args.get("pass", 1))
    pc = _volume().get_component_by_class(unreal.PCGComponent)
    g = pc.get_graph()
    if g is None or g.get_path_name().split(".")[0] != combined.ASSET:
        return {"abort": "PCG_PyCity does not hold %s (run assign)" % combined.ASSET}
    # Rebuilding the graph asset resets the component's graph-instance overrides (traps.md 91): generating
    # then silently runs the graph defaults (measured: terrain ratio 0.5 for 0.4, stage 9 11 items for 479).
    from pypcg import census
    have = census.overrides(pc)
    missing = {k: [v, have.get(k)] for k, v in P.COMPONENT_OVERRIDES.items() if have.get(k) != v}
    if missing:
        return {"abort": "the volume lacks the profile's overrides %s; run assign" % missing}
    _save(_pass_file(k, P), {"gen_at": time.time(), "log_offset": _log_size()})
    pc.activate(True)
    pc.generate_local(True)
    return {"pass": k, "graph": g.get_path_name()}


def _town_per_mesh():
    """The 18-volume town's instances per mesh, summed over its stages (pass 1 of the town run)."""
    p1 = _load(os.path.join(REPORTS, "pypcg_town_pass1.json"), {})
    per = {}
    for _s, entry in p1.items():
        for m, c in entry.get("record", {}).get("instances", {}).get("per_mesh", {}).items():
            per[m] = per.get(m, 0) + c
    return per


def phase_read(args):
    import time
    from pypcg import census
    P = _profile(args)
    refused = _require(P, "read")
    if refused:
        return refused
    k = int(args.get("pass", 1))
    a = _volume()
    pc = a.get_component_by_class(unreal.PCGComponent)
    data = _load(_pass_file(k, P), {})
    inst = census.instances(a)
    town = _town_per_mesh() if _pname(P) == "city" else {}
    diff = {m: [town.get(m, 0), inst["per_mesh"].get(m, 0)] for m in sorted(set(town) | set(inst["per_mesh"]))
            if town.get(m, 0) != inst["per_mesh"].get(m, 0)} if town else {}
    try:
        items = census.outputs(pc)
    except Exception as ex:
        items = [{"error": str(ex)[:200], "tags": []}]
    rec = {"read_at": time.time(), "since_gen_s": round(time.time() - data["gen_at"], 1) if "gen_at" in data else None,
           "generated": bool(pc.get_editor_property("generated")), "instances": inst["total"],
           "meshes": len(inst["per_mesh"]), "components": inst["components"], "output_items": len(items),
           "output_tags": sorted({t for it in items for t in it.get("tags", []) if ":" not in t}),
           "districts": {t: sorted(round(it.get("area_m2") or 0) for it in items if t in it.get("tags", []))
                         for t in ("SmallDistricts", "MediumDistricts", "LargeDistricts", "UndividableDistricts")},
           "top_meshes": sorted(((c, m.rsplit("/", 1)[-1].split(".")[0]) for m, c in inst["per_mesh"].items()),
                                reverse=True)[:12],
           "log": _log_since(data.get("log_offset", 0))}
    if town:
        rec.update(town_instances=sum(town.values()), town_meshes=len(town), differing_meshes=len(diff),
                   per_mesh_abs_diff=sum(abs(x - y) for x, y in diff.values()))
    data.update(read=rec, per_mesh=inst["per_mesh"], diff=diff)
    _save(_pass_file(k, P), data)
    rec["diff_first"] = dict(list(diff.items())[:25])
    return rec


def phase_overview(args):
    P = _profile(args)
    refused = _require(P, "overview")
    if refused:
        return refused
    for m in ("pcg_sa_shots", "pcg_sa_geom"):
        sys.modules.pop(m, None)
    import pcg_sa_geom as G
    import pcg_sa_shots as S
    promoted = S.promote_variants()
    views = {"top": (0, 85, 2.0), "street": (-60, 8, 0.6), "wide": (20, 28, 3.0)}
    az, elev, mult = views[args.get("view", "wide")]
    les = _les()
    (x0, y0, _), (x1, y1, _) = P.LAYOUT.city_bbox()
    center, radius = [(x0 + x1) / 2, (y0 + y1) / 2, 0.0], 0.5 * max(x1 - x0, y1 - y0)
    loc, rot = G.orbit_camera(center, radius, az, elev, mult, min_height=1500.0)
    les.set_level_viewport_camera_info(unreal.Vector(*loc), unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]),
                                       les.get_active_viewport_config_key())
    name = "%soverview_%s.png" % (P.SHOT_PREFIX, args.get("view", "wide"))
    return {"fired": S.fire(name, les), "promoted": promoted}


def phase_save(args):
    from pypcg import census, combined
    refused = _require(_profile(args), "save")
    if refused:
        return refused
    graphs = {str(a.get_actor_label()): (a.get_component_by_class(unreal.PCGComponent).get_graph().get_path_name()
                                         if a.get_component_by_class(unreal.PCGComponent).get_graph() else None)
              for a in census.volumes()}
    running = {k: v for k, v in graphs.items() if v is not None}
    if list(running) != ["PCG_PyCity"] or running["PCG_PyCity"].split(".")[0] != combined.ASSET:
        return {"abort": "refusing to save: graphs on PCG actors are %s" % graphs, "saved": False}
    # A save in the same breath as cleanup_local still wrote the generated components (a 104 MB actor package,
    # traps.md 86); marking the volume modified makes the save write the actor as it is now.
    vol = _volume()
    comps = sorted(c.get_class().get_name() for c in vol.get_components_by_class(unreal.ActorComponent))
    generated = [c for c in comps if c not in ("BrushComponent", "PCGComponent", "BillboardComponent")]
    if generated and not args.get("keep_generated"):
        # cleanup_local finishes over the next ticks: saving before then writes the generated output into
        # the level (149 MB for the town, over GitHub's 100 MB limit). Wait and call save again.
        return {"abort": "the volume still holds %d generated components; reset, wait a few seconds, save again"
                         % len(generated), "saved": False}
    # A save in the same breath as cleanup_local still wrote the generated components (a 104 MB actor package,
    # traps.md 86); marking the volume modified makes the save write the actor as it is now.
    vol.modify()
    return {"saved": bool(_les().save_current_level()), "graphs": graphs, "volume_components": sorted(set(comps))}


PHASES = {"build": phase_build, "make": phase_make, "layout": phase_layout, "assign": phase_assign,
          "reset": phase_reset, "gen": phase_gen, "read": phase_read, "overview": phase_overview,
          "save": phase_save}
DEFERRED = os.path.join(REPORTS, "pypcg_city_deferred.json")


def _defer(phase, args):
    """Run a long phase on the next editor tick and write its result to DEFERRED. A call that blocks the
    game thread longer than the websocket keepalive loses its reply ("connection closed mid-call", traps.md 88),
    while the script itself runs on; deferred, the call returns at once and the result is read from the file."""
    _save(DEFERRED, {"phase": phase, "state": "queued"})
    handle = {}

    def tick(_dt):
        unreal.unregister_slate_post_tick_callback(handle["h"])
        try:
            result = json.loads(json.dumps(PHASES[phase](args), default=str))
            _save(DEFERRED, {"phase": phase, "state": "done", "result": result})
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
