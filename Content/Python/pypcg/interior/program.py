"""PyInterior rule tables (spec 2026-10-28 §4.2 programs, §4.3 room types, §4.5 access, §4.9 styles) -- the BDF of the
interior: change a table, change every house. Pure."""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class RoomType:
    zone: str            # public | private | service | circulation
    min_short: float     # clear interior size, cm
    min_long: float
    floor: str           # a FLOORS kind
    window: object       # an openings.WINDOWS kind, or None
    wall: str            # the style's wall palette
    label: str


ROOMS = {
    "Main": RoomType("public", 280.0, 340.0, "wood", "living", "living", "起居室"),
    "Living": RoomType("public", 300.0, 340.0, "wood", "living", "living", "客厅"),
    "Kitchen": RoomType("public", 180.0, 220.0, "tile", "kitchen", "wet", "厨房"),
    "Dining": RoomType("public", 240.0, 260.0, "wood", "dining", "living", "餐厅"),
    "Master": RoomType("private", 280.0, 300.0, "wood", "bedroom", "bedroom", "主卧"),
    "Bedroom": RoomType("private", 240.0, 270.0, "wood", "bedroom", "bedroom", "卧室"),
    "Study": RoomType("private", 200.0, 240.0, "wood", "bedroom", "bedroom", "书房"),
    "Bath": RoomType("service", 140.0, 180.0, "tile", "high", "wet", "卫生间"),
    "WC": RoomType("service", 85.0, 130.0, "tile", "high", "wet", "厕所"),
    "Laundry": RoomType("service", 140.0, 160.0, "tile", "high", "wet", "洗衣房"),
    "Corridor": RoomType("circulation", 95.0, 110.0, "wood", None, "neutral", "走廊"),
    "Storage": RoomType("service", 90.0, 100.0, "wood", None, "neutral", "储藏间"),     # the filler
}
FLOORS = ("wood", "tile")


@dataclass(frozen=True)
class Slot:
    type: str
    weight: float
    optional: int = 0    # 0 = required; k > 0 = dropped when a layout fails, lowest k first


@dataclass(frozen=True)
class Program:
    name: str
    min_area_m2: float
    public: tuple
    private: tuple

    @property
    def size(self):
        return len(self.public) + len(self.private)

    def types(self):
        return [s.type for s in self.public + self.private]


PROGRAMS = (
    Program("Studio", 0.0, (Slot("Main", 4.0),), (Slot("Bath", 1.0),)),
    Program("OneBed", 34.0, (Slot("Living", 3.0), Slot("Kitchen", 1.3)), (Slot("Bedroom", 2.2), Slot("Bath", 1.0))),
    Program("TwoBed", 58.0, (Slot("Living", 3.0), Slot("Kitchen", 1.5), Slot("Dining", 1.4, 1)),
            (Slot("Master", 2.6), Slot("Bedroom", 2.1), Slot("Bath", 1.1))),
    Program("ThreeBed", 88.0, (Slot("Living", 3.2), Slot("Kitchen", 1.6), Slot("Dining", 1.6, 2)),
            (Slot("Master", 2.7), Slot("Bedroom", 2.1), Slot("Bedroom", 2.0), Slot("Bath", 1.2), Slot("WC", 0.5, 1))),
    Program("FourBed", 130.0, (Slot("Living", 3.4), Slot("Kitchen", 1.8), Slot("Dining", 1.8, 3)),
            (Slot("Master", 2.9), Slot("Bedroom", 2.1), Slot("Bedroom", 2.1), Slot("Bedroom", 2.0), Slot("Bath", 1.3),
             Slot("WC", 0.5, 2), Slot("Study", 1.5, 1), Slot("Laundry", 0.8, 1))),
)

# who may lead into a room (by preference); the entry rooms take the front door
ENTRY = ("Main", "Living")
ACCESS = {
    "Main": (), "Living": (),
    "Kitchen": ("Dining", "Living", "Main", "Corridor"),
    "Dining": ("Living", "Kitchen", "Main"),
    "Corridor": ("Living", "Dining", "Main", "Corridor"),
    "Master": ("Corridor", "Living", "Dining"),
    "Bedroom": ("Corridor", "Living", "Dining", "Main"),
    "Study": ("Corridor", "Living", "Dining"),
    "Bath": ("Corridor", "Living", "Main", "Dining", "Master", "Bedroom"),
    "WC": ("Corridor", "Living", "Dining", "Kitchen"),
    "Laundry": ("Kitchen", "Corridor", "Dining"),
    "Storage": ("Corridor", "Main", "Living", "Kitchen", "Dining", "Master", "Bedroom", "Study"),
}
OPEN = {frozenset(p) for p in (("Living", "Kitchen"), ("Living", "Dining"), ("Kitchen", "Dining"), ("Main", "Kitchen"),
                               ("Main", "Dining"))}       # these links are openings without a door leaf
DOORWAY = {"Corridor"}                                   # entering these is a doorway (frame, no leaf)

