# tl_spike_bdf_types.py — P0 SPIKE S2c. READ-ONLY, type-aware.
#
# The generic getter order coerced types (Level:Int32 read as 1.0, and the
# Levels set's BuildingToken is a NAME not a String, so it never matched).
# This reads each attribute with the getter matching its DECLARED type.
#
# Declared types (from tl_spike_bdf_attrs.py):
#   Levels : BuildingToken=Name, LevelNumber=Int32, LevelToken=String,
#            LevelHeight=Float, Size=Float, F/F0/F1/F2=String,
#            FLengths=Vector, IsTopper=Bool
#   Modules: BuildingToken=String, Level=Int32, Symbol=String, Size=Double,
#            Mod_Name=String, Mesh=SoftObjectPath, HasProps/HasWindow/
#            bScalable=Bool, PivotOffset=Vector, MeshForwardAxis=Double,
#            PropOffset=Vector, PtID=Int32

import json

R = {}
args = mcp_args or {}
SRC = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG"
EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers

def fmt(v):
    """Make a metadata value JSON-safe."""
    if v is None:
        return None
    try:
        if isinstance(v, unreal.Vector):
            return [round(v.x, 4), round(v.y, 4), round(v.z, 4)]
        if isinstance(v, unreal.Vector4):
            return [round(v.x, 4), round(v.y, 4), round(v.z, 4), round(v.w, 4)]
        if isinstance(v, unreal.SoftObjectPath):
            return v.to_string() if hasattr(v, "to_string") else str(v)
        if isinstance(v, unreal.Transform):
            t = v.translation
            return [round(t.x, 3), round(t.y, 3), round(t.z, 3)]
    except Exception:
        pass
    return str(v)

LEVELS = {
    "BuildingToken": "name", "LevelNumber": "int", "LevelToken": "str",
    "LevelHeight": "dbl", "Size": "dbl", "F": "str", "F0": "str",
    "F1": "str", "F2": "str", "FLengths": "vec", "IsTopper": "bool",
}
MODULES = {
    "BuildingToken": "str", "Level": "int", "Symbol": "str", "Size": "dbl",
    "Mod_Name": "str", "Mesh": "sop", "HasProps": "bool", "HasWindow": "bool",
    "bScalable": "bool", "PivotOffset": "vec", "MeshForwardAxis": "dbl",
    "PropOffset": "vec", "PtID": "int",
}

GETTERS = {
    "str": "get_string_attribute",
    "name": "get_name_attribute",
    "int": "get_integer32_attribute",
    "dbl": "get_double_attribute",
    "bool": "get_bool_attribute",
    "vec": "get_vector_attribute",
    "v4": "get_vector4_attribute",
    "sop": "get_soft_object_path_attribute",
    "xf": "get_transform_attribute",
}

def read_row(pt, md, typemap):
    row = {}
    for nm, ty in typemap.items():
        fn = getattr(MA, GETTERS[ty], None)
        if fn is None:
            row[nm] = "<no getter %s>" % ty
            continue
        try:
            row[nm] = fmt(fn(pt, md, nm))
        except Exception as e:
            row[nm] = "<%s>" % type(e).__name__
    return row

a = EAL.load_asset(SRC)
coll = a.get_editor_property("data")
items = coll.get_editor_property("tagged_data")

def get_set(tag):
    for it in items:
        tg = [str(t) for t in it.get_editor_property("tags")]
        if tag in tg:
            d = it.get_editor_property("data").get_editor_property("data")
            return d, d.mutable_metadata()
    return None, None

# ---------- Levels: CHA's per-level rows (the template TL mirrors) ---------
d, md = get_set("Levels")
if d is not None:
    pts = d.get_points()
    cha, tokens = [], set()
    for pt in pts:
        r = read_row(pt, md, LEVELS)
        tokens.add(r.get("BuildingToken"))
        if str(r.get("BuildingToken")) == "CHA":
            cha.append(r)
    def lvnum(r):
        try:
            return int(float(r.get("LevelNumber")))
        except Exception:
            return 999
    cha.sort(key=lvnum)
    R["levels"] = {
        "num_points": len(pts),
        "distinct_tokens": len([t for t in tokens if t and not str(t).startswith("<")]),
        "cha_count": len(cha),
        "cha_rows": cha,
    }

# ---------- Modules: CHA levels 1-3 ---------------------------------------
d, md = get_set("Modules")
if d is not None:
    pts = d.get_points()
    cha1_3, alllevel = [], []
    for pt in pts:
        r = read_row(pt, md, MODULES)
        if str(r.get("BuildingToken")) == "CHA":
            try:
                lv = int(float(r.get("Level")))
            except Exception:
                lv = -1
            alllevel.append(lv)
            if lv in (1, 2, 3):
                cha1_3.append(r)
    R["modules"] = {
        "num_points": len(pts),
        "cha_levels_present": sorted(set(alllevel)),
        "cha_l1_l3_count": len(cha1_3),
        "cha_l1_l3": cha1_3,
    }

# ---------- also: a module row from a DIFFERENT code, to see mesh path shape
d, md = get_set("Modules")
if d is not None:
    for pt in d.get_points():
        r = read_row(pt, md, MODULES)
        if str(r.get("BuildingToken")) == "SFA" and str(r.get("Level")) == "1":
            R["sample_sfa_module"] = r
            break

print(json.dumps(R, indent=1, default=str))
mcp_result = R
