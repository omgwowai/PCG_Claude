# tl_probe_style_lists.py -- READ-ONLY. Find exactly where the hardcoded
# style-code lists live in the buildings graphs.
#
# A byte grep of the .uasset files shows comma-separated style lists (none with
# TL) inside PCG_3_3_1_Buildings, Assign_BldgStyles_per_MinWallWidth and
# Filter_Footprints_for_bldgs. Earlier scans read only surface node properties
# and subgraph_override, so this one also reads each subgraph node's
# subgraph_instance parameter overrides and every struct property's export_text.

import json

GRAPHS = [
    "/CitySamplePCG/Levels/PCG/PCG_3_3_1_Buildings",
    "/CitySamplePCG/PCG/Assign_BldgStyles_per_MinWallWidth",
    "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/Filter_Footprints_for_bldgs",
]
CODES = ("CHA", "CHJ", "SFC", "NYAA", "QBA")


def looks_like_list(s):
    return "," in s and any(c in s for c in CODES)


def node_label(n):
    for getter in ("get_node_title", ):
        try:
            return str(getattr(n, getter)(unreal.PCGNodeTitleType.FULL_TITLE))
        except Exception:
            pass
    for prop in ("node_title", "title"):
        try:
            v = n.get_editor_property(prop)
            if v:
                return str(v)
        except Exception:
            pass
    return n.get_name()


def scan_graph(path):
    out = {"path": path}
    g = unreal.EditorAssetLibrary.load_asset(path)
    if g is None:
        out["fatal"] = "not loadable"
        return out
    try:
        out["user_params"] = g.get_editor_property("user_parameters").export_text()[:500]
    except Exception as e:
        out["user_params_err"] = "%s: %s" % (type(e).__name__, e)

    helpers = getattr(unreal, "PCGGraphParametersHelpers", None)
    out["has_param_helpers"] = helpers is not None

    hits = []
    subgraphs = []
    for n in g.get_editor_property("nodes"):
        try:
            s = n.get_settings()
        except Exception:
            s = None
        if s is None:
            continue
        cls = s.get_class().get_name()
        label = node_label(n)

        if "Subgraph" in cls:
            rec = {"node": label, "class": cls}
            try:
                inst = s.get_editor_property("subgraph_instance")
            except Exception as e:
                inst = None
                rec["inst_err"] = "%s: %s" % (type(e).__name__, e)
            if inst is not None:
                try:
                    sg = inst.get_editor_property("graph")
                    rec["subgraph"] = sg.get_path_name() if sg else None
                except Exception as e:
                    rec["subgraph_err"] = "%s: %s" % (type(e).__name__, e)
                try:
                    po = inst.get_editor_property("parameters_overrides")
                    txt = po.export_text()
                    rec["overrides_has_list"] = looks_like_list(txt)
                    rec["overrides_excerpt"] = txt[:700]
                except Exception as e:
                    rec["overrides_err"] = "%s: %s" % (type(e).__name__, e)
                if helpers is not None:
                    try:
                        v = helpers.get_string_parameter(inst, "BuildingsStyles")
                        rec["BuildingsStyles"] = v
                        rec["BuildingsStyles_overridden"] = helpers.is_overridden(inst, "BuildingsStyles")
                    except Exception as e:
                        rec["BuildingsStyles_err"] = "%s: %s" % (type(e).__name__, str(e)[:160])
            subgraphs.append(rec)

        for prop in dir(s):
            if prop.startswith("_"):
                continue
            try:
                v = s.get_editor_property(prop)
            except Exception:
                continue
            txt = None
            if hasattr(v, "export_text"):
                try:
                    txt = v.export_text()
                except Exception:
                    txt = None
            if txt is None:
                txt = str(v)
            if looks_like_list(txt):
                hits.append({"node": label, "class": cls, "prop": prop,
                             "has_TL": ",TL" in txt or "TL," in txt,
                             "excerpt": txt[:500]})
    out["subgraph_nodes"] = subgraphs
    out["list_hits"] = hits
    return out


def main():
    return {"graphs": [scan_graph(p) for p in GRAPHS]}


R = main()
print(json.dumps(R, indent=1, default=str)[:20000])
mcp_result = json.loads(json.dumps(R, default=str))
