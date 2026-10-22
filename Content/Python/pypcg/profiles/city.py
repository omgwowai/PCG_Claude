"""Bindings for the single-graph city level /Game/PyPCG/L_PyCity (pypcg.combined, guide §13).

ROLES are the control actors the merged graph still reads by actor reference (the landmark park spline and
the two highway splines); pypcg_city.py {"phase": "bind"} writes city_bindings.json. Until it exists the
town's bindings stand in, which is only good for a structural build.

COMPONENT_OVERRIDES are the town's (pypcg.profiles.town) in the merged graph's names; pypcg_city.py adds
the template copy's own per-volume overrides, recorded by the town run, on top of the graph defaults."""
import json
import os

from pypcg import combined
from pypcg.profiles import town

LEVEL = "/Game/PyPCG/L_PyCity"
VOLUME = "PCG_PyCity"                          # the one PCG volume (the town's Terrain volume, relabelled)
BINDINGS = os.path.join(os.path.dirname(__file__), "city_bindings.json")
KEPT_ROLES = ("LandmarkPark", "HighwaySpline2", "HighwaySpline3")

if os.path.exists(BINDINGS):
    with open(BINDINGS, encoding="utf-8") as _fh:
        ROLES = json.load(_fh)
else:
    ROLES = {r: town.ROLES[r] for r in KEPT_ROLES}

KNOBS = {}

COMPONENT_OVERRIDES = combined.component_overrides(town.COMPONENT_OVERRIDES)
