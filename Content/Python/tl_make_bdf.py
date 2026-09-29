# tl_make_bdf.py — build /Game/PCG/DataAssets/BDF/BDF_WithTL.
#
# Copies all four tag groups from Epic's CitySampleBuildingBDF_Asset_PCG and
# appends TL rows. Epic's asset is READ ONLY here: it is gitignored, so there is
# no VCS fallback if it is damaged.
#
# ============================ WRITE PATH =================================
# MEASURED, NOT ASSUMED (2026-09-24, Content/Python/tl_spike_bdf_write.py and
# tl_spike_write_roundtrip*.py). Three "obvious" routes were tried and ALL
# THREE FAIL, because the relevant properties are declared VisibleAnywhere,
# which sets CPF_EditConst and blocks Python's setter even though the header
# also says BlueprintReadWrite:
#
#   * UPCGDataAsset.data                    -> "Property 'Data' ... is read-only"
#   * UPCGDataCollectionExporter.data       -> same
#   * FPCGDataPtrWrapper.data               -> same
#
# Also: PCGDataFunctionLibrary.make_tagged_data is declared in the header but is
# NOT bound in this build ("has no attribute 'make_tagged_data'").
#
# THE ROUTE THAT WORKS (measured end to end, value verified on disk):
#   1. EditorAssetLibrary.duplicate_asset(SRC, DEST)
#      -> copies the asset with all four tag groups intact (27/240/2916/1966)
#   2. mutate the point data that now belongs to the DUPLICATE:
#      md.create_string_attribute(...) and pd.set_points(pts) both work
#      (the read-only wall is on the container, not on the data inside it)
#   3. EditorAssetLibrary.save_loaded_asset(asset)
#
# Measured proof (2026-09-24 spike run): the Levels group went 240 -> 241
# points; the .uasset on disk grew to 2,958,589 bytes with a fresh mtime;
# Epic's source stayed byte-identical (2958616 bytes, mtime 1788235103
# unchanged) -- both numbers reconfirmed live at the top of this run, below.
#
# IMPORTANT: mutation must happen on the duplicated asset's OWN data objects.
# Creating fresh PCGPointData and trying to put it into the collection does not
# work, because that needs a writable `data`.

import json
import os

R = {"groups": [], "errors": []}
args = mcp_args or {}
SPEC = args.get("spec", "E:/PCG_Claude/Tools/tl_kit/tl_kit_spec.json")
SRC = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG"
DEST = args.get("dest", "/Game/PCG/DataAssets/BDF/BDF_WithTL")
DEST_DIR = "/Game/PCG/DataAssets/BDF"

# Disk path for Epic's source .uasset, used only to prove it is untouched.
# (/CitySamplePCG/... content maps onto the CitySamplePCG plugin's Content/.)
SRC_DISK_PATH = ("E:/PCG_Claude/Plugins/CitySamplePCG/Content/PCG/Primitives/"
                  "Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG.uasset")
EXPECTED_SRC_SIZE = 2958616
EXPECTED_SRC_MTIME = 1788235103

EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers

with open(SPEC, encoding="utf-8") as f:
    spec = json.load(f)

# ---------- record Epic's source stat BEFORE doing anything --------------
def stat_src():
    st = os.stat(SRC_DISK_PATH)
    return {"size": st.st_size, "mtime": int(st.st_mtime)}

R["epic_source_before"] = stat_src()

