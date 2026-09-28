# tl_probe_writeroutes.py — find a write route that ACTUALLY works.
#
# Every route the engine probe recommended is blocked by CPF_EditConst:
#   PCGDataAsset.data         VisibleAnywhere -> read-only from Python  FAILED
#   PCGDataCollectionExporter.data  VisibleAnywhere -> read-only       FAILED
#   FPCGDataPtrWrapper.data   VisibleAnywhere -> read-only             FAILED
#
# This enumerates candidate escapes and reports which are real. Cheap: it only
# builds objects in memory, except the last route which writes one test asset.

import json

R = {}
args = mcp_args or {}
transient = unreal.find_package("/Engine/Transient")

# ---------- which helpers even exist? ------------------------------------
try:
    R["has_PythonBPLib"] = hasattr(unreal, "PythonBPLib")
    if hasattr(unreal, "PythonBPLib"):
        R["PythonBPLib_members"] = [m for m in dir(unreal.PythonBPLib)
                                    if not m.startswith("_")][:60]
except Exception as e:
    R["pylib_err"] = type(e).__name__

# ---------- does any object expose a data setter? ------------------------
def callable_members(cls_name):
    cls = getattr(unreal, cls_name, None)
    if cls is None:
        return None
    out = []
    for m in dir(cls):
        if m.startswith("_"):
            continue
        if "data" in m.lower() or "export" in m.lower() or "asset" in m.lower():
            out.append(m)
    return out[:80]

for c in ("PCGDataAsset", "PCGDataCollectionExporter", "PCGAssetExporterUtils",
          "PCGDataFunctionLibrary", "PCGDataCollection"):
    R["members_" + c] = callable_members(c)

# ---------- is the property really editconst, or just named wrong? -------
a = unreal.new_object(unreal.PCGDataAsset, transient, "")
try:
    props = []
    for p in dir(a):
        if p.startswith("_"):
            continue
        try:
            v = a.get_editor_property(p)
            props.append(p)
        except Exception:
            pass
    R["data_asset_readable_props"] = props[:60]
except Exception as e:
    R["props_err"] = "%s: %s" % (type(e).__name__, e)

# is there a duplicate-of-a-live-asset route? DuplicateObject preserves data.
try:
    SRC = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG"
    live = unreal.EditorAssetLibrary.load_asset(SRC)
    R["live_loaded"] = live is not None
    # duplicate it into a new package: this COPIES data without ever setting it
    dup = unreal.EditorAssetLibrary.duplicate_asset(SRC, "/Game/PCGTest/BDF_DupProbe")
    R["duplicate_asset"] = "object" if dup else "None"
    if dup:
        items = dup.get_editor_property("data").get_editor_property("tagged_data")
        R["dup_tagged_count"] = len(items)
        R["dup_groups"] = []
        for it in items:
            d = it.get_editor_property("data").get_editor_property("data")
            R["dup_groups"].append({
                "tags": [str(t) for t in it.get_editor_property("tags")],
                "points": d.get_num_points() if d else 0,
                "class": d.get_class().get_name() if d else None,
            })
except Exception as e:
    R["dup_err"] = "%s: %s" % (type(e).__name__, e)

# ---------- THE key question: can we mutate the DUPLICATED asset's data? --
# If duplicate_asset works, the route is: duplicate Epic's asset, then mutate
# the point data that now belongs to it (its UPCGData subobjects are editable
# because UPCGPointData's members like Points ARE settable).
mut = {}
try:
    dup2 = unreal.EditorAssetLibrary.load_asset("/Game/PCGTest/BDF_DupProbe")
    items = dup2.get_editor_property("data").get_editor_property("tagged_data")
    first = items[0]
    d = first.get_editor_property("data").get_editor_property("data")
    mut["class"] = d.get_class().get_name()
    md = d.mutable_metadata()
    mut["attr_count_before"] = md.get_attribute_count()
    # 1) can we add a brand-new attribute to an existing point set?
    try:
        md.create_string_attribute("TL_ProbeAttr", "hello", False, True)
        mut["create_attr"] = "ok"
    except Exception as e:
        mut["create_attr"] = "%s: %s" % (type(e).__name__, e)
    # 2) can we APPEND points to an existing point set?
    try:
        pts = list(d.get_points())
        mut["points_before"] = len(pts)
        p = unreal.PCGPoint()
        p = unreal.PCGMetadataAccessorHelpers.set_string_attribute(
            p, md, "TL_ProbeAttr", "world")
        pts.append(p)
        d.set_points(pts)
        mut["points_after"] = len(d.get_points())
        mut["append_ok"] = len(d.get_points()) == mut["points_before"] + 1
    except Exception as e:
        mut["append_err"] = "%s: %s" % (type(e).__name__, e)
    # 3) does it survive a save?
    try:
        unreal.EditorAssetLibrary.save_loaded_asset(dup2)
        mut["saved"] = True
    except Exception as e:
        mut["save_err"] = "%s: %s" % (type(e).__name__, e)
except Exception as e:
    mut["fatal"] = "%s: %s" % (type(e).__name__, e)
R["mutate_duplicate"] = mut

# ---------- re-load and confirm persistence ------------------------------
persist = {}
try:
    unreal.EditorAssetLibrary.unload_asset("/Game/PCGTest/BDF_DupProbe")
    again = unreal.EditorAssetLibrary.load_asset("/Game/PCGTest/BDF_DupProbe")
    items = again.get_editor_property("data").get_editor_property("tagged_data")
    d = items[0].get_editor_property("data").get_editor_property("data")
    md = d.mutable_metadata()
    persist["attr_count"] = md.get_attribute_count()
    persist["points"] = d.get_num_points()
    persist["has_new_attr"] = md.bp_has_attribute(unreal.Name("TL_ProbeAttr"))
except Exception as e:
    persist["fatal"] = "%s: %s" % (type(e).__name__, e)
R["persistence"] = persist

# ---------- cleanup ------------------------------------------------------
cl = {}
for path in ("/Game/PCGTest/BDF_DupProbe",):
    try:
        cl[path] = unreal.EditorAssetLibrary.delete_asset(path)
    except Exception as e:
        cl[path] = "%s: %s" % (type(e).__name__, e)
R["cleanup"] = cl

print(json.dumps(R, indent=1, default=str))
mcp_result = R
