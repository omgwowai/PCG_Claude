"""PyInterior assembly (spec 2026-10-28 §4.8): a planned, furnished house -> mesh instances {loc, rot, scale, mesh, mat,
role} in world space, every one a primitive (or a real mesh) for the native spawner.

- Exterior walls: one rectangle per outline segment, ExteriorWall thick inside the outline; horizontal segments own the
  corners (whole at a convex corner, one thickness longer at a reflex one), vertical ones stop at them -- no two walls
  overlap, so wall tops never flicker in a top view.
- Interior walls: InteriorWall thick on the partition lines, ending at the exterior walls' inner face; horizontal ones own
  every junction square, vertical ones are cut there.
- Every wall is cut at its doors (to DOOR_H) and windows (sill .. sill + height); `WallCut` > 0 lowers all walls to it
  (the life-sim "walls down" view).
- Each room paints the four faces of its clear floor 1 cm thick in its own colour and runs a skirting board along them;
  its floor is its own material; one foundation slab per wing.
- Doors: frame, leaf open into the room it swings into (a wet room's sliding door closed in its opening); windows: frame,
  glass, inner sill; furniture: the catalogue's parts, scaled to a kitchen module's solved width -- with RealMeshes, an
  item's StarterContent recipe, its REAL meshes in their own materials.
- A floor of a multi-storey house (spec 2026-10-29 §8, params Level / StairRoom): an upper floor stands on a SLAB thick
  slab over its outline, open over the stair room, which has no floor or skirting there; a stair opening has no frame; a
  terrace door is a frame in the exterior wall with a closed glass leaf. Pure."""
import math

from pypcg.interior import catalog as C
from pypcg.interior import doors as D
from pypcg.interior import layout as L
from pypcg.interior import program as P
from pypcg.interior.footprint import EPS, Rect

MESHES = {"cube": "/Engine/BasicShapes/Cube.Cube", "cyl": "/Engine/BasicShapes/Cylinder.Cylinder",
          "sphere": "/Engine/BasicShapes/Sphere.Sphere"}
MAT_DIR = "/Game/PyPCG/Interior/Materials/"
DEFAULTS = {"WallHeight": 270.0, "WallCut": 0.0, "Style": "Scandi", "Furnish": True, "RealMeshes": True}
FOUNDATION = 30.0
SLAB = 30.0                  # an upper floor's slab (storeys.SLAB)
FLOOR = 2.0
PAINT = 1.0
SKIRT_H, SKIRT_T = 8.0, 1.5
FRAME = 5.0
LEAF_T = 4.0
FLOOR_MATERIAL = "Concrete"


def mat(name):
    return "%sMI_PyInt_%s.MI_PyInt_%s" % (MAT_DIR, name, name) if name else ""


# ---------------------------------------------------------------- walls

def wall_band(segs, t):
    """[(Rect, Seg)]: the exterior wall band, `t` thick inside the outline, horizontal segments owning the corners."""
    out = []
    for s in segs:
        if s.axis == "y":
            y0, y1 = (s.c, s.c + t) if s.normal < 0 else (s.c - t, s.c)
            out.append((Rect(s.a0 - (0.0 if s.convex0 else t), y0, s.a1 + (0.0 if s.convex1 else t), y1), s))
        else:
            x0, x1 = (s.c - t, s.c) if s.normal > 0 else (s.c, s.c + t)
            out.append((Rect(x0, s.a0 + (t if s.convex0 else 0.0), x1, s.a1 - (t if s.convex1 else 0.0)), s))
    return out


def partition_lines(plan):
    """{(axis, c): [(a0, a1)]}: the walls between rooms, merged along each line."""
    lines = {}
    rooms = plan.rooms
    for i, a in enumerate(rooms):
        for b in rooms[i + 1:]:
            s = a.rect.shared(b.rect)
            if s:
                lines.setdefault((s[0], round(s[1], 4)), []).append((s[2], s[3]))
    out = {}
    for key, ivs in lines.items():
        ivs.sort()
        m = []
        for a0, a1 in ivs:
            if m and a0 <= m[-1][1] + EPS:
                m[-1] = (m[-1][0], max(m[-1][1], a1))
            else:
                m.append((a0, a1))
        out[key] = m
    return out


