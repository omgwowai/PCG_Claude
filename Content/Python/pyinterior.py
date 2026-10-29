# pyinterior.py -- PyInterior (docs/superpowers/specs/2026-10-28-pyinterior-design.md): rule-driven life-sim interiors,
# one phase per call. Every phase but build / level / probe runs only in /Game/PyPCG/L_PyInterior.
#   level {"reload"?}             create /Game/PyPCG/L_PyInterior from Template_Default (or open it; reload: reopen it from
#                                 disk, refused while the map has unsaved changes); UObject globals purged
#   probe                         read-only: can a spline component be added to an actor here (SubobjectDataSubsystem)?
#   build                         describe -> /Game/PyPCG/Interior/PCGI_House, structural check, save on 0 diffs
#   site                          the demo street: lawn, road, pavements (static mesh actors, PyInterior/Site)
#   houses                        the demo houses (pypcg.interior.demo): a PCG volume each, its closed footprint spline,
#                                 tags PyInterior_House + its name; replaces the previous ones
#   assign {"params": {...}}      graph, seed, style and any overrides on every house (or {"house": name})
#   gen {"house": name}           generate one house or all
#   read {"house": name}          Summary + Rooms + instances per house -> Saved/Reports/pyinterior_read.json
#   shape {"house", "shape" | "points" | "size"}   give a house a new outline (the dynamic test); it regenerates
#   shot {"view": "overview" | "street"} | {"house", "view": "top" | "angle" | "inside", "tag"}   one screenshot
#                                 | {"house", "view": "room", "room": "Living", "corner": [-1, -1]}   eye height in a room
#   status                        houses, outlines, generated flags, instance counts
#   save {"defer": true}          save the level
import gc
import json
import math
import os
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
REPORTS = os.path.join(_REPO, "Saved", "Reports")
ASSET = "/Game/PyPCG/Interior/PCGI_House"
CUBE = "/Engine/BasicShapes/Cube.Cube"
MAT = "/Game/PyPCG/Interior/Materials/MI_PyInt_%s.MI_PyInt_%s"


def _save(name, data):
    os.makedirs(REPORTS, exist_ok=True)
    with open(os.path.join(REPORTS, name), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, default=str)


def _eas():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _les():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def _tags(a):
    return {str(t) for t in a.get_editor_property("tags")}


def _require(what):
    from pypcg import level
    from pypcg.interior import LEVEL
    return level.require(LEVEL, "pyinterior.py " + what)


def _houses(name=None):
    from pypcg.interior import HOUSE_TAG
    out = [a for a in _eas().get_all_level_actors() if HOUSE_TAG in _tags(a)]
    if name:
        out = [a for a in out if str(a.get_actor_label()) == name]
    return sorted(out, key=lambda a: str(a.get_actor_label()))


def _spline(actor):
    return actor.get_component_by_class(unreal.SplineComponent)


def _purge():
    def holds(v):
        if isinstance(v, (unreal.Object, unreal.StructBase)):
            return True
        if isinstance(v, (list, tuple, set)):
            return any(holds(x) for x in v)
        if isinstance(v, dict):
            return any(holds(x) for x in v.values())
        return False
    dropped = []
    for k, v in list(globals().items()):
        if k.startswith("__") or callable(v) or isinstance(v, type):
            continue
        try:
            if holds(v):
                del globals()[k]
                dropped.append(k)
        except Exception:
            continue
    gc.collect()
    return dropped


def phase_level(args):
    from pypcg import level
    from pypcg.interior import LEVEL, TEMPLATE_MAP
    R = {"purged": _purge(), "before": level.current_map()}
    if args.get("reload") and R["before"] == LEVEL:
        # reopen from disk (does the saved level keep its splines and output?); unsaved changes to the map would be lost
        dirty = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
        if dirty:
            return dict(R, refused="unsaved map: %s" % dirty)
        R["reloaded"] = _les().load_level(LEVEL)
    elif R["before"] != LEVEL:
        if unreal.EditorAssetLibrary.does_asset_exist(LEVEL):
            R["loaded"] = _les().load_level(LEVEL)
        else:
            R["created"] = _les().new_level_from_template(LEVEL, TEMPLATE_MAP)
    R["after"] = level.current_map()
    R["actors"] = sorted("%s (%s)" % (a.get_actor_label(), a.get_class().get_name()) for a in _eas().get_all_level_actors())
    return R


