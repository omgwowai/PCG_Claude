"""One modular building (建筑模块装配): a rectangular footprint, a style code and a storey count become the module
instances of its facades, corners, doors, props and hipped roof -- City Sample's BDF route (style -> vertical grammar
-> per-level horizontal grammar by wall length -> modules -> props, rooftop) over the Megascans kit of kit.py.

Footprint frame: centre (x, y), `w` along the yaw direction, `d` across it. Edges run clockwise from the +d side:
0 (+d side, length w), 1 (+w end, length d), 2 (-d side, length w), 3 (-w end, length d); a module placed along an
edge with the edge's yaw faces out (kit.py's convention). `front` is the edge on the street. Pure."""
import math
import random

from . import bdf, kit as K

SPECIAL_LEVELS = {"Church": ["FND", "L1", "T1", "L3", "CR"],
                  "BellTower": ["FND", "L1", "T1", "L2", "L2", "L2", "L3", "CR"]}
SPECIAL_K = {"Church": 2.0, "BellTower": 3.0, "TownHall": 1.35}
GATED = ("Church", "TownHall")
BAY_SYMBOLS = ("S", "L", "W", "V")
NO_CHIMNEY = ("Barn", "Shed", "Outbuilding", "Church", "BellTower", "TownHall")
BALCONY_P = {"LSA": 0.6, "LSB": 0.5, "PLA": 0.6, "PLB": 0.45, "PLC": 0.0, "BRA": 0.1, "BRB": 0.2}
DOOR_SPAN = ("FND", "L1")                 # family 00's doorway: base + 1st floor (650)
GATE_SPAN = ("FND", "L1", "T1")           # the gate: base + 1st floor + trim (757)
PLINTH = 450.0                            # the stone plinth: 5 cm above the floor down to 4.45 m below it (slopes)
STEP_H = 17.0                             # entrance steps: a step's rise (cm) ...
STEP_T = 32.0                             # ... and tread
STEP_MIN = 20.0                           # a door this far over the ground in front of it gets steps
STEP_MAX = 6                              # at most this many (2 m out: the sidewalk in front stays clear) ...
STEP_H_MAX = 25.0                         # ... and no step higher: past 1.75 m the last step stands on a plinth


def ring_cw(x, y, w, d, yaw):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    hw, hd = 0.5 * w, 0.5 * d
    return [(x + c * a - s * b, y + s * a + c * b) for a, b in ((-hw, hd), (hw, hd), (hw, -hd), (-hw, -hd))]


def edges(ring):
    out = []
    for i in range(len(ring)):
        p, q = ring[i], ring[(i + 1) % len(ring)]
        length = math.hypot(q[0] - p[0], q[1] - p[1])
        u = ((q[0] - p[0]) / length, (q[1] - p[1]) / length)
        out.append({"P": p, "u": u, "n": (-u[1], u[0]), "L": length, "yaw": math.degrees(math.atan2(u[1], u[0]))})
    return out


class _Out:
    def __init__(self):
        self.instances, self.walls = [], {}

    def put(self, e, x, z, mesh, mat, role, scale=(1.0, 1.0, 1.0), y=0.0, yaw_add=0.0):
        p = (e["P"][0] + e["u"][0] * x + e["n"][0] * y, e["P"][1] + e["u"][1] * x + e["n"][1] * y, z)
        self.instances.append({"loc": p, "rot": (0.0, e["yaw"] + yaw_add, 0.0), "scale": tuple(scale), "mesh": mesh,
                               "mat": mat, "role": role})

    def box(self, x, y, z, sx, sy, sz, yaw, mat, role):
        self.instances.append({"loc": (x, y, z), "rot": (0.0, yaw, 0.0), "scale": (sx, sy, sz), "mesh": K.CUBE,
                               "mat": mat, "role": role})


def _spans(res, code):
    w = bdf.widths(code)
    out, x = [], 0.0
    for s in res["symbols"]:
        width = w[s] * (res["scale"] if s in bdf.SCALABLE else 1.0)
        out.append([s, x, x + width])
        x += width
    return out


