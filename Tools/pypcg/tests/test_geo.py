import math
import random

import pytest

from fakes import FakeOps
from pypcg import geo
from pypcg.geo import ParamSet, Points, Polygon, Spline

RECT = [(0.0, 0.0), (10000.0, 0.0), (10000.0, 5000.0), (0.0, 5000.0)]      # 100 x 50 m, CCW


def test_signed_area_and_ccw():
    assert geo.signed_area(RECT) == pytest.approx(5.0e7)
    assert geo.signed_area(geo.ccw(list(reversed(RECT)))) == pytest.approx(5.0e7)


def test_inside_and_contains_with_hole():
    poly = Polygon(RECT, holes=[[(4000, 2000), (4000, 3000), (6000, 3000), (6000, 2000)]])
    assert geo.inside((100, 100), RECT) and not geo.inside((-1, 100), RECT)
    assert geo.contains(poly, (100, 100)) and not geo.contains(poly, (5000, 2500))
    assert geo.area_m2(poly) == pytest.approx(5000 - 200)


def test_clip_path_keeps_the_inside_part():
    parts = geo.clip_path([(-1000, 2500), (20000, 2500)], RECT)
    assert len(parts) == 1
    (x0, y0), (x1, y1) = parts[0][0], parts[0][-1]
    assert (x0, x1) == (pytest.approx(0.0), pytest.approx(10000.0)) and y0 == y1 == 2500


def test_clean_points_follows_the_auto_tangents():
    # CleanSpline judges collinearity on CurveAuto tangents (next - previous), so a vertex whose
    # neighbour's tangent points at a corner survives, and only runs well inside a straight edge go.
    assert geo.clean_points([(0, 0), (500, 0), (1000, 0), (1000, 1000)]) == [(0, 0), (500, 0), (1000, 0), (1000, 1000)]
    assert geo.clean_points([(0, 0), (250, 0), (500, 0), (750, 0), (1000, 0), (1000, 1000)]) == \
        [(0, 0), (750, 0), (1000, 0), (1000, 1000)]


def test_frame_box_of_an_axis_aligned_rectangle():
    o, X, Y, u0, u1, w0, w1 = geo.frame_box(RECT)
    assert o == (0.0, 0.0) and X == (1.0, 0.0) and Y == (-0.0, 1.0)
    assert (u0, u1, w0, w1) == (-1.0, 10001.0, -1.0, 5001.0)        # the engine's +-1 cm point bounds


def test_grid_lines_on_a_rectangle():
    # Lines sit at u0 + k*W (k >= 1) like Subdivide_Areas_withGrid: x = 999, 1999, ..., 9999 and
    # y = 999, ..., 4999; the lines past the far edge clip to nothing.
    lines = geo.grid_lines(RECT, 1000.0, 1000.0)
    xs = sorted(round(seg[0][0]) for axis, seg in lines if axis == "X")
    ys = sorted(round(seg[0][1]) for axis, seg in lines if axis == "Y")
    assert xs == [999 + 1000 * k for k in range(10)]
    assert ys == [999 + 1000 * k for k in range(5)]
    assert all(geo.path_length(seg) == pytest.approx(5000 if axis == "X" else 10000) for axis, seg in lines)


def test_grid_lines_refuses_non_positive_and_absurd_spacings():
    # Final review M4: a user-set grid spacing of 0 or below, or a subdivision count of 0, is a StageError
    # (not a ZeroDivisionError), and so is a spacing that would lay more than MAX_GRID_LINES lines.
    from pypcg.geo import subdivide
    from pypcg.stage_api import StageError
    for width, length in ((0.0, 1000.0), (1000.0, -5.0)):
        with pytest.raises(StageError, match="must be positive"):
            geo.grid_lines(RECT, width, length)
    with pytest.raises(StageError, match="subdivisions"):
        geo.grid_lines(RECT, 0.0, 0.0, subdiv=(0, 2))
    with pytest.raises(StageError, match="limit %d" % subdivide.MAX_GRID_LINES):
        geo.grid_lines(RECT, 0.5, 1000.0)                    # 100 m at 5 mm: ~20 000 lines
    assert geo.grid_lines(RECT, 2.0, 1000.0)                 # 5 000 lines: allowed


