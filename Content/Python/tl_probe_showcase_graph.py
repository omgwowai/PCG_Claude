# tl_probe_showcase_graph.py -- READ-ONLY. Every subgraph node of the showcase
# building graph with its title, subgraph and the overridden parameter values,
# plus the edges. For the documentation.
import json
import re

GRAPH = "/Game/PCG/TL/PCG_TL_Building_BDF"


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


def main():
    g = unreal.EditorAssetLibrary.load_asset(GRAPH)
    R = {"nodes": [], "edges": [], "graph_params": None}
    try:
        R["graph_params"] = g.get_editor_property("user_parameters").export_text()
    except Exception as e:
        R["graph_params"] = str(e)
    nodes = list(g.get_editor_property("nodes"))
    for n in nodes:
        s = n.get_settings()
        rec = {"name": n.get_name(), "title": title(n), "class": s.get_class().get_name() if s else None}
        try:
            inst = s.get_editor_property("subgraph_instance")
            if inst is not None:
                sg = inst.get_editor_property("graph")
                rec["subgraph"] = sg.get_path_name().split(".")[0] if sg else None
                txt = inst.get_editor_property("parameters_overrides").export_text()
                m = re.search(r"PropertyBag_\w+\((.*)\)\),PropertiesIDsOverridden", txt)
                rec["params"] = m.group(1)[:900] if m else txt[:900]
        except Exception:
            pass
        try:
            rec["property_path"] = str(s.get_editor_property("property_path"))
        except Exception:
            pass
        R["nodes"].append(rec)
        for p in n.get_editor_property("output_pins"):
            for e in p.get_editor_property("edges"):
                ip, op = e.get_editor_property("input_pin"), e.get_editor_property("output_pin")
                a, b = (ip, op) if ip.get_outer() == n else (op, ip)
                R["edges"].append("%s.%s -> %s.%s" % (n.get_name(), pin_label(a),
                                                       b.get_outer().get_name(), pin_label(b)))
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