def _add_spline(actor):
    """A SplineComponent added to a placed actor as an instance component (what the Details panel's Add does)."""
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=unreal.SplineComponent,
                                          blueprint_context=None)
    res = sds.add_new_subobject(params)
    handle = res[0] if isinstance(res, tuple) else res
    data = unreal.SubobjectDataBlueprintFunctionLibrary.get_data(handle)
    return unreal.SubobjectDataBlueprintFunctionLibrary.get_object(data)


def phase_probe(args):
    R = {"has_sds": hasattr(unreal, "SubobjectDataSubsystem"), "has_params": hasattr(unreal, "AddNewSubobjectParams")}
    if args.get("try"):
        refused = _require("probe")
        if refused:
            return refused
        a = _eas().spawn_actor_from_class(unreal.PCGVolume, unreal.Vector(0.0, 0.0, -5000.0), unreal.Rotator())
        try:
            sc = _add_spline(a)
            R["added"] = sc.get_class().get_name() if sc else None
            R["found"] = bool(_spline(a))
            R["points"] = _spline(a).get_number_of_spline_points() if _spline(a) else None
        finally:
            R["destroyed"] = _eas().destroy_actor(a)
    return R


def phase_build(args):
    from pypcg import build, compare
    from pypcg.interior import graphs as IG
    ir = IG.house().to_ir(None)
    diffs = build.build_slim(ir, ASSET, save=bool(args.get("save", True)))
    out = {"asset": ASSET, "nodes": len(ir["nodes"]), "diffs": len(diffs), "first": compare.format_diffs(diffs, 10)}
    _save("pyinterior_build.json", out)
    return out


def _box_actor(label, x0, y0, x1, y1, z0, z1, mat, folder="PyInterior/Site"):
    a = _eas().spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)),
                                      unreal.Rotator())
    a.set_actor_label(label)
    a.set_editor_property("tags", ["PyInterior_Site"])
    a.set_folder_path(folder)
    smc = a.static_mesh_component
    smc.set_static_mesh(unreal.load_asset(CUBE))
    smc.set_material(0, unreal.load_asset(MAT % (mat, mat)))
    a.set_actor_scale3d(unreal.Vector((x1 - x0) / 100.0, (y1 - y0) / 100.0, (z1 - z0) / 100.0))
    return a


def phase_site(args):
    refused = _require("site")
    if refused:
        return refused
    from pypcg.interior import demo
    for a in list(_eas().get_all_level_actors()):
        if "PyInterior_Site" in _tags(a):
            _eas().destroy_actor(a)
    hs = demo.houses()
    xs = [p[0] for _n, shape, loc, yaw, _s, _d in hs for p in demo.world_points(shape, loc, yaw)]
    ys = [p[1] for _n, shape, loc, yaw, _s, _d in hs for p in demo.world_points(shape, loc, yaw)]
    x0, x1 = min(xs) - 2000.0, max(xs) + 2000.0
    y0, y1 = min(ys) - 2000.0, max(ys) + 2000.0
    made = [
        _box_actor("PyInterior_Lawn", x0, y0, x1, y1, -60.0, -31.0, "Forest"),
        _box_actor("PyInterior_Road", x0, -400.0, x1, 400.0, -60.0, -29.0, "Charcoal"),
        _box_actor("PyInterior_Pavement_N", x0, 400.0, x1, 650.0, -60.0, -25.0, "Greige"),
        _box_actor("PyInterior_Pavement_S", x0, -650.0, x1, -400.0, -60.0, -25.0, "Greige"),
    ]
    # the template's own floor would cut through the houses
    hidden = []
    for a in _eas().get_all_level_actors():
        if a.get_class().get_name() == "StaticMeshActor" and "PyInterior_Site" not in _tags(a):
            sm = a.static_mesh_component.get_editor_property("static_mesh")
            if sm and "Floor" in sm.get_name():
                a.set_actor_location(unreal.Vector(a.get_actor_location().x, a.get_actor_location().y, -100.0), False, False)
                hidden.append(str(a.get_actor_label()))
    return {"site": [str(a.get_actor_label()) for a in made], "lowered": hidden, "bounds": [x0, y0, x1, y1]}


