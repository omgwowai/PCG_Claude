"""PyInterior storeys (spec 2026-10-29 §3-§4): a house of one to three floors from its footprint splines.

Each floor has its own closed spline on the house actor; its height picks the floor (H = WallHeight + SLAB apart, the lowest
spline is the ground floor). A floor without a spline copies the floor below. Every upper floor is clipped to the floor below
(no overhang), cleaned like the ground floor, and dropped -- with the floors above it -- when it falls below the single-floor
minimum. What the upper floor leaves uncovered of the lower one's roof is a terrace.

The building loop (§6.2): the stair is placed first -- its candidate places best first -- and every floor is planned around
it (floorplan.plan_floor, doors with the terrace doors, windows, furniture; a floor whose furniture does not fit steps down
a program variant, as interior.house). The first K_TRY places are tried and those that plan every floor compared: the most
rooms of the floors' programs first (the bedrooms and bathrooms upstairs above all), then the summed scores (near ties by
the seed). When no place plans every floor the top floor goes, reported, and the rest is planned again; one floor left is
planned as a single-floor house by the caller. Pure."""
from dataclasses import dataclass

from pypcg.interior import assemble as A
from pypcg.interior import checks as K
from pypcg.interior import doors as D
from pypcg.interior import floorplan as FP
from pypcg.interior import footprint as F
from pypcg.interior import furnish as FU
from pypcg.interior import layout as L
from pypcg.interior import openings as O
from pypcg.interior import program as P
from pypcg.interior import stairs as ST
from pypcg.interior import terrace as T
from pypcg.interior.footprint import EPS, Rect

SLAB = 30.0                  # the floor slab between two storeys (cm); the ground floor's foundation is as thick
MAX_FLOORS = 3
K_TRY = 6                    # stair places planned, best first
RETRIES = 3                  # further program variants a floor tries when its furniture does not fit (interior.house)


def floor_height(wall_height):
    """Floor to floor: the walls plus one slab."""
    return float(wall_height) + SLAB


def floor_name(k):
    return "%dF" % (k + 1)


@dataclass(frozen=True)
class Levels:
    outlines: tuple          # per floor k: the world points of its spline, or None (it copies the floor below)
    notes: tuple             # what was read differently from how it was drawn


def _area(pts):
    n = len(pts)
    return 0.5 * abs(sum(pts[k][0] * pts[(k + 1) % n][1] - pts[(k + 1) % n][0] * pts[k][1] for k in range(n)))


def levels(splines, origin_z, wall_height, floors_param):
    """Levels: the splines grouped by floor. `splines` are closed outlines as world points [(x, y, z)]; `floors_param` 0 means
    one floor per level up to the highest spline, 1..3 a set number of floors."""
    H = floor_height(wall_height)
    notes = []
    by = {}
    for pts in splines:
        if len(pts) < 3:
            continue
        z = sum(p[2] for p in pts) / len(pts)
        by.setdefault(int(round((z - origin_z) / H)), []).append(pts)
    if not by:
        return Levels((), ())
    low = min(by)
    if low != 0:
        notes.append("the lowest spline is %d floor(s) %s the house's base: it is the ground floor"
                     % (abs(low), "above" if low > 0 else "below"))
        by = {k - low: v for k, v in by.items()}
    outl = {}
    for k in sorted(by):
        group = sorted(by[k], key=_area, reverse=True)
        if len(group) > 1:
            notes.append("%s: %d splines, the largest is used" % (floor_name(k), len(group)))
        outl[k] = group[0]
    n = int(floors_param) if floors_param else max(outl) + 1
    if n > MAX_FLOORS:
        notes.append("at most %d floors (%d asked)" % (MAX_FLOORS, n))
        n = MAX_FLOORS
    n = max(n, 1)
    above = sorted(k for k in outl if k >= n)
    if above:
        notes.append("splines of %s ignored: the house has %d floor(s)" % (", ".join(floor_name(k) for k in above), n))
    return Levels(tuple(outl.get(k) for k in range(n)), tuple(notes))


