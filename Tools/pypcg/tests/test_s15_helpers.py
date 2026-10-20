"""Stage 15's shared geometry: `geo.frames`' Transform_Align / Transform_Offset helpers and the spline
round trip, pinned to the taps of the official stage-15 graph
(`Tools/pypcg/data/s15_fixture.json`, captured 2026-10-20 from `/Game/PyPCG/Probe/PCG_Tap15`)."""
import json
import math
import os

import pytest

from pypcg.geo import Polygon
from pypcg.geo import frames as F

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FIXTURE = os.path.join(REPO, "Tools", "pypcg", "data", "s15_fixture.json")


def fixture():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def _maxdiff(a, b):
    return max(math.dist(a[i][:2], b[i][:2]) for i in range(len(a)))


def test_fixture_is_the_official_taps():
    fx = fixture()
    assert len(fx["rings"]["aligned"]) == 6
    assert [len(b) for b in fx["rings"]["outer_bands"]] == [4, 6, 4]
    assert [len(h) for h in fx["rings"]["center_halves"]] == [5, 5]
    assert fx["trees"]["n"] == 44
    assert len(fx["rotate"]["base_in"]) == len(fx["rotate"]["base_out"]) == 5


def test_world_box_and_centre():
    pts = [(1.0, 2.0, 3.0), (-3.0, 4.0, -1.0), (2.0, -2.0, 0.0)]
    assert F.world_box(pts) == ([-3.0, -2.0, -1.0], [2.0, 4.0, 3.0])
    assert F.box_centre(pts) == (-0.5, 1.0, 1.0)
    assert F.world_box([]) is None and F.box_centre([]) is None


def test_rotate_in_frame_matches_the_official_turns():
    """`Transform_Offset` (PerPoints false) turns a piece about the data frame's origin, which every piece
    of stage 15's chain carries: -60 deg on the base, +-120 deg on the arms, all to 1e-12 cm."""
    fx, origin = fixture(), fixture()["frame_origin"]
    for key, yaw, src, dst in (("base", fx["rotate"]["base_yaw"], "base_in", "base_out"),
                               ("arm", fx["rotate"]["arm_yaw"], "arm_in", "arm_out"),
                               ("minus", fx["rotate"]["minus_yaw"], "minus_in", "minus_out")):
        got = F.rotate_in_frame([tuple(p) for p in fx["rotate"][src]], yaw, origin)
        assert _maxdiff(got, fx["rotate"][dst]) <= 1e-9, key


def test_rotate_in_frame_zero_is_the_identity():
    pts = [(10.0, 20.0, 3.0), (-4.0, 5.0, 1.0), (0.0, 0.0, 0.0)]
    assert F.rotate_in_frame(pts, 0.0, (123.0, -45.0)) == pts


def test_align_moves_a_whole_set_to_the_target_centre():
    """`Transform_Align` Center -> Center aligns the SET's box centre to the second input's: the official
    +120 arm after its align is the pre-align set shifted by the negated set centre, to 1e-12 cm."""
    fx = fixture()
    got = F.align([tuple(p) for p in fx["align"]["in"]], (0.0, 0.0, 0.0))
    assert _maxdiff(got, fx["align"]["out"]) <= 1e-9
    assert F.box_centre(got)[:2] == pytest.approx((0.0, 0.0), abs=1e-9)


def test_align_keeps_z_and_an_aligned_input():
    fx = fixture()
    ring = [tuple(p) for p in fx["rings"]["aligned"]]
    assert F.align(ring, (0.0, 0.0, 0.0)) == ring
    got = F.align([tuple(p) for p in fx["align"]["in"]], (0.0, 0.0, 0.0))
    assert [p[2] for p in got] == [p[2] for p in fx["align"]["in"]]


def test_polygon_of_and_spline_of_round_trip():
    ring = [(0.0, 0.0, 5.0), (1000.0, 0.0, 5.0), (1000.0, 800.0, 5.0), (0.0, 800.0, 5.0)]
    poly, sp = F.polygon_of(ring)
    assert _maxdiff([tuple(p) for p in sp.vertices], ring) <= 1e-9
    assert poly.z == pytest.approx(5.0)
    assert _maxdiff(F.spline_of(poly), ring) <= 1e-9


def test_spline_of_prefers_the_engine_vertices():
    poly = Polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], [], 2.0,
                   vertices=[(0.0, 0.0, 2.0), (10.0, 0.0, 2.0), (9.0, 10.0, 2.0)])
    assert F.spline_of(poly) == [(0.0, 0.0, 2.0), (10.0, 0.0, 2.0), (9.0, 10.0, 2.0)]
    assert F.spline_of(Polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], [], 7.0)) == [
        (0.0, 0.0, 7.0), (10.0, 0.0, 7.0), (10.0, 10.0, 7.0)]


# ---- Subgraph_2 / Subgraph_9: Create_Spline_Shape's CopyPoints_0 (blocker 1) -----------------------
def hexagon(radius=1250.0):
    """Stage 4's 6-gon about its own origin: the ENGINE_DEG vertex order (s04_main_tower_footprint)."""
    out = []
    for k in range(6):
        a = math.radians(120.0 - 60.0 * k)
        out.append((-(radius * math.cos(a)), -(radius * math.sin(a))))
    return out


