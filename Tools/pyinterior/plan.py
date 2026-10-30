"""Offline floor plans of PyInterior houses (no editor): rooms by type, doors, windows, furniture footprints.

    python Tools/pyinterior/plan.py --demo            one PNG per demo house -> Saved/Reports/pyinterior_plan_<name>.png
    python Tools/pyinterior/plan.py --sweep           a sheet of rectangles 5 x 4.5 .. 20 x 14 m -> pyinterior_sweep.png
    python Tools/pyinterior/plan.py --rect 1300x900   one rectangle (local cm) -> pyinterior_plan_rect.png
    python Tools/pyinterior/plan.py --storeys         each multi-storey demo house, its floors side by side (the stair room,
                                                      its openings in red, the terraces with their railings and furniture)
                                                      -> pyinterior_storeys_<name>.png
"""
import math
import os
import random
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "Content", "Python"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from pypcg.interior import catalog as C  # noqa: E402
from pypcg.interior import doors as D  # noqa: E402
from pypcg.interior import footprint as F  # noqa: E402
from pypcg.interior import house as H  # noqa: E402
from pypcg.interior import layout as L  # noqa: E402
from pypcg.interior import program as P  # noqa: E402

OUT = os.path.join(REPO, "Saved", "Reports")
FILL = {"Main": (238, 214, 170), "Living": (240, 210, 160), "Kitchen": (200, 225, 235), "Dining": (245, 225, 190),
        "Master": (205, 190, 230), "Bedroom": (215, 205, 240), "Study": (210, 230, 200), "Bath": (170, 210, 225),
        "WC": (170, 210, 225), "Laundry": (190, 215, 215), "Corridor": (225, 225, 225), "Storage": (205, 200, 195),
        "Stair": (160, 160, 160)}
DECK = (222, 200, 160)


def font(px):
    for f in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_plan(d, plan, ox, oy, s, extras=None, title=None, fs=18):
    """Draw a plan with its local (0, 0) at image (ox, oy), y up, s px per cm."""
    fp = plan.footprint
    X = lambda x: ox + x * s
    Y = lambda y: oy - y * s
    f_small, f_mid = font(max(9, int(fs * 0.8))), font(fs)
    for (i, j) in fp.cells:
        g = fp.grid
        d.rectangle([X(i * g), Y((j + 1) * g), X((i + 1) * g), Y(j * g)], fill=(250, 250, 250))
    for r in plan.rooms:
        R = r.rect
        d.rectangle([X(R.x0), Y(R.y1), X(R.x1), Y(R.y0)], fill=FILL.get(r.type, (230, 230, 230)), outline=(90, 90, 90), width=2)
        c = L.clear_rect(R, fp, plan.walls)
        label = "%s\n%.1f m²" % (P.ROOMS[r.type].label, c.w * c.h / 1e4)
        d.multiline_text((X(R.cx), Y(R.cy)), label, fill=(40, 40, 40), font=f_mid if R.area > 60000 else f_small,
                         anchor="mm", align="center")
    # passages: the parent links at the middle of the shared wall
    for rid, pid in plan.parents.items():
        if pid is None:
            continue
        a, b = plan.room(pid).rect, plan.room(rid).rect
        sh = a.shared(b)
        if not sh:
            continue
        axis, cc, a0, a1 = sh
        m = 0.5 * (a0 + a1)
        px, py = (X(cc), Y(m)) if axis == "x" else (X(m), Y(cc))
        kind = L.passage(plan.room(pid).type, plan.room(rid).type)
        col = {"opening": (60, 160, 60), "doorway": (60, 120, 200)}.get(kind, (200, 120, 40))
        d.ellipse([px - 6, py - 6, px + 6, py + 6], fill=col)
    if plan.entry is not None:                            # an upper floor has no front door
        x0, x1, y = plan.entry
        d.line([X(x0 + 0.5 * (x1 - x0) - 50), Y(y), X(x0 + 0.5 * (x1 - x0) + 50), Y(y)], fill=(220, 40, 40), width=6)
    if plan.stair is not None:                            # the stair's opening on this floor
        axis, c, s0, s1 = plan.stair.access(plan.stair.role(plan.level))
        pts = [(X(c), Y(s0)), (X(c), Y(s1))] if axis == "x" else [(X(s0), Y(c)), (X(s1), Y(c))]
        d.line(pts, fill=(220, 0, 0), width=5)
    # the outline
    poly = [(X(p[0]), Y(p[1])) for p in fp.poly]
    d.line(poly + poly[:1], fill=(30, 30, 30), width=4)
    if extras:
        extras(d, X, Y, s)
    if title:
        bb = fp.bbox()
        d.text((X(bb.x0), Y(bb.y1) - 1.6 * fs - 4), title, fill=(20, 20, 20), font=font(int(fs * 1.2)))