COLORS = {   # sRGB 0..1; pyinterior_materials.py makes one material instance per entry
    "White": (0.93, 0.93, 0.91), "OffWhite": (0.90, 0.88, 0.83), "Cream": (0.95, 0.92, 0.84),
    "Greige": (0.78, 0.74, 0.68), "Linen": (0.85, 0.81, 0.74), "Sand": (0.86, 0.78, 0.64),
    "Sage": (0.69, 0.75, 0.66), "Mint": (0.74, 0.86, 0.80), "Sky": (0.70, 0.79, 0.86),
    "Blush": (0.88, 0.76, 0.74), "Butter": (0.93, 0.87, 0.66), "Lavender": (0.77, 0.74, 0.86),
    "Terracotta": (0.77, 0.47, 0.36), "Clay": (0.74, 0.55, 0.45), "Rust": (0.62, 0.30, 0.20),
    "Mustard": (0.80, 0.62, 0.22), "Olive": (0.55, 0.56, 0.40), "Forest": (0.24, 0.38, 0.30),
    "Teal": (0.20, 0.45, 0.47), "Navy": (0.18, 0.25, 0.38), "Slate": (0.42, 0.46, 0.52),
    "Charcoal": (0.22, 0.23, 0.25), "Black": (0.04, 0.04, 0.045), "Steel": (0.62, 0.63, 0.65),
    "Plaster_White": (0.88, 0.87, 0.84), "Plaster_Warm": (0.86, 0.76, 0.62), "Plaster_Grey": (0.60, 0.61, 0.62),
    "Porcelain": (0.96, 0.96, 0.95), "Screen": (0.02, 0.02, 0.025),
    "Glass": (0.62, 0.74, 0.80), "Leaf": (0.22, 0.42, 0.18), "Mirror": (0.90, 0.91, 0.92),
    "Oak": (0.70, 0.53, 0.35), "Walnut": (0.36, 0.24, 0.16), "Pine": (0.82, 0.67, 0.46), "Ebony": (0.16, 0.12, 0.10),
}
SURFACE = {"Steel": (0.35, 1.0), "Mirror": (0.04, 1.0), "Glass": (0.05, 0.0), "Screen": (0.15, 0.0),
           "Porcelain": (0.2, 0.0), "Black": (0.4, 0.0)}           # colour -> (roughness, metallic); the rest (0.6, 0)
FLOOR_MATERIALS = ("Floor_Oak", "Floor_Walnut", "Floor_WalnutWorn", "Floor_Pine", "Tile_White", "Tile_Checker",
                   "Tile_Grey", "Concrete")
STYLES = {
    "Scandi": {"facade": "Plaster_White", "trim": "White", "door": "OffWhite",
               "walls": {"living": ("OffWhite", "Greige", "Sage"), "bedroom": ("Sky", "Sage", "Blush", "Lavender", "Mint"),
                         "wet": ("White", "Mint"), "neutral": ("OffWhite",)},
               "floors": {"wood": "Floor_Oak", "tile": "Tile_White"},
               "fabric": ("Linen", "Slate", "Sage", "Mustard", "Sky"), "accent": ("Mustard", "Forest", "Navy", "Blush"),
               "wood": "Oak", "wood_dark": "Walnut"},
    "Warm": {"facade": "Plaster_Warm", "trim": "Cream", "door": "Clay",
             "walls": {"living": ("Sand", "Cream", "Butter"), "bedroom": ("Blush", "Butter", "Sand", "Sage"),
                       "wet": ("Cream", "Sand"), "neutral": ("Cream",)},
             "floors": {"wood": "Floor_Walnut", "tile": "Tile_Checker"},
             "fabric": ("Terracotta", "Mustard", "Olive", "Rust", "Linen"), "accent": ("Rust", "Olive", "Teal"),
             "wood": "Walnut", "wood_dark": "Ebony"},
    "Modern": {"facade": "Plaster_Grey", "trim": "Charcoal", "door": "Charcoal",
               "walls": {"living": ("White", "Greige", "Slate"), "bedroom": ("Greige", "Slate", "Sky", "Lavender"),
                         "wet": ("White", "Greige"), "neutral": ("White",)},
               "floors": {"wood": "Floor_WalnutWorn", "tile": "Tile_Grey"},
               "fabric": ("Charcoal", "Slate", "Teal", "Linen", "Navy"), "accent": ("Teal", "Mustard", "Black"),
               "wood": "Pine", "wood_dark": "Charcoal"},
}


def choose(area_m2):
    best = PROGRAMS[0]
    for p in PROGRAMS:
        if area_m2 >= p.min_area_m2 - 1e-9:
            best = p
    return best


def targets(slots, zone_area):
    total = sum(s.weight for s in slots)
    return [zone_area * s.weight / total for s in slots]


def _drop_order(p):
    """The optional slots of p, the first to drop first: lowest rank, then the later one."""
    opt = [(s.optional, -k, zone) for zone in ("public", "private") for k, s in enumerate(getattr(p, zone)) if s.optional]
    return [(zone, -nk) for _r, nk, zone in sorted(opt)]


def _variants(p):
    yield p
    cur = p
    while True:
        order = _drop_order(cur)
        if not order:
            return
        zone, k = order[0]
        slots = list(getattr(cur, zone))
        del slots[k]
        cur = replace(cur, **{zone: tuple(slots)})
        yield cur


def fallbacks(program):
    """program, then program with its optional rooms dropped one by one, then each lower program the same way -- never
    more rooms than the one before -- ending in Studio."""
    names = [p.name for p in PROGRAMS]
    start = names.index(program.name)
    seen, last = set(), None
    for base in [program] + [PROGRAMS[k] for k in range(start - 1, -1, -1)]:
        for v in _variants(base):
            if v in seen or (last is not None and v.size > last):
                continue
            seen.add(v)
            last = v.size
            yield v
