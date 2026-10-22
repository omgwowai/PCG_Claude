"""The small area: /Game/PyPCG/L_PyCitySmall, the merged graph PCG_PyCity on a ~560 x 440 m layout (guide §13.1).

The graph is the same asset as L_PyCity's; only the level's control actors (small_layout) and the volume's
overrides differ -- which is the point: configuration and control regions stay traditional."""
from pypcg import combined
from pypcg.profiles import city, small_layout

LEVEL = "/Game/PyPCG/L_PyCitySmall"
TEMPLATE = city.LEVEL                          # a copy of L_PyCity: one volume + the control actors
VOLUME = city.VOLUME
LAYOUT = small_layout
SHOT_PREFIX = "ps_"

ROLES = {}
KNOBS = {}

# The town's overrides, then the small area's own (merged-graph names):
#   - the 110 m tower (an 80 m one, measured 2026-10-22, builds no CHJ rings and no upper levels) and the
#     120 x 50 m park of small_layout;
#   - stage 6 splits this layout into eight districts of 20 116, 21 567, 22 098, 22 426, 25 438, 26 239,
#     35 043 and 35 586 m2 (pypcg_city.py read, 2026-10-22): the template's 77 499 m2 "dividable" limit
#     drops to 20 000 so every one stays dividable, and 24 000 / 30 000 give the town's 4 Small, 2 Medium,
#     2 Large (the town's own 95 000 / 120 000 made every district Small).
COMPONENT_OVERRIDES = dict(city.COMPONENT_OVERRIDES)
COMPONENT_OVERRIDES.update(combined.component_overrides({
    "PCG_2_1_MainTower_Footprint": {"RectWidth": 11000.0, "RectLength": 11000.0},
    "PCG_2_2_CentralPark_Footprint": {"RectWidth": 12000.0, "RectLength": 5000.0},
    "PCG_3_1_1_Districts": {"Dividable_district_Limit": 20000.0,
                            "SmallMediumThreshold": 24000.0, "MediumLargeThreshold": 30000.0},
}))