KIND_FILL = {"bed": (255, 255, 255), "sofa": (150, 120, 100), "armchair": (150, 120, 100), "dining_table": (160, 110, 70),
             "coffee_table": (160, 110, 70), "desk": (160, 110, 70), "chair": (190, 150, 110), "wardrobe": (120, 100, 90),
             "counter": (235, 235, 235), "sink": (190, 205, 215), "stove": (60, 60, 60), "fridge": (200, 205, 210),
             "toilet": (250, 250, 250), "vanity": (220, 220, 225), "bathtub": (250, 250, 255), "shower": (205, 225, 240),
             "rug": None, "plant": (90, 150, 80), "tv": (40, 40, 40), "bookshelf": (120, 90, 60)}
SHORT = {"bed": "床", "sofa": "沙发", "dining_table": "餐桌", "desk": "书桌", "wardrobe": "衣柜", "fridge": "冰箱",
         "sink": "水槽", "stove": "灶", "toilet": "马桶", "vanity": "台盆", "basin": "台盆", "bathtub": "浴缸", "shower": "淋浴",
         "tv": "电视", "bookshelf": "书架", "island": "岛台", "washer": "洗衣机", "coffee_table": "茶几"}


def chain(fp, seed=1):
    """The stage's chain (interior.house): (plan, doors, wins, places, fails), a variant stepping down when its required
    furniture does not fit -- so these pictures show what the editor builds for the same seed and rng."""
    return H.plan_house(fp, P.choose(fp.area_m2), random.Random(seed))


def overlay(plan, doors, wins, places):
    """Windows, doors and furniture drawn over a plan (render's `extras`)."""
    def draw(d, X, Y, s):
        fs = font(max(9, int(13 * s / 0.6)))
        for w in wins:
            pts = [(X(w.c), Y(w.s0)), (X(w.c), Y(w.s1))] if w.axis == "x" else [(X(w.s0), Y(w.c)), (X(w.s1), Y(w.c))]
            d.line(pts, fill=(80, 170, 230), width=max(3, int(7 * s / 0.6)))
        for p in places:
            it = C.ITEMS[p.item]
            r = p.rect()
            box = [X(r.x0), Y(r.y1), X(r.x1), Y(r.y0)]
            fill = KIND_FILL.get(it.kind, (205, 195, 185))
            if it.kind == "rug":
                d.rectangle(box, outline=(170, 140, 120), width=1)
                continue
            if p.z >= 100.0:
                continue
            d.rectangle(box, fill=fill, outline=(70, 60, 55), width=1)
            if it.kind in SHORT and r.area > 3000:
                d.text((X(r.cx), Y(r.cy)), SHORT[it.kind], fill=(30, 30, 30) if it.kind not in ("stove", "tv") else (240, 240, 240),
                       font=fs, anchor="mm")
        for dr in doors:
            a, b = ((X(dr.c), Y(dr.s0)), (X(dr.c), Y(dr.s1))) if dr.axis == "x" else ((X(dr.s0), Y(dr.c)), (X(dr.s1), Y(dr.c)))
            d.line([a, b], fill=(255, 255, 255), width=max(4, int(9 * s / 0.6)))
            col = {"opening": (60, 160, 60), "doorway": (60, 120, 200), "front": (220, 40, 40)}.get(dr.kind, (200, 120, 40))
            if dr.leaf and not dr.sliding:
                room = plan.room(dr.b)
                z = D.swing(dr, room, plan)
                hx, hy = (a if dr.hinge == 0 else b)
                rad = dr.width * s
                # quarter arc from the hinge, on the room's side
                cx0, cy0 = X(z.cx), Y(z.cy)
                ang = math.degrees(math.atan2(-(cy0 - hy), cx0 - hx))
                d.arc([hx - rad, hy - rad, hx + rad, hy + rad], -ang - 45, -ang + 45, fill=col, width=2)
            elif dr.sliding:
                d.line([a, b], fill=col, width=3)
            else:
                d.line([a, b], fill=col, width=2)
    return draw


def render(plan, path, title=None, extras=None, s=0.6):
    bb = plan.footprint.bbox()
    W, H = int(bb.w * s) + 120, int(bb.h * s) + 160
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    draw_plan(d, plan, 60 - bb.x0 * s, H - 60 + bb.y0 * s, s, extras, title)
    img.save(path)
    return path


def rect_fp(w, h):
    return F.build([(0, 0, 0), (0, w, 0), (-h, w, 0), (-h, 0, 0)], (0, 0, 0), 0.0)


def local_fp(pts):
    return F.build([(-y, x, 0.0) for x, y in pts], (0, 0, 0), 0.0)


