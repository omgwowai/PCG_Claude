"""Stage 15's shared helpers for the Python nodes BETWEEN the native building nodes (`s15_tower_level1` ..
`3`, `s15_tower_top`, `s15_tower_sidewalk`). Not a stage node itself (no STAGE / run): the rooftops a kept
`Assign_CitySampleBuildings` hands back, read as rings, and the contracts that turn one tower's rooftops into
the next tower's footprint. `docs/pypcg/stages/s15.md` steps 8 - 15."""
import math

from pypcg import geo
from pypcg.geo import Points, Polygon, Spline
from pypcg.geo import areas as A
from pypcg.geo import frames as F
from pypcg.geo import splines as SP

ARM_CONTRACT_CM = 150.0            # Subgraph_45/47/49, 52/54/56, 59/61/63 Contract ("1.5m Between ... Buildings")
CHJ_CONTRACT_CM = 400.0            # Subgraph_5 / Subgraph_7 ("Contract 4m (Outer CHJ Ring)")
SKYSCRAPER_CONTRACT_CM = 1000.0    # Subgraph_65 ("Contract 10m (Central Skyscraper Footprint)")
ASSEMBLY_MIN_M2 = 1000.0           # Subgraph_22 Filter_Areas_BySize Size (Greater)
SEGMENT_ANGLE_DEG = 3.0            # Subgraph_17 Extract_Segments CutAngleThreshold
SQUARE = [(-350.0, -350.0), (-350.0, 350.0), (350.0, 350.0), (350.0, -350.0)]   # Subgraph_9 (Ngon 4, 700)
SQUARE_TURN_OFFSET_DEG = -90.0     # the square's copy turn: yaw - 90 (24 tapped vertices, 0 cm)
COURTYARD_EXPAND_CM = 350.0        # Subgraph_11 Expand (UnionBeforeOutputting: the default, false)
COURTYARD_LIFT_CM = 40.0           # Subgraph_15 offset Z


def rings_of(items):
    """Each closed spline or polygon of a pin as a ring of (x, y, z), in the pin's order; anything else
    (the building node's point sets, an open spline) is skipped."""
    out = []
    for v, _tags in items:
        if isinstance(v, Spline) and v.closed and len(v.points) >= 3:
            out.append([tuple(float(c) for c in p) for p in v.points])
        elif isinstance(v, Polygon) and len(v.outer) >= 3:
            zs = v.zs if v.zs is not None else [v.z] * len(v.outer)
            out.append([(p[0], p[1], z) for p, z in zip(v.outer, zs)])
    return out


def poly_of(ring):
    return Polygon([(p[0], p[1]) for p in ring], [], ring[0][2])


def contract(rings, distance, ops):
    """`Transform_Areas_Contract` (`UnionBeforeOutputting` true, the default) on every ring, each in its
    own frame (trap 64: the start vertex), at that ring's z: the rings it leaves. The primitive publishes
    POLYGONS (the tapped `t02_outer30` is `PCGPolygon2DData`), so `tagged_rings` hands these on as
    polygons."""
    out = []
    for r in rings:
        poly = poly_of(r)
        for p in A.in_frame(poly, lambda q: A.contract([q], distance, ops)):
            if len(p.outer) >= 3:
                out.append([(q[0], q[1], poly.z) for q in p.outer])
    return out


def spline(ring):
    return Spline([tuple(p) for p in ring], closed=True, linear=True)


def tagged_rings(rings, tag, as_polygon=True):
    """Each ring as a polygon at its z (`Transform_Areas_Contract`'s output) or, with `as_polygon` false, a
    closed spline (a rooftop forwarded through a filter)."""
    if as_polygon:
        return [(Polygon([(p[0], p[1]) for p in r], [], r[0][2]), [tag]) for r in rings]
    return [(spline(r), [tag]) for r in rings]


def area_m2(ring):
    return abs(geo.signed_area([(p[0], p[1]) for p in ring])) / 1e4


# ---- the courtyard (s15_tower_level1) ----------------------------------------------------------------
def outline_points(ring):
    """Subgraph_17 `Extract_Segments` (3 deg) on the closed rooftop ring, then Subgraph_18
    `Place_Point_AtCenter` on each run: `[(x, y, z, yaw)]`, the run's midpoint and direction."""
    closed = [tuple(p) for p in ring] + [tuple(ring[0])]
    out = []
    for run in geo.extract_segments(closed, SEGMENT_ANGLE_DEG):
        if len(run) < 2:
            continue
        loc, yaw = SP.center([run[0], run[-1]])
        out.append((loc[0], loc[1], loc[2], yaw))
    return out


