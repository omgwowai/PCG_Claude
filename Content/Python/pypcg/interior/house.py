"""PyInterior's chain in one call (spec 2026-10-28 §3): plan -> doors -> windows -> furnish, a plan accepted only when every
required group of furniture is placed. A house whose kitchen (say) cannot hold its run steps down to the next program
variant, as a room below its minimum size does inside the layout; the steps draw from one rng, so a house that furnishes
first time is exactly what calling the steps one by one gives. Pure."""
from pypcg.interior import doors as D
from pypcg.interior import furnish as FU
from pypcg.interior import layout as L
from pypcg.interior import openings as O

RETRIES = 3                  # further variants tried after the first plan's furniture failed


def plan_house(fp, program, rng, walls=None, mirror=False, furnish=True):
    """(plan, doors, wins, places, fails): the first variant of `program` (program.fallbacks) whose required furniture all
    fits; when none of the next RETRIES does, the first attempt with its failures reported."""
    first, skip = None, set()
    for _ in range(RETRIES + 1):
        plan = L.plan(fp, program, rng, walls, mirror=mirror, skip=skip)
        if first is not None and L.NO_FIT in plan.failures:
            break                                         # no variant left: keep the first plan and its report
        doors = D.connect(plan, rng)
        wins = O.windows(plan, doors, rng)
        places, fails = FU.furnish(plan, doors, wins, rng) if furnish else ([], [])
        if not fails or L.NO_FIT in plan.failures:
            return plan, doors, wins, places, fails
        first = first or (plan, doors, wins, places, fails)
        skip.add(plan.program)
    return first
