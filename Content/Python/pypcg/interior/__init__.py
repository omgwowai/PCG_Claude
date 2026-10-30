"""PyInterior: rule-driven interiors for life-sim houses (docs/superpowers/specs/2026-10-28-pyinterior-design.md).

A house is a PCG volume carrying a closed footprint spline; one Python node turns the footprint into rooms, doors, windows
and furniture by rule tables (City Sample's building system applied to interiors). No unreal import."""

ASSET_DIR = "/Game/PyPCG/Interior/"
GRAPH = "PCGI_House"
LEVEL = "/Game/PyPCG/L_PyInterior"
TEMPLATE_MAP = "/Engine/Maps/Templates/Template_Default"
HOUSE_TAG = "PyInterior_House"
STOREYS_TAG = "PyInterior_Storeys"       # the multi-storey demo houses on the second street (spec 2026-10-29)
STAGE = 201                       # apart from the city's 1..18 and the world's 101..109
