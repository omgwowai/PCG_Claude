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
                              TARGET points, before the partition and the copy, in each target's own
                              frame (corrected 2026-10-19, see below)
  TransformPoints_2           add `RandomPositionRange` / `RandomRotationRange` / `RandomScaleRange`,
                              also on the targets
  BoundsFromMesh_0/1          the asset's and the input point's bounds, from the `Asset` attribute
  AttributeMathsOp_6/7        `MeshSize` / `Size` = bounds max - bounds min
  AttributeMathsOp_4/16       `Scale` = the input's `Size` over the asset's = the fit ratio, which
                              `MatchScaleToInputBounds` swaps in for `$Scale`
  AttributeMathsOp_14         `$Extents` (the point property, half the box) x `ExtentsScale`, on every
                              output point -- the box is rewritten as centre +- extents
  Branch_0 / Branch_2         `UseMeshBounds` / `UniformScale` decide whether the asset's bounds and
                              the ratio are applied; `Branch_0`'s input is the copies AND `Reroute_0`
                              (the moved targets), so the targets are part of the output
  AttributeRename_0           the node's `Assets` pin becomes the attribute `Asset`
  Select_1                    `UseMeshAttribute` picks the point's own mesh attribute over the pick
  Branch_1_Index              `UseIndexattribute` picks `IndexAttribute` over the random pick
  AttributeMathsOp_13         `$Seed` += `dataIndex`, on the SOURCE point before the copy

`choose` covers the random pick (`MatchAndSetAttributes_0`); `expand_items` covers everything after
it and returns the primitive's output item for item; `expand` is the copies merged into one point set
plus four report attributes (`$BoundsMin`/`$BoundsMax`/`$Size`/`$Scale`), the form Task 12 shipped.

**Corrected 2026-10-19 (Task 15, stage 17).** The Task 12 helper put the offsets on the ASSEMBLY's
points and wrote the copies target by target. The stage 17 tap of the official primitive
(`pyg_probe_t15_tap.py`: 30 rotated targets, five kits, 9 843 copies; the comparison script is
`Saved/t15_scratch/assign_study.py`) shows otherwise, and the CoreProcess dump agrees
(`FilterDataByType_4 -> TransformPoints_1 -> TransformPoints_2 -> Reroute_0 -> AttributePartition_1 ->
CopyPoints_0.Target`):
  - `PositionOffset` moves each TARGET along its own rotation (`TransformPoints`, non-absolute:
    `RotateVector(offset)`, no scale), and the offset is a float (`FRandRange` returns float): the
    targets come out of the primitive 492.541260 cm from the hull vertex, to 2e-13 cm;
  - the output is one point set per asset, in the order each asset is FIRST PICKED, then the moved
    targets themselves (carrying `Asset` = the assigned path);
  - inside one asset's set the order is SOURCE-major: assembly point 0 on every target of that asset,
    then point 1, ... (target-major is 2.9 km off on the same data, source-major 7e-12 cm);
  - an assembly point whose `Mesh` is the null path keeps it (`"None"`): it is NOT replaced by the
    assigned kit path, or the spawner would spawn the kit a second time from that point;
  - every output box is rewritten as centre +- half-size x `ExtentsScale` (exactly, all 9 843).
Single-target, zero-offset calls -- what Task 12 measured -- come out the same under either reading.

**Fix round 1 (2026-10-19): two more things the oracle found, and what each parameter rests on.**
  - The primitive's own defaults are `UniformScale` TRUE and `UseMeshBounds` TRUE (its user parameters,
    read through ExportGraphIR); Task 12 defaulted both to false. With `UniformScale`, `TransformPoints`
    draws X only, so `ScaleOffset` (0.2, 1, 1) scales a target by 0.2 on every axis (measured).
  - An asset that is a STATIC MESH loads nothing in `PCGLoadDataAsset_0`: the output is the moved
    targets alone (no copy item); with `UseMeshBounds` they take the mesh's box (stage 14, measured).
  - A NEGATIVE scale on either side sends `FTransform::Multiply` down its matrix path
    (`MultiplyUsingMatrixWithScale`); the kits' mirrored props need it (`_compose_matrix`).
  - The offsets and rotations are floats, the scale offset a double (`PCGTransformPoints.cpp`).

