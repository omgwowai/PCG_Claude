"""V1 checks of stage 1, Terrain (spec 3, V1).

The first node's record holds the extracted terrain points (261 312, over `geo.MAX_RECORDED_POINTS`: a summary),
so it cannot be replayed whole (trap 60's situation) and V1 runs `check_record`, a PARTIAL REPLAY:

  - the footprint is the one the run noted (`footprint x0 y0 x1 y1 z`, exact reprs);
  - `TerrainShaping` and `City` are recorded in full, so `FlattenArea` is rebuilt with the editor's booleans and
    `CityFlatZone` from the City outline; both must equal the recorded outputs field for field (the determinism
    evidence trap 60 asks for);
  - then the mask invariants (`check_masks`): the area's outer ring is the footprint grown 600 m, its z the
    footprint's top less 1820.424606 cm, its area the grown square's less the part of the Terrain_shaping_1
    outlines inside it (measured with the editor's intersection); the flat zone keeps every City control point's
    x, y and tangents and puts it at z 3000.

The blend node's record holds only summaries (its point sets are the whole terrain); its invariant is
`check_blend` (each output position the Lerp of the two inputs, index by index, every other field from the
hills), checked offline on the official sample and live by comparing the written terrain vertex by vertex
(s01.md 6). `check_terrain` holds the brief's invariants as s01.md 5 corrects them."""
from pypcg import geo
from pypcg.checks.s18 import footprint_of
from pypcg.geo import areas as A
from pypcg.stages import s01_terrain as S
from pypcg.stages import s01_terrain_blend as B

AREA_REL_TOL = 1e-9             # the area against grown square less the outline inside it (the booleans' rounding)
EDGE_TOL_CM = 1e-6              # the outer ring against the grown footprint
CITY_PLANE_TOL_CM = 2.0         # the flattened city surface against the 3000 cm plane (official: 2998.70 .. 3000.70)
OUTER_RING_GAP_CM = 1000.0      # the brief: the outer ring lies more than this below the core


def _items(rec, side, pin):
    return rec.get(side, {}).get(pin, [])


def _values(rec, side, pin):
    out = []
    for v, tags in _items(rec, side, pin):
        try:
            out.append((geo.from_json(v), frozenset(tags)))
        except ValueError:
            out.append((v, frozenset(tags)))         # a summary (truncated points)
    return out


def check_record(rec, ops, official=None):
    fp = footprint_of(rec.get("notes"))
    shaping = _values(rec, "inputs", "TerrainShaping")
    city = _values(rec, "inputs", "City")
    rec_area = [v for v, _t in _values(rec, "outputs", "FlattenArea")]
    rec_zone = [v for v, _t in _values(rec, "outputs", "CityFlatZone")]
    f = []
    if fp is None:
        if not any("no terrain points" in n for n in rec.get("notes", [])):
            return ["the run noted no footprint"]
        if rec_area:
            f.append("no terrain points, but %d FlattenArea polygons" % len(rec_area))
    else:
        area = S.flatten_area(fp, shaping, ops)
        if [geo.to_json(p) for p in area] != [geo.to_json(p) for p in rec_area]:
            f.append("FlattenArea: the replay (%d polygons) differs from the run (%d)" % (len(area), len(rec_area)))
        f += check_masks(fp, shaping, rec_area, ops)
    zone = S.city_flat_zone(city)
    if [geo.to_json(s) for s in zone] != [geo.to_json(s) for s in rec_zone]:
        f.append("CityFlatZone: the replay (%d splines) differs from the run (%d)" % (len(zone), len(rec_zone)))
    f += check_zone(city, rec_zone)
    return f


def check_masks(fp, shaping, area, ops):
    """The flatten area against the footprint and the Terrain_shaping_1 outlines (module docstring)."""
    f = []
    x0, y0, x1, y1, z = fp
    e = S.EXPAND_CM
    if len(area) != 1:
        return ["FlattenArea: %d polygons, expected one (the square less the outlines inside it)" % len(area)]
    p = area[0]
    if p.z != z + S.DOWN_CM:
        f.append("FlattenArea: z %r, expected the footprint's top %r %+r" % (p.z, z, S.DOWN_CM))
    xs, ys = [q[0] for q in p.outer], [q[1] for q in p.outer]
    want = (x0 - e, y0 - e, x1 + e, y1 + e)
    got = (min(xs), min(ys), max(xs), max(ys))
    if max(abs(a - b) for a, b in zip(got, want)) > EDGE_TOL_CM:
        f.append("FlattenArea: outer bounds %r, expected the footprint grown %r cm: %r" % (got, e, want))
    sq = geo.Polygon([(want[0], want[1]), (want[2], want[1]), (want[2], want[3]), (want[0], want[3])])
    holes = A.areas_of(shaping)
    inside = sum(A.area_cm2(q) for q in A.intersection(holes, [sq], ops)) if holes else 0.0
    expect = A.area_cm2(sq) - inside
    got_a = A.area_cm2(p)
    if abs(got_a - expect) > AREA_REL_TOL * A.area_cm2(sq):
        f.append("FlattenArea: %.6f m2, expected the grown square less the outlines inside it %.6f m2"
                 % (got_a / 1e4, expect / 1e4))
    return f


