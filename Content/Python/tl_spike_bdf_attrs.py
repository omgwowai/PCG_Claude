# tl_spike_bdf_attrs.py — P0 SPIKE S1/S2 (ATTRIBUTE half). READ-ONLY.
#
# The previous probe found the BDF database is four PCGPointData sets with
# metadata attributes (tags: BDF/Levels/Modules/Props, all on pin "In").
# This probe enumerates the ATTRIBUTE NAMES and dumps the CHA rows, which is
# exactly the schema a new style (TL) must supply.

import json

R = {}
args = mcp_args or {}
SRC = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG"
EAL = unreal.EditorAssetLibrary

a = EAL.load_asset(SRC)
if a is None:
    R["fatal"] = "source not loaded"
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit

coll = a.get_editor_property("data")
items = coll.get_editor_property("tagged_data")

MA = unreal.PCGMetadataAccessorHelpers

def attr_names(md):
    """Enumerate attribute names. get_attributes() is the documented callable."""
    names = []
    try:
        raw = md.get_attributes()
        for x in raw:
            # FPCGAttributeInfo: .name / .type / .id
            try:
                nm = x.get_editor_property("name")
            except Exception:
                nm = getattr(x, "name", None)
            names.append(str(nm) if nm is not None else str(x))
        return names, "get_attributes"
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, e)
    try:
        n = md.get_attribute_count()
        return ["<count=%s>" % n], "get_attribute_count(%s)" % err
    except Exception as e2:
        return [], "both failed: %s / %s" % (err, type(e2).__name__)

def read_point_attrs(pt, md, names):
    row = {}
    for nm in names:
        got = None
        for fn in ("get_string_attribute", "get_name_attribute",
                   "get_double_attribute", "get_integer32_attribute",
                   "get_bool_attribute"):
            try:
                got = getattr(MA, fn)(pt, md, nm)
                break
            except Exception:
                continue
        if got is not None:
            row[nm] = str(got)
    return row

out = {}
for it in items:
    tags = [str(t) for t in it.get_editor_property("tags")]
    wrap = it.get_editor_property("data")
    d = wrap.get_editor_property("data")
    if d is None:
        continue
    key = "+".join(sorted(tags)) or "untagged"
    rec = {"class": d.get_class().get_name(), "tags": tags}

    md = d.mutable_metadata()
    names, how = attr_names(md)
    rec["attr_how"] = how
    rec["attr_count"] = len(names)
    rec["attr_names"] = names[:80]

    # points, if any
    pts = None
    try:
        pts = d.get_points()
        rec["num_points"] = len(pts)
    except Exception as e:
        rec["points_err"] = type(e).__name__

    if pts and names:
        # find the point that looks like CHA (a style code)
        found = None
        for i, pt in enumerate(pts):
            row = read_point_attrs(pt, md, names)
            if any(v == "CHA" for v in row.values()):
                found = (i, row)
                break
        if found is None:
            found = (0, read_point_attrs(pts[0], md, names))
        rec["cha_index"] = found[0]
        rec["cha_row"] = found[1]
        # also dump rows 0 and the last, to see the shape
        rec["row0"] = read_point_attrs(pts[0], md, names)
        if len(pts) > 1:
            rec["row_last"] = read_point_attrs(pts[-1], md, names)

        # point transform / bounds of row0
        try:
            t = pts[0].get_editor_property("transform")
            rec["row0_transform"] = {
                "loc": [t.translation.x, t.translation.y, t.translation.z],
                "scale": [t.scale3d.x, t.scale3d.y, t.scale3d.z],
            }
            rec["row0_bounds_min"] = str(pts[0].get_editor_property("bounds_min"))
            rec["row0_bounds_max"] = str(pts[0].get_editor_property("bounds_max"))
        except Exception as e:
            rec["xform_err"] = type(e).__name__

    out[key] = rec

R["sets"] = out

# also: which style codes appear in the BDF set?
try:
    bdfkey = [k for k in out if "BDF" in k and "BDFData" in k]
    if bdfkey:
        rec = out[bdfkey[0]]
        if rec.get("num_points") and rec.get("attr_names"):
            d = None
            for it in items:
                tg = [str(t) for t in it.get_editor_property("tags")]
                if "BDF" in tg and len(tg) >= 2:
                    d = it.get_editor_property("data").get_editor_property("data")
                    break
            if d:
                md = d.mutable_metadata()
                pts = d.get_points()
                codes = []
                for pt in pts:
                    row = read_point_attrs(pt, md, rec["attr_names"])
                    cand = [v for v in row.values() if len(v) <= 8 and v.isupper()]
                    codes.append(cand[0] if cand else "?")
                R["style_codes_in_bdf_set"] = sorted(set(codes))
                R["style_code_count"] = len(set(codes))
except Exception as e:
    R["codes_err"] = "%s: %s" % (type(e).__name__, e)

print(json.dumps(R, indent=1, default=str))
mcp_result = R
