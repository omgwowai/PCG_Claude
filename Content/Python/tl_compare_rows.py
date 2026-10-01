# tl_compare_rows.py — compare TL's BDF rows against a working sibling's,
# attribute by attribute, to find any structural difference.
#
# Task 9b falsified the height-band hypothesis: TL still generates 0 of 475,723
# instances after MaxBldgHeight was corrected. So the difference is elsewhere.
# The cheapest next question: does TL's row data differ structurally from a
# style that DOES generate? Read every attribute of a TL row and a CHA row and
# compare them field by field, for all three groups.
#
# Type-matched getters only -- a mismatched getter returns a silent sentinel.

import json

R = {}
args = mcp_args or {}
EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers

NEW = "/Game/PCG/DataAssets/BDF/BDF_WithTL"

# attribute -> declaring kind, from the measured schema
BDF_T = {"BuildingToken": "s", "VerticalGrammar": "s",
         "VerticalGrammarStaggered": "s", "MinWallWidth": "f",
         "MinBldgHeight": "f", "MaxBldgHeight": "f", "RoofData": "v4"}
MOD_T = {"BuildingToken": "s", "Level": "i", "Symbol": "s", "Size": "d",
         "Mod_Name": "s", "Mesh": "o", "HasProps": "b", "HasWindow": "b",
         "bScalable": "b", "PivotOffset": "v", "MeshForwardAxis": "d",
         "PropOffset": "v", "PtID": "i"}
LVL_T = {"BuildingToken": "n", "LevelNumber": "i", "LevelToken": "s",
         "LevelHeight": "f", "Size": "f", "F": "s", "F0": "s", "F1": "s",
         "F2": "s", "FLengths": "v", "IsTopper": "b"}

GET = {"s": "get_string_attribute", "n": "get_name_attribute",
       "i": "get_integer32_attribute", "d": "get_double_attribute",
       "f": "get_float_attribute", "b": "get_bool_attribute",
       "v": "get_vector_attribute", "v4": "get_vector4_attribute",
       "o": "get_soft_object_path_attribute"}

def val(pt, md, name, kind):
    try:
        v = getattr(MA, GET[kind])(pt, md, name)
    except Exception as e:
        return "<%s>" % type(e).__name__
    if hasattr(v, "x") and hasattr(v, "z"):
        return [round(v.x, 3), round(v.y, 3), round(v.z, 3)]
    if hasattr(v, "w") and hasattr(v, "x"):
        return [round(v.x, 3), round(v.y, 3), round(v.z, 3), round(v.w, 3)]
    if hasattr(v, "to_string"):
        return v.to_string().split("/")[-1]
    return v

def get_set(asset, tag):
    items = asset.get_editor_property("data").get_editor_property("tagged_data")
    for it in items:
        if tag in [str(t) for t in it.get_editor_property("tags")]:
            d = it.get_editor_property("data").get_editor_property("data")
            return d, d.mutable_metadata()
    return None, None

a = EAL.load_asset(NEW)

def token_of(pt, md, kinds):
    for k in kinds:
        try:
            v = str(getattr(MA, GET[k])(pt, md, "BuildingToken"))
            if v:
                return v
        except Exception:
            continue
    return ""

# ---------- BDF group: TL vs CHA, every field ---------------------------
d, md = get_set(a, "BDF")
if d is not None:
    out = {}
    for pt in d.get_points():
        tok = token_of(pt, md, ["s", "n"])
        if tok in ("TL", "CHA", "CHF"):
            out[tok] = {f: val(pt, md, f, k) for f, k in BDF_T.items()}
    R["bdf_TL_vs_CHA"] = out

# ---------- Levels group: TL LV1 vs CHA LV1 -----------------------------
d2, md2 = get_set(a, "Levels")
if d2 is not None:
    out2 = {}
    for pt in d2.get_points():
        tok = token_of(pt, md2, ["n", "s"])
        lvt = val(pt, md2, "LevelToken", "s")
        key = "%s_%s" % (tok, lvt)
        if key in ("TL_LV1", "CHA_LV1", "CHF_LV1"):
            out2[key] = {f: val(pt, md2, f, k) for f, k in LVL_T.items()}
    R["levels_TL_vs_CHA"] = out2

# ---------- Modules group: TL L1 W1 vs CHA L1 W1 ------------------------
d3, md3 = get_set(a, "Modules")
if d3 is not None:
    out3 = {}
    for pt in d3.get_points():
        tok = val(pt, md3, "BuildingToken", "s")
        lv = val(pt, md3, "Level", "i")
        sym = val(pt, md3, "Symbol", "s")
        key = "%s_L%s_%s" % (tok, lv, sym)
        if key in ("TL_L1_W1", "CHA_L1_W1", "CHF_L1_W1", "TL_L2_W1"):
            out3[key] = {f: val(pt, md3, f, k) for f, k in MOD_T.items()}
    R["modules_TL_vs_CHA"] = out3
    # also: how many module rows reference a mesh that actually exists?
    # NOTE: does_asset_exist rejects a SoftObjectPath -- it needs a plain string
    # ("NativizeProperty: Cannot nativize 'SoftObjectPath' as 'AssetPath'").
    missing = []
    for pt in d3.get_points():
        if val(pt, md3, "BuildingToken", "s") != "TL":
            continue
        mp = val(pt, md3, "Mesh", "o")
        if not mp:
            missing.append({"sym": val(pt, md3, "Symbol", "s"), "path": mp,
                            "why": "empty"})
            continue
        mp_str = str(mp)
        if not EAL.does_asset_exist(mp_str):
            missing.append({"sym": val(pt, md3, "Symbol", "s"),
                            "path": mp_str, "why": "not found"})
    R["TL_module_meshes_missing"] = missing
    R["TL_module_mesh_count_checked"] = len(
        [pt for pt in d3.get_points()
         if val(pt, md3, "BuildingToken", "s") == "TL"])

print(json.dumps(json.loads(json.dumps(R, default=str)), indent=1)[:4500])
mcp_result = json.loads(json.dumps(R, default=str))
