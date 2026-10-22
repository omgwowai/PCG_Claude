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
#   build {"save"}        describe + write /Game/PyPCG/City/PCG_PyCity, structural check (0 diffs), save
#   make                  create /Game/PyPCG/L_PyCity as a template copy of L_PyTown and open it
#   layout                (L_PyCity) keep one volume + the control actors: destroy the other stage volumes,
#                         relabel the Terrain volume PCG_PyCity, turn the two footprint volumes into tagged
#                         control actors (no graph)
#   bind                  the three control-actor roles -> pypcg/profiles/city_bindings.json
#   assign                PCG_PyCity -> the merged graph; the town's per-stage overrides, renamed
#   reset                 cleanup_local on the volume (regenerate_in_editor off)
#   gen                   activate + generate_local(True)
#   read {"pass"}         instances per mesh against the 18-volume town (Tools/data/pypcg_town_census.json)
#   overview {"view"}     one screenshot: top / street / wide
#   save                  save L_PyCity -- only that level, only with the merged graph on its one volume
LEVEL = "/Game/PyPCG/L_PyCity"
TEMPLATE = "/Game/PyPCG/L_PyTown"
REPORTS = os.path.join(_REPO, "Saved", "Reports")
TOWN_OVERRIDES = os.path.join(REPORTS, "pypcg_town_component_overrides.json")
LOG = os.path.join(_REPO, "Saved", "Logs", "PCG_Claude.log")
DESTROY_WHEN_MERGED = "the 15 stage volumes the merged graph replaces"


def _load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True)


def _pass_file(k):
    return os.path.join(REPORTS, "pypcg_city_pass%d.json" % k)


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
           "diffs": len(diffs), "first": compare.format_diffs(diffs, 15), "roles": city.ROLES,
           "refs_rewired": len(g.report["refs_rewired"]), "refs_kept": g.report["refs_kept"],
           "terrain": g.terrain}
    _save(os.path.join(REPORTS, "pypcg_city_build.json"), out)      # the reply can be lost on a long call
    return out


