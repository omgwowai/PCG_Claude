import json
import os
import random

import pytest

from fakes import FakeOps
from pypcg import geo, stage_api
from pypcg.geo import Spline
from pypcg.stages import s06_districts as S

REPO = stage_api.REPO
CITY = Spline([(-100000.0, -50000.0, 500.0), (100000.0, -50000.0, 500.0), (100000.0, 50000.0, 500.0),
               (-100000.0, 50000.0, 500.0)], closed=True)                       # 2000 x 1000 m, z flattened
ARTERY = Spline([(0.0, -60000.0, 0.0), (0.0, 60000.0, 0.0)])                     # straight, across the middle
PARAMS = dict(stage_api.defaults(S))
PARAMS.pop(stage_api.SEED)
PARAMS.update(Dividable_district_Limit=100000.0, SmallMediumThreshold=300000.0, MediumLargeThreshold=400000.0)


def inputs(city=CITY, arteries=(ARTERY,)):
    return {"City": [(city, frozenset({"City"}))] if city else [], "Arteries": [(a, frozenset()) for a in arteries]}


def half(ring):
    return 0.5


def areas(out, tag):
    return [abs(geo.signed_area(p.outer)) / 1e4 for p, _ in out[tag]]


def test_contract_matches_the_official_graph():
    off = json.load(open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_3_1_1_Districts.json"), encoding="utf-8"))
    defaults = {p["name"]: p["value"] for p in off["params"]}
    assert set(S.PARAMS) == {n for n in defaults if not n.startswith("Debug") and n != "SubDistrictSeed"}
    assert all(S.PARAMS[n].default == defaults[n] for n in S.PARAMS)
    assert set(S.OUTPUTS) == {"ArteryRoads", "CollectorRoads", "localRoads", "UndividableDistricts", "SmallDistricts",
                              "MediumDistricts", "LargeDistricts"}


def test_cut_split_classify_and_conserve_area():
    out = S.districts(inputs(), PARAMS, FakeOps(), half)
    assert sorted(areas(out, "LargeDistricts")) == pytest.approx([500000.0] * 4)          # 2 districts x 2 halves
    assert not out["UndividableDistricts"] and not out["SmallDistricts"] and not out["MediumDistricts"]
    total = sum(sum(areas(out, t)) for t in S.OUTPUTS if t.endswith("Districts"))
    assert total == pytest.approx(2000000.0, rel=1e-9)
    assert len(out["CollectorRoads"]) == 2
    assert len(out["ArteryRoads"]) == 2                                                   # outline + 1 clipped artery
    outline = out["ArteryRoads"][0][0]
    assert outline.closed and all(p[2] == 0.0 for p in outline.points)


def test_classes_follow_the_thresholds():
    p = dict(PARAMS, Dividable_district_Limit=600000.0)
    out = S.districts(inputs(), p, FakeOps(), half)
    assert len(out["UndividableDistricts"]) == 4 and not out["localRoads"]               # nothing is gridded
    p = dict(PARAMS, Dividable_district_Limit=100000.0, SmallMediumThreshold=600000.0)
    assert len(S.districts(inputs(), p, FakeOps(), half)["SmallDistricts"]) == 4


def test_grid_lines_stay_inside_their_district():
    out = S.districts(inputs(), PARAMS, FakeOps(), half)
    rings = [p.outer for p, _ in out["LargeDistricts"]]
    assert out["localRoads"]
    for line, tags in out["localRoads"]:
        mid = [(a + b) / 2 for a, b in zip(line.points[0][:2], line.points[-1][:2])]
        assert any(geo.inside(mid, r) for r in rings) and tags == ["localRoads"]


def test_empty_inputs_give_empty_outputs():
    out = S.districts(inputs(city=None), PARAMS, FakeOps(), half)
    assert all(out[pin] == [] for pin in S.OUTPUTS)
    out = S.districts(inputs(arteries=()), PARAMS, FakeOps(), half)            # no arteries: the city is one district
    assert len(out["CollectorRoads"]) == 1 and sum(len(out[t]) for t in S.OUTPUTS if t.endswith("Districts")) == 2


class SliverOps(FakeOps):
    def cut_with_paths(self, ring, paths):
        return super().cut_with_paths(ring, paths) + [[(0.0, 0.0), (10.0, 0.0), (0.0, 10.0)]]


def test_cut_keeps_only_real_pieces():
    out = S.districts(inputs(), PARAMS, SliverOps(), half)
    assert sum(len(out[t]) for t in S.OUTPUTS if t.endswith("Districts")) == 4


def test_seeded_runs_repeat_and_differ():
    def collectors(seed):
        out, _ = stage_api.execute(S, inputs(), dict(stage_api.defaults(S), Seed=seed, **{k: v for k, v in PARAMS.items()}), FakeOps())
        return [l.points for l, _ in out["CollectorRoads"]]
    assert collectors(5) == collectors(5) and collectors(5) != collectors(6)


def test_split_ratios_stay_in_the_official_range():
    draw = S.ratio_fn(random.Random("x"))
    vals = [draw(None) for _ in range(2000)]
    assert 0.3 <= min(vals) and max(vals) <= 0.7 and min(vals) < 0.31 and max(vals) > 0.69


def test_v1_conservation_refuses_a_city_with_no_area_pieces():
    """A run whose City has area but whose outputs hold no area at all conserves nothing: it used to
    pass because both sides were zero (the City was never compared when no piece existed)."""
    from pypcg.checks import s06 as C
    empty = {p: [] for p in S.OUTPUTS}
    failures = C.check(inputs(), PARAMS, empty, FakeOps())
    assert any("no area piece at all" in x for x in failures)
    assert C.check(inputs(city=None), PARAMS, empty, FakeOps()) == []      # no City: nothing to conserve


def test_v1_checks_pass_on_a_real_run_and_catch_a_wrong_class():
    from pypcg.checks import s06 as C
    out = S.districts(inputs(), PARAMS, FakeOps(), half)
    assert C.check(inputs(), PARAMS, out, FakeOps()) == []
    wrong = dict(out, SmallDistricts=out["LargeDistricts"][:1], LargeDistricts=out["LargeDistricts"][1:])
    assert any("its size says LargeDistricts" in x for x in C.check(inputs(), PARAMS, wrong, FakeOps()))
    lost = dict(out, LargeDistricts=out["LargeDistricts"][1:])
    assert any("add up" in x for x in C.check(inputs(), PARAMS, lost, FakeOps()))


def test_oracle_recovers_the_split_ratios():
    from pypcg.checks import s06 as C
    official = S.districts(inputs(), PARAMS, FakeOps(), lambda ring: 0.37)
    off = {t: [v for v, _ in official[t]] for t in S.OUTPUTS}
    mine = S.districts(inputs(), PARAMS, FakeOps(), half)
    assert C.check(inputs(), PARAMS, mine, FakeOps(), off) == []          # the oracle replays with 0.37
    off["CollectorRoads"] = off["CollectorRoads"][:1]
    assert any(x.startswith("oracle") for x in C.check(inputs(), PARAMS, mine, FakeOps(), off))


def test_flat_keeps_the_outline_measurable_as_a_curve():
    """The outline is a curve: its control-point polyline is 4.3 % shorter than the curve the engine
    measures (5945.4 m against 6213.2 m on the demo city), so flat() must keep the dense polyline."""
    dense = [(float(i), 0.0, 5.0) for i in range(11)]
    curved = Spline([(0.0, 0.0, 5.0), (10.0, 0.0, 5.0)], closed=False, linear=False,
                    tangents=[((0.0, 4.0, 0.0), (0.0, 4.0, 0.0))] * 2, polyline=dense)
    f = S.flat(curved)
    assert f.linear is False and f.tangents == curved.tangents and all(p[2] == 0.0 for p in f.polyline)
    assert len(f.polyline) == len(dense)
    from pypcg.checks import s06 as C
    assert C._length(f) == pytest.approx(geo.path_length(dense))
