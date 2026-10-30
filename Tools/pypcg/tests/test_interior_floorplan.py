"""PyInterior floor planning around a fixed stair room (spec 2026-10-29 §7)."""
import random

import pytest

from pypcg.interior import floorplan as FP
from pypcg.interior import layout as L
from pypcg.interior import program as P
from pypcg.interior import stairs as ST
from pypcg.interior import storeys as S

from test_interior_layout import fp_of
from test_interior_stairs import two_floors
from test_interior_storeys import box, with_z

CASES = [(w, h) for w in (800, 1000, 1200, 1400) for h in (700, 850, 1000)]


def covers(r, span):
    """Room rect r has a side on the span's line that runs over the whole span."""
    axis, c, s0, s1 = span
    if axis == "y":
        return min(abs(r.y0 - c), abs(r.y1 - c)) < 1e-6 and r.x0 <= s0 + 1e-6 and r.x1 >= s1 - 1e-6
    return min(abs(r.x0 - c), abs(r.x1 - c)) < 1e-6 and r.y0 <= s0 + 1e-6 and r.y1 >= s1 - 1e-6


def ground(fps, s, seed=1, **kw):
    prog = P.choose_floor((fps[0].area - s.rect.area) / 1e4, 0, False)
    return FP.plan_floor(fps[0], prog, random.Random(seed), dict(L.WALLS), s, 0, "ground", **kw)


def test_pieces_tile_the_floor_without_the_stair():
    fps = two_floors(1000, 800)
    for s in ST.candidates(fps)[0][:6]:
        for opt in FP.pieces_options(fps[0], s.rect):
            assert abs(sum(r.area for r in opt) - (fps[0].area - s.rect.area)) < 1e-6
            assert all(not a.overlaps(b) for i, a in enumerate(opt) for b in opt[i + 1:])
            assert all(not r.overlaps(s.rect) and r.short >= 250.0 - 1e-6 for r in opt)


def test_a_mid_side_stair_offers_both_cuts():
    fps = two_floors(1200, 900)
    s = next(c for c in ST.candidates(fps)[0] if c.rect.x0 > 300 and c.rect.x1 < 900)
    shapes = {tuple(sorted((round(r.w), round(r.h)) for r in opt)) for opt in FP.pieces_options(fps[0], s.rect)}
    assert len(shapes) >= 2


def test_an_enclosed_sliver_rules_the_stair_out():
    """A stair 110 cm from a side wall and against the back wall leaves a 110 cm strip shut in on three sides: every cut keeps
    it, so the stair cannot stand there (the building loop tries its next place)."""
    fp = fp_of([(0, 0), (1000, 0), (1000, 800), (0, 800)])
    assert FP.pieces_options(fp, L.Rect(110, 300, 360, 800)) == []


def test_a_corner_stair_gives_both_ways_round_the_corner():
    """A stair in the back-left corner: the block in front of it reaches across the house, or the block beside it reaches
    the front."""
    fp = fp_of([(0, 0), (1000, 0), (1000, 800), (0, 800)])
    opts = FP.pieces_options(fp, L.Rect(0, 300, 260, 800))
    shapes = {tuple(sorted((round(r.w), round(r.h)) for r in opt)) for opt in opts}
    assert shapes == {((260, 300), (740, 800)), ((740, 500), (1000, 300))}


def _rooms():
    return [L.Room(0, "Living", L.Rect(0, 0, 500, 400)), L.Room(1, "Corridor", L.Rect(500, 0, 700, 400)),
            L.Room(2, "Stair", L.Rect(500, 400, 700, 700)), L.Room(3, "Dining", L.Rect(0, 400, 500, 700))]


def test_connect_only_joins_through_the_named_room():
    fp = fp_of([(0, 0), (700, 0), (700, 700), (0, 700)])
    assert L.connect(_rooms(), fp, 0)[2] == 1               # by preference the corridor
    assert L.connect(_rooms(), fp, 0, only={2: 3})[2] == 3  # restricted: only through the dining room


