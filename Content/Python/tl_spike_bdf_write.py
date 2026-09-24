# tl_spike_bdf_write.py — P0 SPIKE S1/S2 (WRITE half).
#
# Creates a NEW UPCGDataAsset at /Game/PCGTest/BDF_ProbeWrite that MIRRORS the
# existing CitySampleBuildingBDF_Asset_PCG structure, to prove the write path
# works before we ever author TL data.
#
# READ-ONLY with respect to Epic's assets: we never touch the original.
# Run tl_spike_bdf_read.py FIRST (it reports what the structure actually is).

import json

R = {}
args = mcp_args or {}
SRC = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG"
DST_PATH = "/Game/PCGTest/BDF_ProbeWrite"

EAL = unreal.EditorAssetLibrary

# ---------- 1. read the source once --------------------------------------
src = EAL.load_asset(SRC)
R["src_loaded"] = src is not None
if src is None:
    R["fatal"] = "could not load source BDF asset"
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit
R["src_class"] = src.get_class().get_name()

src_coll = src.get_editor_property("data")
src_items = src_coll.get_editor_property("tagged_data")

# ---------- 2. build a fresh collection from the source -------------------
# We re-wrap the SAME UPCGData objects (no duplication) purely to prove the
# exporter writes a collection whose pins survive the round trip.
made = []
for it in src_items:
    pin = it.get_editor_property("pin")
    wrap = it.get_editor_property("data")
    data = wrap.get_editor_property("data")
    tags = it.get_editor_property("tags")
    try:
        td = unreal.PCGDataFunctionLibrary.make_tagged_data(data, set(tags), pin)
        made.append(td)
    except Exception as e:
        R.setdefault("make_errors", []).append("%s: %s" % (type(e).__name__, e))
R["items_rewrapped"] = len(made)

coll = unreal.PCGDataCollection()
coll.set_editor_property("tagged_data", made)

# ---------- 3. exporter -> create_asset -----------------------------------
exporter = None
pkg = None
try:
    transient = unreal.find_package("/Engine/Transient")
    exporter = unreal.new_object(unreal.PCGDataCollectionExporter, transient, "")
    exporter.set_editor_property("data", coll)
    exporter.set_editor_property("asset_description", "TL spike probe")

    params = unreal.PCGAssetExporterParameters()
    params.set_editor_property("open_save_dialog", False)   # default True = modal dialog
    params.set_editor_property("asset_name", "BDF_ProbeWrite")
    params.set_editor_property("asset_path", DST_PATH)
    params.set_editor_property("save_on_export_ended", True)

    pkg = unreal.PCGAssetExporterUtils.create_asset(exporter, params)
    R["create_asset"] = "returned object" if pkg else "None"
except Exception as e:
    R["create_asset_err"] = "%s: %s" % (type(e).__name__, e)

# ---------- 4. verify the new asset round-trips ---------------------------
ver = {}
dst_asset = DST_PATH + "/BDF_ProbeWrite"
ex = EAL.does_asset_exist(dst_asset)
ver["exists"] = ex
if ex:
    a2 = EAL.load_asset(dst_asset)
    ver["class"] = a2.get_class().get_name() if a2 else None
    if a2:
        c2 = a2.get_editor_property("data")
        i2 = c2.get_editor_property("tagged_data")
        ver["tagged_count"] = len(i2)
        pins = {}
        for it in i2:
            p = str(it.get_editor_property("pin"))
            w = it.get_editor_property("data")
            d = w.get_editor_property("data")
            rec = pins.setdefault(p, {"count": 0, "class": None, "points": 0})
            rec["count"] += 1
            if d:
                rec["class"] = d.get_class().get_name()
                try:
                    rec["points"] += d.get_num_points()
                except Exception:
                    pass
        ver["pins"] = pins
        # outer check: data should now be outered to the asset, not transient
        for it in i2[:3]:
            w = it.get_editor_property("data")
            d = w.get_editor_property("data")
            if d:
                ver.setdefault("outers", []).append(d.get_outer().get_name())
R["verify"] = ver

# ---------- 5. cleanup: delete the probe asset ----------------------------
cl = {}
try:
    cl["deleted"] = EAL.delete_asset(dst_asset)
    cl["gone"] = not EAL.does_asset_exist(dst_asset)
except Exception as e:
    cl["err"] = "%s: %s" % (type(e).__name__, e)
R["cleanup"] = cl

print(json.dumps(R, indent=1, default=str))
mcp_result = R
