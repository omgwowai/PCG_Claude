# tl_showcase_read.py -- READ-ONLY. What the showcase building produced:
# instances per mesh grouped into categories (foundation, each storey, props,
# rooftop dressing), the building bounds, and the roof mesh bounds.
import json

LABEL = "TL_Showcase_Building"


def category(name, path):
    if "/Game/Building/TL/" in path:
        for lv in ("L00", "L01", "L02", "L03", "L04"):
            if "_%s_" % lv in name:
                return lv
    if path.startswith("/Game/Prop/BLDG/"):
        return "props"
    return "rooftop"


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = next((a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL), None)
    if vol is None:
        return {"error": "no volume"}
    comp = vol.get_component_by_class(unreal.PCGComponent)
    R = {"generated": bool(comp.get_editor_property("generated")), "cats": {}, "meshes": {}}
    lo, hi = [1e18] * 3, [-1e18] * 3
    zs = {}
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None:
            continue
        n = c.get_instance_count()
        cat = category(sm.get_name(), sm.get_path_name())
        R["cats"][cat] = R["cats"].get(cat, 0) + n
        R["meshes"][sm.get_name()] = R["meshes"].get(sm.get_name(), 0) + n
        for i in range(n):
            p = c.get_instance_transform(i, True).translation
            for k, v in enumerate((p.x, p.y, p.z)):
                lo[k] = min(lo[k], v)
                hi[k] = max(hi[k], v)
            if cat.startswith("L"):
                zs.setdefault(cat, set()).add(round(p.z))
    R["bounds_min"], R["bounds_max"] = lo, hi
    R["storey_z"] = {k: sorted(v)[:12] for k, v in zs.items()}
    R["roofs"] = []
    for dc in vol.get_components_by_class(unreal.DynamicMeshComponent):
        o, e, _ = unreal.SystemLibrary.get_component_bounds(dc)
        R["roofs"].append({"z": [round(o.z - e.z, 1), round(o.z + e.z, 1)],
                           "xy": [round(o.x), round(o.y), round(e.x), round(e.y)]})
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