SQUARE = [(-350.0, -350.0), (-350.0, 350.0), (350.0, 350.0), (350.0, -350.0)]


def centroid(ring):
    return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))


def test_copy_shape_reproduces_the_six_squares():
    """`Subgraph_9` (700, Ngon 4) on the six outline centres: turn `yaw - 90` about the copy's centroid,
    0 cm on all 24 tapped vertices."""
    fx = fixture()
    assert len(fx["copy"]["sq"]) == 6
    for i, (yaw, tapped) in enumerate(zip(fx["copy"]["centre_yaws"], fx["copy"]["sq"])):
        got = F.copy_shape(SQUARE, yaw - 90.0, centroid(tapped))
        assert _maxdiff([(p[0], p[1], 0.0) for p in got], [(p[0], p[1], 0.0) for p in tapped]) <= 1e-9, i


def test_copy_shape_reproduces_the_six_hexagons():
    """`Subgraph_2` (Width 2500, Ngon 6) on the six outline centres: stage 4's hexagon turned by
    `60 - yaw` about the copy's centroid, every one of the 36 tapped vertices to 1.6e-12 cm."""
    fx = fixture()
    assert len(fx["copy"]["hex"]) == 6
    src = hexagon(fx["copy"]["hex_radius"])
    for i, (yaw, tapped) in enumerate(zip(fx["copy"]["centre_yaws"], fx["copy"]["hex"])):
        got = F.copy_shape(src, 60.0 - yaw, centroid(tapped))
        assert _maxdiff([(p[0], p[1], 0.0) for p in got], [(p[0], p[1], 0.0) for p in tapped]) <= 1e-9, i


def test_the_hexagon_copies_sit_on_the_inner_ring():
    """The copies' centres are not the PrimaryInput points: the hexagons sit on the inner ring's
    vertices (its circumradius, 4247.2233), to 1e-9 cm."""
    fx = fixture()
    inner = fx["copy"]["inner_ring"]
    for i, tapped in enumerate(fx["copy"]["hex"]):
        c = centroid(tapped)
        assert min(math.dist(c, p) for p in inner) <= 1e-9, i


def test_the_two_shapes_turn_by_different_shape_constants():
    """The turns are `yaw - 90` (4-gon) and `60 - yaw` (6-gon). The 6-gon's is only fixed up to an index
    shift -- a regular hexagon repeats every 60 degrees and every yaw here is a multiple of 60 -- so what
    this pins is the SQUARE's turn, which no shift can absorb (the square repeats every 90)."""
    fx = fixture()
    for i, (yaw, tapped) in enumerate(zip(fx["copy"]["centre_yaws"], fx["copy"]["sq"])):
        got = F.copy_shape(SQUARE, yaw - 90.0, centroid(tapped))
        assert _maxdiff([(p[0], p[1], 0.0) for p in got], [(p[0], p[1], 0.0) for p in tapped]) <= 1e-9, i


# ---- PlaceTreesOnSpline (blocker 3) -----------------------------------------------------------------
def test_sample_on_spline_reproduces_the_tree_ring():
    """`Place_OnSpline` (`Spacing` 1000, `FitToCurve`): 44 samples, the first on the ring's LAST vertex,
    walking backwards, every position within 0.005 cm and every yaw the edge's direction + 90."""
    fx = fixture()
    trees = fx["trees"]
    got = F.sample_on_spline([(p[0], p[1]) for p in trees["ring"]], trees["spacing"])
    assert len(got) == trees["n"] == 44
    assert max(math.dist(p[:2], q[:2]) for p, q in zip(got, trees["points"])) <= 0.005
    assert [p[2] for p in got] == pytest.approx([r[1] for r in trees["rot"]], abs=1e-9)


def test_sample_on_spline_spacing_is_the_length_over_the_count():
    """`N = int(L / d)` and `L / N` apart -- 44 535.898 / 44 = 1012.1795 cm."""
    fx = fixture()
    ring = [(p[0], p[1]) for p in fx["trees"]["ring"]]
    length = sum(math.dist(ring[i], ring[(i + 1) % 6]) for i in range(6))
    got = F.sample_on_spline(ring, 1000.0)
    assert len(got) == int(length / 1000.0)
    assert math.dist(got[0][:2], got[1][:2]) == pytest.approx(length / 44.0, abs=1e-6)


def test_sample_on_spline_of_a_short_spline_is_empty():
    """`N = int(L / d)` on an OPEN path shorter than one spacing is 0: no sample at all. A CLOSED one
    walks back along its second edge, so its length is the whole loop and not one side."""
    assert F.sample_on_spline([(0.0, 0.0), (500.0, 0.0)], 1000.0, closed=False) == []
    assert F.sample_on_spline([(0.0, 0.0)], 1000.0) == []
    assert len(F.sample_on_spline([(0.0, 0.0), (500.0, 0.0)], 1000.0)) == 1

