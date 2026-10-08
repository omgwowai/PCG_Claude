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
# L1 10, L2 11, L3 11 (Wall_02 is the stretchable filler, Column_02 the thin
# pilaster) + 8 for the L4 cornice. Pins the count so a truncated spec fails
# loudly.
EXPECTED_PART_COUNT = 40

# Grammar symbol per kit part. Wall_02 is the scalable filler (WS1); a level
# without one reuses its Wall_01 as WS1.
PART_TO_SYMBOL = {
    "Wall_01": "W1", "Wall_02": "WS1", "Column_01": "P1", "Column_02": "P2",
    "Entrance_01": "E1", "CornerEx_01": "C_CE", "CornerExL_01": "C_SL",
    "CornerExR_01": "C_SR", "CornerIn_01": "C_I", "CornerInL_01": "C_IL",
    "CornerInR_01": "C_IR",
}
SCALABLE_SYMBOLS = {"WS1"}

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


def level_grammars(level):
    """(F0, F1, F2) for a TL level."""
    if level == 4:
        return (GRAMMAR_F0, GRAMMAR_F1.replace("[E1]", "[W1]"),
                GRAMMAR_F2.replace("[E1]", "[W1]"))
    return (GRAMMAR_F0, GRAMMAR_F1, GRAMMAR_F2)
