"""The distilled stage-6 seed study (Tools/pypcg/data/s06_seed_study.json) is what the two stage-6 rows
of docs/pypcg-v2-thresholds.md cite, so it must hold the numbers those rows quote, and the study must
name the method that re-derives them."""
import json
import os

from pypcg import stage_api

PATH = os.path.join(stage_api.REPO, "Tools", "pypcg", "data", "s06_seed_study.json")
STUDY = json.load(open(PATH, encoding="utf-8"))
TAGS = ("CollectorRoads", "localRoads", "UndividableDistricts", "SmallDistricts", "MediumDistricts", "LargeDistricts")


def test_the_study_is_self_contained():
    assert STUDY["stage"] == 6 and STUDY["stage_module"] == "pypcg.stages.s06_districts"
    assert STUDY["seeds"] == list(range(1, 151))
    assert "run_unreal_script" in STUDY["_"] and "pyg_probe_t9_seeds.py" in STUDY["_"]
    assert "slim_7.run.json" in STUDY["source_run_record"]         # the inputs and parameters it replays
    assert "demo_overrides" in STUDY["graph_params"]
    assert set(STUDY["per_tag"]) == set(TAGS)


def _round(x):
    return round(x, 1)


def test_every_tag_carries_the_metric_its_data_uses():
    for tag in TAGS:
        e = STUDY["per_tag"][tag]
        metric = "length_rel" if tag in ("CollectorRoads", "localRoads") else "area_rel"
        assert metric in e
        s = e[metric]
        assert all(k in s for k in ("n", "min", "median", "max", "p95"))
        assert s["min"] <= s["median"] <= s["max"] and s["n"] >= 142
        assert e["seeds_with_tag"] + e.get("misses", 0) == 150
        assert e["bbox_overshoot_m"]["max"] >= e["bbox_overshoot_m"]["median"] >= 0


def test_the_two_rows_and_the_study_agree():
    """The rows quote CollectorRoads -7.8 %..+24.7 % (median +8.7 %), localRoads -12.8 %..+15.8 %, and the
    worst overshoots LargeDistricts 458 m and UndividableDistricts 1120 m."""
    c, l = STUDY["per_tag"]["CollectorRoads"]["length_rel"], STUDY["per_tag"]["localRoads"]["length_rel"]
    assert (c["min"], c["median"], c["max"]) == (-0.0776, 0.0868, 0.247)
    assert (l["min"], l["max"]) == (-0.1278, 0.158)
    assert _round(STUDY["per_tag"]["LargeDistricts"]["bbox_overshoot_m"]["max"]) == 458.1
    assert _round(STUDY["per_tag"]["UndividableDistricts"]["bbox_overshoot_m"]["max"]) == 1120.4
    assert STUDY["per_tag"]["UndividableDistricts"]["seeds_with_tag"] == 142          # absent from 8 of 150


def test_the_500_m_margin_is_the_smallest_round_one_that_clears_the_seeds():
    """400 m would not clear LargeDistricts' 458 m; 500 m is the first round value that does."""
    present_everywhere = [t for t in TAGS if STUDY["per_tag"][t]["seeds_with_tag"] == 150]
    worst = max(STUDY["per_tag"][t]["bbox_overshoot_m"]["max"] for t in present_everywhere)
    assert 400 < worst <= 500 and int(worst) == 458


def test_the_documented_pass_rates_are_recorded_and_monotone():
    """The length row's rates at limits 0.10 / 0.15 / 0.20 / 0.25, over the median of 5 seeds."""
    rates = STUDY["median_of_5_pass_rate"]
    assert rates["CollectorRoads"] == {"0.10": 0.6212, "0.15": 0.9048, "0.20": 0.9945, "0.25": 1.0}
    assert rates["localRoads"] == {"0.10": 0.9698, "0.15": 1.0, "0.20": 1.0, "0.25": 1.0}
    for tag, row in rates.items():
        seq = [row[k] for k in ("0.10", "0.15", "0.20", "0.25")]
        assert seq == sorted(seq)                                   # a wider limit never passes less often
        assert seq[-1] == 1.0
    assert 0.99 <= rates["CollectorRoads"]["0.20"] < 1.0            # 0.20 is where the tight tag had to land
    assert rates["localRoads"]["0.15"] == 1.0                       # the length check never bound this tag