Every row below is on disk in `Tools/pypcg/data/assign_oracle_rows.json` (run, call, settings, item
sizes, max difference per field). Per parameter, by the oracle (`pypcg_v1_editor.py {"assign": ...}`, the primitive's own taps on a
live volume; "exact" = Asset, seed, scale and bounds bit for bit, location <= 2.9e-11 cm, quaternion
<= 4.4e-16):
  PositionOffset            MEASURED  s17 Subgraph_2 (Y -492.5, 30 rotated docks); s14 Subgraph_7/8 (Z 3/40)
  RotationOffset            MEASURED  s14 Subgraph_5 (yaw -90, its random ranges zeroed); s17 run A
                                      (pitch 0, yaw 90, roll 0) and run D (pitch 10, yaw -90, roll -20),
                                      both set by the oracle
  ScaleOffset != 1          MEASURED  s17 run A (0.2, 1, 1) uniform, run D (1.414055, 0.6, 0.7) non-uniform;
                                      s15 Subgraph_20 with (1.414055, 1, 1) uniform
  ExtentsScale != 1         MEASURED  s14 Subgraph_7 (1.2, 1, 1); s17 run A (0.7, 1, 1), run D (1.2, 0.5, 2);
                                      s15 Subgraph_20 (0.7, 1, 1)
  UniformScale true / false MEASURED  both, above
  UseMeshBounds true        MEASURED  on static meshes (s14 Subgraph_8, s15 Subgraph_20 with UniformScale)
                                      and on kits (s17 default: kit boxes unchanged)
  UseMeshBounds false       MEASURED  s14 Subgraph_7, s17 run D
  random ranges             DERIVED ONLY  the primitive draws from `TransformPoints_2`'s own seeded
                                      `FRandomStream`; the port draws from `ctx.rng` (spec E2), so no
                                      oracle can compare values. The oracle compares item sizes, order
                                      and `Asset` on random calls (s14 Subgraph_4: equal)
  UseIndexattribute         NOT IMPLEMENTED  `expand` ignores it (`assign_calls` reports it unhonoured);
                                      every official user is also random (s13 / s18 Outer Forest)
  MatchScaleToInputBounds   NOT IMPLEMENTED (no official call sets it)
  UseMeshAttribute          DERIVED ONLY  (no official call sets it)
"""
import math
import struct

DEFAULT_POSITION_RANGE = (0.0, 0.0, 0.0)
DEFAULT_ROTATION_RANGE = (0.0, 0.0, 0.0)
DEFAULT_SCALE_RANGE = (1.0, 1.0, 1.0)
ASSET_ATTR = "Asset"
# The primitive's own defaults for the two switches a call usually leaves alone (Assign_Assets user
# parameters, read through ExportGraphIR 2026-10-19: UseMeshBounds true, UniformScale true).
DEFAULT_UNIFORM_SCALE = True
DEFAULT_USE_MESH_BOUNDS = True
# The report attribute is the asset box's FULL size x ExtentsScale; it is named `$Size` so it is not
# mistaken for the engine's `$Extents` property, which is the HALF-size (Task 15 review).
EXTENTS_ATTR = "$Size"
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


REPORT_ATTRS = (("$BoundsMin", "Vector"), ("$BoundsMax", "Vector"), (EXTENTS_ATTR, "Vector"), ("$Scale", "Vector"))


def expand(targets, table, indices, params):
    """The asset's own points copied onto the target points in world space, every copy carrying `Asset`
    (its own mesh path) and the four report attributes `$BoundsMin`/`$BoundsMax`/`$Size` (the asset box's
    full size x `ExtentsScale`)/`$Scale`.
    Returns a fresh `pypcg.geo.Points`: the copies of `expand_items` merged in their output order,
    WITHOUT the moved targets (the primitive's last output item).

    `targets`  the input point set (`Points`); `table` the loaded assets from `pypcg.ue.assets.load`;
    `indices`  one asset index per target point (-1 = none, the point is dropped), or None when
    `use_mesh_attribute` names the asset instead; `params` the primitive's settings:

      use_mesh_attribute  `UseMeshAttribute`: take the asset from the point's own attribute
      mesh_attribute      that attribute's name, default `Mesh`
      uniform_scale       `UniformScale`, DEFAULT TRUE (the primitive's own default, read 2026-10-19):
                          `TransformPoints_1/2`'s `bUniformScale` -- `ScaleOffset.X` (and one random
                          scale draw) scales all three axes; the fit ratio's X likewise
      use_mesh_bounds     `UseMeshBounds`, DEFAULT TRUE: `Branch_0`'s B side runs `BoundsFromMesh_1` on
                          every output point's own `Asset`. A kit point's box IS its mesh's box (all
                          9 873 stage 17 points kept their box exactly), so only a dock whose `Asset`
                          is a single STATIC MESH changes: it takes that mesh's box
      extents_scale       `ExtentsScale`, a per-axis multiplier on every output point's half-size
      position_offset / rotation_offset / scale_offset   `TransformPoints_1`, applied to each TARGET
                          in its own frame before the copy
      random_position_range / random_rotation_range / random_scale_range   `TransformPoints_2`, on the
                          targets too (one draw per target)
      rng                 the `random.Random` those three draw from; a stage passes `ctx.rng` (the
                          primitive seeds `TransformPoints_2` with its own `Seed` parameter)

    The four `$` attributes are this helper's report, NOT the primitive's output (it writes none of
    them, measured 2026-10-16); `expand_items` is the primitive's output as it is."""
    from .types import Points as _Points

    items = _expand(targets, table, indices, params or {}, report=True)
    out = _Points()
    for name, tname in targets.types.items():
        out.declare(name, tname)
    for name, tname in ((ASSET_ATTR, "SoftObjectPath"),) + REPORT_ATTRS:
        if name not in out.attrs:
            out.declare(name, tname)
    quats = []
    for part in items[:-1]:
        out.extend(part)
        quats += list(part.quat or [])
    out.quat = quats or None
    return out


