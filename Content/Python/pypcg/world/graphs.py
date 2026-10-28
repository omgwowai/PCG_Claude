"""The nine PyWorld graphs (spec 2.2): parameter getters -> scene reads -> one Python node -> native terrain writers,
grammars and spawners. pyworld.py build writes them to /Game/PyPCG/World/ (pypcg.build.build_slim, 0 diffs)."""
import json
import os

from pypcg import dsl
from pypcg import world as W
from pypcg.stages import (w01_terrain, w02_locations, w03_river, w04_roads, w05_bridges, w06_settlements,
                          w07_vegetation, w08_props, w09_surface)
from pypcg.world import layout as L


def _graph(module):
    return dsl.SlimGraph(module, name=W.name(W.stage_number(module)))


def _terrain(g, n=None, final=False):
    s = {"MeshPartitionBoundSize": dict(W.QUERY_BOX)}
    if final:
        s["MeshPartitionQueryType"] = "Final"
        title = "Get Mesh Terrain (Final)"
    else:
        query, sub, _w = W.TERRAIN[n]
        if query != "Base":
            s["MeshPartitionQueryType"] = query
        if sub:
            s["ModifierSubPriority"] = sub
        title = "Get Mesh Terrain (%s %d)" % (query, sub)
    return g.sub("Get_MeshTerrain", title, set=s)


def _points(g, terrain):
    return g.sub("Extract_MeshTerrainPoints", "Extract Terrain Points", PrimaryInput=terrain)


def _write(g, n, src, channels=None):
    s = {"MeshPartitionBoundSize": dict(W.QUERY_BOX), "ModifierSubPriority": W.TERRAIN[n][2]}
    if channels:
        s["Channels"] = list(channels)
    return g.sub("Write_MeshTerrain", "Write Terrain (sub-priority %d)" % W.TERRAIN[n][2], set=s, PrimaryInput=src)


def _spawn(g, srcs, title, material=None):
    s = {"UseMeshAttribute": True, "MeshAttribute": "Mesh", "Assets": [W.MESH["Cube"]]}
    if material:
        s["MaterialOverride"] = material
    return g.sub("Spawn_Assets", title, set=s, PrimaryInput=srcs)


def _descriptor():
    """The spawner's component descriptor with every field (no collision, shadows on, no culling), as the editor
    exports it (ism_descriptor.json, from pyworld_probe_descriptor.py)."""
    with open(os.path.join(os.path.dirname(__file__), "ism_descriptor.json")) as fh:
        return json.load(fh)


def _mesh_spawner(g, src, title, cull=0.0, shadow=True, wpo_off=0.0, materials=()):
    """The native spawner, mesh by the `Mesh` attribute, no collision; `cull` (cm) fades small plants out
    (W7: 1.4 M instances; Spawn_Assets' GetClassFromAttribute can race the garbage collector on that many, trap 61);
    `materials` names the attributes holding each point's material overrides, slot by slot (W6's building kit)."""
    td = _descriptor()          # the full struct: the build compares nested settings whole
    td["bCastShadow"] = bool(shadow)
    if cull:
        td.update({"InstanceStartCullDistance": int(0.8 * cull), "InstanceEndCullDistance": int(cull)})
    if wpo_off:
        td["WorldPositionOffsetDisableDistance"] = int(wpo_off)
    return g.node("PCGStaticMeshSpawnerSettings", title, set={
        "MeshSelectorType": "/Script/CoreUObject.Class'/Script/PCG.PCGMeshSelectorByAttribute'",
        "MeshSelectorParameters": {"_ClassName": "/Script/PCG.PCGMeshSelectorByAttribute", "AttributeName": "Mesh",
                                   "TemplateDescriptor": td, "bUseAttributeMaterialOverrides": bool(materials),
                                   "MaterialOverrideAttributes": list(materials)}}, In=src)


def _upstream(g, stages):
    return [g.actor_by_tag(W.volume_tag(m), "Get W%02d Output (%s)" % (m, W.entry(m)[3])) for m in stages]


def build_w01():
    g = _graph(w01_terrain)
    g.connect(_points(g, _terrain(g, 1)), g.py, "MeshTerrain")
    g.connect(g.actor_by_tag(L.TAG_VALLEY, "Get Valley Axis"), g.py, "Valley")
    erode = g.sub("Transform_MeshTerrain_Erosion", "Erode the Mountains", set={"MaskAttribute": "Mountain"},
                  PrimaryInput=g.py["Terrain"])
    _write(g, 1, erode)
    g.out(g.py["Summary"])
    return g


