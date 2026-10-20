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
