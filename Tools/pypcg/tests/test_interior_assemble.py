"""PyInterior assembly: walls without overlaps, openings cut, floors, paint, doors, windows, furniture (spec §4.8)."""
import math
import random

import pytest

from pypcg.interior import assemble as A
from pypcg.interior import doors as D
from pypcg.interior import furnish as FU
from pypcg.interior import layout as L
from pypcg.interior import openings as O
from pypcg.interior import program as P

from test_interior_layout import SWEEP, fp_of


def house(pts, seed=1, yaw=0.0, params=None):
    fp = fp_of(pts, yaw)
    rng = random.Random(seed)
    plan = L.plan(fp, P.choose(fp.area_m2), rng)
    doors = D.connect(plan, rng)
    wins = O.windows(plan, doors, rng)
    places, _fails = FU.furnish(plan, doors, wins, rng)
    return fp, plan, doors, wins, places, A.house(plan, doors, wins, places, dict(A.DEFAULTS, **(params or {})),
                                                  random.Random(seed))


@pytest.mark.parametrize("k", range(0, len(SWEEP), 3))
def test_wall_band_tiles_the_outline_band(k):
    fp = fp_of(SWEEP[k])
    segs = fp.segments()
    band = A.wall_band(segs, 25.0)
    for i, (a, _s) in enumerate(band):
        for b, _t in band[i + 1:]:
            assert not a.overlaps(b)
    perim = sum(s.length for s in segs)
    assert sum(r.area for r, _s in band) == pytest.approx(perim * 25.0 - 4 * 25.0 ** 2)


@pytest.mark.parametrize("k", range(0, len(SWEEP), 4))
def test_walls_never_overlap(k):
    fp, plan, doors, wins, places, inst = house(SWEEP[k])
    walls = A.wall_plan(plan, doors, wins)
    rects = [(r, kind) for r, kind, _axis, _c in walls]
    for i, (a, ka) in enumerate(rects):
        for b, kb in rects[i + 1:]:
            assert not a.overlaps(b), (ka, kb, a, b)
    # interior walls stay inside the band's inner face
    band = [r for r, kind in rects if kind == "ext"]
    for r, kind in rects:
        if kind == "int":
            assert not any(r.overlaps(b) for b in band)


def test_openings_are_cut_out_of_the_walls():
    fp, plan, doors, wins, places, inst = house([(0, 0), (1300, 0), (1300, 900), (0, 900)])
    boxes = [i for i in inst if i["role"] in ("wall", "paint")]
    for d in doors:
        lo, hi = d.s0 + 1.0, d.s1 - 1.0
        for b in boxes:
            r, z0, z1 = b["local"]
            on = (d.axis == "x" and r.x0 - 1 <= d.c <= r.x1 + 1) or (d.axis == "y" and r.y0 - 1 <= d.c <= r.y1 + 1)
            if not on:
                continue
            a0, a1 = (r.y0, r.y1) if d.axis == "x" else (r.x0, r.x1)
            if a0 < hi and lo < a1:
                assert z0 >= D.DOOR_H - 1e-6, (d.kind, b["role"], r, z0, z1)
    for w in wins:
        lo, hi = w.s0 + 1.0, w.s1 - 1.0
        for b in boxes:
            r, z0, z1 = b["local"]
            on = (w.axis == "x" and r.x0 - 1 <= w.c <= r.x1 + 1) or (w.axis == "y" and r.y0 - 1 <= w.c <= r.y1 + 1)
            if not on:
                continue
            a0, a1 = (r.y0, r.y1) if w.axis == "x" else (r.x0, r.x1)
            if a0 < hi and lo < a1:
                assert z1 <= w.sill + 1e-6 or z0 >= w.sill + w.height - 1e-6, (b["role"], r, z0, z1, w)


def test_one_floor_per_room_and_furniture_parts():
    fp, plan, doors, wins, places, inst = house([(0, 0), (1050, 0), (1050, 800), (0, 800)])
    floors = [i for i in inst if i["role"] == "floor"]
    assert len(floors) == len(plan.rooms)
    furn = [i for i in inst if i["role"].startswith("furniture")]
    # every part of every placed piece (its StarterContent recipe when it has one: RealMeshes is on by default)
    assert len(furn) == sum(len(A.C.ITEMS[p.item].mesh or A.C.ITEMS[p.item].parts) for p in places)
    for i in inst:
        assert i["mesh"].startswith("/") and (i["mat"] == "" or i["mat"].startswith("/Game/"))
        assert all(s > 0 for s in i["scale"])


def test_wall_cut_lowers_every_wall():
    *_rest, inst = house([(0, 0), (1050, 0), (1050, 800), (0, 800)], params={"WallCut": 120.0})
    for i in inst:
        if i["role"] in ("wall", "paint", "door", "window"):
            assert i["local"][2] <= 120.0 + 1e-6, i["role"]


