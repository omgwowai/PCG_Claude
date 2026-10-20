"""Stage 15, Python node after the two sidewalk grammars (MainTowerVisuals): `s15_tower_sidewalk`.

  Points   Subgraph_13.Points then Subgraph_12.Points (Subgraph_31's In Points order) -> Subgraph_31
           Custom_Projector_with_rotation_fix onto the terrain -> Subgraph_32 Spawn Sidewalk
"""
from pypcg.geo import Points
from pypcg.stages import s15_main_tower_visuals as M

STAGE = 15
RECORD = "s15_sidewalk"
DOC = """MainTowerVisuals, the sidewalk: the two grammars' points fitted to the terrain."""
RANDOM = False
PARAMS = {}
INPUTS = {"SidewalkPoints": "points", "MeshTerrain": "surface"}
OUTPUTS = ("Points",)


def run(inputs, params, ctx):
    surface = M._surface(inputs)
    out = []
    for v, _tags in inputs.get("SidewalkPoints", []):
        if isinstance(v, Points) and len(v):
            out.append((M.project(v, surface), ["Points"]))
    ctx.notes.append("sidewalk: %d sets, %d points%s" % (len(out), sum(len(p) for p, _t in out),
                                                          "" if surface is not None else " (no terrain)"))
    return {"Points": out}