def test_stair_passage_kind():
    assert L.passage("Living", "Stair") == "stair" and L.passage("Stair", "Corridor") == "stair"
    assert L.passage("Living", "Kitchen") == "opening"


def test_floor_memo_matches_the_layout_checks():
    """floorplan's per-floor caches give exactly layout._sizes_ok and layout._score, bit for bit (near-equal scores
    decide between plans, so a cache that adds the terms in another order would change houses)."""
    fp = two_floors(1200, 900)[0]
    walls = dict(L.WALLS)
    memo = FP._Memo(fp, walls)
    slots = [P.Slot("Bedroom", 2.1), P.Slot("Bath", 1.0), P.Slot("WC", 0.5)]
    n = 0
    for side, span in (("bottom", (0.0, 600.0)), ("left", (0.0, 450.0))):
        for cand in L.private_layouts(L.Rect(0, 0, 600, 450), slots, side, span):
            tg = [3e4 + 1e4 * k / 3.0 for k in range(len(cand))]
            assert memo.ok(cand) == L._sizes_ok(cand, fp, walls)
            assert memo.score(cand, tg) == L._score(cand, fp, walls, tg)
            n += 1
    assert n > 20


# ---------------------------------------------------------------- the ground floor

@pytest.mark.parametrize("seed, mirror", [(1, False), (2, True)])
@pytest.mark.parametrize("w, h", CASES)
def test_ground_floor_invariants(w, h, seed, mirror):
    fps = two_floors(w, h)
    for s in ST.candidates(fps)[0][:3]:
        plan = ground(fps, s, seed, mirror=mirror)
        if plan.failures:
            continue
        by = {r.id: r for r in plan.rooms}
        st = next(r for r in plan.rooms if r.type == "Stair")
        assert st.rect == s.rect and plan.stair is s and plan.level == 0
        parent = by[plan.parents[st.id]]
        assert parent.type in P.ACCESS["Stair"] and covers(parent.rect, s.access("ground"))
        assert by[plan.front_room].type == "Living" and len(plan.parents) == len(plan.rooms)
        assert abs(sum(r.rect.area for r in plan.rooms) - fps[0].area) < 1e-3
        assert all(not a.rect.overlaps(b.rect) for i, a in enumerate(plan.rooms) for b in plan.rooms[i + 1:])
        for r in plan.rooms:
            if r.type != "Stair":
                c = L.clear_rect(r.rect, plan.footprint, plan.walls)
                assert c.short >= P.ROOMS[r.type].min_short - 1e-6
        return
    pytest.fail("no stair candidate gives a ground floor")


def test_townhouse_ground_floor_has_living_front_kitchen_back():
    fps = two_floors(550, 1100, 3)
    plan = ground(fps, ST.candidates(fps)[0][0])
    assert not plan.failures
    liv = next(r for r in plan.rooms if r.type == "Living")
    kit = next(r for r in plan.rooms if r.type == "Kitchen")
    assert liv.rect.cy < kit.rect.cy


def test_a_stair_that_leaves_the_living_room_no_place_gives_no_fit():
    """8 x 7 m, a U against the middle of the back wall: the front band is 330 deep (299 clear, the living room needs
    300) and the blocks beside the stair are 280 wide."""
    fps = two_floors(800, 700)
    s = next(c for c in ST.candidates(fps)[0] if c.type == "U" and c.rect == L.Rect(280, 330, 520, 700))
    plan = ground(fps, s)
    assert plan.failures == [L.NO_FIT] and plan.stair is s and plan.level == 0


def _back_left_u():
    """8 x 7 m, a U in the back-left corner opening to the front: the block in front of it is 260 x 330."""
    fps = two_floors(800, 700)
    return fps, next(c for c in ST.candidates(fps)[0] if c.type == "U" and c.rect == L.Rect(0, 330, 260, 700))


