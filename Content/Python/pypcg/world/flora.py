"""PyWorld's plant and rock palette for the vegetation communities (docs/superpowers/specs/
2026-10-23-pyworld-vegetation-ecology-design.md): high-detail Nanite meshes from Electric Dreams (/Game/Megascans,
copied by Tools/pyworld/ed_closure.py) and the City Sample Megaplants trees. Sizes are the meshes' bounds in cm
(pyworld_veg_probe.py, 2026-10-23). No unreal import."""


def _p(pkg):
    return "%s.%s" % (pkg, pkg.rsplit("/", 1)[1])


_ED_P = "/Game/Megascans/3D_Plants/%s/SM_%s_%s"
_ED_A = "/Game/Megascans/3D_Assets/%s/SM_%s_%s"
_MP = "/CitySamplePCG/Megaplants/Tree_%s/Tree_%s_01/SM_%s_01_%s"


def plants(folder, ids, name=None):
    return tuple(_p(_ED_P % (folder, name or folder, i)) for i in ids)


def assets(folder, ids, name=None):
    return tuple(_p(_ED_A % (folder, name or folder, i)) for i in ids)


def megaplant(tree, ids):
    """The summer copies of the City Sample Megaplants (pyworld_megaplant_summer.py: green foliage instead of the
    demo's autumn); they are Nanite assemblies and need r.Nanite.Foliage=1 (Config/DefaultEngine.ini) for leaves."""
    stem = "Norway_Maple_Forest" if tree == "Norway_Maple" else tree
    return tuple(_p("/Game/PyPCG/World/Trees/SM_%s_01_%s" % (stem, v)) for v in ids)


def _ids(*nums):
    return ["%02d" % n for n in nums]


_HB = "/Game/Megascans/3D_Plants/EuropeanHornbeam/Geometry/SimpleWind/SM_EuropeanHornbeam_%s"


def hornbeam(*names):
    return tuple(_p(_HB % n) for n in names)


