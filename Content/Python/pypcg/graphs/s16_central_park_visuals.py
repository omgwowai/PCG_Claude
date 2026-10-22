"""Slim graph of stage 16, CentralParkVisuals (spec 2.4).

Two Python nodes, because the computation sits on both sides of the native grammar and building nodes:

  s16_park_geometry           the centre, the transverse lines and their outlines, the border-road segments,
                              the pieces and their sidewalk ring, the walkpaths, the vegetation areas, the
                              lakes (edge, water plane, bed), the Met footprint, the exclusion polygons
  s16_central_park_visuals    after Spawn_Border_Road and Spawn_Met_Building: the grown road footprints, the
                              forest areas and their split, the trees, the Met rooftop dropped 10 cm

The official graph publishes nothing (its output node has no wired input) and neither does this one.

Scene reads (kept): `Get_Footprint_Actor` (role CentralParkFootprint), `Get_Drawn_Splines`, `Get_Lake`,
`Get_Forest_Exclusion`, `Subgraph_1` (Final terrain), `Subgraph_50` -> `Subgraph_51` (Intermediate-P5 terrain
points, for the lake writer), `Subgraph_57` (CitySample data); `Subgraph_52` (Roads + Parkings) kept UNWIRED,
as officially (no user).

Generation (all 13 kept, official settings): Spawn_Border_Road, Spawn_Transverse_Roads (disabled and unfed, as
officially), Spawn_Intersections, Subgraph_5, Subgraph_14, Subgraph_19, Spawn_Met_Building, Met_Rooftop_Mesh,
Met_Rooftops, Lake_Mesh, Subgraph_53 (Write_MeshTerrain, P6), Subgraph_6, Subgraph_66.

Native computation (s16.md section 3): `Subgraph_55` (the lake bed onto the 263 358 terrain points); the
three grass chains (Step F); the post-grammar projectors and street-prop chain (ruling T17a's precedent).
What differs from the official wiring: the named reroutes, `Gather_0..3` and `Reroute_0` are plain edges;
the partition branches are gone (`Partitioned` false); `Branch_6/7` live in the vegetation node, which reads
`UseMegaplantsTrees` from the slim graph's own getter.
"""
from pypcg import dsl
from pypcg.stages import s16_central_park_visuals as S
from pypcg.stages import s16_park_geometry as GEO

READS = {"Footprint": "Get_Footprint_Actor", "DrawnSplines": "Get_Drawn_Splines", "Lake": "Get_Lake",
         "ForestExclusion": "Get_Forest_Exclusion", "MeshTerrain": "Subgraph_1"}
OTHER_READS = ("Subgraph_50", "Subgraph_51", "Subgraph_52", "Subgraph_57")
GENERATION = ("Spawn_Border_Road", "Spawn_Transverse_Roads", "Spawn_Intersections", "Subgraph_5", "Subgraph_14",
              "Subgraph_19", "Spawn_Met_Building", "Met_Rooftop_Mesh", "Met_Rooftops", "Lake_Mesh", "Subgraph_53",
              "Subgraph_6", "Subgraph_66")
# the three grass chains: fill -> noise -> density filter -> projector -> assign (official order into Gather_3)
GRASS = {"Selected": ("Subgraph_32", "Subgraph_34", "Subgraph_36", "Subgraph_11", "Subgraph_63"),
         "Unselected": ("Subgraph_28", "Subgraph_30", "Subgraph_31", "Subgraph_12", "Subgraph_64"),
         "ForestZone": ("Subgraph_37", "Subgraph_39", "Subgraph_40", "Subgraph_15", "Subgraph_65")}
PROPS = ("Subgraph_27", "AttributeCast_1", "FilterDataByAttribute_1", "FilterDataByAttribute_2",
         "FilterDataByAttribute_3", "FilterDataByAttribute_4", "AttributeMathsOp_5", "AttributeMathsOp_6",
         "FilterDataByAttribute_5", "FilterDataByType_2", "AttributeStringOp_1", "AttributeStringOp_2",
         "CopyAttributes_0", "AttributeCast_0")
PROJECTORS = ("Subgraph_42", "Subgraph_46", "Subgraph_48")
NATIVE = ("Subgraph_55",) + tuple(n for chain in GRASS.values() for n in chain) + PROPS + PROJECTORS