def test_the_stair_may_open_into_a_hall_corridor():
    """Spec §6.2: the stair is reached from the living room, a corridor or the dining room -- here a corridor across the
    small block in front of it (its other room the WC), entered from the living room."""
    fps, s = _back_left_u()
    plan = ground(fps, s)
    assert not plan.failures and plan.program.name == "Ground_M"
    hall = plan.room(plan.parents[next(r.id for r in plan.rooms if r.type == "Stair")])
    assert hall.type == "Corridor" and plan.room(plan.parents[hall.id]).type == "Living"


def test_a_block_left_empty_at_the_stair_is_a_corridor():
    """Spec §7: a block no room is given is a corridor or a storage room -- a corridor where the stair opens into it."""
    fps, s = _back_left_u()
    plan = FP.plan_floor(fps[0], P.GROUND[0], random.Random(1), dict(L.WALLS), s, 0, "ground")
    assert not plan.failures
    assert [r.type for r in plan.rooms if r.rect == L.Rect(0, 0, 260, 330)] == ["Corridor"]


def test_skip_steps_down_the_ground_table():
    fps = two_floors(1000, 800)
    s = ST.candidates(fps)[0][0]
    first = ground(fps, s)
    second = ground(fps, s, skip={first.program})
    assert not first.failures and not second.failures
    assert second.program != first.program and second.program.size <= first.program.size
    assert second.program in list(P.fallbacks(first.program, P.GROUND))


def test_ground_floor_is_deterministic():
    fps = two_floors(1200, 850)
    s = ST.candidates(fps)[0][0]
    a, b = ground(fps, s, 3), ground(fps, s, 3)
    assert [(r.type, r.rect) for r in a.rooms] == [(r.type, r.rect) for r in b.rooms] and a.parents == b.parents


@pytest.mark.parametrize("w, h", [(1400, 900), (1200, 1000), (1000, 800)])
def test_the_living_room_stays_the_largest_room(w, h):
    """Rooms are sized against the whole floor, not their block: a block left over beside the stair does not make the
    study larger than the living room."""
    fps = two_floors(w, h)
    plan = ground(fps, ST.candidates(fps)[0][0])
    liv = next(r for r in plan.rooms if r.type == "Living")
    assert not plan.failures and all(liv.rect.area >= r.rect.area for r in plan.rooms)


# ---------------------------------------------------------------- the upper floors

def upper(fps, s, level, role, seed=1):
    prog = P.choose_floor((fps[level].area - s.rect.area) / 1e4, level, role == "top")
    return FP.plan_floor(fps[level], prog, random.Random(seed), dict(L.WALLS), s, level, role)


@pytest.mark.parametrize("w, h", CASES)
def test_upper_floor_circulation(w, h):
    """Review Focus 3: every room reached from the stair without passing a bedroom or a wet room (the loft excepted); a
    bedroom may have its own bathroom and closet (a Storage room), as in a single-floor house (program.ACCESS)."""
    fps = two_floors(w, h)
    for s in ST.candidates(fps)[0][:3]:
        plan = upper(fps, s, 1, "top")
        if plan.failures:
            continue
        by = {r.id: r for r in plan.rooms}
        assert by[plan.front_room].type == "Stair" and plan.entry is None and plan.level == 1 and plan.stair is s
        first = [r for r in plan.rooms if plan.parents.get(r.id) == plan.front_room]
        assert len(first) == 1 and (first[0].type == "Corridor" or plan.program.name == "Upper_S")
        assert covers(first[0].rect, s.access("top"))
        for r in plan.rooms:
            pid = plan.parents[r.id]
            while pid is not None and pid != plan.front_room:
                assert by[pid].type not in ("Bath", "WC", "Laundry") and \
                    (by[pid].type not in ("Master", "Bedroom") or r.type in ("Bath", "Storage"))
                pid = plan.parents[pid]
        assert "Bath" in {r.type for r in plan.rooms}
        assert abs(sum(r.rect.area for r in plan.rooms) - fps[1].area) < 1e-3
        return
    pytest.fail("no stair candidate gives an upper floor")