def test_recursive_split_halves_a_rectangle():
    areas, paths = [], []
    geo.recursive_split(RECT, FakeOps(), 1, 1000 * 1e4, lambda ring: 0.5, areas, paths)
    assert sorted(round(abs(geo.signed_area(a)) / 1e4) for a in areas) == [2500, 2500]
    assert len(paths) == 1 and paths[0][0][0] == pytest.approx(5000.0)


def test_recursive_split_keeps_small_areas_whole():
    areas, paths = [], []
    geo.recursive_split(RECT, FakeOps(), 1, 6000 * 1e4, lambda ring: 0.5, areas, paths)
    assert areas == [RECT] and paths == []


class SliverOps:
    def cut_with_paths(self, ring, paths):
        return [ring, [(0, 0), (1, 0), (0, 1)]]


def test_auto_split_drops_slivers():
    pieces, _ = geo.auto_split(RECT, 0.5, SliverOps())
    assert pieces == [RECT]
    areas, paths = [], []
    geo.recursive_split(RECT, SliverOps(), 1, 0, lambda ring: 0.5, areas, paths)
    assert areas == [RECT] and paths == []                 # a cut that does not divide keeps the ring whole


def test_ngon_matches_the_official_tower_hexagon():
    # PCG_2_1_MainTower_Footprint in the demo level (pyg_probe_plan_api3.py, 2026-10-15)
    pts = geo.ngon((0.0, 0.0), 8000.0, 6, start_deg=-60.0, step_deg=-60.0)
    official = [(4000, -6928.2), (-4000, -6928.2), (-8000, 0), (-4000, 6928.2), (4000, 6928.2), (8000, 0)]
    assert all(math.dist(p, q) < 0.1 for p, q in zip(pts, official))


def test_rect_matches_the_official_park():
    pts = geo.rect((60150.0, 57100.0), 50000.0, 10000.0, yaw_deg=34.222659453871444)
    official = [(13182.98, 37248.06), (95868.81, 93489.1), (107117.02, 76951.94), (24431.19, 20710.9)]
    assert all(math.dist(p, q) < 0.5 for p, q in zip(pts, official))


def test_scatter_count_containment_and_determinism():
    poly = Polygon([(0, 0), (10000, 0), (10000, 10000), (0, 10000)], holes=[[(4000, 4000), (4000, 6000), (6000, 6000), (6000, 4000)]])
    a = geo.scatter(poly, 0.01, random.Random("1"))
    assert len(a) == 96 and all(geo.contains(poly, p) for p in a)
    assert a == geo.scatter(poly, 0.01, random.Random("1")) and a != geo.scatter(poly, 0.01, random.Random("2"))


def test_scatter_notes_an_under_fill_without_changing_its_points():
    # Final review M4: a thin sliver in a large bounding box runs out of tries; the shortfall is noted.
    sliver = Polygon([(0, 0), (100000, 100000), (100000, 100010)])
    notes = []
    a = geo.scatter(sliver, 1.0, random.Random("1"), max_tries_factor=1, notes=notes)
    assert a == geo.scatter(sliver, 1.0, random.Random("1"), max_tries_factor=1)
    assert len(notes) == 1 and "under-filled" in notes[0] and ("%d of" % len(a)) in notes[0]
    full = []
    geo.scatter(Polygon(RECT), 0.0001, random.Random("1"), notes=full)
    assert full == []


def test_choose_keeps_an_exact_share():
    picked = geo.choose(608, 0.641598, random.Random("x"))
    assert len(picked) == 390 and picked == sorted(set(picked))


