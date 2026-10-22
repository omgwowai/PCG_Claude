"""The small area's control layout (pypcg.profiles.small_layout) and profile."""
from pypcg import combined
from pypcg.profiles import city, small, small_layout as S

ARTERY_HALF = 1700          # 34 m arteries (S07_Artery_width 3400)


def _clear_of_arteries(poly):
    return min(min(S.polyline_distance(p, S.ARTERY_A1) for p in poly),
               min(S.polyline_distance(p, S.ARTERY_A2) for p in poly)) - ARTERY_HALF


def test_landmarks_sit_inside_the_city_and_clear_of_the_arteries():
    for poly in (S.tower_rect(), S.LANDMARK_PARK, S.PARK_RECT, S.LAKE, S.FOREST_EXCLUSION):
        assert all(S.inside(p, S.CITY) for p in poly)
        assert _clear_of_arteries(poly) > 2000                       # > 20 m of kerb
        assert min(S.edge_distance(p, S.CITY) for p in poly) > 1500   # > 15 m from the waterfront


def test_park_holds_its_lake_paths_and_forest_exclusion():
    for poly in (S.LAKE, S.FOREST_EXCLUSION) + S.PARK_PATHS:
        assert all(S.inside(p, S.PARK_RECT) for p in poly)


def test_arteries_cross_the_city_and_the_inner_highway_cuts_a_corner():
    assert S.crossings(S.ARTERY_A1, S.CITY) == 2 and S.crossings(S.ARTERY_A2, S.CITY) == 2
    assert S.crossings(S.HIGHWAY_2, S.CITY) == 2
    assert min(S.polyline_distance(p, S.HIGHWAY_2) for p in S.tower_rect()) > 2000


def test_layout_tags_cover_every_tag_the_graph_reads():
    read = {"City", "Arteries", "Terrain_shaping_1", "HighRise", "USER_SPLINE", "LAKE", "FOREST_EXCLUSION"}
    read |= set(combined.ROLE_TAGS.values()) | set(combined.CONTROL_TAGS.values())
    assert read <= set(S.TAGS)
    assert set(S.CONTROL_MOVES) == set(S.TAGS["PyCity_MainTowerFootprint"] + S.TAGS["PyCity_CentralParkFootprint"])


def test_profile_sizes_match_the_layout():
    o = small.COMPONENT_OVERRIDES
    assert o["S04_RectWidth"] == o["S04_RectLength"] == 2 * S.TOWER_HALF
    assert (o["S05_RectWidth"], o["S05_RectLength"]) == (2 * S.PARK_HALF[0], 2 * S.PARK_HALF[1])
    assert small.TEMPLATE == city.LEVEL and small.VOLUME == city.VOLUME
    assert set(city.COMPONENT_OVERRIDES) <= set(o)
