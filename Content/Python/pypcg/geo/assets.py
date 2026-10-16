"""Asset assignment (the `Assign_Assets` primitive) as plain values. No unreal import.

The primitive is `/PCGPrimitives/Primitives/Assign/Assign_Assets`; its computation lives in the
subgraph `Assign_Assets_CoreProcess` (82 nodes, dump of 2026-10-16 under `Saved/graph_dumps/`), and
its copy step is the engine's own `CopyPoints` (whose transform rule is
`PCGCopyPoints.usf:66-107` / `PCGCopyPoints.cpp:346-388`). This module is the pure half: the choice
of an asset for each target point, and the expansion of the chosen asset's own points onto the
target. Loading the assets is the editor half (`pypcg.ue.assets`).

What the primitive does, node by node (all inside `Assign_Assets_CoreProcess`):

  FilterDataByType_5/8/9      split the input into points, splines and polygons
  WriteDataIndex_1            `dataIndex` = the index of each input data item
  FilterDataByTag_1           from the loaded asset's entries keep the tag `points`
  AttributeRename_1           that data's `Mesh` attribute becomes `Asset`
  AttributePartition_1        partition that data by `Asset`: one partition per asset
  CopyPoints_0                copy each partition onto the target points; with
                              `bCopyEachSourceOnEveryTarget` false that is N partitions onto 1 target
                              data item, N point sets out. Every output point is in WORLD space:
                              see `_compose` for the rule (measured, not guessed)
  TransformPoints_1           add `PositionOffset` / `RotationOffset` / `ScaleOffset` -- on the
                              ASSEMBLY's points, before the copy, so the offsets move the assembly
                              inside its own frame
  TransformPoints_2           add `RandomPositionRange` / `RandomRotationRange` / `RandomScaleRange`
  BoundsFromMesh_0/1          the asset's and the input point's bounds, from the `Asset` attribute
  AttributeMathsOp_6/7        `MeshSize` / `Size` = bounds max - bounds min
  AttributeMathsOp_4/16       `Scale` = the input's `Size` over the asset's = the fit ratio, which
                              `MatchScaleToInputBounds` swaps in for `$Scale`
  AttributeMathsOp_14         `$Extents` = the asset's bounds size x `ExtentsScale`
  Branch_0 / Branch_2         `UseMeshBounds` / `UniformScale` decide whether the asset's bounds and
                              the ratio are applied
  AttributeRename_0           the node's `Assets` pin becomes the attribute `Asset`
  Select_1                    `UseMeshAttribute` picks the point's own mesh attribute over the pick
  Branch_1_Index              `UseIndexattribute` picks `IndexAttribute` over the random pick
  AttributeMathsOp_13         `$Seed` += `dataIndex`, on the SOURCE point before the copy

`choose` covers the random pick (`MatchAndSetAttributes_0`); `expand` covers the copy, the offsets,
the ratio, the bounds and the seed bump.
"""
import math

DEFAULT_POSITION_RANGE = (0.0, 0.0, 0.0)
DEFAULT_ROTATION_RANGE = (0.0, 0.0, 0.0)
DEFAULT_SCALE_RANGE = (1.0, 1.0, 1.0)
ASSET_ATTR = "Asset"
EXTENTS_ATTR = "$Extents"
MESH_ATTR = "Mesh"        # what the primitive's `MeshAttribute` pin names by default


def stem(path):
    """'/Game/A/SM_B.SM_B' -> 'SM_B'."""
    return str(path).rsplit("/", 1)[-1].split(".", 1)[0]


def choose(n, assets, rng, weights=None):
    """One asset index per target point: uniform over `assets`, drawn from `rng`.

    The primitive's pick is `MatchAndSetAttributes_0` over the `Assets` pin. `weights`, when given, is
    a parallel list of positive weights; the official graphs that weight a kit do it with
    `Filter_RandomChoice` before the primitive, so the default is a plain uniform draw. An empty
    `assets` gives -1 for every point, which `expand` reads as "no asset was drawn"."""
    assets = list(assets)
    n = int(n)
    if not assets:
        return [-1] * n
    if n <= 0:
        return []
    if weights is None:
        return [rng.randrange(len(assets)) for _ in range(n)]
    total = float(sum(weights))
    out = []
    for _ in range(n):
        r = rng.random() * total
        acc = 0.0
        for i, w in enumerate(weights):
            acc += w
            if r < acc:
                out.append(i)
                break
        else:
            out.append(len(assets) - 1)
    return out


