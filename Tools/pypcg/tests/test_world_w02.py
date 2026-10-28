from pypcg.geo import Points
from pypcg.stages import w02_locations as S
from pypcg.world import rules
from world_fixtures import Surface, run_stage


def _actors(rows):
    p = Points()
    for x, y, sc in rows:
        p.add((x, y, 0.0), scale=(sc, sc, 1.0))
    return [(p, frozenset())]


def bowl(x, y):
    return 0.0005 * ((x - 3000.0) ** 2 + y ** 2) / 100.0        # flattest at (3000, 0)


def test_snaps_to_flat_ground_and_classifies():
    out, _ = run_stage(S, {"Locations": _actors([(0.0, 0.0, 2.2), (20000.0, 0.0, 0.7)]),
                           "RiverEnds": _actors([(0.0, 9000.0, 1.0), (0.0, -9000.0, 1.0)]),
                           "Exits": _actors([(5000.0, 9000.0, 1.0), (5000.0, -9000.0, 1.0)]),
                           "Surface": [(Surface(lambda x, y: bowl(x, y) + y * 0.001), frozenset())]})
    locs = out["Locations"][0][0]
    assert locs.attrs["Kind"] == ["Town", "Hamlet"] and locs.attrs["Radius"][0] == 22000.0
    assert abs(locs.loc[0][0] - 3000.0) <= 1500.0
    assert out["RiverEnds"][0][0].attrs["Role"] == ["Outlet", "Source"]     # sorted by y: the south end is lower
    s = out["Summary"][0][0].values
    assert (s["locations"], s["river_ends"], s["exits"], s["off_terrain"]) == (2, 2, 2, 0)
    assert rules.kind_of(14000.0) == "Village"


def test_location_off_terrain():
    out, _ = run_stage(S, {"Locations": _actors([(90000.0, 0.0, 1.0)]),
                           "Surface": [(Surface(lambda x, y: 0.0, half_cm=20000.0), frozenset())]})
    locs = out["Locations"][0][0]
    assert locs.loc[0][:2] == (90000.0, 0.0) and locs.attrs["Slope"] == [-1.0]
    assert out["Summary"][0][0].values["off_terrain"] == 1


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Summary"][0][0].values["locations"] == 0
