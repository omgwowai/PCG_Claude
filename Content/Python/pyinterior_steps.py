# pyinterior_steps.py -- the docs' step-by-step pictures, never saved: House_05's outline (or another demo shape) built on the
# empty lawn west of the street up to one stage of the chain, as temporary static mesh actors tagged PyInterior_Preview, then
# one screenshot. The plan uses the stage's own rng (Random("seed:201")) and parameters, so the last step is the level's house.
#   {"step": "footprint" | "rooms" | "doors" | "windows" | "furniture" | "full", "wallcut": 110,
#    "view": "angle" | "front" | "top" | "room" ({"room": "Living", "corner": [0, -1]}), "tag": "1_footprint",
#    "shape": "lshape", "style": "Warm", "seed": 5}          the previous step's actors are removed first
#   {"step": "plan"}    read-only: program, rooms, doors, windows and pieces of the plan, no actors
#   {"step": "clear"}   remove the preview actors. Spawning and removing leave the map modified: do not save it with previews
#                       in it, and close or switch levels without saving. Reopening the level from a bridge call right
#                       after removing actors crashed the editor (trap 123), so this script never loads a level.
# Steps that spawn or clear run only in /Game/PyPCG/L_PyInterior.
# footprint: one slab per wing (wings tinted apart); rooms: floors, walls, paint, skirting (no openings); doors: + walls cut
# at the passages, frames and leaves; windows: + windows; furniture: + furniture as primitive recipes; full: StarterContent
# meshes (RealMeshes on).
import json
import math
import random
import sys

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.") or m in ("pcg_sa_shots", "pcg_sa_geom")]:
    del sys.modules[_m]
from pypcg import level  # noqa: E402
from pypcg.interior import LEVEL  # noqa: E402
from pypcg.interior import assemble as A  # noqa: E402
from pypcg.interior import demo  # noqa: E402
from pypcg.interior import footprint as F  # noqa: E402
from pypcg.interior import house as H  # noqa: E402
from pypcg.interior import program as P  # noqa: E402
from pypcg.stages import i01_house  # noqa: E402

TAG = "PyInterior_Preview"
LOC = (-1650.0, 1200.0, 0.0)          # the lawn west of House_01, facing the road like the north houses
YAW = -90.0
WING_TINTS = ("Mustard", "Teal", "Terracotta", "Sky")
STEPS = ("footprint", "rooms", "doors", "windows", "furniture", "full")


def _eas():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def clear():
    gone = 0
    for a in list(_eas().get_all_level_actors()):
        if TAG in [str(t) for t in a.get_editor_property("tags")]:
            _eas().destroy_actor(a)
            gone += 1
    return gone


def plan_of(args):
    shape = args.get("shape", "lshape")
    fp = F.build(demo.world_points(shape, LOC, YAW), LOC, YAW)
    rng = random.Random("%d:%d" % (int(args.get("seed", 5)), i01_house.STAGE))
    walls = {"ext": 25.0, "int": 12.0, "height": 270.0}
    plan, doors, wins, places, fails = H.plan_house(fp, P.choose(fp.area_m2), rng, walls)
    return fp, rng, plan, doors, wins, places, fails


def items_of(step, args):
    fp, rng, plan, doors, wins, places, fails = plan_of(args)
    params = dict(A.DEFAULTS, Style=args.get("style", "Warm"), WallCut=float(args.get("wallcut", 0.0)),
                  RealMeshes=(step == "full"))
    upto = STEPS.index(step)
    d = doors if upto >= 2 else []
    w = wins if upto >= 3 else []
    p = places if upto >= 4 else []
    items = A.house(plan, d, w, p, params, rng)        # the palette draws first, so every step gets the same colours
    if step == "footprint":
        items = [i for i in items if i["role"] == "foundation"]
        for k, i in enumerate(items):
            i["mat"] = A.mat(WING_TINTS[k % len(WING_TINTS)])
    return fp, plan, items


