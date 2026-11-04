import numpy as np
import pytest

import gen_starmap
from weather_ref import scenario as SC

REC = {"a": {"rig": {"sun_lux": 10.0, "fog_density": 0.02, "sun_rotation": [-78.4, 0.0, 0.0]},
             "orchestrator": {"active_type": "Clear"}},
       "b": {"rig": {"sun_lux": 0.7, "fog_density": 0.04, "sun_rotation": [-31.6, 0.0, 0.0]},
             "orchestrator": {"active_type": "Overcast"}}}
TH = {"tol": 0.5, "ratio": 0.5}


def test_resolve_follows_dotted_paths_and_list_indices():
    assert SC.resolve(REC, "a.rig.sun_rotation.0") == -78.4
    with pytest.raises(KeyError):
        SC.resolve(REC, "c.rig.sun_lux")


def test_every_check_kind():
    def ok(check):
        return SC.evaluate(dict(check, name="n"), REC, TH)[0]
    assert ok({"kind": "near", "value": "a.rig.sun_rotation.0", "target": -78.0, "tol": "@tol"})
    assert not ok({"kind": "near", "value": "a.rig.sun_rotation.0", "target": -77.0, "tol": "@tol"})
    assert ok({"kind": "ratio_below", "value": "b.rig.sun_lux", "ref": "a.rig.sun_lux", "max_ratio": "@ratio"})
    assert ok({"kind": "greater", "value": "b.rig.fog_density", "ref": "a.rig.fog_density"})
    assert ok({"kind": "less", "value": "a.rig.fog_density", "ref": "b.rig.fog_density"})
    assert ok({"kind": "equal_to", "value": "a.rig.sun_lux", "ref": "a.rig.sun_lux", "tol": 1e-9})
    assert ok({"kind": "equals", "value": "b.orchestrator.active_type", "literal": "Overcast"})
    assert ok({"kind": "at_least", "value": "a.rig.sun_lux", "min": 9.0})
    assert ok({"kind": "at_most", "value": "b.rig.sun_lux", "max": 1.0})


def test_failures_and_missing_records_are_reported_by_name():
    out = SC.run_checks([{"name": "bad", "kind": "at_most", "value": "a.rig.sun_lux", "max": 1.0},
                         {"name": "gone", "kind": "at_least", "value": "zzz.rig.sun_lux", "min": 0.0}], REC, TH)
    assert out["passed"] == 0 and out["failed"] == ["bad", "gone"] and "zzz" in out["results"][1]["detail"]


def test_scenario_files_are_consistent():
    doc, th = SC.load_scenarios(), SC.load_thresholds()
    assert SC.problems(doc, th) == []
    assert len(doc["scenarios"]["m0_look"]["checks"]) == 15


def test_problems_catch_unknown_kinds_records_and_thresholds():
    doc = {"scenarios": {"s": {"milestone": "M0", "steps": [{"record": "r"}, {"jump": 1}],
                               "checks": [{"name": "c", "kind": "near", "value": "q.x", "target": 0, "tol": "@nope"},
                                          {"name": "c", "kind": "wobble", "value": "r.x"}]}}}
    found = SC.problems(doc, {})
    assert any("jump" in p for p in found) and any("q.x" in p for p in found)
    assert any("@nope" in p for p in found) and any("wobble" in p for p in found) and any("duplicate" in p for p in found)


def test_starmap_is_deterministic_dark_and_starry():
    a, b = gen_starmap.make_starmap(256, 128, seed=7), gen_starmap.make_starmap(256, 128, seed=7)
    assert a.shape == (128, 256, 3) and a.dtype == np.uint8 and (a == b).all()
    assert int((a.max(axis=2) > 200).sum()) >= 20 and float(np.median(a)) < 20.0
