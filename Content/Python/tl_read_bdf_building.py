# tl_read_bdf_building.py -- READ-ONLY. What the BDF-route TL test building
# produced: instances per mesh (TL modules, foundation, props), the roof
# mesh's Z against the top of the parapet, and spawned actors.
import json

LABEL = "TL_Building_BDF_Volume"


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = next((a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL), None)
    if vol is None:
        return {"error": "no volume"}
    comp = vol.get_component_by_class(unreal.PCGComponent)
    out = {"generated": bool(comp.get_editor_property("generated")), "meshes": {}}
    cats = {"tl_module": 0, "tl_foundation": 0, "prop": 0, "other": 0}
    top_l4, zmin = None, None
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None:
            continue
        n = c.get_instance_count()
        name, path = sm.get_name(), sm.get_path_name()
        out["meshes"][name] = out["meshes"].get(name, 0) + n
        if "/Game/Building/TL/" in path:
            cats["tl_foundation" if "_L00_" in name else "tl_module"] += n
        elif "/Prop/" in path:
            cats["prop"] += n
        else:
            cats["other"] += n
        for i in range(n):
            z = c.get_instance_transform(i, True).translation.z
            if "_L04_A_" in name:
                top_l4 = z if top_l4 is None else max(top_l4, z)
            zmin = z if zmin is None else min(zmin, z)
    out["categories"] = cats
    out["l4_base_z"] = top_l4
    out["l4_top_z"] = None if top_l4 is None else top_l4 + 120.0
    out["lowest_instance_z"] = zmin
    roofs = []
    for dc in vol.get_components_by_class(unreal.DynamicMeshComponent):
        b = dc.get_editor_property("bounds") if False else None
        o, e, _ = unreal.SystemLibrary.get_component_bounds(dc)
        roofs.append({"comp": dc.get_name(), "z_min": round(o.z - e.z, 1),
                      "z_max": round(o.z + e.z, 1), "ext_xy": [round(e.x), round(e.y)]})
    out["roof_dynamic_meshes"] = roofs[:8]
    out["owned_actors"] = [a.get_actor_label() for a in eas.get_all_level_actors()
                           if a.get_attach_parent_actor() == vol][:10]
    return out


mcp_result = json.loads(json.dumps(main(), default=str))
