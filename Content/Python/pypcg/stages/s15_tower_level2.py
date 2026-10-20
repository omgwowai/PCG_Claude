"""Stage 15, Python node after the second stacked buildings (MainTowerVisuals): `s15_tower_level2`.

  Chj2      Subgraph_6's rooftops (the outer CHJ ring) -> Subgraph_7 (contract 4 m)  -> Subgraph_8
  Arm90/80/70  Subgraph_46 / 53 / 60's rooftops -> Subgraph_47 / 54 / 61 (1.5 m)    -> Subgraph_48 / 55 / 62
"""
from pypcg.stages import s15_tower_rings as R

STAGE = 15
RECORD = "s15_level2"
DOC = """MainTowerVisuals, second level: the outer CHJ ring's rooftop contracted 4 m, and each arm's second
rooftop contracted 1.5 m."""
RANDOM = False
PARAMS = {}
INPUTS = {"Chj1Roofs": "spline", "Arm90Roofs": "spline", "Arm80Roofs": "spline", "Arm70Roofs": "spline"}
OUTPUTS = ("Chj2", "Arm90", "Arm80", "Arm70")


def run(inputs, params, ctx):
    raw = {"Chj2": R.contract(R.rings_of(inputs.get("Chj1Roofs", [])), R.CHJ_CONTRACT_CM, ctx.ops)}
    for arm in ("Arm90", "Arm80", "Arm70"):
        raw[arm] = R.contract(R.rings_of(inputs.get(arm + "Roofs", [])), R.ARM_CONTRACT_CM, ctx.ops)
    ctx.notes.append("level 2: %s" % {pin: len(v) for pin, v in raw.items()})
    return {pin: R.tagged_rings(raw[pin], pin) for pin in OUTPUTS}
