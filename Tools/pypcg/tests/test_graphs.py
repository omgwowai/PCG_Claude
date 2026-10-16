"""Every slim-graph description builds, wires every Python input, uses every Python output, and
declares Seed first (spec 3, structural check before the editor build)."""
import pytest

from pypcg import graphs, ir, stage_api, stages
from pypcg.profiles import official

ALL = [0] + [s[0] for s in stages.STAGES]


@pytest.mark.parametrize("n", ALL)
def test_graph_description(n):
    if not graphs.exists(n):
        pytest.skip("not ported yet")
    out = graphs.graph(n).to_ir(official)              # raises on an unwired Python input pin
    py = [x for x in out["nodes"] if x["class"] == ir.PYTHON_NODE]
    assert py, "no Python node"
    used = {(src, pin) for x in out["nodes"] for p in x.get("inputs", []) for src, pin in p["edges"]}
    for node in py:
        for pin in node["settings"]["OutputDynamicPins"]:
            assert (node["name"], pin) in used, "Python output %s of %s is wired to nothing" % (pin, node["title"])
    assert out["params"][0]["name"] == stage_api.SEED
    getters = {x["getter_param"] for x in out["nodes"] if x.get("getter_param")}
    assert {p["name"] for p in out["params"]} <= getters, "a parameter without a getter"