def _write_outline(actor, pts):
    sc = _spline(actor)
    sc.set_spline_points([unreal.Vector(p[0], p[1], p[2]) for p in pts], unreal.SplineCoordinateSpace.WORLD, False)
    for i in range(len(pts)):
        sc.set_spline_point_type(i, unreal.SplinePointType.LINEAR, False)
    sc.set_closed_loop(True, False)
    sc.update_spline()
    back = [sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD) for i in range(sc.get_number_of_spline_points())]
    return round(max(abs(b.x - p[0]) + abs(b.y - p[1]) for b, p in zip(back, pts)), 4) if len(back) == len(pts) else 1e9


def phase_houses(args):
    refused = _require("houses")
    if refused:
        return refused
    from pypcg.interior import HOUSE_TAG, demo
    gone = [str(a.get_actor_label()) for a in _houses() if _eas().destroy_actor(a)]
    out = {"destroyed": gone, "houses": []}
    for name, shape, loc, yaw, style, seed in demo.houses():
        a = _eas().spawn_actor_from_class(unreal.PCGVolume, unreal.Vector(*loc), unreal.Rotator(pitch=0.0, yaw=yaw, roll=0.0))
        a.set_actor_label(name)
        a.set_editor_property("tags", [HOUSE_TAG, name])
        a.set_folder_path("PyInterior/Houses")
        brush = a.get_component_by_class(unreal.BrushComponent)
        if brush is not None:
            brush.set_visibility(False, False)
        if _spline(a) is None:
            _add_spline(a)
        err = _write_outline(a, demo.world_points(shape, loc, yaw))
        pc = a.get_component_by_class(unreal.PCGComponent)
        pc.set_editor_property("regenerate_in_editor", False)
        out["houses"].append({"name": name, "shape": shape, "outline_error_cm": err})
    return out


def phase_assign(args):
    refused = _require("assign")
    if refused:
        return refused
    from pypcg import census
    from pypcg.interior import demo
    table = {n: (style, seed) for n, _s, _l, _y, style, seed in demo.houses()}
    graph = unreal.EditorAssetLibrary.load_asset(ASSET)
    out = {}
    for a in _houses(args.get("house")):
        name = str(a.get_actor_label())
        style, seed = table.get(name, ("Scandi", 1))
        pc = a.get_component_by_class(unreal.PCGComponent)
        pc.set_editor_property("regenerate_in_editor", False)
        pc.set_graph(graph)
        try:
            pc.set_editor_property("generation_trigger", unreal.PCGComponentGenerationTrigger.GENERATE_ON_LOAD)
        except Exception as ex:
            out["trigger_error"] = str(ex)[:200]
        pc.set_editor_property("seed", int(seed))
        over = {"Seed": int(seed), "Style": style}
        over.update(args.get("params") or {})
        res = census.apply_overrides(pc, over)
        # live editing: dragging the outline's points regenerates the house
        pc.set_editor_property("regenerate_in_editor", bool(args.get("live", True)))
        out[name] = {"style": style, "seed": seed, "skipped": res["skipped"]}
    return out


def _flush():
    """Python's spline edits do not invalidate PCG's cache: Get Spline Data (Self) would hand the Python node the old outline
    (measured 2026-10-28: a 13 x 9 m outline still planned as the 10.5 x 8 m house until the cache was flushed)."""
    unreal.SystemLibrary.execute_console_command(None, "pcg.FlushCache")


