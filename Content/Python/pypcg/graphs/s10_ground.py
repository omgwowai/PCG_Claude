"""Slim graph of stage 10, Ground (spec 2.4).

The official graph publishes nothing (its output node has no wired input) and neither does this one:
there is no `out()` call, and the Python node's four outputs go to the kept generation nodes only.

Scene reads into the Python node: `Subgraph_0 Get Lots`, `Subgraph_2 Get Districts`, `Subgraph_18 Get City
Shape` (actor tag City), `Subgraph_50 Get Landmark`, `Subgraph_43 Landmark Small Park`, `Subgraph_51 Get
Central Park` and `Subgraph_39 Get_MeshTerrain` (Final). `Subgraph_21 Get Roads` reaches the node through
the two official nodes that read the artery width off the road footprint, `FilterDataByTag_4` (tags
containing `Polygon`) and `ExtractAttribute_1` (`@data.ArteryWidth`): a Python node cannot read a
data-domain attribute in this build. `Subgraph_44 Get Base Terrain` is kept and left unwired, exactly as
the official graph leaves it (it has no consumer there either).

Generation side, kept with the native nodes that sit AFTER the grammar nodes (they read the grammar's
own points, so porting them would need a second Python node behind each grammar node, with a terrain
input; stage 9 kept its post-grammar projector native for the same reason):

  GroundTiles      -> Subgraph_32 Spawn ground tiles
  SidewalkSegments -> Subgraph_31 Assign Sidewalks -> Subgraph_34 projector -> AttributeCast_0 ->
                      the four prop filters (FilterDataByAttribute_0..3) -> AttributeMathsOp_0/3 (roll,
                      pitch zeroed) -> FilterDataByAttribute_4 (vehicles) -> FilterDataByType_1 ->
                      AttributeStringOp_0/1 -> CopyAttributes_1 -> AttributeCast_1 -> Gather_1
  CornerShapes     -> Subgraph_26 Assign Corners -> Subgraph_38 projector -> Gather_1
  Gather_1         -> Subgraph_35 Spawn Sidewalk Assets
  RailingZones     -> Subgraph_20 Assign Railing And Fence Grammar -> Subgraph_48 projector ->
                      Subgraph_36 Spawn Fence Assets

What differs from the official wiring: the named reroutes (`Mesh Terrain Final`, `Corners Assets`, ...)
are direct edges; the three `Partitioned` branches (`Branch_5/6/7`) and the partition tail (`Gather_2`,
`Subgraph_12 GridPartition`, `Loop_0`) are dropped with the `debug` branches -- `Partitioned` and `debug`
are false on every volume this port runs, so `Output A` is the side the official graph takes.
"""
from pypcg import dsl
from pypcg.stages import s10_ground as S

READS = {"Lots": "Subgraph_0", "Districts": "Subgraph_2", "City": "Subgraph_18", "MainTower": "Subgraph_50",
         "LandmarkPark": "Subgraph_43", "CentralParkFootprint": "Subgraph_51", "MeshTerrain": "Subgraph_39"}
PROP_FILTERS = ("FilterDataByAttribute_0", "FilterDataByAttribute_1", "FilterDataByAttribute_2",
                "FilterDataByAttribute_3")


def build():
    g = dsl.SlimGraph(S)
    k = {}
    for name in list(READS.values()) + ["Subgraph_21", "Subgraph_44", "FilterDataByTag_4", "ExtractAttribute_1",
                                         "Subgraph_32", "Subgraph_31", "Subgraph_26", "Subgraph_20",
                                         "Subgraph_35", "Subgraph_36", "Subgraph_34", "Subgraph_38", "Subgraph_48",
                                         "AttributeCast_0", "AttributeMathsOp_0", "AttributeMathsOp_3",
                                         "FilterDataByAttribute_4", "FilterDataByType_1", "AttributeStringOp_0",
                                         "AttributeStringOp_1", "CopyAttributes_1", "AttributeCast_1",
                                         "Gather_1"] + list(PROP_FILTERS):
        k[name] = g.keep(name)

    # ---- the scene reads ----
    for pin, name in READS.items():
        g.connect(k[name], g.py, pin)
    g.connect(k["Subgraph_21"], k["FilterDataByTag_4"], "In")
    g.connect(k["FilterDataByTag_4"]["InsideFilter"], k["ExtractAttribute_1"], "In")
    g.connect(k["ExtractAttribute_1"], g.py, "ArteryWidth")
    terrain = k["Subgraph_39"]

    # ---- ground tiles ----
    g.connect(g.py["GroundTiles"], k["Subgraph_32"], "PrimaryInput")

    # ---- sidewalks: grammar, projection, the street-prop roll/pitch fix and the transparent vehicles ----
    g.connect(g.py["SidewalkSegments"], k["Subgraph_31"], "PrimaryInput")
    g.connect(k["Subgraph_31"]["Points"], k["Subgraph_34"], "In Points")
    g.connect(terrain, k["Subgraph_34"], "Surface")
    g.connect(k["Subgraph_34"], k["AttributeCast_0"], "In")
    prev = k["AttributeCast_0"]
    for name in PROP_FILTERS:
        g.connect(prev if name == PROP_FILTERS[0] else prev["OutsideFilter"], k[name], "In")
        g.connect(k[name]["InsideFilter"], k["AttributeMathsOp_0"], "InA")
        prev = k[name]
    g.connect(k["AttributeMathsOp_0"], k["AttributeMathsOp_3"], "InA")
    g.connect(prev["OutsideFilter"], k["FilterDataByAttribute_4"], "In")
    g.connect(k["AttributeMathsOp_3"], k["FilterDataByAttribute_4"], "In")
    g.connect(k["FilterDataByAttribute_4"]["InsideFilter"], k["FilterDataByType_1"], "In")
    g.connect(k["FilterDataByType_1"]["InsideFilter"], k["AttributeStringOp_0"], "In")
    g.connect(k["AttributeStringOp_0"], k["AttributeStringOp_1"], "In")
    g.connect(k["AttributeStringOp_1"], k["CopyAttributes_1"], "Target")
    g.connect(k["AttributeStringOp_1"], k["CopyAttributes_1"], "Source")
    g.connect(k["CopyAttributes_1"], k["AttributeCast_1"], "In")

    # ---- corners ----
    g.connect(g.py["CornerShapes"], k["Subgraph_26"], "PrimaryInput")
    g.connect(k["Subgraph_26"]["Points"], k["Subgraph_38"], "In Points")
    g.connect(terrain, k["Subgraph_38"], "Surface")

    # ---- Gather_1 -> Spawn Sidewalk Assets (official input order) ----
    g.connect([k["FilterDataByAttribute_4"]["InsideFilter"], k["FilterDataByAttribute_4"]["OutsideFilter"],
               k["Subgraph_38"], k["AttributeCast_1"]], k["Gather_1"], "In")
    g.connect(k["Gather_1"], k["Subgraph_35"], "PrimaryInput")

    # ---- railings ----
    g.connect(g.py["RailingZones"], k["Subgraph_20"], "PrimaryInput")
    g.connect(k["Subgraph_20"], k["Subgraph_48"], "In Points")
    g.connect(terrain, k["Subgraph_48"], "Surface")
    g.connect(k["Subgraph_48"], k["Subgraph_36"], "PrimaryInput")
    return g
