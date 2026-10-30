"""PyInterior single-floor regression (multi-storey plan, Task 1): the stage's Parts for the demo houses and a few sweep
footprints, as digests recorded on main 9252cb7 before the multi-storey work. Multi-storey changes must leave every
single-floor house exactly as it was (spec 2026-10-29 §1.4)."""
import hashlib
import math

import pytest

from pypcg import stage_api
from pypcg.geo import Points, Spline
from pypcg.interior import demo
from pypcg.stages import i01_house

GOLDEN = {
    "House_01_Studio": "8b9ff3f9a1569d12d7b3b7598e02e766b0dd7ffe",
    "House_02_OneBed": "09a73fcf5a1c5f980c5f9476ebccb6cd3862a5bc",
    "House_03_TwoBed": "ad0095e2501f91ac1ed47b47077ba3b748e0a45a",
    "House_04_ThreeBed": "5a0cef06de33f53559b38371e3dea211dad2f4f2",
    "House_05_LShape": "c5ace5fd66ae37e99d3f3f1bce9ec0bcbdd9b107",
    "House_06_TShape": "b9de6fbf76997e6be4c7023bf0602198b03aede0",
    "House_07_UShape": "166918b5bed2226671e874e68850d01211032d63",
    "House_08_FourBed": "c9bc16e24c7006de0a4551e0533569a4fad1527f",
    "sweep-rect500x450-1": "7148f3aeb4147c73d13a00a8affd1a724a9da288",
    "sweep-rect500x450-2": "578383801da305ddb858644f8ebb082f5226efda",
    "sweep-rect900x600-1": "d7ee8840dc8f10c1e442b6279d88dd2bb6187475",
    "sweep-rect900x600-2": "df0926b881868e79fa6c5f6f7b7246d9fe675a1d",
    "sweep-rect1200x800-1": "7f1f3e7401b2f206f6fa6f7480c8ba2f02022d5e",
    "sweep-rect1200x800-2": "9a4d977a511fea9456ce6ee55b0367ddecbad403",
    "sweep-rect1500x1000-1": "316540ddf717a452471ffbcff09399910b5c3ade",
    "sweep-rect1500x1000-2": "d2f0cf5670e6c5ea51d5bdea00100fa5987c1f78",
    "sweep-lshape-1": "d66221dccbba9e92fccf830be382746973108bf7",
    "sweep-lshape-2": "13dd6a065a827070d9bb802c62eb58b11140fe29",
    "sweep-ushape-1": "acf4ec3d50606c239df985b9269f6cac3c9cd249",
    "sweep-ushape-2": "5133d9ae308cf100dd0b926fa1304da827426a8d",
}
SWEEP = {"rect500x450": [(0, 0), (500, 0), (500, 450), (0, 450)], "rect900x600": [(0, 0), (900, 0), (900, 600), (0, 600)],
         "rect1200x800": [(0, 0), (1200, 0), (1200, 800), (0, 800)],
         "rect1500x1000": [(0, 0), (1500, 0), (1500, 1000), (0, 1000)],
         "lshape": demo.SHAPES["lshape"], "ushape": demo.SHAPES["ushape"]}


def digest(out):
    p = out["Parts"][0][0]
    rows = [(tuple(round(v, 3) for v in p.loc[i]), tuple(round(v, 3) for v in p.rot[i]),
             tuple(round(v, 4) for v in p.scale[i]), p.attrs["Mesh"][i], p.attrs["Mat0"][i]) for i in range(len(p))]
    return hashlib.sha1(repr(rows).encode()).hexdigest()


def inputs_local(local, loc, yaw):
    """The stage's inputs for a house actor at `loc` turned `yaw` whose one spline is the local outline `local`."""
    a = math.radians(yaw)
    ex, ey = (-math.sin(a), math.cos(a)), (-math.cos(a), -math.sin(a))
    pts = [(loc[0] + x * ex[0] + y * ey[0], loc[1] + x * ex[1] + y * ey[1], loc[2]) for x, y in local]
    vol = Points()
    vol.add(tuple(loc), rot=(0.0, yaw, 0.0), scale=(1.0, 1.0, 1.0))
    return {"Footprint": [(Spline(pts, closed=True, linear=True), [])], "Volume": [(vol, [])]}


@pytest.mark.parametrize("name, shape, loc, yaw, style, seed", demo.houses())
def test_single_floor_houses_are_unchanged(name, shape, loc, yaw, style, seed):
    out, _ctx = stage_api.execute(i01_house, inputs_local(demo.SHAPES[shape], loc, yaw),
                                  dict(stage_api.defaults(i01_house), Style=style, Seed=seed), None)
    assert digest(out) == GOLDEN[name]


@pytest.mark.parametrize("key, seed", [(k, s) for k in SWEEP for s in (1, 2)])
def test_single_floor_sweep_is_unchanged(key, seed):
    out, _ctx = stage_api.execute(i01_house, inputs_local(SWEEP[key], (300.0, -200.0, 0.0), 30.0),
                                  dict(stage_api.defaults(i01_house), Seed=seed), None)
    assert digest(out) == GOLDEN["sweep-%s-%d" % (key, seed)]