def assemble(b):
    """{"instances": [{"loc", "rot", "scale", "mesh", "mat", "role"}], "walls": {(edge, level): [(x0, x1, symbol)]},
    "wall_top", "ridge", "stats"} for the building record `b` (see settle.layout)."""
    rng = random.Random(b["seed"])
    code, special, use = b["style"], b.get("special"), b.get("use", "house")
    st, fam = bdf.STYLES[code], bdf.family(code)
    end = fam["end"]
    levels = list(SPECIAL_LEVELS.get(special) or bdf.levels(code, b["floors"]))
    lvdefs = fam["levels"]
    eds = edges(ring_cw(b["x"], b["y"], b["w"], b["d"], b["yaw"]))
    front = b["front"]
    stone = fam is K.F00
    gate = special in GATED
    out = _Out()
    stats = {"door_edge": None, "levels": levels, "grammars": [], "scale_min": 9.0, "scale_max": 0.0, "slack_max": 0.0,
             "awnings": 0, "balconies": 0, "lamps": 0, "chimneys": 0, "dormers": 0, "signs": 0, "steps": 0}

    def note(res):
        stats["grammars"].append(res.get("grammar"))
        stats["scale_min"] = min(stats["scale_min"], res["scale"])
        stats["scale_max"] = max(stats["scale_max"], res["scale"])
        stats["slack_max"] = max(stats["slack_max"], res["slack"])
    master = []
    for i, e in enumerate(eds):
        res = bdf.front(code, use, e["L"] - 2.0 * end, rng) if (stone and i == front) else bdf.bays(code, e["L"], rng)
        note(res)
        master.append(res)
    ground = next(c for c in levels if lvdefs[c]["storey"] or c == "FND")
    front_res = None
    if not stone:
        front_res = bdf.front(code, use, eds[front]["L"] - 2.0 * end, rng)
        note(front_res)
    variant = {}
    for c in levels:
        if c not in variant:
            alt = lvdefs[c].get("alt", {})
            variant[c] = {s: rng.choice([s] + alts) for s, alts in alt.items()}
    tint = b.get("tint", "Base")
    door = {}
    z = b["z"]
    level_base = {}
    for c in levels:
        lv = lvdefs[c]
        level_base.setdefault(c, z)
        ltint = "Base" if lv.get("band") else tint
        for i, e in enumerate(eds):
            length = e["L"]
            if lv.get("band"):
                res = bdf.band(length - 2.0 * end, rng, {s: m["w"] for s, m in lv["mods"].items()})
                seq = [[s, x0, x1] for s, x0, x1 in _spans_w(res, {s: m["w"] for s, m in lv["mods"].items()})]
            elif front_res is not None and c == ground and i == front:
                res = front_res
                seq = _spans(res, code)
            else:
                res = master[i]
                seq = _spans(res, code)
            spans = out.walls[(i, c)] = []          # a repeated level overwrites: its walls are the same
            corner = lv["corner"]
            if corner.get("mesh"):
                out.put(e, 0.0, z, corner["mesh"], K.material(corner, ltint), "corner")
            spans += [(0.0, corner["cx"], "C"), (length - corner["cy"], length, "C")]
            pier = lv["mods"]["P"]

            def strip(x0, x1, role="pier"):
                if x1 - x0 > 0.5:
                    out.put(e, x0, z, pier["mesh"], K.material(pier, ltint), role, ((x1 - x0) / pier["w"], 1.0, 1.0))
                    spans.append((x0, x1, "F"))
            strip(corner["cx"], end)
            strip(length - end, length - corner["cy"])
            half = 0.5 * res["slack"]
            strip(end, end + half)
            strip(length - end - half, length - end)
            x0 = end + half
            gate_here = gate and stone and i == front and c in GATE_SPAN
            k = 0
            while k < len(seq):
                sym, a, bb = seq[k]
                a, bb = a + x0, bb + x0
                width = bb - a
                if sym == "D" and stone and i == front:
                    if gate_here:
                        lo = seq[k - 1][1] + x0 if k > 0 and seq[k - 1][0] == "P" else a
                        hi = seq[k + 1][2] + x0 if k + 1 < len(seq) and seq[k + 1][0] == "P" else bb
                        if spans and spans[-1][2] == "P" and abs(spans[-1][1] - a) < 1e-6:
                            spans.pop()
                            out.instances.pop()
                        if c == GATE_SPAN[0]:
                            out.put(e, lo, z, K.GATE["mesh"], K.material(K.GATE, tint), "door",
                                    ((hi - lo) / K.GATE["w"], 1.0, 1.0))
                            door = {"edge": i, "x0": lo, "x1": hi, "z": z, "h": K.GATE["h"]}
                        spans.append((lo, hi, "DOOR"))
                        k += 2 if k + 1 < len(seq) and seq[k + 1][0] == "P" else 1
                        continue
                    if c in DOOR_SPAN:
                        if c == DOOR_SPAN[0]:
                            out.put(e, a, z, K.DOOR_00["mesh"], K.material(K.DOOR_00, tint), "door",
                                    (width / K.DOOR_00["w"], 1.0, 1.0))
                            door = {"edge": i, "x0": a, "x1": bb, "z": z, "h": K.DOOR_00["h"]}
                        spans.append((a, bb, "DOOR"))
                        k += 1
                        continue
                    sym = "W"
                if sym == "D":
                    d = fam["door"]
                    sd = d.get("s", 1.0)                 # family 02 scales the stone doorway down to its floor
                    out.put(e, a, z, d["mesh"], K.material(d, tint), "door", (width * sd / d["w"], sd, sd))
                    door = {"edge": i, "x0": a, "x1": bb, "z": z, "h": lv["h"]}
                    spans.append((a, bb, "DOOR"))
                    k += 1
                    continue
                shown = variant[c].get(sym, sym)
                m = lv["mods"].get(shown) or lvdefs[ground]["mods"].get(shown)
                role = "door" if sym == "H" else ("pier" if sym == "P" else "bay")
                out.put(e, a, z, m["mesh"], K.material(m, ltint), role, (width / m["w"], 1.0, 1.0))
                if sym == "H":
                    door = {"edge": i, "x0": a, "x1": bb, "z": z, "h": lv["h"]}
                spans.append((a, bb, shown))
                k += 1
        z += lv["h"]
    wall_top = z
    stats["door_edge"] = door.get("edge")
    _props(out, b, eds, door, levels, lvdefs, level_base, master, front_res, ground, rng, stats, code, fam)
    _steps(out, b, eds, door, stats)
    ridge = _roof(out, b, st, special, wall_top, rng, stats)
    _boxes(out, b, wall_top, ridge, rng, stats, special)
    stats["modules"] = len(out.instances)
    return {"instances": out.instances, "walls": {k: [(a, b2, s) for a, b2, s in v] for k, v in out.walls.items()},
            "wall_top": wall_top, "ridge": ridge, "stats": stats}


