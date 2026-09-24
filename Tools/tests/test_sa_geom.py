import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "Content", "Python"))

import pcg_sa_geom as G


# Measured 2026-09-24 from L_CitySamplePCG_Demo: CityShape is 213006 x 181776 cm.
CITY_MIN = [-115988.107, -83950.695, 0.0]
CITY_MAX = [97018.107, 97825.0, 0.0]


def test_scale_matches_hand_computed_value():
    # 600 m = 60000 cm over the 213006 cm long side -> 0.281682...
    s = G.scale_for_target((CITY_MIN, CITY_MAX), 60000.0)
    assert abs(s - 0.281682) < 1e-5


def test_scale_uses_the_larger_dimension_not_the_first():
    # A tall-but-narrow bbox must be driven by its long side.
    s = G.scale_for_target(([0.0, 0.0, 0.0], [100.0, 400.0, 0.0]), 200.0)
    assert abs(s - 0.5) < 1e-9


def test_center_of_bbox_is_invariant_under_the_transform():
    center = [(CITY_MIN[i] + CITY_MAX[i]) / 2.0 for i in range(3)]
    s = G.scale_for_target((CITY_MIN, CITY_MAX), 60000.0)
    out = G.map_point(center, s, center, center)
    for a, b in zip(out, center):
        assert abs(a - b) < 1e-6


def test_map_point_translates_and_scales_about_the_source_center():
    # Point 1000 cm to the +X of the source center, halved, about the origin.
    out = G.map_point([1000.0, 0.0, 0.0], 0.5, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    assert out == [500.0, 0.0, 0.0]
    # Same scale, moved so the source center lands at (10, 20, 0).
    out2 = G.map_point([1000.0, 0.0, 0.0], 0.5, [0.0, 0.0, 0.0], [10.0, 20.0, 0.0])
    assert out2 == [510.0, 20.0, 0.0]


def test_map_point_keeps_internal_distances_uniform_on_every_axis():
    s = 0.25
    a = G.map_point([0.0, 0.0, 0.0], s, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    b = G.map_point([100.0, 200.0, 300.0], s, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    d = [b[i] - a[i] for i in range(3)]
    assert d == [25.0, 50.0, 75.0]


def test_map_tangent_scales_without_translating():
    assert G.map_tangent([100.0, -50.0, 10.0], 0.5) == [50.0, -25.0, 5.0]


def test_bbox_of_points_handles_a_single_point_and_a_flat_axis():
    mn, mx = G.bbox_of_points([[3.0, 4.0, 5.0]])
    assert mn == [3.0, 4.0, 5.0] and mx == [3.0, 4.0, 5.0]
    mn2, mx2 = G.bbox_of_points([[0.0, 0.0, 7.0], [10.0, -4.0, 7.0]])
    assert mn2 == [0.0, -4.0, 7.0] and mx2 == [10.0, 0.0, 7.0]


def test_city_bbox_from_splines_takes_the_union():
    splines = [
        {"points": [[0.0, 0.0, 0.0], [10.0, 10.0, 0.0]]},
        {"points": [[-5.0, 20.0, 0.0]]},
    ]
    mn, mx = G.city_bbox_from_splines(splines)
    assert mn == [-5.0, 0.0, 0.0] and mx == [10.0, 20.0, 0.0]


def test_orbit_camera_looks_at_the_center_from_the_requested_bearing():
    import math
    loc, rot = G.orbit_camera([0.0, 0.0, 0.0], 300.0, az_deg=0.0, elev_deg=45.0,
                              dist_mult=3.0, min_height=200.0)
    # dist_mult=3 over radius 300 puts the camera 900 units from the centre,
    # measured ALONG THE VIEWING RAY. At 45 degrees elevation that is a horizontal
    # offset of 900*cos(45) = 636.40 with the same again in Z, so the ray distance
    # is the invariant to assert, not the horizontal component.
    ray = (loc[0] ** 2 + loc[1] ** 2 + loc[2] ** 2) ** 0.5
    assert abs(ray - 900.0) < 1e-6
    # bearing 0 = +X: no lateral offset, and above the floor.
    assert loc[0] > 0.0
    assert abs(loc[1]) < 1e-6
    assert abs(loc[2] - 636.3961030678928) < 1e-6
    assert loc[2] >= 200.0
    pitch, yaw, roll = rot
    assert pitch < 0                    # looking downward
    assert abs(abs(yaw) - 180.0) < 1.0  # facing back toward -X
    assert roll == 0.0


def test_orbit_camera_respects_the_minimum_height_for_a_flat_view():
    loc, _ = G.orbit_camera([0.0, 0.0, 0.0], 300.0, az_deg=0.0, elev_deg=2.0,
                            dist_mult=3.0, min_height=500.0)
    assert loc[2] == 500.0
