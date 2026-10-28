"""The building style database (City Sample's BDF, 建筑样式库): seven style codes over the three kit families. Each
style has a vertical grammar of levels (`*` = repeated storeys), a storey range, a minimum wall, roof rules, a colour
palette and City Sample-style tooltip metadata (look / type / era). Each family has its horizontal grammars chosen by
the length of the wall between the corner zones (BDF's F0 / F1 / F2 with FLengths), fallbacks, and the ground-floor
front grammars with the door (`D`) or the shop door (`H`). Pure."""
from . import grammar as G, kit as K

STYLES = {
    "LSA": {"family": "F00", "vertical": "[FND][L1][T1][L2]*[L3][CR]", "floors": (3, 5), "min_wall": 650.0,
            "roof": {"k": (1.25, 1.5), "dormer": 0.5, "over": 20.0, "tints": ("Slate", "BlueSlate")},
            "tooltip": {"look": "limestone, rusticated base, arched windows, pediments, dentil cornice",
                        "type": "civic / bourgeois townhouse", "era": "1850-1900"}},
    "LSB": {"family": "F00", "vertical": "[FND][L1][T1][L2]*[CR]", "floors": (2, 4), "min_wall": 650.0,
            "roof": {"k": (1.2, 1.4), "dormer": 0.35, "over": 20.0, "tints": ("Slate", "BlueSlate", "Brown")},
            "tooltip": {"look": "limestone, plain upper floors under a dentil cornice", "type": "townhouse",
                        "era": "1860-1910"}},
    "PLA": {"family": "F02", "vertical": "[G][TR][N][U]*[RT]", "floors": (2, 5), "min_wall": 500.0,
            "roof": {"k": (1.2, 1.4), "dormer": 0.35, "over": 45.0, "tints": ("Slate", "Terracotta", "BlueSlate")},
            "tooltip": {"look": "plaster, shutters, garlanded piano nobile, cornices", "type": "townhouse / shop",
                        "era": "1840-1890"}},
    "PLB": {"family": "F02", "vertical": "[G][TR][U]*[A][RT]", "floors": (3, 5), "min_wall": 500.0,
            "roof": {"k": (1.25, 1.45), "dormer": 0.2, "over": 45.0, "tints": ("Terracotta", "Brown", "Slate")},
            "tooltip": {"look": "plaster, shutters, low attic storey", "type": "townhouse / apartments",
                        "era": "1850-1900"}},
    "PLC": {"family": "F02", "vertical": "[GC][U3]*[RT]", "floors": (2, 3), "min_wall": 500.0,
            "roof": {"k": (1.4, 1.7), "dormer": 0.0, "over": 45.0, "tints": ("Terracotta", "Brown", "Slate")},
            "tooltip": {"look": "plaster over a rusticated ground floor, small windows", "type": "house",
                        "era": "1800-1870"}},
    "BRA": {"family": "F01", "vertical": "[G][U]*", "floors": (1, 3), "min_wall": 500.0,
            "roof": {"k": (1.7, 2.1), "dormer": 0.0, "over": 40.0, "tints": ("Terracotta", "Brown")},
            "tooltip": {"look": "red brick, cream window surrounds, steep tiled roof", "type": "house / farm / barn",
                        "era": "1880-1930"}},
    "BRB": {"family": "F01", "vertical": "[G][TR][U2]*[T][RT]", "floors": (2, 3), "min_wall": 500.0,
            "roof": {"k": (1.5, 1.8), "dormer": 0.0, "over": 45.0, "tints": ("Terracotta", "Slate")},
            "tooltip": {"look": "red brick, cream string course and cornice, arched top floor",
                        "type": "house / workshop", "era": "1890-1930"}},
}