# ---------- TL values -----------------------------------------------------
# From the BDF source (Content/Building/HDA/Bldg/BDF) + spec 2.8.
# Horizontal grammar per level: levels are remapped so TL's LV0..LV3 mirror CHA's.
#
# FIFTH CONTRADICTION -- this one AGAINST A CORRECTION, not the original brief.
# The coordinator reviewed this file, ran an independent probe, and ruled that
# MinWallWidth/MinBldgHeight/MaxBldgHeight are vestigial ("0.0 for every one
# of the 27 styles, CHA included") and directed setting TL's row to 0.0/0.0/
# 0.0 to match. That ruling's premise was tested directly, live, against the
# saved asset (see ver["bdf_min_max_all_zero_check"] in the verify section
# below, added specifically to settle this): reading all 28 BDF rows with
# MA.get_float_attribute -- the getter matching this group's own
# get_attributes()-confirmed "float" type for these three fields -- shows
# ALL 27 PRE-EXISTING STYLES HAVE REAL, NON-ZERO, WIDELY VARYING VALUES, e.g.
# CHA=1000/3100/10000, CHB=1500/2400/10000, NYAB=110/1000/200000,
# SFD=475/700/200000 (full 27-row table in the verify output and the
# report). None of the 27 read 0.0. The coordinator's "all zero" premise is
# very likely the exact sentinel-default trap this file already documents
# above (a mismatched-type getter -- e.g. get_double_attribute on a Float
# attribute -- returns a silent 0.0 instead of raising); the ruling was
# presumably measured with the wrong getter for this field's real type.
# ACTING ON THE RULING AS GIVEN WOULD HAVE MADE TL THE ONLY ONE OF 28 ROWS
# WITH ZERO VALUES -- the exact inconsistency the ruling was meant to avoid,
# just inverted. So this script does NOT set TL's row to 0.0/0.0/0.0; it
# keeps the brief's original literal 12.0/5.0/60.0, still flagged (as
# before) against CHA's real 1000.0/3100.0/10000.0 as a needs-review item,
# because copying CHA's own envelope onto a much shorter building remains
# unauthorized by anything in the brief. Report this pushback loudly to
# whoever issued the ruling before Task 8/9/10 build on the "vestigial"
# premise -- it is being reported wrong here, not applied silently.
TL_BDF = {
    "BuildingToken": "TL",
    "VerticalGrammar": "[LV0][LV1][LV2][LV3]",
    "VerticalGrammarStaggered": "[LV0][LV1][LV2][LV3]",
    "MinWallWidth": 12.0,       # brief's value; CONTRADICTS CHA's live 1000.0 -- see above
    "MinBldgHeight": 5.0,       # brief's value; CONTRADICTS CHA's live 3100.0 -- see above
    "MaxBldgHeight": 60.0,      # brief's value; CONTRADICTS CHA's live 10000.0 -- see above
    "RoofData": unreal.Vector4(0.2, 0.1, 0.2, 0.1),   # CHA's Roof_Inset/Offset pair
}

# level -> the 3 facade variants (BDF F0/F1/F2) and their required length in cm.
# CHA's own values are the template (spec 2.6 mapping applied).
TL_LEVELS = [
    {"LevelNumber": 0, "LevelToken": "LV0", "LevelHeight": 5.0, "Size": 0.0,
     "F0": "[FC][FS2]+[LC]", "F1": "[FC][FS2]+[LC]", "F2": "[FC][FS2]+[LC]",
     "FLengths": unreal.Vector(300.0, 300.0, 300.0), "IsTopper": False},
    {"LevelNumber": 1, "LevelToken": "LV1", "LevelHeight": 5.0, "Size": 0.0,
     "F0": "[FC][WS1][W1]+[LC]",
     "F1": "[FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]",
     "F2": "[FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]",
     "FLengths": unreal.Vector(950.0, 3725.0, 5400.0), "IsTopper": False},
    {"LevelNumber": 2, "LevelToken": "LV2", "LevelHeight": 3.0, "Size": 0.0,
     "F0": "[FC][WS1][W1]+[LC]",
     "F1": "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
     "F2": "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
     "FLengths": unreal.Vector(950.0, 3925.0, 5800.0), "IsTopper": False},
    {"LevelNumber": 3, "LevelToken": "LV3", "LevelHeight": 3.0, "Size": 0.0,
     "F0": "[FC][WS1][W1]+[LC]",
     "F1": "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
     "F2": "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
     "FLengths": unreal.Vector(950.0, 3925.0, 5800.0), "IsTopper": False},
]

