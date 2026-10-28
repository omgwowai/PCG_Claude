# pyworld_town_preview.py -- a temporary street of sample buildings from pypcg.world.building over the sea south of the
# valley (one per style, shops, the landmarks), as StaticMeshActors labelled PyWorldTown_* in folder PyWorldTown, to check
# the kit's pivots, corners, doors, roofs and colours in screenshots. Never saved: {"clear": true} removes them.
# {"only": [i, ...]} builds a subset of SAMPLES ({"pack": cm} lines them up in that order, that far apart; {"z": cm}
# their floors' height); {"blocker": material} tries another interior material; {"door_rise": cm}
# stands every door that far over the ground (entrance steps); prints the sample centres for pyworld.py shot.
import json
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
from pypcg.world import building as B  # noqa: E402

X0, Y0, Z0, DX = -60000.0, -192000.0, 300.0, 3200.0
SAMPLES = [
    dict(style="PLA", floors=3, w=1150.0, d=1000.0, tint="Ochre", roof_tint="Slate", use="house"),
    dict(style="PLA", floors=4, w=1400.0, d=1100.0, tint="Rose", roof_tint="BlueSlate", use="shop"),
    dict(style="PLB", floors=4, w=1250.0, d=1000.0, tint="Sage", roof_tint="Terracotta", use="house"),
    dict(style="PLC", floors=2, w=900.0, d=900.0, tint="Mist", roof_tint="Brown", use="house"),
    dict(style="BRA", floors=2, w=1050.0, d=900.0, tint="Base", roof_tint="Terracotta", use="house"),
    dict(style="BRB", floors=3, w=1100.0, d=950.0, tint="Umber", roof_tint="Slate", use="house"),
    dict(style="BRA", floors=1, w=800.0, d=700.0, tint="Sand", roof_tint="Brown", use="shop"),
    dict(style="LSB", floors=3, w=1300.0, d=1100.0, tint="Base", roof_tint="Slate", use="house"),
    dict(style="LSA", floors=4, w=1650.0, d=1200.0, tint="Warm", roof_tint="BlueSlate", use="shop"),
    dict(style="LSA", floors=3, w=1800.0, d=1300.0, tint="Base", roof_tint="Slate", special="TownHall"),
    dict(style="LSA", floors=2, w=2500.0, d=1400.0, tint="Grey", roof_tint="Slate", special="Church"),
    dict(style="LSA", floors=5, w=900.0, d=900.0, tint="Grey", roof_tint="Slate", special="BellTower"),
]


def main():
    args = globals().get("mcp_args") or {}
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if str(a.get_actor_label()).startswith("PyWorldTown_"):
            eas.destroy_actor(a)
    if args.get("clear"):
        print(json.dumps({"cleared": True}))
        return
    cache, n, missing, centres = {}, 0, set(), {}
    if args.get("blocker"):                    # try another material on the dark block behind the windows
        B.K.INTERIOR = args["blocker"]

    def load(path):
        if path not in cache:
            cache[path] = unreal.load_asset(path)
            if cache[path] is None:
                missing.add(path)
        return cache[path]
    order = list(args["only"]) if "only" in args else list(range(len(SAMPLES)))
    z0 = float(args.get("z", Z0))              # the floors' height (the sea is at -500: -450 sinks the plinths)
    for k, i in enumerate(order):
        spec = SAMPLES[i]
        x = X0 + (k * float(args["pack"]) if "pack" in args else i * DX)
        b = dict(spec, x=x, y=Y0, z=z0, yaw=0.0, front=0, seed=11 + i, kind=None,
                 door_rise=float(args.get("door_rise", 0.0)))
        out = B.assemble(b)
        centres[i] = [b["x"], b["y"], z0 + 0.5 * (out["ridge"] - z0), round(out["ridge"] - z0)]
        for m in out["instances"]:
            mesh = load(m["mesh"])
            if mesh is None:
                continue
            a = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*m["loc"]),
                                           unreal.Rotator(m["rot"][2], m["rot"][0], m["rot"][1]))
            a.set_actor_scale3d(unreal.Vector(*m["scale"]))
            c = a.static_mesh_component
            c.set_static_mesh(mesh)
            if m["mat"]:
                mat = load(m["mat"])
                if mat is not None:
                    c.set_material(0, mat)
            a.set_actor_label("PyWorldTown_%d_%d" % (i, n))
            a.set_folder_path("PyWorldTown")
            n += 1
    print(json.dumps({"spawned": n, "missing": sorted(missing)[:10], "centres": centres}))


main()
