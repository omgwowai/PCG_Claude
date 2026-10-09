# tl_city_tl_summary.py -- READ-ONLY. TL in the current level's buildings
# stage output: module / foundation instances, TL prop instances (props sitting
# on a TL module), and the per-style totals for the other styles as a sanity
# check that they are unchanged.
import json
import re

PROP_ROOT = "/Game/Prop/BLDG/"


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    total, tl_mod, tl_found, per_style = 0, 0, 0, {}
    tl_pts, props = [], {}
    tl_meshes = {}
    for a in eas.get_all_level_actors():
        if "PCG_3_3_1_Buildings" not in a.get_actor_label():
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            if sm is None:
                continue
            n = c.get_instance_count()
            total += n
            path, name = sm.get_path_name(), sm.get_name()
            if "/Game/Building/TL/" in path:
                tl_meshes[name] = tl_meshes.get(name, 0) + n
                if "_L00_" in name:
                    tl_found += n
                else:
                    tl_mod += n
                    if "_L01_" in name:
                        for i in range(n):
                            p = c.get_instance_transform(i, True).translation
                            tl_pts.append((p.x, p.y))
            elif path.startswith(PROP_ROOT):
                props.setdefault(name, []).extend(
                    c.get_instance_transform(i, True).translation for i in range(n))
            else:
                m = re.match(r"SM_BLDG_([A-Z]+)", name)
                if m:
                    per_style[m.group(1)] = per_style.get(m.group(1), 0) + n
    grid = {}
    for x, y in tl_pts:
        grid.setdefault((int(x // 600), int(y // 600)), True)
    on_tl = {}
    for name, ps in props.items():
        k = sum(1 for p in ps if (int(p.x // 600), int(p.y // 600)) in grid)
        if k:
            on_tl[name] = k
    return {"total": total, "tl_modules": tl_mod, "tl_foundation": tl_found,
            "tl_distinct_meshes": len(tl_meshes),
            "props_near_tl_ground_floor": on_tl, "per_style": per_style}


mcp_result = json.loads(json.dumps(main(), default=str))