# ---- value coercion -----------------------------------------------------------------------------
def _vector(v, default):
    """A 3-vector from None, a scalar, a pair, a triple or a dict of the engine's Vector names."""
    if v is None:
        return tuple(float(x) for x in default)
    if isinstance(v, dict):
        return (float(v.get("X", v.get("x", 0.0))), float(v.get("Y", v.get("y", 0.0))),
                float(v.get("Z", v.get("z", 0.0))))
    if isinstance(v, (int, float)):
        return (float(v),) * 3
    v = tuple(float(x) for x in v)
    if len(v) == 2:
        return v + (0.0,)
    return v[:3]


def _rotator(v):
    """(pitch, yaw, roll) in the engine's order, from a dict of Rotator names or a triple."""
    if v is None:
        return (0.0, 0.0, 0.0)
    if isinstance(v, dict):
        return (float(v.get("Pitch", v.get("pitch", 0.0))), float(v.get("Yaw", v.get("yaw", 0.0))),
                float(v.get("Roll", v.get("roll", 0.0))))
    v = tuple(float(x) for x in v)
    if len(v) == 2:
        return (v[0], v[1], 0.0)
    return v[:3]


def _range_draw(params, key, rng, rotator=False, dlo=DEFAULT_POSITION_RANGE, uniform=False):
    """A random range from `params[key]`, as `TransformPoints_2` reads it.

    The pin takes `min` and `max`; our parameter carries the pair as one value, so a pair-of-pairs is
    read as (min, max) and anything else as a single point (min = max = that value), which is what
    the official graphs mean when they only offset. The rotation range is a Rotator, not a Vector,
    but `TransformPoints` reads its three angles in the same per-axis way, so `_rotator` names them.
    The engine draws X, then Y, then Z (`PCGTransformPoints.cpp:172-192`) and, with `bUniformScale`,
    one number for all three axes."""
    v = params.get(key)
    if v is None:
        span = (dlo, dlo)
    elif isinstance(v, (list, tuple)) and len(v) == 2 and not isinstance(v[0], (int, float)):
        span = (v[0], v[1])
    else:
        span = (v, v)
    if rotator:
        lo, hi = _rotator(span[0]), _rotator(span[1])
    else:
        lo, hi = _vector(span[0], dlo), _vector(span[1], dlo)
    if uniform:
        x = rng.uniform(lo[0], hi[0])
        return (x, x, x)
    return tuple(rng.uniform(lo[a], hi[a]) for a in range(3))


# ---- rotation as quaternions (the engine composes rotations multiplicatively, never additively) --
def quat_of(pitch, yaw, roll):
    """The `FQuat` of an `FRotator`, as `FRotator::Quaternion()` builds it
    (UnrealMath.cpp:462-466, the scalar branch of the same formula)."""
    p, y, r = math.radians(pitch) * 0.5, math.radians(yaw) * 0.5, math.radians(roll) * 0.5
    sp, cp = math.sin(p), math.cos(p)
    sy, cy = math.sin(y), math.cos(y)
    sr, cr = math.sin(r), math.cos(r)
    return (cr * sp * sy - sr * cp * cy,
            -cr * sp * cy - sr * cp * sy,
            cr * cp * sy - sr * sp * cy,
            cr * cp * cy + sr * sp * sy)


def rotator_of(q):
    """The (pitch, yaw, roll) an `FQuat` maps to, through `FRotator(FQuat)`'s matrix."""
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    pitch = math.asin(max(-1.0, min(1.0, 2.0 * (w * y - z * x))))
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    return (math.degrees(pitch), math.degrees(yaw), math.degrees(roll))


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def _qrot(q, v):
    """`QuatRotateVector`: the rotation of `v` by `q`. Verified against the editor's own output on
    2026-10-16: an input point with yaw 90 carries the mesh point (-500, -400, -303.79) to the delta
    (+400, -500, -303.79) -- i.e. to (-source.y, +source.x, source.z). (The (+400, -1000) delta in
    `test_expand_rotates_and_scales_the_position_together` is a different case: the same yaw with an
    input scale of (2, 1, 1), which stretches the source x before the rotation.)"""
    x, y, z, w = q
    vx, vy, vz = v
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx))


