"""Stage 1, second Python node -- the city-flattening decision (Terrain, 地形底座).

`s01_terrain` builds the two areas; the native `SpatialNoise_Hills`, `FlattenProject_AroundCircle` and
`Subgraph_5` stay between the two Python nodes (s01.md 0: measured in Python, the blur takes 445 s and each GPU
projection 36 s). This node does what the official graph does after them, then hands the points to the kept
`WriteMeshTerrain_0`:

  AttributeMathsOp_1   Ratio = OneMinus(CityFlatness), in double (0.3999999761581421 on the demo)
  AttributeMathsOp_0   Lerp($Position of FlattenProject_AroundCircle [InA], $Position of Subgraph_5 [InB], Ratio):
                       each component A + (B - A) * Ratio (`FMath::Lerp`); every other field and attribute --
                       `SourcePositions`, which the writer uses to find each vertex -- from A

Measured on the official taps: 783 936 of 783 936 position components bit for bit (s01.md 0). Note the ratio
is ONE MINUS CityFlatness: CityFlatness 1 keeps the hills and 0 flattens the city, the other way round from the
parameter's tooltip (s01.md 5).
"""
from pypcg.geo import Points
from pypcg.stage_api import Param

STAGE = 1
RECORD = "s01_blend"
DOC = """Terrain, blend: the hills (flattened outside the Terrain_shaping_1 circle) and the same points
flattened to the city plane, blended per position by 1 - CityFlatness, for the terrain write."""
RANDOM = False
PARAMS = {"CityFlatness": Param(0.5, "Controls how flat the terrain is under the city. 0 = fully hilly, 1 = fully "
                                     "flat.", type="Float")}
INPUTS = {"Hills": "points", "City": "points"}
OUTPUTS = ("Terrain",)


def ratio(city_flatness):
    """`AttributeMathsOp_1 OneMinus`."""
    return 1.0 - float(city_flatness)


def lerp(a, b, t):
    """`FMath::Lerp(A, B, Alpha)` = A + Alpha * (B - A)."""
    return a + (b - a) * t


def _copy(p):
    out = Points()
    for c in Points.COLUMNS:
        setattr(out, c, list(getattr(p, c)))
    out.attrs = {k: list(v) for k, v in p.attrs.items()}
    out.types = dict(p.types)
    out.quat = list(p.quat) if getattr(p, "quat", None) else None
    return out


def blend_set(a, b, r):
    """One data item of `AttributeMathsOp_0`: A's points with their positions moved towards B's, index by index
    (one B point applies to all, as the node broadcasts a single value). None when the counts cannot pair."""
    if len(b) not in (1, len(a)):
        return None
    out = _copy(a)
    one = len(b) == 1
    out.loc = [tuple(lerp(pa[k], (b.loc[0] if one else b.loc[i])[k], r) for k in range(3))
               for i, pa in enumerate(a.loc)]
    return out


def blend(hills, city, city_flatness):
    """Pairs the items of the two pins in order (the node's `InA`/`InB` data pairing; a single B item serves
    every A). Returns (point sets, notes)."""
    r = ratio(city_flatness)
    notes = ["ratio %r" % r]
    a_sets = [v for v, _t in hills if isinstance(v, Points)]
    b_sets = [v for v, _t in city if isinstance(v, Points)]
    out = []
    if not a_sets or not b_sets:
        notes.append("nothing to blend (%d hills, %d city items)" % (len(a_sets), len(b_sets)))
        return out, notes
    for i, a in enumerate(a_sets):
        b = b_sets[0] if len(b_sets) == 1 else (b_sets[i] if i < len(b_sets) else None)
        res = blend_set(a, b, r) if b is not None else None
        if res is None:
            notes.append("item %d: %d hills points cannot pair with the city item" % (i, len(a)))
            continue
        out.append(res)
    notes.append("blended %d points in %d sets" % (sum(len(p) for p in out), len(out)))
    return out, notes


def run(inputs, params, ctx):
    sets, notes = blend(inputs.get("Hills", []), inputs.get("City", []), params["CityFlatness"])
    ctx.notes += notes
    return {"Terrain": [(p, ["Terrain"]) for p in sets]}
