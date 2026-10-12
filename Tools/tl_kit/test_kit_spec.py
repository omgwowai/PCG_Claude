import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit_common

SPEC = os.path.join(os.path.dirname(__file__), "tl_kit_spec.json")

KNOWN_KINDS = {
    "foundation", "foundation_corner",
    "shopfront", "filler", "entrance", "pilaster", "pilaster_thin",
    "window", "window_top", "feature_window", "feature_window_top",
    "corner_ex", "corner_in", "corner_half",
    "cornice", "cornice_pier", "cornice_corner_ex", "cornice_corner_in", "cornice_half",
    "end_pier", "end_pier_acute", "fan_front", "fan_back",
}


def load():
    with open(SPEC, encoding="utf-8") as f:
        return json.load(f)


def parts_at(spec, level):
    return {p["part"]: p for p in spec["parts"] if p["level"] == level}


def test_covers_five_levels():
    assert {p["level"] for p in load()["parts"]} == {0, 1, 2, 3, 4}


def test_heights_follow_the_level_table():
    spec = load()
    for p in spec["parts"]:
        assert p["height_m"] == spec["levels"][str(p["level"])]["height_m"], p


def test_cha_aligned_heights():
    spec = load()
    assert [spec["levels"][k]["height_m"] for k in ("1", "2", "3")] == [5.0, 3.0, 3.0]


def test_foundation_matches_the_shared_level0_profile():
    # Every sibling style's LV0 uses FS2 (2 m, scalable) with C_E 40 cm and
    # C_I 10 cm corners; DT_Bldg_LevelMinWidth's LV0 row assumes those sizes.
    lv0 = parts_at(load(), 0)
    assert lv0["Foundation_01"]["width_m"] == 2.0
    assert lv0["CornerEx_01"]["width_m"] == 0.4
    assert lv0["CornerIn_01"]["width_m"] == 0.1


def test_bays_line_up_vertically():
    # One horizontal grammar for every level only aligns the bays if each
    # symbol has the same width on every level.
    spec = load()
    for part in ("Wall_01", "Column_01", "CornerEx_01", "CornerIn_01"):
        widths = {parts_at(spec, lv)[part]["width_m"] for lv in (1, 2, 3, 4)}
        assert len(widths) == 1, (part, widths)
    widths = {parts_at(spec, lv)["Entrance_01"]["width_m"] for lv in (1, 2, 3)}
    assert widths == {parts_at(spec, 1)["Wall_01"]["width_m"]}, widths


def test_corner_width_is_the_same_on_every_level():
    # One corner symbol per material level, all the same size, so the corner
    # pieces stack and the half-corner stub stays half a wall turn.
    spec = load()
    for part in ("CornerEx_01", "CornerExL_01", "CornerIn_01"):
        widths = {parts_at(spec, lv)[part]["width_m"] for lv in (1, 2, 3, 4)}
        assert len(widths) == 1, (part, widths)


def test_flengths_match_the_f1_and_f2_grammars():
    spec = load()
    w = {kit_common.PART_TO_SYMBOL[p]: v["width_m"] * 100 for p, v in parts_at(spec, 1).items()}
    corners = 2 * w["C_CE"]
    for grammar, want in zip(kit_common.level_grammars(1), kit_common.FLENGTHS_CM):
        tokens = grammar.replace("]+", "]").replace("[", " ").replace("]", " ").replace(",", " ").split()
        total = corners + sum(w[t] for t in tokens if t not in ("FC", "LC"))
        assert abs(total - want) < 0.01, (grammar, total, want)


def test_foundation_grammar_is_the_shared_filler_row():
    for g in kit_common.level_grammars(0):
        assert g == "[FC][FS2]+[LC]", g


def test_fillers_are_scalable():
    # [FC][FS2]+[LC] and [WS1] close each segment by stretching; without the
    # flag the remainder stays open (measured: a 119 cm gap at a corner).
    assert {"WS1", "FS2"} <= kit_common.SCALABLE_SYMBOLS


def test_every_level_has_its_symbols():
    spec = load()
    for lv in (1, 2, 3, 4):
        syms = {kit_common.PART_TO_SYMBOL[p] for p in parts_at(spec, lv)}
        needed = {"W1", "P1", "C_CE", "C_I"}
        if lv < 4:
            needed |= {"E1", "WS1"}
        assert needed <= syms, (lv, needed - syms)


def test_kinds_are_known_and_materials_declared():
    spec = load()
    assert set(spec["materials"]) == {"TL_Brick", "TL_Stone", "TL_Glass", "TL_Metal"}
    for p in spec["parts"]:
        assert p["kind"] in KNOWN_KINDS, p
        assert p["part"] in kit_common.PART_TO_SYMBOL, p


def test_names_follow_the_convention():
    for p in load()["parts"]:
        assert p["mesh_name"] == "SM_BLDG_TL_L%02d_A_%s_N1" % (p["level"], p["part"]), p


def test_part_count_matches_expected():
    assert len(load()["parts"]) == kit_common.EXPECTED_PART_COUNT


def test_declared_lods_match_what_the_build_script_produces():
    assert load()["lods"] == kit_common.LODS_PRODUCED


def test_spline_building_parts():
    spec = load()
    for lv in (1, 2, 3, 4):
        p = parts_at(spec, lv)
        assert p["EndPier_01"]["kind"] == "end_pier"
        assert p["EndPierAcute_01"]["kind"] == "end_pier_acute"
        assert p["EndPier_01"]["width_m"] * 100 == kit_common.END_PIER_CM
        assert p["EndPierAcute_01"]["width_m"] * 100 == kit_common.END_PIER_CM
    for lv in (0, 1, 2, 3, 4):
        p = parts_at(spec, lv)
        assert p["FanFront_01"]["kind"] == "fan_front"
        assert p["FanBack_01"]["kind"] == "fan_back"
    assert "EndPier_01" not in parts_at(spec, 0)


def test_spline_symbols_never_reach_the_rules():
    # RULE_TL_* (the SGD route) must not change: the new symbols are skipped there.
    assert {"EL", "EAL", "FF", "FB"} <= kit_common.NON_RULE_SYMBOLS
    for s in kit_common.NON_RULE_SYMBOLS:
        for lv in range(5):
            for g in kit_common.level_grammars(lv):
                assert "[%s]" % s not in g


def test_no_duplicate_symbols_within_a_level():
    # Two parts mapping to the same symbol on one level would make the RULE
    # array ambiguous. The exceptions are the corner pairs: the whole corner and
    # its two halves share the interior symbol (C_I), and the foundation's
    # exterior corner shares C_E with the L1-L4 exterior corner mesh, which is
    # how every sibling style maps a corner piece onto the corner token.
    spec = load()
    for lv in sorted({p["level"] for p in spec["parts"]}):
        syms = [kit_common.PART_TO_SYMBOL[p] for p in parts_at(spec, lv)]
        dupes = {s for s in syms if syms.count(s) > 1}
        assert dupes <= {"C_I", "C_E"}, (lv, dupes)