def test_small_top_floor_is_a_loft():
    """A 6.5 x 6 m top floor over the back of a 9 x 8 m house: Upper_S, its bedroom straight off the stair."""
    lv = S.levels([box(900, 800), with_z(box(650, 600, 0, 200), 300.0)], 0.0, 270.0, 0)
    fps, _ = S.floor_footprints(lv, (0.0, 0.0, 0.0), 0.0, 50.0, 270.0)
    ok = False
    for s in ST.candidates(fps)[0][:6]:
        plan = FP.plan_floor(fps[1], P.choose_floor((fps[1].area - s.rect.area) / 1e4, 1, True), random.Random(1),
                             dict(L.WALLS), s, 1, "top")
        ok = ok or (not plan.failures and plan.program.name == "Upper_S")
    assert ok


def test_a_top_floor_without_a_master_slot_names_its_largest_bedroom():
    """Spec §5.1: one master per house, on the top floor -- the largest bedroom when the top floor's program has none
    (a 5.5 x 7 m loft: its bedroom is large enough for a master)."""
    lv = S.levels([box(900, 800), with_z(box(550, 700, 0, 100), 300.0)], 0.0, 270.0, 0)
    fps, _ = S.floor_footprints(lv, (0.0, 0.0, 0.0), 0.0, 50.0, 270.0)
    plans = [upper(fps, s, 1, "top") for s in ST.candidates(fps)[0][:6]]
    lofts = [p for p in plans if not p.failures and p.program.name == "Upper_S"]
    assert lofts and all([r.type for r in p.rooms].count("Master") == 1 for p in lofts)


def test_middle_floor_has_bedrooms_and_one_landing_over_both_openings():
    """A three-floor U: the middle floor's corridor runs along the whole open end (arrival and departure), and its master
    slot is a bedroom (the master is on the top floor)."""
    fps = two_floors(550, 1100, 3)
    for s in ST.candidates(fps)[0][:3]:
        plan = upper(fps, s, 1, "middle")
        if plan.failures:
            continue
        first = [r for r in plan.rooms if plan.parents.get(r.id) == plan.front_room]
        assert [r.type for r in first] == ["Corridor"] and covers(first[0].rect, s.access("middle"))
        assert "Master" not in {r.type for r in plan.rooms} and "Bath" in {r.type for r in plan.rooms}
        top = upper(fps, s, 2, "top")
        assert not top.failures and [r.type for r in top.rooms].count("Master") == 1
        return
    pytest.fail("no stair candidate gives a middle floor")


def _landing(plan):
    return plan.room(next(r for r, p in plan.parents.items() if p == plan.front_room))


def test_a_shallow_block_at_the_stair_becomes_the_landing():
    """8 x 9 m, a U against the right wall opening to the front: the 270 cm block in front of it holds no room behind a
    corridor, so the whole block is the landing and the bedrooms are entered from it -- the floor keeps Upper_L."""
    fps = two_floors(800, 900)
    s = next(c for c in ST.candidates(fps)[0] if c.type == "U" and c.rect == L.Rect(540, 270, 800, 620))
    plan = upper(fps, s, 1, "top")
    hall = _landing(plan)
    assert plan.program.name == "Upper_L" and hall.type == "Corridor" and hall.rect == L.Rect(540, 0, 800, 270)


def test_a_landing_strip_lets_a_hall_run_into_a_deep_block():
    """12 x 8 m, a U against the left wall opening sideways: a 130 cm landing along the stair's open side, the rest of
    the deep block beside it entered from the landing -- the floor keeps all eight rooms of Upper_XL."""
    fps = two_floors(1200, 800)
    s = next(c for c in ST.candidates(fps)[0] if c.type == "U" and c.rect == L.Rect(0, 280, 370, 520))
    plan = upper(fps, s, 1, "top")
    hall = _landing(plan)
    assert plan.program.name == "Upper_XL" and plan.program.size == 8
    assert hall.type == "Corridor" and hall.rect == L.Rect(370, 0, 500, 800)


