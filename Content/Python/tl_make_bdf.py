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

import gc as _gc
import json
import os


# globals() persists across run_unreal_script calls. A previous run's UObject
# wrappers (dup, d, md, a2, ...) would keep BDF_WithTL referenced, so drop
# every global holding an unreal.Object/StructBase before doing anything.
def _holds_uobject(val):
    if isinstance(val, (unreal.Object, unreal.StructBase)):
        return True
    if isinstance(val, (list, tuple, set)):
        return any(_holds_uobject(v) for v in val)
    if isinstance(val, dict):
        return any(_holds_uobject(v) for v in val.values())
    return False


for _nm, _val in list(globals().items()):
    if _nm.startswith("__") or callable(_val) or isinstance(_val, type):
        continue
    try:
        if _holds_uobject(_val):
            del globals()[_nm]
    except Exception:
        continue
_gc.collect()

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
# Units are centimetres throughout, like every sibling style (the .bdf JSON
# source is metre-scale; TL's values below are the converted ones).
#   MinWallWidth  = 950.0 cm  -- TL's own narrowest FLengths.x (LV1-LV3 all
#                                start at 950), the narrowest wall TL can build on.
#   MinBldgHeight = 1600.0 cm -- TL's full fixed four-level stack:
#                                500(L0)+500(L1)+300(L2)+300(L3).
#   MaxBldgHeight = 200000.0 cm -- an open-ended sentinel, matching 21 of the
#                                28 styles (including every CH*). This field is
#                                read as a match window against a requested
#                                height, not descriptive metadata, so it must
#                                not equal MinBldgHeight (a zero-width window
#                                makes the style unselectable).
#   VerticalGrammar = "[LV0][LV1][LV2]*[LV3]" -- contains a `*` repeat marker,
#                                like all 27 siblings. A grammar with no
#                                repeatable level can only ever produce one
#                                exact height and is rejected by every lot.
#   VerticalGrammarStaggered = "[LV2][LV2]*[LV3]" -- starts at an upper storey
#                                rather than the ground floor, as CHJ's does.
#
# The city-stage zero (0 of 475,728+ instances, no error) was caused by two
# filters upstream of this data, not by any BDF value: the call-site
# BuildingsStyles overrides on PCG_3_3_1_Buildings (see tl_whitelist_city.py)
# and the CitySampleBuildingBDF_NamesOnly_PCG substring filter (see
# tl_names_with_tl.py). Do not change the values below to chase that symptom
# again; see migrated-citysample-library.md §3.2 for the root cause.
TL_BDF = {
    "BuildingToken": "TL",
    "VerticalGrammar": "[LV0][LV1][LV2]*[LV3]",
    # Staggered sections sit on top of the main volume, so like every sibling
    # (CHJ: [LV2][LV2]*[LV3]) they start at an upper storey, not the ground floor.
    "VerticalGrammarStaggered": "[LV2][LV2]*[LV3]",
    "MinWallWidth": 950.0,       # cm; TL's own narrowest FLengths.x (was 12.0 m, unconverted)
    "MinBldgHeight": 1600.0,     # cm; same value as CHF
    "MaxBldgHeight": 200000.0,   # cm; open-ended sentinel, matching 21/28 siblings
    "RoofData": unreal.Vector4(20.0, 10.0, 20.0, 10.0),   # cm
}

