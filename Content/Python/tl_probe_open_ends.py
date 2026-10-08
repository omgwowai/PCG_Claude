# tl_probe_open_ends.py -- READ-ONLY. In a volume's TL output, list module run
# ends (world XY at local y=0 and y=w) that no other module end on the same
# level touches, plus each facade's coverage. Locates corner gaps.
import json

args = mcp_args or {}
VOLUME = args.get("volume", "TL_Building_Volume")
LEVEL_TAG = args.get("level_tag", "_L02_")
TOL = float(args.get("tol", 2.0))


def main():
    ML = unreal.MathLibrary
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    ends = []
    for a in eas.get_all_level_actors():
        if VOLUME not in a.get_actor_label():
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            path = sm.get_path_name() if sm else ""
            if "/Game/Building/TL/" not in path or LEVEL_TAG not in path:
                continue
            bb = sm.get_bounding_box()
            name = path.split(".")[-1].replace("SM_BLDG_TL_", "")
            for i in range(c.get_instance_count()):
                t = c.get_instance_transform(i, True)
                if abs(t.translation.z - float(args.get("z", t.translation.z))) > 1:
                    continue
                for y in (bb.min.y, bb.max.y):
                    p = ML.transform_location(t, unreal.Vector(0, y, 0))
                    ends.append((round(p.x, 1), round(p.y, 1), round(p.z, 1), name, i,
                                 round(t.rotation.rotator().yaw), [round(t.scale3d.x, 3), round(t.scale3d.y, 3)]))
    zs = sorted({e[2] for e in ends})
    z0 = zs[0] if zs else None
    one = [e for e in ends if e[2] == z0]
    open_ends = []
    for e in one:
        if not any(f is not e and (f[3], f[4]) != (e[3], e[4]) and abs(f[0] - e[0]) <= TOL and abs(f[1] - e[1]) <= TOL
                   for f in one):
            open_ends.append(e)
    return {"z": z0, "ends": len(one), "open": open_ends[:40],
            "scales": sorted({tuple(e[6]) for e in one})}


mcp_result = json.loads(json.dumps(main(), default=str))
