# tl_probe_ground.py -- READ-ONLY. Floor mesh size, and candidate ground /
# pavement materials in the project.
import json


def main():
    EAL = unreal.EditorAssetLibrary
    R = {}
    m = EAL.load_asset("/Engine/MapTemplates/SM_Template_Map_Floor")
    bb = m.get_bounding_box()
    R["floor_bounds"] = [bb.min.to_tuple(), bb.max.to_tuple()]
    hits = []
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "MaterialInstanceConstant")],
                          package_paths=["/Game"], recursive_paths=True)
    for ad in reg.get_assets(flt):
        n = str(ad.asset_name)
        if any(k in n.lower() for k in ("sidewalk", "pavement", "plaza", "concrete", "asphalt", "ground_")):
            hits.append(str(ad.package_name))
    R["materials"] = sorted(hits)[:80]
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
