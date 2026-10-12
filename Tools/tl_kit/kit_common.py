"""Constants shared between build_tl_kit.py (runs inside Blender, needs bpy)
and test_kit_spec.py (plain Python, no bpy). This module has NO bpy
dependency so the test can import it directly without running inside
Blender.

This exists specifically to fix a reviewer finding on Task 2: tl_kit_spec.json
declared "lods": [0, 1] while build_tl_kit.py only ever built and exported
LOD0 geometry (the "lod" parameter was dropped because both its branches
produced identical geometry -- see build_tl_kit.py's module docstring). That
mismatch was invisible because nothing in the test suite checked the "lods"
field against what the build script actually produces. Keep LODS_PRODUCED
here in sync with build_tl_kit.py's actual behavior, and change
tl_kit_spec.json's "lods" list in the same commit if that ever changes.
"""

# The LOD indices build_tl_kit.py actually builds a mesh for and exports one
# FBX per part for. Currently LOD0 only.
LODS_PRODUCED = [0]

# Tools/tl_kit/tl_kit_spec.json must declare exactly this many parts:
# L0 3 (foundation), L1 10, L2 11, L3 11 (Wall_02 is the stretchable filler,
# Column_02 the thin pilaster) and L4 8 (cornice). Pins the count so a
# truncated spec fails loudly. There is no roof level: modules only run along
# the facade, so the roof is the planar mesh the pipeline builds from the
# footprint (placed by BDF RoofData).
# +18 spline-building parts: per storey L1-L4 EndPier_01, EndPierAcute_01,
# FanFront_01, FanBack_01; L0 the two fans.
EXPECTED_PART_COUNT = 61

# Grammar symbol per kit part. Wall_02 is the scalable filler (WS1); a level
# without one reuses its Wall_01 as WS1.
PART_TO_SYMBOL = {
    "Foundation_01": "FS2",
    "Wall_01": "W1", "Wall_02": "WS1", "Column_01": "P1", "Column_02": "P2",
    "Entrance_01": "E1", "CornerEx_01": "C_CE", "CornerExL_01": "C_SL",
    "CornerExR_01": "C_SR", "CornerIn_01": "C_I", "CornerInL_01": "C_IL",
    "CornerInR_01": "C_IR",
}
PART_TO_SYMBOL.update({
    "EndPier_01": "EL", "EndPierAcute_01": "EAL",     # ER / EAR share these meshes
    "FanFront_01": "FF", "FanBack_01": "FB",
})
# Symbols of the spline building only. tl_make_rules.py skips them, so the
# RULE_TL_* assets (SGD route) stay exactly as before.
NON_RULE_SYMBOLS = {"EL", "ER", "EAL", "EAR", "FF", "FB"}
# Stretchable symbols: WS1 is each facade level's filler, FS2 the foundation
# strip. FS2 must stay scalable (it is on every sibling style): the foundation
# grammar is [FC][FS2]+[LC], so a non-scalable FS2 leaves the remainder of each
# segment open, a gap of up to one 2 m piece at a building corner.
SCALABLE_SYMBOLS = {"WS1", "FS2"}

# Horizontal grammars shared by every TL level. W1, E1 and P1 have the same
# width on L1-L4, so with one grammar the bays line up vertically: pilaster
# over pilaster, feature window over entrance. L4 (the cornice) swaps E1 for
# W1 and keeps the P1 piers.
GRAMMAR_F0 = "[FC][WS1][W1]+[LC]"
GRAMMAR_F1 = "[FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]"
GRAMMAR_F2 = ("[FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1]"
              "[E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]")
# F0/F1/F2 minimum facade lengths in cm, corners (1.5 m at each end) included.
FLENGTHS_CM = (950.0, 3725.0, 5400.0)

# LV0 (below grade) has the single-row grammar every sibling style uses.
GRAMMAR_FOUNDATION = "[FC][FS2]+[LC]"
FOUNDATION_FLENGTHS_CM = (300.0, 300.0, 300.0)
# The foundation level is 0.5 cm tall in the grammar (as in every sibling) and
# its meshes hang below z = 0, so they keep NY's PivotOffsets rather than the
# (0, -w/2, -h/2) the facade levels use. Measured on CHA's L0 rows.
FOUNDATION_PIVOT_Y = {"FS2": 0.0, "C_CE": -20.173994, "C_E": -20.173994, "C_I": -4.926454}
FOUNDATION_LEVEL_HEIGHT_CM = 0.5


# TL's vertical grammar: foundation, ground floor, any number of L2 storeys,
# the top storey and the cornice. tl_make_bdf.py writes the same string into
# BDF_WithTL (TL_BDF["VerticalGrammar"]); test_corner_math.py checks the two
# stay equal. Only [LV2] repeats, so the levels without a `*` are the fixed
# stack every TL building has.
VERTICAL_GRAMMAR = "[LV0][LV1][LV2]*[LV3][LV4]"


def level_grammars(level):
    """(F0, F1, F2) for a TL level."""
    if level == 0:
        return (GRAMMAR_FOUNDATION,) * 3
    if level == 4:
        return (GRAMMAR_F0, GRAMMAR_F1.replace("[E1]", "[W1]"),
                GRAMMAR_F2.replace("[E1]", "[W1]"))
    return (GRAMMAR_F0, GRAMMAR_F1, GRAMMAR_F2)


def level_flengths_cm(level):
    if level == 0:
        return FOUNDATION_FLENGTHS_CM
    return FLENGTHS_CM


# Spline building (docs/superpowers/specs/2026-10-09-tl-spline-building-design.md).
# End piers replace the corner pieces: one 150 cm pier at each end of every
# wall, flat-ended, so two walls butt at the vertex at any angle.
END_PIER_CM = 150.0
