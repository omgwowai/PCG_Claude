# tl_probe_namesonly.py -- READ-ONLY. Dump CitySampleBuildingBDF_NamesOnly_PCG:
# its tag groups, attribute names/types, point count, and the token values,
# to test whether style selection draws from a names list that lacks TL.
import json

SRC = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_NamesOnly_PCG"
LOAD = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/LoadCitySampleData"


def main():
    R = {"groups": []}
    EAL = unreal.EditorAssetLibrary
    MA = unreal.PCGMetadataAccessorHelpers
    a = EAL.load_asset(SRC)
    if a is None:
        R["fatal"] = "NamesOnly not loadable"
        return R
    R["class"] = a.get_class().get_name()
    for it in a.get_editor_property("data").get_editor_property("tagged_data"):
        tags = [str(t) for t in it.get_editor_property("tags")]
        d = it.get_editor_property("data").get_editor_property("data")
        rec = {"tags": tags, "data_class": d.get_class().get_name() if d else None,
               "pin": str(it.get_editor_property("pin"))}
        if d is not None and hasattr(d, "get_points"):
            md = d.mutable_metadata()
            names, types = md.get_attributes()
            rec["attrs"] = {str(n): str(t) for n, t in zip(names, types)}
            pts = d.get_points()
            rec["points"] = len(pts)
            vals = []
            for pt in pts:
                row = {}
                for n, t in zip(names, types):
                    n = str(n)
                    ts = str(t)
                    try:
                        if "STRING" in ts:
                            row[n] = MA.get_string_attribute(pt, md, n)
                        elif "NAME" in ts:
                            row[n] = str(MA.get_name_attribute(pt, md, n))
                        elif "FLOAT" in ts:
                            row[n] = MA.get_float_attribute(pt, md, n)
                        elif "DOUBLE" in ts:
                            row[n] = MA.get_double_attribute(pt, md, n)
                        elif "INTEGER32" in ts:
                            row[n] = MA.get_integer32_attribute(pt, md, n)
                    except Exception as e:
                        row[n] = "<%s>" % type(e).__name__
                vals.append(row)
            rec["rows"] = vals[:40]
        elif d is not None:
            # param data: read via its metadata domain if exposed
            try:
                md = d.mutable_metadata()
                names, types = md.get_attributes()
                rec["attrs"] = {str(n): str(t) for n, t in zip(names, types)}
            except Exception as e:
                rec["attrs_err"] = "%s: %s" % (type(e).__name__, e)
            try:
                rec["export_excerpt"] = d.export_text()[:600] if hasattr(d, "export_text") else None
            except Exception:
                pass
        R["groups"].append(rec)

    lg = EAL.load_asset(LOAD)
    loads = []
    for n in lg.get_editor_property("nodes"):
        s = n.get_settings()
        if s is not None and s.get_class().get_name() == "PCGLoadDataAssetSettings":
            loads.append({"node": n.get_name(), "asset": str(s.get_editor_property("asset"))})
    R["LoadCitySampleData_loads"] = loads
    return R


R = main()
print(json.dumps(R, indent=1, default=str)[:12000])
mcp_result = json.loads(json.dumps(R, default=str))
