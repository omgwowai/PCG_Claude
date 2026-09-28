# tl_spike_write_roundtrip.py — prove the BDF-authoring write path end to end.
#
# Builds a small PCGPointData FROM SCRATCH (the part Task 7 depends on), writes
# it to a NEW asset through PCGAssetExporterUtils.create_asset, reads it back,
# and verifies the string attributes survived plus how the data got re-outered.
#
# Does NOT touch Epic's assets. Creates and deletes /Game/PCGTest/TL_ProbeRT.

import json

R = {}
args = mcp_args or {}
DEST_DIR = "/Game/PCGTest"
DEST_NAME = "TL_ProbeRT"
TARGET = DEST_DIR + "/" + DEST_NAME

EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers

# ---------- 1. fresh point data, outered to transient --------------------
# new_object REQUIRES a non-null outer; the transient package is what
# DuplicateAndReOuterData looks for when it re-lexes data into the asset.
try:
    transient = unreal.find_package("/Engine/Transient")
    R["transient_outer"] = str(transient)
    pd = unreal.new_object(unreal.PCGPointData, transient, "")
    R["point_data_created"] = pd is not None
except Exception as e:
    R["fatal"] = "new_object: %s: %s" % (type(e).__name__, e)
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit

# ---------- 2. declare attributes ----------------------------------------
md = pd.mutable_metadata()
created = {}
for nm, kind, default in (("BuildingToken", "str", ""),
                          ("LevelNumber", "int", 0),
                          ("Size", "dbl", 0.0),
                          ("IsTopper", "bool", False),
                          ("FLengths", "vec", unreal.Vector())):
    try:
        if kind == "str":
            md.create_string_attribute(nm, default, False, True)
        elif kind == "int":
            md.create_integer32_attribute(nm, default, False, True)
        elif kind == "dbl":
            md.create_double_attribute(nm, default, False, True)
        elif kind == "bool":
            md.create_bool_attribute(nm, default, False, True)
        elif kind == "vec":
            md.create_vector_attribute(nm, default, False, True)
        created[nm] = "ok"
    except Exception as e:
        created[nm] = "%s: %s" % (type(e).__name__, e)
R["attributes_created"] = created
R["attr_count"] = md.get_attribute_count()

# ---------- 3. points ----------------------------------------------------
# set_string_attribute returns the mutated point (UPARAM(ref) comes back as a
# return value in Python), so the result MUST be captured or it is lost.
rows = [("TL", 1, 325.0, False), ("TL", 2, 475.0, False), ("CHA", 3, 325.0, True)]
pts = []
for token, lv, size, topper in rows:
    p = unreal.PCGPoint()
    p = MA.set_string_attribute(p, md, "BuildingToken", token)
    p = MA.set_integer32_attribute(p, md, "LevelNumber", lv)
    p = MA.set_double_attribute(p, md, "Size", size)
    p = MA.set_bool_attribute(p, md, "IsTopper", topper)
    p = MA.set_vector_attribute(p, md, "FLengths", unreal.Vector(size, size, size))
    pts.append(p)
pd.set_points(pts)
R["points_set"] = len(pd.get_points())

# ---------- 4. collection + exporter -------------------------------------
try:
    td = unreal.PCGDataFunctionLibrary.make_tagged_data(pd, {"BDF", "BDFData"}, "In")
    R["tagged_made"] = td is not None
    R["tagged_pin"] = str(td.get_editor_property("pin"))
    R["tagged_tags"] = [str(t) for t in td.get_editor_property("tags")]
    coll = unreal.PCGDataCollection()
    coll.set_editor_property("tagged_data", [td])
    R["coll_count"] = len(coll.get_editor_property("tagged_data"))

    exporter = unreal.new_object(unreal.PCGDataCollectionExporter, transient, "")
    exporter.set_editor_property("data", coll)
    exporter.set_editor_property("asset_description", "TL write probe")

    params = unreal.PCGAssetExporterParameters()
    params.set_editor_property("open_save_dialog", False)   # default True = modal
    params.set_editor_property("asset_name", DEST_NAME)
    params.set_editor_property("asset_path", DEST_DIR)
    params.set_editor_property("save_on_export_ended", True)

    if EAL.does_asset_exist(TARGET):
        EAL.delete_asset(TARGET)
    got = unreal.PCGAssetExporterUtils.create_asset(exporter, params)
    R["create_asset"] = "object" if got else "None"
except Exception as e:
    R["write_err"] = "%s: %s" % (type(e).__name__, e)

# ---------- 5. read back -------------------------------------------------
ver = {}
try:
    ver["exists"] = EAL.does_asset_exist(TARGET)
    a2 = EAL.load_asset(TARGET)
    ver["class"] = a2.get_class().get_name() if a2 else None
    if a2:
        items = a2.get_editor_property("data").get_editor_property("tagged_data")
        ver["tagged_count"] = len(items)
        for it in items:
            d = it.get_editor_property("data").get_editor_property("data")
            if d is None:
                continue
            ver["data_class"] = d.get_class().get_name()
            ver["outer"] = d.get_outer().get_name()      # did it get re-outered?
            ver["num_points"] = d.get_num_points()
            m2 = d.mutable_metadata()
            ver["attr_count"] = m2.get_attribute_count()
            rows_out = []
            for pt in d.get_points():
                rows_out.append({
                    "token": MA.get_string_attribute(pt, m2, "BuildingToken"),
                    "level": MA.get_integer32_attribute(pt, m2, "LevelNumber"),
                    "size": MA.get_double_attribute(pt, m2, "Size"),
                    "topper": MA.get_bool_attribute(pt, m2, "IsTopper"),
                })
            ver["rows"] = rows_out
except Exception as e:
    ver["fatal"] = "%s: %s" % (type(e).__name__, e)
R["verify"] = ver

# ---------- 6. cleanup ---------------------------------------------------
cl = {}
try:
    cl["deleted"] = EAL.delete_asset(TARGET)
    cl["gone"] = not EAL.does_asset_exist(TARGET)
except Exception as e:
    cl["err"] = "%s: %s" % (type(e).__name__, e)
R["cleanup"] = cl

print(json.dumps(R, indent=1, default=str))
mcp_result = R
