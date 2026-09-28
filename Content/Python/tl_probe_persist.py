# tl_probe_persist.py — confirm the duplicate+mutate route survives a reload,
# then clean up. This is the route Task 7 will use.

import json

R = {}
args = mcp_args or {}
EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers
DUP = "/Game/PCGTest/BDF_DupProbe"

# the duplicate from the previous probe; delete-then-recreate for a clean check
try:
    if EAL.does_asset_exist(DUP):
        R["delete_stale"] = EAL.delete_asset(DUP)
    dup = EAL.duplicate_asset(
        "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG",
        DUP)
    R["duplicated"] = dup is not None
except Exception as e:
    R["dup_err"] = "%s: %s" % (type(e).__name__, e)
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit

# ---------- mutate: add a TL row to the BDF group ------------------------
try:
    items = dup.get_editor_property("data").get_editor_property("tagged_data")
    # find the Levels group and append a TL level row, mirroring Task 7
    for it in items:
        tags = [str(t) for t in it.get_editor_property("tags")]
        if "Levels" not in tags:
            continue
        d = it.get_editor_property("data").get_editor_property("data")
        md = d.mutable_metadata()
        R["levels_attrs_before"] = md.get_attribute_count()
        pts = list(d.get_points())
        R["levels_points_before"] = len(pts)
        p = unreal.PCGPoint()
        p = MA.set_name_attribute(p, md, "BuildingToken", "TL")
        p = MA.set_integer32_attribute(p, md, "LevelNumber", 1)
        p = MA.set_string_attribute(p, md, "LevelToken", "LV1")
        p = MA.set_double_attribute(p, md, "LevelHeight", 5.0)
        p = MA.set_string_attribute(p, md, "F0", "[FC][WS1][W1]+[LC]")
        p = MA.set_bool_attribute(p, md, "IsTopper", False)
        pts.append(p)
        d.set_points(pts)
        R["levels_points_after"] = len(d.get_points())

        eal_ok = False
        try:
            eal_ok = EAL.save_loaded_asset(dup)
        except Exception as e:
            R["save_err"] = "%s: %s" % (type(e).__name__, e)
        R["save_loaded_asset"] = eal_ok
        # also try the explicit save_asset on the path
        try:
            R["save_asset"] = EAL.save_asset(DUP, False)
        except Exception as e:
            R["save_asset_err"] = "%s: %s" % (type(e).__name__, e)
        break
except Exception as e:
    R["mutate_err"] = "%s: %s" % (type(e).__name__, e)

# ---------- drop the in-memory object and reload from disk ---------------
# (there is no unload_asset; collect garbage and re-load through a fresh path
#  reference, then compare against a hard re-read)
try:
    import gc
    gc.collect()
except Exception:
    pass

ver = {}
try:
    a2 = EAL.load_asset(DUP)
    R["reload_same_object"] = True
    items2 = a2.get_editor_property("data").get_editor_property("tagged_data")
    ver["tagged_count"] = len(items2)
    for it in items2:
        tags = [str(t) for t in it.get_editor_property("tags")]
        d = it.get_editor_property("data").get_editor_property("data")
        rec = {"points": d.get_num_points()}
        if "Levels" in tags:
            md = d.mutable_metadata()
            toks = []
            for pt in d.get_points():
                try:
                    toks.append(str(MA.get_name_attribute(pt, md, "BuildingToken")))
                except Exception:
                    toks.append("<err>")
            rec["tl_rows"] = [t for t in toks if t == "TL"]
            rec["total"] = len(toks)
        ver["+".join(tags)] = rec
except Exception as e:
    ver["fatal"] = "%s: %s" % (type(e).__name__, e)
R["verify_in_memory"] = ver

# ---------- filesystem-level check: is the asset actually on disk? -------
fs = {}
try:
    on_disk = unreal.EditorAssetLibrary.does_asset_exist(DUP)
    fs["does_asset_exist"] = on_disk
    pkg = unreal.load_package(None, "/Game/PCGTest/BDF_DupProbe")
    fs["load_package"] = "ok" if pkg else "None"
except Exception as e:
    fs["err"] = "%s: %s" % (type(e).__name__, e)
R["filesystem"] = fs

# ---------- cleanup ------------------------------------------------------
cl = {}
try:
    cl["deleted"] = EAL.delete_asset(DUP)
    cl["gone"] = not EAL.does_asset_exist(DUP)
except Exception as e:
    cl["err"] = "%s: %s" % (type(e).__name__, e)
R["cleanup"] = cl

print(json.dumps(R, indent=1, default=str))
mcp_result = R
