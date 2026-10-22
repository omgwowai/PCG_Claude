from pypcg.stages import w03_river as S
from world_fixtures import run_stage, table, terrain


def valley(x, y):
    return 1000.0 + 0.02 * y + 0.0004 * x * x / 100.0          # a trough along x = 0 falling to the south


def _ends(sx, sy, ox, oy):
    return table([{"loc": (sx, sy, 0.0), "Role": "Source"}, {"loc": (ox, oy, 0.0), "Role": "Outlet"}],
                 {"Role": "String"}, ["RiverEnd"])


def test_river_follows_the_trough_and_carves():
    src = terrain(valley)
    out, _ = run_stage(S, {"Terrain": [(src, frozenset())], "Upstream": [_ends(2000.0, 20000.0, -2000.0, -20000.0)]})
    s = out["Summary"][0][0].values
    assert s["length_m"] >= 380.0 and s["monotone"] and s["carved"] > 0
    rows = S.river_rows(out["River"])
    assert max(abs(r[0]) for r in rows[3:-3]) < 6000.0 + 2500.0      # within the meander amplitude
    assert abs(rows[0][3] - 600.0) < 1e-6 and abs(rows[-1][3] - 2000.0) < 1e-6
    before = {p[:2]: p[2] for p in src.loc}
    after = out["Terrain"][0][0]
    assert len(after) == len(src) and all(p[2] <= before[p[:2]] + 1e-9 for p in after.loc)
    assert len(out["Water"][0][0]) == len(rows) - 1


def test_unreachable_outlet():
    src = terrain(valley)
    out, _ = run_stage(S, {"Terrain": [(src, frozenset())], "Upstream": [_ends(0.0, 20000.0, 900000.0, 0.0)]})
    assert out["Summary"][0][0].values["length_m"] == 0.0 and out["River"] == []
    assert [p[2] for p in out["Terrain"][0][0].loc] == [p[2] for p in src.loc]


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Terrain"] == [] and out["Summary"][0][0].values["length_m"] == 0.0


def test_water_planes_follow_the_falling_water_line():
    """Flat planes on a falling river make a staircase; each plane tilts with the water line under it."""
    import math
    src = terrain(valley)
    out, _ = run_stage(S, {"Terrain": [(src, frozenset())], "Upstream": [_ends(2000.0, 20000.0, -2000.0, -20000.0)]})
    rows = S.river_rows(out["River"])
    water = out["Water"][0][0]
    for i, rot in enumerate(water.rot):
        a, b = rows[i], rows[i + 1]
        want = math.degrees(math.atan2(b[2] - a[2], math.hypot(b[0] - a[0], b[1] - a[1])))
        assert abs(rot[0] - want) < 1e-9


def test_river_meanders_on_a_flat_floor():
    """On a valley floor with no fall across it, the river wanders (视频：自然的轨迹) instead of running down one grid
    column: sinuosity (length / straight distance) of at least 1.05."""
    import math
    flat = lambda x, y: 1000.0 + 0.02 * y
    out, _ = run_stage(S, {"Terrain": [(terrain(flat), frozenset())], "Upstream": [_ends(0.0, 21000.0, 0.0, -21000.0)]},
                       MeanderLength=12000.0, MeanderAmplitude=4000.0)   # the test lattice is only 470 m across
    rows = S.river_rows(out["River"])
    chord = math.hypot(rows[-1][0] - rows[0][0], rows[-1][1] - rows[0][1])
    assert rows[-1][5] / chord >= 1.05, rows[-1][5] / chord