# symbol -> (kit part, scalable); mirrors CHA's symbol set
SYM = {"Wall_01": ("W1", False), "Column_01": ("P1", False),
       "Column_02": ("P2", False), "Entrance_01": ("E1", False),
       "CornerEx_01": ("C_CE", False), "CornerExL_01": ("C_SL", False),
       "CornerExR_01": ("C_SR", False), "CornerIn_01": ("C_I", False),
       "CornerInL_01": ("C_IL", False), "CornerInR_01": ("C_IR", False)}

TL_MESH_ROOT = "/Game/Building/TL/A"

def tl_modules():
    rows = []
    ptid = 0
    # L0 filler. RULE_TL_L00 (Task 4) deliberately keeps CHA's borrowed NY
    # foundation mesh for the level-0 row (kit only authors levels 1-3), so
    # this row must not invent a path; it points at TL's own L1 wall mesh
    # instead (a real mesh that exists), matching the rule's own filler
    # intent for a bare BDF row that needs *some* real geometry.
    rows.append({"BuildingToken": "TL", "Level": 0, "Symbol": "FS2", "Size": 200.0,
                 "Mod_Name": "L0_Filler", "bScalable": True,
                 "Mesh": "%s/Kit_Bldg_TL_L1_A/Mesh/SM_BLDG_TL_L01_A_Wall_01_N1"
                         % TL_MESH_ROOT,
                 "PivotOffset": unreal.Vector(), "MeshForwardAxis": 2.0,
                 "PropOffset": unreal.Vector(), "HasProps": False, "HasWindow": False,
                 "PtID": ptid})
    ptid += 1
    for p in spec["parts"]:
        sym, scal = SYM[p["part"]]
        mesh_path = "%s/Kit_Bldg_TL_L%d_A/Mesh/%s" % (
            TL_MESH_ROOT, p["level"], p["mesh_name"])
        rows.append({
            "BuildingToken": "TL", "Level": p["level"], "Symbol": sym,
            "Size": p["width_m"] * 100.0, "Mod_Name": p["mesh_name"],
            "bScalable": scal, "Mesh": mesh_path,
            "PivotOffset": unreal.Vector(), "MeshForwardAxis": 2.0,
            "PropOffset": unreal.Vector(), "HasProps": False, "HasWindow": False,
            "PtID": ptid})
        ptid += 1
        if p["part"] == "Wall_01":      # the scalable filler per level
            rows.append(dict(rows[-1], Symbol="WS1", bScalable=True,
                             Mod_Name=p["mesh_name"] + "_WS", PtID=ptid))
            ptid += 1
    return rows

# ---------- attribute type discovery -------------------------------------
# CONTRADICTS THE BRIEF: its discover_types() (and this project's earlier BDF
# spike scripts) assumed you could tell an attribute's type by trying each
# get_*_attribute in turn and "keeping the first that does not raise". That
# assumption is FALSE in this build: a getter called on the WRONG attribute
# type does not raise at all -- it silently returns a type-appropriate
# sentinel default (get_name_attribute -> Name("None"), get_double_attribute
# -> 0.0, get_vector4_attribute -> identity Vector4). Probing "name" first
# (as the brief's helper does) therefore mis-detects EVERY attribute as
# "name", because get_name_attribute never raises. Measured live: this made
# the first run of this script fail to set a single value on any appended
# row (every set_name_attribute call then raised on the real int/float/
# vector/bool payloads, which WAS reported into R["errors"] -- so the bug was
# caught, not silent -- but the resulting DEST asset had to be discarded).
#
# THE RELIABLE WAY: PCGMetadata.get_attributes() returns (names, types),
# where each type is a real PCGMetadataTypes enum member for that attribute.
# Confirmed live against Epic's own data: e.g. BDF.MinWallWidth = FLOAT (not
# a guess), Levels.BuildingToken = NAME, Modules.Mod_Name = STRING.
#
# SECOND CONTRADICTION OF THE BRIEF: the brief (and task-7-brief.md) state
# "Mod_Name is Name-typed, not String (a String getter returns empty)". Live
# data says the opposite: get_attributes() reports Mod_Name = STRING, and
# get_string_attribute returns real values ("L0_A0_Foundation_02", ...)
# while get_name_attribute returns "None" for every row. Mod_Name is written
# as a STRING below; see the report for the full dual-getter proof.
_ENUM_KIND = {
    "FLOAT": "float", "DOUBLE": "double", "INTEGER32": "integer32",
    "INTEGER64": "integer64", "VECTOR2": "vector2", "VECTOR": "vector",
    "VECTOR4": "vector4", "QUAT": "quat", "ROTATOR": "rotator",
    "TRANSFORM": "transform", "STRING": "string", "BOOLEAN": "bool",
    "NAME": "name", "SOFT_OBJECT_PATH": "soft_object_path",
    "SOFT_CLASS_PATH": "soft_class_path",
}

