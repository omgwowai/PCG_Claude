"""Stage 15, Python node after the third stacked buildings (MainTowerVisuals): `s15_tower_level3`.

  Skyscraper  Subgraph_8's rooftops -> Subgraph_65 (contract 10 m)                       -> Subgraph_66
  Assemblies  Subgraph_8's rooftops -> Subgraph_22 Filter_Areas_BySize (> 1000 m2) Selected -> Subgraph_21
  Arm90/80/70 Subgraph_48 / 55 / 62's rooftops -> Subgraph_49 / 56 / 63 (1.5 m)          -> Subgraph_50 / 57 / 64

`Subgraph_22` passes the rooftops it selects through unchanged, so `Assemblies` forwards them.
"""
from pypcg.stages import s15_tower_rings as R

STAGE = 15
RECORD = "s15_level3"
DOC = """MainTowerVisuals, third level: the 200 m skyscraper's footprint (the second CHJ ring's rooftop
contracted 10 m), the rooftops over 1000 m2 for the rooftop assemblies, and each arm's third rooftop
contracted 1.5 m."""
RANDOM = False
PARAMS = {}
INPUTS = {"Chj2Roofs": "spline", "Arm90Roofs": "spline", "Arm80Roofs": "spline", "Arm70Roofs": "spline"}
OUTPUTS = ("Skyscraper", "Assemblies", "Arm90", "Arm80", "Arm70")


def run(inputs, params, ctx):
    roofs = R.rings_of(inputs.get("Chj2Roofs", []))
    raw = {"Skyscraper": R.contract(roofs, R.SKYSCRAPER_CONTRACT_CM, ctx.ops),
           "Assemblies": [r for r in roofs if R.area_m2(r) > R.ASSEMBLY_MIN_M2]}
    for arm in ("Arm90", "Arm80", "Arm70"):
        raw[arm] = R.contract(R.rings_of(inputs.get(arm + "Roofs", [])), R.ARM_CONTRACT_CM, ctx.ops)
    ctx.notes.append("level 3: %d rooftops (%s m2): %s" % (len(roofs), [round(R.area_m2(r), 1) for r in roofs],
                                                           {pin: len(v) for pin, v in raw.items()}))
    return {pin: R.tagged_rings(raw[pin], pin) for pin in OUTPUTS}
