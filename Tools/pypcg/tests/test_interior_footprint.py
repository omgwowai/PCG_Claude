"""PyInterior footprint: local frame, rasterisation, outline, wings (spec 2026-10-28 §4.1)."""
import math

import pytest

from pypcg.interior import footprint as F
from pypcg.interior.footprint import Rect


def rect_pts(w, h, x0=0.0, y0=0.0):
    return [(x0, y0, 0.0), (x0 + w, y0, 0.0), (x0 + w, y0 + h, 0.0), (x0, y0 + h, 0.0)]


def world_of(local_pts, origin, yaw):
    """Local (x, y) -> world, the inverse of the footprint's frame (e_x = (-sin a, cos a), e_y = (-cos a, -sin a))."""
    a = math.radians(yaw)
    ex, ey = (-math.sin(a), math.cos(a)), (-math.cos(a), -math.sin(a))
    return [(origin[0] + x * ex[0] + y * ey[0], origin[1] + x * ex[1] + y * ey[1], origin[2]) for x, y, *_ in local_pts]


def test_rect_basics():
    a, b = Rect(0, 0, 400, 300), Rect(400, 100, 700, 300)
    assert (a.w, a.h, a.area, a.cx, a.cy) == (400, 300, 120000, 200, 150)
    assert a.contains(10, 10) and not a.contains(450, 10)
    assert not a.overlaps(b) and a.overlaps(Rect(390, 0, 500, 50))
    assert a.shared(b) == ("x", 400, 100, 300)
    assert Rect(0, 300, 400, 500).shared(a) == ("y", 300, 0, 400)
    assert a.shared(Rect(500, 0, 600, 100)) is None
    assert a.shrink(10, 20, 30, 40) == Rect(10, 20, 370, 260)


def test_rectangle_in_the_actor_frame():
    # yaw 0: the house faces world +X, so local x runs along world +Y and local y along world -X
    pts = world_of(rect_pts(1000, 800), (500.0, 200.0, 30.0), 0.0)
    fp = F.build(pts, (500.0, 200.0, 30.0), 0.0)
    assert fp is not None
    assert len(fp.poly) == 4 and len(fp.wings) == 1
    assert fp.wings[0] == Rect(0, 0, 1000, 800)
    assert fp.area_m2 == pytest.approx(80.0)
    assert fp.front == [(0.0, 1000.0, 0.0)]


def test_rotated_rectangle_gives_the_same_local_footprint():
    base = F.build(world_of(rect_pts(1000, 800), (0, 0, 0), 0.0), (0, 0, 0), 0.0)
    for yaw in (30.0, 90.0, 217.0):
        fp = F.build(world_of(rect_pts(1000, 800), (1234.0, -567.0, 0.0), yaw), (1234.0, -567.0, 0.0), yaw)
        assert fp.cells == base.cells and fp.wings == base.wings and fp.poly == base.poly


def test_to_world_round_trips_and_yaw():
    fp = F.build(world_of(rect_pts(600, 500), (100.0, 50.0, 10.0), 30.0), (100.0, 50.0, 10.0), 30.0)
    X, Y, Z = fp.to_world(600.0, 500.0, 5.0)
    back = world_of([(600.0, 500.0)], (100.0, 50.0, 10.0), 30.0)[0]
    assert (X, Y) == pytest.approx(back[:2]) and Z == pytest.approx(15.0)
    # a local direction at yaw t points along world yaw a + 90 + t
    assert fp.yaw_world(0.0) == pytest.approx(120.0)
    assert fp.yaw_world(-90.0) % 360.0 == pytest.approx(30.0)   # local -y (the front) is the actor's forward


def l_shape(w=1400, h=1100, cut_w=600, cut_h=500):
    # CCW, the notch at the back right
    return [(0, 0, 0), (w, 0, 0), (w, h - cut_h, 0), (w - cut_w, h - cut_h, 0), (w - cut_w, h, 0), (0, h, 0)]


