# pyworld_probe_riverribbon.py -- TEMPORARY test (label PyWorldProbe_RiverRibbon; {"clear": true} removes it): a
# continuous dynamic-mesh river surface over one stretch of the real river (Saved/Reports/river_slice.json, from the W3
# record), with the Water plugin's river material and with MI_ocean, next to the old stretched planes, to compare.
import json
import math
import os

import unreal

MATS = {"river": "/Water/Materials/WaterSurface/Water_Material_River", "pyriver": "/Game/PyPCG/World/MI_PyWorldRiver", "stream": "/Game/PyPCG/World/M_PyWorldStream",
        "ocean": "/Game/Prop/kit_ocean/Material/MI_ocean"}


def ribbon(rows, lift=6.0, cross=7):
    E = unreal.GeometryScript_MeshEdits
    b = unreal.GeometryScriptSimpleMeshBuffers()
    verts, uvs, nrm, col, tris = [], [], [], [], []
    s0 = rows[0][5]
    for i, (x, y, w, wd, bed, s) in enumerate(rows):
        a = rows[max(0, i - 1)]
        c = rows[min(len(rows) - 1, i + 1)]
        dx, dy = c[0] - a[0], c[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        half = 0.5 * wd + 60.0                      # a little under the banks
        for j in range(cross):
            t = j / (cross - 1.0) * 2.0 - 1.0
            verts.append(unreal.Vector(x + nx * t * half, y + ny * t * half, w + lift))
            uvs.append(unreal.Vector2D((s - s0) / 100.0, (t + 1.0) * 0.5 * wd / 100.0))   # metres
            nrm.append(unreal.Vector(0.0, 0.0, 1.0))
            col.append(unreal.LinearColor(1.0 - abs(t), 0.4, 0.0, 1.0))
    for i in range(len(rows) - 1):
        for j in range(cross - 1):
            a = i * cross + j
            if FLIP:
                tris += [unreal.IntVector(a, a + 1, a + cross), unreal.IntVector(a + 1, a + cross + 1, a + cross)]
            else:
                tris += [unreal.IntVector(a, a + cross, a + 1), unreal.IntVector(a + 1, a + cross, a + cross + 1)]
    b.vertices, b.uv0, b.normals, b.vertex_colors, b.triangles = verts, uvs, nrm, col, tris
    m = unreal.DynamicMesh()
    E.append_buffers_to_mesh(m, b, 0)
    return m


FLIP = False


def main():
    global FLIP
    args = globals().get("mcp_args") or {}
    FLIP = bool(args.get("flip"))
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if str(a.get_actor_label()).startswith("PyWorldProbe_RiverRibbon"):
            eas.destroy_actor(a)
    if args.get("clear"):
        print("cleared")
        return
    rows = json.load(open(os.path.join(unreal.Paths.project_saved_dir(), "Reports", "river_slice.json")))
    key = args.get("mat", "river")
    a = eas.spawn_actor_from_class(unreal.DynamicMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator())
    a.set_actor_label("PyWorldProbe_RiverRibbon_" + key)
    c = a.get_editor_property("dynamic_mesh_component")
    c.set_dynamic_mesh(ribbon(rows, float(args.get("lift", 6.0))))
    c.set_material(0, unreal.load_asset(MATS[key]))
    print(json.dumps({"rows": len(rows), "mat": key}))


main()
