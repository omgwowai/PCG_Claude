"""PyInterior furnishing: room recipes placed by rules on each room's clear floor (spec 2026-10-28 §4.7)."""
import random

import pytest

from pypcg.interior import catalog as C
from pypcg.interior import doors as D
from pypcg.interior import furnish as FU
from pypcg.interior import house as H
from pypcg.interior import layout as L
from pypcg.interior import openings as O
from pypcg.interior import program as P

from test_interior_layout import SWEEP, fp_of

REQUIRED = {"Bedroom": [("bed",)], "Master": [("bed",)], "Main": [("bed",), ("fridge",), ("sink",), ("stove",)],
            "Kitchen": [("fridge",), ("sink",), ("stove",)], "Bath": [("toilet",), ("vanity", "basin"), ("bathtub", "shower")],
            "WC": [("toilet",)], "Living": [("sofa",)], "Dining": [("dining_table",)], "Laundry": [("washer",)]}


def furnished(pts, seed):
    """The stage's chain (interior.house): plan, doors, windows, furniture, a variant stepping down when its required
    furniture does not fit."""
    fp = fp_of(pts)
    if fp is None:
        return None
    return H.plan_house(fp, P.choose(fp.area_m2), random.Random(seed))


# kitchens that lost their run in a 50 cm census (review finding 1): two wide openings and a window on each outside wall
# leave the 195 cm fridge one window-free corner, the corner the short run takes first
TIGHT = [(1350, 700, 1), (1350, 700, 2), (1350, 700, 3), (1500, 550, 2), (1900, 550, 1), (1950, 550, 2)]


def cases():
    out = []
    for k, pts in enumerate(SWEEP):
        for seed in (1, 2):
            got = furnished(pts, seed)
            if got:
                out.append(("%d-%d" % (k, seed),) + got)
    for w, h, seed in TIGHT:
        out.append(("tight-%dx%d-%d" % (w, h, seed),) + furnished([(0, 0), (w, 0), (w, h), (0, h)], seed))
    return out


CASES = cases()


def check_placements(plan, doors, wins, places):
    """Every piece inside its room's clear floor, none overlapping (but a seat tucked under its table), none in a door's
    swing or a passage's approach, no tall piece in front of a window."""
    by = {r.id: r for r in plan.rooms}
    solid = [p for p in places if C.ITEMS[p.item].kind != "rug" and p.z < 100.0]
    for p in places:
        cr = L.clear_rect(by[p.room].rect, plan.footprint, plan.walls)
        assert p.rect().inside(cr), (p.item, p.rect(), cr)
    tuck = {("chair", "dining_table"), ("chair", "desk"), ("stool", "island")}    # a seat pushed under its table
    for i, a in enumerate(solid):
        for b in solid[i + 1:]:
            if a.room == b.room:
                pair = tuple(sorted((C.ITEMS[a.item].kind, C.ITEMS[b.item].kind)))
                if pair in tuck:
                    assert a.rect().shrink(-25, -25, -25, -25).overlaps(b.rect())
                    continue
                assert not a.rect().overlaps(b.rect()), (by[a.room].type, a.item, b.item)
    for d in doors:
        for rid in (d.a, d.b):
            if rid is None:
                continue
            z = D.swing(d, by[rid], plan) if (d.leaf and rid == d.b) else FU.approach(d, by[rid], plan)
            for p in solid:
                if p.room == rid:
                    assert not p.rect().overlaps(z), (by[rid].type, p.item, d.kind)
    for p in places:
        it = C.ITEMS[p.item]
        if not it.tall or p.wall < 0:
            continue
        for w in wins:
            if w.room == p.room and FU.on_side(by[p.room], p.wall, w.axis, w.c, plan) and it.h > w.sill + 1e-6:
                lo, hi = p.span()
                assert hi <= w.s0 + 1e-6 or lo >= w.s1 - 1e-6, (p.item, w)


