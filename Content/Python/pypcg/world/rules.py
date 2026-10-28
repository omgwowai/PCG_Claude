"""PyWorld's rule tables (视频："建筑规则表"; City Sample 式的分级规则): settlement kinds, zones, the lot table, and
the archetypes that give each building a style code, a storey count from the settlement's height noise, a facade
colour and a roof colour. The styles and their modules are bdf.py and kit.py; the vegetation rules ecology.py and
flora.py."""
from . import bdf, kit as K, noise

KIND_RADII = (("Town", 20000.0), ("Village", 12000.0), ("Hamlet", 0.0))   # a location's kind by its radius (cm)


def kind_of(radius_cm):
    for kind, r in KIND_RADII:
        if radius_cm >= r:
            return kind
    return "Hamlet"


MIN_BUILDINGS = {"Town": 60, "Village": 20, "Hamlet": 5}


def zone_of(fraction):
    """The zone at a distance of `fraction` x radius from the centre (视频：中心 → 外围)."""
    return "core" if fraction < 0.35 else ("residential" if fraction < 0.75 else "outskirts")


# The lot table: w = frontage (along the street), d = depth, in cm; `w_core` the frontage of the core's terraces;
# weights per zone; cap per settlement kind.
BUILDINGS = [
    {"kind": "Shop", "w": (800.0, 1200.0), "w_core": (650.0, 1100.0), "d": (900.0, 1300.0),
     "weights": {"core": 3.0, "residential": 0.5}, "cap": {"Town": 30, "Village": 8, "Hamlet": 0}},
    {"kind": "House", "w": (800.0, 1100.0), "w_core": (650.0, 1050.0), "d": (800.0, 1100.0),
     "weights": {"core": 2.0, "residential": 5.0, "outskirts": 1.0}, "cap": {"Town": 150, "Village": 50, "Hamlet": 10}},
    {"kind": "Farmhouse", "w": (1000.0, 1400.0), "d": (900.0, 1200.0),
     "weights": {"outskirts": 3.0}, "cap": {"Town": 10, "Village": 6, "Hamlet": 3}, "field": True},
    {"kind": "Barn", "w": (1400.0, 1800.0), "d": (1000.0, 1400.0),
     "weights": {"outskirts": 1.5}, "cap": {"Town": 6, "Village": 4, "Hamlet": 2}},
    {"kind": "Shed", "w": (600.0, 850.0), "d": (550.0, 800.0),
     "weights": {"outskirts": 2.0, "residential": 0.3}, "cap": {"Town": 12, "Village": 6, "Hamlet": 4}},
]
LANDMARKS = [   # placed first, facing the plaza, in the widest gaps between roads and streets (w is the radial length)
    {"kind": "Church", "settlements": ("Town", "Village"), "w": 2500.0, "d": 1400.0, "tower": True},
    {"kind": "TownHall", "settlements": ("Town",), "w": 1300.0, "d": 1800.0},      # its long side faces the plaza
]
TOWER = {"kind": "BellTower", "w": 900.0, "d": 900.0}
# leftover lots (City Sample's stage 13): behind a street house, by zone, the chance of an outbuilding (a shed or a
# workshop facing the house) and of a kitchen garden (a Field area: W7 hedges it, W9 digs it)
OUTBUILDING = {"kind": "Outbuilding", "w": (500.0, 700.0), "d": (500.0, 650.0)}
BACKYARD = {"core": (0.2, 0.15), "residential": (0.45, 0.4), "outskirts": (0.25, 0.1)}
# the street cross-section by zone (City Sample's sidewalk kit): raised sidewalks either side in the core and the
# residential zone, a bare lane between verges at the outskirts
SIDEWALKS = {"core": True, "residential": True, "outskirts": False}
# zone -> gap between neighbouring lots on a front (cm), and the chance that a lot instead shares its neighbour's wall
# (0 gap: terraces in the core, semi-detached pairs in the residential zone)
GAPS = {"core": (0.0, 0.0), "residential": (250.0, 500.0), "outskirts": (400.0, 800.0)}
TERRACE_P = {"core": 1.0, "residential": 0.35, "outskirts": 0.0}

