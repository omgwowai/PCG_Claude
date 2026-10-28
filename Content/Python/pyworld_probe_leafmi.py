# pyworld_probe_leafmi.py -- TEMPORARY actors (label PyWorldCatalog_*): one leaf part with its own material and one
# with the summer instance, side by side, to tell the material from the assembly.
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
leaf = unreal.load_asset("/CitySamplePCG/Megaplants/Tree_European_Beech/Instances/BrLeaves_000")
mi = unreal.load_asset("/Game/PyPCG/World/Trees/MI_European_Beech_Foliage_Summer")
for i, override in enumerate((None, mi)):
    a = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(-20000 + i * 300, -172500, -400), unreal.Rotator())
    a.static_mesh_component.set_static_mesh(leaf)
    a.static_mesh_component.set_world_scale3d(unreal.Vector(3, 3, 3))
    if override:
        a.static_mesh_component.set_material(0, override)
    a.set_actor_label("PyWorldCatalog_leaf_%d" % i)
print("ok")
