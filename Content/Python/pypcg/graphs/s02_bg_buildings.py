"""Slim graph of stage 2, BG_Buildings: no scene reads. The Python node's `Points` feed the kept
`SpawnAssets` (`Spawn_Assets`, the 3 SM_bgcity meshes, `PositionOffset.Z` 13200, `ScaleOffset`
(100, 1, 1)), whose output is the graph output, as in the official graph."""
from pypcg import dsl
from pypcg.stages import s02_bg_buildings as S


def build():
    g = dsl.SlimGraph(S)
    spawn = g.keep("SpawnAssets")                       # Spawn Background Buildings
    g.connect(g.py["Points"], spawn, "PrimaryInput")
    g.out(spawn["Out"])
    return g
