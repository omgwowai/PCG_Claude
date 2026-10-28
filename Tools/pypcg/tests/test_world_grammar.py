import random

import pytest

from pypcg.world import grammar as G

W = {"S": 400.0, "L": 500.0, "P": 50.0, "D": 300.0, "A": 100.0, "B": 200.0}
SCALABLE = {"S", "L", "D", "A", "B"}


def total(res, widths=W):
    return sum(widths[s] * (res["scale"] if s in SCALABLE else 1.0) for s in res["symbols"])


def test_parse_sequences_repeats_and_choices():
    parts = G.parse(" [S][P,L]* [P,S]+ {A:2,B:1}3 ")
    assert [p.symbols for p in parts] == [("S",), ("P", "L"), ("P", "S"), ()]
    assert [p.rep for p in parts] == [1, "*", "+", 3]
    assert parts[3].choices == (("A", 2.0), ("B", 1.0))


@pytest.mark.parametrize("bad", ["[S", "S", "[S]x", "{A:0}", "[]", "[S]*2"])
def test_parse_rejects_malformed_grammar(bad):
    with pytest.raises(ValueError):
        G.parse(bad)


@pytest.mark.parametrize("length", [450.0, 900.0, 955.0, 1200.0, 1730.0, 2400.0, 3333.0])
def test_solve_fills_the_wall_exactly(length):
    res = G.solve(G.parse("[S][P,S]*"), length, W, SCALABLE)
    assert res["ok"] and abs(total(res) - length) < 1e-6
    assert 0.85 <= res["scale"] <= 1.2
    assert res["symbols"][0] == "S" and res["symbols"][-1] == "S"


def test_solve_prefers_the_scale_closest_to_one():
    res = G.solve(G.parse("[S][P,S]*"), 1300.0, W, SCALABLE)       # 3 bays: 3 x 400 + 2 x 50 = 1300 exactly
    assert res["symbols"] == ["S", "P", "S", "P", "S"] and abs(res["scale"] - 1.0) < 1e-9


def test_two_stars_share_the_count_so_the_door_is_centred():
    for length in (1500.0, 2300.0, 3100.0):
        res = G.solve(G.parse("[S,P]*[D][P,S]*"), length, W, SCALABLE)
        i = res["symbols"].index("D")
        assert abs(i - (len(res["symbols"]) - 1 - i)) <= 2, (length, res["symbols"])


def test_plus_means_at_least_once_and_numbers_are_fixed():
    res = G.solve(G.parse("[P,S]+"), 300.0, W, SCALABLE, smin=0.1)
    assert res["symbols"].count("S") >= 1
    res = G.solve(G.parse("[A]3[P]"), 350.0, W, SCALABLE)
    assert res["symbols"] == ["A", "A", "A", "P"] and abs(res["scale"] - 1.0) < 1e-9


def test_no_fit_reports_not_ok():
    res = G.solve(G.parse("[S][P,S]*"), 200.0, W, SCALABLE)       # one bay would need scale 0.5
    assert not res["ok"]


def test_slack_keeps_the_bays_in_range_and_leaves_plain_wall():
    """600 cm between corners: one 400 bay would need 1.5, two need 0.69 -- with slack the bay keeps 1.2 and 120 cm
    is left for plain wall (an exact fit always wins over slack)."""
    res = G.solve(G.parse("[S][P,S]*"), 600.0, W, SCALABLE, slack=True)
    assert res["ok"] and res["symbols"] == ["S"] and res["scale"] == 1.2 and abs(res["slack"] - 120.0) < 1e-9
    res = G.solve(G.parse("[S][P,S]*"), 1300.0, W, SCALABLE, slack=True)
    assert res["slack"] == 0.0 and abs(res["scale"] - 1.0) < 1e-9


def test_stochastic_choice_follows_the_seed_and_the_weights():
    parts = G.parse("{A:3,B:1}*")
    a = G.solve(parts, 2000.0, W, SCALABLE, rng=random.Random(4))
    b = G.solve(parts, 2000.0, W, SCALABLE, rng=random.Random(4))
    assert a == b and set(a["symbols"]) <= {"A", "B"}
    picks = [s for seed in range(40) for s in G.solve(parts, 3000.0, W, SCALABLE, rng=random.Random(seed))["symbols"]]
    assert picks.count("A") > 2 * picks.count("B")


def test_positions_follow_the_symbols():
    res = G.solve(G.parse("[S][P,S]*"), 1350.0, W, SCALABLE)
    xs = G.positions(res, W, SCALABLE)
    assert xs[0] == (0.0, W["S"] * res["scale"])
    assert all(abs(a[1] - b[0]) < 1e-9 for a, b in zip(xs, xs[1:])) and abs(xs[-1][1] - 1350.0) < 1e-6


def test_vertical_expansion():
    parts = G.parse("[G][TR][N][U]*[RT]")
    assert G.expand(parts, 0) == ["G", "TR", "N", "RT"]
    assert G.expand(parts, 2) == ["G", "TR", "N", "U", "U", "RT"]
    assert G.expand(G.parse("[G][U]+"), 0) == ["G", "U"]
