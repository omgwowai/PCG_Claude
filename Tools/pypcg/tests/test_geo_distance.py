"""The shared helpers stage 18 added or changed (Task 23; Step C: shared helpers carry their own tests):
`geo.distance` (Write_DistanceFrom on points), `geo.assets.merge_targets` and the banded `geo.ground.fill_random`.
Their official-data measurements are in `test_s18_outer_forest.py`."""
import math
import random

import pytest

from pypcg import geo
from pypcg.geo import Points, Polygon
from pypcg.geo import assets as AS
from pypcg.geo import distance as D
from pypcg.geo import ground as G
from pypcg.stages import s13_leftover_trees as T13


def test_distance_without_targets_is_the_maximum_and_a_point_range_remaps_to_the_middle():
    vals = D.distance_from([[(0.0, 0.0), (5.0, 5.0)]], [], 5000.0, 1.0, 0.0)
    assert vals == [[0.5, 0.5]]
    assert D.Nearest2D([], 100.0).distance(0.0, 0.0) == 100.0
    assert D.Nearest2D([(30.0, 40.0)], 100.0).distance(0.0, 0.0) == 50.0
    assert D.Nearest2D([(100.0, 0.0)], 100.0).distance(0.0, 0.0) == 100.0        # not strictly inside the reach
    with pytest.raises(ValueError):
        D.Nearest2D([], 100.0, cell=50.0)


def test_target_centre_is_the_box_centre_round_trip():
    c = D.target_centre((1.1, 2.2, 3.3), (1.4698423602466122,) * 3, (-10.0,) * 3, (10.0,) * 3)
    e = 10.0 * 1.4698423602466122
    assert c == (((1.1 - e) + (1.1 + e)) * 0.5, ((2.2 - e) + (2.2 + e)) * 0.5)
    r = D.target_centre((0.0, 0.0, 0.0), (1.0,) * 3, (0.0, 0.0, 0.0), (20.0, 0.0, 0.0), AS.quat_of(0.0, 90.0, 0.0))
    assert abs(r[0]) < 1e-9 and abs(r[1] - 10.0) < 1e-9


def test_merge_targets_keeps_rotations_unless_upright_and_adds_the_data_index_to_the_seed():
    a, b = Points(), Points()
    a.add((0.0, 0.0, 0.0), rot=(1.0, 2.0, 3.0), seed=10)
    b.add((1.0, 0.0, 0.0), rot=(4.0, 5.0, 6.0), seed=2 ** 31 - 1)
    m = AS.merge_targets([(a, ()), (b, ()), ("not points", ())])
    assert m.rot == [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)] and m.seed == [10, -2 ** 31] and m.quat is None
    u = AS.merge_targets([(a, ()), (b, ())], upright=True)
    assert u.rot == [(0.0, 2.0, 0.0), (0.0, 5.0, 0.0)]
    assert T13.upright([(a, ()), (b, ())]).rot == u.rot


def test_fill_random_banded_equals_the_full_containment_test():
    """`geo.ground.fill_random` tests each point only against its row's edges; the result must be the full
    `geo.plane.inside` test's, point for point, holes included."""
    ring = [(0.0, 0.0), (9000.0, 300.0), (12000.0, 7000.0), (4000.0, 11000.0), (-2000.0, 6000.0)]
    hole = [(3000.0, 3000.0), (3000.0, 6000.0), (7000.0, 6000.0), (7000.0, 3000.0)]
    poly = Polygon(ring, [hole], 12.5)
    got = G.fill_random(poly, 0.05, random.Random(11))
    rng = random.Random(11)
    cell = math.sqrt(1e4 / 0.05)
    want = []
    for j in range(math.ceil(0.0 / cell), math.floor(11000.0 / cell) + 1):
        for i in range(math.ceil(-2000.0 / cell), math.floor(12000.0 / cell) + 1):
            x, y = i * cell + rng.random() * (cell - 2.0), j * cell + rng.random() * (cell - 2.0)
            if geo.inside((x, y), ring) and not geo.inside((x, y), hole):
                want.append((x, y, 12.5))
    assert got == want and len(got) > 300