@pytest.mark.parametrize("params, top", [({}, D.DOOR_H), ({"WallCut": 120.0}, 120.0)])
def test_a_sliding_door_is_drawn_closed_in_its_opening(params, top):
    """A wet room's door slides (it never swings into the floor), and it is drawn closed: a leaf between the frames inside
    the wall, so the bathroom visibly has a door (review finding 3); clipped to lowered walls like every leaf."""
    fp, plan, doors, wins, places, inst = house([(0, 0), (1050, 0), (1050, 800), (0, 800)], params=params)
    sliding = [d for d in doors if d.sliding]
    assert sliding
    t = plan.walls["int"]
    for d in sliding:
        found = []
        for i in inst:
            if i["role"] != "door":
                continue
            r, z0, z1 = i["local"]
            (a0, a1), (b0, b1) = ((r.y0, r.y1), (r.x0, r.x1)) if d.axis == "x" else ((r.x0, r.x1), (r.y0, r.y1))
            if a0 <= d.s0 + A.FRAME + 1e-6 and a1 >= d.s1 - A.FRAME - 1e-6 and d.c - t / 2 - 1e-6 <= b0 and \
                    b1 <= d.c + t / 2 + 1e-6 and b1 - b0 <= A.LEAF_T + 1e-6:
                found.append((z0, z1))
        assert found, (d.kind, d.axis, d.c, d.s0, d.s1)
        z0, z1 = max(found, key=lambda z: z[1] - z[0])
        assert z1 - z0 > 100.0 and z1 <= top + 1e-6


def _corners(shape, pivot, myaw, scale):
    _path, lo, hi, _y = A.C.REAL[shape]
    c, s = math.cos(math.radians(myaw)), math.sin(math.radians(myaw))
    out = []
    for X in (lo[0], hi[0]):
        for Y in (lo[1], hi[1]):
            for Z in (lo[2], hi[2]):
                x, y = scale[0] * X, scale[1] * Y
                out.append((pivot[0] + c * x - s * y, pivot[1] + s * x + c * y, pivot[2] + scale[2] * Z))
    return out


@pytest.mark.parametrize("shape", ["SM_Couch", "SM_Chair", "SM_TableRound", "SM_Bush"])
def test_a_real_mesh_fills_its_part_box(shape):
    centre, size = (12.0, -7.0, 60.0), (220.0, 92.0, 85.0)
    path, pivot, myaw, scale = A.real_part(shape, centre, size)
    assert path == A.C.REAL[shape][0]
    pts = _corners(shape, pivot, myaw, scale)
    for k in range(3):
        assert min(p[k] for p in pts) == pytest.approx(centre[k] - size[k] / 2, abs=1e-6)
        assert max(p[k] for p in pts) == pytest.approx(centre[k] + size[k] / 2, abs=1e-6)


@pytest.mark.parametrize("shape", ["SM_Couch", "SM_Chair"])
def test_a_seats_back_is_the_items_back(shape):
    """The measured mesh's tall side (its back, native -x, pyinterior_probe_meshes.py) ends on the item's back (-y)."""
    centre, size = (0.0, 0.0, 42.5), (220.0, 92.0, 85.0)
    _path, pivot, myaw, scale = A.real_part(shape, centre, size)
    _p, lo, hi, _y = A.C.REAL[shape]
    c, s = math.cos(math.radians(myaw)), math.sin(math.radians(myaw))
    x, y = scale[0] * lo[0], 0.0
    assert pivot[1] + s * x + c * y == pytest.approx(-size[1] / 2, abs=1e-6)


def test_real_meshes_switch():
    real_paths = {v[0] for v in A.C.REAL.values()}
    *_r, on = house([(0, 0), (1050, 0), (1050, 800), (0, 800)], params={"RealMeshes": True})
    *_r, off = house([(0, 0), (1050, 0), (1050, 800), (0, 800)], params={"RealMeshes": False})
    used = [i for i in on if i["mesh"] in real_paths]
    assert used and all(i["mat"] == "" and i["role"].startswith("furniture:") for i in used)
    assert not any(i["mesh"] in real_paths for i in off)
    assert A.DEFAULTS["RealMeshes"] is True


def test_deterministic():
    a = house([(0, 0), (1050, 0), (1050, 800), (0, 800)], seed=3)[-1]
    b = house([(0, 0), (1050, 0), (1050, 800), (0, 800)], seed=3)[-1]
    assert [(i["loc"], i["mesh"], i["mat"]) for i in a] == [(i["loc"], i["mesh"], i["mat"]) for i in b]


def test_a_turned_house_is_the_same_house_turned():
    a = house([(0, 0), (1050, 0), (1050, 800), (0, 800)], seed=3, yaw=0.0)[-1]
    b = house([(0, 0), (1050, 0), (1050, 800), (0, 800)], seed=3, yaw=30.0)[-1]
    assert len(a) == len(b)
    c, s = math.cos(math.radians(30.0)), math.sin(math.radians(30.0))
    for i, j in zip(a, b):
        x, y, z = i["loc"]
        assert j["loc"][0] == pytest.approx(c * x - s * y, abs=1e-6) and j["loc"][1] == pytest.approx(s * x + c * y, abs=1e-6)
        assert j["rot"][1] == pytest.approx(i["rot"][1] + 30.0, abs=1e-6)
        assert j["mesh"] == i["mesh"] and j["mat"] == i["mat"]