def phase_make(args):
    from pypcg import level
    les = _les()
    ael = unreal.EditorAssetLibrary
    if level.current_map() == level.DEMO:
        return {"abort": "the demo is current; open L_PyTown or another level first"}
    dirty = [str(p.get_name()) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    if dirty:
        return {"abort": "unsaved maps %s; not switching levels" % dirty}
    if ael.does_asset_exist(LEVEL):
        ok = bool(les.load_level(LEVEL))
        how = "load_level"
    else:
        ok = bool(les.new_level_from_template(LEVEL, TEMPLATE))
        how = "new_level_from_template"
    return {"how": how, "ok": ok, "current": level.current_map(), "gate": level.current_map() == LEVEL}


def phase_layout(args):
    from pypcg import census, combined, level, stages
    from pypcg.profiles import city
    refused = level.require(LEVEL, "pypcg_city.py layout")
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
            loc = a.get_actor_location()
            out["controls"][label] = {"tags": [str(t) for t in a.get_editor_property("tags")],
                                      "loc": [round(loc.x), round(loc.y)], "yaw": round(a.get_actor_rotation().yaw, 3)}
        elif eas.destroy_actor(a):
            out["destroyed"].append(label)
    out["pcg_actors_left"] = sorted(str(a.get_actor_label()) for a in census.volumes())
    out["ok"] = bool(out["volume"] and len(out["controls"]) == 2 and len(out["destroyed"]) == 15)
    return out


def phase_bind(args):
    from pypcg import census, level
    from pypcg.profiles import city, official
    refused = level.require(LEVEL, "pypcg_city.py bind")
    if refused:
        return refused
    roles, missing = {}, []
    for role in city.KEPT_ROLES:
        a = census.actor_by_label(official.ROLE_LABELS[role])
        if a is None or not a.get_path_name().startswith(LEVEL + "."):
            missing.append(role)
        else:
            roles[role] = a.get_path_name()
    if missing:
        return {"abort": "roles without an actor of L_PyCity: %s" % missing}
    with open(city.BINDINGS, "w", encoding="utf-8") as fh:
        json.dump(roles, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return {"written": city.BINDINGS, "roles": roles}


def phase_assign(args):
    from pypcg import census, combined, level
    from pypcg.profiles import city
    refused = level.require(LEVEL, "pypcg_city.py assign")
    if refused:
        return refused
    pc = _volume().get_component_by_class(unreal.PCGComponent)
    pc.set_editor_property("regenerate_in_editor", False)
    pc.set_graph(unreal.EditorAssetLibrary.load_asset(combined.ASSET))
    template = combined.component_overrides(_load(TOWN_OVERRIDES, {}))
    wanted = dict(template)
    wanted.update(city.COMPONENT_OVERRIDES)
    res = census.apply_overrides(pc, wanted)
    back = census.overrides(pc)
    # The template's debug and partition switches are not parameters of the slim graphs (ruling N5); the
    # town's own overrides must all land.
    lost = [k for k in city.COMPONENT_OVERRIDES if k in res["skipped"]]
    wrong = {k: [v, back.get(k)] for k, v in wanted.items() if k not in res["skipped"] and back.get(k) != v}
    return {"graph": pc.get_graph().get_path_name(), "seed": pc.get_editor_property("seed"),
            "set": len(res["set"]), "skipped": sorted(res["skipped"]), "town_overrides_lost": lost,
            "mismatched": wrong, "ok": not lost and not wrong}


def phase_reset(args):
    from pypcg import level
    refused = level.require(LEVEL, "pypcg_city.py reset")
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
    from pypcg import combined, level
    refused = level.require(LEVEL, "pypcg_city.py gen")
    if refused:
        return refused
    k = int(args.get("pass", 1))
    pc = _volume().get_component_by_class(unreal.PCGComponent)
    g = pc.get_graph()
    if g is None or g.get_path_name().split(".")[0] != combined.ASSET:
        return {"abort": "PCG_PyCity does not hold %s (run assign)" % combined.ASSET}
    _save(_pass_file(k), {"gen_at": time.time(), "log_offset": _log_size()})
    pc.activate(True)
    pc.generate_local(True)
    return {"pass": k, "graph": g.get_path_name()}


def _town_per_mesh():
    """The 18-volume town's instances per mesh, summed over its stages (pass 1 of the town run)."""
    p1 = _load(os.path.join(REPORTS, "pypcg_town_pass1.json"), {})
    per, by_stage = {}, {}
    for s, entry in p1.items():
        pm = entry.get("record", {}).get("instances", {}).get("per_mesh", {})
        by_stage[int(s)] = sum(pm.values())
        for m, c in pm.items():
            per[m] = per.get(m, 0) + c
    return per, by_stage


def phase_read(args):
    import time
    from pypcg import census, level
    refused = level.require(LEVEL, "pypcg_city.py read")
    if refused:
        return refused
    k = int(args.get("pass", 1))
    a = _volume()
    pc = a.get_component_by_class(unreal.PCGComponent)
    data = _load(_pass_file(k), {})
    inst = census.instances(a)
    town, town_by_stage = _town_per_mesh()
    diff = {m: [town.get(m, 0), inst["per_mesh"].get(m, 0)] for m in sorted(set(town) | set(inst["per_mesh"]))
            if town.get(m, 0) != inst["per_mesh"].get(m, 0)}
    try:
        items = census.outputs(pc)
    except Exception as ex:
        items = [{"error": str(ex)[:200]}]
    rec = {"read_at": time.time(), "since_gen_s": round(time.time() - data["gen_at"], 1) if "gen_at" in data else None,
           "generated": bool(pc.get_editor_property("generated")), "instances": inst["total"],
           "town_instances": sum(town.values()), "meshes": len(inst["per_mesh"]), "town_meshes": len(town),
           "differing_meshes": len(diff), "per_mesh_abs_diff": sum(abs(x - y) for x, y in diff.values()),
           "components": inst["components"], "output_items": len(items),
           "output_tags": sorted({t for it in items for t in it.get("tags", []) if ":" not in t}),
           "log": _log_since(data.get("log_offset", 0))}
    data.update(read=rec, per_mesh=inst["per_mesh"], diff=diff)
    _save(_pass_file(k), data)
    rec["diff_first"] = dict(list(diff.items())[:25])
    return rec


def phase_overview(args):
    from pypcg import level
    from pypcg.profiles import town_layout
    refused = level.require(LEVEL, "pypcg_city.py overview")
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
    (x0, y0, _), (x1, y1, _) = town_layout.city_bbox()
    center, radius = [(x0 + x1) / 2, (y0 + y1) / 2, 0.0], 0.5 * max(x1 - x0, y1 - y0)
    loc, rot = G.orbit_camera(center, radius, az, elev, mult, min_height=1500.0)
    les.set_level_viewport_camera_info(unreal.Vector(*loc), unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]),
                                       les.get_active_viewport_config_key())
    return {"fired": S.fire("pc_overview_%s.png" % args.get("view", "wide"), les), "promoted": promoted}


def phase_save(args):
    from pypcg import census, combined, level
    refused = level.require(LEVEL, "pypcg_city.py save")
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
    vol.modify()
    comps = sorted(c.get_class().get_name() for c in vol.get_components_by_class(unreal.ActorComponent))
    return {"saved": bool(_les().save_current_level()), "graphs": graphs, "volume_components": comps}


PHASES = {"build": phase_build, "make": phase_make, "layout": phase_layout, "bind": phase_bind,
          "assign": phase_assign, "reset": phase_reset, "gen": phase_gen, "read": phase_read,
          "overview": phase_overview, "save": phase_save}
DEFERRED = os.path.join(REPORTS, "pypcg_city_deferred.json")


def _defer(phase, args):
    """Run a long phase on the next editor tick and write its result to DEFERRED. A call that blocks the
    game thread longer than the websocket keepalive loses its reply ("connection closed mid-call"), while
    the script itself runs on; deferred, the call returns at once and the result is read from the file."""
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