def expand_items(targets, table, indices, params):
    """The `Assign_Assets` primitive's output, item for item (measured 2026-10-19 on stage 17, see the
    module docstring): one `Points` per assigned asset, in the order each asset is first picked, with
    that asset's points copied onto each of its targets source-major; then the moved targets
    themselves, carrying `Asset` = the assigned path. Arguments as `expand`. An empty list when
    nothing was assigned.

    Every point carries the engine quaternion in `Points.quat` (the composed `Target * Source`), so a
    comparison with the primitive can be made on the rotation itself rather than on a rotator."""
    return _expand(targets, table, indices, params or {}, report=False)


def _f32(v):
    """A double rounded through a C++ float, as `FPCGTransformPointsElement` holds its offsets
    (`const float OffsetX = RandomSource.FRandRange(...)`)."""
    return struct.unpack("f", struct.pack("f", float(v)))[0]


def _box(lo, hi, scale):
    """`AttributeMathsOp_14`: `$Extents *= ExtentsScale`, which rewrites the box as centre +- half-size
    (measured exact on all 9 843 stage 17 copies at a scale of 1)."""
    c = [(lo[a] + hi[a]) / 2.0 for a in range(3)]
    e = [(hi[a] - lo[a]) / 2.0 * scale[a] for a in range(3)]
    return tuple(c[a] - e[a] for a in range(3)), tuple(c[a] + e[a] for a in range(3))


def _moved(targets, i, pos_off, rot_q, scale_off, rng, params, uniform):
    """`TransformPoints_1` (the fixed offsets) then `TransformPoints_2` (the random ranges) on target i:
    non-absolute offset `loc + RotateVector(q, offset)`, rotation `q * offset_q`, scale `s * offset`."""
    from .plane import quat_rotate
    loc = tuple(float(x) for x in targets.loc[i])
    q = tuple(targets.quat[i]) if targets.quat else quat_of(*targets.rot[i])
    s = tuple(float(x) for x in targets.scale[i])
    d = quat_rotate(q, pos_off)
    loc = (loc[0] + d[0], loc[1] + d[1], loc[2] + d[2])
    if rot_q is not None:
        q = _qmul(q, rot_q)
    s = tuple(s[a] * scale_off[a] for a in range(3))
    if rng is not None:
        rp = tuple(_f32(x) for x in _range_draw(params, "random_position_range", rng))
        rr = tuple(_f32(x) for x in _range_draw(params, "random_rotation_range", rng, rotator=True))
        rs = _range_draw(params, "random_scale_range", rng, dlo=DEFAULT_SCALE_RANGE, uniform=uniform)
        d = quat_rotate(q, rp)
        loc = (loc[0] + d[0], loc[1] + d[1], loc[2] + d[2])
        if any(rr):
            q = _qmul(q, quat_of(*rr))
        s = tuple(s[a] * rs[a] for a in range(3))
    return loc, q, s


