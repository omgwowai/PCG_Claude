# tl_probe_kit_depths.py -- READ-ONLY. Local bounding box of every TL kit mesh
# (x = depth: exterior +X, facade plane at 0; y = run; z = height), so the corner
# design knows how far each piece projects in front of and behind the facade.
import json


def main():
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    out = {}
    for ad in reg.get_assets_by_path("/Game/Building/TL/A", recursive=True):
        if str(ad.asset_class_path.asset_name) != "StaticMesh":
            continue
        m = ad.get_asset()
        bb = m.get_bounding_box()
        out[str(ad.asset_name)] = {"x": [round(bb.min.x, 1), round(bb.max.x, 1)],
                                   "y": [round(bb.min.y, 1), round(bb.max.y, 1)],
                                   "z": [round(bb.min.z, 1), round(bb.max.z, 1)]}
    return dict(sorted(out.items()))


mcp_result = json.loads(json.dumps(main(), default=str))
