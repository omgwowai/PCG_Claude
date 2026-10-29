"""PyInterior layout: the zoning grammar (spec 2026-10-28 §4.4) over a sweep of footprints."""
import random

import pytest

from pypcg.interior import footprint as F
from pypcg.interior import layout as L
from pypcg.interior import program as P


def fp_of(local_pts, yaw=0.0):
    import math
    a = math.radians(yaw)
    ex, ey = (-math.sin(a), math.cos(a)), (-math.cos(a), -math.sin(a))
    pts = [(x * ex[0] + y * ey[0], x * ex[1] + y * ey[1], 0.0) for x, y in local_pts]
    return F.build(pts, (0.0, 0.0, 0.0), yaw)


def rect(w, h):
    return [(0, 0), (w, 0), (w, h), (0, h)]


def l_shape(w, h, cw, ch):
    return [(0, 0), (w, 0), (w, h - ch), (w - cw, h - ch), (w - cw, h), (0, h)]


def t_shape(w, h, sw, sh):
    # a bar of w x (h - sh) at the front with a stem sw x sh centred at the back
    x0 = (w - sw) / 2
    return [(0, 0), (w, 0), (w, h - sh), (x0 + sw, h - sh), (x0 + sw, h), (x0, h), (x0, h - sh), (0, h - sh)]


def u_shape(w, h, gap_w, gap_h):
    x0 = (w - gap_w) / 2
    return [(0, 0), (w, 0), (w, h), (x0 + gap_w, h), (x0 + gap_w, h - gap_h), (x0, h - gap_h), (x0, h), (0, h)]


SWEEP = [rect(w, h) for w in range(500, 2001, 150) for h in range(450, 1401, 150) if max(w, h) / min(w, h) <= 3.5] + \
    [l_shape(1400, 1100, 600, 500), l_shape(1200, 1000, 500, 400), l_shape(1600, 1200, 700, 600), l_shape(1000, 900, 450, 400),
     t_shape(1600, 1100, 600, 500), t_shape(1400, 1000, 500, 450), u_shape(1600, 1000, 600, 500), u_shape(1800, 1200, 700, 600)]
# Review Focus 1: the program band edges (34 / 58 / 88 / 130 m2, as near as the 50 cm grid allows: 33.75, 35, 57.75, 58.5,
# 88, 123.5, 130) and legs / stems / arms of 250-300 cm off a front block deep enough for a living room
SWEEP += [rect(450, 750), rect(500, 700), rect(550, 1050), rect(650, 900), rect(800, 1100), rect(950, 1300), rect(1000, 1300),
          l_shape(1000, 1000, 750, 550), l_shape(1100, 1100, 800, 600), t_shape(1200, 1000, 250, 500),
          t_shape(1200, 1000, 300, 450), u_shape(1300, 1100, 800, 600), u_shape(1400, 1100, 800, 600)]


def all_plans():
    for k, pts in enumerate(SWEEP):
        fp = fp_of(pts)
        if fp is None:
            continue
        for seed in (1, 2, 3):
            yield k, seed, fp, L.plan(fp, P.choose(fp.area_m2), random.Random(seed))


PLANS = list(all_plans())


def test_sweep_is_big_enough():
    assert len(PLANS) >= 200