def floor_footprints(lv, origin, yaw, grid, wall_height):
    """([Footprint] per floor, [dropped floor notes]). Floor k's frame sits k * H above the ground's, so everything planned on
    it lands at its height; its cells are its spline's (or the floor below's) clipped to the floor below."""
    H = floor_height(wall_height)
    oz = origin[2] if len(origin) > 2 else 0.0
    fps, dropped = [], []
    for k, pts in enumerate(lv.outlines):
        if k == 0:
            fp = F.build(pts, (origin[0], origin[1], oz), yaw, grid) if pts else None
        else:
            frame = F.Frame((origin[0], origin[1], oz + k * H), yaw)
            prev = fps[-1]
            cells = F.rasterise([frame.local(p) for p in pts], grid) if pts else set(prev.cells)
            fp = F.from_cells(set(cells) & set(prev.cells), grid, frame)
        if fp is None:
            dropped.append("%s: smaller than %.1f x %.1f m / %.0f m2%s" % (
                floor_name(k), F.MIN_EXTENT / 100, F.MIN_LONG / 100, F.MIN_AREA_M2,
                " after clipping to the floor below" if k else ""))
            dropped += ["%s: above a dropped floor" % floor_name(j) for j in range(k + 1, len(lv.outlines))]
            break
        fps.append(fp)
    return fps, dropped


def terrace_rects(fps):
    """{k: [Rect]}: for each upper floor k, the rectangles of the floor below's roof it leaves uncovered (house-local)."""
    out = {}
    for k in range(1, len(fps)):
        rest = set(fps[k - 1].cells) - set(fps[k].cells)
        g = fps[k].grid
        out[k] = [Rect(i0 * g, j0 * g, i1 * g, j1 * g) for i0, j0, i1, j1 in F.decompose(rest)] if rest else []
    return out


# ---------------------------------------------------------------- the building loop

@dataclass
class FloorResult:
    level: int
    fp: object               # its footprint (frame k x H above the ground's)
    plan: object             # layout.Plan around the stair
    doors: list              # doors.Door, its terrace doors with them
    wins: list
    places: list
    fails: list              # required furniture that did not fit
    terraces: list           # terrace.Terrace on the roof of the floor below


@dataclass
class Building:
    floors: tuple            # FloorResult bottom up; () when one floor is left (the caller plans it as a single floor)
    stair: object            # stairs.Stair; None then
    notes: tuple             # how the splines were read, a StairType that could not be used
    dropped: tuple           # the floors that went, and why
    fps: tuple = ()          # the floors' footprints (the ground's alone when one floor is left)


def _walls(params, wall_height):
    return {"ext": float(params.get("ExteriorWall", 25.0)), "int": float(params.get("InteriorWall", 12.0)),
            "height": wall_height}


def _required(p):
    return sum(1 for s in p.public + p.private if not s.optional)


def _plan_floor(fps, k, stair, rects, rng, walls, mirror, furnish, memo=None):
    """FloorResult of floor k around `stair`; a variant whose required furniture does not fit steps down to the next one
    (up to RETRIES), else the first attempt and its failures are kept (as interior.house). `memo`: the floor's
    floorplan._Memo, shared by the stair places tried."""
    fp = fps[k]
    role = stair.role(k)
    prog = P.choose_floor((fp.area - stair.rect.area) / 1e4, k, role == "top")
    first, skip = None, set()
    for _ in range(RETRIES + 1):
        plan = FP.plan_floor(fp, prog, rng, walls, stair, k, role, mirror=mirror, skip=skip, shared=memo)
        if L.NO_FIT in plan.failures:
            return first or FloorResult(k, fp, plan, [], [], [], [], [])
        doors = D.connect(plan, rng) + D.terrace_doors(plan, rects)
        wins = O.windows(plan, doors, rng)
        places, fails = FU.furnish(plan, doors, wins, rng) if furnish else ([], [])
        terraces = T.plan_terraces(fps[k - 1], rects, plan, doors, rng) if k else []
        res = FloorResult(k, fp, plan, doors, wins, places, fails, terraces)
        if not fails:
            return res
        first = first or res
        skip.add(plan.program)
    return first


def _rank(floors, stair):
    """(-required rooms, -rooms, score), the smaller the better: as many rooms of the floors' programs as possible -- the
    bedrooms and bathrooms upstairs first -- then the floors' zoning scores plus the stair room's and the corridors' area
    (spec §6.2)."""
    req = sum(_required(f.plan.program) for f in floors)
    rooms = sum(f.plan.program.size for f in floors)
    halls = sum(r.rect.area for f in floors for r in f.plan.rooms if r.type == "Corridor")
    return -req, -rooms, sum(f.plan.score for f in floors) + stair.rect.area / 1e5 + halls / 1e5


