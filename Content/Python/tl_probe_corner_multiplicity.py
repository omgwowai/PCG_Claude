# tl_probe_corner_multiplicity.py -- READ-ONLY. In the current level's
# PCG_3_3_1_Buildings output:
#   corners: for CornerEx instances whose mesh path contains `match`, count
#            the other CornerEx instances within 2.5 m at the same height and
#            their relative yaw, i.e. is a building corner placed once, or
#            once per segment end (FC of one segment + LC of the next)?
#   roofs:   dynamic-mesh components owned by the buildings stage (the
#            planar roofs), with bounds, and for a few CHA buildings the gap
#            between the roof and the highest module pivot under it.
import json
import math

args = mcp_args or {}
MATCH = args.get("match", "/Game/Building/CH/A/Kit_Bldg_CHA_L2_A/")
LIMIT = int(args.get("limit", 400))


def stage_actors():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    return [a for a in eas.get_all_level_actors() if "PCG_3_3_1_Buildings" in a.get_actor_label()]


def corners(actors):
    cs = []
    for a in actors:
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            if sm is None:
                continue
            p = sm.get_path_name()
            if MATCH in p and "CornerEx_01" in p:
                for i in range(c.get_instance_count()):
                    cs.append(c.get_instance_transform(i, True))
    cs = cs[:LIMIT * 4]
    grid = {}
    for i, t in enumerate(cs):
        grid.setdefault((int(t.translation.x // 300), int(t.translation.y // 300)), []).append(i)
    pats = {}
    for i, t in enumerate(cs[:LIMIT]):
        near = []
        gx, gy = int(t.translation.x // 300), int(t.translation.y // 300)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((gx + dx, gy + dy), ()):
                    if j == i:
                        continue
                    u = cs[j]
                    d = math.hypot(t.translation.x - u.translation.x, t.translation.y - u.translation.y)
                    if d < 250 and abs(t.translation.z - u.translation.z) < 5:
                        dyaw = (u.rotation.rotator().yaw - t.rotation.rotator().yaw + 540) % 360 - 180
                        near.append("d%d/yaw%d" % (round(d / 10) * 10, round(dyaw)))
        k = ",".join(sorted(near)) or "alone"
        pats[k] = pats.get(k, 0) + 1
    return {"n": len(cs), "patterns": dict(sorted(pats.items(), key=lambda kv: -kv[1])[:10])}


def roofs(actors):
    out = []
    for a in actors:
        for c in a.get_components_by_class(unreal.ActorComponent):
            cls = c.get_class().get_name()
            if "DynamicMesh" not in cls:
                continue
            try:
                o, e = c.get_editor_property("bounds").origin, c.get_editor_property("bounds").box_extent
            except Exception:
                o = e = None
            out.append({"cls": cls, "o": o.to_tuple() if o else None, "e": e.to_tuple() if e else None})
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    other = {}
    for a in eas.get_all_level_actors():
        cls = a.get_class().get_name()
        if "DynamicMesh" in cls or "PCGPartition" in cls or "PCGArtifact" in cls:
            other[cls] = other.get(cls, 0) + 1
    return {"components": len(out), "sample": out[:5], "actor_classes": other}


def main():
    actors = stage_actors()
    return {"stage_actors": [a.get_actor_label() for a in actors][:5], "corners": corners(actors),
            "roofs": roofs(actors)}


mcp_result = json.loads(json.dumps(main(), default=str))