def phase_gen(args):
    refused = _require("gen")
    if refused:
        return refused
    _flush()
    done = []
    for a in _houses(args.get("house")):
        pc = a.get_component_by_class(unreal.PCGComponent)
        pc.generate_local(True)
        done.append(str(a.get_actor_label()))
    return {"generating": done}


def _summary(pc):
    from pypcg.ue import convert
    summary, rooms = None, []
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        try:
            v = convert.from_pcg(td.get_editor_property("data").get_editor_property("data"))
        except TypeError:
            continue
        tags = {str(t) for t in td.get_editor_property("tags")}
        if "Summary" in tags and hasattr(v, "values"):
            summary = dict(v.values)
        elif "Room" in tags and hasattr(v, "attrs"):
            for i in range(len(v)):
                row = {k: col[i] for k, col in v.attrs.items() if k in ("Type", "Area", "Windows", "Items", "SizeX", "SizeY")}
                row["loc"] = [round(c, 1) for c in v.loc[i]]
                rooms.append(row)
    return summary, rooms


def phase_read(args):
    refused = _require("read")
    if refused:
        return refused
    from pypcg import census
    out = {}
    for a in _houses(args.get("house")):
        pc = a.get_component_by_class(unreal.PCGComponent)
        summary, rooms = _summary(pc)
        inst = census.instances(a)
        out[str(a.get_actor_label())] = {"generated": bool(pc.get_editor_property("generated")), "summary": summary,
                                         "rooms": rooms, "instances": inst["total"], "meshes": len(inst["per_mesh"]),
                                         "pass_ok": bool(summary) and summary.get("failures", 1) == 0 and inst["total"] > 0}
    _save("pyinterior_read.json", out)
    brief = {k: {"ok": v["pass_ok"], "program": (v["summary"] or {}).get("program"), "rooms": (v["summary"] or {}).get("rooms"),
                 "failures": (v["summary"] or {}).get("failures"), "first_failure": (v["summary"] or {}).get("first_failure"),
                 "instances": v["instances"]} for k, v in out.items()}
    return brief


def phase_shape(args):
    refused = _require("shape")
    if refused:
        return refused
    from pypcg.interior import demo
    a = _houses(args["house"])
    if not a:
        return {"abort": "no house %r" % args["house"]}
    a = a[0]
    loc = a.get_actor_location()
    yaw = a.get_actor_rotation().yaw
    if "points" in args:
        local = [tuple(p) for p in args["points"]]
    elif "size" in args:
        w, d = args["size"]
        local = [(0, 0), (w, 0), (w, d), (0, d)]
    else:
        local = demo.SHAPES[args["shape"]]
    a_ = math.radians(yaw)
    ex, ey = (-math.sin(a_), math.cos(a_)), (-math.cos(a_), -math.sin(a_))
    pts = [(loc.x + x * ex[0] + y * ey[0], loc.y + x * ex[1] + y * ey[1], loc.z) for x, y in local]
    err = _write_outline(a, pts)
    _flush()
    pc = a.get_component_by_class(unreal.PCGComponent)
    pc.generate_local(True)
    return {"house": str(a.get_actor_label()), "outline": local, "outline_error_cm": err}


def phase_status(args):
    from pypcg import census, level
    out = {"map": level.current_map(), "houses": {}}
    for a in _houses():
        sc, pc = _spline(a), a.get_component_by_class(unreal.PCGComponent)
        g = pc.get_graph()
        out["houses"][str(a.get_actor_label())] = {
            "points": sc.get_number_of_spline_points() if sc else None, "closed": bool(sc.is_closed_loop()) if sc else None,
            "graph": g.get_name() if g else None, "generated": bool(pc.get_editor_property("generated")),
            "instances": census.instances(a)["total"]}
    return out