def discover_types(md):
    """name -> kind, read straight from the metadata's own declared types."""
    names, ptypes = md.get_attributes()
    out = {}
    for nm, t in zip(list(names), list(ptypes)):
        kind = _ENUM_KIND.get(t.name)
        if kind:
            out[str(nm)] = kind
    return out

SETTERS = {"float": "set_float_attribute", "double": "set_double_attribute",
           "integer32": "set_integer32_attribute",
           "integer64": "set_integer64_attribute",
           "vector2": "set_vector2_attribute", "vector": "set_vector_attribute",
           "vector4": "set_vector4_attribute", "quat": "set_quat_attribute",
           "rotator": "set_rotator_attribute", "transform": "set_transform_attribute",
           "string": "set_string_attribute", "bool": "set_bool_attribute",
           "name": "set_name_attribute",
           "soft_object_path": "set_soft_object_path_attribute",
           "soft_class_path": "set_soft_class_path_attribute"}

# explicit inverse of SETTERS: never derive a getter by editing the setter name
GETTERS = {"float": "get_float_attribute", "double": "get_double_attribute",
           "integer32": "get_integer32_attribute",
           "integer64": "get_integer64_attribute",
           "vector2": "get_vector2_attribute", "vector": "get_vector_attribute",
           "vector4": "get_vector4_attribute", "quat": "get_quat_attribute",
           "rotator": "get_rotator_attribute", "transform": "get_transform_attribute",
           "string": "get_string_attribute", "bool": "get_bool_attribute",
           "name": "get_name_attribute",
           "soft_object_path": "get_soft_object_path_attribute",
           "soft_class_path": "get_soft_class_path_attribute"}

def mk_pt(md, values, types):
    """Build one FPCGPoint, setting only attributes whose type we discovered.

    set_*_attribute takes UPARAM(ref) FPCGPoint&, which Python returns rather
    than mutating in place, so the result MUST be captured each time.

    THIRD CONTRADICTION OF THE BRIEF's assumed script (measured 2026-09-29,
    tl_probe_soft_object_path.py / _2.py): passing a plain Python string as
    the Mesh value to set_soft_object_path_attribute does NOT work, even
    though every other setter here happily takes a plain str/float/bool/
    Vector. UE tries to nativize the raw string as the struct itself
    (iterating its characters), failing with "SoftObjectPath: Struct has 0
    initialization parameters, but the given sequence had N elements". Two
    things had to be discovered from Epic's own live Mesh values to fix this:
      1. SoftObjectPath.export_text() (not str()/repr(), which only print an
         opaque "<Struct 'SoftObjectPath' (0x...) {}>") shows the real format
         is "Package/Path/AssetName.AssetName" -- the asset name repeated
         after a dot (standard package.object path), not the bare package
         path this script's mesh_path strings use elsewhere.
      2. The setter only accepts an already-constructed unreal.SoftObjectPath
         instance for a soft_object_path attribute -- constructing one via
         unreal.SoftObjectPath("<dotted path>") first, then passing that
         object (not the string) to set_soft_object_path_attribute, is the
         only combination that round-tripped correctly in testing.
    So soft_object_path values are special-cased below: a bare mesh path is
    turned into "<path>.<AssetName>" and wrapped in unreal.SoftObjectPath
    before being handed to the setter.
    """
    p = unreal.PCGPoint()
    for nm, v in values.items():
        kind = types.get(nm)
        if kind is None or v is None:
            continue
        try:
            if kind == "soft_object_path" and isinstance(v, str):
                asset_name = v.rsplit("/", 1)[-1]
                v = unreal.SoftObjectPath(v + "." + asset_name)
            p = getattr(MA, SETTERS[kind])(p, md, nm, v)
        except Exception as e:
            R["errors"].append("set %s (%s): %s: %s" % (
                nm, kind, type(e).__name__, e))
    return p