def test_a_whole_block_landing_only_where_no_room_fits_behind_one():
    """Three floors of 7.5 x 10 m: a block deep enough for rooms behind a landing never becomes one big hall."""
    fps = two_floors(750, 1000, 3)
    seen = 0
    for s in ST.candidates(fps)[0][:3]:
        for lv in (1, 2):
            plan = upper(fps, s, lv, s.role(lv))
            if plan.failures:
                continue
            hall = _landing(plan)
            assert hall.type != "Corridor" or hall.rect.short < L.CORRIDOR + FP.MIN_PIECE - 1e-6
            seen += 1
    assert seen


def test_two_corridors_never_stand_side_by_side():
    """A landing with a gallery right behind it is one corridor split in two: the floor finds another way (the 10 x 6 m
    upper floor over a 10 x 9 m house had two parallel 2.7 m2 corridors). Corridors meeting in an L or a T are fine."""
    fps, rects, (plan, doors, wins, places, fails) = _terrace_floor()
    halls = [r.rect for r in plan.rooms if r.type == "Corridor"]
    assert not any(FP._side_by_side(a, b) for i, a in enumerate(halls) for b in halls[i + 1:])
    assert FP._side_by_side(L.Rect(0, 0, 130, 500), L.Rect(130, 0, 260, 500))
    assert not FP._side_by_side(L.Rect(0, 0, 260, 270), L.Rect(260, 0, 390, 900))       # a landing and a hall on from it


# ---------------------------------------------------------------- doors, windows, furniture on the floors

def furnished_floor(fps, s, level, seed=1, terraces=()):
    from pypcg.interior import doors as D
    from pypcg.interior import furnish as FU
    from pypcg.interior import openings as O
    plan = upper(fps, s, level, s.role(level), seed) if level else ground(fps, s, seed)
    rng = random.Random(seed)
    doors = D.connect(plan, rng) + D.terrace_doors(plan, terraces)
    wins = O.windows(plan, doors, rng)
    places, fails = FU.furnish(plan, doors, wins, rng)
    return plan, doors, wins, places, fails


@pytest.mark.parametrize("w, h, n", [(1000, 800, 2), (1200, 1000, 2), (800, 900, 2), (550, 1100, 3)])
def test_upper_floor_furniture_keeps_every_rule(w, h, n):
    from pypcg.interior import checks as K
    from test_interior_furnish import check_placements
    fps = two_floors(w, h, n)
    for s in ST.candidates(fps)[0][:3]:
        plan, doors, wins, places, fails = furnished_floor(fps, s, n - 1)
        if plan.failures:
            continue
        assert not fails, fails
        check_placements(plan, doors, wins, places)
        assert K.validate(plan, doors, wins, places) == []
        return
    pytest.fail("no stair candidate gives a top floor")


def test_stair_landing_is_kept_free():
    """Nothing stands on the 100 cm in front of a stair opening, over its whole width (the landing, or the stair foot)."""
    from pypcg.interior import catalog as C
    from pypcg.interior import furnish as FU
    for w, h, n in ((1000, 800, 2), (550, 1100, 3), (1200, 1000, 2)):
        fps = two_floors(w, h, n)
        s = ST.candidates(fps)[0][0]
        for lv in range(n):
            plan, doors, wins, places, fails = furnished_floor(fps, s, lv)
            if plan.failures:
                continue
            d = next(d for d in doors if d.kind == "stair")
            acc = plan.room(d.a if plan.room(d.b).type == "Stair" else d.b)
            zone = FU.approach(d, acc, plan)
            assert (zone.w if d.axis == "x" else zone.h) == pytest.approx(FU.LANDING + 0.5 * plan.walls["int"])
            assert (zone.h if d.axis == "x" else zone.w) == pytest.approx(d.width)
            assert not [p.item for p in places if p.room == acc.id and C.ITEMS[p.item].kind != "rug"
                        and p.rect().overlaps(zone)]