def _house_box(a):
    sc = _spline(a)
    pts = [sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD) for i in range(sc.get_number_of_spline_points())]
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def phase_shot(args):
    for m in ("pcg_sa_shots", "pcg_sa_geom"):
        sys.modules.pop(m, None)
    import pcg_sa_geom as G
    import pcg_sa_shots as S
    refused = _require("shot")
    if refused:
        return refused
    for a in _houses():
        sc = _spline(a)
        if sc is not None:
            try:
                sc.set_editor_property("draw_debug", False)
            except Exception:
                pass
    view = args.get("view", "overview")
    if "house" in args:
        a = _houses(args["house"])[0]
        x0, y0, x1, y1 = _house_box(a)
        cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
        span = max(x1 - x0, y1 - y0)
        yaw = a.get_actor_rotation().yaw
        if view == "top":
            loc, rot = G.orbit_camera([cx, cy, 0.0], span * 1.05, yaw + 180.0, 89.0, 1.0, min_height=0.0)
        elif view == "angle":
            loc, rot = G.orbit_camera([cx, cy, 50.0], span * 1.0, yaw + 180.0 + float(args.get("az", 35.0)),
                                      float(args.get("elev", 52.0)), 1.0, min_height=0.0)
        elif view == "room":
            # eye height in a corner of the named room (its clear floor from the Rooms output), looking across it
            _s, rooms = _summary(a.get_component_by_class(unreal.PCGComponent))
            r = next((x for x in rooms if x.get("Type") == args.get("room", "Living")), None)
            if r is None:
                return {"abort": "no %s room in %s: %s" % (args.get("room", "Living"), args["house"],
                                                          [x.get("Type") for x in rooms])}
            a_ = math.radians(yaw)
            ex, ey = (-math.sin(a_), math.cos(a_)), (-math.cos(a_), -math.sin(a_))
            sx, sy = args.get("corner", [-1, -1])
            k = float(args.get("inset", 0.4))
            ox, oy = sx * k * r["SizeX"], sy * k * r["SizeY"]
            rx, ry, rz = r["loc"]
            loc = [rx + ox * ex[0] + oy * ey[0], ry + ox * ex[1] + oy * ey[1], rz - 5.0 + float(args.get("height", 165.0))]
            rot = [float(args.get("pitch", -12.0)), math.degrees(math.atan2(ry - loc[1], rx - loc[0])), 0.0]
        else:
            loc, rot = list(args["eye"]), list(args["rot"])
    else:
        c = args.get("centre", [3500.0, 0.0, 0.0])
        loc, rot = G.orbit_camera(list(c), float(args.get("radius", 7000.0)), float(args.get("az", -65.0)),
                                  float(args.get("elev", 48.0)), 1.0, min_height=0.0)
    les = _les()
    les.set_level_viewport_camera_info(unreal.Vector(*loc), unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]),
                                       les.get_active_viewport_config_key())
    name = "pyinterior_%s%s%s.png" % (args.get("house", "street").lower(), "_" + view, ("_" + args["tag"]) if args.get("tag") else "")
    return {"fired": S.fire(name, les), "camera": [loc, rot]}


def phase_save(args):
    refused = _require("save")
    if refused:
        return refused
    for a in _houses():
        a.modify()
    saved = bool(_les().save_current_level())
    return {"saved": saved}


PHASES = {"level": phase_level, "probe": phase_probe, "build": phase_build, "site": phase_site, "houses": phase_houses,
          "assign": phase_assign, "gen": phase_gen, "read": phase_read, "shape": phase_shape, "status": phase_status,
          "shot": phase_shot, "save": phase_save}
DEFERRED = os.path.join(REPORTS, "pyinterior_deferred.json")


def _defer(phase, args):
    _save("pyinterior_deferred.json", {"phase": phase, "state": "queued"})
    handle = {}

    def tick(_dt):
        unreal.unregister_slate_post_tick_callback(handle["h"])
        try:
            _save("pyinterior_deferred.json", {"phase": phase, "state": "done", "result": PHASES[phase](args)})
        except Exception as exc:
            _save("pyinterior_deferred.json", {"phase": phase, "state": "error", "error": "%s: %s" % (type(exc).__name__, str(exc)[:800])})
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
