import pytest

from fakes import FakeOps, FlatTerrain
from pypcg import geo, stage_api
from pypcg.geo import Points, Spline
from pypcg.stages import s00_probe as S


def inputs():
    vol = Points()
    vol.add((100.0, 200.0, 300.0))
    city = Spline([(0, 0, 0), (1000, 0, 0), (1000, 1000, 0)], closed=True,
                  polyline=[(0, 0, 0), (500, 0, 0), (1000, 0, 0), (1000, 1000, 0)])
    return {"Volume": [(vol, frozenset())], "Terrain": [(FlatTerrain(55.0), frozenset())],
            "Spline": [(city, frozenset({"City"}))], "Empty": []}


def test_probe_writes_every_kind_of_value():
    out, _ = stage_api.execute(S, inputs(), stage_api.defaults(S), FakeOps())
    area = out["Area"][0][0]
    assert geo.area_m2(area) == pytest.approx((10000.0 ** 2 - 2500.0 ** 2) / 1e4) and len(area.holes) == 1
    assert out["Line"][0][0].closed and len(out["Line"][0][0].points) == 4
    pts = out["Points"][0][0]
    assert len(pts) == 3 and pts.attrs["Mesh"] == ["/Engine/BasicShapes/Cube.Cube"] * 3 and pts.attrs["Weight"] == [0.0, 0.5, 1.0]
    assert out["Params"][0][0].values == {"A": 1.5, "Name": "x"}
    assert len(out["Bench"][0][0]) == 0


def test_probe_reports_what_it_read():
    out, _ = stage_api.execute(S, inputs(), dict(stage_api.defaults(S), BenchPoints=2500), FakeOps())
    r = out["Report"][0][0].values
    assert r["TerrainZ"] == 55.0 and r["SplineCount"] == 1 and r["SplineControl"] == 3 and r["SplinePolyline"] == 4
    assert r["SplineClosed"] is True and r["EmptyCount"] == 0 and r["Label"] == "probe" and r["Version"] == S.VERSION
    assert len(out["Bench"][0][0]) == 2500