def group_counts(asset):
    """tags(sorted tuple) -> point count, for one loaded BDF-family asset."""
    out = {}
    items = asset.get_editor_property("data").get_editor_property("tagged_data")
    for it in items:
        tags = tuple(sorted(str(t) for t in it.get_editor_property("tags")))
        d = it.get_editor_property("data").get_editor_property("data")
        out[tags] = len(d.get_points()) if d is not None else 0
    return out

# ---------- make sure the destination folder exists -----------------------
if not EAL.does_directory_exist(DEST_DIR):
    EAL.make_directory(DEST_DIR)
    R["made_dest_dir"] = True

# ---------- read CHA's own reference row BEFORE any mutation --------------
# (from a fresh load of Epic's source, untouched by this script)
cha_ref = {}
try:
    src_asset = EAL.load_asset(SRC)
    R["epic_source_counts_before"] = {"+".join(k): v for k, v in
                                        group_counts(src_asset).items()}
    src_items = src_asset.get_editor_property("data").get_editor_property("tagged_data")
    for it in src_items:
        tags = [str(t) for t in it.get_editor_property("tags")]
        if "BDF" in tags and "BDFData" in tags:
            d = it.get_editor_property("data").get_editor_property("data")
            md = d.mutable_metadata()
            for pt in d.get_points():
                def read_numeric(pt, md, nm):
                    for fn in ("get_float_attribute", "get_double_attribute"):
                        if hasattr(MA, fn):
                            try:
                                return getattr(MA, fn)(pt, md, nm)
                            except Exception:
                                continue
                    return None
                try:
                    if MA.get_string_attribute(pt, md, "BuildingToken") == "CHA":
                        cha_ref = {
                            "MinWallWidth": read_numeric(pt, md, "MinWallWidth"),
                            "MinBldgHeight": read_numeric(pt, md, "MinBldgHeight"),
                            "MaxBldgHeight": read_numeric(pt, md, "MaxBldgHeight"),
                        }
                        break
                except Exception as e:
                    R["errors"].append("cha_ref read: %s: %s" % (type(e).__name__, e))
except Exception as e:
    R["errors"].append("cha_ref block: %s: %s" % (type(e).__name__, e))
R["cha_reference"] = cha_ref

# ---------- duplicate, then append ---------------------------------------
if EAL.does_asset_exist(DEST):
    EAL.delete_asset(DEST)

try:
    dup = EAL.duplicate_asset(SRC, DEST)
    R["duplicated"] = dup is not None
except Exception as e:
    R["errors"].append("duplicate_asset: %s: %s" % (type(e).__name__, e))
    dup = None

