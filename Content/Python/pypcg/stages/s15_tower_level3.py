"""Stage 15, Python node after the third stacked buildings (MainTowerVisuals): `s15_tower_level3`.

  Skyscraper  Subgraph_8's rooftops -> Subgraph_65 (contract 10 m)                       -> Subgraph_66
  Assemblies  Subgraph_8's rooftops -> Subgraph_22 Filter_Areas_BySize (> 1000 m2) Selected -> Subgraph_21
  Arm90/80/70 Subgraph_48 / 55 / 62's rooftops -> Subgraph_49 / 56 / 63 (1.5 m)          -> Subgraph_50 / 57 / 64

`Subgraph_22` passes the rooftops it selects through unchanged, so `Assemblies` forwards the very splines the
building node made (`FORWARD_SPLINES`, stage 11's mechanism).
"""
from pypcg.geo import Polygon, Spline
from pypcg.stages import s15_tower_rings as R

STAGE = 15
RECORD = "s15_level3"
DOC = """MainTowerVisuals, third level: the 200 m skyscraper's footprint (the second CHJ ring's rooftop
contracted 10 m), the rooftops over 1000 m2 for the rooftop assemblies, and each arm's third rooftop
contracted 1.5 m."""
RANDOM = False
FORWARD_SPLINES = True
PARAMS = {}
INPUTS = {"Chj2Roofs": "spline", "Arm90Roofs": "spline", "Arm80Roofs": "spline", "Arm70Roofs": "spline"}
OUTPUTS = ("Skyscraper", "Assemblies", "Arm90", "Arm80", "Arm70")


def selected(items):
    """`Subgraph_22` (`Operator` Greater, `Size` 1000 m2): the rooftop items over the size, as they came."""
    out = []
    for v, _tags in items:
        rings = R.rings_of([(v, ())])
        if rings and isinstance(v, (Spline, Polygon)) and R.area_m2(rings[0]) > R.ASSEMBLY_MIN_M2:
            out.append(v)
    return out


def run(inputs, params, ctx):
    items = inputs.get("Chj2Roofs", [])
    roofs = R.rings_of(items)
    raw = {"Skyscraper": R.contract(roofs, R.SKYSCRAPER_CONTRACT_CM, ctx.ops)}
    for arm in ("Arm90", "Arm80", "Arm70"):
        raw[arm] = R.contract(R.rings_of(inputs.get(arm + "Roofs", [])), R.ARM_CONTRACT_CM, ctx.ops)
    keep = selected(items)
    ctx.notes.append("level 3: %d rooftops (%s m2), %d over %g m2: %s" % (
        len(roofs), [round(R.area_m2(r), 1) for r in roofs], len(keep), R.ASSEMBLY_MIN_M2,
        {pin: len(v) for pin, v in raw.items()}))
    out = {pin: R.tagged_rings(raw[pin], pin) for pin in ("Skyscraper", "Arm90", "Arm80", "Arm70")}
    out["Assemblies"] = [(v, ["Assemblies"]) for v in keep]
    return out
