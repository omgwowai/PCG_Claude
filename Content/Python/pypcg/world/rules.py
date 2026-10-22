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
    {"kind": "Shed", "w": (800.0, 950.0), "d": (800.0, 950.0), "height": ("Low",),
     "weights": {"outskirts": 2.0, "residential": 0.3}, "cap": {"Town": 12, "Village": 6, "Hamlet": 4}},
]
LANDMARKS = [   # placed first, facing the plaza, in the widest gaps between roads and streets (w is the radial length)
    {"kind": "Church", "settlements": ("Town", "Village"), "w": 2500.0, "d": 1400.0, "height": ("High",), "tower": True},
    {"kind": "TownHall", "settlements": ("Town",), "w": 1800.0, "d": 1300.0, "height": ("High",)},
]
TOWER = {"kind": "BellTower", "height": ("Tower",), "w": 900.0, "d": 900.0}
MIN_EDGE = 800.0     # shortest footprint edge the building grammar fits (W6 in the editor, 2026-10-22)
GROUPS = ("Low", "Mid", "High", "Tower")
HEIGHT = {"Low": 600.0, "Mid": 750.0, "High": 1050.0, "Tower": 1950.0}   # the grammar's Size per group (cm)
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


from . import MESH, SEA_Z


def _m(*keys):
    return tuple(MESH[k] for k in keys)


BIOMES = {   # density = probability per 7 m cell; clump mixes in low-frequency noise (0: none, 1: all)
    "rock": {"kind": "Rock", "density": 0.10, "clump": 0.0, "sink": 25.0,
             "species": [(_m("Boulder"), 1.0, (0.6, 1.5)), (_m("MossyRock"), 2.0, (2.0, 5.0))]},
    "riparian": {"kind": "Tree", "density": 0.30, "clump": 0.3, "sink": 15.0,
                 "species": [(_m(*("Alder" + v for v in "ABCD")), 3.0, (0.7, 1.05)),
                             (_m(*("Hazel" + v for v in "ABCD")), 2.0, (0.8, 1.2))]},
    "alpine": {"kind": "Tree", "density": 0.22, "clump": 0.4, "sink": 15.0,
               "species": [(_m("Pine"), 3.0, (0.8, 1.2)), (_m("Spruce"), 3.0, (2.2, 3.2)), (_m("YoungTree"), 1.0, (0.9, 1.3))]},
    "forest": {"kind": "Tree", "density": 0.35, "clump": 0.6, "sink": 15.0,
               "species": [(_m(*("Beech" + v for v in "ABCD")), 3.0, (0.6, 0.9)),
                           (_m(*("Maple" + v for v in "ABCD")), 2.0, (0.8, 1.1)),
                           (_m(*("Aspen" + v for v in "ABCD")), 2.0, (0.8, 1.1)),
                           (_m(*("Hazel" + v for v in "ABCD")), 1.0, (0.8, 1.2))]},
    "meadow": {"kind": "Tree", "density": 0.06, "clump": 1.0, "sink": 15.0,
               "species": [(_m(*("Birch" + v for v in "abcdefgh")), 2.0, (0.9, 1.2)),
                           (_m(*("Beech" + v for v in "ABCD")), 1.0, (0.5, 0.7)),
                           (_m(*("Aspen" + v for v in "ABCD")), 1.0, (0.8, 1.0))]},
}
GRASS = {"meshes": _m(*("Grass" + v for v in "ABDEFG")), "density": 0.35, "scale": (0.8, 1.3), "sink": 3.0}
ALDERS = frozenset(_m(*("Alder" + v for v in "ABCD")))


def biome_of(s):
    """The biome at a sample: sea, rock (> 34 deg), riparian (25 m from the bank or a gully), alpine (120 m above the
    valley floor), forest (slopes over 7 deg or 25 m up), else meadow."""
    if s["z"] < SEA_Z + 100.0:
        return None
    if s["slope"] >= 34.0:
        return "rock"
    if (s["river"] < 2500.0 and s["slope"] < 22.0) or (s["acc"] >= 300 and s["slope"] < 25.0):
        return "riparian"
    if s["rel"] >= 12000.0:
        return "alpine"
    if s["slope"] >= 7.0 or s["rel"] >= 2500.0:
        return "forest"
    return "meadow"


def pick_species(spec, rng):
    x = rng.uniform(0.0, sum(w for _m_, w, _s in spec["species"]))
    for meshes, w, (lo, hi) in spec["species"]:
        x -= w
        if x <= 0.0:
            return rng.choice(meshes), rng.uniform(lo, hi)
    meshes, _w, (lo, hi) = spec["species"][-1]
    return rng.choice(meshes), rng.uniform(lo, hi)
