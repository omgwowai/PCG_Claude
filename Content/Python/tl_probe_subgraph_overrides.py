# tl_probe_subgraph_overrides.py -- READ-ONLY. For one graph: every subgraph
# node's subgraph path and its parameter overrides (export_text), plus the graph's
# own user parameters. Answers "which value does the caller pass in" questions
# such as RoundSegmentAngles' Precision inside BDF_BuildingFromSpline.
# Args: {"graph": "<asset path>"}
import json

args = mcp_args or {}


def main():
    g = unreal.EditorAssetLibrary.load_asset(args["graph"])
    R = {"user_parameters": None, "subgraphs": []}
    try:
        R["user_parameters"] = g.get_editor_property("user_parameters").export_text()
    except Exception as e:
        R["user_parameters"] = "ERR %s" % e
    for n in g.get_editor_property("nodes"):
        s = n.get_settings()
        try:
            inst = s.get_editor_property("subgraph_instance")
        except Exception:
            continue
        if inst is None:
            continue
        sg = inst.get_editor_property("graph")
        R["subgraphs"].append({
            "node": n.get_name(),
            "subgraph": sg.get_path_name().split(".")[0] if sg else None,
            "overrides": inst.get_editor_property("parameters_overrides").export_text()[:1500]})
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
