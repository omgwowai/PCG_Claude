"""PyInterior furniture catalogue (spec 2026-10-28 §4.7): every item's size, how it stands, the floor it keeps clear, and its
look as a recipe of primitive parts (the City Sample building's modules, for furniture). An item's frame: origin at the
centre of its footprint on the floor, +y its front, its back at y = -d/2. A part is (shape, centre, size, material key);
the material keys are resolved per house by the style (pypcg.interior.assemble). `mesh` is the recipe used instead when the
project has StarterContent (stage parameter RealMeshes): a part's shape may name a REAL mesh, posed and scaled so its
measured box fills the part's box, in its own materials. Pure."""
from dataclasses import dataclass

MATERIAL_KEYS = ("wood", "wood_dark", "fabric", "fabric2", "accent", "white", "black", "steel", "porcelain", "mattress",
                 "linen", "glass", "screen", "plant", "pot", "rug", "counter", "mirror")
_SC = "/Game/StarterContent/Props/%s.%s"
# measured by pyinterior_probe_meshes.py (2026-10-28): path, bounding box min / max (cm), and the yaw that turns the mesh's
# front to +y -- the couch's and the lounge chair's backs (their top vertices) are at -x, so they face +x
REAL = {
    "SM_Couch": (_SC % ("SM_Couch", "SM_Couch"), (-41.08, -135.97, 0.1), (41.08, 135.97, 115.45), 90.0),
    "SM_Chair": (_SC % ("SM_Chair", "SM_Chair"), (-41.94, -40.45, 0.0), (40.21, 40.45, 115.35), 90.0),
    "SM_TableRound": (_SC % ("SM_TableRound", "SM_TableRound"), (-61.54, -61.54, 0.11), (61.54, 61.54, 70.31), 0.0),
    "SM_Bush": (_SC % ("SM_Bush", "SM_Bush"), (-56.4, -61.01, -0.47), (56.4, 61.01, 137.51), 0.0),
}


@dataclass(frozen=True)
class Item:
    name: str
    w: float                 # along the wall it backs onto
    d: float                 # depth, back to front
    h: float
    kind: str
    place: str               # wall | corner | center
    front: float             # floor kept free in front (cm)
    tall: bool               # blocks a window behind it whose sill is below its top (h)
    parts: tuple
    mesh: tuple = ()         # the recipe with REAL meshes (RealMeshes on), or () -- then `parts` either way


def box(x, y, z, sx, sy, sz, m):
    return ("cube", (x, y, z + sz / 2.0), (sx, sy, sz), m)


def cyl(x, y, z, dx, dy, sz, m):
    return ("cyl", (x, y, z + sz / 2.0), (dx, dy, sz), m)


def ball(x, y, z, dx, dy, sz, m):
    return ("sphere", (x, y, z + sz / 2.0), (dx, dy, sz), m)


def real(shape, x, y, z, sx, sy, sz):
    """A REAL mesh filling the box (sx, sy, sz) whose bottom centre is (x, y, z), in the mesh's own materials."""
    return (shape, (x, y, z + sz / 2.0), (sx, sy, sz), "")


def legs(w, d, h, t=5.0, inset=3.0, m="wood"):
    xs, ys = w / 2.0 - inset - t / 2.0, d / 2.0 - inset - t / 2.0
    return [box(sx * xs, sy * ys, 0.0, t, t, h, m) for sx in (-1, 1) for sy in (-1, 1)]


def _bed(w, d, pillows):
    out = [box(0.0, -d / 2 + 4, 0.0, w, 8.0, 100.0, "wood"),            # headboard
           box(0.0, 4.0, 0.0, w, d - 8.0, 30.0, "wood"),                 # frame
           box(0.0, 5.0, 30.0, w - 8.0, d - 16.0, 20.0, "mattress"),
           box(0.0, 35.0, 50.0, w - 4.0, d - 78.0, 5.0, "fabric")]      # duvet over the lower part
    pw = (w - 30.0) / pillows
    for k in range(pillows):
        out.append(box(-w / 2 + 15 + pw * (k + 0.5), -d / 2 + 32, 50.0, pw - 8.0, 36.0, 13.0, "linen"))
    return tuple(out)


