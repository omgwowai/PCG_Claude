"""Regression tests for the six Important findings of the whole-branch review.

Each test names the finding it pins. The five that are unit-testable get one; the
comment-text finding has no test (asserting on a string would prove nothing about the
behaviour), so it is recorded in the ledger as fixed-without-test instead.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import build_pcg_stage_report as R
import sa_manifest as M


# ---------------------------------------------------------------- finding 1 + 12
def test_shot_count_reflects_shots_not_stages_when_files_are_absent(tmp_path):
    """Finding 1: `captured=N` was structurally vacuous.

    A missing shot emitted by sa_manifest carries `img_missing` and NO `path`, so the
    old code appended nothing to `missing` and `n_shot = n_total - len(missing)` came
    out equal to the stage count even when every PNG was gone. Building from an empty
    shots dir must now report zero captured shots.
    """
    census = {"order": ["PCG_A", "PCG_B"], "real_instances": {"1": 1, "2": 2},
              "debug_instances": {"1": 3, "2": 4}}
    cpath = tmp_path / "c.json"
    cpath.write_text(json.dumps(census), encoding="utf-8")
    empty = tmp_path / "shots"
    empty.mkdir()

    stages = M.build_stages(str(cpath), str(empty), order=["PCG_A", "PCG_B"])
    man = {"title": "t", "subtitle": "s", "level": "/Game/X",
           "stages": stages, "footer": "f"}
    doc, _kb, missing = R.build_html_with_stats(man, max_edge=64, quality=50)

    # four shots were asked for, none exist
    assert len(missing) == 4, "each absent shot must be counted, got %r" % (missing,)
    # The stats strip must not claim any capture succeeded.
    assert "<b>4</b><span>张截图</span>" not in doc
    assert "<b>0</b><span>张截图</span>" in doc


def test_shot_count_is_shot_based_when_some_are_present(tmp_path):
    """Finding 12: a stage missing both shots was counted twice in n_shot.

    NB: the two present shots must clear MIN_BYTES or they count as missing, which is
    what the first version of this test got wrong — an 80x60 PNG is a few hundred bytes
    against a 50 KB floor, so stage A read as absent and the assertion failed for a
    reason unrelated to the fix.
    """
    from PIL import Image
    census = {"order": ["PCG_A", "PCG_B"], "real_instances": {"1": 1, "2": 2},
              "debug_instances": {"1": 3, "2": 4}}
    cpath = tmp_path / "c.json"
    cpath.write_text(json.dumps(census), encoding="utf-8")
    shots = tmp_path / "shots"
    shots.mkdir()
    for kind in ("debug", "geometry"):
        p = shots / M.shot_name(1, "PCG_A", kind)
        Image.new("RGB", (80, 60), (1, 2, 3)).save(p)
        p.write_bytes(p.read_bytes() + b"\0" * 60000)   # clear the size floor

    stages = M.build_stages(str(cpath), str(shots), order=["PCG_A", "PCG_B"])
    man = {"title": "t", "subtitle": "s", "level": "/Game/X",
           "stages": stages, "footer": "f"}
    doc, _kb, missing = R.build_html_with_stats(man, max_edge=64, quality=50)

    assert len(missing) == 2, "stage B's two shots, got %r" % (missing,)
    assert all(g == "PCG_B" for g, _k in missing), "only stage B is missing"
    # 4 shots asked for, 2 present
    assert "<b>2</b><span>张截图</span>" in doc


# -------------------------------------------------------------------- finding 3
def test_every_status_the_manifest_can_emit_has_a_label_and_a_style():
    """Finding 3: stage 18 rendered the raw token `empty_expected_geometry`."""
    emitted = set()
    for n in (1, 4, 5, 6, 7, 18):          # data stages and non-data stages
        for inst in (0, 1234):
            for present in (True, False):
                emitted.add(M.status_for(n, inst, shots_present=present))

    for status in emitted:
        assert status in R.STATUS_ZH, "no Chinese label for status %r" % status
        assert R.STATUS_ZH[status] != status, "label for %r is the raw token" % status
    # every chip class the manifest can produce must have a CSS rule in PAGE
    for status in emitted:
        assert ".chip.%s{" % status in R.PAGE or ".chip.%s " % status in R.PAGE, \
            "no CSS rule for .chip.%s" % status


def test_the_empty_non_data_stage_gets_an_explanatory_note(tmp_path):
    """Finding 3: stage 18's card had an empty note, with the reason only in the ledger.

    Driven from the real 18-stage order: the first version of this test used a one-entry
    census, so the stage under test was index 1 — a DATA_ONLY stage — and it asserted
    against the data-stage note rather than the empty-stage one.
    """
    census = {"order": list(M.ORDER), "real_instances": {}, "debug_instances": {}}
    for i, graph in enumerate(M.ORDER, start=1):
        census["real_instances"][str(i)] = 1
        census["debug_instances"][str(i)] = 0
    census["real_instances"]["18"] = 0            # PCG_5_2_OuterForest, the empty one
    census["debug_instances"]["18"] = 667013
    cpath = tmp_path / "c.json"
    cpath.write_text(json.dumps(census), encoding="utf-8")
    shots = tmp_path / "shots"
    shots.mkdir()
    # Create stage 18's two shots so `present` is True and the status is genuinely
    # `empty_expected_geometry` — the real manifest's condition. Without them status is
    # `missing` first, which the note logic used to depend on.
    from PIL import Image
    for kind in ("debug", "geometry"):
        p = shots / M.shot_name(18, "PCG_5_2_OuterForest", kind)
        Image.new("RGB", (80, 60), (1, 2, 3)).save(p)
        p.write_bytes(p.read_bytes() + b"\0" * 60000)

    stages = M.build_stages(str(cpath), str(shots))
    assert len(stages) == 18
    empty = [s for s in stages if s["n"] == 18][0]
    assert empty["metrics"]["status"] == "empty_expected_geometry"
    assert empty["notes"], "the run's only empty stage must carry a note"
    assert "PCG_5_2_OuterForest" in empty["notes"]
    # and the data-only stages keep their own note, not this one
    d1 = [s for s in stages if s["n"] == 1][0]
    assert "数据阶段" in d1["notes"]
    assert d1["notes"] != empty["notes"]


def test_the_empty_stage_note_survives_absent_shots(tmp_path):
    """The note describes the stage, not its PNGs, so it must not vanish when the shots do."""
    census = {"order": list(M.ORDER), "real_instances": {}, "debug_instances": {}}
    for i, graph in enumerate(M.ORDER, start=1):
        census["real_instances"][str(i)] = 1
        census["debug_instances"][str(i)] = 0
    census["real_instances"]["18"] = 0
    census["debug_instances"]["18"] = 667013
    cpath = tmp_path / "c.json"
    cpath.write_text(json.dumps(census), encoding="utf-8")
    shots = tmp_path / "shots"
    shots.mkdir()                                  # deliberately empty

    empty = [s for s in M.build_stages(str(cpath), str(shots)) if s["n"] == 18][0]
    assert empty["metrics"]["status"] == "missing"
    assert "空阶段" in empty["notes"], "the data-driven note must still be present"


def test_the_generated_page_carries_the_footer_prose(tmp_path):
    """A footer function that nothing calls passes its own tests and ships nothing.

    That is exactly what happened: footer_text() was added and tested while main() kept
    emitting an inline footer, so the page had none of the Review Focus content.
    """
    stages = M.build_stages(M.DEFAULT_CENSUS, str(tmp_path))
    man = {"title": "t", "subtitle": "s", "level": "/Game/X",
           "stages": stages, "footer": M.footer_text(stages)}
    doc = R.build_html(man, max_edge=64, quality=50)
    for needle in ("Block grid", "HighWay_2", "missing_visual",
                   "PCG_4_2_CentralPark_Visuals", "288"):
        assert needle in doc, "the page is missing %r" % needle


# -------------------------------------------------------------------- finding 4
def test_footer_states_the_magnitude_of_the_excluded_actor(tmp_path):
    """Finding 4: the disclosure said 'one actor' for 62% of the geometry.

    Driven from the tracked census so the fraction is the real one. The first version
    passed a single-stage list, where the largest stage IS the total and the fraction
    works out to 100%, so it could never see 62.
    """
    shots = tmp_path / "shots"
    shots.mkdir()
    stages = M.build_stages(M.DEFAULT_CENSUS, str(shots))
    totals = sum(s["metrics"]["instances"] for s in stages)
    stages_inst = [s["metrics"]["instances"] for s in stages]
    assert totals > 2_000_000 and max(stages_inst) > 1_000_000, \
        "test assumes the tracked census's real totals"

    footer = M.footer_text(stages)
    assert "PCG_4_2_CentralPark_Visuals" in footer, \
        "the excluded actor's stage must be named"
    assert "62" in footer, "the fraction of geometry missing must be stated, got %r" \
        % footer[:0]
    assert "288" in footer, "the file size must be stated"


# -------------------------------------------------------------------- finding 5
def test_footer_carries_the_measurements_the_plan_requires(tmp_path):
    """Finding 5: the density trade-off, its parameter position, and the two visual
    questions (highway silhouette provenance, missing_visual) were never in the report."""
    footer = M.footer_text(stages=[{"metrics": {"instances": 0,
                                               "debug_instances": 0}}])
    assert "PCG_3_1_1_Districts" in footer, "next-step parameter position must be named"
    assert "Block grid" in footer, "the exact parameter to change must be named"
    assert "1,806,980" in footer or "1806980" in footer, "density evidence must appear"
    assert "HighWay" in footer, "the highway silhouette's provenance must be addressed"
    assert "missing_visual" in footer, "the unverified-visual case must be addressed"


# -------------------------------------------------------------------- finding 6
def test_shot_name_candidates_accept_any_variant_not_only_r2():
    """Finding 6: the guards' fallback checked only `_r2`, but claim_name can emit `_r3`
    and beyond — and stage 1 actually used `_r3`."""
    cdir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "Content", "Python")
    if cdir not in sys.path:
        sys.path.insert(0, cdir)
    import pcg_sa_shots
    names = pcg_sa_shots.shot_name_candidates(1, "PCG_1_1_Terrain", "debug")
    assert names[0] == "sa_stage_01_PCG_1_1_Terrain_debug.png"
    assert "sa_stage_01_PCG_1_1_Terrain_debug_r2.png" in names
    assert "sa_stage_01_PCG_1_1_Terrain_debug_r3.png" in names, \
        "the fallback must cover the variant that was actually used"
    assert len(names) >= 8, "must cover an unbounded variant sequence"
