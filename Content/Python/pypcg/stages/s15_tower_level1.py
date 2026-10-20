"""Stage 15, Python node after the first stacked buildings (MainTowerVisuals): `s15_tower_level1`.

Reads the rooftops of the four kept buildings the main node feeds -- `AssignBuilding` (CHC 50 m) and the
first CHJ tower of each arm (`Subgraph_40` 90 m, `Subgraph_51` 80 m, `Subgraph_58` 70 m) -- and the main
node's hexagons, and makes:

  OuterChj        Subgraph_17 -> 18 -> 9 -> Subgraph_19 (the CHC rooftop less six 7 m squares on its outline
                  centres) -> Subgraph_5 (contract 4 m)                          -> Subgraph_6
  Courtyard       AttributeMathsOp_1 -> Subgraph_10 -> Subgraph_11 (expand 3.5 m) -> Subgraph_12 / 13
  CourtyardLifted Subgraph_15 (+40)                                              -> Subgraph_14 / 41
  Arm90/80/70     Subgraph_45 / 52 / 59 (contract 1.5 m)                         -> Subgraph_46 / 53 / 60
"""
from pypcg.stages import s15_tower_rings as R

STAGE = 15
RECORD = "s15_level1"
DOC = """MainTowerVisuals, first level: the CHC block's notched outline contracted 4 m for the outer CHJ ring,
the courtyard round the 25 m hexagons, and each arm's first rooftop contracted 1.5 m."""
RANDOM = False
PARAMS = {}
INPUTS = {"ChcRoofs": "spline", "Hexagons": "spline", "Arm90Roofs": "spline", "Arm80Roofs": "spline",
          "Arm70Roofs": "spline"}
OUTPUTS = ("OuterChj", "Courtyard", "CourtyardLifted", "Arm90", "Arm80", "Arm70")


def level1(inputs, ops):
    out = {pin: [] for pin in OUTPUTS}
    chc = R.rings_of(inputs.get("ChcRoofs", []))
    hexes = R.rings_of(inputs.get("Hexagons", []))
    out["OuterChj"] = R.contract(R.notched(chc, ops), R.CHJ_CONTRACT_CM, ops)
    out["Courtyard"], out["CourtyardLifted"] = R.courtyard(hexes, ops)
    for arm in ("Arm90", "Arm80", "Arm70"):
        out[arm] = R.contract(R.rings_of(inputs.get(arm + "Roofs", [])), R.ARM_CONTRACT_CM, ops)
    return out, ["level 1: %d CHC rooftops -> %d outer CHJ rings; %d hexagons -> %d courtyard pieces; arms %s"
                 % (len(chc), len(out["OuterChj"]), len(hexes), len(out["Courtyard"]),
                    [len(out[a]) for a in ("Arm90", "Arm80", "Arm70")])]


def run(inputs, params, ctx):
    raw, notes = level1(inputs, ctx.ops)
    ctx.notes += notes
    out = {pin: R.tagged_rings(raw[pin], pin) for pin in ("OuterChj", "Arm90", "Arm80", "Arm70")}
    out["Courtyard"] = [(p, ["Courtyard"]) for p in raw["Courtyard"]]
    out["CourtyardLifted"] = [(p, ["CourtyardLifted"]) for p in raw["CourtyardLifted"]]
    return out