def sweep(path, seed=1):
    sizes = [(w, h) for h in (450, 600, 800, 1000, 1200, 1400) for w in (500, 700, 900, 1200, 1500, 1800, 2000) if w >= h]
    s = 0.13
    cell = (int(2000 * s) + 30, int(1400 * s) + 50)
    cols = 6
    rows = (len(sizes) + cols - 1) // cols
    img = Image.new("RGB", (cols * cell[0] + 20, rows * cell[1] + 20), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for k, (w, h) in enumerate(sizes):
        fp = rect_fp(w, h)
        p, doors, wins, places, fails = chain(fp, seed)
        cx, cy = 20 + (k % cols) * cell[0], 20 + (k // cols + 1) * cell[1] - 30
        draw_plan(d, p, cx, cy, s, overlay(p, doors, wins, places),
                  title="%gx%g m %s%s" % (w / 100, h / 100, p.program.name, " FAIL" if fails else ""), fs=10)
    img.save(path)
    return path


def storeys(seed=None):
    """One sheet per multi-storey demo house (pypcg.interior.demo.STOREYS): its floors side by side, each with its
    terraces (deck, railing, furniture) drawn under it, through storeys.plan_building as the stage runs it."""
    from pypcg.interior import demo
    from pypcg.interior import storeys as S
    params = {"WallHeight": 270.0, "ExteriorWall": 25.0, "InteriorWall": 12.0, "Grid": 50.0, "Mirror": False,
              "Furnish": True}
    paths = []
    for name, outlines, floors, stair, style, hseed in demo.STOREYS:
        splines = [[(-y, x, k * 300.0) for x, y in o] for k, o in enumerate(outlines) if o is not None]
        b = S.plan_building(splines, (0.0, 0.0, 0.0), 0.0, dict(params, Floors=floors, StairType=stair),
                            random.Random(hseed if seed is None else seed))
        if not b.floors:
            print("%s: one floor left (%s)" % (name, "; ".join(b.dropped)))
            continue
        s = 0.4
        bb = b.floors[0].fp.bbox()
        W = int(len(b.floors) * (bb.w * s + 60) + 60)
        img = Image.new("RGB", (W, int(bb.h * s + 150)), (255, 255, 255))
        d = ImageDraw.Draw(img)
        fails = S.validate(b)
        d.text((20, 8), "%s  %s stair  %s%s" % (name, b.stair.type, " / ".join(f.plan.program.name for f in b.floors),
                                                 ("  FAIL " + fails[0]) if fails else ""), fill=(20, 20, 20), font=font(16))
        for f in b.floors:
            ox, oy = 40 - bb.x0 * s + f.level * (bb.w * s + 60), 100 + bb.y1 * s
            for t in f.terraces:
                r = t.rect
                d.rectangle([ox + r.x0 * s, oy - r.y1 * s, ox + r.x1 * s, oy - r.y0 * s], fill=DECK)
                for axis, c, lo, hi, _o in t.rails:
                    pts = [(ox + c * s, oy - lo * s), (ox + c * s, oy - hi * s)] if axis == "x" else \
                        [(ox + lo * s, oy - c * s), (ox + hi * s, oy - c * s)]
                    d.line(pts, fill=(60, 60, 60), width=3)
            places = f.places + [p for t in f.terraces for p in t.places]
            draw_plan(d, f.plan, ox, oy, s, overlay(f.plan, f.doors, f.wins, places),
                      title="%dF %s" % (f.level + 1, f.plan.program.name), fs=12)
        path = os.path.join(OUT, "pyinterior_storeys_%s.png" % name)
        img.save(path)
        paths.append(path)
    return paths


def main():
    os.makedirs(OUT, exist_ok=True)
    seed = 1
    if "--seed" in sys.argv:
        seed = int(sys.argv[sys.argv.index("--seed") + 1])
    if "--storeys" in sys.argv:
        for path in storeys(seed if "--seed" in sys.argv else None):
            print(path)
    if "--sweep" in sys.argv:
        print(sweep(os.path.join(OUT, "pyinterior_sweep.png"), seed))
    if "--rect" in sys.argv:
        w, h = (float(v) for v in sys.argv[sys.argv.index("--rect") + 1].split("x"))
        fp = rect_fp(w, h)
        p = L.plan(fp, P.choose(fp.area_m2), random.Random(seed))
        print(render(p, os.path.join(OUT, "pyinterior_plan_rect.png"), "%s %.0f m2" % (p.program.name, fp.area_m2)))
    if "--demo" in sys.argv:
        from pypcg.interior import demo
        for name, pts in demo.SHAPES.items():
            fp = local_fp(pts)
            p, doors, wins, places, fails = chain(fp, seed)
            print(render(p, os.path.join(OUT, "pyinterior_plan_%s.png" % name), "%s %s %.0f m2%s" % (
                name, p.program.name, fp.area_m2, "  FAIL %s" % fails if fails else ""), overlay(p, doors, wins, places)))


if __name__ == "__main__":
    main()
