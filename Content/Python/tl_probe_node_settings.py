# tl_probe_node_settings.py -- READ-ONLY. Full export_text() of the settings of
# chosen nodes in one PCG graph (the graph-dump probe keeps only a few keys), plus
# the graph's user parameters. Writes Saved/graph_dumps/<Graph>_settings.json and
# returns only a short summary.
# Args: {"graph": "<asset path>", "nodes": ["AttributeFilter_4", ...]}  ([] = all)
import json
import os

args = mcp_args or {}
GRAPH = args["graph"]
WANT = set(args.get("nodes", []))
OUT_DIR = os.path.join(unreal.Paths.project_saved_dir(), "graph_dumps")


def main():
    g = unreal.EditorAssetLibrary.load_asset(GRAPH)
    out = {"graph": GRAPH, "nodes": {}}
    try:
        out["user_parameters"] = g.get_editor_property("user_parameters").export_text()
    except Exception as e:
        out["user_parameters"] = "ERR %s" % e
    for n in g.get_editor_property("nodes"):
        if WANT and n.get_name() not in WANT:
            continue
        s = n.get_settings()
        if s is None:
            continue
        rec = {"class": s.get_class().get_name()}
        try:
            rec["text"] = unreal.PCGSettings.export_text(s) if hasattr(unreal.PCGSettings, "export_text") else None
        except Exception:
            rec["text"] = None
        if not rec["text"]:
            props = {}
            for p in dir(s):
                if p.startswith("_"):
                    continue
                try:
                    if callable(getattr(s, p, None)):
                        continue
                    v = s.get_editor_property(p)
                except Exception:
                    continue
                try:
                    props[p] = v.export_text() if hasattr(v, "export_text") else str(v)
                except Exception:
                    props[p] = str(v)
            rec["props"] = props
        out["nodes"][n.get_name()] = rec
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, GRAPH.rsplit("/", 1)[-1] + "_settings.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)
    return {"file": path, "n": len(out["nodes"])}


mcp_result = json.loads(json.dumps(main(), default=str))
