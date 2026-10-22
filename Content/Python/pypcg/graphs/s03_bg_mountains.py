"""Slim graph of stage 3, BG_Mountains: the kept `PCGLoadDataAsset_0` (`VistaCliffs_PCG`) feeds the
Python node's `Cliffs`; its stamped `Points` feed the kept `StaticMeshSpawner_0` (mesh selector by the
`Mesh` attribute) and the graph output. The official graph's output node is unwired; the contract
publishes the stamped points, which nothing downstream reads."""
from pypcg import dsl
from pypcg.stages import s03_bg_mountains as S


def build():
    g = dsl.SlimGraph(S)
    g.connect(g.keep("PCGLoadDataAsset_0"), g.py, "Cliffs")       # Load Vista Cliffs Data Asset
    spawner = g.keep("StaticMeshSpawner_0")                        # Spawn Vista Cliff Meshes
    g.connect(g.py["Points"], spawner, "In")
    g.out(g.py["Points"])
    return g
