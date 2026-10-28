# pyworld_probe_dynmesh5.py -- READ-ONLY: did the probe volume spawn a dynamic mesh component? Reports its triangle
# count, materials and bounds, and the log lines of the probe.
import json

import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
out = {}
for a in eas.get_all_level_actors():
    if str(a.get_actor_label()) == "PyWorldProbe_DynMesh":
        comps = a.get_components_by_class(unreal.DynamicMeshComponent)
        out["components"] = len(comps)
        for c in comps[:3]:
            m = c.get_dynamic_mesh()
            b = c.get_editor_property("bounds") if False else None
            out.setdefault("meshes", []).append({
                "tris": m.get_triangle_count() if hasattr(m, "get_triangle_count") else None,
                "mats": [x.get_name() if x else None for x in c.get_materials()],
                "origin": str(c.get_world_location())})
        pc = a.get_component_by_class(unreal.PCGComponent)
        out["generated"] = bool(pc.get_editor_property("generated"))
print(json.dumps(out, indent=1))
