import gc
import json

import unreal

# pyworld_probe_meshes.py -- READ ONLY. Bounds (min / max in the mesh's own space) of every mesh PyWorld places,
# so the plan's module lengths, pivots and scales come from the assets, not from their names.

MESHES = [
    "/Engine/BasicShapes/Cube", "/Engine/BasicShapes/Cylinder", "/Engine/BasicShapes/Cone", "/Engine/BasicShapes/Plane",
    "/PCGPrimitives/Meshes/SM_Lane_Car_400_500", "/PCGPrimitives/Meshes/SM_Lane_Divider_15_500",
    "/PCGPrimitives/Meshes/SM_Lane_Path_300_160", "/PCGPrimitives/Meshes/SM_Lane_Sidewalk_300_500",
    "/PCGPrimitives/Meshes/SM_Square_150_150", "/PCGPrimitives/Meshes/SM_park_bench_N01",
    "/Game/Megascans/3D_Assets/Modular_Rail_Guard_4m_00/Modular_Rail_Guard_4m_LOD0_uh1kbcxga",
    "/Game/Prop/Kit_StreetLamp_A/Mesh/SM_StreetLamp_A_Pole_Small",
    "/Game/Megascans/3D_Assets/Mossy_Rock_ulldfii/S_Mossy_Rock_ulldfii_lod3_Var1",
    "/PCGBiomeSample/Meshes/PCG_Boulder_01", "/PCGBiomeSample/Meshes/PCG_Pine_01", "/PCGBiomeSample/Meshes/PCG_Spruce_01",
    "/PCGBiomeSample/Meshes/PCG_Tree_01", "/PCGBiomeSample/Meshes/PCG_Sapling_02",
    "/CitySamplePCG/Megaplants/Tree_Black_Alder/Tree_Black_Alder_01/SM_Black_Alder_01_A",
    "/CitySamplePCG/Megaplants/Tree_Common_Hazel/Tree_Common_Hazel_01/SM_Common_Hazel_01_A",
    "/CitySamplePCG/Megaplants/Tree_European_Beech/Tree_European_Beech_01/SM_European_Beech_01_A",
    "/CitySamplePCG/Megaplants/Tree_Norway_Maple/Tree_Norway_Maple_01/SM_Norway_Maple_01_A",
    "/CitySamplePCG/Megaplants/Tree_European_Aspen/Tree_European_Aspen_01/SM_European_Aspen_01_A",
    "/CitySamplePCG/Megascans/Plants/Wild_Grass/Medium/StaticMeshes/SM_Grass_VarA",
    "/Game/Prop/kit_ocean/Material/MI_ocean",
    "/Engine/BasicShapes/BasicShapeMaterial",
]


def run():
    out = {}
    eal = unreal.EditorAssetLibrary
    for p in MESHES:
        a = eal.load_asset(p)
        if a is None:
            out[p] = None
            continue
        if isinstance(a, unreal.StaticMesh):
            b = a.get_bounding_box()
            out[p] = {"min": [round(v, 1) for v in (b.min.x, b.min.y, b.min.z)],
                      "max": [round(v, 1) for v in (b.max.x, b.max.y, b.max.z)],
                      "nanite": bool(a.get_editor_property("nanite_settings").get_editor_property("enabled"))}
        else:
            out[p] = a.get_class().get_name()
    maple = eal.list_assets("/CitySamplePCG/Megaplants/Tree_Norway_Maple", True, False)
    out["maple_meshes"] = [str(x).split(".")[0] for x in maple if "/Tree_Norway_Maple_01/SM_" in str(x)]
    beech = eal.list_assets("/CitySamplePCG/Megaplants/Tree_European_Beech", True, False)
    out["beech_meshes"] = [str(x).split(".")[0] for x in beech if "/Tree_European_Beech_01/SM_" in str(x)]
    return out


mcp_result = json.loads(json.dumps(run(), default=str))
gc.collect()