# A species: its meshes, the layer it lives in, the scale range, how deep it sinks (cm), how much it follows the
# slope (0 upright .. 1 on the normal), the spacing radius (cm, trees and shrubs) and, for ground plants, how many
# plants a clump has and how far they spread (cm).
SPECIES = {
    # ---- canopy trees
    "Beech": dict(meshes=megaplant("European_Beech", "AB"), layer="tree", scale=(0.78, 1.0), sink=15.0, space=420.0),
    "BeechYoung": dict(meshes=megaplant("European_Beech", "CD"), layer="tree", scale=(0.85, 1.15), sink=10.0, space=220.0),
    "Hornbeam": dict(meshes=hornbeam(*("Forest_%02d" % n for n in range(1, 9))), layer="tree", scale=(0.9, 1.2),
                     sink=15.0, space=360.0),
    "HornbeamSmall": dict(meshes=hornbeam("Forest_09", "Forest_10"), layer="tree", scale=(0.9, 1.25), sink=10.0,
                          space=200.0),
    "HornbeamField": dict(meshes=hornbeam("Field_01", "Field_02", "Field_03", "Field_04"), layer="tree",
                          scale=(0.85, 1.15), sink=15.0, space=650.0),
    "Maple": dict(meshes=megaplant("Norway_Maple", "AB"), layer="tree", scale=(0.85, 1.15), sink=15.0, space=330.0),
    "MapleYoung": dict(meshes=megaplant("Norway_Maple", "C"), layer="tree", scale=(0.85, 1.2), sink=10.0,
                       space=180.0),
    "Aspen": dict(meshes=megaplant("European_Aspen", "ABC"), layer="tree", scale=(0.85, 1.2), sink=12.0, space=230.0),
    "Alder": dict(meshes=megaplant("Black_Alder", "ABCD"), layer="tree", scale=(0.8, 1.1), sink=15.0, space=320.0),
    "Hazel": dict(meshes=megaplant("Common_Hazel", "AB"), layer="tree", scale=(0.9, 1.3), sink=10.0, space=260.0),
    "DeadTree": dict(meshes=assets("DeadTree", _ids(1, 2)), layer="tree", scale=(0.9, 1.4), sink=20.0, space=250.0),
    # ---- shrubs
    "Elderberry": dict(meshes=plants("Elderberry", _ids(5, 6, 7, 8, 9, 10, 11, 12)), layer="shrub", scale=(0.8, 1.4),
                       sink=8.0, space=130.0, align=0.2),
    "HazelSmall": dict(meshes=megaplant("Common_Hazel", "CD"), layer="shrub", scale=(0.9, 1.4), sink=8.0, space=120.0),
    "Sapling": dict(meshes=hornbeam(*("Sapling_%02d" % n for n in range(1, 9))), layer="shrub", scale=(0.8, 1.4),
                    sink=6.0, space=110.0, align=0.15),
    "Seedling": dict(meshes=hornbeam(*("Seedling_%02d" % n for n in range(1, 4))), layer="shrub", scale=(0.8, 1.3),
                     sink=4.0, space=70.0, align=0.3),
    "MapleSapling": dict(meshes=megaplant("Norway_Maple", "D"), layer="shrub", scale=(0.8, 1.2), sink=6.0,
                         space=110.0),
    "AspenSapling": dict(meshes=megaplant("European_Aspen", "D"), layer="shrub", scale=(0.8, 1.3), sink=6.0, space=110.0),
    # ---- ground plants (clump = (min, max) plants, spread cm)
    "Kikuyu": dict(meshes=plants("KikuyuGrass", _ids(1, 2, 3, 4, 5, 6)), layer="grass", scale=(0.8, 1.3), sink=3.0,
                   align=0.6, clump=(1, 3), spread=70.0),
    "KikuyuSmall": dict(meshes=plants("KikuyuGrass", _ids(7, 8, 9, 10)), layer="grass", scale=(0.9, 1.4), sink=2.0,
                        align=0.6, clump=(2, 4), spread=50.0),
    "WildGrass": dict(meshes=tuple(_p("/CitySamplePCG/Megascans/Plants/Wild_Grass/Medium/StaticMeshes/SM_Grass_Var" + v)
                                   for v in "ADEFG"), layer="grass", scale=(0.8, 1.3), sink=3.0, align=0.5,
                      clump=(1, 2), spread=80.0),
    "Clover": dict(meshes=plants("CloverVarieties", _ids(1, 2, 3)), layer="ground", scale=(0.8, 1.3), sink=1.0,
                   align=1.0, clump=(1, 3), spread=90.0),
    "CloverPatch": dict(meshes=plants("CloverVarieties", _ids(4, 5)), layer="ground", scale=(0.6, 1.0), sink=2.0,
                        align=1.0, clump=(1, 1), spread=0.0),
    "Fern": dict(meshes=plants("Fern", _ids(1, 2, 3, 4, 5, 6)), layer="ground", scale=(0.8, 1.4), sink=4.0, align=0.5,
                 clump=(1, 3), spread=110.0),
    "LadyFern": dict(meshes=plants("SilverLadyFern", _ids(1, 2, 3)), layer="ground", scale=(0.8, 1.3), sink=3.0,
                     align=0.5, clump=(1, 3), spread=80.0),
    "BeechFern": dict(meshes=plants("BeechFern", _ids(4, 5, 9, 10, 11, 15)), layer="ground", scale=(0.9, 1.5),
                      sink=2.0, align=0.6, clump=(2, 5), spread=60.0),
    "Windflower": dict(meshes=plants("WhiteWindflower", _ids(1, 2, 3, 4, 5, 6, 7)), layer="ground", scale=(0.5, 0.8),
                       sink=2.0, align=0.5, clump=(1, 3), spread=60.0),
    "Archangel": dict(meshes=plants("YellowArchangel", _ids(4, 8, 9, 10, 1, 2)), layer="ground", scale=(1.2, 2.0),
                      sink=1.0, align=0.6, clump=(3, 7), spread=45.0),
    "Lily": dict(meshes=plants("LilyOfTheValley", _ids(1, 2, 3, 4)), layer="ground", scale=(0.9, 1.3), sink=2.0,
                 align=0.6, clump=(2, 4), spread=50.0),
    "Periwinkle": dict(meshes=plants("Periwinkle", _ids(1, 2, 3, 4)), layer="ground", scale=(0.4, 0.6), sink=2.0,
                       align=0.4, clump=(2, 4), spread=40.0),
    "Crownbeard": dict(meshes=plants("Crownbeard", _ids(3, 4, 5, 6, 7, 8, 9)), layer="ground", scale=(0.8, 1.2),
                       sink=2.0, align=0.3, clump=(2, 4), spread=55.0),
    "Shamrock": dict(meshes=plants("PurpleShamrock", _ids(1, 2, 3)), layer="ground", scale=(1.0, 1.6), sink=1.0,
                     align=0.7, clump=(3, 6), spread=40.0),
    "Purslane": dict(meshes=plants("CommonPurslane", _ids(1, 2, 3, 4, 5)), layer="ground", scale=(1.0, 1.6), sink=0.5,
                     align=1.0, clump=(2, 4), spread=45.0),
    "Lachenalia": dict(meshes=plants("RedLachenalia", _ids(1, 6, 12, 13, 14)), layer="ground", scale=(1.0, 1.6),
                       sink=1.0, align=0.5, clump=(2, 5), spread=35.0),
    "Moss": dict(meshes=plants("CustomMoss", _ids(1, 2, 3, 4, 5)), layer="ground", scale=(1.5, 3.0), sink=6.0, align=1.0,
                 clump=(2, 5), spread=60.0),
    "GroundCover": dict(meshes=plants("GroundCover", _ids(1, 2, 3, 4, 5, 6, 7, 8)), layer="ground", scale=(1.0, 1.8),
                        sink=1.0, align=1.0, clump=(2, 5), spread=60.0),
    "Ivy": dict(meshes=plants("EnglishIvy", _ids(1, 3, 4, 6, 7, 8)), layer="ground", scale=(0.9, 1.4), sink=2.0, align=0.8,
                clump=(2, 4), spread=60.0),
    "Leaves": dict(meshes=plants("DeadLeaves", _ids(1, 13, 14, 12)), layer="ground", scale=(1.0, 1.6), sink=2.0,
                   align=1.0, clump=(2, 4), spread=160.0),
    "Pebbles": dict(meshes=assets("SmallStonesPack", _ids(*range(1, 15))), layer="ground", scale=(1.0, 2.5), sink=3.0,
                    align=1.0, clump=(3, 7), spread=70.0),
    # ---- dead wood (logs lie across the slope)
    "Log": dict(meshes=assets("FallenSpruceTree", _ids(1)) + assets("LargeFallenTree", _ids(1, 2))
                + assets("OldFallenTree", _ids(1, 2)) + assets("MossyTree", _ids(1)), layer="debris", scale=(0.8, 1.1),
                sink=12.0, align=1.0),
    "Stump": dict(meshes=assets("TreeStump", _ids(1)) + assets("BirchTreeStump", _ids(1)) + assets("RottenTreeStump", _ids(1, 2))
                  + assets("BrokenStump", _ids(1)), layer="debris", scale=(0.8, 1.3), sink=10.0, align=0.5),
    "Branch": dict(meshes=assets("DryBranches", _ids(*range(1, 9))) + assets("OakBranch", _ids(1))
                   + assets("BrokenTreeBranch", _ids(1)), layer="debris", scale=(0.8, 1.5), sink=1.0, align=1.0,
                   clump=(2, 5), spread=120.0),
    "Twigs": dict(meshes=assets("WoodenSticksAndTwigs", _ids(*range(1, 11))), layer="debris", scale=(1.5, 3.0), sink=0.5,
                  align=1.0, clump=(4, 9), spread=80.0),
    "Roots": dict(meshes=assets("MossyForestRoots", _ids(1, 2, 3)), layer="debris", scale=(0.7, 1.0), sink=6.0, align=1.0),
    "ClimbingIvy": dict(meshes=plants("Ivy", _ids(11, 17, 25, 18, 12), name="Ivy"), layer="debris", scale=(0.8, 1.1),
                        sink=3.0, align=0.0),
    # ---- rocks (sink is a fraction of the mesh height)
    "Crag": dict(meshes=assets("NordicBoulder", _ids(1, 2)) + assets("TundraMossyBoulder", _ids(1)), layer="rock",
                 scale=(0.25, 0.55), sink=0.3, align=0.7),
    "Boulder": dict(meshes=assets("MossyForestBoulder", _ids(1, 3, 4, 7)), layer="rock", scale=(0.6, 1.3), sink=0.3,
                    align=0.6),
    "Rock": dict(meshes=assets("MossyForestBoulder", _ids(2, 5, 6)) + assets("MossyForestRock", _ids(1, 2, 3))
                 + assets("LichenedForestBoulder", _ids(1)), layer="rock", scale=(0.4, 1.1), sink=0.25, align=0.8),
    "RockSlab": dict(meshes=assets("MossyRocks", _ids(1, 2)), layer="rock", scale=(0.5, 1.0), sink=0.4, align=1.0),
}

