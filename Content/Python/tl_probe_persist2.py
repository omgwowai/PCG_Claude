# tl_probe_persist2.py — prove the write persists ON DISK, then clean up.
#
# The previous run showed the BDF group at 28 points (was 27) in a fresh script
# call, but that could be the still-loaded in-memory object. This:
#   1. removes the leftover probe asset
#   2. duplicates fresh, mutates, saves
#   3. reports the disk path + size so bash can check the mtime
#   4. cleans up again

import json
import os

R = {}
args = mcp_args or {}
EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers
SRC = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG"
DUP = "/Game/PCGTest/BDF_PersistProbe"

# ---------- 1. clear any leftover ----------------------------------------
R["cleanup_before"] = {}
for p in ("/Game/PCGTest/BDF_DupProbe", DUP):
    try:
        R["cleanup_before"][p] = {
            "existed": EAL.does_asset_exist(p),
            "deleted": EAL.delete_asset(p),
        }
    except Exception as e:
        R["cleanup_before"][p] = "%s: %s" % (type(e).__name__, e)

# ---------- 2. duplicate + mutate + save ---------------------------------
try:
    dup = EAL.duplicate_asset(SRC, DUP)
    R["duplicated"] = dup is not None
    if dup:
        items = dup.get_editor_property("data").get_editor_property("tagged_data")
        for it in items:
            tags = [str(t) for t in it.get_editor_property("tags")]
            if "Levels" not in tags:
                continue
            d = it.get_editor_property("data").get_editor_property("data")
            md = d.mutable_metadata()
            pts = list(d.get_points())
            R["before"] = len(pts)
            p = unreal.PCGPoint()
            p = MA.set_name_attribute(p, md, "BuildingToken", "TL")
            p = MA.set_integer32_attribute(p, md, "LevelNumber", 1)
            p = MA.set_string_attribute(p, md, "LevelToken", "LV1")
            pts.append(p)
            d.set_points(pts)
            R["after"] = len(d.get_points())
            break
        R["save_loaded"] = EAL.save_loaded_asset(dup)
except Exception as e:
    R["err"] = "%s: %s" % (type(e).__name__, e)

# ---------- 3. locate the package on disk --------------------------------
# /Game/... maps to <project>/Content/...
disk = os.path.join("E:/PCG_Claude/Content", "PCGTest", "BDF_PersistProbe.uasset")
try:
    R["disk_path"] = disk
    R["disk_exists"] = os.path.isfile(disk)
    if os.path.isfile(disk):
        st = os.stat(disk)
        R["disk_size"] = st.st_size
        R["disk_mtime"] = st.st_mtime
        R["readonly"] = not os.access(disk, os.W_OK)
except Exception as e:
    R["disk_err"] = "%s: %s" % (type(e).__name__, e)

# also report the source's mtime, to prove Epic's file was NOT touched
src_disk = os.path.join(
    "E:/PCG_Claude/Plugins/CitySamplePCG/Content/PCG/Primitives/Buildings/Subgraphs",
    "CitySampleBuildingBDF_Asset_PCG.uasset")
try:
    if os.path.isfile(src_disk):
        R["source_mtime"] = os.stat(src_disk).st_mtime
        R["source_size"] = os.stat(src_disk).st_size
except Exception as e:
    R["source_err"] = type(e).__name__

print(json.dumps(R, indent=1, default=str))
mcp_result = R
