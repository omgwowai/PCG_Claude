# pyworld_probe_mpd.py -- READ-ONLY: which property of the mesh partition definition holds the terrain material.
import json

import unreal

PATH = "/PCGPrimitives_MeshPartitionInterop/Assets/MeshPartitionDefinitions/MPD_Basic"
m = unreal.load_asset(PATH)
out = {"class": m.get_class().get_name()}
cls = m.get_class()
names = []
for n in ("material", "terrain_material", "default_material", "mesh_material", "materials", "channels",
          "channel_definitions", "material_channels", "surface_material", "render_material", "landscape_material"):
    try:
        v = m.get_editor_property(n)
        out[n] = v.get_path_name() if isinstance(v, unreal.Object) else str(v)[:800]
    except Exception as ex:
        names.append(n)
out["missing"] = names
try:
    out["export"] = unreal.PyPCGToolsLibrary.export_object_properties(m)[:3000]
except Exception as ex:
    out["export_err"] = str(ex)[:200]
print(json.dumps(out, indent=1))