@pytest.mark.parametrize("cid, plan, doors, wins, places, fails", CASES, ids=[c[0] for c in CASES])
def test_furnishing_invariants(cid, plan, doors, wins, places, fails):
    assert not fails, fails
    # required furniture
    cats = {}
    for p in places:
        cats.setdefault(p.room, set()).add(C.ITEMS[p.item].kind)
    for r in plan.rooms:
        for alts in REQUIRED.get(r.type, []):
            assert any(a in cats.get(r.id, set()) for a in alts), (r.type, alts, sorted(cats.get(r.id, set())))
    check_placements(plan, doors, wins, places)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_a_kitchen_whose_one_free_corner_both_want_gets_its_run(seed):
    """13.5 x 7 m: a 2.3 x 2.7 m kitchen, an opening on each inside wall and a window mid each outside wall. The short run
    took the one window-free corner the 195 cm fridge needs; now the fridge stands there first (the plain steps, no
    downgrade: the kitchen run itself must manage)."""
    fp = fp_of([(0, 0), (1350, 0), (1350, 700), (0, 700)])
    rng = random.Random(seed)
    plan = L.plan(fp, P.choose(fp.area_m2), rng)
    doors = D.connect(plan, rng)
    wins = O.windows(plan, doors, rng)
    places, fails = FU.furnish(plan, doors, wins, rng)
    assert not fails, fails
    k = next(r for r in plan.rooms if r.type == "Kitchen")
    assert {"fridge", "sink", "stove"} <= {C.ITEMS[p.item].kind for p in places if p.room == k.id}
    check_placements(plan, doors, wins, places)


@pytest.mark.parametrize("w, h, seed", [(600, 1400, 1), (750, 1200, 1), (800, 1000, 1), (850, 800, 1)])
def test_kitchen_counters_are_never_slivers(w, h, seed):
    """A stretch a little longer than its appliances used to get a 10-20 cm counter (and wall cabinet) to fill it: the
    solver's scale fell below its 0.5 limit and the result was taken anyway. The leftover is now an empty gap."""
    plan, doors, wins, places, fails = furnished([(0, 0), (w, 0), (w, h), (0, h)], seed)
    assert not fails, fails
    narrow = [round(p.w, 1) for p in places if p.item in ("Counter", "UpperCab_60", "UpperCab_80") and p.w < 30.0 - 1e-6]
    assert not narrow, narrow


def _huge_fridge(monkeypatch):
    from dataclasses import replace
    monkeypatch.setitem(C.ITEMS, "Fridge", replace(C.ITEMS["Fridge"], w=900.0))


def test_a_failed_kitchen_run_leaves_the_room_as_it_was(monkeypatch):
    """A kitchen run that cannot be placed reports False and takes nothing with it: no pieces, no floor blocked for the
    pieces that come after it (its three-piece fallback used to leave the sink and stove it had tried in `blocked`)."""
    _huge_fridge(monkeypatch)
    rng = random.Random(1)
    plan = L.plan(fp_of([(0, 0), (1050, 0), (1050, 800), (0, 800)]), P.choose(84.0), rng)
    doors = D.connect(plan, rng)
    wins = O.windows(plan, doors, rng)
    room = next(r for r in plan.rooms if r.type == "Kitchen")
    ctx = FU.RoomCtx(room, plan, doors, wins, random.Random(1))
    before = (list(ctx.blocked), list(ctx.soft))
    out = []
    assert FU.kitchen_run(ctx, out) is False
    assert out == [] and (ctx.blocked, ctx.soft) == before


def test_a_missing_required_piece_is_reported_not_forced(monkeypatch):
    """A room too small for a required group gets a failure in the Summary and keeps every other rule (Review Focus 4)."""
    _huge_fridge(monkeypatch)
    plan, doors, wins, places, fails = furnished([(0, 0), (1050, 0), (1050, 800), (0, 800)], 1)
    assert any("no kitchen_run" in f for f in fails), fails
    assert not any(p.item == "Fridge" for p in places)
    check_placements(plan, doors, wins, places)


