import math

from pypcg.world import hydro, noise
from pypcg.world.grid import Lattice


def test_noise_ranges_and_determinism():
    vals = [noise.value(x * 0.37, x * 0.61, 3) for x in range(400)]
    assert 0.0 <= min(vals) and max(vals) <= 1.0
    assert noise.value(1.3, 2.7, 3) == noise.value(1.3, 2.7, 3) != noise.value(1.3, 2.7, 4)
    assert abs(noise.value(5.0, 5.0, 1) - noise.value(5.0 + 1e-7, 5.0, 1)) < 1e-5
    f = [noise.fbm(x * 0.13, -x * 0.29, 9) for x in range(400)]
    r = [noise.ridged(x * 0.13, x * 0.07, 9) for x in range(400)]
    assert -1.0 <= min(f) and max(f) <= 1.0 and 0.0 <= min(r) and max(r) <= 1.0


def _lat(fn, n=11, s=100.0):
    locs = [(i * s - 500.0, j * s - 500.0, fn(i * s - 500.0, j * s - 500.0)) for j in range(n) for i in range(n)]
    return Lattice.from_locs(locs, s)


def test_lattice_roundtrip_seams_and_height():
    locs = [(0.0, 0.0, 1.0), (100.0, 0.0, 2.0), (0.0, 100.0, 3.0), (100.0, 100.0, 4.0), (100.0, 0.0, 2.0)]
    lat, ks = Lattice.from_locs(locs, 100.0)
    assert lat.n == 2 and ks[1] == ks[4]
    assert lat.height(50.0, 50.0) == 2.5
    assert lat.height(500.0, 0.0) is None
    assert lat.xy(ks[3]) == (100.0, 100.0)


def test_slope_and_coarse():
    lat, _ = _lat(lambda x, y: 0.5 * x)
    k = lat.nearest(0.0, 0.0)
    assert abs(lat.slope_deg(k) - math.degrees(math.atan(0.5))) < 1e-9
    co = lat.coarse(2, 400.0)
    assert co.n == 5 and co.s == 200.0 and co.xy(co.nearest(0.0, 0.0)) == (0.0, 0.0)
    assert sum(1 for _ in lat.cells_in_box(-100.0, -100.0, 100.0, 100.0)) == 9


def test_min_filter_and_flow():
    lat, _ = _lat(lambda x, y: abs(x) + 0.01 * y)          # a V valley draining towards -y
    m = hydro.min_filter(lat, 1)
    k = lat.nearest(200.0, 0.0)
    assert m[k] == min(lat.z[lat.nearest(x, y)] for x in (100.0, 200.0, 300.0) for y in (-100.0, 0.0, 100.0))
    acc = hydro.flow_accumulation(lat)
    assert acc.index(max(acc)) == lat.nearest(0.0, -500.0)