def _spans_w(res, w):
    out, x = [], 0.0
    for s in res["symbols"]:
        width = w[s] * (res["scale"] if s in bdf.SCALABLE else 1.0)
        out.append((s, x, x + width))
        x += width
    return out


def _props(out, b, eds, door, levels, lvdefs, level_base, master, front_res, ground, rng, stats, code, fam):
    if not door:
        return
    e = eds[door["edge"]]
    special, use = b.get("special"), b.get("use", "house")
    mid = 0.5 * (door["x0"] + door["x1"])
    # wall lamps either side of the door
    if special or rng.random() < 0.8:
        lamp = rng.choice(K.LAMPS)
        zl = door["z"] + min(door["h"] * 0.6, 260.0)
        for x in (door["x0"] - 28.0, door["x1"] + 28.0):
            out.put(e, x, zl, lamp, "", "lamp")
            stats["lamps"] += 1
    # a balcony over the door, on the first storey above the ground floor, centred on the nearest upper bay
    upper = next((c for c in levels[levels.index(ground) + 1:] if lvdefs[c]["storey"] and c not in DOOR_SPAN), None)
    # (the gate of the town hall and the church carries its own balcony)
    p = 0.0 if special else BALCONY_P[code] * (0.6 if use == "shop" else 1.0)
    if upper is not None and rng.random() < p:
        bays = [(a, bb) for s, a, bb in _spans(master[door["edge"]], code) if s in BAY_SYMBOLS + ("D",)]
        x0 = fam["end"] + 0.5 * master[door["edge"]]["slack"]
        if bays:
            a, bb = min(bays, key=lambda q: abs(x0 + 0.5 * (q[0] + q[1]) - mid))
            bw = bb - a
            out.put(e, x0 + 0.5 * (a + bb), level_base[upper], K.BALCONY["mesh"], "", "balcony",
                    (min(1.0, max(0.6, (bw + 40.0) / K.BALCONY["w"])), 1.0, 1.0))
            stats["balconies"] += 1
    if special == "TownHall":
        for x in (door["x0"] - 70.0, door["x1"] + 70.0):
            out.put(e, x, door["z"] + 180.0, rng.choice(K.PLAQUES), "", "plaque")
    # a shop: an awning over every window of the ground floor's street side, a blade sign by the door
    if use == "shop" and front_res is not None:
        awning = rng.choice(K.AWNINGS)
        x0 = fam["end"] + 0.5 * front_res["slack"]
        top = door["z"] + lvdefs[ground]["h"] - 25.0
        for s, a, bb in _spans(front_res, code):
            if s in BAY_SYMBOLS + ("H",):                    # (family 01's shop door has its shop window)
                out.put(e, x0 + 0.5 * (a + bb), top, awning, "", "awning",
                        (min(1.15, max(0.6, (bb - a - 30.0) / K.AWNING_W)), 1.0, 1.0))
                stats["awnings"] += 1
        out.put(e, door["x1"] + 25.0, door["z"] + lvdefs[ground]["h"] + 15.0, rng.choice(K.BANNERS), "", "sign",
                yaw_add=90.0)
        stats["signs"] += 1