def _on_outline(segs, x, y):
    for s in segs:
        if s.axis == "y" and abs(y - s.c) < EPS and s.a0 - EPS <= x <= s.a1 + EPS:
            return True
        if s.axis == "x" and abs(x - s.c) < EPS and s.a0 - EPS <= y <= s.a1 + EPS:
            return True
    return False


def _clip_to_band(r, axis, band):
    """An interior wall piece cut back to the exterior band's inner face where it runs into it: a partition a few cm from a
    reflex corner would otherwise end inside that corner's band square (a T's stem 20 cm off a room boundary)."""
    for b, _s in band:
        if not r.overlaps(b):
            continue
        if axis == "x":
            r = Rect(r.x0, r.y0, r.x1, min(r.y1, b.y0)) if b.cy >= r.cy else Rect(r.x0, max(r.y0, b.y1), r.x1, r.y1)
        else:
            r = Rect(r.x0, r.y0, min(r.x1, b.x0), r.y1) if b.cx >= r.cx else Rect(max(r.x0, b.x1), r.y0, r.x1, r.y1)
        if r.w <= EPS or r.h <= EPS:
            return None
    return r


def interior_walls(plan, segs, t, t_ext):
    """[(Rect, axis, c)]: interior wall pieces, no two overlapping, none inside the exterior band."""
    lines = partition_lines(plan)
    hs = [(c, a0, a1) for (axis, c), ivs in lines.items() if axis == "y" for a0, a1 in ivs]
    vs = [(c, a0, a1) for (axis, c), ivs in lines.items() if axis == "x" for a0, a1 in ivs]
    h = t / 2.0
    band = wall_band(segs, t_ext)

    def meets_v(x, y):
        return any(abs(x - c) < EPS and a0 - EPS <= y <= a1 + EPS for c, a0, a1 in vs)

    def meets_h(x, y):
        return any(abs(y - c) < EPS and a0 - EPS <= x <= a1 + EPS for c, a0, a1 in hs)

    out = []
    for c, a0, a1 in hs:
        x0 = a0 + t_ext if _on_outline(segs, a0, c) else (a0 - h if meets_v(a0, c) else a0)
        x1 = a1 - t_ext if _on_outline(segs, a1, c) else (a1 + h if meets_v(a1, c) else a1)
        if x1 - x0 > EPS:
            out.append((Rect(x0, c - h, x1, c + h), "y", c))
    for c, a0, a1 in vs:
        y0 = a0 + t_ext if _on_outline(segs, c, a0) else (a0 + h if meets_h(c, a0) else a0)
        y1 = a1 - t_ext if _on_outline(segs, c, a1) else (a1 - h if meets_h(c, a1) else a1)
        cuts = sorted(hc for hc, b0, b1 in hs if b0 - EPS <= c <= b1 + EPS and y0 + EPS < hc < y1 - EPS)
        y = y0
        for hc in cuts:
            if hc - h - y > EPS:
                out.append((Rect(c - h, y, c + h, hc - h), "x", c))
            y = hc + h
        if y1 - y > EPS:
            out.append((Rect(c - h, y, c + h, y1), "x", c))
    clipped = [(_clip_to_band(r, axis, band), axis, c) for r, axis, c in out]
    return [(r, axis, c) for r, axis, c in clipped if r is not None]


def wall_plan(plan, doors=None, wins=None):
    """[(Rect, "ext" | "int", axis, c)]: the walls in plan, before the openings are cut."""
    segs = plan.footprint.segments()
    out = [(r, "ext", s.axis, s.c) for r, s in wall_band(segs, plan.walls["ext"])]
    out += [(r, "int", axis, c) for r, axis, c in interior_walls(plan, segs, plan.walls["int"], plan.walls["ext"])]
    return out


def cut(lo, hi, holes, H):
    """[(a0, a1, z0, z1)] covering lo..hi x 0..H without the holes (a0, a1, z0, z1)."""
    hs = sorted((max(lo, a0), min(hi, a1), z0, z1) for a0, a1, z0, z1 in holes if a1 > lo + EPS and a0 < hi - EPS)
    out, x = [], lo
    for a0, a1, z0, z1 in hs:
        if a0 > x + EPS:
            out.append((x, a0, 0.0, H))
        if z0 > EPS:
            out.append((a0, a1, 0.0, min(z0, H)))
        if z1 < H - EPS:
            out.append((a0, a1, z1, H))
        x = max(x, a1)
    if hi > x + EPS:
        out.append((x, hi, 0.0, H))
    return [p for p in out if p[1] - p[0] > EPS and p[3] - p[2] > EPS]