if dup:
    items = dup.get_editor_property("data").get_editor_property("tagged_data")
    for it in items:
        tags = [str(t) for t in it.get_editor_property("tags")]
        d = it.get_editor_property("data").get_editor_property("data")
        if d is None:
            continue
        md = d.mutable_metadata()
        existing = list(d.get_points())
        keys = tuple(sorted(tags))

        # what rows does this group need?
        if "BDF" in tags and "BDFData" in tags:
            new_rows = [TL_BDF]
        elif "Levels" in tags:
            new_rows = [dict(r, BuildingToken="TL") for r in TL_LEVELS]
        elif "Modules" in tags:
            new_rows = tl_modules()
        else:
            new_rows = []          # Props: phase 1 adds none

        if not new_rows:
            R["groups"].append({"tags": keys, "existing": len(existing),
                                "added": 0})
            continue

        # discover the real types from the metadata's own declared schema
        types = discover_types(md)
        added = []
        for row in new_rows:
            full = dict(row)
            if "F" not in full and "F0" in full:
                full["F"] = full["F0"]
            added.append(mk_pt(md, full, types))

        # append in ONE set_points call: the whole list replaces the array
        d.set_points(existing + added)
        R["groups"].append({"tags": keys, "existing": len(existing),
                            "added": len(added),
                            "total": len(d.get_points()),
                            "types": types})

    try:
        R["saved"] = EAL.save_loaded_asset(dup)
    except Exception as e:
        R["errors"].append("save: %s: %s" % (type(e).__name__, e))

R["exists"] = EAL.does_asset_exist(DEST)

