# tl_probe_graph_dump.py -- READ-ONLY. Write a PCG graph's nodes (with key
# settings) and edges to Saved/graph_dumps/<GraphName>.json and return only a
# summary, so large graphs do not flood the bridge reply.
# Args: {"graphs": ["<asset path>", ...]}
import json
import os

args = mcp_args or {}
GRAPHS = args.get("graphs", [])
OUT_DIR = os.path.join(unreal.Paths.project_saved_dir(), "graph_dumps")

KEYS = ("asset", "attribute", "attributes", "tag", "tags", "input_source", "input_source1",
        "input_source2", "input_source3", "output_target", "target_attribute", "operation",
        "filter_mode", "selected_tags", "tags_to_filter", "value", "comment", "attribute_name",
        "operator", "threshold_attribute", "use_constant_threshold", "attribute_types",
        "mesh_selector_parameters", "static_mesh", "mesh", "offset_min", "offset_max",
        "rotation_min", "rotation_max", "scale_min", "scale_max", "absolute_rotation")


def title(n):
    try:
        t = n.get_editor_property("node_title")
        if t and str(t) != "None":
            return str(t)
    except Exception:
        pass
    return ""


def pin_label(p):
    try:
        return str(p.get_editor_property("properties").get_editor_property("label"))
    except Exception:
        return "?"


def settings_summary(s):
    out = {"class": s.get_class().get_name()}
    for prop in KEYS:
        try:
            v = s.get_editor_property(prop)
        except Exception:
            continue
        txt = v.export_text() if hasattr(v, "export_text") else str(v)
        out[prop] = txt[:400]
    try:
        inst = s.get_editor_property("subgraph_instance")
        if inst is not None:
            sg = inst.get_editor_property("graph")
            out["subgraph"] = sg.get_path_name() if sg else None
    except Exception:
        pass
    try:
        sg = s.get_editor_property("subgraph_override")
        if sg is not None:
            out["subgraph_override"] = sg.get_path_name()
    except Exception:
        pass
    return out


def dump(path):
    g = unreal.EditorAssetLibrary.load_asset(path)
    if g is None:
        return {"graph": path, "fatal": "not loadable"}
    R = {"graph": path, "nodes": [], "edges": [], "comments": []}
    nodes = list(g.get_editor_property("nodes"))
    for extra in ("input_node", "output_node"):
        try:
            nodes.append(g.get_editor_property(extra))
        except Exception:
            pass
    for n in nodes:
        s = None
        try:
            s = n.get_settings()
        except Exception:
            pass
        R["nodes"].append({"name": n.get_name(), "title": title(n),
                           **(settings_summary(s) if s else {})})
        try:
            outs = n.get_editor_property("output_pins")
        except Exception:
            continue
        for p in outs:
            try:
                edges = p.get_editor_property("edges")
            except Exception:
                continue
            for e in edges:
                try:
                    ip = e.get_editor_property("input_pin")
                    op = e.get_editor_property("output_pin")
                    a, b = (ip, op) if ip.get_outer() == n else (op, ip)
                    R["edges"].append("%s.%s -> %s.%s" % (
                        n.get_name(), pin_label(a), b.get_outer().get_name(), pin_label(b)))
                except Exception:
                    continue
    try:
        R["user_parameters"] = g.get_editor_property("user_parameters").export_text()[:4000]
    except Exception:
        pass
    os.makedirs(OUT_DIR, exist_ok=True)
    fn = os.path.join(OUT_DIR, path.rsplit("/", 1)[-1].split(".")[0] + ".json")
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(R, f, indent=1, default=str)
    return {"graph": path, "file": fn, "nodes": len(R["nodes"]), "edges": len(R["edges"])}


mcp_result = json.loads(json.dumps([dump(p) for p in GRAPHS], default=str))
