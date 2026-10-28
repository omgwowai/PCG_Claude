# pyworld_probe_dynmesh4.py -- PROBE (makes a throwaway graph /Game/PyPCG/Probe/PCG_DynMeshProbe and a volume labelled
# PyWorldProbe_DynMesh; {"clear": true} removes both): does a Python Data Processor node that outputs a PCGDynamicMeshData
# (built with GeometryScript AppendBuffersToMesh: vertices, normals, UV0, vertex colours, triangles) reach a native
# "Spawn Dynamic Mesh" node and render? Also times the buffer build for a 60k-triangle ribbon in editor Python.
import json
import time

import unreal

GRAPH = "/Game/PyPCG/Probe/PCG_DynMeshProbe"
LABEL = "PyWorldProbe_DynMesh"
SCRIPT = '''
import unreal, math
E = unreal.GeometryScript_MeshEdits
b = unreal.GeometryScriptSimpleMeshBuffers()
n, w = 400, 8
verts, uvs, nrm, col, tris = [], [], [], [], []
for i in range(n):
    for j in range(w):
        x = i * 50.0
        y = (j - (w - 1) / 2.0) * 120.0 + 600.0 * math.sin(i / 40.0)
        verts.append(unreal.Vector(x, y, 3000.0 + 80.0 * math.sin(i / 25.0)))
        uvs.append(unreal.Vector2D(i * 0.05, j / (w - 1.0)))
        nrm.append(unreal.Vector(0.0, 0.0, 1.0))
        col.append(unreal.LinearColor(j / (w - 1.0), 0.0, 0.0, 1.0))
for i in range(n - 1):
    for j in range(w - 1):
        a = i * w + j
        tris.append(unreal.IntVector(a, a + 1, a + w))
        tris.append(unreal.IntVector(a + 1, a + w + 1, a + w))
b.vertices = verts; b.uv0 = uvs; b.normals = nrm; b.vertex_colors = col; b.triangles = tris
m = unreal.DynamicMesh()
E.append_buffers_to_mesh(m, b, 0)
d = unreal.PCGDynamicMeshData()
d.k2_initialize(m, [unreal.load_asset("/Game/Prop/kit_ocean/Material/MI_ocean")], True)
data_out.add_to_collection(d, "Output", ["Ribbon"])
unreal.log("DYNMESH PROBE: %d verts %d tris" % (m.get_vertex_count() if hasattr(m, "get_vertex_count") else -1, len(tris)))
'''


def main():
    args = globals().get("mcp_args") or {}
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if str(a.get_actor_label()) == LABEL:
            eas.destroy_actor(a)
    if args.get("clear"):
        if unreal.EditorAssetLibrary.does_asset_exist(GRAPH):
            unreal.EditorAssetLibrary.delete_asset(GRAPH)
        print("cleared")
        return
    out = {}
    # time the buffer build alone
    t0 = time.perf_counter()
    ns = {"data_out": None}
    E = unreal.GeometryScript_MeshEdits
    b = unreal.GeometryScriptSimpleMeshBuffers()
    verts = [unreal.Vector(i * 1.0, j * 1.0, 0.0) for i in range(3000) for j in range(11)]
    tris = [unreal.IntVector(i * 11 + j, i * 11 + j + 1, (i + 1) * 11 + j) for i in range(2999) for j in range(10)]
    tris += [unreal.IntVector(i * 11 + j + 1, (i + 1) * 11 + j + 1, (i + 1) * 11 + j) for i in range(2999) for j in range(10)]
    b.vertices = verts
    b.triangles = tris
    m = unreal.DynamicMesh()
    E.append_buffers_to_mesh(m, b, 0)
    out["build_60k_tris_s"] = round(time.perf_counter() - t0, 3)
    out["tri_count"] = m.get_triangle_count() if hasattr(m, "get_triangle_count") else [f for f in dir(unreal.GeometryScript_MeshQueries) if "triangle" in f and "count" in f]
    # graph: Python node -> Spawn Dynamic Mesh
    ael = unreal.EditorAssetLibrary
    if ael.does_asset_exist(GRAPH):
        ael.delete_asset(GRAPH)
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    g = tools.create_asset("PCG_DynMeshProbe", "/Game/PyPCG/Probe", unreal.PCGGraph, unreal.PCGGraphFactory())
    py_node, py_settings = g.add_node_of_type(unreal.PCGPythonDataProcessorSettings)
    L = unreal.PyPCGToolsLibrary
    out["set"] = str(L.set_properties_json(py_settings, json.dumps({"InlineScript": SCRIPT, "bMuteEditorToast": True})))
    out["pins"] = str(L.set_dynamic_pin_labels(py_settings, [], ["Output"]))
    sp_node, sp_settings = g.add_node_of_type(unreal.PCGSpawnDynamicMeshSettings)
    ok = g.add_edge(py_node, "Output", sp_node, "In")
    out["edge"] = bool(ok)
    ael.save_asset(GRAPH, only_if_is_dirty=False)
    vol = eas.spawn_actor_from_class(unreal.PCGVolume, unreal.Vector(0, -150000, 0), unreal.Rotator())
    vol.set_actor_label(LABEL)
    vol.set_actor_scale3d(unreal.Vector(100, 100, 100))
    pc = vol.get_component_by_class(unreal.PCGComponent)
    pc.set_graph(g)
    pc.set_editor_property("regenerate_in_editor", False)
    pc.activate(True)
    pc.generate_local(True)
    out["generating"] = True
    print(json.dumps(out, indent=1))


main()
