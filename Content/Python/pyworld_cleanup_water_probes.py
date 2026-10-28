# pyworld_cleanup_water_probes.py -- deletes the water experiments' leftovers (2026-10-26 probes): the probe material
# /Game/PyPCG/Probe/M_ProbeWater and the unused river material instance /Game/PyPCG/World/MI_PyWorldRiver, each only
# when nothing references it; and any PyWorldProbe_* actor still in the level. Reports what it did.
import json

import unreal

EAL = unreal.EditorAssetLibrary
out = {"deleted": [], "kept": {}, "actors": []}
for path in ("/Game/PyPCG/Probe/M_ProbeWater", "/Game/PyPCG/World/MI_PyWorldRiver"):
    if not EAL.does_asset_exist(path):
        continue
    refs = [str(r) for r in EAL.find_package_referencers_for_asset(path, False)]
    if refs:
        out["kept"][path] = refs
    elif EAL.delete_asset(path):
        out["deleted"].append(path)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for a in eas.get_all_level_actors():
    if str(a.get_actor_label()).startswith("PyWorldProbe_"):
        out["actors"].append(str(a.get_actor_label()))
        eas.destroy_actor(a)
print(json.dumps(out, indent=1))