# Archetypes (City Sample: each size class's BuildingsStyles list): per lot kind and zone, the style codes with their
# weights ("*" = any zone), the storey range drawn from the height noise, the ground floor's use, roof overrides.
ARCHETYPES = {
    "Shop": {"use": "shop",
             "styles": {"core": [("PLA", 3.0), ("PLB", 2.0), ("BRB", 1.0), ("PLC", 0.5)],
                        "residential": [("PLA", 1.0), ("PLC", 1.0), ("BRB", 1.0)], "*": [("BRB", 1.0)]},
             "floors": {"core": (3, 4), "residential": (2, 3), "*": (2, 2)}},
    "House": {"use": "house",
              "styles": {"core": [("PLA", 2.0), ("PLB", 2.0), ("LSB", 1.5), ("LSA", 0.5), ("BRB", 1.0)],
                         "residential": [("PLC", 2.0), ("BRB", 2.0), ("BRA", 2.0), ("PLA", 1.0)],
                         "outskirts": [("BRA", 3.0), ("PLC", 1.0)]},
              "floors": {"core": (3, 4), "residential": (2, 3), "outskirts": (1, 2)}},
    "Farmhouse": {"use": "house", "styles": {"*": [("BRA", 1.0)]}, "floors": {"*": (1, 2)}},
    "Barn": {"use": "house", "styles": {"*": [("BRA", 1.0)]}, "floors": {"*": (1, 1)}, "roof_tints": ("Brown",),
             "tints": ("Umber",), "k": 2.0},
    "Shed": {"use": "house", "styles": {"*": [("BRA", 1.0)]}, "floors": {"*": (1, 1)}, "roof_tints": ("Brown", "Slate")},
    "Outbuilding": {"use": "house", "styles": {"*": [("BRA", 1.0)]}, "floors": {"*": (1, 1)},
                    "roof_tints": ("Brown", "Terracotta", "Slate")},
    "Church": {"use": "house", "styles": {"*": [("LSA", 1.0)]}, "floors": {"*": (2, 2)}, "roof_tints": ("Slate",),
               "landmark": True},
    "BellTower": {"use": "house", "styles": {"*": [("LSA", 1.0)]}, "floors": {"*": (5, 5)}, "roof_tints": ("Slate",),
                  "landmark": True},
    "TownHall": {"use": "house", "styles": {"*": [("LSA", 1.0)]}, "floors": {"*": (3, 4)},
                 "roof_tints": ("BlueSlate", "Slate"), "landmark": True},
}
STONE = ("LSA", "LSB")            # limestone only in towns
HEIGHT_CELL = 7000.0              # the height noise's scale (cm): neighbouring buildings share a skyline
PLAZA_BONUS = 1                   # one more storey round the plaza
# the settlement's rank sets its skyline (City Sample: a height band per district): storeys added to the core's and
# the residential zone's houses and shops by settlement kind; the outskirts' farms and the landmarks are the same
# everywhere
RANK_STOREYS = {"Town": 0, "Village": -1, "Hamlet": -1}
RANKED_ZONES = ("core", "residential")


def frontage(spec, zone):
    return spec["w_core"] if zone == "core" and "w_core" in spec else spec["w"]


def styles_for(arch, zone, settlement):
    styles = arch["styles"].get(zone) or arch["styles"]["*"]
    return [(s, w) for s, w in styles if settlement == "Town" or s not in STONE or arch.get("landmark")]


def _weighted(items, rng):
    x = rng.uniform(0.0, sum(w for _s, w in items))
    for s, w in items:
        x -= w
        if x <= 0.0:
            return s
    return items[-1][0]


def dress(kind, zone, settlement, x, y, sid, w, d, rng, near_plaza=False, avoid_tint=None):
    """Style, storeys, colours and the ground floor's use of one building (City Sample: style from the class's list,
    height from a noise texture, its band from the settlement's rank). Only styles whose minimum wall fits the lot
    are drawn."""
    arch = ARCHETYPES[kind]
    styles = [(s, wt) for s, wt in styles_for(arch, zone, settlement) if bdf.STYLES[s]["min_wall"] <= min(w, d)]
    style = _weighted(styles or [("BRA", 1.0)], rng)
    lo, hi = arch["floors"].get(zone) or arch["floors"]["*"]
    if zone in RANKED_ZONES and not arch.get("landmark"):
        rank = RANK_STOREYS.get(settlement, 0)
        lo, hi = max(1, lo + rank), max(1, hi + rank)
    h = noise.value(x / HEIGHT_CELL, y / HEIGHT_CELL, sid + 101)
    floors = lo + min(hi - lo, int(h * (hi - lo + 1))) + (PLAZA_BONUS if near_plaza else 0)
    slo, shi = bdf.STYLES[style]["floors"]
    floors = max(slo, min(shi, floors))
    palette = arch.get("tints") or list(K.TINTS[bdf.family(style)["palette"]])
    tint = rng.choice([t for t in palette if t != avoid_tint] or palette)
    return {"style": style, "floors": floors, "tint": tint, "use": arch["use"],
            "roof_tint": rng.choice(arch.get("roof_tints") or bdf.STYLES[style]["roof"]["tints"]),
            "k": arch.get("k"), "seed": rng.randrange(1 << 30)}


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
