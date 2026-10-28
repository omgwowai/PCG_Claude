# pyworld_probe_watermat.py -- TEMPORARY test actors (label PyWorldProbe_Water_*; {"clear": true} removes them): a flat
# 30 x 10 m dynamic-mesh ribbon with each candidate water material, on the sea south of the valley, to see which one
# renders as a convincing river surface on a plain mesh (no Water Body actor). Also reports each material's shading
# model and blend mode.
import json

import unreal

CANDIDATES = {
    "ocean": "/Game/Prop/kit_ocean/Material/MI_ocean",
    "river": "/Water/Materials/WaterSurface/Water_Material_River",
    "lake": "/Water/Materials/WaterSurface/Water_Material_Lake",
    "custom": "/Water/Materials/WaterSurface/Water_Material_CustomMesh",
}
X0, Y0, Z = -15000.0, -175000.0, 200.0


def ribbon(cx, cy, z, length=3000.0, width=1000.0, n=30, w=6):
    E = unreal.GeometryScript_MeshEdits
    b = unreal.GeometryScriptSimpleMeshBuffers()
    verts, uvs, nrm, tris = [], [], [], []
    for i in range(n):
        for j in range(w):
            verts.append(unreal.Vector(cx + (i / (n - 1.0) - 0.5) * length, cy + (j / (w - 1.0) - 0.5) * width, z))
            uvs.append(unreal.Vector2D(i / (n - 1.0) * length / 1000.0, j / (w - 1.0)))
            nrm.append(unreal.Vector(0.0, 0.0, 1.0))
    for i in range(n - 1):
        for j in range(w - 1):
            a = i * w + j
            tris += [unreal.IntVector(a, a + 1, a + w), unreal.IntVector(a + 1, a + w + 1, a + w)]
    b.vertices, b.uv0, b.normals, b.triangles = verts, uvs, nrm, tris
    m = unreal.DynamicMesh()
    E.append_buffers_to_mesh(m, b, 0)
    return m


def main():
    args = globals().get("mcp_args") or {}
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if str(a.get_actor_label()).startswith("PyWorldProbe_Water_"):
            eas.destroy_actor(a)
    if args.get("clear"):
        print("cleared")
        return
    out = {}
    for i, (key, path) in enumerate(CANDIDATES.items()):
        mat = unreal.load_asset(path)
        if mat is None:
            out[key] = "missing"
            continue
        base = mat.get_base_material()
        out[key] = {"shading": str(base.get_editor_property("shading_model")),
                    "blend": str(base.get_editor_property("blend_mode")),
                    "used_with_water": bool(base.get_editor_property("used_with_water")) if hasattr(base, "used_with_water") else None}
        a = eas.spawn_actor_from_class(unreal.DynamicMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator())
        a.set_actor_label("PyWorldProbe_Water_" + key)
        c = a.get_editor_property("dynamic_mesh_component")
        c.set_dynamic_mesh(ribbon(X0 + i * 4000.0, Y0, Z))
        c.set_material(0, mat)
    print(json.dumps(out, indent=1))


main()
