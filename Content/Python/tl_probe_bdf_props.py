# tl_probe_bdf_props.py -- READ-ONLY. Schema and sample rows of BDF_WithTL's
# Props group, the Modules rows that carry props, and which Levels grammars
# use the half-corner symbols. Args: {"token": "CHA", "limit": 12}
import json

args = mcp_args or {}
ASSET = args.get("asset", "/Game/PCG/DataAssets/BDF/BDF_WithTL")
TOKEN = args.get("token", "CHA")
LIMIT = int(args.get("limit", 12))
MA = unreal.PCGMetadataAccessorHelpers

KIND = {"FLOAT": "float", "DOUBLE": "double", "INTEGER32": "integer32",
        "INTEGER64": "integer64", "VECTOR2": "vector2", "VECTOR": "vector",
        "VECTOR4": "vector4", "QUAT": "quat", "ROTATOR": "rotator",
        "TRANSFORM": "transform", "STRING": "string", "BOOLEAN": "bool",
        "NAME": "name", "SOFT_OBJECT_PATH": "soft_object_path"}


def types_of(md):
    names, ts = md.get_attributes()
    return {str(n): KIND.get(t.name, t.name) for n, t in zip(list(names), list(ts))}


def val(pt, md, nm, kind):
    fn = getattr(MA, "get_%s_attribute" % kind, None)
    if fn is None:
        return "?"
    v = fn(pt, md, nm)
    if hasattr(v, "export_text"):
        return v.export_text()
    return v if isinstance(v, (int, float, bool, str)) else str(v)


def row(pt, md, types):
    out = {nm: val(pt, md, nm, k) for nm, k in types.items()}
    out["$transform"] = pt.transform.export_text() if hasattr(pt.transform, "export_text") else str(pt.transform)
    return out


def main():
    a = unreal.EditorAssetLibrary.load_asset(ASSET)
    R = {}
    for it in a.get_editor_property("data").get_editor_property("tagged_data"):
        tags = [str(t) for t in it.get_editor_property("tags")]
        d = it.get_editor_property("data").get_editor_property("data")
        md = d.mutable_metadata()
        types = types_of(md)
        pts = list(d.get_points())
        key = "+".join(tags)
        rec = {"types": types, "points": len(pts)}
        tk = types.get("BuildingToken")
        if "Props" in tags:
            mine = [p for p in pts if tk and str(val(p, md, "BuildingToken", tk)) == TOKEN]
            rec["token_rows"] = len(mine)
            rec["sample"] = [row(p, md, types) for p in (mine or pts)[:LIMIT]]
            tokens = {}
            for p in pts:
                t = str(val(p, md, "BuildingToken", tk)) if tk else "?"
                tokens[t] = tokens.get(t, 0) + 1
            rec["rows_per_token"] = tokens
            for col in ("GroupType", "Group_Type", "Type", "AnchorType", "Mesh"):
                if col in types:
                    c = {}
                    for p in pts:
                        v = str(val(p, md, col, types[col]))
                        c[v] = c.get(v, 0) + 1
                    rec["distinct_" + col] = dict(sorted(c.items(), key=lambda kv: -kv[1])[:40])
        elif "Modules" in tags:
            withp = [p for p in pts if str(val(p, md, "BuildingToken", tk)) == TOKEN
                     and "HasProps" in types and val(p, md, "HasProps", "bool")]
            rec["token_rows_with_props"] = len(withp)
            rec["sample_with_props"] = [row(p, md, types) for p in withp[:6]]
            hp = {}
            for p in pts:
                t = str(val(p, md, "BuildingToken", tk))
                if val(p, md, "HasProps", "bool"):
                    hp[t] = hp.get(t, 0) + 1
            rec["has_props_per_token"] = hp
        elif "Levels" in tags:
            uses = {}
            for p in pts:
                t = str(val(p, md, "BuildingToken", tk))
                for col in ("F", "F0", "F1", "F2"):
                    g = str(val(p, md, col, "string"))
                    for sym in ("C_SL", "C_SR", "C_IL", "C_IR", "C_CE", "C_CI", "C_E", "C_I", "FC", "LC"):
                        if sym in g:
                            uses.setdefault(sym, set()).add(t)
            rec["symbol_users"] = {k: sorted(v) for k, v in uses.items()}
        elif "BDF" in tags:
            rd = {}
            for p in pts:
                t = str(val(p, md, "BuildingToken", tk))
                rd[t] = val(p, md, "RoofData", "vector4")
            rec["roofdata"] = rd
        R[key] = rec
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
