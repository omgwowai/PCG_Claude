"""PyInterior I1 -- a life-sim house's interior from its footprint (docs/superpowers/specs/2026-10-28-pyinterior-design.md).

The house actor's own closed spline is the footprint; the actor's forward is the front. The chain is pypcg.interior:
footprint -> program (area -> rooms, rule table) -> layout (zoning grammar) -> doors -> windows (wall grammar) ->
furnish (room recipes; a variant whose required furniture does not fit steps down, interior.house) -> assemble (walls,
paint, floors, doors, windows, furniture parts) -> checks. Parts carry each piece's mesh and slot-0 material for the native
spawner; Rooms one point per room; Summary the counts and failures."""
from pypcg.geo import Spline
from pypcg.interior import assemble as A
from pypcg.interior import checks as K
from pypcg.interior import footprint as F
from pypcg.interior import house as H
from pypcg.interior import layout as L
from pypcg.interior import program as P
from pypcg.stage_api import Param, volume_point
from pypcg.world import points as WP

STAGE = 201
RECORD = "i01"
DOC = """PyInterior House (室内): rooms, doors, windows and furniture of a life-sim house, planned by rule tables from the
house actor's own footprint spline; change the outline and the plan follows."""
RANDOM = True
PARAMS = {
    "WallHeight": Param(270.0, "Wall height (cm)", type="Double"),
    "WallCut": Param(0.0, "Walls down: > 0 lowers every wall to this height (cm), 0 full height", type="Double"),
    "ExteriorWall": Param(25.0, "Exterior wall thickness (cm)", type="Double"),
    "InteriorWall": Param(12.0, "Interior wall thickness (cm)", type="Double"),
    "Grid": Param(50.0, "Footprint grid (cm): the outline snaps to it", type="Double"),
    "Style": Param("Scandi", "Scandi | Warm | Modern", type="String"),
    "Program": Param("Auto", "Auto (by area) | Studio | OneBed | TwoBed | ThreeBed | FourBed", type="String"),
    "Furnish": Param(True, "Furniture", type="Bool"),
    "RealMeshes": Param(True, "StarterContent meshes for the sofas, armchair, round table and plants (off: primitive "
                              "recipes, for a project without StarterContent)", type="Bool"),
    "Mirror": Param(False, "Put the public zone at the other end of a long-fronted house", type="Bool"),
}
INPUTS = {"Footprint": "spline", "Volume": "points"}
OUTPUTS = ("Parts", "Rooms", "Summary")
ROOM_TYPES = {"Type": "String", "Label": "String", "Area": "Double", "Parent": "Int32", "Windows": "Int32",
              "Items": "Int32", "SizeX": "Double", "SizeY": "Double"}


def _area(pts):
    return 0.5 * abs(sum(pts[k][0] * pts[(k + 1) % len(pts)][1] - pts[(k + 1) % len(pts)][0] * pts[k][1]
                         for k in range(len(pts))))


def _empty(error):
    return {"Parts": [], "Rooms": [], "Summary": [(WP.summary({"error": error, "failures": 1, "rooms": 0}), ["Summary"])]}


def run(inputs, params, ctx):
    loc, yaw = volume_point(inputs)
    splines = []
    for v, _tags in inputs.get("Footprint", []):
        if isinstance(v, Spline):
            pts = v.polyline if (not v.linear and v.polyline) else v.points
            if len(pts) >= 3:
                splines.append(pts)
    if loc is None or not splines:
        return _empty("no footprint spline on the house actor")
    pts = max(splines, key=_area)
    fp = F.build(pts, loc, yaw, params["Grid"])
    if fp is None:
        return _empty("footprint smaller than %.1f x %.1f m / %.0f m2" % (F.MIN_EXTENT / 100, F.MIN_LONG / 100,
                                                                         F.MIN_AREA_M2))
    names = {p.name: p for p in P.PROGRAMS}
    prog = names.get(params["Program"]) or P.choose(fp.area_m2)
    walls = {"ext": params["ExteriorWall"], "int": params["InteriorWall"], "height": params["WallHeight"]}
    # plan -> doors -> windows -> furniture; a variant whose required furniture does not fit steps down (interior.house)
    plan, doors, wins, places, fails = H.plan_house(fp, prog, ctx.rng, walls, mirror=bool(params["Mirror"]),
                                                    furnish=bool(params["Furnish"]))
    if L.NO_FIT in plan.failures:
        # not even a studio: say so, as for a footprint below the minimum, rather than one room that fails every check
        main, bath = P.ROOMS["Main"], P.ROOMS["Bath"]
        return _empty("no program fits the footprint (%.0f m2): a studio needs a %.1f x %.1f m room on the front and a "
                      "%.1f x %.1f m bathroom, clear of the walls" % (fp.area_m2, main.min_short / 100, main.min_long / 100,
                                                                     bath.min_short / 100, bath.min_long / 100))
    parts = A.house(plan, doors, wins, places, {"WallHeight": params["WallHeight"], "WallCut": params["WallCut"],
                                                "Style": params["Style"], "Furnish": params["Furnish"],
                                                "RealMeshes": params["RealMeshes"]}, ctx.rng)
    failures = fails + K.validate(plan, doors, wins, places)
    summary = K.summary(plan, doors, wins, places, parts, failures)
    rows = []
    lit = {}
    for w in wins:
        lit[w.room] = lit.get(w.room, 0) + 1
    items = {}
    for p in places:
        items[p.room] = items.get(p.room, 0) + 1
    for r in plan.rooms:
        c = L.clear_rect(r.rect, fp, plan.walls)
        # the point is the clear floor's centre; SizeX / SizeY its size along the house's own x / y (cm)
        rows.append({"loc": fp.to_world(c.cx, c.cy, 5.0), "Type": r.type, "Label": P.ROOMS[r.type].label,
                     "Area": round(c.w * c.h / 1e4, 2), "Parent": -1 if plan.parents.get(r.id) is None else plan.parents[r.id],
                     "Windows": lit.get(r.id, 0), "Items": items.get(r.id, 0), "SizeX": round(c.w, 1),
                     "SizeY": round(c.h, 1)})
    ctx.notes.append("%s %.0f m2: %d rooms (%s), %d windows, %d pieces, %d parts, %d failures" % (
        plan.program.name, fp.area_m2, len(plan.rooms), summary["room_types"], len(wins), len(places), len(parts),
        len(failures)))
    return {"Parts": [(WP.module_points(parts), ["HousePart"])],
            "Rooms": [(WP.table_points(rows, ROOM_TYPES), ["Room"])],
            "Summary": [(WP.summary(summary), ["Summary"])]}