def _expand(targets, table, indices, params, report):
    from .types import Points as _Points

    n = len(targets)
    if n <= 0 or not table:
        return []

    use_attr = bool(params.get("use_mesh_attribute", False))
    mesh_attr = params.get("mesh_attribute") or MESH_ATTR
    uniform = bool(params.get("uniform_scale", DEFAULT_UNIFORM_SCALE))
    mesh_bounds = bool(params.get("use_mesh_bounds", DEFAULT_USE_MESH_BOUNDS))
    extents_scale = _vector(params.get("extents_scale"), (1.0, 1.0, 1.0))
    pos_off = tuple(_f32(x) for x in _vector(params.get("position_offset"), DEFAULT_POSITION_RANGE))
    rot_off = tuple(_f32(x) for x in _rotator(params.get("rotation_offset")))
    # Offsets and rotations are `const float` in `FPCGTransformPointsElement`; the scale is a double
    # `FVector` (measured: ScaleOffset 0.2 came back as the double 0.2, not 0.20000000298).
    scale_off = _vector(params.get("scale_offset"), DEFAULT_SCALE_RANGE)
    if uniform:                     # `FVector(FRandRange(ScaleMin.X, ScaleMax.X))` (PCGTransformPoints.cpp)
        scale_off = (scale_off[0],) * 3
    rot_q = quat_of(*rot_off) if any(rot_off) else None
    rng = params.get("rng")

    picked = _picked(targets, table, indices, use_attr, mesh_attr)
    valid = [i for i in range(n) if _entry(table, picked[i]) is not None]
    moved = {i: _moved(targets, i, pos_off, rot_q, scale_off, rng, params, uniform) for i in valid}

    # AttributePartition_1: one partition per asset, in the order the asset is first picked.
    order = []
    for i in valid:
        if picked[i] not in order:
            order.append(picked[i])

    items = []
    for a in order:
        entry = table[a]
        assembly = entry.get("points")
        if assembly is None or len(assembly) == 0:
            continue
        if not report and _is_mesh(entry):
            # `PCGLoadDataAsset_0` loads nothing from a STATIC MESH path, so `CopyPoints_0` has no
            # source and the primitive's output is the moved targets alone (measured 2026-10-19 on
            # stage 14's Subgraph_7 / Subgraph_8, one static mesh each: one item, the targets).
            # `expand` (report form) still stands the mesh in as a one-point assembly, as Task 12 did.
            continue
        bounds = bounds_of(assembly) or entry.get("bounds")
        if bounds is None:
            continue
        members = [i for i in valid if picked[i] == a]
        mesh_size = size_of(bounds)
        part = _Points()
        for name, tname in targets.types.items():
            part.declare(name, tname)
        for name, tname in assembly.types.items():
            name = ASSET_ATTR if name == MESH_ATTR else name
            if name not in part.attrs and name not in _Points.COLUMNS:
                part.declare(name, tname)
        if ASSET_ATTR not in part.attrs:
            part.declare(ASSET_ATTR, "SoftObjectPath")
        if report:
            for name, tname in REPORT_ATTRS:
                if name not in part.attrs:
                    part.declare(name, tname)
        quats = []
        for j in range(len(assembly)):
            sq = tuple(assembly.quat[j]) if assembly.quat else quat_of(*assembly.rot[j])
            sloc, sscale = assembly.loc[j], assembly.scale[j]
            bmin, bmax = _box(assembly.bounds_min[j], assembly.bounds_max[j], extents_scale)
            for i in members:
                tloc, tq, ts = moved[i]
                # `CopyPoints`: Out = Source * Target, i.e. T + RotateVector(qT, sT * S); qT * qS; sS * sT.
                wloc, q, wscale = _compose(tloc, tq, ts, sloc, sq, sscale)
                quats.append(q)
                kw = {name: targets.attrs[name][i] for name in targets.types}
                for name in assembly.types:
                    kw[ASSET_ATTR if name == MESH_ATTR else name] = assembly.attrs[name][j]
                kw[ASSET_ATTR] = _point_mesh(assembly, j, entry)
                if report:
                    ratio = fit_ratio((targets.bounds_min[i], targets.bounds_max[i]), mesh_size, uniform)
                    kw["$BoundsMin"] = tuple(bounds[0])
                    kw["$BoundsMax"] = tuple(bounds[1])
                    kw[EXTENTS_ATTR] = tuple(mesh_size[k] * extents_scale[k] for k in range(3))
                    kw["$Scale"] = tuple(ratio)
                # `CopyPoints`' Relative seed inheritance is `ComputeSeed(source, target)`
                # (PCGHelpers.cpp:40-43), measured 2026-10-16 and again on all 9 843 stage 17 copies.
                part.add(wloc, rot=rotator_of(q), scale=wscale, bounds_min=bmin, bounds_max=bmax,
                         density=assembly.density[j], color=assembly.color[j],
                         steepness=assembly.steepness[j],
                         seed=compute_seed(int(assembly.seed[j]), int(targets.seed[i])), **kw)
        part.quat = quats
        items.append(part)

    # `Branch_0` takes `Reroute_0` too: the moved targets, each carrying the assigned path as `Asset`.
    tail = _Points()
    for name, tname in targets.types.items():
        tail.declare(name, tname)
    if ASSET_ATTR not in tail.attrs:
        tail.declare(ASSET_ATTR, "SoftObjectPath")
    quats = []
    for i in valid:
        tloc, tq, ts = moved[i]
        entry = table[picked[i]]
        if mesh_bounds and _is_mesh(entry):
            bmin, bmax = _box(entry["bounds"][0], entry["bounds"][1], extents_scale)
        else:
            bmin, bmax = _box(targets.bounds_min[i], targets.bounds_max[i], extents_scale)
        kw = {name: targets.attrs[name][i] for name in targets.types}
        kw[ASSET_ATTR] = table[picked[i]]["path"]
        tail.add(tloc, rot=rotator_of(tq), scale=ts, bounds_min=bmin, bounds_max=bmax,
                 density=targets.density[i], color=targets.color[i], steepness=targets.steepness[i],
                 seed=int(targets.seed[i]), **kw)
        quats.append(tq)
    tail.quat = quats or None
    if len(tail):
        items.append(tail)
    return items


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