INF = float("inf")
# family -> [(span below which, grammar)] (F0 / F1 / F2), then fallbacks tried in order
GRAMMARS = {
    "F02": ([(1200.0, "[S][P,S]*"), (2400.0, "[S][P,L]*[P,S]"), (INF, "[S,P][L,P]*[S][P,L]*[P,S]")],
            ["[L][P,L]*", "[S][P,L]*", "[L][P,S]*", "[S][P,S]*"]),
    "F01": ([(INF, "[W][P,W]*")], []),
    "F00": ([(INF, "[W][P,W]*")], []),
    "band": ([(INF, "[S][P,S]*")], ["[L][P,L]*", "[S][P,L]*"]),
}
# family -> use -> front grammars (the ground floor of the street side), tried in order
FRONTS = {
    "F02": {"house": ["[S,P]*[D][P,S]*", "[L,P]*[D][P,L]*", "[S,P]*[D][P,L]*", "[D][P,S]*"],
            "shop": ["[S,P]*[D][P,S]*", "[L,P]*[D][P,L]*", "[S,P]*[D][P,L]*", "[D][P,S]*"]},
    "F01": {"house": ["[W,P]*[D][P,W]*", "[V,P]*[D][P,V]*", "[W,P]*[D][P,V]*", "[D][P,W]*"],
            "shop": ["[V,P]*[H][P,V]*", "[W,P]*[H][P,W]*", "[V,P]*[H][P,W]*", "[H][P,W]*"]},
    "F00": {"house": ["[W,P]*[D][P,W]*"], "shop": ["[W,P]*[D][P,W]*"]},   # the doorway takes a bay of base + 1st floor
}
BAY_SCALE = (0.85, 1.2)
FRONT_SCALE = (0.8, 1.25)


def family(code):
    return K.FAMILIES[STYLES[code]["family"]]


def levels(code, floors):
    """The style's levels, bottom to top, for `floors` storeys (clamped to its range)."""
    st = STYLES[code]
    lo, hi = st["floors"]
    floors = max(lo, min(hi, int(floors)))
    lv = family(code)["levels"]
    parts = G.parse(st["vertical"])
    fixed = sum(lv[s]["storey"] for p in parts if isinstance(p.rep, int) for s in p.symbols for _ in range(p.rep))
    per = sum(lv[s]["storey"] for p in parts if not isinstance(p.rep, int) for s in p.symbols) or 1
    return G.expand(parts, max(0, (floors - fixed) // per))


def widths(code, level=None):
    """Symbol -> slot width for the style's family (the bay grid, plus the ground floor's doors and wide windows)."""
    fam = family(code)
    w = dict(fam["bays"])
    if fam.get("door"):
        w["D"] = fam["door"]["w"]
    g = fam["levels"].get("G")
    if g is not None and fam is K.F01:
        w.update({"V": g["mods"]["V"]["w"], "H": g["mods"]["H"]["w"]})
    if level is not None:
        w.update({s: m["w"] for s, m in fam["levels"][level]["mods"].items()})
    return w


SCALABLE = {"S", "L", "W", "V", "D", "H"}
SLACK_OK = 40.0                       # the FLengths grammar is kept while it leaves at most this much plain wall


def _fit(grammars, length, w, rng, scale):
    """The first grammar that fits with at most SLACK_OK of plain wall, else the one leaving the least."""
    best = None
    for text in grammars:
        res = G.solve(G.parse(text), length, w, SCALABLE, rng=rng, smin=scale[0], smax=scale[1], slack=True)
        res["grammar"] = text
        if res["ok"] and res["slack"] <= SLACK_OK:
            return res
        if res["ok"] and (best is None or res["slack"] < best["slack"]):
            best = res
    return best or {"symbols": [], "scale": 1.0, "ok": False, "counts": [], "slack": 0.0, "grammar": None}


def _bays(fam_key, span, w, rng):
    staged, fallback = GRAMMARS[fam_key]
    first = next(text for limit, text in staged if span < limit)
    return _fit([first] + fallback + [t for _l, t in staged if t != first], span, w, rng, BAY_SCALE)


def bays(code, length, rng):
    """The bay sequence of a wall `length` long (corner zones excluded): F0 / F1 / F2 by the span, then fallbacks."""
    fam = family(code)
    return _bays(STYLES[code]["family"], length - 2.0 * fam["end"], widths(code), rng)


def band(span, rng, w):
    """A continuous band (string course, cornice) solved on its own: its joints need not meet the bays."""
    return _bays("band", span, w, rng)


def front(code, use, span, rng):
    """The street side over `span` with one door (`D`) or shop door (`H`) in the middle: the ground floor's sequence
    (families 01 / 02), or every level's (family 00, whose doorway spans the base and the 1st floor)."""
    return _fit(FRONTS[STYLES[code]["family"]][use], span, widths(code), rng, FRONT_SCALE)


def span(res, code):
    w = widths(code)
    return sum(w[s] * (res["scale"] if s in SCALABLE else 1.0) for s in res["symbols"])
