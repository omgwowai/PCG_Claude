"""PyInterior's chain in one call (pypcg.interior.house): a plan is accepted only when every required group of furniture
fits; otherwise the house steps down to the next program variant (review finding 1)."""
import random
from dataclasses import replace

import pytest

from pypcg.interior import catalog as C
from pypcg.interior import doors as D
from pypcg.interior import furnish as FU
from pypcg.interior import house as H
from pypcg.interior import layout as L
from pypcg.interior import openings as O
from pypcg.interior import program as P

from test_interior_layout import fp_of, rect


# narrow 5.5 m houses whose first plan has a 2.5 x 2 m kitchen with a 1.8 m opening on each inside wall and a window on each
# outside wall: no corner left for the run once the fridge stands (the 50 cm census of the review)
@pytest.mark.parametrize("w, h, seed", [(1500, 550, 2), (1900, 550, 1), (1950, 550, 2)])
def test_an_unfurnishable_kitchen_steps_down_a_variant(w, h, seed):
    fp = fp_of(rect(w, h))
    first = L.plan(fp, P.choose(fp.area_m2), random.Random(seed))
    plan, doors, wins, places, fails = H.plan_house(fp, P.choose(fp.area_m2), random.Random(seed))
    assert not fails, fails
    assert plan.program != first.program and plan.program.size <= first.program.size
    for r in plan.rooms:
        if r.type in ("Kitchen", "Main"):
            kinds = {C.ITEMS[p.item].kind for p in places if p.room == r.id}
            assert {"fridge", "sink", "stove"} <= kinds, (r.type, sorted(kinds))


def test_a_house_that_furnishes_first_time_is_unchanged():
    """The chain draws the same numbers as the steps called one by one, so every house that was fine stays as it was."""
    fp = fp_of(rect(1050, 800))
    rng = random.Random(3)
    plan = L.plan(fp, P.choose(fp.area_m2), rng)
    doors = D.connect(plan, rng)
    wins = O.windows(plan, doors, rng)
    places, _fails = FU.furnish(plan, doors, wins, rng)
    got = H.plan_house(fp, P.choose(fp.area_m2), random.Random(3))
    assert [(r.type, r.rect) for r in got[0].rooms] == [(r.type, r.rect) for r in plan.rooms]
    assert [(p.item, p.x, p.y, p.yaw) for p in got[3]] == [(p.item, p.x, p.y, p.yaw) for p in places]


def test_when_no_variant_furnishes_the_first_attempt_is_reported(monkeypatch):
    """Every variant fails the same way (a fridge no kitchen can hold): the first plan comes back with its failure, not a
    studio and not the 'no program fits' plan."""
    monkeypatch.setitem(C.ITEMS, "Fridge", replace(C.ITEMS["Fridge"], w=900.0))
    fp = fp_of(rect(1050, 800))
    plan, doors, wins, places, fails = H.plan_house(fp, P.choose(fp.area_m2), random.Random(1))
    assert plan.program.name == "TwoBed" and any("no kitchen_run" in f for f in fails)


def test_without_furniture_the_first_plan_is_taken():
    fp = fp_of(rect(1900, 550))
    plan, doors, wins, places, fails = H.plan_house(fp, P.choose(fp.area_m2), random.Random(1), furnish=False)
    assert places == [] and fails == [] and plan.program == L.plan(fp, P.choose(fp.area_m2), random.Random(1)).program