def _compose(tloc, tq, tscale, src_loc, src_q, src_scale):
    """`CopyPoints`' transform rule: the output transform is `Target * Source`, returned as
    `(location, quaternion, scale)`.

    The node's CPU path builds `OutPoint.Transform = SourceTransform * TargetTransform`
    (`PCGCopyPoints.cpp:369`) and the GPU path adds the rotated, scaled source offset to the target
    position (`PCGCopyPoints.usf:66-107`); both mean the same thing for `FTransform::Multiply`
    (`TransformNonVectorized.h:1338-1340`, `Out = B` applied after `A`), namely:

        OutPosition = TargetPosition + QuatRotateVector(TargetRotation, SourcePosition * TargetScale)
        OutRotation = TargetRotation * SourceRotation
        OutScale    = SourceScale * TargetScale

    The rotation of the position is `geo.quat_rotate`, `FQuat::RotateVector` in the engine's own
    operation order. Confirmed against the editor's own output on 2026-10-16 (pyg_probe_t12_one.py /
    pyg_probe_t12_case.py, the pairs recorded in task-12-report.md):
      - the mesh point (-500, -400, -303.79) with an input at (10000, 20000, 0), yaw 90 and scale 1
        landed at (10400, 19500, -303.79), a delta of (+400, -500, -303.79);
      - the same mesh point with an input at the origin and no rotation landed at exactly the mesh
        point plus the input's translation;
      - the same mesh point with an input scale of (2, 1, 1) and yaw 90 landed at (400, -1000,
        -303.79): the input's scale stretches x (to -1000) before the rotation swaps the axes.
    and on 2026-10-19 on all 9 843 copies of stage 17's official call, to 7e-12 cm. Every copied point
    is therefore in world space, measured in the input point's frame; the asset is never scaled by the
    fit ratio."""
    from .plane import quat_rotate
    if any(v < 0.0 for v in tuple(src_scale) + tuple(tscale)):
        return _compose_matrix(tloc, tq, tscale, src_loc, src_q, src_scale)
    d = quat_rotate(tq, (src_loc[0] * tscale[0], src_loc[1] * tscale[1], src_loc[2] * tscale[2]))
    return ((tloc[0] + d[0], tloc[1] + d[1], tloc[2] + d[2]), _qmul(tq, src_q),
            tuple(src_scale[a] * tscale[a] for a in range(3)))


