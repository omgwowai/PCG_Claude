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

# Tools/tl_kit/tl_kit_spec.json must declare exactly this many parts (9 L1 +
# 10 L2 + 10 L3, per the plan). Used to fail loudly on a truncated or
# malformed spec before the build loop runs, and to pin the count in tests.
EXPECTED_PART_COUNT = 29
