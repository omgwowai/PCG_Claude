"""Stage 13, third Python node -- the plaza points after the five fitting-asset nodes (LeftOverLots).

The five kept `Fill_Areas_WithFittingAssets_with_Corrective` nodes (`SpawnAssets` false) hand over the plaza
kits' points, each carrying its `Asset`. Officially they then go through 25 nodes before `Subgraph_74 Spawn
Plaza`; this node is those nodes (official names in brackets):

  PROJECT     every point onto the final mesh terrain [Subgraph_20 Custom_Projector_with_rotation_fix],
              `Z_offset` = its z before; a miss stays put at density 0 with its z doubled
  CAST        `AssetString` = the `Asset` path as text [AttributeCast_0, FilterDataByType_3]
  BIRCHES     the points whose `AssetString` contains `Tree_Birch` (case-insensitive) [AttributeFilter_0]:
              roll and pitch set to 0 [AttributeMathsOp_1 / 2]; those under a highway ground tile removed
              [Subgraph_56 Compose_Points_Difference, Discrete / Binary] -- the tiles being the highway
              filled on a 6 m grid [Subgraph_55 Fill_Areas_Uniformly, 300] and fitted to the terrain
              [Subgraph_57]; then a new tree each [Branch_3: `UseMegaplantsTrees` false -> Subgraph_73
              Assign Trees (four Black Alder field meshes, `ExtentsScale` (0.7, 1, 1), scale 1 +- 0.2),
              true -> Subgraph_12 Assign Megaplant Trees (four Megaplants, scale 1 +- 0.2)]
  THE REST    `plane` props dropped (AttributeFilter_1's Inside has no reader) [FilterDataByType_0,
              AttributeFilter_1]; `sidewalk`, `border`, `cone` props kept as they are [AttributeFilter_2 /
              4 / 5 and FilterDataByType_1 / 5 / 6]; everything else upright, roll and pitch 0
              [AttributeMathsOp_5 / 6]
  GATHER      [Gather_2]: the upright rest, the sidewalk, border and cone props; `Asset` as a soft object
              path [AttributeCast_1]; then the new trees [Gather_3] -> `PlazaPoints` -> the kept
              `Subgraph_74 Spawn Plaza`

The new trees' mesh pick and scale are Python's own draws (spec E2); everything else is deterministic.
"""
from pypcg import geo
from pypcg.geo import areas as A
from pypcg.geo import assets as AS
from pypcg.geo import ground as G
from pypcg.stage_api import Param

STAGE = 13
RECORD = "s13_plazas"
DOC = """LeftOverLots, plaza props: the five fitting nodes' kit points fitted to the final mesh terrain; the
birch trees among them upright, less those under the highway's ground tiles, and given new tree meshes; the
plane props dropped; sidewalk, border and cone props as they are; the rest upright."""
RANDOM = True
PARAMS = {"UseMegaplantsTrees": Param(False, "Use the Megaplants trees instead of the Black Alder field trees",
                                      type="Bool")}
INPUTS = {"Plazas": "points", "Highways": "polygon", "MeshTerrain": "surface"}
OUTPUTS = ("PlazaPoints",)

BIRCH, PLANE, KEPT_AS_IS = "tree_birch", "plane", ("sidewalk", "border", "cone")   # AttributeFilter_0/1/2/4/5
HIGHWAY_TILE_EXTENT_CM = 300.0          # Subgraph_55 PointExtents
_BA = "/CitySamplePCG/BlackAlder/Geometry/PivotPainter/SM_BlackAlder_Field_%02d_PP.SM_BlackAlder_Field_%02d_PP"
_MP = "/CitySamplePCG/Megaplants/Tree_Black_Alder/Tree_Black_Alder_01/SM_Black_Alder_01_%s.SM_Black_Alder_01_%s"
TREES = tuple(_BA % (k, k) for k in (1, 2, 3, 4))                      # Subgraph_73 Assets
MEGA = tuple(_MP % (k, k) for k in "ABCD")                            # Subgraph_12 Assets
TREES_SETTINGS = {"extents_scale": {"X": 0.7, "Y": 1.0, "Z": 1.0},
                  "random_scale_range": {"X": 0.2, "Y": 0.0, "Z": 0.0}}
MEGA_SETTINGS = {"random_scale_range": {"X": 0.2, "Y": 0.0, "Z": 0.0}}
ASSET, ASSET_STRING, Z_OFFSET = "Asset", "AssetString", "Z_offset"


def _surface(inputs):
    for v, _tags in inputs.get("MeshTerrain", []):
        if hasattr(v, "height"):
            return v
    return None


def _copy_types(src, dst):
    for name, tname in src.types.items():
        if name not in dst.attrs:
            dst.declare(name, tname)


def _row(pts, j, **over):
    kw = {"rot": pts.rot[j], "scale": pts.scale[j], "density": pts.density[j], "bounds_min": pts.bounds_min[j],
          "bounds_max": pts.bounds_max[j], "color": pts.color[j], "steepness": pts.steepness[j], "seed": pts.seed[j]}
    kw.update({name: col[j] for name, col in pts.attrs.items()})
    kw.update(over)
    return kw


