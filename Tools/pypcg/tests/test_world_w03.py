import math

from pypcg.geo import Mesh
from pypcg.stages import w03_river as S
from pypcg.world import VERTEX_CM, geom, shape
from pypcg.world.grid import Lattice
from world_fixtures import run_stage, table, terrain

LOC_T = {"Id": "Int32", "Kind": "String", "Radius": "Double", "Slope": "Double"}


def valley(x, y):
    return 1000.0 + 0.02 * y + 0.0004 * x * x / 100.0          # a trough along x = 0 falling to the south


def _ends(sx, sy, ox, oy):
    return table([{"loc": (sx, sy, 0.0), "Role": "Source"}, {"loc": (ox, oy, 0.0), "Role": "Outlet"}],
                 {"Role": "String"}, ["RiverEnd"])


def _run(fn=valley, half=60, ends=(0.0, 33000.0, 0.0, -33000.0), extra=(), **params):
    src = terrain(fn, half)
    out, _ = run_stage(S, {"Terrain": [(src, frozenset())], "Upstream": [_ends(*ends)] + list(extra)}, **params)
    return src, out


def test_river_follows_the_trough_and_carves():
    src, out = _run()
    s = out["Summary"][0][0].values
    assert s["length_m"] >= 600.0 and s["monotone"] and s["carved"] > 0
    rows = S.river_rows(out["River"])
    assert max(abs(r[0]) for r in rows) < 8000.0                    # the meanders stay in the trough
    assert abs(rows[0][3] - 600.0) < 1e-6 and abs(rows[-1][3] - 2000.0) < 1e-6
    before = {p[:2]: p[2] for p in src.loc}
    after = out["Terrain"][0][0]
    assert len(after) == len(src) and all(p[2] <= before[p[:2]] + 1e-9 for p in after.loc)


def test_the_river_runs_from_source_to_outlet_without_crossing_itself():
    _src, out = _run()
    rows = S.river_rows(out["River"])
    assert geom.dist2d(rows[0], (0.0, 33000.0)) < 1200.0 and geom.dist2d(rows[-1], (0.0, -33000.0)) < 1200.0
    assert all(b[2] <= a[2] + 1e-9 for a, b in zip(rows, rows[1:]))           # the water line never rises
    assert all(abs(b[5] - a[5] - S.ROW_CM) < 0.03 * S.ROW_CM for a, b in zip(rows, rows[1:]))
    assert not geom.self_intersects([r[:2] for r in rows])


def test_the_river_meanders_in_round_bends():
    """用户：水的形状应该更圆润，不应该有那么多直线. Sine-generated (Kinoshita) bends: almost nothing straighter than a
    1.5 km radius, no kink (heading change per 5 m under 15 degrees: no bend under a 19 m radius), clearly sinuous."""
    _src, out = _run(half=90, ends=(0.0, 50000.0, 0.0, -50000.0))
    rows = S.river_rows(out["River"])
    st = shape.stats([r[:2] for r in rows])
    assert st["straight_share"] < 0.15 and st["max_turn_deg"] < 15.0 and st["sinuosity"] >= 1.2, st
    s = out["Summary"][0][0].values
    assert abs(s["straight_share"] - st["straight_share"]) < 1e-9 and s["bends"] >= 6


def test_bends_are_as_tight_as_natural_ones_and_no_tighter():
    """Natural meanders turn at 2-3 channel widths (Leopold & Wolman): no bend under 1.5 widths."""
    _src, out = _run(half=90, ends=(0.0, 50000.0, 0.0, -50000.0))
    rows = S.river_rows(out["River"])
    k = shape.curvature([r[:2] for r in rows])
    assert min(1.0 / max(abs(c), 1e-12) / r[3] for c, r in zip(k[2:-2], rows[2:-2])) >= 1.5


def test_width_varies_wider_in_the_bends():
    _src, out = _run()
    rows = S.river_rows(out["River"])
    total = rows[-1][5]
    ratio = [r[3] / (600.0 + 1400.0 * r[5] / total) for r in rows]
    m = sum(ratio) / len(ratio)
    assert math.sqrt(sum((x - m) ** 2 for x in ratio) / len(ratio)) >= 0.05
    bend = [x for x, r in zip(ratio, rows) if abs(r[6]) * 2.5 * r[3] > 0.5]
    cross = [x for x, r in zip(ratio, rows) if abs(r[6]) * 2.5 * r[3] < 0.2]
    assert bend and cross and sum(bend) / len(bend) > sum(cross) / len(cross)