# mesh height (cm): rocks sink a fraction of it
HEIGHT = {}
_SIZES = {"NordicBoulder_01": 407, "NordicBoulder_02": 399, "TundraMossyBoulder_01": 179, "MossyForestBoulder_01": 95,
          "MossyForestBoulder_02": 60, "MossyForestBoulder_03": 130, "MossyForestBoulder_04": 199,
          "MossyForestBoulder_05": 69, "MossyForestBoulder_06": 69, "MossyForestBoulder_07": 94, "MossyForestRock_01": 43,
          "MossyForestRock_02": 71, "MossyForestRock_03": 19, "LichenedForestBoulder_01": 46, "MossyRocks_01": 34,
          "MossyRocks_02": 35}
for _sp in SPECIES.values():
    for _m in _sp["meshes"]:
        _k = _m.rsplit(".", 1)[1][3:]
        if _k in _SIZES:
            HEIGHT[_m] = float(_SIZES[_k])

TREES = frozenset(n for n, s in SPECIES.items() if s["layer"] == "tree")
TREE_MESHES = frozenset(m for n in TREES for m in SPECIES[n]["meshes"])
TREE_SINK = {m: SPECIES[n]["sink"] for n in TREES for m in SPECIES[n]["meshes"]}
ALDERS = frozenset(SPECIES["Alder"]["meshes"])


def all_meshes():
    return sorted({m for s in SPECIES.values() for m in s["meshes"]})
