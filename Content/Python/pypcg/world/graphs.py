"""The nine PyWorld graphs (spec 2.2): parameter getters -> scene reads -> one Python node -> native terrain writers,
grammars and spawners. pyworld.py build writes them to /Game/PyPCG/World/ (pypcg.build.build_slim, 0 diffs)."""
from pypcg import dsl
from pypcg import world as W
from pypcg.stages import (w01_terrain, w02_locations, w03_river, w04_roads, w05_bridges, w06_settlements,
                          w07_vegetation, w08_props, w09_surface)
from pypcg.world import layout as L, rules


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
    _spawn(g, g.py["Water"], "Spawn Water Surface", W.WATER_MATERIAL)
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
    for group in rules.GROUPS:
        g.sub("Assign_ShapeGrammarDefinition", "Buildings (%s)" % group,
              set={"ShapeGrammarDefinition": W.GRAMMAR, "Size": rules.HEIGHT[group]},
              PrimaryInput=g.py["Footprints" + group])
    _spawn(g, g.py["Parts"], "Spawn Foundations, Roofs, Streets and Plazas")
    g.out(g.py["Buildings"], g.py["Streets"], g.py["Areas"], g.py["Summary"])
    return g


def build_w07():
    g = _graph(w07_vegetation)
    terrain = _terrain(g, final=True)
    g.connect(_points(g, terrain), g.py, "Terrain")
    g.connect(terrain, g.py, "Surface")
    g.connect(_upstream(g, [3, 4, 5, 6]), g.py, "Upstream")
    _spawn(g, [g.py["Trees"], g.py["Rocks"], g.py["Grass"]], "Spawn Trees, Rocks and Grass")
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