def test_bends_have_a_point_bar_inside_and_a_cut_bank_outside():
    _src, out = _run()
    rows = S.river_rows(out["River"])
    lat, _ks = Lattice.from_locs(out["Terrain"][0][0].loc, VERTEX_CM)
    inner, outer = [], []
    for i in range(1, len(rows) - 1):
        x, y, water, wd, bed, s, curv, bar = rows[i]
        if abs(curv) * 2.5 * wd < 0.6:
            continue
        assert bar > 0.0 and bed < water - S.PARAMS["Depth"].default * 0.8 + 1e-6
        dx, dy = rows[i + 1][0] - rows[i - 1][0], rows[i + 1][1] - rows[i - 1][1]
        ln = math.hypot(dx, dy)
        side = 1.0 if curv > 0 else -1.0                       # turning left: the centre of the bend is on the left
        nx, ny = -dy / ln * side, dx / ln * side
        d = 0.5 * wd + 400.0
        inner.append(lat.height(x + nx * d, y + ny * d) - water)
        outer.append(lat.height(x - nx * d, y - ny * d) - water)
    assert len(inner) >= 10
    assert sum(inner) / len(inner) < sum(outer) / len(outer) - 20.0


def test_the_water_is_one_continuous_surface_over_the_channel():
    """One mesh along the whole river instead of a stretched plane per 10 m (straight edges, steps): cross sections
    every 5 m, wider than the water so its edge tucks under the banks, lying on the water line."""
    _src, out = _run()
    rows = S.river_rows(out["River"])
    water = out["Water"]
    assert len(water) == 1 and isinstance(water[0][0], Mesh)
    m, n = water[0][0], S.CROSS
    assert len(m.vertices) == n * len(rows) and len(m.triangles) == 2 * (n - 1) * (len(rows) - 1)
    for a, b, c in m.triangles:
        (ax, ay, _), (bx, by, _), (cx, cy, _) = m.vertices[a], m.vertices[b], m.vertices[c]
        assert (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) < 0.0     # the winding the engine draws from above
    for i, r in enumerate(rows):
        assert geom.dist2d(m.vertices[i * n], m.vertices[i * n + n - 1]) >= r[3] + 100.0
        assert all(abs(m.vertices[i * n + j][2] - r[2] - S.SURFACE_LIFT) < 1e-6 for j in range(n))
    assert len(m.uvs) == len(m.colors) == len(m.normals) == len(m.vertices)
    assert m.material == S.WATER_MATERIAL


def test_river_keeps_out_of_town_centres():
    village = table([{"loc": (2500.0, 0.0, 1000.0), "Id": 0, "Kind": "Village", "Radius": 9000.0, "Slope": 0.0}],
                    LOC_T, ["Location"])
    _src, out = _run(extra=[village])
    rows = S.river_rows(out["River"])
    assert min(geom.dist2d(r, (2500.0, 0.0)) for r in rows) >= 4500.0


def test_unreachable_outlet():
    src = terrain(valley)
    out, _ = run_stage(S, {"Terrain": [(src, frozenset())], "Upstream": [_ends(0.0, 20000.0, 900000.0, 0.0)]})
    assert out["Summary"][0][0].values["length_m"] == 0.0 and out["River"] == [] and out["Water"] == []
    assert [p[2] for p in out["Terrain"][0][0].loc] == [p[2] for p in src.loc]


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Terrain"] == [] and out["Summary"][0][0].values["length_m"] == 0.0


def bend_lengths(rows):
    """Channel length between consecutive inflections (where the curvature changes sign)."""
    k = shape.curvature([r[:2] for r in rows])
    cuts = [i for i in range(1, len(k)) if (k[i - 1] < 0.0) != (k[i] < 0.0)]
    return [rows[b][5] - rows[a][5] for a, b in zip(cuts, cuts[1:])]


def test_meanders_are_irregular():
    """用户：不要太均匀、太规则. Every bend draws its own wavelength and angle: the bends' lengths vary by 20 % or more
    (a sine-like river with one wavelength would be under 5 %)."""
    _src, out = _run(half=90, ends=(0.0, 50000.0, 0.0, -50000.0))
    lengths = bend_lengths(S.river_rows(out["River"]))
    m = sum(lengths) / len(lengths)
    assert len(lengths) >= 6 and math.sqrt(sum((x - m) ** 2 for x in lengths) / len(lengths)) / m >= 0.2, lengths


def test_the_course_wanders_across_a_flat_floor():
    """On a flat valley floor the base line drifts across it at a large scale (the meander belt wanders) instead of
    running down the valley's centre line: the river's mean position differs between the upper and the lower half."""
    flat = lambda x, y: 1000.0 + 0.02 * y + (0.0004 * (abs(x) - 15000.0) ** 2 / 100.0 if abs(x) > 15000.0 else 0.0)
    _src, out = _run(fn=flat, half=90, ends=(0.0, 50000.0, 0.0, -50000.0))
    rows = S.river_rows(out["River"])
    half = len(rows) // 2
    upper = sum(r[0] for r in rows[:half]) / half
    lower = sum(r[0] for r in rows[half:]) / (len(rows) - half)
    assert abs(upper - lower) > 1500.0 or max(abs(upper), abs(lower)) > 1500.0, (upper, lower)
