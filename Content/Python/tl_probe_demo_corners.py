# tl_probe_demo_corners.py -- READ-ONLY. For a probe volume (by label): every
# corner-mesh instance on the lowest storey, its yaw, and the yaws of the two
# nearest wall instances, so it is clear how the official kit's 90 deg corner
# pieces sit on a footprint whose corners are not 90 deg. A mesh counts as a
# corner when its name contains "Corner" (CitySample) or "Corner" / "_C" (SGD kit).
# Args: {"label": "TLPROBE_CSHex", "zmax": 400}
import json
import math

args = mcp_args or {}


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = next((a for a in eas.get_all_level_actors() if a.get_actor_label() == args["label"]), None)
    if vol is None:
        return {"error": "no volume"}
    zmax = float(args.get("zmax", 400.0))
    origin = vol.get_actor_location()
    counts, corners, walls = {}, [], []
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None:
            continue
        n = sm.get_name()
        counts[n] = counts.get(n, 0) + c.get_instance_count()
        for i in range(c.get_instance_count()):
            t = c.get_instance_transform(i, True)
            if t.translation.z - origin.z > zmax:
                continue
            rec = (n, t.translation, round(t.rotation.rotator().yaw, 1),
                   [round(v, 3) for v in t.scale3d.to_tuple()])
            (corners if "Corner" in n else walls).append(rec)
    out = []
    for n, p, yaw, sc in corners:
        near = sorted(walls, key=lambda w: (w[1].x - p.x) ** 2 + (w[1].y - p.y) ** 2)[:2]
        out.append({"corner": n, "xy": [round(p.x - origin.x), round(p.y - origin.y)], "yaw": yaw,
                    "scale": sc,
                    "nearest_walls": [{"mesh": w[0], "yaw": w[2],
                                       "dist": round(math.hypot(w[1].x - p.x, w[1].y - p.y))}
                                      for w in near]})
    return {"meshes": dict(sorted(counts.items(), key=lambda kv: -kv[1])[:30]),
            "n_corner_instances_low": len(corners), "corners": out[:14]}


mcp_result = json.loads(json.dumps(main(), default=str))
