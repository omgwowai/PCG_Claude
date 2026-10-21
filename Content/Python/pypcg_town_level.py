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

# pypcg_town_level.py -- shape the template copy into the town (Task 25), then bind its roles.
# Args: {"phase": "make" | "layout" | "bind" | "save"}
#   make   : create /Game/PyPCG/L_PyTown as a template copy of the demo level and open it. Refuses if
#            the demo is current afterwards, and only ever *reads* the demo package.
#   layout : cleanup every volume, destroy unneeded control actors, move landmark volumes, rewrite the
#            control splines from town_layout.SPLINES, audit the actor tags the kept native nodes read
#   bind   : resolve the 13 roles to actors of this level -> pypcg/profiles/town_bindings.json
#   save   : save L_PyTown itself -- never the demo, never save-all
#
# No PCG generation happens here (Task 27 does that): `layout` cleans up and writes splines only.
# Spline points are written in WORLD space after any actor move (traps.md 30: read before moving,
# write after; the spline actors this task rewrites are never moved, so one pass is enough).
LEVEL = "L_PyTown"
LEVEL_PATH = "/Game/PyPCG/L_PyTown"
TEMPLATE = "/CitySamplePCG/Levels/L_CitySamplePCG_Demo"
DEMO_LEVEL = "L_CitySamplePCG_Demo"
BINDINGS = os.path.join(_PY, "pypcg", "profiles", "town_bindings.json")


def _level_name(les):
    """The current map's short name ("L_PyTown"). The current ULevel is always named PersistentLevel, so
    the map name comes from its path (/Game/PyPCG/L_PyTown.L_PyTown:PersistentLevel)."""
    lvl = les.get_current_level()
    if lvl is None:
        return ""
    return lvl.get_path_name().split(":", 1)[0].rsplit(".", 1)[-1]


def _on_town(les):
    """True when L_PyTown is the level being edited. Nothing else may be written."""
    name = _level_name(les)
    if name == DEMO_LEVEL:
        raise RuntimeError("the demo level is current; refusing to touch it")
    return name == LEVEL


def _actor(label):
    from pypcg import census
    a = census.actor_by_label(label)
    if a is None:
        raise RuntimeError("no actor labelled %s" % label)
    return a


def _world_points(sc):
    return [sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD)
            for i in range(sc.get_number_of_spline_points())]


def _write_spline(actor, spec):
    """Positions, closedness and point types, then read every point back.

    `set_spline_points` resets all point types to CurveAuto (traps.md 27), so the LINEAR points are
    typed after the positions are in. The points carry no rotation: no spline this task writes feeds a
    corner-reading grammar, and the ones that do (stage 16's park paths) are written by Task 16 itself.
    """
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
    back = _world_points(sc)
    err = max(abs(a.x - b[0]) + abs(a.y - b[1]) + abs(a.z - b[2])
              for a, b in zip(back, spec["points"])) if len(back) == len(spec["points"]) else 1e9
    return {"points": len(back), "closed": bool(sc.is_closed_loop()),
            "linear": sorted({str(sc.get_spline_point_type(i)).rsplit(".", 1)[-1].rstrip(":>")
                              for i in range(len(back))}),
            "max_error_cm": round(err, 4)}


def _tags(a):
    try:
        return [str(t) for t in a.get_editor_property("tags")]
    except Exception:
        return []


def phase_make():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ael = unreal.EditorAssetLibrary
    out = {"template": TEMPLATE, "target": LEVEL_PATH, "current_before": str(les.get_current_level())}
    out["existed"] = bool(ael.does_asset_exist(LEVEL_PATH))
    attempts = []
    ok = False
    if not out["existed"]:
        try:
            ok = bool(les.new_level_from_template(LEVEL_PATH, TEMPLATE))
            attempts.append({"path": "new_level_from_template", "ok": ok})
        except Exception as ex:
            attempts.append({"path": "new_level_from_template",
                             "error": "%s: %s" % (type(ex).__name__, str(ex)[:300])})
        if not ok:
            try:
                world = unreal.EditorLoadingAndSavingUtils.new_map_from_template(TEMPLATE, False)
                ok = bool(unreal.EditorLoadingAndSavingUtils.save_map(world, LEVEL_PATH)) if world else False
                attempts.append({"path": "new_map_from_template+save_map", "ok": ok})
            except Exception as ex:
                attempts.append({"path": "new_map_from_template+save_map",
                                 "error": "%s: %s" % (type(ex).__name__, str(ex)[:300])})
    else:
        ok = bool(les.load_level(LEVEL_PATH))
        attempts.append({"path": "load_level", "ok": ok})
    out["attempts"] = attempts
    out["current_after"] = str(les.get_current_level())
    # The demo must not be the level we edit; a copy that landed on the demo would be a disaster.
    out["demo_is_current"] = _level_name(les) == DEMO_LEVEL
    out["on_target"] = _level_name(les) == LEVEL and LEVEL_PATH.split("/")[-1] in out["current_after"]
    out["gate"] = {"pass": bool(ok and out["on_target"] and not out["demo_is_current"])}
    return out


