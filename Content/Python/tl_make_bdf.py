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
# SIXTH CONTRADICTION -- correcting the FIFTH. The coordinator re-measured
# with both get_float_attribute and get_double_attribute on the same rows
# (CHA MinWallWidth: 1000.0 vs. 0.0; CHA LV1 LevelHeight: 500.0 vs. 0.0) and
# confirmed the FIFTH CONTRADICTION above: get_double_attribute on a Float
# attribute returns a silent 0.0 sentinel, which is what produced their
# original "every style reads 0.0" premise. That premise is retracted. The
# real defect was different: TL's own MinWallWidth/MinBldgHeight/
# MaxBldgHeight (12.0/5.0/60.0) and LevelHeight (5.0/5.0/3.0/3.0, in
# TL_LEVELS below) were carried over from the .bdf JSON's METRE-scale
# numbers, unconverted, while every sibling style is in CENTIMETRES (CHA's
# MinWallWidth=1000cm=10m, LV1 LevelHeight=500cm=5m). Corrected per the
# coordinator's ruling, derived from TL's own geometry rather than copied
# from CHA's envelope:
#   MinWallWidth  = 950.0  cm -- TL's own narrowest FLengths.x (LV1/LV2/LV3
#                               all start at 950), i.e. the narrowest wall
#                               TL can actually build on.
#   MinBldgHeight = MaxBldgHeight = 1600.0 cm -- TL's full fixed four-level
#                               stack: 500(L0)+500(L1)+300(L2)+300(L3). TL's
#                               grammar does not repeat levels the way CHA's
#                               does, so unlike CHA's wide 3100-10000 range,
#                               TL's min and max legitimately coincide.
#
# EIGHTH CONTRADICTION -- correcting the SIXTH's MaxBldgHeight, after Task 9
# ran the real city pipeline (PCG_3_3_1_Buildings) end to end: 475,728 total
# instances generated, 0 of them TL, while CH/SF/NY/QB all generated
# normally. The coordinator then read all 28 styles' height bands directly
# and found TL is the ONLY one with a zero span (minH=maxH=1600, span=0);
# every other style has a strictly positive span, and 21 of the 28
# (including every CH* and most others) use MaxBldgHeight=200000.0 as a
# shared open-ended sentinel upper bound. The SIXTH's "min and max
# legitimately coincide because TL doesn't repeat levels" reasoning was
# wrong about how this field is actually consumed: it is read as a MATCH
# WINDOW against a requested height, not merely descriptive metadata, and a
# zero-width window is exactly the shape that fails an overlap/normalization
# test and makes a style unselectable. Fix: MaxBldgHeight -> 200000.0,
# matching the dominant (21-of-28) sibling convention, giving TL a positive
# 1600-200000 span with an open-ended top like most of its siblings.
# MinBldgHeight stays 1600.0 (Task 9 independently ruled out MinWallWidth=
# 950.0 as a factor -- 97.33% of 1272 real lots fit it -- so that field is
# untouched here).
#
# THIS IS A HYPOTHESIS, NOT A PROVEN FIX. Neither Task 9 nor the coordinator
# has located the specific node that rejects the degenerate zero-span band --
# Task 9 traced as far as Fill_Areas_WithFittingAssets (plugin content)
# without finding it, and the graph's own MinHeight=1000/MaxHeight=5000
# parameters would NOT reject a 1600 band by simple containment. The
# empirical test is a fresh re-run of the Task 9 city stage, done
# separately and NOT by this script/session, specifically so the
# verification is independent of the agent that made the change.
TL_BDF = {
    "BuildingToken": "TL",
    "VerticalGrammar": "[LV0][LV1][LV2][LV3]",
    "VerticalGrammarStaggered": "[LV0][LV1][LV2][LV3]",
    "MinWallWidth": 950.0,       # cm; TL's own narrowest FLengths.x (was 12.0 m, unconverted)
    "MinBldgHeight": 1600.0,     # cm; TL's fixed 4-level stack (was 5.0 m, unconverted)
    "MaxBldgHeight": 200000.0,   # cm; open-ended sentinel, matching 21/28 siblings (was 1600.0 -- zero span, EIGHTH CONTRADICTION)
    "RoofData": unreal.Vector4(0.2, 0.1, 0.2, 0.1),   # CHA's Roof_Inset/Offset pair
}

