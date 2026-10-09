# tl_probe_facade_sequence.py -- READ-ONLY. The actual module sequence the
# showcase building laid down on each facade of one storey: every TL instance
# of the requested level, grouped into facades by its exterior direction
# (module local +X) and facade plane, then sorted along the run. Each entry is
# the module's short name, its run interval (cm, world) and its run scale.
# Args: {"level": "L01", "zmax": 2000, "out": path} -- zmax keeps only the base
# layer; with "out" the full result goes to that JSON file and only counts return.
import json

args = mcp_args or {}
LABEL = "TL_Showcase_Building"
LEVEL = args.get("level", "L01")
ZMAX = float(args.get("zmax", 2000.0))


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = next(a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL)
    groups = {}
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None or "_TL_%s_" % LEVEL not in sm.get_name():
            continue
        short = sm.get_name().split("_A_")[1].replace("_N1", "")
        bb = sm.get_bounding_box()
        for i in range(c.get_instance_count()):
            t = c.get_instance_transform(i, True)
            if t.translation.z > ZMAX:
                continue
            n = t.transform_direction(unreal.Vector(1, 0, 0))
            r = t.transform_direction(unreal.Vector(0, 1, 0))
            key = (round(n.x), round(n.y))
            xs, ys = [], []
            for x in (bb.min.x, bb.max.x):
                for y in (bb.min.y, bb.max.y):
                    p = t.transform_location(unreal.Vector(x, y, 0))
                    xs.append(p.x)
                    ys.append(p.y)
            # run axis is world X for facades facing +-Y, world Y otherwise
            if key[0] == 0:
                a0, a1, plane = min(xs), max(xs), round(t.translation.y / 50.0) * 50
            else:
                a0, a1, plane = min(ys), max(ys), round(t.translation.x / 50.0) * 50
            groups.setdefault("%s|%s" % (key, plane), []).append(
                {"m": short, "a0": round(a0, 1), "a1": round(a1, 1),
                 "s": round(t.scale3d.y, 3), "z": round(t.translation.z, 1),
                 "run": [round(r.x), round(r.y)]})
    out = {}
    for k, v in groups.items():
        v.sort(key=lambda e: e["a0"])
        out[k] = {"n": len(v), "span": [v[0]["a0"], v[-1]["a1"]], "seq": v}
    if args.get("out"):
        with open(args["out"], "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
        return {k: v["n"] for k, v in out.items()}
    return out


mcp_result = json.loads(json.dumps(main(), default=str))