def check_tiling(fp):
    covered = set()
    g = fp.grid
    for i, a in enumerate(fp.wings):
        assert min(a.w, a.h) >= 250.0
        for b in fp.wings[i + 1:]:
            assert not a.overlaps(b)
        for ci in range(int(round(a.x0 / g)), int(round(a.x1 / g))):
            for cj in range(int(round(a.y0 / g)), int(round(a.y1 / g))):
                covered.add((ci, cj))
    assert covered == fp.cells


def test_l_shape_two_wings_tile_the_cells():
    fp = F.build(world_of(l_shape(), (0, 0, 0), 0.0), (0, 0, 0), 0.0)
    assert len(fp.wings) == 2
    check_tiling(fp)
    assert fp.area_m2 == pytest.approx(14 * 11 - 6 * 5)
    assert len(fp.poly) == 6


def test_u_shape_three_wings():
    u = [(0, 0, 0), (1600, 0, 0), (1600, 1000, 0), (1100, 1000, 0), (1100, 500, 0), (500, 500, 0), (500, 1000, 0),
         (0, 1000, 0)]
    fp = F.build(world_of(u, (0, 0, 0), 0.0), (0, 0, 0), 0.0)
    assert len(fp.wings) == 3
    check_tiling(fp)


def test_noisy_points_snap_to_the_grid():
    noisy = [(x + dx, y + dy, 0) for (x, y, _), (dx, dy) in
             zip(rect_pts(1000, 800), [(12, -9), (-11, 7), (8, 12), (-12, -10)])]
    fp = F.build(world_of(noisy, (0, 0, 0), 0.0), (0, 0, 0), 0.0)
    assert fp.wings == [Rect(0, 0, 1000, 800)]


def test_too_small_is_rejected():
    assert F.build(world_of(rect_pts(300, 300), (0, 0, 0), 0.0), (0, 0, 0), 0.0) is None
    assert F.build([], (0, 0, 0), 0.0) is None


@pytest.mark.parametrize("w, h, ok", [(450, 450, False), (470, 470, False), (450, 470, False), (480, 450, True),
                                      (450, 480, True), (500, 500, True), (450, 600, True)])
def test_the_smallest_footprint_holds_a_studio(w, h, ok):
    """A 4.5 x 4.5 m square cannot hold a studio's living room (280 x 340 clear) beside or behind its bathroom (140 x 180)
    once the walls are counted, so the long side must reach 5 m after the outline snaps to the grid (4.6-4.7 m snap to 4.5);
    every footprint that is accepted plans clean (review finding 2)."""
    import random
    from pypcg.interior import layout as L
    from pypcg.interior import program as P
    fp = F.build(world_of(rect_pts(w, h), (0, 0, 0), 0.0), (0, 0, 0), 0.0)
    assert (fp is not None) == ok
    if ok:
        plan = L.plan(fp, P.choose(fp.area_m2), random.Random(1))
        assert plan.program.name == "Studio" and not plan.failures, plan.failures


def test_sliver_is_dropped():
    # a 1 m bump on the front: thinner than a wing, so the house is simplified back to the rectangle
    bump = [(0, 0, 0), (400, 0, 0), (400, -100, 0), (600, -100, 0), (600, 0, 0), (1000, 0, 0), (1000, 800, 0),
            (0, 800, 0)]
    fp = F.build(world_of(bump, (0, 0, 0), 0.0), (0, 0, 0), 0.0)
    assert fp.wings == [Rect(0, 0, 1000, 800)]
    check_tiling(fp)


def test_segments_and_corners():
    fp = F.build(world_of(l_shape(), (0, 0, 0), 0.0), (0, 0, 0), 0.0)
    segs = fp.segments()
    # 6 boundary segments, total length = perimeter
    assert len(segs) == 6
    assert sum(s.a1 - s.a0 for s in segs) == pytest.approx(2 * (1400 + 1100))
    # one reflex corner (at the notch): exactly one segment end is not convex on each of two segments
    reflex = sum((not s.convex0) + (not s.convex1) for s in segs)
    assert reflex == 2
    front = [s for s in segs if s.axis == "y" and s.normal < 0]
    assert [(s.a0, s.a1, s.c) for s in front] == [(0.0, 1400.0, 0.0)]