def _wardrobe(w):
    out = [box(0.0, 0.0, 0.0, w, 62.0, 215.0, "white"), box(0.0, 0.0, 0.0, w, 62.0, 8.0, "wood_dark")]
    doors = max(2, int(round(w / 50.0)))
    for k in range(1, doors):
        out.append(box(-w / 2 + w * k / doors, 30.5, 10.0, 1.0, 1.0, 200.0, "wood_dark"))
    for k in range(doors):
        x = -w / 2 + w * (k + 0.5) / doors + (8.0 if k % 2 else -8.0)
        out.append(box(x, 30.0, 95.0, 2.0, 2.0, 30.0, "steel"))
    return tuple(out)


def _sofa(w, d):
    arm = 20.0
    out = [box(0.0, 3.0, 8.0, w, d - 6.0, 30.0, "fabric"),                # base
           box(0.0, -d / 2 + 11, 8.0, w - 2 * arm, 22.0, 75.0, "fabric"),  # back
           box(-w / 2 + arm / 2, 0.0, 8.0, arm, d, 55.0, "fabric"),
           box(w / 2 - arm / 2, 0.0, 8.0, arm, d, 55.0, "fabric")]
    n = 3 if w > 190 else 2
    cw = (w - 2 * arm) / n
    for k in range(n):
        out.append(box(-w / 2 + arm + cw * (k + 0.5), 10.0, 38.0, cw - 3.0, d - 30.0, 12.0, "fabric2"))
        out.append(box(-w / 2 + arm + cw * (k + 0.5), -d / 2 + 30, 50.0, cw - 10.0, 14.0, 34.0, "accent"))
    out += [box(sx * (w / 2 - 6), sy * (d / 2 - 6), 0.0, 6.0, 6.0, 8.0, "black") for sx in (-1, 1) for sy in (-1, 1)]
    return tuple(out)


def _chair(w=46.0, d=50.0):
    return (box(0.0, 2.0, 44.0, w, d - 4.0, 5.0, "wood"), box(0.0, -d / 2 + 2, 49.0, w, 4.0, 43.0, "wood"),
            *legs(w, d, 44.0, 4.0, 2.0, "wood"))


def _table(w, d, h=75.0, m="wood"):
    return (box(0.0, 0.0, h - 4.0, w, d, 4.0, m), *legs(w, d, h - 4.0, 6.0, 6.0, m))


def _counter(w, extra=()):
    return (box(0.0, -1.0, 8.0, w, 60.0, 80.0, "white"), box(0.0, -1.0, 0.0, w - 4.0, 54.0, 8.0, "black"),
            box(0.0, 0.0, 88.0, w, 62.0, 4.0, "counter"), *extra)


ITEMS = {}


def _add(name, w, d, h, kind, place, front, tall, parts, mesh=()):
    ITEMS[name] = Item(name, float(w), float(d), float(h), kind, place, float(front), tall, tuple(parts), tuple(mesh))


# bedroom
_add("Bed_Single", 100, 210, 100, "bed", "wall", 60, False, _bed(100.0, 210.0, 1))
_add("Bed_Double", 160, 215, 100, "bed", "wall", 60, False, _bed(160.0, 215.0, 2))
_add("Bed_King", 185, 220, 100, "bed", "wall", 60, False, _bed(185.0, 220.0, 2))
_add("Nightstand", 45, 40, 55, "nightstand", "wall", 0, False,
     (box(0.0, 0.0, 0.0, 45.0, 40.0, 50.0, "wood"), box(0.0, 19.5, 30.0, 38.0, 1.0, 12.0, "wood_dark"),
      cyl(8.0, -5.0, 50.0, 12.0, 12.0, 14.0, "steel"), cyl(8.0, -5.0, 62.0, 24.0, 24.0, 18.0, "linen")))
for _w in (100, 150, 200):
    _add("Wardrobe_%d" % _w, _w, 62, 215, "wardrobe", "wall", 70, True, _wardrobe(float(_w)))