def spawn(items):
    meshes, mats = {}, {}
    for i in items:
        if i["mesh"] not in meshes:
            meshes[i["mesh"]] = unreal.load_asset(i["mesh"])
        if i["mat"] and i["mat"] not in mats:
            mats[i["mat"]] = unreal.load_asset(i["mat"])
        x, y, z = i["loc"]
        p, yw, r = i["rot"]
        a = _eas().spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(x, y, z), unreal.Rotator(pitch=p, yaw=yw, roll=r))
        a.set_actor_scale3d(unreal.Vector(*i["scale"]))
        a.set_editor_property("tags", [TAG])
        a.set_folder_path("PyInterior/Preview")
        smc = a.static_mesh_component
        smc.set_static_mesh(meshes[i["mesh"]])
        if i["mat"]:
            smc.set_material(0, mats[i["mat"]])
    return len(items)


def shoot(fp_pts, args, name, fp=None, plan=None):
    import pcg_sa_geom as G
    import pcg_sa_shots as S
    xs, ys = [p[0] for p in fp_pts], [p[1] for p in fp_pts]
    cx, cy = 0.5 * (min(xs) + max(xs)), 0.5 * (min(ys) + max(ys))
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    view = args.get("view", "angle")
    if view == "room":
        # eye height in a corner of the named room's clear floor, looking across it (pyinterior.py shot view "room")
        from pypcg.interior import layout as L
        r = next(x for x in plan.rooms if x.type == args.get("room", "Living"))
        c = L.clear_rect(r.rect, fp, plan.walls)
        sx, sy = args.get("corner", [0, -1])
        k = float(args.get("inset", 0.42))
        ex0, ey0, _z = fp.to_world(c.cx + sx * k * c.w, c.cy + sy * k * c.h, 0.0)
        tx, ty, _z = fp.to_world(c.cx, c.cy, 0.0)
        loc = [ex0, ey0, float(args.get("height", 165.0))]
        rot = [float(args.get("pitch", -10.0)), math.degrees(math.atan2(ty - ey0, tx - ex0)) + float(args.get("turn", 0.0)), 0.0]
    elif view == "top":
        loc, rot = G.orbit_camera([cx, cy, 0.0], span * 1.05, YAW + 180.0, 89.0, 1.0, min_height=0.0)
    elif view == "front":
        loc, rot = G.orbit_camera([cx, cy, 120.0], span * float(args.get("radius", 1.25)), YAW + float(args.get("az", 20.0)),
                                  float(args.get("elev", 24.0)), 1.0, min_height=0.0)
    else:
        loc, rot = G.orbit_camera([cx, cy, 50.0], span * float(args.get("radius", 1.0)),
                                  YAW + 180.0 + float(args.get("az", 35.0)), float(args.get("elev", 52.0)), 1.0, min_height=0.0)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    les.set_level_viewport_camera_info(unreal.Vector(*loc), unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]),
                                       les.get_active_viewport_config_key())
    return S.fire(name, les), [loc, rot]


def run(args):
    step = args.get("step")
    if step == "plan":
        fp, _rng, plan, doors, wins, places, fails = plan_of(args)
        return {"program": plan.program.name, "area_m2": fp.area_m2, "wings": len(fp.wings),
                "rooms": [r.type for r in plan.rooms], "doors": len(doors), "sliding": sum(1 for d in doors if d.sliding),
                "windows": len(wins), "pieces": len(places), "fails": fails}
    if step != "clear" and step not in STEPS:
        return {"abort": "step must be one of %s, plan or clear" % (STEPS,)}
    refused = level.require(LEVEL, "pyinterior_steps.py " + step)
    if refused:
        return refused
    if step == "clear":
        return {"removed": clear()}
    removed = clear()
    fp, plan, items = items_of(step, args)
    n = spawn(items)
    pts = demo.world_points(args.get("shape", "lshape"), LOC, YAW)
    fired, cam = shoot(pts, args, "pyinterior_step_%s.png" % args.get("tag", step), fp, plan)
    return {"step": step, "removed": removed, "actors": n, "program": plan.program.name, "fired": fired, "camera": cam}


mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
