import gc
import json

import unreal

# pyworld_probe_defaults.py -- READ ONLY. The user-parameter defaults of the primitives PyWorld wires (what an
# absent override means), and the Norway Maple / Birch folders' static meshes.


def run():
    from pypcg import extract
    out = {}
    for name, path in [("Spawn_Assets", "/PCGPrimitives/Primitives/Spawn/Spawn_Assets"),
                       ("Assign_ShapeGrammarDefinition", "/PCGPrimitives/Primitives/Assign/Assign_ShapeGrammarDefinition"),
                       ("Get_MeshTerrain", "/PCGPrimitives_MeshPartitionInterop/Primitives/Get/Get_MeshTerrain"),
                       ("Extract_MeshTerrainPoints", "/PCGPrimitives_MeshPartitionInterop/Primitives/Extract/Extract_MeshTerrainPoints")]:
        ir = extract.export_path(path)
        out[name] = [[p["name"], p["type"], p["value"]] for p in ir["params"]
                     if not p["name"].endswith("Graph")]
    eal = unreal.EditorAssetLibrary
    out["maple"] = [str(x).split(".")[0] for x in eal.list_assets("/CitySamplePCG/Megaplants/Tree_Norway_Maple", True, False)][:40]
    birch = {}
    for p in eal.list_assets("/Game/Prop/Kit_Tree_Birch/Mesh", True, False):
        a = eal.load_asset(str(p).split(".")[0])
        if isinstance(a, unreal.StaticMesh):
            b = a.get_bounding_box()
            birch[str(p).split(".")[0]] = [round(b.max.x - b.min.x), round(b.max.y - b.min.y), round(b.min.z), round(b.max.z)]
    out["birch"] = birch
    return out


mcp_result = json.loads(json.dumps(run(), default=str))
gc.collect()