_add("Dresser", 110, 48, 175, "dresser", "wall", 70, True,
     (box(0.0, 0.0, 0.0, 110.0, 48.0, 82.0, "wood"), box(0.0, 0.0, 82.0, 110.0, 48.0, 3.0, "wood_dark"),
      box(0.0, -22.0, 100.0, 70.0, 2.0, 75.0, "mirror")))
_add("Desk", 120, 60, 75, "desk", "wall", 80, False, _table(120.0, 60.0, 75.0))
_add("Chair", 46, 50, 92, "chair", "center", 0, False, _chair())
# living
_add("Sofa", 220, 92, 85, "sofa", "wall", 80, False, _sofa(220.0, 92.0), (real("SM_Couch", 0, 0, 0, 220, 92, 85),))
_add("Sofa_Small", 170, 88, 85, "sofa", "wall", 80, False, _sofa(170.0, 88.0), (real("SM_Couch", 0, 0, 0, 170, 88, 85),))
_add("Armchair", 85, 85, 85, "armchair", "corner", 40, False, _sofa(85.0, 85.0), (real("SM_Chair", 0, 0, 0, 85, 85, 85),))
_add("CoffeeTable", 110, 60, 42, "coffee_table", "center", 0, False,
     (box(0.0, 0.0, 38.0, 110.0, 60.0, 4.0, "wood"), box(0.0, 0.0, 10.0, 100.0, 50.0, 2.0, "wood_dark"),
      *legs(110.0, 60.0, 38.0, 4.0, 4.0, "black")))
_add("TVUnit", 170, 45, 135, "tv", "wall", 60, True,
     (box(0.0, 0.0, 0.0, 170.0, 45.0, 50.0, "wood_dark"), box(0.0, -8.0, 50.0, 30.0, 20.0, 4.0, "black"),
      box(0.0, -8.0, 54.0, 6.0, 6.0, 8.0, "black"), box(0.0, -8.0, 60.0, 130.0, 5.0, 75.0, "screen")))
_add("Bookshelf", 100, 35, 200, "bookshelf", "wall", 60, True,
     (box(-48.5, 0.0, 0.0, 3.0, 35.0, 200.0, "wood"), box(48.5, 0.0, 0.0, 3.0, 35.0, 200.0, "wood"),
      box(0.0, -16.5, 0.0, 94.0, 2.0, 200.0, "wood_dark"),
      *[box(0.0, 0.0, z, 94.0, 33.0, 3.0, "wood") for z in (0.0, 48.0, 96.0, 144.0, 197.0)],
      box(-25.0, 2.0, 3.0, 36.0, 24.0, 30.0, "accent"), box(20.0, 2.0, 51.0, 44.0, 24.0, 28.0, "fabric2"),
      box(-10.0, 2.0, 99.0, 60.0, 24.0, 32.0, "accent"), box(28.0, 2.0, 147.0, 30.0, 24.0, 26.0, "fabric")))
_add("FloorLamp", 40, 40, 165, "lamp", "corner", 0, False,
     (cyl(0.0, 0.0, 0.0, 30.0, 30.0, 3.0, "black"), cyl(0.0, 0.0, 3.0, 4.0, 4.0, 132.0, "steel"),
      cyl(0.0, 0.0, 135.0, 40.0, 40.0, 30.0, "linen")))
_add("Plant", 50, 50, 125, "plant", "corner", 0, False,
     (cyl(0.0, 0.0, 0.0, 40.0, 40.0, 42.0, "pot"), ball(0.0, 0.0, 38.0, 50.0, 50.0, 55.0, "plant"),
      ball(-6.0, 4.0, 78.0, 34.0, 34.0, 47.0, "plant")),
     (cyl(0.0, 0.0, 0.0, 40.0, 40.0, 42.0, "pot"), real("SM_Bush", 0, 0, 38, 50, 50, 87)))
_add("ShoeCabinet", 100, 35, 95, "shoe_cabinet", "wall", 60, False,
     (box(0.0, 0.0, 0.0, 100.0, 35.0, 92.0, "white"), box(0.0, 0.0, 92.0, 100.0, 35.0, 3.0, "wood")))
