# tl_probe_graph_edges.py -- READ-ONLY. Dump a PCG graph's nodes and edges so
# the consumers of a given pin can be traced. Args:
#   {"graph": "<asset path>", "focus": "<substring of node name/title/settings class>"}
import json

args = mcp_args or {}
GRAPH = args.get("graph", "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/Assign_CitySampleBuildings_CoreProcess")


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
        try:
            return str(p.get_editor_property("label"))
        except Exception:
            return "?"


def settings_summary(s):
    out = {"class": s.get_class().get_name()}
    for prop in ("asset", "attribute", "attributes", "tag", "tags", "input_source",
                 "target_attribute", "operation", "filter_mode", "selected_tags",
                 "tags_to_filter", "value", "comment", "attribute_name"):
        try:
            v = s.get_editor_property(prop)
        except Exception:
            continue
        txt = v.export_text() if hasattr(v, "export_text") else str(v)
        out[prop] = txt[:200]
    try:
        inst = s.get_editor_property("subgraph_instance")
        if inst is not None:
            sg = inst.get_editor_property("graph")
            out["subgraph"] = sg.get_path_name().split(".")[-1] if sg else None
    except Exception:
        pass
    return out


def main():
    R = {"graph": GRAPH, "nodes": [], "edges": []}
    g = unreal.EditorAssetLibrary.load_asset(GRAPH)
    if g is None:
        R["fatal"] = "not loadable"
        return R
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
        except Exception as e:
            R.setdefault("pin_err", "%s: %s" % (type(e).__name__, e))
            continue
        for p in outs:
            try:
                edges = p.get_editor_property("edges")
            except Exception as e:
                R.setdefault("edge_err", "%s: %s" % (type(e).__name__, e))
                continue
            for e in edges:
                try:
                    ip = e.get_editor_property("input_pin")
                    op = e.get_editor_property("output_pin")
                    # input_pin is the upstream (output side) pin in PCG's naming
                    a, b = (ip, op) if ip.get_outer() == n else (op, ip)
                    R["edges"].append("%s.%s -> %s.%s" % (
                        n.get_name(), pin_label(a), b.get_outer().get_name(), pin_label(b)))
                except Exception as ex:
                    R.setdefault("edge_read_err", "%s: %s" % (type(ex).__name__, ex))
    return R


R = main()
print(json.dumps(R, indent=1, default=str)[:30000])
mcp_result = json.loads(json.dumps(R, default=str))
