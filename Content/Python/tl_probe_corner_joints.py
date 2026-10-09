# tl_probe_corner_joints.py -- READ-ONLY. For one PCG volume (by label): instance
# counts per TL mesh, and for every L01 corner instance the gap to the nearest
# wall end on each wing. A wing whose nearest wall end is more than a few cm away
# (or overlaps) means the corner does not close at that turn angle.
# Args: {"label": "TLPROBE_Hex", "level": "L01", "zmax": 600}
import json
import math

args = mcp_args or {}
LABEL = args.get("label", "TLPROBE_Hex")
LEVEL = args.get("level", "L01")
ZMAX = float(args.get("zmax", 600.0))


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = next((a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL), None)
    if vol is None:
        return {"error": "no volume %s" % LABEL}
    counts, walls, corners = {}, [], []
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None:
            continue
        n = sm.get_name()
        counts[n] = counts.get(n, 0) + c.get_instance_count()
        if "_TL_%s_" % LEVEL not in n:
            continue
        bb = sm.get_bounding_box()
        for i in range(c.get_instance_count()):
            t = c.get_instance_transform(i, True)
            if t.translation.z > ZMAX:
                continue
            short = n.split("_A_")[1].replace("_N1", "")
            if short.startswith("Corner"):
                corners.append((short, t, bb))
            else:
                # the two ends of the run, at the facade plane (local x = 0)
                e0 = t.transform_location(unreal.Vector(0, bb.min.y, 0))
                e1 = t.transform_location(unreal.Vector(0, bb.max.y, 0))
                walls.append((short, e0, e1, t.rotation.rotator().yaw))
    out = []
    for short, t, bb in corners:
        yaw = t.rotation.rotator().yaw
        # wing ends of the kit corner: wing A runs +Y, wing B runs -X (exterior corner)
        ends = {"A(+Y)": t.transform_location(unreal.Vector(0, bb.max.y, 0)),
                "B(-X)": t.transform_location(unreal.Vector(bb.min.x, 0, 0))}
        rec = {"corner": short, "yaw": round(yaw, 1), "at": [round(v) for v in t.translation.to_tuple()[:2]]}
        for k, p in ends.items():
            best = None
            for wn, e0, e1, wyaw in walls:
                for e in (e0, e1):
                    d = math.hypot(e.x - p.x, e.y - p.y)
                    if best is None or d < best[0]:
                        best = (d, wn, round(wyaw, 1))
            rec[k] = {"gap_cm": round(best[0], 1), "wall": best[1], "wall_yaw": best[2]} if best else None
        out.append(rec)
    tl = {k: v for k, v in counts.items() if "_TL_" in k}
    return {"tl_instances": sum(tl.values()), "all_instances": sum(counts.values()),
            "tl_meshes": len(tl), "corners": out}


mcp_result = json.loads(json.dumps(main(), default=str))
