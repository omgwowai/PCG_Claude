# tl_probe_tl_site.py -- READ-ONLY. Locate TL buildings in the city output and
# return one good viewing spot: the TL cluster with the most entrance bays,
# with its bounds and a corner exterior corner instance.
import json


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    pts = []
    corners = []
    for a in eas.get_all_level_actors():
        if "PCG_3_3_1_Buildings" not in a.get_actor_label():
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            path = sm.get_path_name() if sm else ""
            if "/Game/Building/TL/" not in path:
                continue
            for i in range(c.get_instance_count()):
                t = c.get_instance_transform(i, True)
                p = t.translation
                pts.append((p.x, p.y, p.z))
                if "_L01_A_CornerEx_01" in path:
                    corners.append((p.x, p.y, p.z, round(t.rotation.rotator().yaw)))
    cells = {}
    for x, y, z in pts:
        cells.setdefault((int(x // 5000), int(y // 5000)), []).append((x, y, z))
    best = max(cells.values(), key=len)
    xs, ys, zs = zip(*best)
    box = {"min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)], "n": len(best)}
    near = [c for c in corners if box["min"][0] - 1 <= c[0] <= box["max"][0] + 1
            and box["min"][1] - 1 <= c[1] <= box["max"][1] + 1]
    return {"box": box, "corners_in_box": near[:6], "clusters": len(cells)}


mcp_result = json.loads(json.dumps(main(), default=str))
