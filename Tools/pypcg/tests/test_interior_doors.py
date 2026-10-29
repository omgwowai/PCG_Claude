"""PyInterior doors: passages along the connection tree, the front door, extra openings (spec 2026-10-28 §4.5)."""
import random

import pytest

from pypcg.interior import doors as D
from pypcg.interior import layout as L
from pypcg.interior import program as P

from test_interior_layout import SWEEP, fp_of


def sweep_doors():
    out = []
    for k, pts in enumerate(SWEEP):
        fp = fp_of(pts)
        if fp is None:
            continue
        for seed in (1, 2):
            plan = L.plan(fp, P.choose(fp.area_m2), random.Random(seed))
            out.append((k, seed, plan, D.connect(plan, random.Random(seed))))
    return out


CASES = sweep_doors()


@pytest.mark.parametrize("k, seed, plan, doors", CASES, ids=["%d-%d" % (k, s) for k, s, _p, _d in CASES])
def test_door_invariants(k, seed, plan, doors):
    fp = plan.footprint
    by = {r.id: r for r in plan.rooms}
    tree = [d for d in doors if d.tree]
    fronts = [d for d in doors if d.kind == "front"]
    assert len(fronts) == 1
    f = fronts[0]
    fr = by[plan.front_room]
    # the front door: on the entry room's exterior front wall, facing -y
    assert f.b == plan.front_room and f.axis == "y" and f.c == pytest.approx(fr.rect.y0)
    assert any(a - 1e-6 <= f.s0 and f.s1 <= b + 1e-6 for a, b in L.exterior_parts(fp, "y", fr.rect.y0, fr.rect.x0,
                                                                                    fr.rect.x1, -1))
    # one tree passage into every room but the front room; reaching everything from the front door
    into = {}
    for d in tree:
        if d.kind != "front":
            into.setdefault(d.b, []).append(d)
    assert sorted(into) == sorted(r.id for r in plan.rooms if r.id != plan.front_room)
    assert all(len(v) == 1 for v in into.values())
    reached, todo = {plan.front_room}, [plan.front_room]
    kids = {}
    for d in tree:
        if d.kind != "front":
            kids.setdefault(d.a, []).append(d.b)
    while todo:
        for c in kids.get(todo.pop(), []):
            if c not in reached:
                reached.add(c)
                todo.append(c)
    assert len(reached) == len(plan.rooms)
    for d in doors:
        if d.kind == "front":
            continue
        a, b = by[d.a], by[d.b]
        # never into a bedroom from a bathroom, a kitchen or another bedroom
        if b.type in ("Bedroom", "Master") and d.tree:
            assert a.type not in ("Bath", "WC", "Kitchen", "Bedroom", "Master", "Laundry", "Storage")
        # within the shared wall, clear of its ends
        sh = a.rect.shared(b.rect)
        assert sh is not None and sh[0] == d.axis and sh[1] == pytest.approx(d.c)
        assert d.s0 >= sh[2] + D.MARGIN - 1e-6 and d.s1 <= sh[3] - D.MARGIN + 1e-6, (a.type, b.type, d, sh)
        # public rooms meet through openings
        if frozenset((a.type, b.type)) in P.OPEN:
            assert d.kind == "opening"
        assert d.s1 - d.s0 >= 79.9


def test_widths_and_leaves():
    plan = L.plan(fp_of([(0, 0), (1300, 0), (1300, 900), (0, 900)]), P.choose(117.0), random.Random(1))
    doors = D.connect(plan, random.Random(1))
    by = {r.id: r for r in plan.rooms}
    for d in doors:
        w = d.s1 - d.s0
        if d.kind == "front":
            assert w == pytest.approx(D.WIDTH["front"])
        elif d.kind in ("door", "bath"):
            assert w == pytest.approx(D.WIDTH[d.kind])
            assert d.leaf and d.hinge in (0, 1)
            # the swing zone lies in the room the leaf opens into and keeps clear of the wall line
            z = D.swing(d, by[d.b], plan)
            assert z.inside(by[d.b].rect) and z.w > 0 and z.h > 0
        else:
            assert not d.leaf


def test_extra_openings_join_open_plan_rooms():
    plan = L.plan(fp_of([(0, 0), (1300, 0), (1300, 900), (0, 900)]), P.choose(117.0), random.Random(1))
    doors = D.connect(plan, random.Random(1))
    by = {r.id: r for r in plan.rooms}
    pairs = {frozenset((by[d.a].type, by[d.b].type)) for d in doors if d.kind == "opening"}
    kitchen = next(r for r in plan.rooms if r.type == "Kitchen")
    dining = next(r for r in plan.rooms if r.type == "Dining")
    if L.shared_length(kitchen.rect, dining.rect) >= L.SPAN["opening"]:
        assert frozenset(("Kitchen", "Dining")) in pairs
