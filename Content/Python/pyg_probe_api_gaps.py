# pyg_probe_api_gaps.py -- READ-ONLY. For the properties a Python graph builder
# must write (subgraph parameter overrides, ActorReferences arrays, inline pin
# defaults, node comments/positions, graph user parameters), report whether the
# Python reflection layer exposes them at all, on a loaded official graph.
# Nothing is modified or saved.
import json

GRAPH = "/CitySamplePCG/Levels/PCG/PCG_3_1_4_Lots"


def probe(obj, names):
    out = {}
    for n in names:
        try:
            v = obj.get_editor_property(n)
            txt = v.export_text() if hasattr(v, "export_text") else str(v)
            out[n] = "READ ok: " + txt[:160]
        except Exception as e:
            out[n] = "ERR " + str(e)[:160]
    return out


def main():
    R = {}
    g = unreal.EditorAssetLibrary.load_asset(GRAPH)
    R["graph"] = probe(g, ["user_parameters", "comment_nodes", "extra_editor_nodes"])
    R["graph_methods"] = sorted(m for m in dir(g) if any(k in m for k in
                                ("param", "comment", "node", "edge")))
    byref = None
    inline = None
    for n in g.get_editor_property("nodes"):
        st = n.get_settings()
        cname = st.get_class().get_name()
        if byref is None and cname == "PCGSubgraphSettings":
            inst = st.get_editor_property("subgraph_instance")
            sg = inst.get_editor_property("graph") if inst else None
            if sg and sg.get_name() == "Get_ActorDataByRef":
                byref = (n, st, inst)
        if inline is None and cname == "PCGMetadataMathsSettings":
            inline = (n, st)
    n, st, inst = byref
    R["node"] = probe(n, ["node_title", "node_comment", "position_x", "comment_bubble_visible"])
    R["node_methods"] = sorted(m for m in dir(n) if "position" in m or "title" in m or "comment" in m)
    R["instance"] = probe(inst, ["parameters_overrides", "graph"])
    R["instance_methods"] = sorted(m for m in dir(inst) if not m.startswith("_"))[:80]
    H = unreal.PCGGraphParametersHelpers
    R["helpers"] = sorted(m for m in dir(H) if not m.startswith("_"))
    try:
        R["is_overridden_ActorReferences"] = H.is_overridden(inst, "ActorReferences")
    except Exception as e:
        R["is_overridden_ActorReferences"] = "ERR " + str(e)[:160]
    for getter in ("get_soft_object_path_parameter", "get_string_parameter"):
        try:
            R[getter] = str(getattr(H, getter)(inst, "ActorReferences"))[:200]
        except Exception as e:
            R[getter] = "ERR " + str(e)[:160]
    if inline:
        n2, st2 = inline
        R["maths_settings"] = probe(st2, ["default_values", "DefaultValues"])
        R["maths_methods"] = sorted(m for m in dir(st2) if "default" in m.lower() or "pin" in m.lower())
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
