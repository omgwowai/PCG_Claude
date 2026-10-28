import random

import pytest

from pypcg.world import bdf, grammar as G, kit as K


def test_seven_style_codes_with_city_sample_tooltips():
    assert len(bdf.STYLES) == 7
    for code, st in bdf.STYLES.items():
        assert len(code) == 3 and st["family"] in K.FAMILIES
        assert {"look", "type", "era"} <= set(st["tooltip"]), code
        assert set(st["roof"]["tints"]) <= set(K.TINTS["Roof"]), code


@pytest.mark.parametrize("code", sorted(bdf.STYLES))
def test_vertical_grammar_gives_the_asked_number_of_storeys(code):
    st = bdf.STYLES[code]
    fam = K.FAMILIES[st["family"]]
    lo, hi = st["floors"]
    for n in range(lo, hi + 1):
        levels = bdf.levels(code, n)
        assert all(lv in fam["levels"] for lv in levels), (code, levels)
        assert sum(fam["levels"][lv]["storey"] for lv in levels) == n, (code, n, levels)
    assert bdf.levels(code, hi + 3) == bdf.levels(code, hi) and bdf.levels(code, 0) == bdf.levels(code, lo)


@pytest.mark.parametrize("code", sorted(bdf.STYLES))
def test_every_wall_from_the_minimum_to_forty_metres_has_a_facade(code):
    st = bdf.STYLES[code]
    fam = K.FAMILIES[st["family"]]
    for length in range(int(st["min_wall"]), 4001, 25):
        res = bdf.bays(code, float(length), random.Random(length))
        assert res["ok"] and bdf.BAY_SCALE[0] <= res["scale"] <= bdf.BAY_SCALE[1], (code, length, res)
        assert abs(bdf.span(res, code) + res["slack"] - (length - 2.0 * fam["end"])) < 1e-6
        assert 0.0 <= res["slack"] < 0.7 * max(fam["bays"].values()), (code, length, res)


@pytest.mark.parametrize("code", sorted(c for c in bdf.STYLES if bdf.FRONTS[bdf.STYLES[c]["family"]]))
@pytest.mark.parametrize("use", ["house", "shop"])
def test_every_front_gets_one_door(code, use):
    st = bdf.STYLES[code]
    end = K.FAMILIES[st["family"]]["end"]
    for length in range(int(st["min_wall"]), 3001, 25):
        res = bdf.front(code, use, length - 2.0 * end, random.Random(length))
        assert res["ok"], (code, use, length, res)
        assert abs(bdf.span(res, code) + res["slack"] - (length - 2.0 * end)) < 1e-6
        assert sum(s in ("D", "H") for s in res["symbols"]) == 1, (code, use, length, res["symbols"])


def test_long_walls_use_the_richer_grammars():
    """FLengths: a short wall gets F0 (equal bays), longer ones F1 / F2 (large bays in the middle, alternating)."""
    short = bdf.bays("PLA", 1000.0, random.Random(1))["symbols"]
    long = bdf.bays("PLA", 3000.0, random.Random(1))["symbols"]
    assert "L" not in short and "L" in long and "S" in long