_add("Console", 100, 35, 80, "console", "wall", 50, False,
     (*_table(100.0, 35.0, 80.0, "wood_dark"), cyl(30.0, 0.0, 80.0, 14.0, 14.0, 28.0, "accent")))
_add("Rug_Large", 240, 170, 1, "rug", "center", 0, False, (box(0.0, 0.0, 0.0, 240.0, 170.0, 1.0, "rug"),))
_add("Rug_Small", 160, 110, 1, "rug", "center", 0, False, (box(0.0, 0.0, 0.0, 160.0, 110.0, 1.0, "rug"),))
# kitchen
_add("Counter", 60, 62, 92, "counter", "wall", 90, False, _counter(60.0))
_add("Sink", 80, 62, 92, "sink", "wall", 90, False,
     _counter(80.0, (box(0.0, 4.0, 89.0, 52.0, 38.0, 4.0, "steel"), cyl(0.0, -24.0, 92.0, 4.0, 4.0, 28.0, "steel"))))
_add("Stove", 60, 62, 92, "stove", "wall", 90, False,
     _counter(60.0, (box(0.0, 1.0, 92.0, 56.0, 50.0, 1.0, "black"), box(0.0, 30.5, 20.0, 54.0, 1.0, 55.0, "black"),
                     *[cyl(x, y, 93.0, 16.0, 16.0, 1.0, "steel") for x in (-13.0, 13.0) for y in (-11.0, 13.0)])))
_add("Fridge", 70, 68, 195, "fridge", "wall", 90, True,
     (box(0.0, 0.0, 0.0, 70.0, 66.0, 195.0, "steel"), box(0.0, 33.5, 120.0, 66.0, 1.0, 1.0, "black"),
      box(-28.0, 33.5, 70.0, 2.0, 1.0, 40.0, "black"), box(-28.0, 33.5, 135.0, 2.0, 1.0, 40.0, "black")))
for _w in (60, 80):
    _add("UpperCab_%d" % _w, _w, 35, 70, "upper", "wall", 0, False,
         (box(0.0, 0.0, 0.0, float(_w), 35.0, 70.0, "white"), box(0.0, 17.0, 0.0, _w - 2.0, 1.0, 1.0, "wood_dark")))
_add("Island", 160, 90, 92, "island", "center", 90, False,
     (box(0.0, 0.0, 0.0, 150.0, 80.0, 88.0, "white"), box(0.0, 0.0, 88.0, 160.0, 90.0, 4.0, "counter")))
# dining
_add("Table_2", 80, 75, 75, "dining_table", "center", 0, False, _table(80.0, 75.0),
     (real("SM_TableRound", 0, 0, 0, 80, 75, 75),))
_add("Table_4", 140, 85, 75, "dining_table", "center", 0, False, _table(140.0, 85.0))
_add("Table_6", 190, 95, 75, "dining_table", "center", 0, False, _table(190.0, 95.0))
_add("Sideboard", 150, 45, 82, "sideboard", "wall", 60, False,
     (box(0.0, 0.0, 10.0, 150.0, 45.0, 72.0, "wood"), *legs(150.0, 45.0, 10.0, 4.0, 6.0, "black"),
      cyl(-45.0, 0.0, 82.0, 18.0, 18.0, 30.0, "accent")))
# bathroom
_add("Toilet", 40, 68, 78, "toilet", "wall", 55, False,
     (box(0.0, 6.0, 0.0, 36.0, 52.0, 40.0, "porcelain"), box(0.0, 8.0, 40.0, 38.0, 48.0, 3.0, "white"),
      box(0.0, -26.0, 0.0, 40.0, 16.0, 78.0, "porcelain")))
_add("Vanity", 80, 50, 150, "vanity", "wall", 70, True,
     (box(0.0, 0.0, 10.0, 80.0, 50.0, 72.0, "wood"), box(0.0, 0.0, 82.0, 80.0, 50.0, 4.0, "porcelain"),
      box(0.0, 4.0, 86.0, 46.0, 34.0, 3.0, "white"), cyl(0.0, -18.0, 86.0, 4.0, 4.0, 22.0, "steel"),
      box(0.0, -24.0, 105.0, 60.0, 2.0, 45.0, "mirror")))
