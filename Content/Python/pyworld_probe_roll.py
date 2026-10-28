# pyworld_probe_roll.py -- READ-ONLY: which way UE's positive roll tilts a mesh's +Y side (and positive pitch its +X):
# transforms the local points (0, 300, 0) and (300, 0, 0) by a rotator. Prints JSON.
import json

import unreal

out = {}
for name, rot in (("roll+20", unreal.Rotator(20.0, 0.0, 0.0)), ("pitch+20", unreal.Rotator(0.0, 20.0, 0.0)),
                  ("yaw90_roll+20", unreal.Rotator(20.0, 0.0, 90.0))):
    t = unreal.Transform(unreal.Vector(0.0, 0.0, 0.0), rot, unreal.Vector(1.0, 1.0, 1.0))
    py = t.transform_location(unreal.Vector(0.0, 300.0, 0.0))
    px = t.transform_location(unreal.Vector(300.0, 0.0, 0.0))
    out[name] = {"rot": [rot.roll, rot.pitch, rot.yaw], "+Y ->": [round(py.x), round(py.y), round(py.z)],
                 "+X ->": [round(px.x), round(px.y), round(px.z)]}
print(json.dumps(out))
