# pyworld_probe_ribbonmats.py -- swaps the river ribbon probe's material ({"mat": "default"|"stream"|"ocean"}) and
# reports the material's usage flags: a material not flagged for dynamic mesh / Nanite / the vertex factory falls back
# to the default material silently in some cases.
import json

import unreal

MEL = unreal.MaterialEditingLibrary
MATS = {"default": "/Engine/BasicShapes/BasicShapeMaterial", "stream": "/Game/PyPCG/World/M_PyWorldStream",
        "ocean": "/Game/Prop/kit_ocean/Material/MI_ocean", "river": "/Water/Materials/WaterSurface/Water_Material_River"}
args = globals().get("mcp_args") or {}
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
key = args.get("mat", "default")
m = unreal.load_asset(MATS[key])
out = {"mat": key}
base = m.get_base_material()
for u in ("used_with_static_lighting", "used_with_instanced_static_meshes", "used_with_nanite", "used_with_water",
          "used_with_editor_compositing"):
    try:
        out[u] = bool(base.get_editor_property(u))
    except Exception:
        pass
for a in eas.get_all_level_actors():
    if str(a.get_actor_label()).startswith("PyWorldProbe_RiverRibbon"):
        c = a.get_editor_property("dynamic_mesh_component")
        c.set_material(0, m)
        out["set_on"] = str(a.get_actor_label())
print(json.dumps(out))