def check_zone(city, zone):
    """Each City outline, in order, at world z 3000 with its own x, y, tangents, flags."""
    src = [v for v, _t in city if isinstance(v, geo.Spline) and v.points]
    if len(src) != len(zone):
        return ["CityFlatZone: %d splines for %d City outlines" % (len(zone), len(src))]
    f = []
    for k, (a, b) in enumerate(zip(src, zone)):
        if [(q[0], q[1]) for q in a.points] != [(q[0], q[1]) for q in b.points]:
            f.append("CityFlatZone %d: control points moved in x, y" % k)
        if any(q[2] != S.CITY_Z_CM + S.CITY_UP_CM for q in b.points):
            f.append("CityFlatZone %d: z %r, expected %r" % (k, sorted({q[2] for q in b.points}),
                                                           S.CITY_Z_CM + S.CITY_UP_CM))
        if (a.closed, a.linear) != (b.closed, b.linear) or (a.tangents or None) != (b.tangents or None):
            f.append("CityFlatZone %d: flags or tangents differ from the City outline" % k)
    return f


def check_blend(hills, city, out, city_flatness):
    """`AttributeMathsOp_0`: one output point per hills point, each position `hills + (city - hills) * (1 -
    CityFlatness)` bit for bit, every other column and attribute the hills point's."""
    r = B.ratio(city_flatness)
    if len(out) != len(hills) or len(city) not in (1, len(hills)):
        return ["blend: %d points out of %d hills and %d city points" % (len(out), len(hills), len(city))]
    f = []
    bad = 0
    for i, (a, o) in enumerate(zip(hills.loc, out.loc)):
        b = city.loc[0 if len(city) == 1 else i]
        if tuple(o) != tuple(B.lerp(a[k], b[k], r) for k in range(3)):
            bad += 1
    if bad:
        f.append("blend: %d of %d positions are not the Lerp" % (bad, len(out)))
    for c in geo.Points.COLUMNS:
        if c != "loc" and list(getattr(out, c)) != list(getattr(hills, c)):
            f.append("blend: column %s is not the hills'" % c)
    if out.attrs != hills.attrs or out.types != hills.types:
        f.append("blend: the attributes are not the hills' (SourcePositions finds each vertex)")
    return f


def check_terrain(extracted_n, final, hills, flat, inside_city, city_flatness, core, outer_ring):
    """The brief's invariants as s01.md 5 corrects them, on the final positions (z only):
    the count equals the extracted count; inside the City every height is the blend of the hills and the flat
    surface bit for bit, the flat surface lies within 2 cm of the city plane and the mean is the blend of the
    means; the outer ring's mean lies more than 1000 cm below the core's. `inside_city`, `core`, `outer_ring` are
    index lists into the three z lists."""
    f = []
    if len(final) != extracted_n:
        f.append("terrain: %d points written, %d extracted" % (len(final), extracted_n))
    r = B.ratio(city_flatness)
    plane = S.CITY_Z_CM + S.CITY_UP_CM
    bad = [i for i in inside_city if final[i] != B.lerp(hills[i], flat[i], r)]
    if bad:
        f.append("terrain: %d of %d city heights are not the blend" % (len(bad), len(inside_city)))
    off = [i for i in inside_city if abs(flat[i] - plane) > CITY_PLANE_TOL_CM]
    if off:
        f.append("terrain: %d city points' flat surface more than %.0f cm off the %.0f cm plane"
                 % (len(off), CITY_PLANE_TOL_CM, plane))
    if inside_city:
        n = float(len(inside_city))
        mean = sum(final[i] for i in inside_city) / n
        want = (1.0 - r) * sum(hills[i] for i in inside_city) / n + r * sum(flat[i] for i in inside_city) / n
        if abs(mean - want) > 1e-6 * max(1.0, abs(want)):
            f.append("terrain: city mean %.6f, the blend of the means %.6f" % (mean, want))
    if core and outer_ring:
        c = sum(final[i] for i in core) / len(core)
        o = sum(final[i] for i in outer_ring) / len(outer_ring)
        if not c - o > OUTER_RING_GAP_CM:
            f.append("terrain: the outer ring's mean %.1f cm is not %.0f cm below the core's %.1f cm"
                     % (o, OUTER_RING_GAP_CM, c))
    return f
