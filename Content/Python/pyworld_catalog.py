# pyworld_catalog.py -- a temporary lineup of the tree and shrub meshes on the sea south of the valley, to identify
# them in a screenshot; {"clear": true} removes it. Actors are labelled PyWorldCatalog_* (never saved: run clear).
# Rows = species (flora.SPECIES order), columns = the species' meshes. Prints the layout.
import json

import unreal

from pypcg.world import flora

X0, Y0, Z = -20000.0, -175000.0, -500.0
DX, DY = 2500.0, 2500.0


def main():
    args = globals().get("mcp_args") or {}
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if str(a.get_actor_label()).startswith("PyWorldCatalog_"):
            eas.destroy_actor(a)
    if args.get("clear"):
        print(json.dumps({"cleared": True}))
        return
    global X0, Y0, Z, DX, DY
    if "at" in args:                                         # elsewhere (on land): [x, y, z], spacing "step"
        X0, Y0, Z = (float(v) for v in args["at"])
        DX = DY = float(args.get("step", DX))
    layers = args.get("layers", ["tree", "shrub"])
    rows = args["names"] if "names" in args else [n for n, s in flora.SPECIES.items() if s["layer"] in layers]
    layout = {}
    for c, mesh in enumerate(args.get("meshes", [])):       # raw mesh paths, on the row before the species
        a = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(X0 + c * DX, Y0 - DY, Z), unreal.Rotator())
        a.static_mesh_component.set_static_mesh(unreal.load_asset(mesh))
        a.set_actor_label("PyWorldCatalog_mesh_%d" % c)
    for r, name in enumerate(rows):
        for c, mesh in enumerate(flora.SPECIES[name]["meshes"]):
            sm = unreal.load_asset(mesh.split(".")[0])
            loc = unreal.Vector(X0 + c * DX, Y0 + r * DY, Z)
            a = eas.spawn_actor_from_class(unreal.StaticMeshActor, loc, unreal.Rotator(0, 0, 0))
            a.static_mesh_component.set_static_mesh(sm)
            a.set_actor_label("PyWorldCatalog_%s_%d" % (name, c))
        layout[r] = name
    print(json.dumps({"rows": layout, "x0": X0, "y0": Y0, "dx": DX, "dy": DY}))


main()
