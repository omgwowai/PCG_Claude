# tl_check_minwall2.py — settle the float/double question with BOTH getters.
#
# My earlier probe used get_double_attribute on these fields and read 0.0 for
# every style. The implementer reports non-zero values (CHA=1000/3100/10000).
# Task 1's own type list says these attributes are FLOAT, not Double -- and a
# mismatched getter returns a silent sentinel here rather than raising. So read
# each field with BOTH getters and compare. Whichever disagrees with 0.0 is real.

import json

R = {}
args = mcp_args or {}
EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers

NEW = "/Game/PCG/DataAssets/BDF/BDF_WithTL"
SRC = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG"

def get_set(asset, tag):
    items = asset.get_editor_property("data").get_editor_property("tagged_data")
    for it in items:
        if tag in [str(t) for t in it.get_editor_property("tags")]:
            d = it.get_editor_property("data").get_editor_property("data")
            return d, d.mutable_metadata()
    return None, None

def attrs_of(data):
    """The real attribute names + declared types, via get_attributes()."""
    try:
        raw = data.mutable_metadata().get_attributes()
        return [str(x) for x in raw]
    except Exception as e:
        return ["<%s>" % type(e).__name__]

a = EAL.load_asset(NEW)
R["declared_types_BDF_group"] = attrs_of(
    get_set(a, "BDF")[0]) if get_set(a, "BDF")[0] else None

# ---------- BDF group: both getters side by side -------------------------
d, md = get_set(a, "BDF")
if d is not None:
    rows = []
    for pt in d.get_points():
        tok = MA.get_string_attribute(pt, md, "BuildingToken")
        if tok not in ("TL", "CHA", "CHB", "SFJ"):
            continue
        rec = {"tok": tok}
        for f in ("MinWallWidth", "MinBldgHeight", "MaxBldgHeight"):
            try:
                rec[f + "_as_float"] = MA.get_float_attribute(pt, md, f)
            except Exception as e:
                rec[f + "_as_float"] = "<%s>" % type(e).__name__
            try:
                rec[f + "_as_double"] = MA.get_double_attribute(pt, md, f)
            except Exception as e:
                rec[f + "_as_double"] = "<%s>" % type(e).__name__
        rows.append(rec)
    R["BDF_both_getters"] = rows
    R["BDF_all_tokens"] = sorted(
        {MA.get_string_attribute(pt, md, "BuildingToken") for pt in d.get_points()})

# ---------- Levels group: LevelHeight both ways -------------------------
d2, md2 = get_set(a, "Levels")
if d2 is not None:
    lv = []
    for pt in d2.get_points():
        tok = MA.get_name_attribute(pt, md2, "BuildingToken")
        if tok != "TL":
            continue
        rec = {"LevelToken": MA.get_string_attribute(pt, md2, "LevelToken")}
        for kind, fn in (("float", "get_float_attribute"), ("double", "get_double_attribute")):
            try:
                rec["LevelHeight_" + kind] = getattr(MA, fn)(pt, md2, "LevelHeight")
            except Exception as e:
                rec["LevelHeight_" + kind] = "<%s>" % type(e).__name__
        lv.append(rec)
    R["TL_levels_both_getters"] = sorted(lv, key=lambda r: r["LevelToken"])
    # and CHA's first level for comparison
    for pt in d2.get_points():
        if MA.get_name_attribute(pt, md2, "BuildingToken") == "CHA" \
                and MA.get_string_attribute(pt, md2, "LevelToken") == "LV1":
            R["CHA_LV1_LevelHeight_float"] = MA.get_float_attribute(pt, md2, "LevelHeight")
            R["CHA_LV1_LevelHeight_double"] = MA.get_double_attribute(pt, md2, "LevelHeight")
            break

print(json.dumps(json.loads(json.dumps(R, default=str)), indent=1))
mcp_result = json.loads(json.dumps(R, default=str))
