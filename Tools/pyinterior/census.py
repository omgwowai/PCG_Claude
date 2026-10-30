"""PyInterior failure census: every rectangle on a fine grid through the stage's chain (interior.house), counting failures
and kitchen modules narrower than 30 cm. Run it before and after changing a rule table -- the test sweep steps 150 cm and
misses the odd footprint a 50 cm grid finds (the review's 13.5 x 7 m kitchen).

--storeys: multi-storey houses through interior.storeys (spec 2026-10-29 §10.3) -- two floors 6-16 x 6-12 m (step 100),
three floors 5-8 x 9-14 m, two floors with the upper one set back 200 / 300 / 400 cm at the front, the back or a side;
three seeds each. A failure is a building that fails storeys.validate (or, when it is left with one floor, a single-floor
house that fails); a dropped floor is listed, not counted (the spec's report); the slowest plans are listed.

Usage: python Tools/pyinterior/census.py [--step 50] [--seeds 3]   (about 3 minutes at the defaults)
       python Tools/pyinterior/census.py --storeys [--seeds 3]     (about 6 minutes)"""
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
from pypcg.interior import storeys as S  # noqa: E402

NARROW = 30.0                # a counter or wall cabinet narrower than this is a sliver
PARAMS = {"WallHeight": 270.0, "ExteriorWall": 25.0, "InteriorWall": 12.0, "Grid": 50.0, "Floors": 0, "StairType": "Auto",
          "Mirror": False, "Furnish": True}


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


def _rect(w, h, x0=0.0, y0=0.0):
    return [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]


def _splines(outlines, H_=300.0):
    """World splines for an actor at the origin, yaw 0 (local x = world y, local y = -world x), floor k raised k x H."""
    return [[(-y, x, k * H_) for x, y in o] for k, o in enumerate(outlines)]


def storey_cases():
    """[(name, outlines)]: the census houses."""
    out = []
    for w in range(600, 1601, 100):
        for h in range(600, 1201, 100):
            out.append(("2F %dx%d" % (w, h), [_rect(w, h)] * 2))
    for w in range(500, 801, 100):
        for h in range(900, 1401, 100):
            out.append(("3F %dx%d" % (w, h), [_rect(w, h)] * 3))
    for w in range(800, 1601, 200):
        for h in range(700, 1201, 200):
            for sb in (200, 300, 400):
                out.append(("front%d %dx%d" % (sb, w, h), [_rect(w, h), _rect(w, h - sb, 0, sb)]))
                out.append(("back%d %dx%d" % (sb, w, h), [_rect(w, h), _rect(w, h - sb)]))
                out.append(("side%d %dx%d" % (sb, w, h), [_rect(w, h), _rect(w - sb, h)]))
    return out


def storey_census(seeds=3):
    """(plans, [(case, seed, failures)], [(case, seed, dropped)], [(seconds, case, seed)] slowest first)"""
    n, bad, drops, times = 0, [], [], []
    for name, outlines in storey_cases():
        for seed in range(1, seeds + 1):
            t = time.perf_counter()
            b = S.plan_building(_splines(outlines), (0.0, 0.0, 0.0), 0.0, PARAMS, random.Random(seed))
            fails = S.validate(b) if b.floors else []
            if not b.floors and b.fps:
                # one floor left: the stage plans it as a single-floor house
                plan, _d, _w, _p, f = H.plan_house(b.fps[0], P.choose(b.fps[0].area_m2), random.Random(seed))
                fails = list(plan.failures) + list(f)
            times.append((time.perf_counter() - t, name, seed))
            n += 1
            if fails:
                bad.append((name, seed, fails[:2]))
            if b.dropped:
                drops.append((name, seed, b.dropped))
    times.sort(reverse=True)
    return n, bad, drops, times


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=50)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--storeys", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    if a.storeys:
        n, bad, drops, times = storey_census(a.seeds)
        print("buildings %d, failing %d, with a dropped floor %d, %.0f s; slowest %.2f s (%s, seed %d)" % (
            n, len(bad), len(drops), time.time() - t0, times[0][0], times[0][1], times[0][2]))
        for b in bad[:40]:
            print("  failing", b)
        for d in drops:
            if d[1] == 1:
                print("  dropped", d[0], "--", "; ".join(d[2]))
        for t in times[:5]:
            print("  slow %.2f s %s seed %d" % t)
        sys.exit(1 if bad else 0)
    n, bad, slivers = census(a.step, a.seeds)
    print("plans %d, failing %d, narrow kitchen modules %d, %.0f s" % (n, len(bad), len(slivers), time.time() - t0))
    for b in bad[:40]:
        print("  failing", b)
    for s in slivers[:20]:
        print("  narrow", s)
    sys.exit(1 if bad or slivers else 0)


if __name__ == "__main__":
    main()
