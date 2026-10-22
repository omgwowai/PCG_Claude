"""Slim graph of stage 11, Buildings (spec 2.4).

Three Python nodes: `s11_buildings_lots` (the class split), `s11_buildings` (MAIN: heights, HighRise,
terrain fit, the complex-shape split) and `s11_buildings_rooftops` (tags and rooftop materials).

Scene reads: `Subgraph_1 Get Lots` (the stage-9 volume), `Subgraph_5 HighRise Zone` (actor tag), `Subgraph_10
Get Final Mesh Terrain`, `Subgraph_2 LoadCitySampleData` (one, shared by the three building nodes).

  Subgraph_1 -> s11_buildings_lots -> Subgraph_2_{Small,Medium,Large}District (Write_Attribute_fromTexture,
                NATIVE: the texture's pixels; RemapValueOutLow / High from the Min / Max height getters)
             -> s11_buildings, with each texture node's `@data.MaxHeight` through an ExtractAttribute adapter
  s11_buildings -> CopyAttributes adapters (`MaxHeight` -> `@data.MaxHeight`, one per stream) ->
                SmallFootprints  -> Subgraph_3  Assign City Sample Buildings - Small
                MediumFootprints -> Subgraph_40 Assign City Sample Buildings - Medium
                LargeFootprints  -> Subgraph_41 Assign City Sample Buildings - Large
                MediumComplex    -> Loop_2 AssignBuildingShape -> Subgraph_36 SetComplexBuildings
                LargeComplex     -> Loop_1 AssignBuildingShape -> Subgraph_33 SetComplexBuildings
                {Small,Medium,Large}Collision -> Loop_5 / Loop_4 / Loop_3 (extruded collision; always EMPTY)
                SpawnMeshes (true: Partitioned is dropped) -> the three Assign nodes' SpawnMeshes pins
  Subgraph_3 / (36, 40) / (33, 41) rooftops -> s11_buildings_rooftops -> the output (the three tags) and the
                thirteen Create_Mesh_Planar rooftop meshes (Subgraph_0, 20 .. 31)

Adapters (not official nodes): a Python node can neither read nor write a data-domain attribute in this build
(stage 10's precedent), so `@data.MaxHeight` crosses each Python boundary through a native node: three
`ExtractAttribute` in, eight `CopyAttributes` out. What differs from the official wiring otherwise: the named
reroutes are plain edges; `Partitioned` is dropped with Branch_0 .. 6 / 9 .. 11, the spawn-actor and planar-
mesh-actor loops (Loop_13 / 19 / 21, Loop_0 / 18 / 20) and the three `NOT Partitioned` nodes; `Debug` with its
three branches and extrudes. The collision loops stay wired but receive nothing: officially they run only when
Partitioned is true (then CollisionGeometry), and Partitioned is dropped as false (ruling T20a).
"""
from pypcg import dsl
from pypcg.stages import s11_buildings as S
from pypcg.stages import s11_buildings_lots as L
from pypcg.stages import s11_buildings_rooftops as R

READS = {"Lots": "Subgraph_1", "HighRise": "Subgraph_5", "MeshTerrain": "Subgraph_10"}
CITY_DATA = "Subgraph_2"
TEXTURE = {"Small": "Subgraph_2_SmallDistrict", "Medium": "Subgraph_2_MediumDistrict",
           "Large": "Subgraph_2_LargeDistrict"}
ASSIGN = {"Small": "Subgraph_3", "Medium": "Subgraph_40", "Large": "Subgraph_41"}
SHAPE = {"Medium": ("Loop_2", "Subgraph_36"), "Large": ("Loop_1", "Subgraph_33")}
COLLISION = {"Small": "Loop_5", "Medium": "Loop_4", "Large": "Loop_3"}


def build():
    g = dsl.SlimGraph(S, more_modules=(L, R))
    lots, roofs = g.pynodes["s11_buildings_lots"], g.pynodes["s11_buildings_rooftops"]
    k = {}
    names = (list(READS.values()) + [CITY_DATA] + list(TEXTURE.values()) + list(ASSIGN.values())
             + [x for pair in SHAPE.values() for x in pair] + list(COLLISION.values()) + [m for m, _p in R.MESHES])
    for name in names:
        k[name] = g.keep(name)

    # ---- the class split, the native texture writes and their heights ----
    g.connect(k[READS["Lots"]], lots, "Lots")
    for cls, name in TEXTURE.items():
        tex = k[name]
        g.connect(lots[cls + "Lots"], tex, "PrimaryInput")
        g.connect(g.p("MinHeight%sDistrict" % cls), tex, "RemapValueOutLow")
        g.connect(g.p("MaxHeight%sDistrict" % cls), tex, "RemapValueOutHigh")
        g.connect(tex, g.py, cls + "Lots")
        x = g.node("PCGExtractAttributeSettings", "Read MaxHeight - %s" % cls,
                   set={"InputSource": dsl.sel("@data.MaxHeight")}, In=tex)
        g.connect(x, g.py, cls + "Heights")
    g.connect(k[READS["HighRise"]], g.py, "HighRise")
    g.connect(k[READS["MeshTerrain"]], g.py, "MeshTerrain")

    # ---- every stream's height back onto @data.MaxHeight ----
    w = {}
    for stream in S.STREAMS:
        w[stream] = g.node("PCGCopyAttributesSettings", "Write MaxHeight - %s" % stream,
                           set={"InputSource": dsl.sel("MaxHeight"), "OutputTarget": dsl.sel("@data.MaxHeight")},
                           Source=g.py[stream + "Heights"], Target=g.py[stream])

    # ---- the building nodes ----
    for cls, name in ASSIGN.items():
        g.connect(w[cls + "Footprints"], k[name], "BuildingsFootprints")
        g.connect(k[CITY_DATA], k[name], "CitySample data")
        g.connect(g.py["SpawnMeshes"], k[name], "SpawnMeshes")
    for cls, (shape, complex_) in SHAPE.items():
        g.connect(w[cls + "Complex"], k[shape], "In")
        g.connect(k[shape], k[complex_], "Out")
    for cls, name in COLLISION.items():
        g.connect(w[cls + "Collision"], k[name], "In")

    # ---- the rooftops: Gather_6 / Gather_3 order (the complex footprints first), the tags, the materials ----
    g.connect(k[ASSIGN["Small"]]["Rooftops Footprints"], roofs, "SmallRoofs")
    g.connect([k[SHAPE["Medium"][1]]["Footprints"], k[ASSIGN["Medium"]]["Rooftops Footprints"]], roofs, "MediumRoofs")
    g.connect([k[SHAPE["Large"][1]]["Footprints"], k[ASSIGN["Large"]]["Rooftops Footprints"]], roofs, "LargeRoofs")
    g.out(roofs["SmallRooftops"], roofs["MediumRooftops"], roofs["LargeRooftops"])
    for mesh, pin in R.MESHES:
        g.connect(roofs[pin], k[mesh], "PrimaryInput")
    return g