_add("Basin", 45, 32, 85, "basin", "wall", 50, False,
     (box(0.0, 0.0, 70.0, 45.0, 32.0, 15.0, "porcelain"), box(0.0, -12.0, 0.0, 12.0, 8.0, 70.0, "porcelain")))
_add("Bathtub", 170, 75, 58, "bathtub", "wall", 55, False,
     (box(0.0, 0.0, 0.0, 170.0, 75.0, 56.0, "porcelain"), box(0.0, 0.0, 56.0, 154.0, 59.0, 1.0, "white"),
      cyl(-70.0, -25.0, 57.0, 5.0, 5.0, 14.0, "steel")))
_add("Shower", 90, 90, 200, "shower", "wall", 55, True,
     (box(0.0, 0.0, 0.0, 90.0, 90.0, 6.0, "porcelain"), box(0.0, 44.0, 6.0, 90.0, 2.0, 194.0, "glass"),
      box(44.0, 0.0, 6.0, 2.0, 88.0, 194.0, "glass"), cyl(-30.0, -38.0, 150.0, 14.0, 14.0, 3.0, "steel")))
# laundry and storage
_add("Washer", 60, 62, 85, "washer", "wall", 80, False,
     (box(0.0, 0.0, 0.0, 60.0, 62.0, 85.0, "white"), cyl(0.0, 30.0, 25.0, 34.0, 2.0, 34.0, "black")))
_add("Dryer", 60, 62, 85, "dryer", "wall", 80, False,
     (box(0.0, 0.0, 0.0, 60.0, 62.0, 85.0, "white"), cyl(0.0, 30.0, 25.0, 34.0, 2.0, 34.0, "steel")))
_add("Shelf", 90, 40, 180, "shelf", "wall", 60, True,
     (box(-43.5, 0.0, 0.0, 3.0, 40.0, 180.0, "steel"), box(43.5, 0.0, 0.0, 3.0, 40.0, 180.0, "steel"),
      *[box(0.0, 0.0, z, 84.0, 38.0, 2.0, "wood") for z in (10.0, 60.0, 110.0, 178.0)],
      box(-15.0, 0.0, 12.0, 40.0, 30.0, 30.0, "fabric2"), box(20.0, 0.0, 112.0, 35.0, 30.0, 25.0, "accent")))
_add("Stool", 40, 40, 75, "stool", "center", 0, False,
     (cyl(0.0, 0.0, 70.0, 36.0, 36.0, 5.0, "wood"), cyl(0.0, 0.0, 0.0, 6.0, 6.0, 70.0, "steel"),
      cyl(0.0, 0.0, 0.0, 30.0, 30.0, 2.0, "steel")))

# what each room type is furnished with, in order: (group or item, required)
RECIPES = {
    "Main": [("kitchen_run", True), ("bed_group", True), ("sofa_group", False), ("dining_small", False),
             ("Plant", False)],
    "Living": [("sofa_group", True), ("ShoeCabinet", False), ("Bookshelf", False), ("Armchair", False),
               ("FloorLamp", False), ("Plant", False)],
    "Kitchen": [("kitchen_run", True), ("island", False), ("dining_small", False)],
    "Dining": [("dining_group", True), ("Sideboard", False), ("Plant", False)],
    "Master": [("bed_group", True), ("wardrobe", False), ("Dresser", False), ("Armchair", False), ("Plant", False)],
    "Bedroom": [("bed_group", True), ("wardrobe", False), ("desk_group", False), ("Plant", False)],
    "Study": [("desk_group", True), ("Bookshelf", False), ("Armchair", False), ("Plant", False)],
    "Bath": [("bathing", True), ("Toilet", True), ("Vanity", True)],
    "WC": [("Toilet", True), ("Basin", False)],
    "Laundry": [("Washer", True), ("Dryer", False), ("Shelf", False)],
    "Corridor": [("Console", False), ("Plant", False)],
    "Storage": [("Shelf", False)],
}