@pytest.mark.parametrize("k, seed, fp, plan", PLANS, ids=["%d-%d" % (k, s) for k, s, _f, _p in PLANS])
def test_plan_invariants(k, seed, fp, plan):
    assert not plan.failures, plan.failures
    rooms = plan.rooms
    # rooms tile the footprint
    assert sum(r.rect.area for r in rooms) == pytest.approx(fp.area)
    for i, a in enumerate(rooms):
        assert any(a.rect.inside(w) for w in fp.wings), (a.type, a.rect)
        for b in rooms[i + 1:]:
            assert not a.rect.overlaps(b.rect), (a.type, b.type)
    # every room meets its minimum clear size
    for r in rooms:
        c = L.clear_rect(r.rect, fp, plan.walls)
        rt = P.ROOMS[r.type]
        assert c.short >= rt.min_short - 1e-6 and c.long >= rt.min_long - 1e-6, (r.type, c)
    # all rooms reachable from the front door, each through an allowed parent
    reached = L.connect(rooms, fp, plan.front_room)
    assert reached is not None and len(reached) == len(rooms)
    # the program's rooms are all there (the plan's program may be a fallback)
    types = sorted(r.type for r in rooms if r.type not in ("Corridor", "Storage"))
    assert types == sorted(plan.program.types())
    # the front door lands on the front room's exterior front side
    fr = next(r for r in rooms if r.id == plan.front_room)
    x0, x1, y = plan.entry
    assert y == pytest.approx(fr.rect.y0) and fr.rect.x0 - 1e-6 <= x0 < x1 <= fr.rect.x1 + 1e-6 and x1 - x0 >= 120.0
    # habitable rooms have an exterior wall for a window
    for r in rooms:
        if r.type in ("Living", "Main", "Master", "Bedroom"):
            assert L.exterior_length(r.rect, fp) >= 100.0, r.type


def bedrooms(plan):
    return sum(1 for r in plan.rooms if r.type in ("Master", "Bedroom"))


def test_bedrooms_never_drop_as_the_house_grows():
    for aspect in (1.0, 1.3, 1.6, 2.2):
        last = 0
        for w in range(500, 2101, 50):
            h = round(w / aspect / 50) * 50
            fp = fp_of(rect(w, h))
            if fp is None:
                continue
            n = bedrooms(L.plan(fp, P.choose(fp.area_m2), random.Random(1)))
            assert n >= last, (aspect, w, h, n, last)
            last = n


@pytest.mark.parametrize("w, h, name, rooms", [
    (600, 500, "Studio", {"Main", "Bath"}),
    (800, 650, "OneBed", {"Living", "Kitchen", "Bedroom", "Bath"}),
    (1050, 800, "TwoBed", {"Living", "Kitchen", "Master", "Bedroom", "Bath"}),
    (1300, 900, "ThreeBed", {"Living", "Kitchen", "Master", "Bedroom", "Bath"}),
])
def test_named_houses(w, h, name, rooms):
    plan = L.plan(fp_of(rect(w, h)), P.choose(w * h / 1e4), random.Random(1))
    assert plan.program.name == name
    assert rooms <= {r.type for r in plan.rooms}


def test_three_bed_has_a_corridor():
    plan = L.plan(fp_of(rect(1300, 900)), P.choose(117.0), random.Random(1))
    assert any(r.type == "Corridor" for r in plan.rooms)


def test_l_shape_gets_three_bedrooms():
    fp = fp_of(l_shape(1400, 1100, 600, 500))
    plan = L.plan(fp, P.choose(fp.area_m2), random.Random(1))
    assert plan.program.name == "ThreeBed" and bedrooms(plan) == 3


@pytest.mark.parametrize("pts", [l_shape(1000, 1000, 750, 750), l_shape(1100, 1000, 800, 700), u_shape(1300, 900, 800, 600)])
def test_a_front_wing_too_shallow_for_a_living_room_fits_no_program(pts):
    """The front door opens into the living room (or a studio's main room, 280 clear at least): a front wing of 250-300 cm
    holds neither, so no program fits and the stage publishes only its error (review finding 2's backstop)."""
    fp = fp_of(pts)
    assert fp is not None
    plan = L.plan(fp, P.choose(fp.area_m2), random.Random(1))
    assert plan.failures == [L.NO_FIT]


def test_deterministic_and_rotation_free():
    a = L.plan(fp_of(rect(1300, 900)), P.choose(117.0), random.Random(5))
    b = L.plan(fp_of(rect(1300, 900)), P.choose(117.0), random.Random(5))
    c = L.plan(fp_of(rect(1300, 900), yaw=37.0), P.choose(117.0), random.Random(5))
    key = lambda p: [(r.type, r.rect) for r in p.rooms]
    assert key(a) == key(b) == key(c)
