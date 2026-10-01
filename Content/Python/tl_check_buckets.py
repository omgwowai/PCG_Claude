# tl_check_buckets.py — check the one graph Task 8 never edited.
#
# The original pipeline analysis said Assign_BldgStyles_per_MinWallWidth holds the
# full 27-code list "plus 7 progressively narrower wall-width buckets". Task 8
# edited two DataTables, the BuildingsStyles parameter, and LoadCitySampleData —
# but NEVER this graph. If the buckets are hardcoded style lists inside it and TL
# is absent from them, TL would never be assigned to any lot, which matches the
# observed symptom exactly: zero TL, no error, every other style normal.
#
# READ-ONLY.

import json

R = {}
args = mcp_args or {}
EAL = unreal.EditorAssetLibrary

G = "/CitySamplePCG/PCG/Assign_BldgStyles_per_MinWallWidth"
g = EAL.load_asset(G)
if g is None:
    R["fatal"] = "graph not loadable"
else:
    R["loaded"] = True
    nodes = g.get_editor_property("nodes")
    R["node_count"] = len(nodes)

    # 1. the graph's own user parameters (Task 1 said this bag is empty)
    try:
        txt = g.get_editor_property("user_parameters").export_text()
        R["graph_user_params_excerpt"] = txt[:600]
        R["graph_params_mention_TL"] = ("TL" in txt)
    except Exception as e:
        R["user_params_err"] = "%s: %s" % (type(e).__name__, e)

    # 2. every node's settings, hunting for any style-code string
    hits = []
    node_kinds = {}
    for n in nodes:
        try:
            s = n.get_settings()
        except Exception:
            continue
        if s is None:
            continue
        cls = s.get_class().get_name()
        node_kinds[cls] = node_kinds.get(cls, 0) + 1
        # scan every readable property for a comma-separated style list
        for prop in dir(s):
            if prop.startswith("_"):
                continue
            try:
                v = s.get_editor_property(prop)
            except Exception:
                continue
            sv = str(v)
            if ("CHA" in sv and "," in sv) or ("NYAA" in sv) or ("SFJ" in sv):
                hits.append({
                    "node_class": cls,
                    "param": prop,
                    "mentions_TL": ("TL" in sv.split(",")),
                    "excerpt": sv[:400],
                })
    R["node_kinds"] = node_kinds
    R["style_list_hits"] = hits
    R["hit_count"] = len(hits)

    # 3. subgraph references, and whether any override a parameter
    subs = []
    for n in nodes:
        try:
            s = n.get_settings()
        except Exception:
            continue
        if s is None:
            continue
        if "Subgraph" not in s.get_class().get_name():
            continue
        rec = {"class": s.get_class().get_name()}
        for prop in ("subgraph_override", "subgraph_instance"):
            try:
                v = s.get_editor_property(prop)
                rec[prop] = str(v)[:200]
            except Exception:
                rec[prop] = "<err>"
        subs.append(rec)
    R["subgraph_nodes"] = subs

print(json.dumps(json.loads(json.dumps(R, default=str)), indent=1)[:5000])
mcp_result = json.loads(json.dumps(R, default=str))
