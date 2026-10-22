"""PyWorld's rule tables (视频："建筑规则表"、散布规则): settlement kinds, streets, building types and biomes."""

KIND_RADII = (("Town", 20000.0), ("Village", 12000.0), ("Hamlet", 0.0))   # a location's kind by its radius (cm)


def kind_of(radius_cm):
    for kind, r in KIND_RADII:
        if radius_cm >= r:
            return kind
    return "Hamlet"


STREETS = {"Town": (5, True), "Village": (3, False), "Hamlet": (2, False)}     # radial streets, ring street
MIN_BUILDINGS = {"Town": 60, "Village": 20, "Hamlet": 5}


def zone_of(fraction):
    """The zone at a distance of `fraction` x radius from the centre (视频：中心 → 外围)."""
    return "core" if fraction < 0.35 else ("residential" if fraction < 0.75 else "outskirts")


# w = frontage (along the street), d = depth, in cm; weights per zone; cap per settlement kind.
BUILDINGS = [
    {"kind": "Shop", "w": (800.0, 1200.0), "d": (900.0, 1200.0), "height": ("Mid", "High"),
     "weights": {"core": 3.0, "residential": 0.5}, "cap": {"Town": 24, "Village": 6, "Hamlet": 0}},
    {"kind": "House", "w": (800.0, 1100.0), "d": (800.0, 1100.0), "height": ("Low", "Mid"),
     "weights": {"core": 2.0, "residential": 5.0, "outskirts": 1.0}, "cap": {"Town": 150, "Village": 50, "Hamlet": 10}},
    {"kind": "Farmhouse", "w": (1000.0, 1400.0), "d": (900.0, 1200.0), "height": ("Low",),
     "weights": {"outskirts": 3.0}, "cap": {"Town": 10, "Village": 6, "Hamlet": 3}, "field": True},
    {"kind": "Barn", "w": (1400.0, 1800.0), "d": (1000.0, 1400.0), "height": ("Mid",),
     "weights": {"outskirts": 1.5}, "cap": {"Town": 6, "Village": 4, "Hamlet": 2}},
    {"kind": "Shed", "w": (500.0, 700.0), "d": (500.0, 700.0), "height": ("Low",),
     "weights": {"outskirts": 2.0, "residential": 0.3}, "cap": {"Town": 12, "Village": 6, "Hamlet": 4}},
]
LANDMARKS = [   # placed first, facing the plaza, in the widest gaps between roads and streets (w is the radial length)
    {"kind": "Church", "settlements": ("Town", "Village"), "w": 2500.0, "d": 1400.0, "height": ("High",), "tower": True},
    {"kind": "TownHall", "settlements": ("Town",), "w": 1800.0, "d": 1300.0, "height": ("High",)},
]
TOWER = {"kind": "BellTower", "height": ("Tower",)}
GROUPS = ("Low", "Mid", "High", "Tower")
HEIGHT = {"Low": 450.0, "Mid": 750.0, "High": 1050.0, "Tower": 2400.0}   # the grammar's Size per group (cm)
WALL_TOP = dict(HEIGHT)          # top of the grammar's walls per group; Task 18 replaces it with the measured tops


def pick(zone, kind, counts, rng):
    """A building type for a plot in `zone` of a `kind` settlement (weighted, below its cap), or None."""
    cands = [(b, b["weights"].get(zone, 0.0)) for b in BUILDINGS
             if b["weights"].get(zone, 0.0) > 0.0 and counts.get(b["kind"], 0) < b["cap"].get(kind, 0)]
    if not cands:
        return None
    x = rng.uniform(0.0, sum(w for _b, w in cands))
    for b, w in cands:
        x -= w
        if x <= 0.0:
            return b
    return cands[-1][0]
