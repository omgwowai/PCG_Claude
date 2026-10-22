import math

from pypcg.world import astar, geom
from pypcg.world.grid import Lattice


def test_resample_chaikin_average():
    pts = geom.resample([(0.0, 0.0), (1000.0, 0.0)], 300.0)
    assert len(pts) == 5 and pts[-1] == (1000.0, 0.0) and abs(geom.dist2d(pts[0], pts[1]) - 250.0) < 1e-9
    c = geom.chaikin([(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)], 1)
    assert c[0] == (0.0, 0.0) and c[-1] == (100.0, 100.0) and len(c) == 6
    assert geom.moving_average([0.0, 0.0, 3.0, 0.0, 0.0], 1)[2] == 1.0
    (x, y), yaw = geom.at_distance([(0.0, 0.0), (0.0, 100.0)], [0.0, 100.0], 40.0)
    assert (x, y) == (0.0, 40.0) and yaw == 90.0


def test_segment_index_and_intersections():
    idx = geom.SegmentIndex(500.0)
    idx.add_polyline([(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0)], 7)
    d, i, t = idx.nearest(500.0, 30.0, 100.0)
    assert abs(d - 30.0) < 1e-9 and idx.payload(i) == 7 and abs(t - 0.5) < 1e-9
    assert idx.nearest(500.0, 300.0, 100.0) is None
    hits = geom.polyline_intersections([(0.0, -50.0), (0.0, 50.0)], [(-50.0, 0.0), (50.0, 0.0)])
    assert len(hits) == 1 and abs(hits[0][0]) < 1e-9 and abs(hits[0][3] - 0.5) < 1e-9


def test_rects_rings():
    r = geom.rect(0.0, 0.0, 400.0, 200.0, 90.0)
    xs, ys = [p[0] for p in r], [p[1] for p in r]
    assert abs(max(ys) - 200.0) < 1e-9 and abs(max(xs) - 100.0) < 1e-9
    area = 0.5 * sum(r[i][0] * r[(i + 1) % 4][1] - r[(i + 1) % 4][0] * r[i][1] for i in range(4))
    assert area > 0
    assert geom.point_in_ring(0.0, 150.0, r) and not geom.point_in_ring(150.0, 0.0, r)
    assert geom.rings_overlap(r, geom.rect(0.0, 190.0, 50.0, 50.0, 0.0))
    assert not geom.rings_overlap(r, geom.rect(0.0, 300.0, 50.0, 50.0, 0.0))
    ri = geom.RingIndex(1000.0)
    ri.add(r, "a")
    assert ri.contains(0.0, 0.0) == "a" and ri.near(130.0, 0.0, 40.0) and not ri.near(200.0, 0.0, 40.0)
    assert ri.overlaps(geom.rect(80.0, 0.0, 50.0, 50.0, 0.0))


def test_astar_prefers_cheap_and_reaches_any_goal():
    lat = Lattice(9, 100.0, 0.0, 0.0, [0.0] * 81)
    wall = {lat.k(4, j) for j in range(0, 8)}

    def cost(a, b, L):
        return None if b in wall else L
    path = astar.search(lat, {lat.k(0, 0): 0.0}, {lat.k(8, 0)}, cost, astar.MOVES8)
    assert path[0] == lat.k(0, 0) and path[-1] == lat.k(8, 0) and lat.k(4, 8) in path
    multi = astar.search(lat, {lat.k(0, 0): 0.0}, {lat.k(2, 0), lat.k(0, 7)}, cost, astar.MOVES16, h_scale=0.0)
    assert multi[-1] == lat.k(2, 0)
    assert astar.search(lat, {lat.k(0, 0): 0.0}, {lat.k(8, 0)}, lambda a, b, L: None) is None