def plan_building(splines, origin, yaw, params, rng):
    """Building of the house's splines (world points per floor) for a house actor at `origin` turned `yaw`; `params` the
    stage's (WallHeight, ExteriorWall, InteriorWall, Grid, Floors, StairType, Mirror, Furnish)."""
    wh = float(params.get("WallHeight", 270.0))
    oz = origin[2] if len(origin) > 2 else 0.0
    lv = levels(splines, oz, wh, int(params.get("Floors", 0) or 0))
    notes = list(lv.notes)
    fps, dropped = floor_footprints(lv, origin, yaw, float(params.get("Grid", 50.0)), wh) if lv.outlines else ([], [])
    dropped = list(dropped)
    walls = _walls(params, wh)
    mirror, furnish = bool(params.get("Mirror", False)), bool(params.get("Furnish", True))
    while len(fps) >= 2:
        cands, cnotes = ST.candidates(fps, params.get("StairType", "Auto") or "Auto", walls)
        notes += [n for n in cnotes if n not in notes]
        rects = terrace_rects(fps)
        memos = [FP._Memo(fp, dict(L.WALLS, **walls)) for fp in fps]     # a floor's room checks hold for every place
        found = []
        for s in cands[:K_TRY]:
            floors = []
            for k in range(len(fps)):
                res = _plan_floor(fps, k, s, rects.get(k, []), rng, walls, mirror, furnish, memos[k])
                if res.plan.failures or res.fails:
                    break
                floors.append(res)
            else:
                found.append((_rank(floors, s), s, tuple(floors)))
        if found:
            low = min(r[:2] for r, _s, _f in found)
            best = sorted(((r[2], (s, fl)) for r, s, fl in found if r[:2] == low), key=lambda c: c[0])
            s, floors = L._near(best, rng)[0][1]
            return Building(floors, s, tuple(notes), tuple(dropped), tuple(fps))
        dropped.append("%s: %s" % (floor_name(len(fps) - 1), "no stair place plans every floor" if cands else
                                   "no stair place leaves rooms on every floor"))
        fps = fps[:-1]
    return Building((), None, tuple(notes), tuple(dropped), tuple(fps))


# ---------------------------------------------------------------- checks and outputs

def parts(b, params, rng):
    """The building's instances (assemble.house items, each tagged with its "floor"): floors 1..ShowFloors (0 = all;
    clamped), each with its stair flights and terraces; only the top floor shown takes WallCut (the floors below keep
    full walls under the slab above). The top floor has no roof (the cutaway view)."""
    n = len(b.floors)
    show = int(params.get("ShowFloors", 0) or 0)
    shown = n if show <= 0 else min(show, n)
    wh = float(params.get("WallHeight", 270.0))
    cut = float(params.get("WallCut", 0.0) or 0.0)
    style = params.get("Style", "Scandi")
    furnish, real = bool(params.get("Furnish", True)), bool(params.get("RealMeshes", True))
    items = []
    for f in b.floors[:shown]:
        top = f.level == shown - 1
        sid = next(r.id for r in f.plan.rooms if r.type == "Stair")
        got = A.house(f.plan, f.doors, f.wins, f.places, {"WallHeight": wh, "WallCut": cut if top else 0.0,
                                                          "Style": style, "Furnish": furnish, "RealMeshes": real,
                                                          "Level": f.level, "StairRoom": sid}, rng)
        out = A._Out(f.fp, (min(wh, cut) if cut > 0.0 else wh) if top else None)
        pal = A.palette(f.plan, style, rng)[0]
        ST.parts(b.stair, out, f.level, f.level + 1 < shown, top, floor_height(wh), pal)
        T.parts(f.terraces, out, pal, furnish, real)
        for i in got + out.items:
            i["floor"] = f.level
            items.append(i)
    return items


def _master_fits(plan):
    mt = P.ROOMS["Master"]
    return any(r.type == "Bedroom" and c.short >= mt.min_short - EPS and c.long >= mt.min_long - EPS
               for r in plan.rooms for c in [L.clear_rect(r.rect, plan.footprint, plan.walls)])


