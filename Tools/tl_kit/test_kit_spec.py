import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit_common

SPEC = os.path.join(os.path.dirname(__file__), "tl_kit_spec.json")

# CHA dimensions TL aligns to (spec 2.8). Widths in meters, heights in meters.
CHA_L1_PARTS = {"Wall_01": 3.25, "Column_01": 1.25, "Entrance_01": 3.25,
                "CornerEx_01": 1.5, "CornerExL_01": 1.5, "CornerExR_01": 1.5,
                "CornerIn_01": 1.5, "CornerInL_01": 1.5, "CornerInR_01": 1.5}
CHA_L2_PARTS = dict(CHA_L1_PARTS)
CHA_L2_PARTS["Entrance_01"] = 4.75
CHA_L2_PARTS["Column_02"] = 0.25


def load():
    with open(SPEC, encoding="utf-8") as f:
        return json.load(f)


def test_covers_three_levels():
    spec = load()
    levels = {p["level"] for p in spec["parts"]}
    assert levels == {1, 2, 3}, levels


def test_level1_heights_and_widths():
    spec = load()
    l1 = [p for p in spec["parts"] if p["level"] == 1]
    for p in l1:
        assert p["height_m"] == 5.0, p
        assert p["width_m"] == CHA_L1_PARTS[p["part"]], p


def test_level2_3_heights_and_widths():
    spec = load()
    for lvl, want in ((2, CHA_L2_PARTS), (3, CHA_L2_PARTS)):
        for p in [x for x in spec["parts"] if x["level"] == lvl]:
            assert p["height_m"] == 3.0, p
            assert p["width_m"] == want[p["part"]], p


def test_每_part_has_a_material_and_pivot():
    spec = load()
    for p in spec["parts"]:
        assert p["material"], p
        assert "pivot_z_m" in p, p


def test_names_follow_the_convention():
    # NOTE: the plan brief's original assertion here was
    # `mesh_name.endswith("_01_N1")` for every part. That is wrong: real,
    # on-disk CHA assets (e.g.
    # Content/Building/CH/A/Kit_Bldg_CHA_L2_A/Mesh/SM_BLDG_CHA_L02_A_Column_02_N1.uasset)
    # prove the mesh name embeds the PART's own numeric suffix (Column_01 ->
    # "..._Column_01_N1", Column_02 -> "..._Column_02_N1"), not a fixed
    # "_01". The TL spec's Column_02 parts correctly follow that real
    # convention, so this test's blanket "_01_N1" check is the defect (it
    # would fail against genuine CHA data too) and is corrected here to
    # check against each part's own suffix instead of hardcoding "01".
    spec = load()
    for p in spec["parts"]:
        assert p["mesh_name"].startswith("SM_BLDG_TL_L"), p
        assert p["mesh_name"].endswith(p["part"] + "_N1"), p


def test_part_count_matches_expected():
    # Guards the "fail loudly on a short/truncated spec" property: if the
    # spec ever gains or loses a part without kit_common.EXPECTED_PART_COUNT
    # being updated deliberately, this test (and build_tl_kit.py's own
    # runtime check) catches it instead of silently building a partial or
    # oversized kit.
    spec = load()
    assert len(spec["parts"]) == kit_common.EXPECTED_PART_COUNT, len(spec["parts"])


def test_declared_lods_match_what_the_build_script_produces():
    # Reviewer finding on Task 2: tl_kit_spec.json declared "lods": [0, 1]
    # while build_tl_kit.py only ever builds/exports LOD0 (the "lod"
    # parameter was dropped from build_part() because both its branches
    # produced identical geometry). That drift was invisible because nothing
    # in this suite checked the "lods" field against reality -- a Task 3
    # importer trusting "lods": [0, 1] would go looking for 29 "_LOD1" FBX
    # files that were never produced. This test pins the spec's declared
    # LOD set to kit_common.LODS_PRODUCED, the single source of truth for
    # what build_tl_kit.py actually builds, so the two cannot drift apart
    # silently again.
    spec = load()
    assert spec["lods"] == kit_common.LODS_PRODUCED, spec["lods"]
