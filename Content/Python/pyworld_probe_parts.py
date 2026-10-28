# pyworld_probe_parts.py -- READ-ONLY: materials of a Megaplant assembly's parts.
import json

import unreal

reg = unreal.AssetRegistryHelpers.get_asset_registry()
out = {}
for ad in reg.get_assets_by_path("/CitySamplePCG/Megaplants/Tree_European_Beech/Instances", True):
    m = unreal.load_asset(str(ad.package_name))
    if isinstance(m, unreal.StaticMesh):
        out[str(ad.asset_name)] = [s.material_interface.get_name() if s.material_interface else None
                                   for s in m.get_editor_property("static_materials")]
print(json.dumps(out))
