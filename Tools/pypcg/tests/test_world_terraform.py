from pypcg.geo import ParamSet, Points
from pypcg.world import WORLD_HALF_CM, layout as L, points as WP, terraform as T
from pypcg.world.grid import Lattice


def _flat(z=1000.0, n=41, s=100.0):
    return Lattice(n, s, -2000.0, -2000.0, [z] * (n * n))


def test_carve_only_lowers_and_reaches_bed():
    lat = _flat()
    river = [(-2000.0, 0.0, 900.0, 600.0), (2000.0, 0.0, 900.0, 600.0)]
    n = T.carve_river(lat, river, depth=150.0)
    assert n > 0 and abs(lat.z[lat.nearest(0.0, 0.0)] - 750.0) < 1e-9
    assert lat.z[lat.nearest(0.0, 1900.0)] == 1000.0 and max(v for v in lat.z) == 1000.0


def test_corridor_flattens_and_skips_bridges():
    lat = _flat()
    T.flatten_corridor(lat, [(-2000.0, 0.0, 1200.0, 300.0, False), (0.0, 0.0, 1200.0, 300.0, False)], 100.0, 300.0)
    assert lat.z[lat.nearest(-1000.0, 300.0)] == 1200.0
    assert lat.z[lat.nearest(-1000.0, 1000.0)] == 1000.0
    lat2 = _flat()
    T.flatten_corridor(lat2, [(-2000.0, 0.0, 1200.0, 300.0, True), (0.0, 0.0, 1200.0, 300.0, True)])
    assert max(lat2.z) == 1000.0


def test_plane_fit_is_clamped_and_platform_pad():
    lat = Lattice(41, 100.0, -2000.0, -2000.0, [0.0] * 1681)
    for k in range(1681):
        lat.z[k] = 0.5 * lat.xy(k)[0]
    a, b, c = T.fit_plane(lat, 0.0, 0.0, 1000.0, 4.0)
    assert abs(a - 0.0699268119) < 1e-6 and abs(b) < 1e-12 and abs(c) < 1e-6
    T.platform(lat, 0.0, 0.0, 1000.0, (a, b, c))
    assert abs(lat.z[lat.nearest(500.0, 0.0)] - a * 500.0) < 1e-9
    ring = [(-100.0, -100.0), (100.0, -100.0), (100.0, 100.0), (-100.0, 100.0)]
    T.pad(lat, ring, 77.0)
    assert lat.z[lat.nearest(0.0, 0.0)] == 77.0 and lat.z[lat.nearest(300.0, 0.0)] == 77.0


def test_points_helpers():
    src = Points()
    src.declare("SourcePositions", "Vector")
    src.add((0.0, 0.0, 5.0), SourcePositions=(0.0, 0.0, -600.0))
    lat, ks = Lattice.from_locs(src.loc, 100.0)
    lat.z[ks[0]] = 9.0
    out = WP.with_heights(src, lat, ks, {"Mountain": ("Double", [0.5])})
    assert out.loc[0] == (0.0, 0.0, 9.0) and out.attrs["SourcePositions"][0] == (0.0, 0.0, -600.0)
    assert out.attrs["Mountain"] == [0.5] and src.loc[0][2] == 5.0
    m = WP.mesh_points([((1.0, 2.0, 3.0), (0.0, 90.0, 0.0), (2.0, 2.0, 2.0), "/A/B.B")])
    assert m.types[WP.MESH_ATTR] == "SoftObjectPath" and m.attrs["Mesh"] == ["/A/B.B"] and m.rot[0][1] == 90.0
    t = WP.table_points([{"loc": (0.0, 0.0, 0.0), "Kind": "Town", "Radius": 1.0}], {"Kind": "String", "Radius": "Double"})
    assert WP.rows_of(t)[0]["Kind"] == "Town"
    s = WP.summary({"a": 1, "b": 2.0, "c": True, "d": "x"})
    assert isinstance(s, ParamSet) and s.types == {"a": "Int32", "b": "Double", "c": "Bool", "d": "String"}


def test_layout_is_inside_the_world():
    pts = L.valley_points()
    assert all(b[1] > a[1] for a, b in zip(pts, pts[1:]))
    assert L.floor_z(-150000.0) == -800.0 and L.floor_z(0.0) == 2500.0
    for _n, x, y, r in L.LOCATIONS:
        assert abs(x) + r < WORLD_HALF_CM and abs(y) + r < WORLD_HALF_CM
    assert len(L.LOCATIONS) == 5 and len(L.RIVER_ENDS) == 2 and len(L.ROAD_EXITS) == 2
