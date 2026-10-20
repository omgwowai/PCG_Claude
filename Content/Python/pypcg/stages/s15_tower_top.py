"""Stage 15, Python node on the skyscraper's rooftop (MainTowerVisuals): `s15_tower_top`.

  Antenna   Subgraph_66's rooftops -> Subgraph_23 Place_Point_AtCenter -> Subgraph_24 Spawn_Antenna
"""
from pypcg.stages import s15_tower_rings as R

STAGE = 15
RECORD = "s15_top"
DOC = """MainTowerVisuals, the antenna: one point at the centre of the 200 m skyscraper's rooftop."""
RANDOM = False
PARAMS = {}
INPUTS = {"SkyscraperRoofs": "spline"}
OUTPUTS = ("Antenna",)


def run(inputs, params, ctx):
    pts = R.antenna(R.rings_of(inputs.get("SkyscraperRoofs", [])))
    ctx.notes.append("antenna: %d points %s" % (len(pts), [(tuple(round(c, 2) for c in pts.loc[i]),
                                                            round(pts.rot[i][1], 3)) for i in range(len(pts))]))
    return {"Antenna": [(pts, ["Antenna"])] if len(pts) else []}