def phase_layout():
    from pypcg import census, stages
    from pypcg.profiles import town_layout as T
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not _on_town(les):
        return {"abort": "L_PyTown is not the current level"}
    out = {"cleaned": 0, "destroyed": [], "missing_destroy": [], "moved": {}, "splines": {},
           "volumes": 0, "graphs": [], "tags": {}}
    for v in census.volumes():
        pc = v.get_component_by_class(unreal.PCGComponent)
        # Cleanup only removes; it generates nothing. Activate first for the same reason generation
        # needs it (traps.md 18): a component that is not activated skips the work silently.
        pc.activate(True)
        pc.cleanup_local(True)
        out["cleaned"] += 1
        out["volumes"] += 1
        g = pc.get_graph()
        out["graphs"].append(g.get_name() if g else None)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for label in T.DESTROY:
        a = census.actor_by_label(label)
        if a is None:
            out["missing_destroy"].append(label)
        elif eas.destroy_actor(a):
            out["destroyed"].append(label)
    for label, move in T.VOLUME_MOVES.items():
        a = _actor(label)
        z = a.get_actor_location().z
        a.set_actor_location(unreal.Vector(move["xy"][0], move["xy"][1], z), False, False)
        if "yaw" in move:
            r = a.get_actor_rotation()
            a.set_actor_rotation(unreal.Rotator(pitch=r.pitch, yaw=move["yaw"], roll=r.roll), False)
        loc, rot = a.get_actor_location(), a.get_actor_rotation()
        out["moved"][label] = {"loc": [round(loc.x, 2), round(loc.y, 2), round(loc.z, 2)],
                               "yaw": round(rot.yaw, 4)}
    for label, spec in T.SPLINES.items():
        out["splines"][label] = _write_spline(_actor(label), spec)
    # The tags the kept native nodes read must land on the control actors that survive. A tag with no
    # carrier is a silent zero in the stage that reads it (traps.md 1, 66).
    carriers = {}
    for a in eas.get_all_level_actors():
        for t in _tags(a):
            carriers.setdefault(t, set()).add(str(a.get_actor_label()))
    for tag, labels in T.TAGS.items():
        got = sorted(carriers.get(tag, set()))
        out["tags"][tag] = {"expected": labels, "carriers": got, "ok": got == sorted(labels)}
    expected_graphs = sorted(stages.name(n) for n, _l, _m, _t in stages.STAGES)
    out["missing_graphs"] = [g for g in expected_graphs if g not in out["graphs"]]
    out["ok"] = bool(
        not out["missing_destroy"]
        and len(out["destroyed"]) == len(T.DESTROY)
        and out["volumes"] == 18 and not out["missing_graphs"]
        and all(s["max_error_cm"] < 0.5 for s in out["splines"].values())
        and all(v["ok"] for v in out["tags"].values())
    )
    return out


def phase_bind():
    from pypcg import census
    from pypcg.profiles import official, town_layout as T
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not _on_town(les):
        return {"abort": "L_PyTown is not the current level"}
    out = {"bindings": {}, "classes": {}, "missing": [], "wrong_level": [], "wrong_class": [],
           "written": False}
    for role, label in sorted(official.ROLE_LABELS.items()):
        a = census.actor_by_label(label)
        if a is None:
            out["missing"].append(role)
            continue
        out["bindings"][role] = a.get_path_name()
        out["classes"][role] = a.get_class().get_name()
    # Every role must be an actor of THIS level, and one whose class the reading node can use: the
    # spline roles are plain actors, everything else is a volume.
    spline_roles = {r for r, l in official.ROLE_LABELS.items() if l in T.SPLINES}
    for role, path in out["bindings"].items():
        if LEVEL_PATH + "." + LEVEL not in path:
            out["wrong_level"].append(role)
        cls = out["classes"][role]
        if role in spline_roles:
            if cls not in ("Actor", "SplineActor"):
                out["wrong_class"].append([role, cls])
        elif cls != "PCGVolume":
            out["wrong_class"].append([role, cls])
    missing_roles = sorted(set(official.ROLES) - set(out["bindings"]))
    out["missing"] = sorted(set(out["missing"]) | set(missing_roles))
    if not out["missing"] and not out["wrong_level"] and not out["wrong_class"] \
            and len(out["bindings"]) == len(official.ROLES) == len(official.ROLE_LABELS):
        os.makedirs(os.path.dirname(BINDINGS), exist_ok=True)
        with open(BINDINGS, "w", encoding="utf-8") as fh:
            json.dump(out["bindings"], fh, indent=1, sort_keys=True)
            fh.write("\n")
        out["written"] = True
    return out


def phase_save():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not _on_town(les):
        return {"abort": "L_PyTown is not the current level; refusing to save", "saved": False}
    return {"level": LEVEL_PATH, "saved": bool(les.save_current_level())}


def run(args):
    phase = str(args.get("phase", "layout"))
    phases = {"make": phase_make, "layout": phase_layout, "bind": phase_bind, "save": phase_save}
    if phase not in phases:
        return {"abort": "unknown phase %r" % phase}
    return phases[phase]()


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
