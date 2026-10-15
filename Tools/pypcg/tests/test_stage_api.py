import json
import os
import random
import subprocess
import sys
import types

import pytest

from pypcg import geo, stage_api
from pypcg.geo import Polygon
from pypcg.stage_api import Param, StageError


def stub(**kw):
    m = types.SimpleNamespace(__name__="pypcg.stages.s09_stub", STAGE=9, DOC="d", RANDOM=True,
                              PARAMS={"A": 1.5, "B": Param(3, "tip", category="Grid"), "C": True, "D": "x"},
                              INPUTS={"In": "any"}, OUTPUTS=("Out",),
                              run=lambda inputs, params, ctx: {"Out": [(Polygon([(0, 0), (1, 0), (0, 1)]), ["Out"])]})
    for k, v in kw.items():
        setattr(m, k, v)
    return m


def test_param_specs_put_seed_first_and_infer_types():
    assert stage_api.param_specs(stub()) == [
        ("Seed", "Int32", 42, "Random seed of this step; the step number is mixed in.", "", ""),
        ("A", "Double", 1.5, "", "", ""), ("B", "Int32", 3, "tip", "", "Grid"),
        ("C", "Bool", True, "", "", ""), ("D", "String", "x", "", "", "")]


def test_seed_is_reserved():
    with pytest.raises(StageError):
        stage_api.param_specs(stub(PARAMS={"Seed": 1}))


def test_execute_reports_param_mismatch():
    params = stage_api.defaults(stub())
    params.pop("A")
    params["Renamed"] = 2.0
    with pytest.raises(StageError) as e:
        stage_api.execute(stub(), {"In": []}, params, None)
    assert "missing ['A']" in str(e.value) and "Renamed" in str(e.value)


def test_execute_requires_every_input_pin():
    with pytest.raises(StageError) as e:
        stage_api.execute(stub(), {}, stage_api.defaults(stub()), None)
    assert "In" in str(e.value)


def test_execute_checks_outputs():
    bad_pin = stub(run=lambda i, p, c: {"Nope": []})
    with pytest.raises(StageError):
        stage_api.execute(bad_pin, {"In": []}, stage_api.defaults(bad_pin), None)
    bad_value = stub(run=lambda i, p, c: {"Out": [("not a value", ["Out"])]})
    with pytest.raises(StageError):
        stage_api.execute(bad_value, {"In": []}, stage_api.defaults(bad_value), None)


def test_execute_rejects_a_string_as_the_tag_list():
    m = stub(run=lambda i, p, c: {"Out": [(Polygon([(0, 0), (1, 0), (0, 1)]), "Out")]})
    with pytest.raises(StageError):
        stage_api.execute(m, {"In": []}, stage_api.defaults(m), None)


def test_execute_passes_params_without_seed_and_a_seeded_rng():
    seen = {}

    def run(inputs, params, ctx):
        seen.update(params=params, draw=ctx.rng.random(), seed=ctx.seed)
        return {}
    m = stub(run=run)
    stage_api.execute(m, {"In": []}, dict(stage_api.defaults(m), Seed=5), None)
    assert "Seed" not in seen["params"] and seen["seed"] == 5
    assert seen["draw"] == random.Random("5:9").random()


def test_ctx_rng_is_session_independent():
    code = ("import sys; sys.path.insert(0, %r); from pypcg import stage_api; "
            "print(repr(stage_api.Ctx(6, 42, None).rng.random()))" % os.path.join(stage_api.REPO, "Content", "Python"))
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONHASHSEED=s)).stdout for s in ("1", "2")}
    assert len(outs) == 1 and outs.pop().strip() == repr(random.Random("42:6").random())


def test_record_writes_inputs_params_and_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_api, "RUNS_DIR", str(tmp_path))
    m = stub()
    inputs = {"In": [(Polygon([(0, 0), (1, 0), (0, 1)]), frozenset({"Lots"}))]}
    params = stage_api.defaults(m)
    outputs, ctx = stage_api.execute(m, inputs, params, None)
    path = stage_api.record(m, inputs, params, outputs, 0.5, ctx)
    rec = json.load(open(path, encoding="utf-8"))
    assert rec["stage"] == 9 and rec["params"]["Seed"] == 42 and rec["seconds"] == 0.5
    assert rec["inputs"]["In"][0][1] == ["Lots"] and rec["outputs"]["Out"][0][1] == ["Out"]
    assert geo.from_json(rec["inputs"]["In"][0][0]) == inputs["In"][0][0]
