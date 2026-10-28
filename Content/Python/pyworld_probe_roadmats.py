# pyworld_probe_roadmats.py -- READ-ONLY: the lane module's material (PCGPrimitives SM_Lane_Car_400_500), its parents and
# textures, plus the candidate road textures' sizes / VT flags / compression, and the PCG Spawn Dynamic Mesh node's pins
# (made on a throwaway graph that is deleted again).
import json

import unreal

EAL = unreal.EditorAssetLibrary
out = {}
m = unreal.load_asset("/PCGPrimitives/Meshes/SM_Lane_Car_400_500")
out["lane_mats"] = []
for s in m.get_editor_property("static_materials"):
    mi = s.material_interface
    chain, p = [], mi
    while p is not None:
        chain.append(p.get_path_name())
        p = p.get_editor_property("parent") if isinstance(p, unreal.MaterialInstance) else None
    tex = {}
    if mi:
        for n in unreal.MaterialEditingLibrary.get_texture_parameter_names(mi):
            t = unreal.MaterialEditingLibrary.get_material_instance_texture_parameter_value(mi, n) \
                if isinstance(mi, unreal.MaterialInstance) else None
            tex[str(n)] = t.get_path_name() if t else None
    out["lane_mats"].append({"slot": str(s.material_slot_name), "chain": chain, "tex": tex})
b = m.get_bounding_box()
out["lane_bounds"] = [[b.min.x, b.min.y, b.min.z], [b.max.x, b.max.y, b.max.z]]
S = "/Game/Megascans/Surfaces/"
for p in (S + "Asphalt_Dried01_2x2/Asphalt_Dried01_C", S + "Asphalt_Dried01_2x2/Asphalt_Dried01_N",
          S + "Asphalt_Dried01_2x2/Asphalt_Dried01_AOMRD", S + "Ground_Rubble_2x2_00/Ground_Rubble_2x2_00_Albedo",
          S + "Ground_Rubble_2x2_00/Ground_Rubble_2x2_00_Normal", S + "Ground_Rubble_2x2_00/Ground_Rubble_2x2_00_AOMRD",
          S + "Gravel_Pavement_2x2/Gravel_Pavement_2x2_N"):
    t = unreal.load_asset(p)
    out[p.rsplit("/", 1)[1]] = None if t is None else [t.blueprint_get_size_x(), bool(t.get_editor_property("virtual_texture_streaming")),
                                                        str(t.get_editor_property("compression_settings")), bool(t.get_editor_property("srgb"))]
cls = unreal.load_class(None, "/Script/PCGGeometryScriptInterop.PCGSpawnDynamicMeshSettings")
cdo = unreal.get_default_object(cls)
out["spawn_dm_class"] = cls.get_name() if cls else None
print(json.dumps(out, indent=1))