def build_w02():
    g = _graph(w02_locations)
    g.connect(g.actor_points(L.TAG_LOCATION, "Get Locations"), g.py, "Locations")
    g.connect(g.actor_points(L.TAG_RIVER_END, "Get River Ends"), g.py, "RiverEnds")
    g.connect(g.actor_points(L.TAG_EXIT, "Get Road Exits"), g.py, "Exits")
    g.connect(_terrain(g, final=True), g.py, "Surface")
    for pin in w02_locations.OUTPUTS:
        g.out(g.py[pin])
    return g


def build_w03():
    g = _graph(w03_river)
    g.connect(_points(g, _terrain(g, 3)), g.py, "Terrain")
    g.connect(_upstream(g, [2]), g.py, "Upstream")
    _write(g, 3, g.py["Terrain"])
    # one continuous water surface (a geo.Mesh -> PCGDynamicMeshData; its material travels with the data)
    g.node("PCGSpawnDynamicMeshSettings", "Spawn Water Surface (Dynamic Mesh)", In=g.py["Water"])
    g.out(g.py["River"], g.py["Summary"])
    return g


def build_w04():
    g = _graph(w04_roads)
    g.connect(_points(g, _terrain(g, 4)), g.py, "Terrain")
    g.connect(_upstream(g, [2, 3]), g.py, "Upstream")
    _write(g, 4, g.py["Terrain"])
    _spawn(g, g.py["Modules"], "Spawn Road Lanes")
    g.out(g.py["Roads"], g.py["Summary"])
    return g


def build_w05():
    g = _graph(w05_bridges)
    g.connect(_upstream(g, [3, 4]), g.py, "Upstream")
    _spawn(g, g.py["Parts"], "Spawn Bridge Parts")
    g.out(g.py["Bridges"], g.py["Summary"])
    return g


def build_w06():
    g = _graph(w06_settlements)
    g.connect(_points(g, _terrain(g, 6)), g.py, "Terrain")
    g.connect(_upstream(g, [2, 3, 4]), g.py, "Upstream")
    _write(g, 6, g.py["Terrain"])
    # the buildings: Megascans kit modules, each point's mesh and slot-0 material (a facade or roof colour) by attribute
    _mesh_spawner(g, g.py["Modules"], "Spawn Building Modules", materials=("Mat0",))
    _spawn(g, g.py["Parts"], "Spawn Street Paths and Plaza Tiles")
    g.out(g.py["Buildings"], g.py["Streets"], g.py["Areas"], g.py["Summary"])
    return g


def build_w07():
    g = _graph(w07_vegetation)
    g.connect(_points(g, _terrain(g, final=True)), g.py, "Terrain")
    g.connect(_upstream(g, [3, 4, 5, 6]), g.py, "Upstream")
    for pin, title, cull, shadow, wpo in (("Trees", "Trees", 0, True, 0), ("Shrubs", "Shrubs", 40000, True, 15000),
                                          ("Grass", "Grass", 12000, True, 6000),
                                          ("Ground", "Ground Plants", 9000, False, 5000),
                                          ("Debris", "Dead Wood", 20000, True, 0), ("Rocks", "Rocks", 0, True, 0)):
        _mesh_spawner(g, g.py[pin], "Spawn " + title, cull, shadow, wpo)
    g.out(g.py["Trees"], g.py["Summary"])
    return g


def build_w08():
    g = _graph(w08_props)
    g.connect(_terrain(g, final=True), g.py, "Surface")
    g.connect(_upstream(g, [2, 4, 5, 6]), g.py, "Upstream")
    _spawn(g, g.py["Props"], "Spawn Poles, Wires, Rails, Lamps and Benches")
    g.out(g.py["Summary"])
    return g


def build_w09():
    g = _graph(w09_surface)
    g.connect(_points(g, _terrain(g, 9)), g.py, "Terrain")
    g.connect(_upstream(g, [3, 4, 6, 7]), g.py, "Upstream")
    _write(g, 9, g.py["Terrain"], W.CHANNELS)
    g.out(g.py["Summary"])
    return g


GRAPHS = {1: build_w01, 2: build_w02, 3: build_w03, 4: build_w04, 5: build_w05, 6: build_w06, 7: build_w07,
          8: build_w08, 9: build_w09}


def graph(n):
    return GRAPHS[n]()
