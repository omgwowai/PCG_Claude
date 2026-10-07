# tl_names_with_tl.py -- give the style-name list a TL entry and point
# LoadCitySampleData at it.
#
# Assign_CitySampleBuildings_CoreProcess validates every requested style code
# against CitySampleBuildingBDF_NamesOnly_PCG: it JOINs the list's Name values
# into one string (AttributeReduce_1) and keeps a requested code only if it is a
# substring of that string (AttributeStringOp_0 -> AttributeFilter_1). The list
# holds the 27 original codes, so TL is dropped before any lot is assigned,
# whatever BuildingsStyles says, and nothing logs it.
#
# Epic's NamesOnly asset is not modified: it is duplicated into /Game (same
# route as BDF_WithTL) and the copy gets the TL entry. LoadCitySampleData's
# PCGLoadDataAsset_1 is repointed at the copy, with a file backup under Saved/.
#
# Args: {"apply": true} to write; default is a dry run.

import json
import os
import shutil

SRC = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_NamesOnly_PCG"
DEST = "/Game/PCG/DataAssets/BDF/BDF_NamesOnly_WithTL"
LOAD = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/LoadCitySampleData"
LOAD_DISK = ("E:/PCG_Claude/Plugins/CitySamplePCG/Content/PCG/Primitives/Buildings/"
             "Subgraphs/LoadCitySampleData.uasset")
BACKUP = "E:/PCG_Claude/Saved/TL_backups/LoadCitySampleData.uasset"
CODE = "TL"


def names_of(asset):
    MA = unreal.PCGMetadataAccessorHelpers
    d = asset.get_editor_property("data").get_editor_property("tagged_data")[0] \
        .get_editor_property("data").get_editor_property("data")
    md = d.const_metadata()
    out = []
    for k in range(md.get_item_count_for_child()):
        p = unreal.PCGPoint()
        p.import_text("(MetadataEntry=%d)" % k)
        out.append(str(MA.get_name_attribute(p, md, "Name")))
    return out


def names_loader(load_graph):
    for n in load_graph.get_editor_property("nodes"):
        s = n.get_settings()
        if s is None or s.get_class().get_name() != "PCGLoadDataAssetSettings":
            continue
        a = s.get_editor_property("asset")
        path = a.get_path_name() if a else ""
        if "NamesOnly" in path:
            return s, path
    return None, None


def main(apply):
    R = {"apply": apply, "errors": []}
    EAL = unreal.EditorAssetLibrary
    MA = unreal.PCGMetadataAccessorHelpers

    src = EAL.load_asset(SRC)
    R["src_names"] = names_of(src)
    R["src_has_TL"] = CODE in R["src_names"]

    lg = EAL.load_asset(LOAD)
    loader, loader_path = names_loader(lg)
    R["loader_points_at"] = loader_path
    if loader is None:
        R["errors"].append("no NamesOnly loader node in LoadCitySampleData")
        return R

    if EAL.does_asset_exist(DEST):
        dest = EAL.load_asset(DEST)
        R["dest_existed"] = True
    else:
        dest = None
        R["dest_existed"] = False

    if not apply:
        R["note"] = "dry run"
        if dest is not None:
            R["dest_names"] = names_of(dest)
        return R

    if dest is None:
        dest = EAL.duplicate_asset(SRC, DEST)
        if dest is None:
            R["errors"].append("duplicate_asset returned None")
            return R

    if CODE not in names_of(dest):
        d = dest.get_editor_property("data").get_editor_property("tagged_data")[0] \
            .get_editor_property("data").get_editor_property("data")
        md = d.mutable_metadata()
        pt = MA.set_name_attribute(unreal.PCGPoint(), md, "Name", CODE)
        R["new_entry_key"] = pt.get_editor_property("metadata_entry")
        dest.modify()
    R["dest_names"] = names_of(dest)
    R["dest_saved"] = EAL.save_asset(DEST, only_if_is_dirty=False)

    if loader_path and not loader_path.startswith(DEST):
        if not os.path.exists(BACKUP):
            os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
            shutil.copy2(LOAD_DISK, BACKUP)
        R["backup"] = BACKUP
        lg.modify()
        loader.modify()
        loader.set_editor_property("asset", dest)
        R["load_saved"] = EAL.save_asset(LOAD, only_if_is_dirty=False)
    _, R["loader_points_at_after"] = names_loader(lg)

    if R["dest_names"][:27] != R["src_names"]:
        R["errors"].append("the copy's first 27 names differ from Epic's list")
    if R["dest_names"].count(CODE) != 1:
        R["errors"].append("the copy does not hold exactly one TL entry")
    if not str(R["loader_points_at_after"]).startswith(DEST):
        R["errors"].append("LoadCitySampleData does not point at the copy")
    R["src_names_after"] = names_of(EAL.load_asset(SRC))
    R["src_untouched"] = R["src_names_after"] == R["src_names"]
    return R


R = main(bool((mcp_args or {}).get("apply")))
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
