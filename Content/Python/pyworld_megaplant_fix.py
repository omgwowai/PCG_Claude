# pyworld_megaplant_fix.py -- DUPLICATES the City Sample Megaplants tree meshes into /Game/PyPCG/World/Trees/ and
# rebuilds their Nanite data with shape preservation "Preserve Area" instead of "Voxelize", then saves them.
# Why: the Megaplants' leaves are Nanite voxel foliage; this project runs without r.Nanite.Foliage (as City Sample does,
# and the engine's foliage voxels change every shader key), so the leaves never draw and the trees stand bare
# (catalog shots 2026-10-23). Preserve Area is what the Electric Dreams hornbeams use, and they render.
# The plugin's own assets are not touched. Args: {"names": [...]} (default: every mesh, a few per call:
# {"start": 0, "count": 4}).
import json

import unreal

EAL = unreal.EditorAssetLibrary
DST = "/Game/PyPCG/World/Trees/"
SRC = ["/CitySamplePCG/Megaplants/Tree_%s/Tree_%s_01/SM_%s_01_%s" % (t, t, t, v)
       for t in ("European_Beech", "Black_Alder", "Common_Hazel", "European_Aspen") for v in "ABCD"] + \
      ["/CitySamplePCG/Megaplants/Tree_Norway_Maple/Tree_Norway_Maple_Forest_01/SM_Norway_Maple_Forest_01_" + v
       for v in "ABCD"]


def main():
    args = globals().get("mcp_args") or {}
    start, count = int(args.get("start", 0)), int(args.get("count", 4))
    out = {}
    for src in SRC[start:start + count]:
        dst = DST + src.rsplit("/", 1)[1]
        if not EAL.does_asset_exist(dst):
            EAL.duplicate_asset(src, dst)
        m = unreal.load_asset(dst)
        ns = m.get_editor_property("nanite_settings")
        before = str(ns.get_editor_property("shape_preservation"))
        ns.set_editor_property("shape_preservation", unreal.NaniteShapePreservation.PRESERVE_AREA)
        m.set_editor_property("nanite_settings", ns)          # notified: rebuilds the Nanite data
        EAL.save_asset(dst, only_if_is_dirty=False)
        out[dst] = before
    print(json.dumps({"done": out, "next": start + count if start + count < len(SRC) else None, "total": len(SRC)}))


main()