def squares(points):
    """Subgraph_9 `Create_Spline_Shape` (Ngon 4, 700) copied onto each outline point: the square turned
    `yaw - 90` about the point (`geo.frames.copy_shape`, measured 0 cm on all 24 tapped vertices)."""
    return [[(q[0], q[1], z) for q in F.copy_shape(SQUARE, yaw + SQUARE_TURN_OFFSET_DEG, (x, y))]
            for x, y, z, yaw in points]


def notched(roofs, ops):
    """Subgraph_17 -> 18 -> 9 -> Subgraph_19 `Compose_Areas_Exclusion`: every rooftop less the union of the
    squares on its own outline centres, at the rooftop's z."""
    out = []
    for r in roofs:
        sq = squares(outline_points(r))
        for p in A.exclusion([poly_of(r)], [poly_of(s) for s in sq], ops):
            if len(p.outer) >= 3:
                out.append([(q[0], q[1], r[0][2]) for q in p.outer])
    return out


COURTYARD_Z = 0.0                  # AttributeMathsOp_1 Set $Position.Z: its second input is unwired -> 0


def _union_order(polys):
    """The item order `Compose_Areas_Union` hands back: descending centroid x, then ascending y (the taps
    u33 / u27 / u28: (4247, 0), (2124, -3678), (2124, 3678), (-2124, -3678), (-2124, 3678), (-4247, 0)).
    Centroids are rounded to 1e-3 cm so a last-bit difference cannot reorder a tie."""
    def key(p):
        n = len(p.outer)
        return (-round(sum(q[0] for q in p.outer) / n, 3), round(sum(q[1] for q in p.outer) / n, 3))
    return sorted(polys, key=key)


def courtyard(hexes, ops):
    """AttributeMathsOp_1 -> Subgraph_10 `Compose_Areas_Union` -> Subgraph_11 `Transform_Areas_Expand` (350):
    the courtyard polygons, and Subgraph_15's +40 copy. `AttributeMathsOp_1` ("Snap Courtyard Z To Building
    Height") SETS `$Position.Z` from an unwired second input, i.e. to 0: the tapped union, courtyard and lift
    are at z 0, 0 and 40 (u33, u27, u28; the courtyard mesh's spline u29 at 40), not at the CHC roof that
    s15.md 2.13 states. On the demo the union is a no-op: six disjoint 405.95 m2 hexagons."""
    if not hexes:
        return [], []
    z = COURTYARD_Z
    polys = [Polygon([(p[0], p[1]) for p in h], [], z) for h in hexes]
    united = ops.union(A.rings(polys)) if len(polys) > 1 else polys
    united = _union_order([Polygon(p.outer, p.holes, z) for p in united])
    grown = [Polygon(p.outer, p.holes, z) for p in A.expand(united, COURTYARD_EXPAND_CM, ops)]
    lifted = [Polygon(list(p.outer), [list(h) for h in p.holes], p.z + COURTYARD_LIFT_CM) for p in grown]
    return grown, lifted


# ---- the antenna (s15_tower_top) ---------------------------------------------------------------------
def centre_point(ring):
    """Subgraph_23 `Place_Point_AtCenter` on one rooftop: the box centre of its control points at the
    rooftop's z, turned along the ring's FIRST edge (control point 0 -> 1) -- the rule `Subgraph_18` follows
    on its two-point runs. Measured: the official antenna point is (0, 0, 43 756.2605) at yaw 60 (s15.md
    2.15), and the slim run's skyscraper rooftop has its first edge at 60.000 deg; the polygon's own frame
    would give -90."""
    c = F.box_centre(ring)
    a, b = ring[0], ring[1 % len(ring)]
    yaw = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    return (c[0], c[1], ring[0][2]), yaw


def antenna(roofs):
    pts = Points()
    for r in roofs:
        loc, yaw = centre_point(r)
        pts.add(loc, rot=(0.0, yaw, 0.0), steepness=1.0)
    return pts
