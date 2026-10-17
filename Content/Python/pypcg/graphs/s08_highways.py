"""Slim graph of stage 8, Highways (spec 2.4).

The scene reads the official graph keeps feed the Python node: the two highway spline actors
(`Subgraph_7`) and the final mesh terrain (`Subgraph_3`). The Python node prepares the splines --
flatten, resample at 80 m, project onto the terrain, clamp, rebuild level -- and hands them to the
kept `Assign_HighwayShapeGrammar`, which is the node that builds the footprint.

The generation side stays native by contract (Ruling 2). `Assign_HighwayShapeGrammar` and the pillar
chain down to `Subgraph_4 Spawn Highway Support Assets` are kept by name, exactly as the brief lists
them; `Subgraph_0 Transform_Areas_Expand(1500)` and `AddTag_Highway` are the two one-node wrappers
between that footprint and the published `Highway` tag, and they stay native too, so the published
polygon is the engine's own expansion rather than a Python re-derivation.

What differs from the official graph's own wiring:

  - `Assign_HighwayShapeGrammar Size` reads `g.p('Highway_Width')` rather than the official
    `GetParam_HighwayWidth`: a slim graph carries one getter per declared parameter (ruling E6), and
    the official getter's GUID binding is not something a slim graph reproduces.
  - The dropped partition machinery (`GetGraphParameter_0/1` -> `Subgraph_2 GridPartition` ->
    `Loop_1 LoopSpawnActorPerData`) goes with its nodes. `Branch_0` is kept and still tests
    `Partitioned`, so the slim graph declares the parameter for it and leaves it false.
  - `Subgraph_6 "Filter: Road-Modified Terrain"` is dropped: it has no outgoing edge in the official
    graph, so nothing reads it.
"""
from pypcg import dsl
from pypcg.stages import s08_highways as S


def build():
    g = dsl.SlimGraph(S)
    _n = {}                   # official node name -> the kept Node

    _n['AddTag_Highway'] = g.keep('AddTag_Highway')
    _n['Assign_HighwayShapeGrammar'] = g.keep('Assign_HighwayShapeGrammar')
    _n['AttributeCast_1'] = g.keep('AttributeCast_1')
    _n['AttributeFilter_1'] = g.keep('AttributeFilter_1')
    _n['AttributeFilter_2'] = g.keep('AttributeFilter_2')
    _n['Branch_0'] = g.keep('Branch_0')
    _n['FilterDataByType_2'] = g.keep('FilterDataByType_2')
    _n['FilterDataByType_3'] = g.keep('FilterDataByType_3')
    _n['FilterDataByType_5'] = g.keep('FilterDataByType_5')
    _n['MakeConcrete_1'] = g.keep('MakeConcrete_1')
    _n['Projection_0'] = g.keep('Projection_0')
    _n['Reroute_0'] = g.keep('Reroute_0')
    _n['Reroute_1'] = g.keep('Reroute_1')
    _n['Subgraph_0'] = g.keep('Subgraph_0')
    _n['Subgraph_1'] = g.keep('Subgraph_1')
    _n['Subgraph_3'] = g.keep('Subgraph_3')
    _n['Subgraph_4'] = g.keep('Subgraph_4')
    _n['Subgraph_5'] = g.keep('Subgraph_5')
    _n['Subgraph_7'] = g.keep('Subgraph_7')

    # The scene reads: the two highway spline actors (ONE node, one pin -- `Subgraph_7` reads both
    # actors at once), the Roads actor output and the final terrain. `Roads` is read by this node even
    # though the computation does not use it: the pin is on the contract, and an unwired dynamic pin
    # makes the PCG compiler cull the node (`dsl.SlimGraph`).
    g.connect(_n['Subgraph_7'], g.py, 'HighwaySplines')
    g.connect(_n['Subgraph_5'], g.py, 'Roads')
    g.connect(_n['Subgraph_3'], g.py, 'MeshTerrain')

    # The contract output: the footprint the official `AddTag_Highway` stamps.
    g.out(_n['AddTag_Highway']['Out'])

    # ---- the spline chain: the Python node feeds the grammar node ----
    g.connect(g.py['Highway'], _n['Assign_HighwayShapeGrammar'], 'PrimaryInput')
    g.connect(g.p('Highway_Width'), _n['Assign_HighwayShapeGrammar'], 'Size')

    # ---- the footprint chain: expand 15 m, then tag ----
    g.connect(_n['Assign_HighwayShapeGrammar']['Footprints'], _n['Subgraph_0'], 'PrimaryInput')
    g.connect(_n['Subgraph_0']['Out'], _n['AddTag_Highway'], 'In')

    # ---- the kept pillar chain, fed the grammar node's own points ----
    g.connect(_n['Assign_HighwayShapeGrammar']['Points'], _n['AttributeCast_1'], 'In')
    g.connect(_n['AttributeCast_1']['Out'], _n['FilterDataByType_2'], 'In')
    g.connect(_n['FilterDataByType_2']['InsideFilter'], _n['AttributeFilter_1'], 'In')
    g.connect(_n['AttributeFilter_1']['OutsideFilter'], _n['Reroute_1'], 'In')
    g.connect(_n['Reroute_1']['Out'], _n['Reroute_0'], 'In')
    g.connect(_n['AttributeFilter_1']['InsideFilter'], _n['FilterDataByType_5'], 'In')
    g.connect(_n['FilterDataByType_5']['InsideFilter'], _n['Projection_0'], 'In')
    g.connect(_n['MakeConcrete_1']['Out'], _n['Projection_0'], 'Projection Target')
    g.connect(_n['Projection_0']['Out'], _n['FilterDataByType_3'], 'In')
    g.connect(_n['FilterDataByType_3']['InsideFilter'], _n['AttributeFilter_2'], 'In')
    g.connect([_n['AttributeFilter_2']['InsideFilter'], _n['Reroute_0']['Out']], _n['Branch_0'], 'In')
    g.connect(g.p('Partitioned'), _n['Branch_0'], 'bOutputToB')
    g.connect(_n['Branch_0']['Output A'], _n['Subgraph_4'], 'PrimaryInput')

    # ---- the Roads actor read, into the concrete the pillars are projected onto ----
    g.connect(_n['Subgraph_5'], _n['Subgraph_1'], 'PrimaryInput')
    g.connect(_n['Subgraph_1']['Selected'], _n['MakeConcrete_1'], 'In')

    # `Branch_0 Output B` -- the official graph's dropped `Subgraph_2 GridPartition` ->
    # `Loop_1 LoopSpawnActorPerData` chain -- is left unwired: the contract drops both nodes, and
    # `Partitioned` is false everywhere this port runs, so `Output A` is the side the graph takes.
    return g
