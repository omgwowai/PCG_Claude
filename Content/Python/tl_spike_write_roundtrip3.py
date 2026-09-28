# tl_spike_write_roundtrip3.py — the third and last construction route.
#
# Findings so far:
#   route 1 (build FPCGTaggedData by hand)  -> FPCGDataPtrWrapper.data is READ-ONLY
#   route 2 (add_to_collection)             -> WORKS, pin + tags survive
#   route 3 (PCGDataCollectionExporter)     -> exporter.data is READ-ONLY
#
# So the exporter is out. This tests the AssetTools route from the engine probe:
#   asset_tools.create_asset(name, path, unreal.PCGDataAsset, None)
#   then asset.set_editor_property("data", coll)
#
# UPCGDataAsset.data is UPROPERTY(BlueprintReadWrite) FPCGDataCollection, so it
# should be settable. Creates and deletes /Game/PCGTest/TL_ProbeRT3.

import json

R = {}
args = mcp_args or {}
DEST_DIR = "/Game/PCGTest"
DEST_NAME = "TL_ProbeRT3"
TARGET = DEST_DIR + "/" + DEST_NAME

EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers
AT = unreal.AssetToolsHelpers.get_asset_tools()
transient = unreal.find_package("/Engine/Transient")

# ---------- four TL-shaped point sets, like the real BDF asset ------------
GROUPS = [
    ({"BDF", "BDFData"},
     [("BuildingToken", "str"), ("VerticalGrammar", "str"), ("MinWallWidth", "dbl")],
     [{"BuildingToken": "TL", "VerticalGrammar": "[LV0][LV1][LV2][LV3]", "MinWallWidth": 12.0}]),
    ({"Levels", "BDFData"},
     [("BuildingToken", "str"), ("LevelNumber", "int"), ("LevelToken", "str"),
      ("LevelHeight", "dbl"), ("F0", "str"), ("IsTopper", "bool")],
     [{"BuildingToken": "TL", "LevelNumber": 0, "LevelToken": "LV0",
       "LevelHeight": 5.0, "F0": "[FC][FS2]+[LC]", "IsTopper": False},
      {"BuildingToken": "TL", "LevelNumber": 1, "LevelToken": "LV1",
       "LevelHeight": 5.0, "F0": "[FC][WS1][W1]+[LC]", "IsTopper": False}]),
    ({"Modules", "BDFData"},
     [("BuildingToken", "str"), ("Level", "int"), ("Symbol", "str"),
      ("Size", "dbl"), ("bScalable", "bool")],
     [{"BuildingToken": "TL", "Level": 1, "Symbol": "W1", "Size": 325.0, "bScalable": False},
      {"BuildingToken": "TL", "Level": 1, "Symbol": "WS1", "Size": 325.0, "bScalable": True}]),
]


def make_pd(decls, rows):
    pd = unreal.new_object(unreal.PCGPointData, transient, "")
    md = pd.mutable_metadata()
    for nm, kind in decls:
        if kind == "str":
            md.create_string_attribute(nm, "", False, True)
        elif kind == "int":
            md.create_integer32_attribute(nm, 0, False, True)
        elif kind == "dbl":
            md.create_double_attribute(nm, 0.0, False, True)
        elif kind == "bool":
            md.create_bool_attribute(nm, False, False, True)
    pts = []
    for row in rows:
        p = unreal.PCGPoint()
        for nm, kind in decls:
            v = row.get(nm)
            if v is None:
                continue
            if kind == "str":
                p = MA.set_string_attribute(p, md, nm, str(v))
            elif kind == "int":
                p = MA.set_integer32_attribute(p, md, nm, int(v))
            elif kind == "dbl":
                p = MA.set_double_attribute(p, md, nm, float(v))
            elif kind == "bool":
                p = MA.set_bool_attribute(p, md, nm, bool(v))
        pts.append(p)
    pd.set_points(pts)
    return pd


coll = unreal.PCGDataCollection()
built = []
for tags, decls, rows in GROUPS:
    pd = make_pd(decls, rows)
    coll = unreal.PCGDataFunctionLibrary.add_to_collection(
        coll, pd, unreal.Name("In"), sorted(tags))
    built.append({"tags": sorted(tags), "points": len(rows)})
R["built_groups"] = built
R["coll_count"] = len(coll.get_editor_property("tagged_data"))

# ---------- create the asset, then set data on it -------------------------
try:
    if EAL.does_asset_exist(TARGET):
        EAL.delete_asset(TARGET)
    asset = AT.create_asset(DEST_NAME, DEST_DIR, unreal.PCGDataAsset, None)
    R["create_asset"] = "object" if asset else "None"
    if asset:
        asset.set_editor_property("data", coll)
        R["data_set"] = True
        EAL.save_loaded_asset(asset)
        R["saved"] = True
except Exception as e:
    R["write_err"] = "%s: %s" % (type(e).__name__, e)

# ---------- verify, including which factory/pins got stamped --------------
ver = {}
try:
    ver["exists"] = EAL.does_asset_exist(TARGET)
    a2 = EAL.load_asset(TARGET)
    ver["class"] = a2.get_class().get_name() if a2 else None
    if a2:
        items = a2.get_editor_property("data").get_editor_property("tagged_data")
        ver["tagged_count"] = len(items)
        groups = []
        for it in items:
            d = it.get_editor_property("data").get_editor_property("data")
            rec = {"pin": str(it.get_editor_property("pin")),
                   "tags": [str(t) for t in it.get_editor_property("tags")]}
            if d:
                rec["class"] = d.get_class().get_name()
                rec["outer"] = d.get_outer().get_name()
                m2 = d.mutable_metadata()
                rec["attr_count"] = m2.get_attribute_count()
                rec["no_points"] = d.get_num_points()
                # read the string attr back
                toks = []
                for pt in d.get_points():
                    for nm in ("BuildingToken",):
                        try:
                            toks.append(MA.get_string_attribute(pt, m2, nm))
                        except Exception:
                            pass
                rec["tokens"] = toks
            groups.append(rec)
        ver["groups"] = groups
except Exception as e:
    ver["fatal"] = "%s: %s" % (type(e).__name__, e)
R["verify"] = ver

# ---------- cleanup -------------------------------------------------------
cl = {}
try:
    cl["deleted"] = EAL.delete_asset(TARGET)
    cl["gone"] = not EAL.does_asset_exist(TARGET)
except Exception as e:
    cl["err"] = "%s: %s" % (type(e).__name__, e)
R["cleanup"] = cl

print(json.dumps(R, indent=1, default=str))
mcp_result = R