def test_another_seed_gives_a_valid_different_furnishing():
    """Same footprint, another seed: still every rule kept, but not the same house (Review Focus 5)."""
    got = [furnished([(0, 0), (1050, 0), (1050, 800), (0, 800)], seed) for seed in (1, 2)]
    for plan, doors, wins, places, fails in got:
        assert not fails, fails
        check_placements(plan, doors, wins, places)
    a, b = ([(p.item, round(p.x, 1), round(p.y, 1), p.yaw) for p in g[3]] for g in got)
    assert a != b


def test_kitchen_run_uses_the_grammar():
    rng = random.Random(1)
    plan = L.plan(fp_of([(0, 0), (1300, 0), (1300, 900), (0, 900)]), P.choose(117.0), rng)
    doors = D.connect(plan, rng)
    wins = O.windows(plan, doors, rng)
    places, fails = FU.furnish(plan, doors, wins, rng)
    k = next(r for r in plan.rooms if r.type == "Kitchen")
    run = [p for p in places if p.room == k.id and p.group == "kitchen_run"]
    kinds = [C.ITEMS[p.item].kind for p in run]
    assert {"fridge", "sink", "stove"} <= set(kinds)
    assert kinds.count("counter") >= 1


def test_deterministic():
    def run(seed):
        rng = random.Random(seed)
        plan = L.plan(fp_of([(0, 0), (1050, 0), (1050, 800), (0, 800)]), P.choose(84.0), rng)
        doors = D.connect(plan, rng)
        wins = O.windows(plan, doors, rng)
        return [(p.item, round(p.x, 3), round(p.y, 3), p.yaw) for p in FU.furnish(plan, doors, wins, rng)[0]]
    assert run(4) == run(4)


def test_catalog_parts_fit_their_items():
    for name, it in C.ITEMS.items():
        assert it.w > 0 and it.d > 0 and it.h > 0, name
        assert it.parts, name
        for shape, (cx, cy, cz), (sx, sy, sz), mat in it.parts:
            assert shape in ("cube", "cyl", "sphere"), name
            assert -it.w / 2 - 1e-6 <= cx - sx / 2 and cx + sx / 2 <= it.w / 2 + 1e-6, (name, "x")
            assert -it.d / 2 - 1e-6 <= cy - sy / 2 and cy + sy / 2 <= it.d / 2 + 1e-6, (name, "y")
            assert cz - sz / 2 >= -1e-6, (name, "z")
            assert mat in C.MATERIAL_KEYS, (name, mat)


def test_catalog_real_mesh_variants_fit_their_items():
    """The StarterContent variants (spec §4.9): each part a primitive or a measured REAL mesh (own materials), inside the
    item's box; every item keeps its primitive recipe as the fallback."""
    real = {name: it for name, it in C.ITEMS.items() if it.mesh}
    assert set(real) >= {"Sofa", "Sofa_Small", "Armchair", "Table_2", "Plant"}
    for name, it in real.items():
        assert it.parts and any(p[0] in C.REAL for p in it.mesh), name
        for shape, (cx, cy, cz), (sx, sy, sz), mat in it.mesh:
            assert shape in ("cube", "cyl", "sphere") or shape in C.REAL, (name, shape)
            assert (mat == "") if shape in C.REAL else (mat in C.MATERIAL_KEYS), (name, mat)
            assert -it.w / 2 - 1e-6 <= cx - sx / 2 and cx + sx / 2 <= it.w / 2 + 1e-6, (name, "x")
            assert -it.d / 2 - 1e-6 <= cy - sy / 2 and cy + sy / 2 <= it.d / 2 + 1e-6, (name, "y")
            assert cz - sz / 2 >= -1e-6 and cz + sz / 2 <= it.h + 1e-6, (name, "z")
    for path, lo, hi, yaw in C.REAL.values():
        assert path.startswith("/Game/StarterContent/") and all(b > a for a, b in zip(lo, hi)) and yaw % 90.0 == 0.0