def project(pts, surface):
    """`Subgraph_20` on one item: a new `Points` with `Z_offset` and `AssetString` (AttributeCast_0)."""
    out = geo.Points()
    _copy_types(pts, out)
    for name, tname in ((Z_OFFSET, "Double"), (ASSET_STRING, "String")):
        if name not in out.attrs:
            out.declare(name, tname)
    for j in range(len(pts)):
        loc, rot, density = pts.loc[j], pts.rot[j], pts.density[j]
        if surface is not None:
            loc, rot, hit = G.project_point(pts.loc[j], pts.rot[j], pts.bounds_min[j], pts.bounds_max[j], surface,
                                            scale=pts.scale[j], quat=pts.quat[j] if pts.quat else None)
            density = density if hit else 0.0
        asset = (pts.attrs.get(ASSET) or [None] * len(pts))[j]
        out.add(loc, **_row(pts, j, rot=rot, density=density, **{Z_OFFSET: float(pts.loc[j][2]),
                                                                  ASSET_STRING: "" if asset is None else str(asset)}))
    return out


def _upright(pts, j):
    r = pts.rot[j]
    return (0.0, r[1], 0.0)


def split(pts):
    """`AttributeFilter_0/1/2/4/5` in their chain: (birches, upright rest, sidewalk, border, cone) as
    index lists; the plane props are in none of them."""
    birch, rest, kept = [], [], {k: [] for k in KEPT_AS_IS}
    for j, s in enumerate(pts.attrs.get(ASSET_STRING) or [""] * len(pts)):
        s = (s or "").lower()
        if BIRCH in s:
            birch.append(j)
        elif PLANE in s:
            continue
        else:
            for k in KEPT_AS_IS:
                if k in s:
                    kept[k].append(j)
                    break
            else:
                rest.append(j)
    return birch, rest, kept["sidewalk"], kept["border"], kept["cone"]


def take(pts, idx, upright=False):
    out = geo.Points()
    _copy_types(pts, out)
    for j in idx:
        out.add(pts.loc[j], **_row(pts, j, rot=_upright(pts, j) if upright else pts.rot[j]))
    return out


def highway_tiles(highways, surface):
    """`Subgraph_55 Fill_Areas_Uniformly` (300) then `Subgraph_57` onto the terrain: `(loc, quat, scale,
    bounds_min, bounds_max, density)` per tile, the form `geo.ground.difference_binary` reads. A tile that
    misses the terrain has density 0 (it removes nothing)."""
    e = HIGHWAY_TILE_EXTENT_CM
    out = []
    for p in highways:
        locs, yaw = G.fill_uniform(p.outer, p.z, e)
        for loc in locs:
            if surface is None:
                continue
            nloc, rot, hit = G.project_point(loc, (0.0, yaw, 0.0), (-e, -e, -e), (e, e, e), surface)
            out.append((nloc, AS.quat_of(*rot), (1.0, 1.0, 1.0), (-e, -e, -e), (e, e, e), 1.0 if hit else 0.0))
    return out


def plazas(items, highways, surface, mega, rng, loader):
    """The whole chain; returns `(points items in the official gather order, notes)`."""
    projected = [project(pts, surface) for pts in items]
    parts = [split(p) for p in projected]
    rest = [take(p, s[1], upright=True) for p, s in zip(projected, parts)]
    side = [take(p, s[2]) for p, s in zip(projected, parts)]
    border = [take(p, s[3]) for p, s in zip(projected, parts)]
    cone = [take(p, s[4]) for p, s in zip(projected, parts)]
    birches = [take(p, s[0], upright=True) for p, s in zip(projected, parts)]
    out = [x for x in rest + side + border + cone if len(x)]
    tiles = highway_tiles(highways, surface) if any(len(b) for b in birches) else []
    kept_birch = []
    for b in birches:
        if not len(b):
            continue
        rows = [(b.loc[j], AS.quat_of(*b.rot[j]), b.scale[j], b.bounds_min[j], b.bounds_max[j], b.density[j])
                for j in range(len(b))]
        keep = G.difference_binary(rows, tiles) if tiles else list(range(len(b)))
        if keep:
            kept_birch.append(b.take(keep))
    trees = []
    n_birch = sum(len(b) for b in kept_birch)
    if n_birch and loader is not None:
        targets = geo.Points()
        for idx, b in enumerate(kept_birch):             # Assign_Assets merges its items, $Seed += dataIndex
            _copy_types(b, targets)
            for j in range(len(b)):
                targets.add(b.loc[j], **_row(b, j, seed=AS._i32(int(b.seed[j]) + idx)))
        paths, settings = (MEGA, MEGA_SETTINGS) if mega else (TREES, TREES_SETTINGS)
        table = loader(list(paths))
        picks = AS.choose(len(targets), paths, rng)
        trees = AS.expand_items(targets, table, picks, dict(settings, rng=rng))
    notes = ["plazas: %d items, %d points; %d birches, %d left after the highway tiles (%d tiles); %d kept"
             % (len(items), sum(len(p) for p in items), sum(len(b) for b in birches), n_birch, len(tiles),
                sum(len(x) for x in out))]
    return out + list(trees), notes


def run(inputs, params, ctx):
    items = [v for v, _t in inputs.get("Plazas", []) if isinstance(v, geo.Points)]
    loader = getattr(ctx.ops, "assets", None)
    pts, notes = plazas(items, A.areas_of(inputs.get("Highways", [])), _surface(inputs),
                        bool(params.get("UseMegaplantsTrees", False)), ctx.rng, loader)
    ctx.notes += notes
    return {"PlazaPoints": [(p, ["PlazaPoints"]) for p in pts]}
