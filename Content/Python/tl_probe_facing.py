# tl_probe_facing.py -- READ-ONLY. Which local axis of a placed facade module
# points to the building exterior? Instances matching `match` are clustered into
# buildings (union of pivots closer than `link_cm` in XY); for each wall-type
# instance, the cluster centroid's position in the instance's local frame is
# taken. Exterior = the side away from the centroid. Also reports the sign of
# each instance's Y scale (mirroring) and, for corner meshes, the local
# quadrant the centroid falls in.
import json
import math

args = mcp_args or {}
MATCH = args.get("match", "/Game/Building/TL/")
VOLUME = args.get("volume", "")          # actor label substring; "" = any PCGVolume
LINK = float(args.get("link_cm", 800.0))
KINDS = ("Wall_01", "Entrance_01", "Column_01", "CornerEx_01", "CornerIn_01")


def kind_of(path):
    for k in KINDS:
        if "_" + k in path:
            return k
    return None


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    inst = []
    for a in eas.get_all_level_actors():
        if a.get_class().get_name() != "PCGVolume":
            continue
        if VOLUME and VOLUME not in a.get_actor_label():
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            path = sm.get_path_name() if sm else ""
            if MATCH not in path:
                continue
            k = kind_of(path)
            for i in range(c.get_instance_count()):
                t = c.get_instance_transform(i, True)
                inst.append((k, t))
    if not inst:
        return {"instances": 0}

    # union-find clustering on XY pivots, grid-hashed
    n = len(inst)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    grid = {}
    pts = [(t.translation.x, t.translation.y) for _, t in inst]
    for i, (x, y) in enumerate(pts):
        grid.setdefault((int(x // LINK), int(y // LINK)), []).append(i)
    for (gx, gy), ids in grid.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((gx + dx, gy + dy), ()):
                    for i in ids:
                        if i < j and (pts[i][0] - pts[j][0]) ** 2 + (pts[i][1] - pts[j][1]) ** 2 <= LINK * LINK:
                            parent[find(i)] = find(j)
    sums = {}
    for i, (x, y) in enumerate(pts):
        r = find(i)
        s = sums.setdefault(r, [0.0, 0.0, 0])
        s[0] += x
        s[1] += y
        s[2] += 1
    cent = {r: (s[0] / s[2], s[1] / s[2]) for r, s in sums.items()}

    stats = {}
    for i, (k, t) in enumerate(inst):
        cx, cy = cent[find(i)]
        rot = t.rotation
        # world -> local direction for the centroid offset
        off = unreal.Vector(cx - t.translation.x, cy - t.translation.y, 0.0)
        local = rot.unrotate_vector(off)
        sc = t.scale3d
        st = stats.setdefault(k, {"n": 0, "centroid_local_x_neg": 0, "centroid_local_x_pos": 0,
                                  "centroid_local_y_neg": 0, "centroid_local_y_pos": 0,
                                  "scale_y_neg": 0, "scale_x_neg": 0})
        st["n"] += 1
        st["centroid_local_x_neg" if local.x < 0 else "centroid_local_x_pos"] += 1
        st["centroid_local_y_neg" if local.y < 0 else "centroid_local_y_pos"] += 1
        st["scale_y_neg"] += sc.y < 0
        st["scale_x_neg"] += sc.x < 0
    return {"instances": n, "clusters": len(cent), "by_kind": stats}


R = main()
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