# level -> the 3 facade variants (BDF F0/F1/F2) and their required length in cm.
# CHA's own values are the template (spec 2.6 mapping applied). LevelHeight
# is in centimetres, matching every sibling style (CHA's LV1 reads 500.0).
#
# Size mirrors LevelHeight per row, confirmed live against CHA (LV1:
# LevelHeight=500.0, Size=500.0) and CHF (LV1: LevelHeight=550.0, Size=550.0);
# every working sibling's Size equals its own LevelHeight.
TL_LEVELS = [
    # LV0 is the foundation band: 0.5 cm in all 27 sibling styles, and the
    # same 0.5 the SGD route's RULE_TL_L00 produces in Lvl_TL_Building.
    {"LevelNumber": 0, "LevelToken": "LV0", "LevelHeight": 0.5, "Size": 0.5,
     "F0": "[FC][FS2]+[LC]", "F1": "[FC][FS2]+[LC]", "F2": "[FC][FS2]+[LC]",
     "FLengths": unreal.Vector(300.0, 300.0, 300.0), "IsTopper": False},
    {"LevelNumber": 1, "LevelToken": "LV1", "LevelHeight": 500.0, "Size": 500.0,
     "F0": "[FC][WS1][W1]+[LC]",
     "F1": "[FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]",
     "F2": "[FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]",
     "FLengths": unreal.Vector(950.0, 3725.0, 5400.0), "IsTopper": False},
    {"LevelNumber": 2, "LevelToken": "LV2", "LevelHeight": 300.0, "Size": 300.0,
     "F0": "[FC][WS1][W1]+[LC]",
     "F1": "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
     "F2": "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
     "FLengths": unreal.Vector(950.0, 3925.0, 5800.0), "IsTopper": False},
    {"LevelNumber": 3, "LevelToken": "LV3", "LevelHeight": 300.0, "Size": 300.0,
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
TL_LEVEL_HEIGHT = {r["LevelNumber"]: r["LevelHeight"] for r in TL_LEVELS}

def tl_modules(level0_rows):
    """TL's Modules rows.

    The BDF route places each module with its slot origin at the slot's
    horizontal centre and the level's mid-height, so every sibling style sets
    PivotOffset = (0, -run_centre, -LevelHeight/2). TL's kit is corner/base
    pivoted (run along +Y over [0, width], height over [0, LevelHeight]), so
    its offset is (0, -width/2, -LevelHeight/2). The SGD route
    (Lvl_TL_Building) does not read these rows.

    Level 0 is CHA's level 0 (`level0_rows`, cloned from the asset), the same
    choice RULE_TL_L00 makes for the SGD route: the kit authors no foundation.
    Every sibling's corner grammar also uses C_E for exterior corners, so each
    TL level gets a C_E row on the same CornerEx mesh as its C_CE row, as CHA
    does.
    """
    rows = [dict(r, BuildingToken="TL") for r in level0_rows]
    ptid = 0
    for p in spec["parts"]:
        sym, scal = SYM[p["part"]]
        width = p["width_m"] * 100.0
        mesh_path = "%s/Kit_Bldg_TL_L%d_A/Mesh/%s" % (
            TL_MESH_ROOT, p["level"], p["mesh_name"])
        rows.append({
            "BuildingToken": "TL", "Level": p["level"], "Symbol": sym,
            "Size": width, "Mod_Name": p["mesh_name"],
            "bScalable": scal, "Mesh": mesh_path,
            "PivotOffset": unreal.Vector(0.0, -width / 2.0,
                                         -TL_LEVEL_HEIGHT[p["level"]] / 2.0),
            "MeshForwardAxis": 2.0,
            "PropOffset": unreal.Vector(), "HasProps": False, "HasWindow": False,
            "PtID": ptid})
        ptid += 1
        if p["part"] == "Wall_01":      # the scalable filler per level
            rows.append(dict(rows[-1], Symbol="WS1", bScalable=True,
                             Mod_Name=p["mesh_name"] + "_WS", PtID=ptid))
            ptid += 1
        if sym == "C_CE":
            rows.append(dict(rows[-1], Symbol="C_E", PtID=ptid))
            ptid += 1
    return rows


def level0_of(d, md, types, token="CHA"):
    """Every attribute of `token`'s level-0 module rows, as setter-ready dicts."""
    out = []
    for pt in d.get_points():
        if MA.get_string_attribute(pt, md, "BuildingToken") != token:
            continue
        if MA.get_integer32_attribute(pt, md, "Level") != 0:
            continue
        out.append({nm: getattr(MA, GETTERS[kind])(pt, md, nm)
                    for nm, kind in types.items()})
    return out

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

    THIRD CONTRADICTION OF THE BRIEF's assumed script (measured 2026-09-29 via
    a throwaway probe): passing a plain Python string as
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
# SEVENTH CONTRADICTION -- the embedded editor Python interpreter's `globals()`
# namespace is NOT fresh per run_unreal_script call; it persists across runs
# within the same editor session (confirmed with a throwaway probe: a second
# run found DEST/dup/TL_BDF/etc. still bound from the previous run's
# execution of this very script). That is silently dangerous here: if a
# previous run left "dup"/"d"/"md"/"asset"/etc. bound to Python wrappers of
# BDF_WithTL's UObjects, EditorAssetLibrary.delete_asset(DEST) below returns
# False (not an exception) because something still references the object,
# duplicate_asset then produces a stale/no-op result, and everything after it
# silently mutates or reads the OLD asset while this run's own R["groups"]
# stays empty and R["duplicated"] is never true -- exactly what happened on
# a real re-run here: groups: [], duplicated: false, and the verify block
# read back last run's values instead of this run's fix. The purge of every
# global holding an unreal.Object/StructBase therefore runs at the very top of
# this script, before it defines anything of its own (TL_BDF and TL_LEVELS
# hold unreal.Vector values and would be purged too).

# ---------- patch vs. rebuild mode ----------------------------------------
# LoadCitySampleData references DEST once it exists. delete_asset(DEST)
# force-deletes it out from under that reference, nulls the reference, and
# logs "this package is now potentially corrupt" (measured 2026-10-01,
# traps.md item 39). So when DEST exists, PATCH IN PLACE IS THE DEFAULT. A
# full rebuild (delete + duplicate_asset) only runs when the caller asks for
# it explicitly AND find_package_referencers_for_asset confirms nothing
# references DEST; if that function is unavailable in this build, the
# rebuild is refused rather than risking a delete with no way to check.
#
# {"patch_only": true} is still accepted but is now a no-op alias: patching
# is already what happens by default.
_patch_mode = False
if EAL.does_asset_exist(DEST):
    _rebuild_requested = bool(args.get("rebuild"))
    _rebuild_cleared = False
    if _rebuild_requested:
        if hasattr(EAL, "find_package_referencers_for_asset"):
            _referencers = list(EAL.find_package_referencers_for_asset(DEST, False))
            _rebuild_cleared = len(_referencers) == 0
            if not _rebuild_cleared:
                R["errors"].append(
                    "rebuild requested but %s has referencers %s -- "
                    "refusing to delete a referenced asset; patching in "
                    "place instead." % (DEST, _referencers))
        else:
            R["errors"].append(
                "rebuild requested but this build's EditorAssetLibrary has "
                "no find_package_referencers_for_asset, so referencers "
                "can't be confirmed empty; refusing the rebuild and "
                "patching in place instead.")

    if _rebuild_requested and _rebuild_cleared:
        _deleted = EAL.delete_asset(DEST)
        if not _deleted and EAL.does_asset_exist(DEST):
            R["errors"].append(
                "delete_asset(%s) returned False and the asset still "
                "exists -- a stale Python reference from a previous run in "
                "this same editor session is the most likely cause; "
                "patching in place instead." % DEST)
            R["patch_mode"] = True
            _patch_mode = True
    else:
        R["patch_mode"] = True
        _patch_mode = True

if _patch_mode:
    dup = EAL.load_asset(DEST)
    R["duplicated"] = False
    if dup is None:
        R["errors"].append("patch_mode: load_asset(%s) returned None" % DEST)
else:
    try:
        dup = EAL.duplicate_asset(SRC, DEST)
        R["duplicated"] = dup is not None
        if dup is None:
            R["errors"].append(
                "duplicate_asset(%s, %s) returned None -- likely because the "
                "prior delete_asset failed (see above); aborting rather than "
                "silently reading/writing whatever asset is currently at DEST."
                % (SRC, DEST))
    except Exception as e:
        R["errors"].append("duplicate_asset: %s: %s" % (type(e).__name__, e))
        dup = None

if dup and _patch_mode:
    # Narrow patch: touch only the specific fields on TL's EXISTING rows that
    # differ from TL_BDF/TL_LEVELS above (VerticalGrammar,
    # VerticalGrammarStaggered, MaxBldgHeight, RoofData, Levels.Size). All
    # are re-applied unconditionally -- idempotent, since TL_BDF/TL_LEVELS
    # already hold their correct values -- so the patch block stays
    # self-contained rather than relying on a prior run having landed them.
    # TL's Modules rows are replaced wholesale (old TL rows dropped, fresh
    # ones appended); Props carries no TL rows and Levels/BDF are patched in
    # place, so nothing is duplicated.
    items = dup.get_editor_property("data").get_editor_property("tagged_data")
    patched_bdf = False
    patched_levels = 0
    patched_modules = 0
    for it in items:
        tags = [str(t) for t in it.get_editor_property("tags")]
        d = it.get_editor_property("data").get_editor_property("data")
        if d is None:
            continue
        md = d.mutable_metadata()

        if "BDF" in tags and "BDFData" in tags:
            pts = list(d.get_points())
            new_pts = []
            for pt in pts:
                bt = MA.get_string_attribute(pt, md, "BuildingToken")
                if bt == "TL":
                    pt = MA.set_float_attribute(
                        pt, md, "MaxBldgHeight", TL_BDF["MaxBldgHeight"])
                    pt = MA.set_vector4_attribute(
                        pt, md, "RoofData", TL_BDF["RoofData"])
                    pt = MA.set_string_attribute(
                        pt, md, "VerticalGrammar", TL_BDF["VerticalGrammar"])
                    pt = MA.set_string_attribute(
                        pt, md, "VerticalGrammarStaggered",
                        TL_BDF["VerticalGrammarStaggered"])
                    patched_bdf = True
                new_pts.append(pt)
            d.set_points(new_pts)
            R["groups"].append({"tags": tuple(sorted(tags)),
                                "patched_maxbldgheight_roofdata_grammar": patched_bdf,
                                "total": len(d.get_points())})

        elif "Levels" in tags:
            # Levels.BuildingToken is NAME-typed (not String -- see the
            # dual-getter proof in the verify block / levels_lh checks
            # elsewhere in this script), so TL rows must be matched with
            # get_name_attribute here, not get_string_attribute.
            pts = list(d.get_points())
            new_pts = []
            heights = {r["LevelNumber"]: r["LevelHeight"] for r in TL_LEVELS}
            for pt in pts:
                bt = str(MA.get_name_attribute(pt, md, "BuildingToken"))
                if bt == "TL":
                    lh = heights[MA.get_integer32_attribute(pt, md, "LevelNumber")]
                    pt = MA.set_float_attribute(pt, md, "LevelHeight", lh)
                    pt = MA.set_float_attribute(pt, md, "Size", lh)
                    patched_levels += 1
                new_pts.append(pt)
            d.set_points(new_pts)
            R["groups"].append({"tags": tuple(sorted(tags)),
                                "patched_levels_size_rows": patched_levels,
                                "total": len(d.get_points())})

        elif "Modules" in tags:
            # TL's module rows are rebuilt wholesale: drop them, append fresh.
            types = discover_types(md)
            kept = [pt for pt in d.get_points()
                    if MA.get_string_attribute(pt, md, "BuildingToken") != "TL"]
            fresh = [mk_pt(md, row, types)
                     for row in tl_modules(level0_of(d, md, types))]
            d.set_points(kept + fresh)
            patched_modules = len(fresh)
            R["groups"].append({"tags": tuple(sorted(tags)),
                                "replaced_tl_module_rows": patched_modules,
                                "total": len(d.get_points())})

    R["patched"] = patched_bdf and patched_levels == 4 and patched_modules > 0
    if not R["patched"]:
        R["errors"].append(
            "patch_mode: expected to patch 1 BDF row, 4 Levels rows and the TL "
            "Modules rows, got patched_bdf=%s patched_levels=%d "
            "patched_modules=%d -- aborting the save rather than writing a "
            "half-patched asset." % (patched_bdf, patched_levels, patched_modules))
    else:
        # NEW FINDING (2026-10-01): in patch_mode, save_loaded_asset(dup)
        # reported no error but the .uasset on disk did NOT get a fresh
        # mtime (measured via a throwaway probe: disk_mtime stayed at the
        # Sep-29 value after a save_loaded_asset-only path, then changed only after
        # an explicit EAL.save_asset(DEST, only_if_is_dirty=False) call, and
        # a fresh load confirmed TL's MaxBldgHeight=200000.0 only after
        # that). save_asset is the one proven (measured, not assumed) to
        # actually flush to disk here; use it instead of/alongside
        # save_loaded_asset in patch_mode.
        try:
            R["saved"] = EAL.save_loaded_asset(dup)
        except Exception as e:
            R["errors"].append("save (patch_mode): %s: %s" % (type(e).__name__, e))
        try:
            R["saved_to_disk"] = EAL.save_asset(DEST, only_if_is_dirty=False)
        except Exception as e:
            R["errors"].append("save_asset (patch_mode): %s: %s" % (type(e).__name__, e))
elif dup:
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
            new_rows = tl_modules(level0_of(d, md, discover_types(md)))
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

    # Skip the save on a half-built asset, and use save_asset -- the call
    # proven (traps.md item 39) to actually flush to disk here, the same one
    # the patch path uses -- rather than save_loaded_asset alone.
    if R["errors"]:
        R["saved"] = False
        R["errors"].append("full rebuild: skipping save because errors is non-empty")
    else:
        try:
            R["saved"] = EAL.save_asset(DEST, only_if_is_dirty=False)
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

        # Consistency check for TL's BDF constraint fields: confirms TL's
        # MinWallWidth/MinBldgHeight/MaxBldgHeight read back as real non-zero
        # centimetre-scale values via the type-matched MA.get_float_attribute
        # (a mismatched getter returns a silent 0.0 sentinel instead of
        # raising -- confirm the type with get_attributes() first).
        # non_zero_rows lists every row whose three fields aren't all 0.0,
        # i.e. every real row. "span" (MaxBldgHeight - MinBldgHeight) is
        # reported per row so the report can show TL has a positive span
        # like every sibling.
        #
        # roofdata_check reads RoofData for TL, CHA, and CHF side by side
        # with the type-matched get_vector4_attribute, so the report can show
        # TL's value is centimetre-scale like its siblings.
        #
        # grammar_check reads VerticalGrammar and VerticalGrammarStaggered
        # for TL, CHA, CHF, and CHJ (TL's closest structural analogue) side
        # by side with get_string_attribute, so the report can show TL's
        # grammar contains a `*` repeat marker like every sibling.
        if "BDF" in tg:
            bad = []
            roofdata = {}
            grammar = {}
            for pt in d.get_points():
                bt = MA.get_string_attribute(pt, md, "BuildingToken")
                vals = {nm: MA.get_float_attribute(pt, md, nm) for nm in
                         ("MinWallWidth", "MinBldgHeight", "MaxBldgHeight")}
                if any(v != 0.0 for v in vals.values()):
                    bad.append({"BuildingToken": bt,
                                "span": vals["MaxBldgHeight"] - vals["MinBldgHeight"],
                                **vals})
                if bt in ("TL", "CHA", "CHF"):
                    try:
                        rd = MA.get_vector4_attribute(pt, md, "RoofData")
                        roofdata[bt] = [rd.x, rd.y, rd.z, rd.w]
                    except Exception as e:
                        roofdata[bt] = "ERROR: %s" % e
                if bt in ("TL", "CHA", "CHF", "CHJ"):
                    try:
                        vg = MA.get_string_attribute(pt, md, "VerticalGrammar")
                        vgs = MA.get_string_attribute(
                            pt, md, "VerticalGrammarStaggered")
                        grammar[bt] = {
                            "VerticalGrammar": vg,
                            "VerticalGrammarStaggered": vgs,
                            "has_star": "*" in vg,
                        }
                    except Exception as e:
                        grammar[bt] = "ERROR: %s" % e
            ver["bdf_min_max_all_zero_check"] = {
                "rows_checked": len(d.get_points()),
                "non_zero_rows": bad,
            }
            ver["roofdata_check"] = roofdata
            ver["grammar_check"] = grammar

        # Consistency check for Levels.LevelHeight: confirms TL's 4 rows read
        # back as real centimetre-scale values (500.0/500.0/300.0/300.0)
        # matching every sibling's unit convention (e.g. CHA LV1 = 500.0),
        # via the type-matched get_float_attribute. cha_lh is captured
        # alongside tl_lh so the report can show both side by side.
        #
        # size_check reads Size alongside LevelHeight for TL, CHA, and CHF so
        # the report can show Size mirrors LevelHeight on TL's rows
        # (500/500/300/300) the same way it does on every sibling.
        if "Levels" in tg:
            all_lh = [MA.get_float_attribute(pt, md, "LevelHeight")
                      for pt in d.get_points()]
            tl_lh = [MA.get_float_attribute(pt, md, "LevelHeight")
                     for pt in d.get_points()
                     if str(MA.get_name_attribute(pt, md, "BuildingToken")) == "TL"]
            cha_lh = [
                {"LevelToken": MA.get_string_attribute(pt, md, "LevelToken"),
                 "LevelHeight": MA.get_float_attribute(pt, md, "LevelHeight")}
                for pt in d.get_points()
                if str(MA.get_name_attribute(pt, md, "BuildingToken")) == "CHA"
            ]
            ver["levels_levelheight_check"] = {
                "rows_checked": len(all_lh),
                "non_zero_count_all": sum(1 for v in all_lh if v != 0.0),
                "tl_rows_levelheight": tl_lh,
                "cha_rows_levelheight": cha_lh,
            }
            size_rows = {}
            for bt_want in ("TL", "CHA", "CHF"):
                rows = []
                for pt in d.get_points():
                    bt = str(MA.get_name_attribute(pt, md, "BuildingToken"))
                    if bt == bt_want:
                        rows.append({
                            "LevelToken": MA.get_string_attribute(pt, md, "LevelToken"),
                            "LevelHeight": MA.get_float_attribute(pt, md, "LevelHeight"),
                            "Size": MA.get_float_attribute(pt, md, "Size"),
                        })
                size_rows[bt_want] = rows
            ver["size_check"] = size_rows

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
