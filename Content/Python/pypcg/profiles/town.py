"""Bindings for the town level /Game/PyPCG/L_PyTown (spec 5.2).

ROLES come from town_bindings.json (pypcg_town_level.py {"phase": "bind"}).
COMPONENT_OVERRIDES are set on the volumes' PCG components after set_graph (traps.md 44), so the town's
graphs differ from the official ones only at their role bindings. The landmark sizes are ordinary
parameters of stages 4 and 5 (Task 13), which is why no knob mechanism exists any more."""
import json
import os

LEVEL = "/Game/PyPCG/L_PyTown"

with open(os.path.join(os.path.dirname(__file__), "town_bindings.json"), encoding="utf-8") as _fh:
    ROLES = json.load(_fh)

KNOBS = {}

COMPONENT_OVERRIDES = {
    # 110 m tower (spec D7); the 160 m fallback is RectWidth/Length = 16000 (Task 27 Step 5)
    "PCG_2_1_MainTower_Footprint": {"RectWidth": 11000.0, "RectLength": 11000.0},
    "PCG_2_2_CentralPark_Footprint": {"RectWidth": 26000.0, "RectLength": 9000.0},
    # Ruling T27h (Task 27): the template's class thresholds (152 961 / 329 288 m2) were sized for the demo's
    # 9.7 km city, so every town district came out Small and the town had no Medium or Large buildings (and
    # so no TL, which only the Medium style list carries). The town's eight districts measure 78 156,
    # 85 469, 88 871, 89 316, 100 118, 103 242, 138 532 and 140 042 m2 (stage 6, 2026-10-21; the split does
    # not depend on these thresholds). With 95 000 / 120 000: 4 Small, 2 Medium, 2 Large.
    # Dividable_district_Limit stays the template's 77 499 m2: every district remains dividable.
    "PCG_3_1_1_Districts": {"SmallMediumThreshold": 95000.0, "MediumLargeThreshold": 120000.0},
}
