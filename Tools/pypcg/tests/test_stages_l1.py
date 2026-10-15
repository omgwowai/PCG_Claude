"""L1 gate: every stage file on disk reproduces its official graph exactly (spec 3.6)."""
import json
import os

import pytest

from pypcg import compare, ir, stages
from pypcg.profiles import official
import reference_drafts

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LIB = json.load(open(os.path.join(REPO, "Content", "Python", "pypcg", "library.json"), encoding="utf-8"))
STAGE_DIR = os.path.join(REPO, "Tools", "pypcg", "reference_drafts")


@pytest.mark.parametrize("n", [s[0] for s in stages.STAGES], ids=[s[2] for s in stages.STAGES])
def test_stage_matches_official(n):
    module = stages.entry(n)[2]
    if not os.path.exists(os.path.join(STAGE_DIR, module + ".py")):
        pytest.skip("not written yet")
    snap = ir.load(os.path.join(REPO, "Tools", "pypcg", "official_ir", stages.name(n) + ".json"))
    diffs = compare.diff(reference_drafts.graph(n).to_ir(official), snap, LIB["fresh_seeds"])
    assert diffs == [], "\n" + compare.format_diffs(diffs)


@pytest.mark.parametrize("n", [s[0] for s in stages.STAGES], ids=[s[2] for s in stages.STAGES])
def test_stage_has_no_unsorted_step(n):
    module = stages.entry(n)[2]
    path = os.path.join(STAGE_DIR, module + ".py")
    if not os.path.exists(path):
        pytest.skip("not written yet")
    if "CODEGEN DRAFT" in open(path, encoding="utf-8").read():
        pytest.skip("draft; curated in Tasks 9-17")
    steps = {x["step"] for x in reference_drafts.graph(n).to_ir(official)["nodes"] if x["name"] not in ir.IO_NODES}
    assert None not in steps and not any(s.startswith("0 ") for s in steps)
