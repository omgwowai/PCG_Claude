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
}