def _holes(axis, c, doors, wins):
    out = [(d.s0, d.s1, 0.0, D.DOOR_H) for d in doors if d.axis == axis and abs(d.c - c) < EPS]
    out += [(w.s0, w.s1, w.sill, w.sill + w.height) for w in wins if w.axis == axis and abs(w.c - c) < EPS]
    return out


# ---------------------------------------------------------------- materials

def palette(plan, style, rng):
    st = P.STYLES.get(style) or P.STYLES["Scandi"]
    fabrics = list(st["fabric"])
    rng.shuffle(fabrics)
    accents = list(st["accent"])
    rng.shuffle(accents)
    pal = {"facade": st["facade"], "trim": st["trim"], "door": st["door"], "wood": st["wood"], "wood_dark": st["wood_dark"],
           "fabric": fabrics[0], "fabric2": fabrics[1 % len(fabrics)], "accent": accents[0],
           "rug": accents[1 % len(accents)], "white": "White", "black": "Black", "steel": "Steel",
           "porcelain": "Porcelain", "mattress": "White", "linen": "Linen", "glass": "Glass", "screen": "Screen",
           "plant": "Leaf", "pot": "Terracotta", "counter": "Greige" if style != "Modern" else "Charcoal", "mirror": "Mirror"}
    walls = {}
    for r in plan.rooms:
        pool = list(st["walls"][P.ROOMS[r.type].wall])
        parent = plan.parents.get(r.id)
        if parent in walls and len(pool) > 1 and walls[parent] in pool:
            pool.remove(walls[parent])
        walls[r.id] = pool[rng.randrange(len(pool))]
    floors = {r.id: st["floors"][P.ROOMS[r.type].floor] for r in plan.rooms}
    return pal, walls, floors


# ---------------------------------------------------------------- the house

class _Out:
    def __init__(self, fp, top=None):
        self.fp, self.items, self.top = fp, [], top     # top: walls, doors and windows end here (walls down)

    def box(self, rect, z0, z1, mat_name, role, shape="cube", clip=False):
        if clip and self.top is not None:
            z1 = min(z1, self.top)
        if rect.w <= EPS or rect.h <= EPS or z1 - z0 <= EPS:
            return
        x, y, z = self.fp.to_world(rect.cx, rect.cy, 0.5 * (z0 + z1))
        self.items.append({"loc": (x, y, z), "rot": (0.0, self.fp.yaw_world(0.0), 0.0),
                           "scale": (rect.w / 100.0, rect.h / 100.0, (z1 - z0) / 100.0), "mesh": MESHES[shape],
                           "mat": mat(mat_name), "role": role, "local": (rect, z0, z1)})

    def part(self, cx, cy, cz, size, yaw, shape, mat_name, role):
        x, y, z = self.fp.to_world(cx, cy, cz)
        self.items.append({"loc": (x, y, z), "rot": (0.0, self.fp.yaw_world(yaw), 0.0),
                           "scale": tuple(max(v, 0.1) / 100.0 for v in size), "mesh": MESHES[shape], "mat": mat(mat_name),
                           "role": role})

    def real(self, cx, cy, cz, scale, yaw, path, role):
        x, y, z = self.fp.to_world(cx, cy, cz)
        self.items.append({"loc": (x, y, z), "rot": (0.0, self.fp.yaw_world(yaw), 0.0), "scale": tuple(scale),
                           "mesh": path, "mat": "", "role": role})

    def bar(self, p0, p1, t, mat_name, role):
        """A cube bar t x t from local point p0 to p1 (x, y, z), sloped: its length along the line (pitch, yaw)."""
        a, b = self.fp.to_world(*p0), self.fp.to_world(*p1)
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length <= EPS:
            return
        pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
        yaw = math.degrees(math.atan2(dy, dx))
        self.items.append({"loc": (0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1]), 0.5 * (a[2] + b[2])), "rot": (pitch, yaw, 0.0),
                           "scale": (length / 100.0, t / 100.0, t / 100.0), "mesh": MESHES["cube"], "mat": mat(mat_name),
                           "role": role, "ends": (tuple(p0), tuple(p1))})