# ---- the geometry ------------------------------------------------------------------------------
def bounds_of(points):
    """`([min], [max])` of a point set: the union of its own bounds columns, or None when it is empty.
    This is what `BoundsFromMesh` writes and `AttributeMathsOp_6/7` subtract."""
    n = len(points)
    if n == 0:
        return None
    lo = [min(points.bounds_min[i][a] for i in range(n)) for a in range(3)]
    hi = [max(points.bounds_max[i][a] for i in range(n)) for a in range(3)]
    return (lo, hi)


def size_of(bounds):
    """`AttributeMathsOp_6/7`: bounds max - bounds min; a zero vector when there are no bounds."""
    if bounds is None:
        return (0.0, 0.0, 0.0)
    return tuple(bounds[1][a] - bounds[0][a] for a in range(3))


def fit_ratio(input_bounds, mesh_size, uniform):
    """`AttributeMathsOp_4`/`16`: the input point's own size over the asset's, per axis. An asset axis
    that is zero-sized leaves the ratio at 1 rather than dividing by zero. `UniformScale` uses X for
    all three (`AttributeMathsOp_5` writes one number into `$Scale`).

    The ratio does NOT scale the copied points: measured in the editor, 2026-10-16, with an input box
    of 1000x1000x100 cm against the lane mesh's own 200x200x20 -- the output point kept scale 1 while
    the ratio was 5. The ratio reaches `$Scale` and, through `MatchScaleToInputBounds`, the input
    points' `$Scale`; `expand` reports it as the `$Scale` attribute instead of applying it."""
    own = size_of(input_bounds)
    out = tuple(own[a] / mesh_size[a] if mesh_size[a] else 1.0 for a in range(3))
    if uniform:
        return (out[0],) * 3
    return out