# level -> the 3 facade variants (BDF F0/F1/F2) and their required length in cm.
# CHA's own values are the template (spec 2.6 mapping applied).
# LevelHeight is in CENTIMETRES, matching every sibling style (CHA's LV1
# reads 500.0) -- corrected here from the original metre-scale 5.0/5.0/3.0/
# 3.0, the same unit bug as TL_BDF above (SIXTH CONTRADICTION).
TL_LEVELS = [
    {"LevelNumber": 0, "LevelToken": "LV0", "LevelHeight": 500.0, "Size": 0.0,
     "F0": "[FC][FS2]+[LC]", "F1": "[FC][FS2]+[LC]", "F2": "[FC][FS2]+[LC]",
     "FLengths": unreal.Vector(300.0, 300.0, 300.0), "IsTopper": False},
    {"LevelNumber": 1, "LevelToken": "LV1", "LevelHeight": 500.0, "Size": 0.0,
     "F0": "[FC][WS1][W1]+[LC]",
     "F1": "[FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]",
     "F2": "[FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]",
     "FLengths": unreal.Vector(950.0, 3725.0, 5400.0), "IsTopper": False},
    {"LevelNumber": 2, "LevelToken": "LV2", "LevelHeight": 300.0, "Size": 0.0,
     "F0": "[FC][WS1][W1]+[LC]",
     "F1": "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
     "F2": "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
     "FLengths": unreal.Vector(950.0, 3925.0, 5800.0), "IsTopper": False},
    {"LevelNumber": 3, "LevelToken": "LV3", "LevelHeight": 300.0, "Size": 0.0,
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
# SEVENTH CONTRADICTION -- the embedded editor Python interpreter's `globals()`
# namespace is NOT fresh per run_unreal_script call; it persists across runs
# within the same editor session (confirmed with tl_probe_globals.py: a
# second run found DEST/dup/TL_BDF/etc. still bound from the previous run's
# execution of this very script). That is silently dangerous here: if a
# previous run left "dup"/"d"/"md"/"asset"/etc. bound to Python wrappers of
# BDF_WithTL's UObjects, EditorAssetLibrary.delete_asset(DEST) below returns
# False (not an exception) because something still references the object,
# duplicate_asset then produces a stale/no-op result, and everything after it
# silently mutates or reads the OLD asset while this run's own R["groups"]
# stays empty and R["duplicated"] is never true -- exactly what happened on
# a real re-run here: groups: [], duplicated: false, and the verify block
# read back last run's values instead of this run's fix. Clearing the known
# heavy-object globals and forcing GC before delete_asset fixes it.
for _nm in ("dup", "d", "md", "asset", "src_asset", "src_asset2", "bdf_d",
            "d0", "d2", "md0", "md2", "existing", "items", "items2", "it",
            "pt", "last_pt"):
    globals().pop(_nm, None)
import gc as _gc
_gc.collect()
try:
    unreal.SystemLibrary.collect_garbage()
except Exception:
    pass

_patch_mode = False
if EAL.does_asset_exist(DEST):
    _deleted = EAL.delete_asset(DEST)
    if not _deleted and EAL.does_asset_exist(DEST):
        R["errors"].append(
            "delete_asset(%s) returned False and the asset still exists -- "
            "a stale Python reference from a previous run in this same "
            "editor session is the most likely cause; see the comment "
            "above this block." % DEST)

        # NEW FINDING (2026-10-01, EIGHTH CONTRADICTION re-run) -- the
        # delete can ALSO fail for a completely different reason than the
        # stale-Python-globals bug documented above: a genuine engine-level
        # referencer. tl_probe_referencers.py found BDF_WithTL has a live
        # referencer, /CitySamplePCG/.../Subgraphs/LoadCitySampleData, with
        # the editor's current world still L_CitySamplePCG_Demo -- almost
        # certainly left wired up by Task 9's own city-pipeline test run.
        # ForceDeleteObject then logs "this package is now potentially
        # corrupt" and the subsequent duplicate_asset fails because the
        # (undeleted) destination still exists. Retrying delete does not
        # help, because the referencer is real, not stale.
        #
        # Rather than force-delete an asset something else now legitimately
        # points at (risking corrupting that referencer, per the engine's
        # own warning), fall back to PATCHING THE EXISTING DEST ASSET IN
        # PLACE: load it directly (no delete, no duplicate, no re-append of
        # rows that are already there from the prior successful build) and
        # mutate only the one field this round actually changed --
        # BDF.MaxBldgHeight on TL's existing row. This is strictly narrower
        # than the normal full-rebuild path below and is only taken when
        # delete_asset has demonstrably failed with DEST still present.
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
    # Narrow patch: touch only the BDF group's existing TL row's
    # MaxBldgHeight. Do not re-append rows to Levels/Modules/Props -- they
    # are already correct from the prior successful full build, and
    # re-appending here (without the delete+duplicate reset) would duplicate
    # them.
    items = dup.get_editor_property("data").get_editor_property("tagged_data")
    patched = False
    for it in items:
        tags = [str(t) for t in it.get_editor_property("tags")]
        if "BDF" in tags and "BDFData" in tags:
            d = it.get_editor_property("data").get_editor_property("data")
            if d is None:
                continue
            md = d.mutable_metadata()
            pts = list(d.get_points())
            new_pts = []
            for pt in pts:
                bt = MA.get_string_attribute(pt, md, "BuildingToken")
                if bt == "TL":
                    pt = MA.set_float_attribute(
                        pt, md, "MaxBldgHeight", TL_BDF["MaxBldgHeight"])
                    patched = True
                new_pts.append(pt)
            d.set_points(new_pts)
            R["groups"].append({"tags": tuple(sorted(tags)),
                                "patched_maxbldgheight": patched,
                                "total": len(d.get_points())})
    R["patched"] = patched
    if not patched:
        R["errors"].append(
            "patch_mode: no existing TL row found in the BDF group to patch "
            "-- DEST exists but doesn't have the TL row this script expects; "
            "aborting the save rather than writing a half-patched asset.")
    else:
        # NEW FINDING (2026-10-01): in patch_mode, save_loaded_asset(dup)
        # reported no error but the .uasset on disk did NOT get a fresh
        # mtime (tl_probe_save_state.py: disk_mtime stayed at the Sep-29
        # value after a save_loaded_asset-only path, then changed only after
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

        # Consistency check for TL's BDF constraint fields, added when the
        # coordinator's original "these fields are vestigial, set TL to 0.0"
        # ruling was tested and retracted (see the SIXTH CONTRADICTION note
        # above TL_BDF). The retraction's root cause: the ruling's probe used
        # get_double_attribute on a Float-typed attribute, which returns a
        # silent 0.0 sentinel instead of raising -- the same sentinel-default
        # trap this file already documents for get_name_attribute et al.
        # Measured here with MA.get_float_attribute, the type-matched getter
        # confirmed via get_attributes(). non_zero_rows lists every row whose
        # three fields aren't all 0.0 -- i.e. every real row, TL included now
        # that it carries its own geometry-derived values (950.0/200000.0 cm,
        # EIGHTH CONTRADICTION) rather than the unconverted metre-scale
        # 12.0/5.0/60.0, the since-retracted 0.0/0.0/0.0, or the zero-span
        # 950.0/1600.0/1600.0 that Task 9 showed makes TL unselectable.
        # "span" (MaxBldgHeight - MinBldgHeight) is reported per row so the
        # report can show TL now has a positive span like every sibling,
        # rather than the degenerate 0 the EIGHTH CONTRADICTION fixes.
        if "BDF" in tg:
            bad = []
            for pt in d.get_points():
                bt = MA.get_string_attribute(pt, md, "BuildingToken")
                vals = {nm: MA.get_float_attribute(pt, md, nm) for nm in
                         ("MinWallWidth", "MinBldgHeight", "MaxBldgHeight")}
                if any(v != 0.0 for v in vals.values()):
                    bad.append({"BuildingToken": bt,
                                "span": vals["MaxBldgHeight"] - vals["MinBldgHeight"],
                                **vals})
            ver["bdf_min_max_all_zero_check"] = {
                "rows_checked": len(d.get_points()),
                "non_zero_rows": bad,
            }

        # Consistency check for Levels.LevelHeight, added for the same reason
        # as bdf_min_max_all_zero_check above: the coordinator's original
        # "LevelHeight is vestigial, reads 0.0 everywhere" claim was also a
        # get_double_attribute-on-Float sentinel artifact, retracted once
        # re-measured with the type-matched get_float_attribute. TL's own 4
        # rows now carry centimetre-scale values (500.0/500.0/300.0/300.0)
        # matching every sibling's unit convention (e.g. CHA LV1 = 500.0),
        # not the metre-scale 5.0/5.0/3.0/3.0 this script originally wrote.
        # cha_lh is captured alongside tl_lh so the report can show both
        # side by side, as requested.
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
