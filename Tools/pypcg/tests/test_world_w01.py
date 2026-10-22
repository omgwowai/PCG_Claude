import math

from pypcg.geo import Spline
from pypcg.stages import w01_terrain as S
from world_fixtures import run_stage, terrain

VALLEY = [(Spline([(0.0, -30000.0, 1000.0), (0.0, 30000.0, 1000.0)], linear=True), frozenset(["PyWorld_Valley"]))]
SMALL = dict(FloorHalfWidth=3000.0, WallWidth=8000.0, RidgeHeight=6000.0, EdgeStart=18000.0, EdgeEnd=23000.0)


def _run(**p):
    src = terrain(lambda x, y: -600.0)
    out, _ = run_stage(S, {"MeshTerrain": [(src, frozenset())], "Valley": VALLEY}, **p)
    return src, out


def test_shape_keeps_vertices_and_rises_from_the_floor():
    src, out = _run(**SMALL)
    t = out["Terrain"][0][0]
    assert len(t) == len(src) and t.attrs["SourcePositions"] == src.attrs["SourcePositions"]
    assert [p[:2] for p in t.loc] == [p[:2] for p in src.loc]
    z = {(round(p[0]), round(p[1])): p[2] for p in t.loc}
    m = t.attrs["Mountain"]
    assert 0.0 <= min(m) and max(m) <= 1.0 and t.types["Mountain"] == "Double"
    assert abs(z[(0, 0)] - 1000.0) < 300.0
    assert z[(11719, 0)] > z[(0, 0)] + 2500.0
    assert abs(z[(23438, 23438)] - (-600.0)) < 1e-6          # past EdgeEnd: the sea floor
    s = out["Summary"][0][0].values
    assert s["points"] == len(src) and s["nan"] == 0 and s["floor_err_max_cm"] < 400.0


def test_seed_changes_the_noise_only():
    _, a = _run(Seed=1, **SMALL)
    _, b = _run(Seed=2, **SMALL)
    _, c = _run(Seed=1, **SMALL)
    za, zb, zc = ([p[2] for p in o["Terrain"][0][0].loc] for o in (a, b, c))
    assert za == zc and za != zb


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Terrain"] == [] and out["Summary"][0][0].values["points"] == 0