def real_part(shape, centre, size):
    """(path, pivot, yaw, scale): a catalogue REAL mesh posed in its item's frame -- turned by its measured yaw (front to
    +y) and scaled along its own axes so its measured box fills the part box `size` centred on `centre`."""
    path, lo, hi, myaw = C.REAL[shape]
    turned = int(round(myaw / 90.0)) % 2 == 1
    sx = (size[1] if turned else size[0]) / (hi[0] - lo[0])
    sy = (size[0] if turned else size[1]) / (hi[1] - lo[1])
    sz = size[2] / (hi[2] - lo[2])
    nx, ny, nz = sx * 0.5 * (lo[0] + hi[0]), sy * 0.5 * (lo[1] + hi[1]), sz * 0.5 * (lo[2] + hi[2])
    c, s = math.cos(math.radians(myaw)), math.sin(math.radians(myaw))
    return path, (centre[0] - (c * nx - s * ny), centre[1] - (s * nx + c * ny), centre[2] - nz), myaw, (sx, sy, sz)


def _along(axis, c, a0, a1, t0, t1):
    """The rectangle of a wall piece on the line (axis, c) from a0 to a1 along it, t0..t1 across it (offsets from c)."""
    if axis == "x":
        return Rect(c + t0, a0, c + t1, a1)
    return Rect(a0, c + t0, a1, c + t1)


def _walls(out, plan, doors, wins, pal, H):
    for r, kind, axis, c in wall_plan(plan):
        holes = _holes(axis, c, doors, wins)
        lo, hi = (r.y0, r.y1) if axis == "x" else (r.x0, r.x1)
        for a0, a1, z0, z1 in cut(lo, hi, holes, H):
            piece = Rect(r.x0, a0, r.x1, a1) if axis == "x" else Rect(a0, r.y0, a1, r.y1)
            out.box(piece, z0, z1, pal["facade"] if kind == "ext" else pal["trim"], "wall")


def _room_faces(out, plan, room, doors, wins, color, pal, H, skirting=True):
    R = L.clear_rect(room.rect, plan.footprint, plan.walls)
    lines = [("y", room.rect.y0, R.y0, 1), ("x", room.rect.x1, R.x1, -1), ("y", room.rect.y1, R.y1, -1),
             ("x", room.rect.x0, R.x0, 1)]
    for k, (axis, c, face, inward) in enumerate(lines):
        if axis == "y":
            lo, hi = R.x0, R.x1
        else:
            lo, hi = R.y0 + PAINT, R.y1 - PAINT
        holes = _holes(axis, c, doors, wins)
        for a0, a1, z0, z1 in cut(lo, hi, holes, H):
            t0, t1 = sorted((face - c, face - c + inward * PAINT))
            out.box(_along(axis, c, a0, a1, t0, t1), z0, z1, color, "paint")
        if not skirting:
            continue
        # skirting along the paint, not across a passage
        slo, shi = (lo, hi) if axis == "y" else (lo + SKIRT_T, hi - SKIRT_T)
        if axis == "y":
            slo, shi = R.x0 + PAINT, R.x1 - PAINT
        for a0, a1, z0, z1 in cut(slo, shi, [(d.s0, d.s1, 0.0, D.DOOR_H) for d in doors
                                             if d.axis == axis and abs(d.c - c) < EPS], SKIRT_H):
            if z0 > EPS:
                continue
            t0, t1 = sorted((face - c + inward * PAINT, face - c + inward * (PAINT + SKIRT_T)))
            out.box(_along(axis, c, a0, a1, t0, t1), 0.0, SKIRT_H, pal["trim"], "skirting")


def minus(r, hole):
    """[Rect] covering r without `hole` (at most four: the bands below and above it, the pieces beside it)."""
    if not r.overlaps(hole):
        return [r]
    hx0, hy0, hx1, hy1 = max(r.x0, hole.x0), max(r.y0, hole.y0), min(r.x1, hole.x1), min(r.y1, hole.y1)
    out = [Rect(r.x0, r.y0, r.x1, hy0), Rect(r.x0, hy1, r.x1, r.y1), Rect(r.x0, hy0, hx0, hy1), Rect(hx1, hy0, r.x1, hy1)]
    return [p for p in out if p.w > EPS and p.h > EPS]


