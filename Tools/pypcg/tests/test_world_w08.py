from pypcg.geo import Polygon
from pypcg.stages import w08_props as S
from pypcg.world import geom
from world_fixtures import Surface, run_stage, table

RT = {"RoadId": "Int32", "Class": "String", "Width": "Double", "Bridge": "Bool", "S": "Double"}


def _road():
    return table([{"loc": (x, 0.0, 1000.0), "RoadId": 0, "Class": "Main", "Width": 800.0, "Bridge": False,
                   "S": x + 20000.0} for x in range(-20000, 20001, 500)], RT, ["Road", "Main"])


def _street():
    return table([{"loc": (x, 8000.0, 1000.0), "Width": 400.0, "S": float(x)} for x in range(0, 6001, 500)],
                 {"Width": "Double", "S": "Double"}, ["Street"])


def test_poles_wires_lamps_benches():
    plaza = (Polygon(geom.circle(0.0, -8000.0, 1800.0, 32), [], 1000.0), frozenset(["Plaza"]))
    out, _ = run_stage(S, {"Surface": [(Surface(lambda x, y: 1000.0), frozenset())],
                           "Upstream": [_road(), _street(), plaza]})
    s = out["Summary"][0][0].values
    assert s["poles"] == 11 and abs(s["pole_spacing_mean_m"] - 40.0) < 1e-6
    assert s["wire_segments"] == 10 * 2 * 16 and s["lamps"] == 3 and s["benches"] == 6 and s["rails"] == 0


def test_rails_where_the_road_is_on_an_embankment():
    out, _ = run_stage(S, {"Surface": [(Surface(lambda x, y: 1000.0 if abs(y) < 500.0 else 700.0), frozenset())],
                           "Upstream": [_road()]})
    assert out["Summary"][0][0].values["rails"] > 150


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Props"] == [] and out["Summary"][0][0].values["poles"] == 0
