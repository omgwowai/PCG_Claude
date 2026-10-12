# tl_probe_demo_joints.py -- READ-ONLY. Corner joint gaps on a probe volume's
# lowest storey, for both official corner conventions:
#   * CitySample 90 deg corner pieces ("CornerEx" in the name): wing A ends at
#     local (0, max.y), wing B at local (min.x, 0); each wing end is matched to
#     the nearest wall end (local (0, min.y) / (0, max.y) of a non-corner piece).
#   * PCGPrimitives half corners ("CornerLeft" / "CornerRight"): each half's two
#     facade-edge ends (0, min.y) / (0, max.y); the end nearest another corner
#     instance is matched to that instance's nearest end (the partner half).
# Args: {"label": "TLPROBE_CSHex", "zmax": 400}
import json
import math

args = mcp_args or {}


def ends(t, bb, kind):
    if kind == "cs":
        return [t.transform_location(unreal.Vector(0, bb.max.y, 0)),
                t.transform_location(unreal.Vector(bb.min.x, 0, 0))]
    return [t.transform_location(unreal.Vector(0, bb.min.y, 0)),
            t.transform_location(unreal.Vector(0, bb.max.y, 0))]


def d2(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = next((a for a in eas.get_all_level_actors() if a.get_actor_label() == args["label"]), None)
    if vol is None:
        return {"error": "no volume"}
    oz = vol.get_actor_location().z
    zmax = float(args.get("zmax", 400.0))
    corners, walls = [], []
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None:
            continue
        n = sm.get_name()
        if "Prop" in n or "decal" in n or "Square" in n or "PCG_Cube" in n:
            continue
        bb = sm.get_bounding_box()
        for i in range(c.get_instance_count()):
            t = c.get_instance_transform(i, True)
            if t.translation.z - oz > zmax:
                continue
            if "CornerEx" in n:
                corners.append((n, "cs", ends(t, bb, "cs")))
            elif "CornerLeft" in n or "CornerRight" in n:
                corners.append((n, "sgd", ends(t, bb, "sgd")))
            else:
                walls.append(ends(t, bb, "wall"))
    gaps = []
    for idx, (n, kind, es) in enumerate(corners):
        if kind == "cs":
            g = [min(d2(e, w) for wl in walls for w in wl) for e in es]
            gaps.append({"corner": n, "wingA_gap": round(g[0], 1), "wingB_gap": round(g[1], 1)})
        else:
            best = None
            for j, (n2, k2, es2) in enumerate(corners):
                if j == idx:
                    continue
                for e in es:
                    for e2 in es2:
                        dd = d2(e, e2)
                        if best is None or dd < best:
                            best = dd
            gaps.append({"corner": n, "gap_to_partner_half": round(best, 1)})
    return {"n_corners": len(corners), "gaps": gaps}


mcp_result = json.loads(json.dumps(main(), default=str))
