"""Stage 14, second Python node -- every point after the two kept grammar nodes (Parkings).

The official graph sends the parking line decals, the two grammars' module points, the ground tiles, the
arrows and both car sets through ten nodes before `Subgraph_13 Spawn All Parking Lot Assets`; this node is
those nodes (official names in brackets):

  PROJECT     every point onto the final mesh terrain [Subgraph_3 Custom_Projector_with_rotation_fix], in its
              In Points order (Subgraph_7, 53, 54, the tiles, the arrows, the forward and the reverse cars);
              a point that misses stays put at density 0 with its z doubled (trap 69)
  LIFT        +22 cm along each point's own (now tilted) up axis [Subgraph_9 Transform_Offset, non-absolute]
  CAST        `AssetString` = the `Asset` path as text [AttributeCast_1]
  VEHICLES    the points whose `AssetString` contains `SM_veh` [FilterDataByAttribute_1, Substring] are kept AND
              copied with `/Mesh/` -> `/Mesh/Transparent/` and `SM_veh` -> `SM_All_Trans_veh` in the path
              [FilterDataByType_0, AttributeStringOp_1 / 2, CopyAttributes_0, AttributeCast_0]: every car is
              spawned twice, once with its transparent twin
  GATHER      [Gather_0]: the vehicles, the rest, the transparent copies -> `Points` -> the kept `Subgraph_13`

Deterministic: no draw.
"""
from pypcg import geo
from pypcg.geo import assets as AS
from pypcg.geo import ground as G

STAGE = 14
RECORD = "s14_finish"
DOC = """Parkings, final points: every parking point and grammar module fitted to the final mesh terrain, lifted
22 cm; every car also spawned as its transparent twin."""
RANDOM = False
PARAMS = {}
INPUTS = {"Points": "points", "MeshTerrain": "surface"}
OUTPUTS = ("Points",)

LIFT_CM = 22.0                                     # Subgraph_9 offset Z
VEHICLE = "SM_veh"                                 # FilterDataByAttribute_1 (Substring, case-sensitive)
REPLACES = (("/Mesh/", "/Mesh/Transparent/"), ("SM_veh", "SM_All_Trans_veh"))   # AttributeStringOp_1 / 2
ASSET, ASSET_STRING = "Asset", "AssetString"


def _surface(inputs):
    for v, _tags in inputs.get("MeshTerrain", []):
        if hasattr(v, "height"):
            return v
    return None


def _row(pts, j, **over):
    kw = {"rot": pts.rot[j], "scale": pts.scale[j], "density": pts.density[j], "bounds_min": pts.bounds_min[j],
          "bounds_max": pts.bounds_max[j], "color": pts.color[j], "steepness": pts.steepness[j], "seed": pts.seed[j]}
    kw.update({name: col[j] for name, col in pts.attrs.items()})
    kw.update(over)
    return kw


def _new_like(pts):
    out = geo.Points()
    for name, tname in pts.types.items():
        out.declare(name, tname)
    if ASSET_STRING not in out.attrs:
        out.declare(ASSET_STRING, "String")
    return out


def project_lift(pts, surface):
    """`Subgraph_3` then `Subgraph_9` then `AttributeCast_1`, on one item: a new `Points`. The lift is a
    non-absolute `Transform_Offset` (`TransformPoints`, `RotateVector(q, offset)`): +22 cm along the point's
    OWN up axis, which the projector has just tilted to the terrain -- 22 cm up a 13 deg slope moves the
    point 5 cm sideways (measured: a vertical lift put the official points up to 5.4 cm off)."""
    out = _new_like(pts)
    assets = pts.attrs.get(ASSET) or [None] * len(pts)
    for j in range(len(pts)):
        loc, rot, density = pts.loc[j], pts.rot[j], pts.density[j]
        if surface is not None:
            loc, rot, hit = G.project_point(pts.loc[j], pts.rot[j], pts.bounds_min[j], pts.bounds_max[j], surface,
                                            scale=pts.scale[j], quat=pts.quat[j] if pts.quat else None)
            density = density if hit else 0.0
        up = geo.quat_rotate(AS.quat_of(*rot), (0.0, 0.0, LIFT_CM))
        a = assets[j]
        out.add((loc[0] + up[0], loc[1] + up[1], loc[2] + up[2]),
                **_row(pts, j, rot=rot, density=density, **{ASSET_STRING: "" if a is None else str(a)}))
    return out


def transparent(path):
    """The transparent twin's path: `AttributeStringOp_1` then `_2`, `Replace` (every occurrence)."""
    for a, b in REPLACES:
        path = path.replace(a, b)
    return path


def split_vehicles(pts):
    """`FilterDataByAttribute_1`: (vehicle indices, the rest)."""
    strings = pts.attrs.get(ASSET_STRING) or [""] * len(pts)
    veh = [j for j, s in enumerate(strings) if VEHICLE in (s or "")]
    rest = [j for j, s in enumerate(strings) if VEHICLE not in (s or "")]
    return veh, rest


def twins(pts):
    """`AttributeStringOp_1/2` -> `CopyAttributes_0` (`Asset` = the new string) -> `AttributeCast_0`."""
    out = _new_like(pts)
    for j in range(len(pts)):
        s = transparent(pts.attrs[ASSET_STRING][j] or "")
        out.add(pts.loc[j], **_row(pts, j, **{ASSET_STRING: s, ASSET: s}))
    return out


def finish(items, surface):
    """The whole chain; returns `(points items in Gather_0's order, notes)`."""
    projected = [project_lift(p, surface) for p in items]
    veh, rest, copies = [], [], []
    for p in projected:
        v, r = split_vehicles(p)
        if v:
            veh.append(p.take(v))
        if r:
            rest.append(p.take(r))
    copies = [twins(p) for p in veh]
    n = sum(len(p) for p in items)
    notes = ["%d items, %d points in; %d vehicles (+%d transparent twins)"
             % (len(items), n, sum(len(p) for p in veh), sum(len(p) for p in copies))]
    return veh + rest + copies, notes


def run(inputs, params, ctx):
    items = [v for v, _t in inputs.get("Points", []) if isinstance(v, geo.Points)]
    pts, notes = finish(items, _surface(inputs))
    ctx.notes += notes
    return {"Points": [(p, ["Points"]) for p in pts]}
