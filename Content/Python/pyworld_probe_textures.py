# pyworld_probe_textures.py -- READ-ONLY: load the terrain-layer textures one by one and report size and VT flag.
import json

import unreal

import pyworld_terrain_material as TM

out = {}
paths = sorted({p for spec in TM.LAYERS.values() for p in (spec[0], spec[1], spec[2][0], spec[3][0])})
for p in paths:
    t = unreal.load_asset(p)
    out[p.rsplit("/", 1)[1]] = None if t is None else [t.blueprint_get_size_x(), t.blueprint_get_size_y(),
                                                        bool(t.get_editor_property("virtual_texture_streaming")),
                                                        str(t.get_editor_property("compression_settings"))]
print(json.dumps(out, indent=1))
