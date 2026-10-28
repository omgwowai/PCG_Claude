# pyworld_probe_assembly.py -- READ-ONLY: is each tree mesh a Nanite assembly (parts that need r.Nanite.AllowAssemblies)?
import json

import unreal

from pypcg.world import flora

out = {}
for name, s in flora.SPECIES.items():
    if s["layer"] not in ("tree", "shrub"):
        continue
    m = unreal.load_asset(s["meshes"][0].split(".")[0])
    try:
        out[name] = bool(m.is_nanite_assembly())
    except Exception as ex:
        out[name] = str(ex)[:80]
print(json.dumps(out))
