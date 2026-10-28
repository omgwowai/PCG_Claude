# pyworld_megaplant_summer.py -- BUILDS AND SAVES summer copies of the City Sample Megaplants trees in
# /Game/PyPCG/World/Trees/: per species a foliage material instance with City Sample's autumn look turned off
# (Seasons off, green tints), and a copy of every tree mesh whose foliage slot uses it. The copies keep pointing at the
# plugin's Nanite assembly parts, whose materials the assembly remaps onto the root mesh's slots
# (NaniteAssemblyDataBuilder.cpp), so the root's slot decides the leaf colour. The plugin's own assets are not touched
# (they are the City demo's reference, Tools/pypcg/baseline.py). The leaves only draw with r.Nanite.Foliage=1
# (Config/DefaultEngine.ini): the Megaplants are Nanite assemblies with voxel foliage.
# Args: {"start": 0, "count": 20}
import json

import unreal

EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
DST = "/Game/PyPCG/World/Trees/"
MP = "/CitySamplePCG/Megaplants/"
TREES = {"European_Beech": ("Tree_European_Beech_01/SM_European_Beech_01_", "ABCD"),
         "Black_Alder": ("Tree_Black_Alder_01/SM_Black_Alder_01_", "ABCD"),
         "Common_Hazel": ("Tree_Common_Hazel_01/SM_Common_Hazel_01_", "ABCD"),
         "European_Aspen": ("Tree_European_Aspen_01/SM_European_Aspen_01_", "ABCD"),
         "Norway_Maple": ("Tree_Norway_Maple_Forest_01/SM_Norway_Maple_Forest_01_", "ABCD")}
# per species: (base colour tint, translucency tint) -- a spread of greens so the canopy is not one colour
GREEN = {"European_Beech": ((0.30, 0.46, 0.20), (0.08, 0.16, 0.03)),
         "Black_Alder": ((0.17, 0.27, 0.10), (0.05, 0.11, 0.03)),
         "Common_Hazel": ((0.23, 0.34, 0.13), (0.07, 0.14, 0.03)),
         "European_Aspen": ((0.27, 0.40, 0.15), (0.09, 0.16, 0.04)),
         "Norway_Maple": ((0.21, 0.37, 0.13), (0.07, 0.15, 0.03))}


def summer_mi(tree):
    src = "%sTree_%s/Materials/MI_%s_Foliage_01" % (MP, tree, tree)
    dst = DST + "MI_%s_Foliage_Summer" % tree
    if not EAL.does_asset_exist(dst):
        EAL.duplicate_asset(src, dst)
    mi = unreal.load_asset(dst)
    # Some species split the leaves' colour off ("Split Base Color Controls", an orange "BaseColor Tint Leaves") and
    # some leave the tint off: one tint for the whole crown, on, for every species.
    for name, on in (("Seasons", False), ("Split Base Color Controls", False), ("Split Translucency Controls", False),
                     ("Tint BaseColor", True), ("Tint Translucency", True)):
        MEL.set_material_instance_static_switch_parameter_value(mi, name, on)
    MEL.set_material_instance_vector_parameter_value(mi, "BaseColor Controls", unreal.LinearColor(1.0, 1.0, 1.0, 0.0))
    base, trans = GREEN[tree]
    MEL.set_material_instance_vector_parameter_value(mi, "BaseColor Tint", unreal.LinearColor(*base, 1.0))
    MEL.set_material_instance_vector_parameter_value(mi, "Translucency Tint", unreal.LinearColor(*trans, 1.0))
    MEL.update_material_instance(mi)
    EAL.save_asset(dst, only_if_is_dirty=False)
    return mi


def main():
    args = globals().get("mcp_args") or {}
    if args.get("materials_only"):
        print(json.dumps({t: summer_mi(t).get_name() for t in TREES}))
        return
    if EAL.does_directory_exist(DST + "European_Beech"):          # an earlier whole-folder copy: refs not fixed up
        EAL.delete_directory(DST + "European_Beech")
    mis = {tree: summer_mi(tree) for tree in TREES}
    meshes = [(tree, MP + "Tree_%s/%s%s" % (tree, stem, v)) for tree, (stem, vs) in TREES.items() for v in vs]
    start, count = int(args.get("start", 0)), int(args.get("count", 20))
    done = []
    for tree, src in meshes[start:start + count]:
        dst = DST + src.rsplit("/", 1)[1]
        if not EAL.does_asset_exist(dst):
            EAL.duplicate_asset(src, dst)
        m = unreal.load_asset(dst)
        mats = list(m.get_editor_property("static_materials"))
        slots = []
        for i, s in enumerate(mats):
            if s.material_interface and "Foliage" in s.material_interface.get_name():
                s.material_interface = mis[tree]
                mats[i] = s                                       # the loop variable is a copy of the struct
                slots.append(i)
        m.set_editor_property("static_materials", mats)
        EAL.save_asset(dst, only_if_is_dirty=False)
        now = [x.material_interface.get_name() for x in m.get_editor_property("static_materials")]
        done.append([dst.rsplit("/", 1)[1], slots, now])
    print(json.dumps({"meshes": done, "next": start + count if start + count < len(meshes) else None}))


main()
