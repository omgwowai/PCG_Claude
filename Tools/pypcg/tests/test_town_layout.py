"""The town layout's relations (Task 25): the 18 stages rely on these, so they are tests, not notes.

The nine tests of the brief come first; the ones after them pin what `pypcg_town_level.py`'s
`layout` and `bind` phases and the direct spline writes depend on (the spline table covers every
control actor, the tags have exactly one carrier in the town, the landmark volumes sit over the
landmarks)."""
import math

from pypcg import graphs, stages
from pypcg.profiles import official, town_layout as T

M = 100  # cm per m


def test_city_is_about_1100_by_900_m():
    (x0, y0, _), (x1, y1, _) = T.city_bbox()
    assert abs((x1 - x0) / M - 1100) <= 220 and abs((y1 - y0) / M - 900) <= 180


def test_terrain_shaping_contains_city_with_100_m_margin():
    assert all(T.inside(p, T.TERRAIN_SHAPING) for p in T.CITY)
    assert min(T.edge_distance(p, T.TERRAIN_SHAPING) for p in T.CITY) >= 100 * M


def test_arteries_cross_the_city_and_each_other():
    for a in (T.ARTERY_A1, T.ARTERY_A2):
        assert T.crossings(a, T.CITY) == 2
        assert not T.inside(a[0], T.CITY) and not T.inside(a[-1], T.CITY)
        assert min(T.edge_distance(a[0], T.CITY), T.edge_distance(a[-1], T.CITY)) >= 150 * M
    assert T.crossings(T.ARTERY_A1, [p for p in T.ARTERY_A2], closed=False) == 1


