"""Bindings for the single-graph city level /Game/PyPCG/L_PyCity (pypcg.combined, guide §13).

The merged graph reads every control actor by tag, so there are no actor-reference roles to bind.
COMPONENT_OVERRIDES are the town's (pypcg.profiles.town) in the merged graph's names; pypcg_city.py adds
the template copy's own per-volume overrides, recorded by the town run, under them."""
from pypcg import combined
from pypcg.profiles import town, town_layout

LEVEL = "/Game/PyPCG/L_PyCity"
TEMPLATE = "/Game/PyPCG/L_PyTown"              # `make` copies this level; `layout` keeps one volume
VOLUME = "PCG_PyCity"                          # the one PCG volume (the town's Terrain volume, relabelled)
LAYOUT = town_layout                           # the control splines are the town's, unchanged
SHOT_PREFIX = "pc_"

ROLES = {}
KNOBS = {}

COMPONENT_OVERRIDES = combined.component_overrides(town.COMPONENT_OVERRIDES)
