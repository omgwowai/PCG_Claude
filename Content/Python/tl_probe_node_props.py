# tl_probe_node_props.py -- READ-ONLY. Dump every Python-visible property of the
# settings of chosen nodes in a PCG graph, plus the edges into and out of them.
# Args: {"graph": "<asset path>", "nodes": ["AttributeStringOp_3", ...]}
import json

args = mcp_args or {}
GRAPH = args.get("graph", "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/BDF_BuildingFromSpline")
WANT = set(args.get("nodes", []))


def txt(v, depth=0):
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    if hasattr(v, "export_text"):
        try:
            return v.export_text()[:600]
        except Exception:
            pass
    if isinstance(v, (list, tuple)) or hasattr(v, "__iter__") and not isinstance(v, unreal.Object):
        try:
            return [txt(x, depth + 1) for x in list(v)[:40]]
        except Exception:
            pass
    if isinstance(v, unreal.Object):
        return v.get_path_name()
    return str(v)[:600]


def props(obj):
    out = {}
    for nm in dir(obj):
        if nm.startswith("_"):
            continue
        try:
            v = getattr(obj, nm)
        except Exception:
            continue
        if callable(v):
            continue
        out[nm] = txt(v)
    return out


def main():
    g = unreal.EditorAssetLibrary.load_asset(GRAPH)
    nodes = list(g.get_editor_property("nodes"))
    R = {}
    for n in nodes:
        if n.get_name() not in WANT:
            continue
        s = n.get_settings()
        R[n.get_name()] = {"class": s.get_class().get_name(), "props": props(s)}
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
