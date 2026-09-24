# tl_spike_bdf_rows.py — P0 SPIKE S2b. READ-ONLY.
#
# Attribute NAMES are known (from tl_spike_bdf_attrs.py). This dumps the actual
# VALUES for style code CHA, which is the template TL will mirror.
# Also lists every BuildingToken present, so we know the real code inventory.

import json

R = {}
args = mcp_args or {}
SRC = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG"
EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers

BDF_ATTRS = ["BuildingToken", "VerticalGrammar", "VerticalGrammarStaggered",
             "MinWallWidth", "MinBldgHeight", "MaxBldgHeight", "RoofData"]
LVL_ATTRS = ["BuildingToken", "LevelNumber", "LevelToken", "LevelHeight", "Size",
             "F", "F0", "F1", "F2", "FLengths", "IsTopper"]
MOD_ATTRS = ["BuildingToken", "Level", "Symbol", "Size", "Mod_Name", "Mesh",
             "HasProps", "HasWindow", "bScalable", "PivotOffset",
             "MeshForwardAxis", "PropOffset", "PtID"]

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

def read_row(pt, md, names):
    """Read each attribute, trying typed getters in order."""
    row = {}
    for nm in names:
        for fn, tag in (("get_string_attribute", "s"),
                        ("get_name_attribute", "n"),
                        ("get_double_attribute", "d"),
                        ("get_integer32_attribute", "i"),
                        ("get_bool_attribute", "b")):
            try:
                v = getattr(MA, fn)(pt, md, nm)
                row[nm] = str(v)
                break
            except Exception:
                continue
        else:
            row[nm] = None
    return row

# ---------- BDF set: all style codes + CHA's row ---------------------------
d, md = get_set("BDF")
if d is not None:
    pts = d.get_points()
    tokens = []
    cha_row = None
    for pt in pts:
        r = read_row(pt, md, BDF_ATTRS)
        t = r.get("BuildingToken")
        tokens.append(t)
        if t == "CHA":
            cha_row = r
    R["bdf"] = {
        "num_points": len(pts),
        "tokens": tokens,
        "token_count": len(set(tokens)),
        "cha_row": cha_row,
    }

# ---------- Levels set: CHA's rows ----------------------------------------
d, md = get_set("Levels")
if d is not None:
    pts = d.get_points()
    cha_lv = []
    tokens = set()
    for pt in pts:
        r = read_row(pt, md, LVL_ATTRS)
        tokens.add(r.get("BuildingToken"))
        if r.get("BuildingToken") == "CHA":
            cha_lv.append(r)
    cha_lv.sort(key=lambda r: int(r.get("LevelNumber") or 0))
    R["levels"] = {
        "num_points": len(pts),
        "token_count": len([t for t in tokens if t]),
        "cha_level_count": len(cha_lv),
        "cha_levels": cha_lv,
    }

# ---------- Modules set: CHA's rows ---------------------------------------
d, md = get_set("Modules")
if d is not None:
    pts = d.get_points()
    cha_mod = []
    for pt in pts:
        r = read_row(pt, md, MOD_ATTRS)
        if r.get("BuildingToken") == "CHA":
            cha_mod.append(r)
    ok = [r for r in cha_mod if r.get("Level") in ("1", "2", "3")]
    R["modules"] = {
        "num_points": len(pts),
        "cha_module_count": len(cha_mod),
        "cha_levels_1_2_3": ok,
    }

print(json.dumps(R, indent=1, default=str))
mcp_result = R
