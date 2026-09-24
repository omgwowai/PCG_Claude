# tl_spike_bdf_read.py — P0 SPIKE S1/S2 (READ half). READ-ONLY.
#
# Answers U1: what IS the internal schema of CitySampleBuildingBDF_Asset_PCG?
#
# Reports: pin labels, tagged-data count/classes, point counts, available
# metadata-attribute API surface, and (for param data) the actual attribute
# names + a few sample rows. Everything that answers "what does
# BDF_Input_Processor expect" without modifying anything.

import json

R = {}
args = mcp_args or {}

SRC = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG"
NAMES_ONLY = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_NamesOnly_PCG"

EAL = unreal.EditorAssetLibrary

def members(o, limit=200):
    out = []
    for m in dir(o):
        if m.startswith("_"):
            continue
        out.append(m)
    return sorted(out)[:limit]

def dump_one(asset_path):
    """Return a JSON-safe description of a UPCGDataAsset."""
    out = {"path": asset_path}
    a = EAL.load_asset(asset_path)
    out["loaded"] = a is not None
    if a is None:
        return out
    out["class"] = a.get_class().get_name()
    for prop in ("name", "description", "exporter_class", "category"):
        try:
            out[prop] = str(a.get_editor_property(prop))
        except Exception as e:
            out[prop] = "<%s>" % type(e).__name__

    coll = a.get_editor_property("data")
    out["collection_class"] = type(coll).__name__
    items = coll.get_editor_property("tagged_data")
    out["tagged_count"] = len(items)

    entries = []
    for idx, it in enumerate(items):
        rec = {"i": idx}
        try:
            rec["pin"] = str(it.get_editor_property("pin"))
        except Exception as e:
            rec["pin"] = "<%s>" % type(e).__name__
        try:
            rec["tags"] = [str(t) for t in it.get_editor_property("tags")]
        except Exception as e:
            rec["tags"] = "<%s>" % type(e).__name__
        try:
            rec["b_pinless"] = bool(it.get_editor_property("b_pinless_data"))
        except Exception:
            pass

        wrap = it.get_editor_property("data")
        d = wrap.get_editor_property("data")
        rec["data_class"] = d.get_class().get_name() if d else None
        rec["outer"] = d.get_outer().get_name() if d else None

        if d is None:
            entries.append(rec)
            continue

        # point data?
        try:
            rec["num_points"] = d.get_num_points()
        except Exception:
            pass

        # metadata surface
        md = None
        try:
            md = d.mutable_metadata()
            rec["md_class"] = md.get_class().get_name()
        except Exception as e:
            rec["md_err"] = "%s: %s" % (type(e).__name__, e)

        if md is not None:
            # try hard to enumerate attribute names
            names = None
            for getter in ("attributes", "attribute_names"):
                try:
                    v = md.get_editor_property(getter)
                    names = [str(x) for x in v]
                    rec["attr_via"] = getter
                    break
                except Exception:
                    continue
            if names is None:
                # last resort: look for any list-of-name-ish property
                try:
                    keys = [p for p in members(md)]
                    rec["md_members_sample"] = keys
                except Exception as e:
                    rec["md_members_err"] = type(e).__name__
            else:
                rec["attr_names"] = names[:60]
                rec["attr_count"] = len(names)

            try:
                rec["entries_count"] = md.get_item_count_for_child()
            except Exception:
                pass

            # For param data: read first rows via metadata keys
            if rec["data_class"] == "PCGParamData" and names:
                rows = []
                try:
                    for k in range(min(3, int(rec.get("entries_count") or 0))):
                        row = {}
                        for nm in names[:40]:
                            try:
                                v = unreal.PCGMetadataAccessorHelpers.get_string_attribute_by_metadata_key(
                                    k, md, nm)
                                row[nm] = v
                            except Exception:
                                pass
                        rows.append(row)
                except Exception as e:
                    rec["rows_err"] = "%s: %s" % (type(e).__name__, e)
                rec["sample_rows"] = rows

        entries.append(rec)

    out["items"] = entries
    return out

# ---------- run on both database assets ----------------------------------
try:
    R["bdf_asset"] = dump_one(SRC)
except Exception as e:
    R["bdf_asset_fatal"] = "%s: %s" % (type(e).__name__, e)

try:
    R["names_only"] = dump_one(NAMES_ONLY)
except Exception as e:
    R["names_only_fatal"] = "%s: %s" % (type(e).__name__, e)

# ---------- API surface probe: what can PCGMetadata actually do? ---------
try:
    probe = {}
    for cls_name in ("PCGMetadata", "PCGMetadataAccessorHelpers", "PCGDataFunctionLibrary",
                     "PCGAssetExporterUtils", "PCGDataCollectionExporter",
                     "PCGAssetExporterParameters"):
        cls = getattr(unreal, cls_name, None)
        probe[cls_name] = members(cls) if cls else None
    R["api_surface"] = probe
except Exception as e:
    R["api_surface_err"] = "%s: %s" % (type(e).__name__, e)

print(json.dumps(R, indent=1, default=str))
mcp_result = R
