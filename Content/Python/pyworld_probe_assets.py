import gc
import json

import unreal

# pyworld_probe_assets.py -- READ ONLY. Facts the PyWorld design depends on: mounted plugins, the mesh lists
# of the vegetation / rock libraries, the heightmap texture, and how the engine's MeshTerrain examples configure
# Write_MeshTerrain (Channels, ModifierLayerPriority), Transform_MeshTerrain_Erosion and Get_ActorData.

EAL = unreal.EditorAssetLibrary


def _meshes(root, limit=60):
    try:
        paths = EAL.list_assets(root, True, False)
    except Exception as ex:
        return "ERR %s" % str(ex)[:120]
    out = []
    for p in paths:
        d = unreal.EditorAssetLibrary.find_asset_data(p)
        if str(d.asset_class_path.asset_name) == "StaticMesh":
            out.append(str(p).split(".")[0])
    return out[:limit]


def _nodes(path, wanted):
    from pypcg import extract
    try:
        ir = extract.export_path(path)
    except Exception as ex:
        return "ERR %s" % str(ex)[:200]
    out = []
    for n in ir["nodes"]:
        sg = (n.get("subgraph") or "").split("/")[-1].split(".")[0]
        if any(w in sg or w in n["class"] for w in wanted):
            out.append({"name": n["name"], "title": n.get("title"), "sub": sg, "overrides": n.get("overrides"),
                        "pin_defaults": n.get("pin_defaults"),
                        "inputs": [[p["label"], p["edges"]] for p in n.get("inputs", []) if p["edges"]]})
    return out


def run():
    out = {}
    out["mounted"] = {d: bool(EAL.does_directory_exist(d)) for d in
                      ["/PCGBiomeSample", "/PCGBiomeCore", "/PCGPrimitives_MeshPartitionInterop", "/CitySamplePCG"]}
    out["meshes"] = {
        "biome": _meshes("/PCGBiomeSample/Meshes"),
        "megaplants": _meshes("/CitySamplePCG/Megaplants", 80),
        "wild_grass": _meshes("/CitySamplePCG/Megascans/Plants"),
        "mossy_rock": _meshes("/Game/Megascans/3D_Assets/Mossy_Rock_ulldfii"),
        "birch": _meshes("/Game/Prop/Kit_Tree_Birch"),
        "maple": _meshes("/Game/Prop/Kit_Tree_Maple_Sugar") + _meshes("/Game/Prop/Kit_Tree_Maple_Red"),
        "rail": _meshes("/Game/Megascans/3D_Assets/Modular_Rail_Guard_4m_00"),
        "fence": _meshes("/Game/Prop/CONSTRUCTION/Kit_Fence"),
        "prim": _meshes("/PCGPrimitives/Meshes"),
    }
    tex = EAL.load_asset("/PCGPrimitives_MeshPartitionInterop/Assets/Textures/Heightmaps/Heightmap_Valley_2km")
    if tex:
        out["heightmap"] = {"class": tex.get_class().get_name(), "size": [tex.blueprint_get_size_x(), tex.blueprint_get_size_y()],
                            "srgb": str(tex.get_editor_property("srgb")),
                            "compression": str(tex.get_editor_property("compression_settings"))}
    ex = "/PCGPrimitives_MeshPartitionInterop/Examples/MeshTerrain/"
    out["occlusion_texturing"] = _nodes(ex + "MeshTerrain_Occlusion_Texturing", ["Write_MeshTerrain", "Get_MeshTerrain", "Erosion", "Write_Attribute"])
    out["forest_with_road"] = _nodes(ex + "MeshTerrain_Hills_ForestWithRoad", ["Write_MeshTerrain", "Get_MeshTerrain", "Assign_Shape", "Spawn_Assets", "Write_Attribute"])
    from pypcg import extract
    for name, path in [("erosion", "/PCGPrimitives_MeshPartitionInterop/Primitives/Transform/Transform_MeshTerrain_Erosion"),
                       ("get_actor_data", "/PCGPrimitives/Primitives/Get/Get_ActorData"),
                       ("get_actor_data_by_ref", "/PCGPrimitives/Primitives/Get/Get_ActorDataByRef"),
                       ("write_mesh_terrain", "/PCGPrimitives_MeshPartitionInterop/Primitives/Write/Write_MeshTerrain")]:
        try:
            ir = extract.export_path(path)
            out[name] = {"params": [[p["name"], p["type"], p["value"]] for p in ir["params"]],
                         "native": sorted({n["class"] for n in ir["nodes"]}),
                         "data_from_actor": [n.get("settings") for n in ir["nodes"] if n["class"] == "PCGDataFromActorSettings"][:2]}
        except Exception as e:
            out[name] = "ERR %s" % str(e)[:200]
    return out


mcp_result = json.loads(json.dumps(run(), default=str))
gc.collect()
