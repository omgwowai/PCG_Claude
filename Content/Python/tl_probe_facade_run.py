# tl_probe_facade_run.py -- READ-ONLY. Lay out one facade of the TL building at
# one storey: every instance whose pivot lies on the facade line (x == X or
# y == Y within 1 cm), sorted along the run, with its local run [y0, y1] mapped
# to world, its mesh and its Y scale. Shows the actual placement sequence the
# grammar produced, so gaps and overlaps are explicit.
import json

args = mcp_args or {}
VOLUME = args.get("volume", "TL_Building_Volume")
Z = float(args.get("z", 50500.5))
AXIS = args.get("axis", "y")          # facade line: "y" means y == VALUE
VALUE = float(args.get("value", 2250.0))


def main():
    ML = unreal.MathLibrary
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    rows = []
    for a in eas.get_all_level_actors():
        if VOLUME not in a.get_actor_label():
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            path = sm.get_path_name() if sm else ""
            bb = sm.get_bounding_box()
            name = path.split(".")[-1].replace("SM_BLDG_", "")
            for i in range(c.get_instance_count()):
                t = c.get_instance_transform(i, True)
                p = t.translation
                if abs(p.z - Z) > 1.0:
                    continue
                on = abs((p.y if AXIS == "y" else p.x) - VALUE) <= 1.0
                if not on:
                    continue
                a0 = ML.transform_location(t, unreal.Vector(0, bb.min.y, 0))
                a1 = ML.transform_location(t, unreal.Vector(0, bb.max.y, 0))
                k = 0 if AXIS == "y" else 1
                s0, s1 = sorted(((a0.x, a0.y)[k], (a1.x, a1.y)[k]))
                rows.append({"mesh": name, "from": round(s0, 1), "to": round(s1, 1),
                             "pivot": round((p.x, p.y)[k], 1),
                             "yaw": round(t.rotation.rotator().yaw),
                             "sy": round(t.scale3d.y, 3)})
    rows.sort(key=lambda r: r["from"])
    gaps = []
    for r0, r1 in zip(rows, rows[1:]):
        if r1["from"] - r0["to"] > 1.0:
            gaps.append([r0["to"], r1["from"]])
    return {"n": len(rows), "rows": rows, "gaps": gaps}


mcp_result = json.loads(json.dumps(main(), default=str))
