# pcg_migration_verify.py — acceptance test for the City Sample migration.
#
# Run AFTER the editor has been restarted with the new plugins enabled. Proves,
# numerically, that the migrated library is actually usable:
#   * /CitySamplePCG/ is mounted
#   * all 18 city-stage graphs load and are PCGGraph assets
#   * all 27 building style assets load
#   * the moved /Game art loads
#   * the required script modules are present as classes
#
# Reads only. Nothing here writes or generates.

import json

R = {}
def S(x):
    return str(x)

EAL = unreal.EditorAssetLibrary

# ---------- 1. plugin mount ----------
M = {}
M["dir_mounted"] = EAL.does_directory_exist("/CitySamplePCG")
M["levels_dir"] = EAL.does_directory_exist("/CitySamplePCG/Levels")
M["pcg_dir"] = EAL.does_directory_exist("/CitySamplePCG/PCG")
M["examples_dir"] = EAL.does_directory_exist("/CitySamplePCG/Examples")
R["mount"] = M

# ---------- 2. the 18 city-stage graphs ----------
GRAPHS = [
    "PCG_1_1_Terrain", "PCG_1_2_BG_Buildings", "PCG_1_3_BG_Mountains",
    "PCG_2_1_MainTower_Footprint", "PCG_2_2_CentralPark_Footprint",
    "PCG_3_1_1_Districts", "PCG_3_1_2_Roads", "PCG_3_1_3_Highways",
    "PCG_3_1_4_Lots", "PCG_3_2_1_Ground", "PCG_3_2_2_LeftOverLots",
    "PCG_3_2_3_Parkings", "PCG_3_3_1_Buildings", "PCG_3_3_2_Rooftops",
    "PCG_4_1_MainTower_Visuals", "PCG_4_2_CentralPark_Visuals",
    "PCG_5_1_CityEdge", "PCG_5_2_OuterForest",
]
G = {}
ok = 0
for n in GRAPHS:
    p = "/CitySamplePCG/Levels/PCG/" + n
    e = {}
    try:
        e["exists"] = EAL.does_asset_exist(p)
        a = EAL.load_asset(p) if e["exists"] else None
        e["class"] = a.get_class().get_name() if a else None
        if a:
            try:
                e["nodes"] = len(a.get_editor_property("nodes"))
                e["edges"] = len(a.get_all_edges())
            except Exception as ie:
                e["graph_err"] = type(ie).__name__
        if e.get("class") == "PCGGraph":
            ok += 1
    except Exception as ex:
        e["err"] = "%s: %s" % (type(ex).__name__, S(ex)[:100])
    G[n] = e
R["city_graphs"] = G
R["city_graphs_loaded_as_PCGGraph"] = ok
R["city_graphs_expected"] = len(GRAPHS)

# ---------- 3. the 27 building style assets ----------
CODES = ["CHA","CHB","CHC","CHD","CHE","CHF","CHG","CHH","CHI","CHJ",
         "NYAA","NYAB","NYAC","NYAD","NYAE","NYAF","NYG","NYGA","NYH",
         "QBA","QBAA","SFA","SFB","SFC","SFD","SFE","SFJ"]
St = {}
sok = 0
for c in CODES:
    p = "/CitySamplePCG/PCG/DataAssets/Buildings/%s/SGD_%s_A" % (c, c)
    try:
        exists = EAL.does_asset_exist(p)
        a = EAL.load_asset(p) if exists else None
        cls = a.get_class().get_name() if a else None
        St[c] = {"exists": exists, "class": cls}
        if exists and a:
            sok += 1
    except Exception as ex:
        St[c] = "ERR %s" % type(ex).__name__
R["style_assets"] = St
R["style_assets_loaded"] = sok
R["style_assets_expected"] = len(CODES)

# ---------- 4. moved /Game art ----------
A = {}
ART = [
    "/Game/Building/CH/A/Kit_Bldg_CHA_L10_A/Mesh/SM_BLDG_CHA_L10_A_Wall_01_N1",
    "/Game/Building/Library/Building_Shapes/BLDG_Volume_C",
    "/Game/Building/Library/Kit_Hero_Bldg",
    "/Game/Prop/Kit_roof_exhaust_RR/Mesh/SM_roof_pipe_a_N1",
    "/Game/Prop/Kit_antenna_RR/Mesh/SM_roof_antenna_a_N1",
    "/Game/Road/Kit_Sidewalk_A/Mesh/SM_Sidewalk_0-75_3_A",
    "/Game/Road/Kit_Sidewalk_A/Mesh/SM_Plaza_Square_A",
    "/Game/Material/M_Bldg_Base",
]
for p in ART:
    try:
        a = EAL.load_asset(p)
        A[p.split("/Game/")[-1]] = (a.get_class().get_name() if a else None)
    except Exception as ex:
        A[p.split("/Game/")[-1]] = "ERR %s" % type(ex).__name__
R["game_art"] = A

# ---------- 5. required script modules resolve ----------
Cl = {}
for cls in ("PCGVolume", "PCGGraph", "PCGComponent", "PCGMeshPartition",
            "DynamicMesh", "PCGMeshPartitionDefinition"):
    Cl[cls] = hasattr(unreal, cls)
R["classes"] = Cl

# ---------- 6. inventory of the migrated mount ----------
I = {}
for path in ("/CitySamplePCG", "/CitySamplePCG/Levels",
             "/CitySamplePCG/PCG/DataAssets/Buildings", "/CitySamplePCG/Examples",
             "/Game/Building", "/Game/Prop", "/Game/Road"):
    try:
        I[path] = len(EAL.list_assets(path, recursive=True, include_folder=False))
    except Exception as ex:
        I[path] = "ERR %s" % type(ex).__name__
try:
    I["/Game_total"] = len(EAL.list_assets("/Game", recursive=True, include_folder=False))
except Exception as ex:
    I["/Game_total"] = "ERR %s" % type(ex).__name__
R["inventory"] = I

verdict = (M["dir_mounted"] and ok == len(GRAPHS) and sok == len(CODES))
R["MIGRATION_USABLE"] = bool(verdict)
print("PASS=%s  graphs=%d/%d  styles=%d/%d  mounted=%s" % (
    verdict, ok, len(GRAPHS), sok, len(CODES), M["dir_mounted"]))
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