def expand(targets, table, indices, params):
    """The target points carrying `Asset` (a mesh path) and the asset's `$Bounds`/`$Extents`, with the
    asset's own points copied onto them in world space. Returns a fresh `pypcg.geo.Points`.

    `targets`  the input point set (`Points`); `table` the loaded assets from `pypcg.ue.assets.load`;
    `indices`  one asset index per target point (-1 = none, the point is dropped), or None when
    `use_mesh_attribute` names the asset instead; `params` the primitive's settings:

      use_mesh_attribute  `UseMeshAttribute`: take the asset from the point's own attribute
      mesh_attribute      that attribute's name, default `Mesh`
      uniform_scale       `UniformScale`: the ratio's X also scales Y and Z, and a random scale range
                          draws one number for all three axes
      use_mesh_bounds     `UseMeshBounds`: replace the asset's own bounds with the input point's
      extents_scale       `ExtentsScale`, a per-axis multiplier on the asset's `$Extents`
      position_offset / rotation_offset / scale_offset   `TransformPoints_1`, applied to the
                          ASSEMBLY's points in its own frame
      random_position_range / random_rotation_range / random_scale_range   `TransformPoints_2`
      rng                 the `random.Random` those three draw from; a stage passes `ctx.rng` (the
                          primitive seeds `TransformPoints_2` with its own `Seed` parameter)

    Point order is the primitive's: for each input point, its asset's points in table order, so input
    point i's points are contiguous (`CopyPoints` copies one partition per input data item)."""
    from .types import Points as _Points

    params = params or {}
    n = len(targets)
    if n <= 0 or not table:
        return _Points()

    use_attr = bool(params.get("use_mesh_attribute", False))
    mesh_attr = params.get("mesh_attribute") or MESH_ATTR
    uniform = bool(params.get("uniform_scale", False))
    mesh_bounds = bool(params.get("use_mesh_bounds", False))
    extents_scale = _vector(params.get("extents_scale"), (1.0, 1.0, 1.0))
    pos_off = _vector(params.get("position_offset"), DEFAULT_POSITION_RANGE)
    rot_off = _rotator(params.get("rotation_offset"))
    scale_off = _vector(params.get("scale_offset"), DEFAULT_SCALE_RANGE)
    rng = params.get("rng")

    picked = _picked(targets, table, indices, use_attr, mesh_attr)

    out = _Points()
    for name, tname in targets.types.items():
        out.declare(name, tname)
    for name, tname in ((ASSET_ATTR, "SoftObjectPath"), ("$BoundsMin", "Vector"),
                        ("$BoundsMax", "Vector"), (EXTENTS_ATTR, "Vector"), ("$Scale", "Vector")):
        if name not in out.attrs:
            out.declare(name, tname)

    for i in range(n):
        entry = _entry(table, picked[i])
        if entry is None:
            continue
        assembly = entry.get("points")
        if assembly is None or len(assembly) == 0:
            continue
        bounds = bounds_of(assembly) or entry.get("bounds")
        if bounds is None:
            continue
        mesh_size = size_of(bounds)
        ratio = fit_ratio((targets.bounds_min[i], targets.bounds_max[i]), mesh_size, uniform)
        tloc, trot, tscale = targets.loc[i], targets.rot[i], targets.scale[i]
        tq = _quat_of_rot(trot)
        for j in range(len(assembly)):
            loc, rot, scale = assembly.loc[j], assembly.rot[j], assembly.scale[j]
            if rng is not None:
                rp = _range_draw(params, "random_position_range", rng)
                rr = _range_draw(params, "random_rotation_range", rng, rotator=True)
                rs = _range_draw(params, "random_scale_range", rng,
                                 dlo=DEFAULT_SCALE_RANGE, uniform=uniform)
            else:
                rp = rr = (0.0, 0.0, 0.0)
                rs = (1.0, 1.0, 1.0)
            # TransformPoints_1 then TransformPoints_2, both on the assembly in its own frame: the
            # offset is rotated by the assembly's own rotation (`bAbsoluteOffset` is off).
            src_loc = tuple(loc[a] + _rotate_offset(rot, tuple(pos_off[a] + rp[a] for a in range(3)))[a]
                            for a in range(3))
            src_rot = tuple(rot[a] + rot_off[a] + rr[a] for a in range(3))
            src_scale = tuple(scale[a] * scale_off[a] * rs[a] for a in range(3))
            wloc, wrot, wscale = _compose(tloc, tq, tscale, src_loc, src_rot, src_scale)
            kw = {}
            for name in targets.types:
                kw[name] = targets.attrs[name][i]
            # Measured 2026-10-16 (pyg_probe_t12_case.py): with UseMeshBounds OFF the copied point keeps
            # the ASSET's own bounds (the lane mesh's 200x200x20 and the plaza's first point both came
            # through unchanged against an input box of -500..500 x -500..500 x 0..100), which is what
            # `CopyPoints` does -- it copies the source point and only overwrites what `BoundsFromMesh`
            # was asked to overwrite. With it ON the box is the asset's whole bounds.
            kw["bounds_min"] = bounds[0] if mesh_bounds else assembly.bounds_min[j]
            kw["bounds_max"] = bounds[1] if mesh_bounds else assembly.bounds_max[j]
            kw["density"] = assembly.density[j]
            kw["color"] = assembly.color[j]
            kw["steepness"] = assembly.steepness[j]
            # `CopyPoints`' Relative seed inheritance is `ComputeSeed(source, target)`
            # (PCGHelpers.cpp:40-43). Measured 2026-10-16: an assembly point seeded -2111086339 with an
            # input point seeded 42 gave -455695611, and the same assembly with 7 gave 258744612 --
            # both equal `ComputeSeed(assembly, input)`.
            kw["seed"] = compute_seed(int(assembly.seed[j]), int(targets.seed[i]))
            # `AttributeRename_1` turns the loaded data's `Mesh` into `Asset` BEFORE the copy, so the
            # output's `Asset` is the ASSEMBLY POINT's own mesh (measured: a kit assigned as one asset
            # gave SM_Plane_NN_A on point 0 and SM_Cone_C_A on point 2), and only falls back to the
            # assigned path when the point carries no mesh.
            kw[ASSET_ATTR] = _point_mesh(assembly, j, entry)
            kw["$BoundsMin"] = tuple(bounds[0])
            kw["$BoundsMax"] = tuple(bounds[1])
            kw[EXTENTS_ATTR] = tuple(mesh_size[a] * extents_scale[a] for a in range(3))
            kw["$Scale"] = tuple(ratio)
            out.add(wloc, rot=wrot, scale=wscale, **kw)
    return out


_U32 = 0xFFFFFFFF


def _i32(v):
    """Wrap a Python int into the 32-bit signed range the engine's int arithmetic keeps."""
    v &= _U32
    return v - 0x100000000 if v >= 0x80000000 else v