def _floors(out, plan, floors, level=0, stair=None, pal=None):
    """The ground floor's foundation per wing, or an upper floor's slab open over its stair room; every room's floor
    (none in an upper floor's stair room)."""
    fp = plan.footprint
    for w in fp.wings:
        if level == 0:
            out.box(w, -FOUNDATION, 0.0, FLOOR_MATERIAL, "foundation")
            continue
        for piece in (minus(w, stair.rect) if stair is not None else [w]):
            out.box(piece, -SLAB, 0.0, pal["facade"], "slab")
    for r in plan.rooms:
        if level and stair is not None and r.id == stair.id:
            continue
        ins = [plan.walls["ext"] if L.exterior_parts(fp, axis, c, a0, a1, o) else 0.0 for axis, c, a0, a1, o in r.rect.edges()]
        b, rr, t, l = ins
        out.box(r.rect.shrink(l, b, rr, t), 0.0, FLOOR, floors[r.id], "floor")


def _doors(out, plan, doors, pal):
    by = {r.id: r for r in plan.rooms}
    for d in doors:
        t = plan.walls["ext"] if d.kind in ("front", "terrace") else plan.walls["int"]
        h = t / 2.0 + PAINT
        if d.kind == "terrace":
            # in the exterior wall, whose line is the outline: the frame fills the wall's thickness on the room's side
            inward = 1.0 if ((by[d.b].rect.x0 >= d.c - EPS) if d.axis == "x" else (by[d.b].rect.y0 >= d.c - EPS)) else -1.0
            t0, t1 = sorted((0.0, inward * t))
            for a0, a1 in ((d.s0, d.s0 + FRAME), (d.s1 - FRAME, d.s1)):
                out.box(_along(d.axis, d.c, a0, a1, t0, t1), 0.0, D.DOOR_H, pal["trim"], "door", clip=True)
            out.box(_along(d.axis, d.c, d.s0 + FRAME, d.s1 - FRAME, t0, t1), D.DOOR_H - FRAME, D.DOOR_H, pal["trim"], "door",
                    clip=True)
            g0, g1 = sorted((inward * (0.5 * t - LEAF_T / 2), inward * (0.5 * t + LEAF_T / 2)))
            out.box(_along(d.axis, d.c, d.s0 + FRAME, d.s1 - FRAME, g0, g1), 1.0, D.DOOR_H - FRAME - 1.0, pal["glass"], "door",
                    clip=True)
            continue
        if d.kind not in ("opening", "stair"):
            for a0, a1 in ((d.s0, d.s0 + FRAME), (d.s1 - FRAME, d.s1)):
                out.box(_along(d.axis, d.c, a0, a1, -h, h), 0.0, D.DOOR_H, pal["trim"], "door", clip=True)
            out.box(_along(d.axis, d.c, d.s0 + FRAME, d.s1 - FRAME, -h, h), D.DOOR_H - FRAME, D.DOOR_H, pal["trim"], "door",
                    clip=True)
        if not d.leaf:
            continue
        if d.sliding:
            # a wet room's door slides, so it never takes floor: drawn closed, a leaf between the frames mid-wall
            out.box(_along(d.axis, d.c, d.s0 + FRAME, d.s1 - FRAME, -LEAF_T / 2, LEAF_T / 2), 1.0, D.DOOR_H - FRAME - 1.0,
                    pal["wood"], "door", clip=True)
            continue
        room = by[d.b]
        side = 1.0 if ((room.rect.x0 >= d.c - EPS) if d.axis == "x" else (room.rect.y0 >= d.c - EPS)) else -1.0
        length = d.width - 2 * FRAME
        hinge = d.s0 + FRAME if d.hinge == 0 else d.s1 - FRAME
        a0, a1 = (hinge, hinge + LEAF_T) if d.hinge == 0 else (hinge - LEAF_T, hinge)
        t0, t1 = sorted((side * h, side * (h + length)))
        out.box(_along(d.axis, d.c, a0, a1, t0, t1), 1.0, D.DOOR_H - FRAME - 1.0,
                pal["door"] if d.kind == "front" else pal["wood"], "door", clip=True)


