# pyworld_probe_descriptor.py -- READ-ONLY: the full MeshSelectorParameters of W7's "Spawn Rocks" node (the in-memory
# graph after a build), written to Content/Python/pypcg/world/ism_descriptor.json minus the values graphs.py sets.
import json
import os

import unreal

from pypcg import world as W

g = unreal.load_asset(W.asset(7))
ir = json.loads(unreal.PyPCGToolsLibrary.export_graph_ir(g))
node = next(n for n in ir["nodes"] if n.get("title") == "Spawn Rocks")
td = node["settings"]["MeshSelectorParameters"]["TemplateDescriptor"]
path = os.path.join(os.path.dirname(W.__file__), "ism_descriptor.json")
with open(path, "w") as fh:
    json.dump(td, fh, indent=1, sort_keys=True)
print(len(td), path)