def compute_seed(a, b=None, c=None):
    """`PCGHelpers::ComputeSeed` (PCGHelpers.cpp:35-48), including its int32 wrapping."""
    out = _i32(a * 196314165 + 907633515)
    if b is not None:
        out ^= _i32(b * 73148459 + 453816763)
    if c is not None:
        out ^= _i32(c * 34731343 + 453816743)
    return _i32(out)


def _compose(tloc, tq, tscale, src_loc, src_rot, src_scale):
    """`CopyPoints`' transform rule: the output transform is `Target * Source`.

    The node's CPU path builds `OutPoint.Transform = SourceTransform * TargetTransform`
    (`PCGCopyPoints.cpp:369`) and the GPU path adds the rotated, scaled source offset to the target
    position (`PCGCopyPoints.usf:66-107`); both mean the same thing for `FTransform::Multiply`
    (`TransformNonVectorized.h:1338-1340`, `Out = B` applied after `A`), namely:

        OutPosition = TargetPosition + QuatRotateVector(TargetRotation, SourcePosition * TargetScale)
        OutRotation = TargetRotation * SourceRotation
        OutScale    = SourceScale * TargetScale

    Confirmed against the editor's own output on 2026-10-16 (pyg_probe_t12_one.py /
    pyg_probe_t12_case.py, the pairs recorded in task-12-report.md):
      - the mesh point (-500, -400, -303.79) with an input at (10000, 20000, 0), yaw 90 and scale 1
        landed at (10400, 19500, -303.79), a delta of (+400, -500, -303.79);
      - the same mesh point with an input at the origin and no rotation landed at exactly the mesh
        point plus the input's translation;
      - the same mesh point with an input scale of (2, 1, 1) and yaw 90 landed at (400, -1000,
        -303.79): the input's scale stretches x (to -1000) before the rotation swaps the axes.
    Every copied point is therefore in world space, measured in the input point's frame; the asset is
    never scaled by the fit ratio or by the fixed `ScaleOffset` beyond what `src_scale` already
    carries."""
    mq = quat_of(*src_rot)
    loc = _qrot(tq, tuple(src_loc[a] * tscale[a] for a in range(3)))
    return (tuple(tloc[a] + loc[a] for a in range(3)),
            rotator_of(_qmul(tq, mq)),
            tuple(src_scale[a] * tscale[a] for a in range(3)))


_QUAT_CACHE = {}


def _quat_of_rot(rot):
    key = (round(rot[0], 6), round(rot[1], 6), round(rot[2], 6))
    if key not in _QUAT_CACHE:
        _QUAT_CACHE[key] = quat_of(*rot)
    return _QUAT_CACHE[key]


def _rotate_offset(rot, offset):
    """`TransformPoints`' non-absolute offset: the assembly's own rotation carries the offset."""
    return _qrot(quat_of(*rot), offset)


def _picked(targets, table, indices, use_attr, mesh_attr):
    """The asset index of every target point (`Select_1`, `MatchAndSetAttributes_0/1`).

    `UseMeshAttribute` reads the point's own attribute -- named by `mesh_attribute`, which the
    primitive's `MeshAttribute` pin holds; the official graphs leave it at `Mesh`, the attribute a
    loaded kit point carries -- and finds that path in the table. Otherwise `indices` is the pick
    `choose` drew. A name that is not in the table gives -1, which drops the point rather than
    raising: the official graph's `BoundsFromMesh` only warns about that."""
    n = len(targets)
    if use_attr:
        column = targets.attrs.get(mesh_attr)
        if column is None:
            return [-1] * n
        return [_index_of(table, column[i]) for i in range(n)]
    return list(indices) + [-1] * (n - len(indices)) if indices is not None else [-1] * n


def _point_mesh(assembly, j, entry):
    """The mesh path of one assembly point: its own `Mesh` attribute, else the assigned asset path."""
    mesh_attr = MESH_ATTR if MESH_ATTR in assembly.attrs else ASSET_ATTR
    if mesh_attr in assembly.attrs:
        value = assembly.attrs[mesh_attr][j]
        if value not in (None, "", "None"):
            return str(value)
    return entry["path"]


def _entry(table, index):
    if index is None or index < 0 or index >= len(table):
        return None
    return table[index]


def _index_of(table, path):
    if path is None:
        return -1
    for i, entry in enumerate(table):
        if entry["path"] == path or stem(entry["path"]) == stem(path):
            return i
    return -1
