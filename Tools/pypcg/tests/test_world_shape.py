import math

from pypcg.world import shape


def _arc(r, degrees, n=200):
    return [(r * math.cos(math.radians(degrees * i / n)), r * math.sin(math.radians(degrees * i / n))) for i in range(n + 1)]


def test_a_straight_line_is_all_straight():
    s = shape.stats([(0.0, 0.0), (50000.0, 0.0)])
    assert s["straight_share"] == 1.0 and abs(s["longest_straight_m"] - 500.0) < 1e-6 and s["max_turn_deg"] < 1e-9


def test_a_circle_arc_has_no_straight_and_its_radius():
    s = shape.stats(_arc(20000.0, 120.0, 4000))            # dense: the 5 m resample stays on the circle
    assert s["straight_share"] == 0.0 and abs(s["min_radius_m"] - 200.0) < 2.0
    assert abs(s["max_turn_deg"] - math.degrees(500.0 / 20000.0)) < 0.05


def test_a_kink_shows_as_a_turn():
    """A 45 degree corner falls inside one 5 m resample step, so it shows split over two steps (> 20 degrees each
    side); a smooth curve at road radii turns < 2 degrees per step."""
    s = shape.stats([(0.0, 0.0), (10000.0, 0.0), (20000.0, 10000.0)])
    assert s["max_turn_deg"] > 20.0 and s["straight_share"] > 0.9


def test_signed_curvature():
    k = shape.curvature(_arc(1000.0, 90.0, 20))
    assert all(abs(x - 0.001) < 1e-6 for x in k[1:-1])          # counter-clockwise: positive
    k = shape.curvature(_arc(1000.0, 90.0, 20)[::-1])
    assert all(abs(x + 0.001) < 1e-6 for x in k[1:-1])


def test_overlap_length():
    a = [(0.0, 0.0), (10000.0, 0.0)]
    b = [(5000.0, 100.0), (20000.0, 100.0)]
    assert abs(shape.overlap_length(a, b) - 5000.0) < 501.0
    assert shape.overlap_length(a, [(0.0, 5000.0), (10000.0, 5000.0)]) == 0.0
