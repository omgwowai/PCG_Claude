# tl_probe_found_corner.py -- READ-ONLY. Around one building corner of the
# showcase building, list every L0 instance (mesh, world pivot, yaw, scale) and
# the world-space bounds of its mesh, so a gap at the foundation corner can be
# traced to the piece responsible. Args: {"at": [x, y], "r": cm}
import json

args = mcp_args or {}
LABEL = "TL_Showcase_Building"


def main():
    at = args.get("at", [3000, -3000])
    r = float(args.get("r", 600))
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = next(a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL)
    out = []
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None or ("_L00_" not in sm.get_name() and "_L01_A_CornerEx" not in sm.get_name()):
            continue
        bb = sm.get_bounding_box()
        for i in range(c.get_instance_count()):
            t = c.get_instance_transform(i, True)
            p = t.translation
            if abs(p.x - at[0]) > r or abs(p.y - at[1]) > r:
                continue
            corners = []
            for x in (bb.min.x, bb.max.x):
                for y in (bb.min.y, bb.max.y):
                    w = t.transform_location(unreal.Vector(x, y, 0))
                    corners.append((round(w.x), round(w.y)))
            xs = [q[0] for q in corners]
            ys = [q[1] for q in corners]
            out.append({"mesh": sm.get_name().replace("SM_BLDG_TL_", ""),
                        "pivot": [round(p.x), round(p.y), round(p.z)],
                        "yaw": round(t.rotation.rotator().yaw),
                        "scale": [round(v, 3) for v in t.scale3d.to_tuple()],
                        "world_x": [min(xs), max(xs)], "world_y": [min(ys), max(ys)]})
    return out


mcp_result = json.loads(json.dumps(main(), default=str))