def validate(b):
    """[failure] of a multi-storey building: every floor's own checks (checks.validate, its furniture), the stair room in
    place on every floor with its opening, one master bedroom (on the top floor; none only when no bedroom there could
    be one), a bathroom on every floor with bedrooms, a door onto every terrace a room touches."""
    out = []
    masters = 0
    for f in b.floors:
        name = floor_name(f.level)
        out += ["%s: %s" % (name, x) for x in f.fails + K.validate(f.plan, f.doors, f.wins, f.places)]
        st = [r for r in f.plan.rooms if r.type == "Stair"]
        if len(st) != 1 or st[0].rect != b.stair.rect:
            out.append("%s: the stair room is not where the stair is" % name)
        elif [(d.axis, d.c, d.s0, d.s1) for d in f.doors if d.kind == "stair"] != [b.stair.access(b.stair.role(f.level))]:
            out.append("%s: the stair has no opening onto this floor" % name)
        types = [r.type for r in f.plan.rooms]
        masters += types.count("Master")
        if ("Master" in types or "Bedroom" in types) and "Bath" not in types:
            out.append("%s: bedrooms without a bathroom" % name)
        for t in f.terraces:
            if t.door is None and D.terrace_doors(f.plan, [t.rect]):
                out.append("%s: no door onto the terrace a room touches" % name)
    if b.floors:
        if masters > 1:
            out.append("%d master bedrooms" % masters)
        elif masters == 0 and _master_fits(b.floors[-1].plan):
            out.append("no master bedroom")
    return out


def summary(b, parts, failures):
    """The Summary of a multi-storey building: the single-floor counts over every floor, the floors' programs, the stair,
    the terraces, the dropped floors and the notes."""
    rooms = [r for f in b.floors for r in f.plan.rooms]
    doors = [d for f in b.floors for d in f.doors]
    items = sum(len(f.places) + sum(len(t.places) for t in f.terraces) for f in b.floors)
    return {"program": " / ".join(f.plan.program.name for f in b.floors),
            "area_m2": round(sum(f.fp.area_m2 for f in b.floors), 2), "wings": len(b.floors[0].fp.wings),
            "rooms": len(rooms), "bedrooms": sum(1 for r in rooms if r.type in ("Master", "Bedroom")),
            "corridors": sum(1 for r in rooms if r.type == "Corridor"), "room_types": ",".join(r.type for r in rooms),
            "doors": sum(1 for d in doors if d.leaf), "openings": sum(1 for d in doors if not d.leaf),
            "windows": sum(len(f.wins) for f in b.floors), "items": items, "parts": len(parts),
            "failures": len(failures), "first_failure": failures[0] if failures else "", "error": "",
            "floors": len(b.floors), "stair": b.stair.type, "terraces": sum(len(f.terraces) for f in b.floors),
            "dropped": "; ".join(b.dropped), "notes": "; ".join(b.notes)}


def room_rows(b):
    """One row per room of every floor (the stair room on each), one per terrace: the stage's Rooms, with Floor."""
    rows = []
    for f in b.floors:
        fp, plan = f.fp, f.plan
        lit, items = {}, {}
        for w in f.wins:
            lit[w.room] = lit.get(w.room, 0) + 1
        for p in f.places:
            items[p.room] = items.get(p.room, 0) + 1
        for r in plan.rooms:
            c = L.clear_rect(r.rect, fp, plan.walls)
            rows.append({"loc": fp.to_world(c.cx, c.cy, 5.0), "Type": r.type, "Label": P.ROOMS[r.type].label,
                         "Area": round(c.w * c.h / 1e4, 2),
                         "Parent": -1 if plan.parents.get(r.id) is None else plan.parents[r.id],
                         "Windows": lit.get(r.id, 0), "Items": items.get(r.id, 0), "SizeX": round(c.w, 1),
                         "SizeY": round(c.h, 1), "Floor": f.level})
        for t in f.terraces:
            q = t.rect
            rows.append({"loc": fp.to_world(q.cx, q.cy, 5.0), "Type": "Terrace", "Label": "露台",
                         "Area": round(q.area / 1e4, 2), "Parent": t.door.b if t.door else -1, "Windows": 0,
                         "Items": len(t.places), "SizeX": round(q.w, 1), "SizeY": round(q.h, 1), "Floor": f.level})
    return rows
