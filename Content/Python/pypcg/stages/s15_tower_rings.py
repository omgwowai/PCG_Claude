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
    own frame (trap 64: the start vertex), at that ring's z: the rings it leaves."""
    out = []
    for r in rings:
        poly = poly_of(r)
        for p in A.in_frame(poly, lambda q: A.contract([q], distance, ops)):
            if len(p.outer) >= 3:
                out.append([(q[0], q[1], poly.z) for q in p.outer])
    return out


def spline(ring):
    return Spline([tuple(p) for p in ring], closed=True, linear=True)


def tagged_rings(rings, tag):
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


def courtyard(hexes, roof_z, ops):
    """AttributeMathsOp_1 (the hexagons' z set to the CHC roof: measured 6556.2605 on the union, s15.md
    2.13) -> Subgraph_10 `Compose_Areas_Union` -> Subgraph_11 `Transform_Areas_Expand` (350): the courtyard
    polygons, and Subgraph_15's +40 copy."""
    if not hexes:
        return [], []
    polys = [Polygon([(p[0], p[1]) for p in h], [], roof_z) for h in hexes]
    united = ops.union(A.rings(polys)) if len(polys) > 1 else polys
    united = [Polygon(p.outer, p.holes, roof_z) for p in united]
    grown = [Polygon(p.outer, p.holes, roof_z) for p in A.expand(united, COURTYARD_EXPAND_CM, ops)]
    lifted = [Polygon(list(p.outer), [list(h) for h in p.holes], p.z + COURTYARD_LIFT_CM) for p in grown]
    return grown, lifted


# ---- the antenna (s15_tower_top) ---------------------------------------------------------------------
def centre_point(ring):
    """Subgraph_23 `Place_Point_AtCenter` on one rooftop: the box centre of its control points in the
    polygon's own frame, turned with that frame (`geo.frames.polygon_of`), at the rooftop's z."""
    poly, sp = F.polygon_of(ring)
    t, q = sp.frame
    from pypcg.geo.plane import quat_rotate
    inv = (-q[0], -q[1], -q[2], q[3])
    local = [quat_rotate(inv, (p[0] - t[0], p[1] - t[1], p[2] - t[2])) for p in sp.points]
    c = [(min(v[a] for v in local) + max(v[a] for v in local)) / 2.0 for a in range(3)]
    w = quat_rotate(q, (c[0], c[1], 0.0))
    yaw = math.degrees(2.0 * math.atan2(q[2], q[3]))
    yaw = (yaw + 180.0) % 360.0 - 180.0
    return (t[0] + w[0], t[1] + w[1], ring[0][2]), yaw


def antenna(roofs):
    pts = Points()
    for r in roofs:
        loc, yaw = centre_point(r)
        pts.add(loc, rot=(0.0, yaw, 0.0), steepness=1.0)
    return pts