def _windows(out, plan, wins, pal):
    t = plan.walls["ext"]
    for w in wins:
        # the wall line is the outline; the wall lies on the inner side (opposite `outward`)
        inner = -w.outward
        t0, t1 = sorted((0.0, inner * t))
        z0, z1 = w.sill, w.sill + w.height
        if out.top is not None and z0 >= out.top - EPS:
            continue                                      # the walls end below this window
        for a0, a1 in ((w.s0, w.s0 + FRAME), (w.s1 - FRAME, w.s1)):
            out.box(_along(w.axis, w.c, a0, a1, t0, t1), z0, z1, pal["trim"], "window", clip=True)
        out.box(_along(w.axis, w.c, w.s0 + FRAME, w.s1 - FRAME, t0, t1), z0, z0 + FRAME, pal["trim"], "window", clip=True)
        if out.top is None or z1 <= out.top + EPS:
            out.box(_along(w.axis, w.c, w.s0 + FRAME, w.s1 - FRAME, t0, t1), z1 - FRAME, z1, pal["trim"], "window")
        g0, g1 = sorted((inner * (0.5 * t - 1.0), inner * (0.5 * t + 1.0)))
        out.box(_along(w.axis, w.c, w.s0 + FRAME, w.s1 - FRAME, g0, g1), z0 + FRAME, z1 - FRAME, pal["glass"], "window",
                clip=True)
        s0, s1 = sorted((inner * (t + PAINT), inner * (t + PAINT + 5.0)))
        out.box(_along(w.axis, w.c, w.s0, w.s1, s0, s1), z0 - 3.0, z0, pal["wood"], "window")


WALL_HUNG = ("upper", "dresser", "vanity")      # their wall-hung parts go with the wall when the walls are down


def _furniture(out, places, pal, real=True):
    for p in places:
        it = C.ITEMS[p.item]
        if out.top is not None and p.z >= out.top - EPS:
            continue                                      # wall cabinets above lowered walls
        sx = p.w / it.w
        c, s = math.cos(math.radians(p.yaw)), math.sin(math.radians(p.yaw))
        for shape, (cx, cy, cz), size, mkey in (it.mesh if real and it.mesh else it.parts):
            if out.top is not None and it.kind in WALL_HUNG and p.z + cz - size[2] / 2.0 >= out.top - EPS:
                continue                                  # a mirror above lowered walls
            lx = cx * sx
            if shape in C.REAL:
                path, (px, py, pz), myaw, scale = real_part(shape, (lx, cy, cz), (size[0] * sx, size[1], size[2]))
                out.real(p.x + c * px - s * py, p.y + s * px + c * py, p.z + pz, scale, p.yaw + myaw, path,
                         "furniture:" + p.item)
                continue
            out.part(p.x + c * lx - s * cy, p.y + s * lx + c * cy, p.z + cz, (size[0] * sx, size[1], size[2]), p.yaw,
                     shape, pal[mkey], "furniture:" + p.item)


def house(plan, doors, wins, places, params, rng):
    """The house's instances, in world space. `Level` (0) and `StairRoom` (the stair room's id) make it a floor of a
    multi-storey house."""
    H = float(params.get("WallHeight", DEFAULTS["WallHeight"]))
    cut_h = float(params.get("WallCut", 0.0) or 0.0)
    if cut_h > 0.0:
        H = min(H, cut_h)
    level = int(params.get("Level", 0) or 0)
    sid = params.get("StairRoom")
    stair = plan.room(sid) if sid is not None else None
    pal, walls, floors = palette(plan, params.get("Style", "Scandi"), rng)
    out = _Out(plan.footprint, H)
    _floors(out, plan, floors, level, stair, pal)
    _walls(out, plan, doors, wins, pal, H)
    for r in plan.rooms:
        _room_faces(out, plan, r, doors, wins, walls[r.id], pal, H, skirting=not (level and stair is not None and r is stair))
    _doors(out, plan, doors, pal)
    _windows(out, plan, wins, pal)
    if params.get("Furnish", True):
        _furniture(out, places, pal, bool(params.get("RealMeshes", DEFAULTS["RealMeshes"])))
    return out.items
