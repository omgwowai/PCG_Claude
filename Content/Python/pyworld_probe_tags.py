import gc
import json

import unreal

# pyworld_probe_tags.py -- READ ONLY. What Get_ActorData does to the tags of the data it reads (its DeleteTags
# node), and the mode / selector of its DataFromActor node: can a stage read another stage volume's output by tag?


def run():
    from pypcg import extract
    ir = extract.export_path("/PCGPrimitives/Primitives/Get/Get_ActorData")
    out = {"nodes": []}
    for n in ir["nodes"]:
        out["nodes"].append({"name": n["name"], "class": n["class"], "settings": n.get("settings"),
                             "inputs": [[p["label"], p["edges"]] for p in n.get("inputs", []) if p["edges"]]})
    return out


mcp_result = json.loads(json.dumps(run(), default=str))
gc.collect()
