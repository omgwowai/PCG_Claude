"""`pypcg.geo.splines` (the open-path primitives, stage 14 first) and `pypcg.geo.areas.follow_subjects` (where the
engine's offset puts a result ring's first vertex). Measured against the official taps in s14.md 2 and 6."""
from pypcg.geo import Polygon
from pypcg.geo import areas as A
from pypcg.geo import splines as SP


def box(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_truncate_cuts_both_ends_and_reverses():
    path = [(0.0, 0.0, 0.0), (1000.0, 0.0, 0.0), (1000.0, 1000.0, 0.0)]
    out = SP.truncate(path, 500.0, 300.0)
    assert out == [(1000.0, 700.0, 0.0), (1000.0, 0.0, 0.0), (500.0, 0.0, 0.0)]
    # a path not longer than an offset keeps that side (the measured 978 cm run: 478 cm left)
    assert SP.truncate([(0.0, 0.0, 0.0), (978.0, 0.0, 0.0)], 500.0, 500.0) == [(978.0, 0.0, 0.0), (500.0, 0.0, 0.0)]
    assert SP.truncate([(0.0, 0.0, 0.0), (400.0, 0.0, 0.0)], 500.0, 500.0) == [(400.0, 0.0, 0.0), (0.0, 0.0, 0.0)]


def test_resample_fit_drops_lines_under_two_samples():
    line = lambda L: [(0.0, 0.0, 0.0), (L, 0.0, 0.0)]     # noqa: E731
    assert SP.resample_fit(line(349.0), 350.0) == []
    assert SP.resample_fit(line(699.0), 350.0) == []                       # one sample: no spline
    assert [p[0] for p in SP.resample_fit(line(899.0), 350.0)] == [0.0, 899.0]
    pts = SP.resample_fit(line(3499.0), 350.0)
    assert len(pts) == 9 and abs(pts[1][0] - 3499.0 / 8) < 1e-9
    assert len(SP.resample_fit(line(3500.0), 350.0)) == 10


def test_chord_subdivide_offset_pairs_center():
    path = [(0.0, 0.0, 0.0), (300.0, 0.0, 0.0), (600.0, 10.0, 0.0)]
    assert SP.chord(path) == [(0.0, 0.0, 0.0), (600.0, 10.0, 0.0)]
    sub = SP.subdivide([(0.0, 0.0, 0.0), (600.0, 0.0, 0.0)], 5)
    assert [p[0] for p in sub] == [0.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0]
    off = SP.offset_local([(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)], -100.0, 200.0)
    assert all(abs(a - b) < 1e-9 for p, q in zip(off, [(-100.0, 200.0, 0.0), (0.0, 200.0, 0.0)]) for a, b in zip(p, q))
    assert SP.pairs(path) == [[path[0], path[1]], [path[1], path[2]]]
    loc, yaw = SP.center([(0.0, 0.0, 0.0), (0.0, 350.0, -2.0)])
    assert loc == (0.0, 175.0, -1.0) and abs(yaw - 90.0) < 1e-12
    assert SP.control_yaws([(0.0, 0.0), (0.0, 1.0), (-1.0, 1.0)]) == [90.0, 180.0, 180.0]


def test_follow_subjects_orders_and_restarts_the_rings():
    a, b = box(0, 0, 10, 10), box(10, 0, 20, 10)
    # a union result spanning both subjects (its vertex mean (9, 5) lies in A), handed back starting elsewhere
    spanning = Polygon([(17, 9), (1, 9), (1, 1), (17, 1)])
    # a result outside every subject: the nearest subject by vertex mean is B (15, 5), not A (5, 5)
    outside = Polygon([(31, 3), (30, 3), (30, 2), (31, 2)])
    out = A.follow_subjects([outside, spanning], [a, b])
    assert out[0].outer == [(1, 1), (17, 1), (17, 9), (1, 9)]       # A's: restarted at A's first vertex (0, 0)
    assert out[1].outer == [(30, 2), (31, 2), (31, 3), (30, 3)]     # B's: restarted at B's first vertex (10, 0)
    assert [len(p.outer) for p in out] == [4, 4]
