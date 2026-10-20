"""`pypcg.geo.curves` (stage 16 first): the Hermite evaluation, its derivative and the nearest-key search, on
splines whose answers are known in closed form, plus the auto tangents, split, per-point offset and reverse on
small hand-made cases. The stage-16 tap comparisons live in `test_s16_central_park_visuals.py`."""
import math

from pypcg.geo import curves as C

# a straight 3-point open spline along X with tangents (100, 0, 0): a Hermite curve that IS the line x = 100 t
LINE = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (200.0, 0.0, 0.0)]
LINE_T = [((100.0, 0.0, 0.0), (100.0, 0.0, 0.0))] * 3


def test_position_at_the_keys_and_between_them():
    for k in (0.0, 1.0, 2.0 - 1e-12):
        p = C.position_at(LINE, LINE_T, False, k)
        assert abs(p[0] - 100.0 * k) <= 1e-9 and p[1] == 0.0
    assert C.position_at(LINE, LINE_T, False, 0.25) == (25.0, 0.0, 0.0)
    assert C.position_at(LINE, LINE_T, False, 1.5) == (150.0, 0.0, 0.0)


def test_position_follows_the_hermite_basis_on_a_curved_segment():
    pts = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)]
    tans = [((0.0, 100.0, 0.0), (0.0, 100.0, 0.0)), ((0.0, -100.0, 0.0), (0.0, -100.0, 0.0))]
    # y(a) = 100 (a^3 - 2a^2 + a) - 100 (a^3 - a^2) = 100 (a - a^2)
    for a in (0.1, 0.5, 0.9):
        p = C.position_at(pts, tans, False, a)
        assert abs(p[1] - 100.0 * (a - a * a)) <= 1e-9
        assert abs(p[0] - 100.0 * (3 * a * a - 2 * a ** 3)) <= 1e-9


def test_derivative_is_the_tangent_at_the_keys_and_the_slope_between():
    pts = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)]
    tans = [((0.0, 100.0, 0.0), (0.0, 100.0, 0.0)), ((0.0, -100.0, 0.0), (0.0, -100.0, 0.0))]
    assert C.derivative_at(pts, tans, False, 0.0) == (0.0, 100.0, 0.0)
    d = C.derivative_at(pts, tans, False, 1.0 - 1e-12)
    assert abs(d[1] + 100.0) <= 1e-6 and abs(d[0]) <= 1e-6
    a, h = 0.3, 1e-6
    num = [(C.position_at(pts, tans, False, a + h)[k] - C.position_at(pts, tans, False, a - h)[k]) / (2 * h)
           for k in range(3)]
    assert all(abs(x - y) <= 1e-4 for x, y in zip(num, C.derivative_at(pts, tans, False, a)))
    assert C.derivative_at(LINE, None, False, 0.5) == (100.0, 0.0, 0.0)          # linear: the chord


def test_nearest_key_finds_the_closest_curve_point():
    """A golden-section search on the distance, which is flat (quadratic) at its minimum: keys to ~1e-8, i.e.
    about 1e-6 cm here -- finer than the engine's own FLOAT key."""
    assert abs(C.nearest_key(LINE, LINE_T, False, (137.5, 40.0, 0.0)) - 1.375) <= 1e-7
    assert abs(C.nearest_key(LINE, LINE_T, False, (-50.0, 10.0, 0.0)) - 0.0) <= 1e-7          # before the start
    pts = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)]
    tans = [((0.0, 100.0, 0.0), (0.0, 100.0, 0.0)), ((0.0, -100.0, 0.0), (0.0, -100.0, 0.0))]
    target = C.position_at(pts, tans, False, 0.4)
    k = C.nearest_key(pts, tans, False, target)
    assert abs(k - 0.4) <= 1e-7


def test_auto_tangents_closed_and_open():
    sq = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (0.0, 10.0, 0.0)]
    assert C.auto_tangents(sq, True)[0] == (5.0, -5.0, 0.0)
    assert C.auto_tangents(LINE, False) == [(50.0, 0.0, 0.0), (100.0, 0.0, 0.0), (50.0, 0.0, 0.0)]


def test_split_keeps_inner_points_and_scales_the_cut_tangents():
    pts, tans = C.split(LINE, LINE_T, 0.5, 1.5)
    assert [p[0] for p in pts] == [50.0, 100.0, 150.0]
    assert tans[0] == ((50.0, 0.0, 0.0), (50.0, 0.0, 0.0))            # r = 0.5 both ways
    assert tans[1] == ((50.0, 0.0, 0.0), (50.0, 0.0, 0.0))            # arrive x (1 - 0.5), leave x 0.5
    assert C.split(LINE, LINE_T, 1.5, 0.5) == ([], [])


def test_offset_points_moves_along_the_tilted_up_and_reverse_negates():
    flat = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 100.0, 0.0)]
    tans = [((100.0, 0.0, 0.0), (100.0, 0.0, 0.0))] * 3
    moved, _t = C.offset_points(flat, tans, True, (0.0, 0.0, -50.0))
    assert all(abs(m[2] + 50.0) <= 1e-9 and abs(m[0] - p[0]) <= 1e-9 for m, p in zip(moved, flat))
    tilted = [((100.0, 0.0, 100.0), (100.0, 0.0, 100.0))] * 3        # a 45 deg slope tilts the offset
    moved, _t = C.offset_points(flat, tilted, True, (0.0, 0.0, -50.0))
    assert abs(moved[0][0] - 50.0 / math.sqrt(2.0)) <= 1e-9
    p, t = C.reverse(flat, tans)
    assert p == flat[::-1] and t[0] == ((-100.0, -0.0, -0.0), (-100.0, -0.0, -0.0))
