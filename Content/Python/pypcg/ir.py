"""Graph IR: plain JSON in the shape UPyPCGToolsLibrary.ExportGraphIR writes. No unreal import."""
import json
import os
import re

SCHEMA = 1
IN_NODE = "DefaultInputNode"
OUT_NODE = "DefaultOutputNode"
IO_NODES = (IN_NODE, OUT_NODE)

_QUOTED_PATH = re.compile(r"'([^']+)'$")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def dump(ir, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(ir, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")


def alias_of(path):
    """'/PCGPrimitives/Primitives/Get/Get_ActorData.Get_ActorData' -> 'Get_ActorData'."""
    return path.rsplit("/", 1)[-1].split(".", 1)[0]


def object_path(text):
    """"/Script/PCG.Class'/Pkg.Obj:Sub.X'" -> "/Pkg.Obj:Sub.X"; a bare path comes back unchanged."""
    m = _QUOTED_PATH.search(text)
    return m.group(1) if m else text


def node_refs_to_names(value, graph_path):
    """Replace every object path inside `graph_path` by {"node_ref": <node name>}, recursively.

    A named-reroute usage stores its declaration as the declaration's settings object, e.g.
    ".../PCG_3_1_4_Lots.PCG_3_1_4_Lots:NamedRerouteDeclaration_6.PCGNamedRerouteDeclarationSettings_12".
    Two graphs only compare once those paths are reduced to node names."""
    prefix = graph_path + ":"
    if isinstance(value, str):
        p = object_path(value)
        if graph_path and p.startswith(prefix):
            return {"node_ref": p[len(prefix):].split(".", 1)[0]}
        return value
    if isinstance(value, list):
        return [node_refs_to_names(v, graph_path) for v in value]
    if isinstance(value, dict):
        if set(value) == {"node_ref"}:
            return value
        return {k: node_refs_to_names(v, graph_path) for k, v in value.items()}
    return value
