"""PyInterior failure census: every rectangle on a fine grid through the stage's chain (interior.house), counting failures
and kitchen modules narrower than 30 cm. Run it before and after changing a rule table -- the test sweep steps 150 cm and
misses the odd footprint a 50 cm grid finds (the review's 13.5 x 7 m kitchen).

Usage: python Tools/pyinterior/census.py [--step 50] [--seeds 3]   (about 3 minutes at the defaults)"""
import argparse
import os
import random
import sys
import time

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "Content", "Python"))
from pypcg.interior import footprint as F  # noqa: E402
from pypcg.interior import house as H  # noqa: E402
from pypcg.interior import program as P  # noqa: E402

NARROW = 30.0                # a counter or wall cabinet narrower than this is a sliver


def rect_fp(w, h):
    return F.build([(0.0, 0.0, 0.0), (0.0, w, 0.0), (-h, w, 0.0), (-h, 0.0, 0.0)], (0.0, 0.0, 0.0), 0.0)


def census(step=50, seeds=3, max_aspect=4.0):
    """(plans, [(w, h, seed, program, failures)], [(w, h, seed, narrowest module)])"""
    n, bad, slivers = 0, [], []
    for w in range(450, 2001, step):
        for h in range(450, 1401, step):
            if max(w, h) / min(w, h) > max_aspect:
                continue
            fp = rect_fp(w, h)
            if fp is None:
                continue
            for seed in range(1, seeds + 1):
                plan, _doors, _wins, places, fails = H.plan_house(fp, P.choose(fp.area_m2), random.Random(seed))
                n += 1
                fails = list(plan.failures) + list(fails)
                if fails:
                    bad.append((w, h, seed, plan.program.name, fails[:2]))
                mods = [p.w for p in places if p.item in ("Counter", "UpperCab_60", "UpperCab_80")]
                if mods and min(mods) < NARROW:
                    slivers.append((w, h, seed, round(min(mods), 1)))
    return n, bad, slivers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=50)
    ap.add_argument("--seeds", type=int, default=3)
    a = ap.parse_args()
    t0 = time.time()
    n, bad, slivers = census(a.step, a.seeds)
    print("plans %d, failing %d, narrow kitchen modules %d, %.0f s" % (n, len(bad), len(slivers), time.time() - t0))
    for b in bad[:40]:
        print("  failing", b)
    for s in slivers[:20]:
        print("  narrow", s)
    sys.exit(1 if bad or slivers else 0)


if __name__ == "__main__":
    main()
