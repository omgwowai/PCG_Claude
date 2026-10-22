from pypcg.geo import Polygon, Spline
from pypcg.stages import w06_settlements as S
from pypcg.world import geom
from world_fixtures import run_stage, table, terrain

LOC_T = {"Id": "Int32", "Kind": "String", "Radius": "Double", "Slope": "Double"}
RT = {"RoadId": "Int32", "Class": "String", "Width": "Double", "Bridge": "Bool", "S": "Double"}


def _locs(rows):
    return table([{"loc": (x, y, 1000.0), "Id": i, "Kind": k, "Radius": r, "Slope": 0.0}
                  for i, (x, y, k, r) in enumerate(rows)], LOC_T, ["Location"])


def _road():
    return table([{"loc": (x, 0.0, 1000.0), "RoadId": 0, "Class": "Main", "Width": 800.0, "Bridge": False,
                   "S": x + 23000.0} for x in range(-23000, 23001, 500)], RT, ["Road", "Main"])


def _run(locs, seed=42):
    out, _ = run_stage(S, {"Terrain": [(terrain(lambda x, y: 1000.0 + 0.01 * y), frozenset())],
                           "Upstream": [_locs(locs), _road()]}, Seed=seed)
    return out


def test_village_follows_the_rules():
    out = _run([(0.0, 3000.0, "Village", 14000.0)])
    s = out["Summary"][0][0].values
    assert s["buildings"] >= 20 and s["village_min"] >= 20 and s["churches_min"] == 1
    assert s["overlaps"] == 0 and s["on_road"] == 0 and s["plazas"] == 1
    feet = [v for pin in ("FootprintsLow", "FootprintsMid", "FootprintsHigh", "FootprintsTower") for v, _t in out[pin]]
    assert len(feet) == s["buildings"] and all(isinstance(f, Spline) and f.closed and f.linear for f in feet)
    areas = [v for v, t in out["Areas"] if "Footprint" in t]
    assert all(isinstance(a, Polygon) for a in areas) and len(areas) == s["buildings"]
    assert len(out["Parts"][0][0]) > s["buildings"]


def test_two_close_settlements_never_overlap():
    out = _run([(-6000.0, 4000.0, "Town", 22000.0), (12000.0, -6000.0, "Village", 14000.0)])
    s = out["Summary"][0][0].values
    assert s["overlaps"] == 0 and s["on_road"] == 0 and s["buildings"] > 40


def test_same_seed_same_layout():
    a = _run([(0.0, 3000.0, "Village", 14000.0)], 7)
    b = _run([(0.0, 3000.0, "Village", 14000.0)], 7)
    assert [v.loc for v, _t in a["Buildings"]] == [v.loc for v, _t in b["Buildings"]]


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Summary"][0][0].values["buildings"] == 0