def _matrix(loc, q, scale):
    """`FTransform::ToMatrixWithScale` (row-vector convention: rows are the scaled axes, row 3 the origin)."""
    x, y, z, w = q
    x2, y2, z2 = x + x, y + y, z + z
    xx2, yy2, zz2 = x * x2, y * y2, z * z2
    yz2, wx2, xy2, wz2, xz2, wy2 = y * z2, w * x2, x * y2, w * z2, x * z2, w * y2
    sx, sy, sz = scale
    return [[(1.0 - (yy2 + zz2)) * sx, (xy2 + wz2) * sx, (xz2 - wy2) * sx, 0.0],
            [(xy2 - wz2) * sy, (1.0 - (xx2 + zz2)) * sy, (yz2 + wx2) * sy, 0.0],
            [(xz2 + wy2) * sz, (yz2 - wx2) * sz, (1.0 - (xx2 + yy2)) * sz, 0.0],
            [loc[0], loc[1], loc[2], 1.0]]


def _quat_of_matrix(m):
    """`FQuat(const FMatrix&)` (Quat.h:775), on a scale-free matrix."""
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0.0:
        inv = 1.0 / math.sqrt(tr + 1.0)
        s = 0.5 * inv
        return ((m[1][2] - m[2][1]) * s, (m[2][0] - m[0][2]) * s, (m[0][1] - m[1][0]) * s, 0.5 * (1.0 / inv))
    i = 0
    if m[1][1] > m[0][0]:
        i = 1
    if m[2][2] > m[i][i]:
        i = 2
    j = (1, 2, 0)[i]
    k = (1, 2, 0)[j]
    inv = 1.0 / math.sqrt(m[i][i] - m[j][j] - m[k][k] + 1.0)
    qt = [0.0] * 4
    qt[i] = 0.5 * (1.0 / inv)
    s = 0.5 * inv
    qt[3] = (m[j][k] - m[k][j]) * s
    qt[j] = (m[i][j] + m[j][i]) * s
    qt[k] = (m[i][k] + m[k][i]) * s
    return tuple(qt)


def _compose_matrix(tloc, tq, tscale, src_loc, src_q, src_scale):
    """`FTransform::Multiply` when either side has a NEGATIVE scale (TransformNonVectorized.h:1331):
    `MultiplyUsingMatrixWithScale` -- the two scaled matrices multiplied, the scale removed row by row,
    each axis given back the sign of the product scale, and the rotation read off that matrix
    (`ConstructTransformFromMatrixWithDesiredScale`, :1277). The kits carry mirrored props (negative
    scale on one axis); on those the quaternion product differs from the engine by up to 2.4e-6
    (measured 2026-10-19, stage 17 oracle with a pitch/roll RotationOffset)."""
    a, b = _matrix(src_loc, src_q, src_scale), _matrix(tloc, tq, tscale)
    m = [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]
    desired = tuple(src_scale[k] * tscale[k] for k in range(3))
    for r in range(3):
        sq = m[r][0] * m[r][0] + m[r][1] * m[r][1] + m[r][2] * m[r][2]
        f = 1.0 / math.sqrt(sq) if sq > 0.0 else 1.0
        sign = 1.0 if desired[r] > 0.0 else (-1.0 if desired[r] < 0.0 else 0.0)
        m[r] = [m[r][0] * f * sign, m[r][1] * f * sign, m[r][2] * f * sign, m[r][3]]
    q = _quat_of_matrix(m)
    n = math.sqrt(sum(v * v for v in q))
    q = tuple(v / n for v in q) if n > 0.0 else (0.0, 0.0, 0.0, 1.0)
    return (m[3][0], m[3][1], m[3][2]), q, desired


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
    """The `Asset` of one copied point: the assembly point's own `Mesh` (renamed by `AttributeRename_1`)
    when the assembly carries a `Mesh` attribute AT ALL -- the null path `"None"` included, which the
    primitive keeps (measured 2026-10-19: 30 of stage 17's 9 843 copies are `"None"`, and the spawner
    skips them; replacing them with the kit path would spawn the kit again from each). Only an assembly
    with no mesh attribute (a single `StaticMesh` entry) stands in the assigned path."""
    mesh_attr = MESH_ATTR if MESH_ATTR in assembly.attrs else ASSET_ATTR
    if mesh_attr in assembly.attrs:
        value = assembly.attrs[mesh_attr][j]
        return "None" if value in (None, "") else str(value)
    return entry["path"]


def _is_mesh(entry):
    """A table entry that is one static mesh (`pypcg.ue.assets._from_static_mesh`: one point whose `Mesh`
    is the entry's own path), which `BoundsFromMesh` can read a box from; a `PCGDataAsset` kit is not."""
    pts = entry.get("points")
    return (pts is not None and len(pts) == 1 and entry.get("bounds") is not None
            and (pts.attrs.get(MESH_ATTR) or [None])[0] == entry["path"])


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