def test_highways_cut_the_north_east_corner_30_m_apart():
    for h in (T.HIGHWAY_2, T.HIGHWAY_3):
        assert T.crossings(h, T.CITY) == 2
    gap = T.polyline_distance(T.HIGHWAY_2[len(T.HIGHWAY_2) // 2], T.HIGHWAY_3)
    assert abs(gap / M - 30) < 1


def test_main_tower_and_landmarks_sit_inside_with_margins():
    tower = T.MAIN_TOWER
    assert T.inside(tower, T.CITY)
    assert T.edge_distance(tower, T.CITY) - T.TOWER_HALF >= 50 * M
    assert min(T.polyline_distance(tower, h) for h in (T.HIGHWAY_2, T.HIGHWAY_3)) - T.TOWER_HALF >= 60 * M
    assert all(T.inside(p, T.CITY) for p in T.HIGHRISE + T.LANDMARK_PARK)
    lx = [p[0] for p in T.LANDMARK_PARK]
    assert max(lx) < tower[0] - T.TOWER_HALF          # the small park does not overlap the tower


def test_central_park_and_parking_are_clear_of_edges_and_arteries():
    for shape in (T.PARK_RECT, T.parking_rect()):
        assert all(T.inside(p, T.CITY) for p in shape)
        assert min(T.edge_distance(p, T.CITY) for p in shape) >= 30 * M
        assert min(T.polyline_distance(p, a) for p in shape for a in (T.ARTERY_A1, T.ARTERY_A2)) >= 40 * M


def test_park_features_lie_inside_the_park():
    for shape in [T.LAKE, T.FOREST_EXCLUSION] + list(T.PARK_PATHS):
        assert all(T.inside(p, T.PARK_RECT) for p in shape)


def test_spline_table_is_complete():
    assert set(T.SPLINES) == {"CityShape", "TerrainShaping", "Artery_1", "Artery_2", "HighWay_2", "HighWay_3",
                              "HighRise_Zone_1", "MainTowerPark", "Lake_1", "ParkPath_1", "ParkPath_2",
                              "ForestExclusion_1"}
    for spec in T.SPLINES.values():
        assert all(len(p) == 3 for p in spec["points"])


def test_parking_rect_is_about_70_by_45_m():
    assert abs((T.PARKING_HALF[0] * 2) / M - 70) < 5 and abs((T.PARKING_HALF[1] * 2) / M - 45) < 5


# ---- beyond the brief: what the level script and the graphs depend on

def test_spline_points_are_the_layout_geometry():
    """Each spline is its own source polygon, converted once to (x, y, 0) -- no second copy of a
    coordinate anywhere, so an edit to CITY or PARK_PATHS cannot land in one and miss the other."""
    flat = lambda pts: [(float(x), float(y), 0.0) for x, y in pts]
    assert T.SPLINES["CityShape"]["points"] == flat(T.CITY)
    assert T.SPLINES["TerrainShaping"]["points"] == flat(T.TERRAIN_SHAPING)
    assert T.SPLINES["Artery_1"]["points"] == flat(T.ARTERY_A1)
    assert T.SPLINES["Artery_2"]["points"] == flat(T.ARTERY_A2)
    assert T.SPLINES["HighWay_2"]["points"] == flat(T.HIGHWAY_2)
    assert T.SPLINES["HighWay_3"]["points"] == flat(T.HIGHWAY_3)
    assert T.SPLINES["HighRise_Zone_1"]["points"] == flat(T.HIGHRISE)
    assert T.SPLINES["MainTowerPark"]["points"] == flat(T.LANDMARK_PARK)
    assert T.SPLINES["Lake_1"]["points"] == flat(T.LAKE)
    assert T.SPLINES["ParkPath_1"]["points"] == flat(T.PARK_PATHS[0])
    assert T.SPLINES["ParkPath_2"]["points"] == flat(T.PARK_PATHS[1])
    assert T.SPLINES["ForestExclusion_1"]["points"] == flat(T.FOREST_EXCLUSION)


def test_every_spline_is_at_ground_level():
    """The town lies on the terrain plane; a non-zero z would put CityShape above the ground the
    projections sample."""
    for name, spec in T.SPLINES.items():
        assert all(p[2] == 0.0 for p in spec["points"]), name


def test_closedness_follows_the_geometry():
    closed = {n for n, s in T.SPLINES.items() if s["closed"]}
    assert closed == set(T.SPLINE_CLOSED)
    assert closed == {"CityShape", "TerrainShaping", "HighRise_Zone_1", "MainTowerPark", "Lake_1",
                      "ForestExclusion_1"}
    assert set(T.SPLINES) - closed == {"Artery_1", "Artery_2", "HighWay_2", "HighWay_3",
                                       "ParkPath_1", "ParkPath_2"}


def test_destroy_list_is_exactly_the_unused_carriers():
    """The template copy carries four control actors the town does not need; they are the ones the
    brief names, and nothing else is destroyed."""
    assert T.DESTROY == ["Artery_3", "HighRise_Zone_2", "Lake_2", "ForestExclusion_2"]
    assert not set(T.DESTROY) & set(T.SPLINES)


def test_landmark_volumes_sit_over_their_landmarks():
    moves = T.VOLUME_MOVES
    assert set(moves) == {"PCG_2_1_MainTower_Footprint", "PCG_4_1_MainTower_Visuals",
                          "PCG_2_2_CentralPark_Footprint"}
    assert tuple(moves["PCG_2_1_MainTower_Footprint"]["xy"]) == T.MAIN_TOWER
    assert tuple(moves["PCG_4_1_MainTower_Visuals"]["xy"]) == T.MAIN_TOWER
    assert tuple(moves["PCG_2_2_CentralPark_Footprint"]["xy"]) == T.PARK_CENTER
    assert moves["PCG_2_2_CentralPark_Footprint"]["yaw"] == T.PARK_YAW
    # No parking-footprint move: ParkingFootprint is LeftOverLots (Task 25, decision 1).
    assert "PCG_3_2_2_LeftOverLots" not in moves
    # The tower's volume sits over its own spline zone; the park's over the park.
    assert T.inside(moves["PCG_2_1_MainTower_Footprint"]["xy"], T.HIGHRISE)
    assert T.inside(moves["PCG_2_2_CentralPark_Footprint"]["xy"], T.PARK_RECT)


def test_park_frame_is_the_volumes_yaw():
    """park(u, v) must be the frame of a rectangle turned by PARK_YAW about its centre -- the yaw the
    layout writes onto PCG_2_2_CentralPark_Footprint -- or stage 5's shape won't sit on the rect."""
    assert T.park(0, 0) == T.PARK_CENTER
    a = math.atan2(T.park(1000, 0)[1] - T.PARK_CENTER[1], T.park(1000, 0)[0] - T.PARK_CENTER[0])
    assert abs(math.degrees(a) - T.PARK_YAW) < 1e-9
    # Edges are the half-sizes: 2 * PARK_HALF wide and tall.
    edge = lambda p, q: math.hypot(p[0] - q[0], p[1] - q[1])
    assert abs(edge(T.PARK_RECT[0], T.PARK_RECT[1]) - 2 * T.PARK_HALF[0]) < 1e-6
    assert abs(edge(T.PARK_RECT[1], T.PARK_RECT[2]) - 2 * T.PARK_HALF[1]) < 1e-6


def test_bbox_is_the_layout_bbox():
    (x0, y0, z0), (x1, y1, z1) = T.city_bbox()
    (mx0, my0, _), (mx1, my1, _) = T.city_bbox(20000)
    assert (mx0, my0) == (x0 - 20000, y0 - 20000) and (mx1, my1) == (x1 + 20000, y1 + 20000)
    assert z0 < 0 < z1                            # spans the ground plane, as a volume's box must
    assert (x0, y0) == (min(p[0] for p in T.CITY), min(p[1] for p in T.CITY))
    assert (x1, y1) == (max(p[0] for p in T.CITY), max(p[1] for p in T.CITY))


def test_geometry_helpers_agree_with_brute_force():
    """inside/edge_distance/polyline_distance are the acceptance tests' rulers; check them on points
    whose answer is known by construction."""
    square = [(0, 0), (100, 0), (100, 100), (0, 100)]
    assert T.inside((50, 50), square) and not T.inside((150, 50), square)
    assert not T.inside((-1, 50), square)              # a vertex column is outside
    assert abs(T.edge_distance((50, 50), square) - 50) < 1e-9
    assert abs(T.edge_distance((0, 40), square) - 0) < 1e-9
    line = [(0, 0), (0, 100)]
    assert abs(T.polyline_distance((30, 50), line) - 30) < 1e-9
    assert abs(T.polyline_distance((-30, 150), line) - math.hypot(30, 50)) < 1e-9
    # crossings: a chord through the square crosses two edges, a segment inside crosses none.
    assert T.crossings([(-10, 50), (110, 50)], square) == 2
    assert T.crossings([(10, 10), (90, 90)], square) == 0


def test_stage_labels_are_unique_and_match_the_template_copy():
    """`bind` looks actors up by label; the labels are the stage table's, and no two stages share one."""
    labels = [T.STAGE_LABELS[n] for n in sorted(T.STAGE_LABELS)]
    assert len(labels) == len(set(labels)) == 18
    assert T.STAGE_LABELS[1] == "PCG_1_1_Terrain" and T.STAGE_LABELS[18] == "PCG_5_2_OuterForest"


def test_tag_carriers_are_the_ones_the_graphs_read():
    """The kept native nodes read these actor tags; each must name the control actors the town keeps,
    so an actor left unrenamed (or a tag lost in the copy) is caught offline."""
    assert T.TAGS["City"] == ["CityShape"]
    assert T.TAGS["Terrain_shaping_1"] == ["TerrainShaping"]
    assert T.TAGS["Arteries"] == ["Artery_1", "Artery_2"]
    assert T.TAGS["Highway"] == ["HighWay_2", "HighWay_3"]
    assert T.TAGS["HighRise"] == ["HighRise_Zone_1"]
    assert T.TAGS["LandmarkPark"] == ["MainTowerPark"]
    assert T.TAGS["LAKE"] == ["Lake_1"]
    assert T.TAGS["USER_SPLINE"] == ["ParkPath_1", "ParkPath_2"]
    assert T.TAGS["FOREST_EXCLUSION"] == ["ForestExclusion_1"]
    # Every carrier is an actor the town keeps: a spline it rewrites, or the terrain-shaping one.
    kept = set(T.SPLINES) | {"TerrainShaping"}
    assert all(a in kept for actors in T.TAGS.values() for a in actors)


def test_roads_come_from_the_splines_they_are_bound_to():
    """Stage 8 reads HighwaySpline2/3 (the raw splines), and the highway volumes publish roads by tag
    `Highway`. Both sides must be the same two lines, 30 m apart."""
    assert T.TAGS["Highway"] == [T.ROLE_LABELS["HighwaySpline2"], T.ROLE_LABELS["HighwaySpline3"]]
    a, b = T.SPLINES["HighWay_2"]["points"], T.SPLINES["HighWay_3"]["points"]
    assert a != b and len(a) == len(b)
    gap = T.polyline_distance(a[len(a) // 2][:2], [p[:2] for p in b])
    assert abs(gap - 3000) < 100


def test_the_town_does_not_touch_the_park_footprint_spline():
    """Stage 5 builds the park shape from the volume's RectWidth/RectLength and yaw (Task 13), so the
    volume's own 4-point spline is left as the copy brought it -- the layout must not rewrite it."""
    assert "PCG_2_2_CentralPark_Footprint" not in T.SPLINES
    assert "PCG_2_2_CentralPark_Footprint" not in T.DESTROY


# ---- the duplicated tables must not drift from their sources

def test_stage_labels_match_the_stage_table():
    assert T.STAGE_LABELS == {s[0]: s[1] for s in stages.STAGES}


def test_role_labels_match_the_official_profile():
    assert T.ROLE_LABELS == official.ROLE_LABELS


def test_bind_covers_every_role_the_ported_graphs_read():
    """What `bind` must write: the roles the slim graphs actually resolve. If a ported graph starts
    reading a role the town does not bind, the town build fails at `to_ir`, not at generation."""
    used = set()
    for n in [s[0] for s in stages.STAGES]:
        if not graphs.exists(n):
            continue
        out = graphs.graph(n).to_ir(official)
        used |= {r for site in out.get("sites", []) if site["kind"] == "role" for r in site["roles"]}
    assert used == set(official.ROLES) == set(T.ROLE_LABELS)
    assert len(used) == 13
