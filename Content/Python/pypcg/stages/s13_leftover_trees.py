"""Stage 13, second Python node -- the outer-forest trees after the texture writes (LeftOverLots).

`s13_leftover_lots` scatters the tree points and fits them to the terrain (`Subgraph_1`, `Subgraph_19`); the
two official `Write_Attribute_fromTexture` nodes stay NATIVE between the two Python nodes (`Subgraph_27`
writes `$scale` from the texture's G channel remapped to 0.6..2, `Subgraph_28` writes `index` remapped to
1..9; the texture read cannot be reproduced in pure Python -- see `docs/pypcg/stages/s13.md` 4.2). This
node does what follows them, as officially:

  AttributeMathsOp_3 / 4   roll and pitch set to 0
  Branch_4                 `UseMegaplantsTrees` false -> `Subgraph_26` (Black Alder field trees),
                           true -> `Subgraph_14` (Megaplants)
  Subgraph_26 / 14         `Assign_Assets` with `UseIndexattribute` on `Index`: each point takes the entry
                           its texture index names (`geo.assets.index_picks`; truncated; an index that
                           names no entry keeps the point with entry 0, as measured), plus the call's random rotation (+-2, +-2, +-180)
                           and scale (1 +- 0.2, uniform) drawn from `ctx.rng` (spec E2)
  Branch_2                 `Partitioned` false: everything to the kept `Subgraph_76 Spawn Outer Forest Trees`

ON THE DEMO LEVEL THIS NODE RECEIVES NOTHING: the official texture `/Game/Textures/Noise/T_CloudNoise_4k`
is not in this project, so `GetTextureData_0` fails inside both texture writes and they output no points
(measured 2026-10-19: 6 518 tree points reach `Subgraph_27`, none leave it), officially and in the port.
"""
from pypcg import geo
from pypcg.geo import assets as AS
from pypcg.stage_api import Param

STAGE = 13
RECORD = "s13_trees"
DOC = """LeftOverLots, outer-forest trees: the tree points after the native texture writes, roll and pitch
zeroed, each assigned the tree mesh its texture index names (Black Alder field trees, or Megaplants with
UseMegaplantsTrees), with a random yaw and scale."""
RANDOM = True
PARAMS = {"UseMegaplantsTrees": Param(False, "Use the Megaplants trees instead of the Black Alder field trees",
                                      type="Bool")}
INPUTS = {"TreePoints": "points"}
OUTPUTS = ("Trees",)

_BA = "/CitySamplePCG/BlackAlder/Geometry/PivotPainter/SM_BlackAlder_Field_%02d_PP.SM_BlackAlder_Field_%02d_PP"
_MP = "/CitySamplePCG/Megaplants/Tree_%s/Tree_%s_01/SM_%s_01_%s.SM_%s_01_%s"


def _mp(kind, short, letter):
    return _MP % (kind, kind, short, letter, short, letter)


# Subgraph_26's Assets, in the official order (entry k is picked by index k; 5, 4, 3, 2 repeat)
FOREST = tuple(_BA % (k, k) for k in (5, 4, 3, 2, 4, 3, 2, 1))
# Subgraph_14's Assets
MEGA = (_mp("Common_Hazel", "Common_Hazel", "B"), _mp("Common_Hazel", "Common_Hazel", "A"),
        _mp("Black_Alder", "Black_Alder", "D"), _mp("Black_Alder", "Black_Alder", "B"),
        _mp("Black_Alder", "Black_Alder", "A"), _mp("European_Beech", "European_Beech", "A"),
        _mp("European_Beech", "European_Beech", "B"), _mp("European_Beech", "European_Beech", "C"))
_COMMON = {"use_index_attribute": True, "index_attribute": "Index",
           "random_rotation_range": {"X": 2.0, "Y": 2.0, "Z": 180.0},
           "random_scale_range": {"X": 0.2, "Y": 0.0, "Z": 0.0}}
FOREST_SETTINGS = dict(_COMMON, scale_offset={"X": 0.7, "Y": 1.0, "Z": 1.0})      # Subgraph_26
MEGA_SETTINGS = dict(_COMMON)                                                      # Subgraph_14


def upright(items):
    """`AttributeMathsOp_3` / `4`: `$Rotation.Roll` and `.Pitch` set to 0 on every point; the merged target
    set `Assign_Assets` makes of its input items (`$Seed += dataIndex`, `MergePoints_0`)."""
    out = geo.Points()
    for idx, (pts, _tags) in enumerate(items):
        if not isinstance(pts, geo.Points):
            continue
        for name, tname in pts.types.items():
            if name not in out.attrs:
                out.declare(name, tname)
        for j in range(len(pts)):
            kw = {name: col[j] for name, col in pts.attrs.items()}
            out.add(pts.loc[j], rot=(0.0, pts.rot[j][1], 0.0), scale=pts.scale[j], density=pts.density[j],
                    bounds_min=pts.bounds_min[j], bounds_max=pts.bounds_max[j], color=pts.color[j],
                    steepness=pts.steepness[j], seed=AS._i32(int(pts.seed[j]) + idx), **kw)
    out.quat = None
    return out


def run(inputs, params, ctx):
    out = {"Trees": []}
    targets = upright(inputs.get("TreePoints", []))
    if not len(targets):
        ctx.notes.append("trees: no points after the texture writes")
        return out
    loader = getattr(ctx.ops, "assets", None)
    if loader is None:
        ctx.notes.append("no asset loader (ctx.ops.assets): no trees assigned")
        return out
    mega = bool(params.get("UseMegaplantsTrees", False))
    paths, settings = (MEGA, MEGA_SETTINGS) if mega else (FOREST, FOREST_SETTINGS)
    table = loader(list(paths))
    items = AS.expand_items(targets, table, None, dict(settings, rng=ctx.rng))
    out["Trees"] = [(pts, ["Trees"]) for pts in items]
    ctx.notes.append("trees: %d points, %d placed (%s)" % (len(targets), len(items[-1]) if items else 0,
                                                            "Megaplants" if mega else "Black Alder field"))
    return out
