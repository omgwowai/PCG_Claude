import json
import os
import types

import pytest

import codegen
from pypcg import compare, dsl, ir, stages
from pypcg.profiles import official

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LIB = json.load(open(os.path.join(REPO, "Content", "Python", "pypcg", "library.json"), encoding="utf-8"))
ROLES_BY_PATH = {p: r for r, p in official.ROLES.items()}


def run(code):
    ns = {"__name__": "generated_stage"}
    exec(compile(code, "generated_stage.py", "exec"), ns)
    return ns["build"]()


@pytest.mark.parametrize("name", stages.names())
def test_draft_of_every_official_graph_round_trips(name):
    snap = ir.load(os.path.join(REPO, "Tools", "pypcg", "official_ir", name + ".json"))
    code = codegen.generate(snap, ROLES_BY_PATH, LIB["fresh_seeds"])
    diffs = compare.diff(run(code).to_ir(official), snap, LIB["fresh_seeds"])
    assert diffs == [], compare.format_diffs(diffs)


def test_unknown_actor_reference_is_an_error():
    snap = ir.load(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_3_1_4_Lots.json"))
    with pytest.raises(KeyError):
        codegen.generate(snap, {}, LIB["fresh_seeds"])


def test_snake_names_are_valid_and_unique():
    used = set()
    names = [codegen.unique(codegen.snake(t), used) for t in ("Get Roads", "Get Roads", "1 · INPUT", "class", "")]
    assert len(set(names)) == len(names)
    assert all(n.isidentifier() for n in names)