def _steps(out, b, eds, door, stats):
    """Entrance steps (Hochparterre): the floor follows the ground within limits (W6), so on a slope a door can stand
    over the ground in front of it -- `door_rise` cm (W6 measures it). It gets a flight of limestone steps from its
    sill down to that ground: n equal rises (the last one onto the ground; at most STEP_MAX steps of STEP_H_MAX, a
    higher door's last step stands on a plinth), each step a slab of its own tread from the plinth's face outwards,
    down into the ground, 20 cm wider than the doorway each side."""
    rise = b.get("door_rise") or 0.0
    if not door or rise < STEP_MIN:
        return
    n = max(1, min(STEP_MAX, int(round(rise / STEP_H)) - 1))
    h = min(STEP_H_MAX, rise / (n + 1))
    e = eds[door["edge"]]
    mid, width = 0.5 * (door["x0"] + door["x1"]), door["x1"] - door["x0"] + 40.0
    bottom = door["z"] - rise - 20.0
    for k in range(1, n + 1):
        top = door["z"] - k * h
        y = 8.0 + (k - 0.5) * STEP_T
        x, yy = e["P"][0] + e["u"][0] * mid + e["n"][0] * y, e["P"][1] + e["u"][1] * mid + e["n"][1] * y
        out.box(x, yy, 0.5 * (top + bottom), width / 100.0, STEP_T / 100.0, (top - bottom) / 100.0, e["yaw"],
                K.LIMESTONE, "step")
    stats["steps"] = n


def _roof(out, b, st, special, wall_top, rng, stats):
    """Roof_Kit_00 as a hipped roof over the footprint grown by the eave: four hip corners (D/2 square each, scaled
    s = D / 1200, Z by the pitch factor k), straight runs between them on the long sides (a dormer run by chance)."""
    r = st["roof"]
    over = r["over"]
    k = SPECIAL_K.get(special) or b.get("k") or rng.uniform(*r["k"])
    big, small, yaw = b["w"] + 2.0 * over, b["d"] + 2.0 * over, b["yaw"]
    if big < small:
        big, small, yaw = small, big, yaw + 90.0
    s = small / (2.0 * K.ROOF["depth"])
    sz = s * k
    mat = K.tinted(K.ROOF["kit"], b.get("roof_tint", "Slate"))
    dormer_p = 0.0 if special in ("Church", "BellTower") or k > 1.45 else r["dormer"]
    half = 0.5 * small
    for e in edges(ring_cw(b["x"], b["y"], big, small, yaw)):
        # the hip corner on the roof rectangle's corner, turned so its eaves lie along this edge and the one before
        out.put(e, 0.0, wall_top, K.ROOF["corner"]["mesh"], mat, "roof_corner", (s, s, sz), yaw_add=90.0)
        run = e["L"] - small
        if run > 1.0:
            n = max(1, int(round(run / (K.ROOF["run"]["w"] * s))))
            for j in range(n):
                dormer = rng.random() < dormer_p
                out.put(e, half + j * run / n, wall_top, K.ROOF["dormer" if dormer else "run"]["mesh"], mat,
                        "dormer" if dormer else "roof_run", (run / n / K.ROOF["run"]["w"], s, sz))
                stats["dormers"] += dormer
    out.ridge_axis = (yaw, big - small)
    return wall_top + K.ROOF["rise"] * sz


def _boxes(out, b, wall_top, ridge, rng, stats, special):
    """A stone plinth, a dark block behind the windows (family 01's have no glass) and brick chimneys through the ridge."""
    x, y, z, yaw = b["x"], b["y"], b["z"], b["yaw"]
    out.box(x, y, z - 0.5 * PLINTH + 5.0, (b["w"] + 16.0) / 100.0, (b["d"] + 16.0) / 100.0, PLINTH / 100.0, yaw,
            K.LIMESTONE, "plinth")
    h = wall_top - z
    if b["w"] > 220.0 and b["d"] > 220.0:
        out.box(x, y, z + 0.5 * h, (b["w"] - 160.0) / 100.0, (b["d"] - 160.0) / 100.0, (h - 20.0) / 100.0, yaw,
                K.INTERIOR, "blocker")
    if special or b.get("kind") in NO_CHIMNEY:
        return
    n = 1 + (rng.random() < 0.45)
    ryaw, run = out.ridge_axis
    ux, uy = math.cos(math.radians(ryaw)), math.sin(math.radians(ryaw))
    top = ridge + rng.uniform(60.0, 110.0)
    for q in range(n):
        t = rng.uniform(0.15, 0.4) * run * (1 if q == 0 else -1)
        cx, cy = x + ux * t, y + uy * t
        hgt = top - wall_top
        out.box(cx, cy, wall_top + 0.5 * hgt, 0.7, 0.7, hgt / 100.0, ryaw, K.BRICK, "chimney")
        out.box(cx, cy, top + 6.0, 0.88, 0.88, 0.12, ryaw, K.LIMESTONE, "chimney_cap")
        stats["chimneys"] += 1