def test_points_columns_attributes_and_take():
    pts = Points()
    pts.declare("Mesh", "SoftObjectPath")
    pts.add((1, 2, 3), Mesh="/Game/A.A")
    pts.add((4, 5, 6), rot=(0.0, 90.0, 0.0), Mesh="/Game/B.B")
    assert len(pts) == 2 and pts.scale[0] == (1.0, 1.0, 1.0) and pts.rot[1] == (0.0, 90.0, 0.0)
    sub = pts.take([1])
    assert len(sub) == 1 and sub.attrs["Mesh"] == ["/Game/B.B"] and sub.types == {"Mesh": "SoftObjectPath"}
    with pytest.raises(KeyError):
        pts.add((0, 0, 0), Undeclared=1)
    assert len(pts) == 2 and len(pts.attrs["Mesh"]) == 2          # a refused add leaves no partial row
    with pytest.raises(KeyError):
        pts.declare("seed", "Int32")                 # a point property, not an attribute


def test_json_round_trip_and_truncation():
    pts = Points()
    pts.declare("Label", "String")
    pts.add((1, 2, 3), Label="a")
    for v in (Polygon(RECT, z=5.0), Spline([(0, 0, 0), (1, 0, 0)], tangents=[((1, 0, 0), (1, 0, 0))] * 2, linear=False),
              ParamSet({"A": 1.5}, {"A": "Double"}), pts):
        back = geo.from_json(geo.to_json(v))
        assert geo.to_json(back) == geo.to_json(v)
    big = Points()
    for i in range(geo.MAX_RECORDED_POINTS + 1):
        big.add((i, 0, 0))
    rec = geo.to_json(big)
    assert rec["truncated"] and rec["n"] == geo.MAX_RECORDED_POINTS + 1
    with pytest.raises(ValueError):
        geo.from_json(rec)


def test_items_helpers():
    items = [("a", {"Small"}), ("b", {"Large", "Lots"}), ("c", {"Lots"})]
    assert geo.values(items) == ["a", "b", "c"] and geo.with_tag(items, "Lots") == ["b", "c"]


def test_enclosing_polygon_wraps_the_padded_box_around_the_path():
    # GetEnclosingPolygonFromPath closes an open artery-cut path by walking around the box
    # (padded 1 % of its largest side) rather than cutting through it.
    path = [(5000.0, 0.0), (5000.0, 10000.0)]
    bb = ((0.0, 0.0), (10000.0, 5000.0))
    result = geo.enclosing_polygon(path, bb)
    assert result[0] == path[0] and result[1] == path[1]
    corners = [(-100.0, -100.0), (10100.0, -100.0), (10100.0, 5100.0), (-100.0, 5100.0)]
    assert all(result.count(c) == 1 for c in corners)
    assert abs(geo.signed_area(result)) >= 10100.0 * 5100.0
    assert geo.inside(path[0], result)
    assert geo.enclosing_polygon(path, bb) == result        # no shared mutable state across calls


def test_enclosing_polygon_floors_the_padding_at_1_cm_on_a_degenerate_box():
    result = geo.enclosing_polygon([(5000.0, 0.0), (5000.0, 10000.0)], ((0.0, 0.0), (0.0, 0.0)))
    assert abs(geo.signed_area(result)) >= 4.0


def test_degenerate_rings_enclose_nothing():
    # Task 27: stage 7's planar union in the town returned holes like these; MakePolygon2DData refuses them.
    from pypcg import geo as G
    assert G.degenerate([(-39987.0, 32572.0), (-39777.3, 32347.6), (-39777.3, 32347.6)])
    assert G.degenerate([(5.0, 5.0)] * 4)
    assert G.degenerate([(0.0, 0.0), (1.0, 0.0), (0.0, 1e-7)])
    assert not G.degenerate([(0.0, 0.0), (100.0, 0.0), (0.0, 100.0)])
