import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import sa_manifest as M


def test_two_shot_names_are_suffixed_by_kind():
    assert M.shot_name(7, "PCG_3_1_2_Roads", "debug") == \
        "sa_stage_07_PCG_3_1_2_Roads_debug.png"
    assert M.shot_name(13, "PCG_3_3_1_Buildings", "geometry") == \
        "sa_stage_13_PCG_3_3_1_Buildings_geometry.png"


def test_status_is_empty_only_for_data_stages_with_zero_geometry():
    # stage 6 is a data stage: zero geometry is expected, not a failure
    assert M.status_for(6, 0, shots_present=True) == "empty"
    # stage 7 with zero geometry is a real problem
    assert M.status_for(7, 0, shots_present=True) == "empty_expected_geometry"
    assert M.status_for(7, 1234, shots_present=True) == "ok"
    assert M.status_for(7, 1234, shots_present=False) == "missing"


def test_build_stages_always_emits_both_kinds_in_order(tmp_path):
    census = {"order": ["PCG_A", "PCG_B"],
              "real_instances": {"1": 0, "2": 55},
              "debug_instances": {"1": 10, "2": 20}}
    cpath = tmp_path / "sa_census.json"
    cpath.write_text(json.dumps(census), encoding="utf-8")
    shots = tmp_path / "shots"
    shots.mkdir()
    for kind in ("debug", "geometry"):
        (shots / M.shot_name(2, "PCG_B", kind)).write_bytes(b"x" * 60000)

    stages = M.build_stages(str(cpath), str(shots),
                            order=["PCG_A", "PCG_B"], min_bytes=50000)
    assert [s["n"] for s in stages] == [1, 2]
    # `s` was undefined here in the brief's version of this test: it was only bound
    # inside the list comprehension above, and comprehension variables do not leak in
    # Python 3. Asserting per stage states the intent (both kinds, in order there).
    for st in stages:
        assert [sh["kind"] for sh in st["shots"]] == ["debug", "geometry"]
    # stage 1 has no files -> both entries carry img_missing, not a crash
    assert "img_missing" in stages[0]["shots"][0]
    assert "img_missing" in stages[0]["shots"][1]
    # stage 2 has both -> both carry a path and a size
    assert stages[1]["shots"][0]["path"].endswith("_debug.png")
    assert stages[1]["shots"][1]["bytes"] > 50000
    assert stages[1]["metrics"]["instances"] == 55
    assert stages[1]["metrics"]["status"] == "ok"


def test_a_too_small_file_counts_as_missing(tmp_path):
    census = {"order": ["PCG_A"], "real_instances": {"1": 5},
              "debug_instances": {"1": 5}}
    cpath = tmp_path / "c.json"
    cpath.write_text(json.dumps(census), encoding="utf-8")
    shots = tmp_path / "shots"
    shots.mkdir()
    (shots / M.shot_name(1, "PCG_A", "debug")).write_bytes(b"x" * 100)
    stages = M.build_stages(str(cpath), str(shots), order=["PCG_A"],
                            min_bytes=50000)
    assert "img_missing" in stages[0]["shots"][0]
