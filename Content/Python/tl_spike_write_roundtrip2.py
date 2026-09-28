# tl_spike_write_roundtrip2.py — same goal as v1, but constructs FPCGTaggedData
# directly instead of via PCGDataFunctionLibrary.make_tagged_data, which is NOT
# bound in this build (AttributeError even though the header declares it).
#
# Also probes which of the three construction routes actually work, so Task 7
# can use the one that is real:
#   route 1: unreal.PCGTaggedData() struct + FPCGDataPtrWrapper
#   route 2: PCGDataFunctionLibrary.add_to_collection (UPARAM(ref) -> returns it)
#   route 3: set the FPCGDataCollection's tagged_data from a built list
#
# Creates and deletes /Game/PCGTest/TL_ProbeRT2. Touches no Epic asset.

import json

R = {}
args = mcp_args or {}
DEST_DIR = "/Game/PCGTest"
DEST_NAME = "TL_ProbeRT2"
TARGET = DEST_DIR + "/" + DEST_NAME

EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers

transient = unreal.find_package("/Engine/Transient")

# ---------- build point data ---------------------------------------------
pd = unreal.new_object(unreal.PCGPointData, transient, "")
md = pd.mutable_metadata()
for nm, kind in (("BuildingToken", "str"), ("LevelNumber", "int"),
                 ("Size", "dbl"), ("IsTopper", "bool"), ("FLengths", "vec")):
    if kind == "str":
        md.create_string_attribute(nm, "", False, True)
    elif kind == "int":
        md.create_integer32_attribute(nm, 0, False, True)
    elif kind == "dbl":
        md.create_double_attribute(nm, 0.0, False, True)
    elif kind == "bool":
        md.create_bool_attribute(nm, False, False, True)
    elif kind == "vec":
        md.create_vector_attribute(nm, unreal.Vector(), False, True)

pts = []
for token, lv, size, topper in (("TL", 1, 325.0, False), ("TL", 2, 475.0, False),
                                ("CHA", 3, 325.0, True)):
    p = unreal.PCGPoint()
    p = MA.set_string_attribute(p, md, "BuildingToken", token)
    p = MA.set_integer32_attribute(p, md, "LevelNumber", lv)
    p = MA.set_double_attribute(p, md, "Size", size)
    p = MA.set_bool_attribute(p, md, "IsTopper", topper)
    p = MA.set_vector_attribute(p, md, "FLengths", unreal.Vector(size, size, size))
    pts.append(p)
pd.set_points(pts)
R["points"] = len(pd.get_points())

# ---------- route 1: construct the tagged-data struct by hand -------------
route1 = {}
try:
    wrap = unreal.PCGDataPtrWrapper()
    wrap.set_editor_property("data", pd)
    td = unreal.PCGTaggedData()
    td.set_editor_property("data", wrap)
    td.set_editor_property("tags", {"BDF", "BDFData"})
    td.set_editor_property("pin", unreal.Name("In"))
    route1["built"] = True
    route1["pin"] = str(td.get_editor_property("pin"))
    route1["tags"] = [str(t) for t in td.get_editor_property("tags")]
    back = td.get_editor_property("data").get_editor_property("data")
    route1["data_roundtrip"] = back.get_class().get_name() if back else None
    route1["points_roundtrip"] = back.get_num_points() if back else 0
except Exception as e:
    route1["err"] = "%s: %s" % (type(e).__name__, e)
R["route1_struct"] = route1

# ---------- route 2: add_to_collection -----------------------------------
route2 = {}
try:
    coll2 = unreal.PCGDataCollection()
    out = unreal.PCGDataFunctionLibrary.add_to_collection(
        coll2, pd, unreal.Name("In"), ["BDF", "BDFData"])
    items2 = out.get_editor_property("tagged_data") if out else \
        coll2.get_editor_property("tagged_data")
    route2["count"] = len(items2)
    if items2:
        route2["pin"] = str(items2[0].get_editor_property("pin"))
        route2["tags"] = [str(t) for t in items2[0].get_editor_property("tags")]
except Exception as e:
    route2["err"] = "%s: %s" % (type(e).__name__, e)
R["route2_add_to_collection"] = route2

# ---------- pick a route and write ---------------------------------------
use_struct = bool(route1.get("built"))
R["chosen_route"] = "struct" if use_struct else ("add_to_collection" if route2.get("count") else "none")

if R["chosen_route"] != "none":
    try:
        coll = unreal.PCGDataCollection()
        if use_struct:
            coll.set_editor_property("tagged_data", [td])
        else:
            coll = unreal.PCGDataFunctionLibrary.add_to_collection(
                coll, pd, unreal.Name("In"), ["BDF", "BDFData"])
        R["coll_count"] = len(coll.get_editor_property("tagged_data"))

        exporter = unreal.new_object(unreal.PCGDataCollectionExporter, transient, "")
        exporter.set_editor_property("data", coll)
        exporter.set_editor_property("asset_description", "TL write probe 2")
        params = unreal.PCGAssetExporterParameters()
        params.set_editor_property("open_save_dialog", False)
        params.set_editor_property("asset_name", DEST_NAME)
        params.set_editor_property("asset_path", DEST_DIR)
        params.set_editor_property("save_on_export_ended", True)
        if EAL.does_asset_exist(TARGET):
            EAL.delete_asset(TARGET)
        got = unreal.PCGAssetExporterUtils.create_asset(exporter, params)
        R["create_asset"] = "object" if got else "None"
    except Exception as e:
        R["write_err"] = "%s: %s" % (type(e).__name__, e)

# ---------- verify -------------------------------------------------------
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
            ver["outer"] = d.get_outer().get_name()
            ver["num_points"] = d.get_num_points()
            m2 = d.mutable_metadata()
            ver["attr_count"] = m2.get_attribute_count()
            ver["rows"] = [{
                "token": MA.get_string_attribute(pt, m2, "BuildingToken"),
                "level": MA.get_integer32_attribute(pt, m2, "LevelNumber"),
                "size": MA.get_double_attribute(pt, m2, "Size"),
                "topper": MA.get_bool_attribute(pt, m2, "IsTopper"),
            } for pt in d.get_points()]
except Exception as e:
    ver["fatal"] = "%s: %s" % (type(e).__name__, e)
R["verify"] = ver

# ---------- cleanup ------------------------------------------------------
cl = {}
try:
    cl["deleted"] = EAL.delete_asset(TARGET)
    cl["gone"] = not EAL.does_asset_exist(TARGET)
except Exception as e:
    cl["err"] = "%s: %s" % (type(e).__name__, e)
R["cleanup"] = cl

print(json.dumps(R, indent=1, default=str))
mcp_result = R