def _terrace_floor():
    """1F 10 x 9, 2F 10 x 6 at the back: a 10 x 3 m terrace in front of the upper floor."""
    lv = S.levels([box(1000, 900), with_z(box(1000, 600, 0, 300), 300.0)], 0.0, 270.0, 0)
    fps, _ = S.floor_footprints(lv, (0.0, 0.0, 0.0), 0.0, 50.0, 270.0)
    rects = S.terrace_rects(fps)[1]
    for s in ST.candidates(fps)[0][:3]:
        got = furnished_floor(fps, s, 1, terraces=rects)
        if not got[0].failures:
            return fps, rects, got
    raise AssertionError("no stair candidate gives the terrace floor")


def test_a_large_terrace_gets_a_table_chairs_and_a_plant():
    from pypcg.interior import terrace as T
    fps, rects, (plan, doors, wins, places, fails) = _terrace_floor()
    ts = T.plan_terraces(fps[0], rects, plan, doors, random.Random(1))
    assert len(ts) == 1 and ts[0].level == 1 and ts[0].door is not None and ts[0].rect == rects[0]
    # railed along the front and both ends, not along the upper floor's wall
    assert sorted((a, c, lo, hi) for a, c, lo, hi, _o in ts[0].rails) == [("x", 0.0, 0.0, 300.0), ("x", 1000.0, 0.0, 300.0),
                                                                          ("y", 0.0, 0.0, 1000.0)]
    items = sorted(p.item for p in ts[0].places)
    assert items.count("Table_2") == 1 and 2 <= items.count("Armchair") <= 4 and items.count("Plant") >= 1
    deck = ts[0].rect.shrink(T.INSET, T.INSET, T.INSET, T.INSET)
    keep = T.door_zone(ts[0].door, ts[0].rect)
    for i, p in enumerate(ts[0].places):
        assert p.rect().inside(deck) and not p.rect().overlaps(keep)
        assert all(not p.rect().overlaps(q.rect()) for q in ts[0].places[i + 1:])


def test_small_narrow_and_doorless_terraces():
    """Spec §8: a plant from 3 m2; a strip under 120 cm and a terrace no room opens onto get the railing alone."""
    from pypcg.interior import terrace as T
    fps, rects, (plan, doors, wins, places, fails) = _terrace_floor()
    mid = next(d for d in doors if d.kind == "terrace").mid
    small = L.Rect(mid - 150, 300 - 160, mid + 150, 300)              # 3.0 x 1.6 m: 4.8 m2, short side 160
    strip = L.Rect(mid - 300, 300 - 100, mid + 300, 300)              # 1 m deep
    got = T.plan_terraces(fps[0], [small, strip], plan, doors, random.Random(1))
    assert [p.item for p in got[0].places] == ["Plant"] and got[1].places == []
    assert T.plan_terraces(fps[0], rects, plan, [x for x in doors if x.kind != "terrace"], random.Random(1))[0].places == []


def test_the_table_set_is_only_built_where_it_stays_on_the_deck(monkeypatch):
    """Final review (spec §1.7, at most 1.5 s a building): a 16 x 2 m terrace's table set was built and checked at every
    10 cm of the deck, four, three and two chairs, both ways round -- some 17 000 sets for each stair place tried, nearly
    all of them over the deck's edge. A set that leaves the deck is not built (it never fitted, so no seed is drawn
    for it either way), and the deck still gets its set."""
    from pypcg.interior import terrace as T
    deck, keep = L.Rect(15, 915, 1585, 1085), L.Rect(670, 900, 820, 1020)
    built = []
    real = T._set

    def counting(*a):
        ps = real(*a)
        built.append(ps)
        return ps
    monkeypatch.setattr(T, "_set", counting)
    got = T._table_set(deck, keep, random.Random(1))
    assert got and got[0].item == "Table_2"
    over = [ps for ps in built if not all(p.rect().inside(deck.shrink(-1.0, -1.0, -1.0, -1.0)) for p in ps)]
    assert not over, (len(over), len(built))
