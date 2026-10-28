# pyworld_kit_test.py -- a temporary test assembly of building-kit meshes over the sea south of the valley, to check
# pivots, facing and joints in a screenshot (actors PyWorldKitTest_*, never saved; {"clear": true} removes them).
# {"items": [[mesh, [x, y, z], yaw, [sx, sy, sz], [slot0, slot1, ...]], ...]} -- mesh and materials are package paths
# ("/Game/...") or "" for no override; {"file": "<path under the project>"} reads the same list from a JSON file;
# {"origin": [x, y, z]} shifts every item (default just south of the kit catalog).
import json
import os

import unreal

X0, Y0, Z0 = -60000.0, -183000.0, 300.0


def _full(path):
    return path if "." in path.rsplit("/", 1)[-1] else "%s.%s" % (path, path.rsplit("/", 1)[-1])


def main():
    args = globals().get("mcp_args") or {}
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if str(a.get_actor_label()).startswith("PyWorldKitTest_"):
            eas.destroy_actor(a)
    if args.get("clear"):
        print(json.dumps({"cleared": True}))
        return
    ox, oy, oz = args.get("origin", [X0, Y0, Z0])
    items = args.get("items", [])
    if args.get("file"):
        root = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
        with open(os.path.join(root, args["file"])) as fh:
            items = json.load(fh)
    cache, n, missing = {}, 0, []
    for item in items:
        mesh, loc, yaw, scale = item[0], item[1], item[2], item[3]
        mats = item[4] if len(item) > 4 else []
        if mesh not in cache:
            cache[mesh] = unreal.load_asset(_full(mesh))
        if cache[mesh] is None:
            missing.append(mesh)
            continue
        a = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(ox + loc[0], oy + loc[1], oz + loc[2]),
                                       unreal.Rotator(0.0, 0.0, float(yaw)))
        a.set_actor_scale3d(unreal.Vector(*scale))
        c = a.static_mesh_component
        c.set_static_mesh(cache[mesh])
        for i, m in enumerate(mats):
            if m:
                if m not in cache:
                    cache[m] = unreal.load_asset(_full(m))
                if cache[m] is not None:
                    c.set_material(i, cache[m])
        a.set_actor_label("PyWorldKitTest_%d" % n)
        a.set_folder_path("PyWorldKitTest")
        n += 1
    print(json.dumps({"spawned": n, "missing": sorted(set(missing))}))


main()