def build():
    g = dsl.SlimGraph(S, more_modules=(GEO,))
    geo_node = g.pynodes["s16_park_geometry"]
    veg = g.py
    k = {name: g.keep(name) for name in tuple(READS.values()) + OTHER_READS + GENERATION + NATIVE}
    terrain = k["Subgraph_1"]

    # ---- the geometry node ----
    for pin, name in READS.items():
        g.connect(k[name], geo_node, pin)
    g.connect(geo_node["BorderSegments"], k["Spawn_Border_Road"], "PrimaryInput")
    g.connect(geo_node["Corners"], k["Spawn_Intersections"], "PrimaryInput")
    g.connect(geo_node["SidewalkSegments"], k["Subgraph_5"], "PrimaryInput")
    g.connect(geo_node["Walkpaths"], k["Subgraph_19"], "PrimaryInput")
    g.connect(geo_node["LakeEdge"], k["Subgraph_14"], "PrimaryInput")
    g.connect(geo_node["Lake"], k["Lake_Mesh"], "PrimaryInput")
    g.connect(geo_node["MetFootprint"], k["Spawn_Met_Building"], "BuildingsFootprints")
    g.connect(k["Subgraph_57"], k["Spawn_Met_Building"], "CitySample data")

    # ---- the lake bed: the terrain points onto the bed (native Subgraph_55) -> the writer ----
    g.connect(k["Subgraph_50"], k["Subgraph_51"], "PrimaryInput")
    g.connect(k["Subgraph_51"], k["Subgraph_55"], "PrimaryInput")
    g.connect(geo_node["LakeBed"], k["Subgraph_55"], "SecondaryInput")
    g.connect(k["Subgraph_55"], k["Subgraph_53"], "PrimaryInput")

    # ---- the vegetation node ----
    g.connect(geo_node["ParkAreas"], veg, "ParkAreas")
    g.connect(geo_node["Exclusions"], veg, "Exclusions")
    g.connect(k["Spawn_Border_Road"]["Footprints"], veg, "RoadFootprints")
    g.connect(k["Spawn_Met_Building"]["Rooftops Footprints"], veg, "MetRoofs")
    g.connect(terrain, veg, "MeshTerrain")
    g.connect(k["Spawn_Met_Building"]["Rooftops Footprints"], k["Met_Rooftop_Mesh"], "PrimaryInput")
    g.connect(veg["MetRoofsLowered"], k["Met_Rooftops"], "PrimaryInput")
    g.connect(k["Met_Rooftops"], k["Subgraph_66"], "PrimaryInput")

    # ---- the grass chains, native (Step F) ----
    sources = {"Selected": veg["Selected"], "Unselected": veg["Unselected"], "ForestZone": geo_node["ForestZone"]}
    grass = {}
    for side, (fill, noise, dens, proj, assign) in GRASS.items():
        g.connect(sources[side], k[fill], "PrimaryInput")
        g.connect(k[fill], k[noise], "PrimaryInput")
        g.connect(k[noise], k[dens], "PrimaryInput")
        g.connect(k[dens]["Selected"], k[proj], "In Points")
        g.connect(terrain, k[proj], "Surface")
        g.connect(k[proj], k[assign], "PrimaryInput")
        grass[side] = k[assign]

    # ---- the post-grammar point chain, native (T17a) ----
    g.connect([k["Spawn_Intersections"]["Points"], k["Subgraph_5"]["Points"]], k["Subgraph_27"], "In Points")
    g.connect(terrain, k["Subgraph_27"], "Surface")
    g.connect(k["Subgraph_27"], k["AttributeCast_1"], "In")
    g.connect(k["AttributeCast_1"], k["FilterDataByAttribute_1"], "In")
    g.connect(k["FilterDataByAttribute_1"]["OutsideFilter"], k["FilterDataByAttribute_2"], "In")
    g.connect(k["FilterDataByAttribute_2"]["OutsideFilter"], k["FilterDataByAttribute_3"], "In")
    g.connect(k["FilterDataByAttribute_3"]["OutsideFilter"], k["FilterDataByAttribute_4"], "In")
    g.connect([k["FilterDataByAttribute_%d" % i]["InsideFilter"] for i in (1, 2, 3, 4)], k["AttributeMathsOp_5"], "InA")
    g.connect(k["AttributeMathsOp_5"], k["AttributeMathsOp_6"], "InA")
    g.connect([k["FilterDataByAttribute_4"]["OutsideFilter"], k["AttributeMathsOp_6"]], k["FilterDataByAttribute_5"], "In")
    g.connect(k["FilterDataByAttribute_5"]["InsideFilter"], k["FilterDataByType_2"], "In")
    g.connect(k["FilterDataByType_2"]["InsideFilter"], k["AttributeStringOp_1"], "In")
    g.connect(k["AttributeStringOp_1"], k["AttributeStringOp_2"], "In")
    g.connect(k["AttributeStringOp_2"], k["CopyAttributes_0"], "Target")
    g.connect(k["AttributeStringOp_2"], k["CopyAttributes_0"], "Source")
    g.connect(k["CopyAttributes_0"], k["AttributeCast_0"], "In")
    g.connect(k["Subgraph_19"]["Points"], k["Subgraph_42"], "In Points")
    g.connect(k["Subgraph_14"]["Points"], k["Subgraph_46"], "In Points")
    g.connect(k["Spawn_Border_Road"]["Points"], k["Subgraph_48"], "In Points")
    for name in PROJECTORS:
        g.connect(terrain, k[name], "Surface")

    # ---- everything into Subgraph_6, in Gather_3's order ----
    spawn = k["Subgraph_6"]
    g.connect([k["AttributeCast_0"], k["FilterDataByAttribute_5"]["InsideFilter"],
               k["FilterDataByAttribute_5"]["OutsideFilter"]], spawn, "PrimaryInput")        # Sidewalks (Gather_2)
    g.connect(k["Subgraph_46"], spawn, "PrimaryInput")                                       # Lake edges
    g.connect(veg["Trees"], spawn, "PrimaryInput")                                           # Megaplant trees
    g.connect([grass["Selected"], grass["Unselected"]], spawn, "PrimaryInput")               # Wild grass (Gather_1)
    g.connect(grass["ForestZone"], spawn, "PrimaryInput")                                    # exclusion-zone grass
    g.connect(k["Subgraph_42"], spawn, "PrimaryInput")                                       # walkpath
    g.connect(k["Subgraph_48"], spawn, "PrimaryInput")                                       # road
    return g
