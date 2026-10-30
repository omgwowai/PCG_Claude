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


# ---------------------------------------------------------------- multi-storey floors (spec 2026-10-29)

def _floor(fps, s, level, seed=1):
    from pypcg.interior import floorplan as FP
    role = s.role(level)
    prog = P.choose_floor((fps[level].area - s.rect.area) / 1e4, level, role == "top")
    return FP.plan_floor(fps[level], prog, random.Random(seed), dict(L.WALLS), s, level, role)


def test_front_door_only_on_the_ground_floor():
    from pypcg.interior import stairs as ST
    from test_interior_stairs import two_floors
    fps = two_floors(1000, 800)
    s = ST.candidates(fps)[0][0]
    g, t = _floor(fps, s, 0), _floor(fps, s, 1)
    assert not g.failures and not t.failures
    kinds = [d.kind for d in D.connect(g, random.Random(1))], [d.kind for d in D.connect(t, random.Random(1))]
    assert kinds[0].count("front") == 1 and "front" not in kinds[1]


def test_stair_openings_sit_at_the_access_spans():
    """The stair room's one passage is its opening on that floor, the whole opening, no leaf: into the stair from the room
    in front of it on the ground floor, out of it onto the landing upstairs."""
    from pypcg.interior import stairs as ST
    from test_interior_stairs import two_floors
    seen = 0
    for w, h, n in ((1000, 800, 2), (550, 1100, 3), (650, 1300, 2), (1200, 1000, 2)):
        fps = two_floors(w, h, n)
        for s in ST.candidates(fps)[0][:3]:
            for lv in range(n):
                plan = _floor(fps, s, lv)
                if plan.failures:
                    continue
                st = next(r for r in plan.rooms if r.type == "Stair")
                ds = [d for d in D.connect(plan, random.Random(1)) if st.id in (d.a, d.b)]
                assert len(ds) == 1 and ds[0].kind == "stair" and not ds[0].leaf and ds[0].tree
                d = ds[0]
                assert (d.axis, d.c, d.s0, d.s1) == s.access(s.role(lv))
                assert (d.b == st.id) == (lv == 0)
                seen += 1
    assert seen >= 12


def test_terrace_door_faces_the_terrace():
    """1F 10 x 9, 2F 10 x 6 at the back: the 10 x 3 m front roof is a terrace. One glass door onto it, 90 wide, from a
    room that may open onto a terrace, on y = 300; that room's terrace wall has no window (spec §8)."""
    from pypcg.interior import openings as O
    from pypcg.interior import stairs as ST
    from pypcg.interior import storeys as S
    from test_interior_storeys import box, with_z
    lv = S.levels([box(1000, 900), with_z(box(1000, 600, 0, 300), 300.0)], 0.0, 270.0, 0)
    fps, _ = S.floor_footprints(lv, (0.0, 0.0, 0.0), 0.0, 50.0, 270.0)
    rects = S.terrace_rects(fps)[1]
    for s in ST.candidates(fps)[0][:3]:
        plan = _floor(fps, s, 1)
        if plan.failures:
            continue
        doors = D.connect(plan, random.Random(1))
        td = D.terrace_doors(plan, rects)
        assert len(td) == 1
        d = td[0]
        room = plan.room(d.b)
        assert d.kind == "terrace" and d.leaf and d.sliding and not d.tree and d.a is None
        assert d.axis == "y" and d.c == pytest.approx(300.0) and d.width == pytest.approx(D.WIDTH["terrace"])
        assert room.type in D.TERRACE_ROOMS and room.rect.y0 == pytest.approx(300.0)
        assert room.rect.x0 + D.MARGIN - 1e-6 <= d.s0 and d.s1 <= room.rect.x1 - D.MARGIN + 1e-6
        wins = O.windows(plan, doors + td, random.Random(1))
        assert not [w for w in wins if w.room == room.id and w.axis == "y" and abs(w.c - 300.0) < 1e-6]
        return
    pytest.fail("no stair candidate gives the terrace floor")