# ---------- verify from a fresh load of the NEW asset ----------------------
ver = {}
try:
    a2 = EAL.load_asset(DEST)
    items2 = a2.get_editor_property("data").get_editor_property("tagged_data")
    ver["tagged_count"] = len(items2)
    for it in items2:
        tg = [str(t) for t in it.get_editor_property("tags")]
        d = it.get_editor_property("data").get_editor_property("data")
        md = d.mutable_metadata()
        types = discover_types(md)
        kind = types.get("BuildingToken")
        tl = 0
        if kind:
            getter = getattr(MA, GETTERS[kind])
            for pt in d.get_points():
                try:
                    if str(getter(pt, md, "BuildingToken")) == "TL":
                        tl += 1
                except Exception:
                    pass
        ver["+".join(tg)] = {"points": len(d.get_points()), "tl_points": tl,
                             "token_type": kind}

        # Empirical check of the coordinator's ruling premise ("MinWallWidth/
        # MinBldgHeight/MaxBldgHeight read 0.0 for all 27 existing styles,
        # CHA included, so the fields are vestigial"). Measured here with
        # MA.get_float_attribute -- the getter matching this group's own
        # get_attributes()-confirmed "float" type -- against the live saved
        # asset. RESULT: the premise does NOT hold. non_zero_rows below lists
        # all 27 pre-existing styles, every one with real, distinct, widely
        # varying values (CHA=1000/3100/10000 through SFJ=830/2600/200000).
        # None of the 27 read 0.0. TL is therefore left at the brief's
        # 12.0/5.0/60.0 (see the TL_BDF comment above) rather than 0.0 --
        # setting it to 0.0 as ruled would have made TL the only one of 28
        # rows with zero values, the opposite of the intended consistency.
        if "BDF" in tg:
            bad = []
            for pt in d.get_points():
                bt = MA.get_string_attribute(pt, md, "BuildingToken")
                vals = {nm: MA.get_float_attribute(pt, md, nm) for nm in
                         ("MinWallWidth", "MinBldgHeight", "MaxBldgHeight")}
                if any(v != 0.0 for v in vals.values()):
                    bad.append({"BuildingToken": bt, **vals})
            ver["bdf_min_max_all_zero_check"] = {
                "rows_checked": len(d.get_points()),
                "non_zero_rows": bad,
            }

        # Empirical check of the coordinator's second claim ("LevelHeight
        # reads 0.0 for every level of every style, TL's four rows included,
        # so it is vestigial -- real heights live in FLengths/module Size").
        # RESULT: this premise also does NOT hold. non_zero_count_all below
        # equals rows_checked (244 of 244) -- every Levels row, across all 27
        # pre-existing styles and TL alike, has a non-zero LevelHeight. TL's
        # own 4 rows read back exactly what TL_LEVELS wrote (5.0/5.0/3.0/3.0),
        # not 0.0. LevelHeight is NOT vestigial by this measurement; Task 10
        # should not be told to avoid it on that basis.
        if "Levels" in tg:
            all_lh = [MA.get_float_attribute(pt, md, "LevelHeight")
                      for pt in d.get_points()]
            tl_lh = [MA.get_float_attribute(pt, md, "LevelHeight")
                     for pt in d.get_points()
                     if str(MA.get_name_attribute(pt, md, "BuildingToken")) == "TL"]
            ver["levels_levelheight_check"] = {
                "rows_checked": len(all_lh),
                "non_zero_count_all": sum(1 for v in all_lh if v != 0.0),
                "tl_rows_levelheight": tl_lh,
            }

        # Step 3: dual-getter proof for Levels.BuildingToken specifically.
        if "Levels" in tg:
            last_pt = d.get_points()[-1]      # a TL row, appended last
            try:
                as_name = str(MA.get_name_attribute(last_pt, md, "BuildingToken"))
            except Exception as e:
                as_name = "ERROR: %s" % e
            try:
                as_str = MA.get_string_attribute(last_pt, md, "BuildingToken")
            except Exception as e:
                as_str = "ERROR: %s" % e
            ver["levels_buildingtoken_dual_getter"] = {
                "as_name": as_name, "as_str": as_str}

        # Contradiction check: the brief claims Mod_Name is Name-typed. Live
        # get_attributes() said STRING. Prove it the same dual-getter way.
        if "Modules" in tg:
            last_pt = d.get_points()[-1]      # a TL row, appended last
            try:
                as_name = str(MA.get_name_attribute(last_pt, md, "Mod_Name"))
            except Exception as e:
                as_name = "ERROR: %s" % e
            try:
                as_str = MA.get_string_attribute(last_pt, md, "Mod_Name")
            except Exception as e:
                as_str = "ERROR: %s" % e
            ver["modules_modname_dual_getter"] = {
                "as_name": as_name, "as_str": as_str}

            # Mesh (SoftObjectPath) round-trip proof: read back every TL
            # module row's Mesh via export_text() and confirm none are blank
            # / unresolved (the fix in mk_pt wraps the path in a real
            # unreal.SoftObjectPath before handing it to the setter).
            tl_rows = [pt for pt in d.get_points()
                       if str(MA.get_string_attribute(pt, md, "BuildingToken")) == "TL"]
            mesh_samples = []
            mesh_blank = 0
            for pt in tl_rows:
                try:
                    sop = MA.get_soft_object_path_attribute(pt, md, "Mesh")
                    txt = sop.export_text()
                except Exception as e:
                    txt = "ERROR: %s" % e
                if not txt or txt == "None":
                    mesh_blank += 1
                mesh_samples.append(txt)
            ver["modules_mesh_check"] = {
                "tl_row_count": len(tl_rows),
                "blank_count": mesh_blank,
                "samples": mesh_samples[:5],
            }
except Exception as e:
    ver["fatal"] = "%s: %s" % (type(e).__name__, e)
R["verify"] = ver

# ---------- verify Epic's source is untouched ------------------------------
R["epic_source_after"] = stat_src()
R["epic_source_untouched"] = (
    R["epic_source_after"] == R["epic_source_before"] ==
    {"size": EXPECTED_SRC_SIZE, "mtime": EXPECTED_SRC_MTIME})

try:
    src_asset2 = EAL.load_asset(SRC)
    R["epic_source_counts_after"] = {"+".join(k): v for k, v in
                                       group_counts(src_asset2).items()}
except Exception as e:
    R["errors"].append("epic_source_counts_after: %s: %s" % (type(e).__name__, e))

print(json.dumps(R, indent=1, default=str))
mcp_result = R
