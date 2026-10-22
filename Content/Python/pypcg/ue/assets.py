"""Editor only: load the assets `Assign_Assets` assigns (the primitive's `Assets` pin).

A `PCGDataAsset` is what the City Sample kits are: a collection of tagged PCG data. The primitive's
`PCGLoadDataAsset_0` (with `bLoadFromInput` on and the `@Last` selector) loads one per input point's
asset reference, then `FilterDataByTag_1` keeps the entries tagged `points` and `AttributeRename_1`
renames their `Mesh` attribute to `Asset`. The other entries of a kit asset (`Root`, `Splines`,
`Polygon2Ds`) are not points and are ignored here, exactly as the primitive's
`FilterDataByType_5/8/9` ignore them.

A `StaticMesh` path gives one point: the mesh itself, carrying its own bounds. That is the shape the
primitive's `BoundsFromMesh` reaches for, and what the graphs that assign a single mesh use.

Bounds come from `UStaticMesh::GetExtendedBounds().GetBox()` — the engine's `GetBoundingBox()`, which
is what `FPCGBoundsFromMeshElement::BoundsFromMesh` reads (`PCGBoundsFromMesh.cpp:239`, 2026-10-16).
`GetBounds()` (the FBoxSphereBounds) is the same box, so either can be probed; this uses
`get_bounding_box()` because it is the exact call the element makes.
"""
import unreal

from pypcg.geo import Points
from pypcg.geo import assets as gassets
from pypcg.ue import convert

# The tag the primitive's FilterDataByTag_1 keeps. The official kits write it capitalised, so both
# spellings are accepted; the primitive compares exactly, and every City Sample kit uses "Points".
POINTS_TAGS = ("Points", "points")
MESH_ATTR = "Mesh"


def is_null_path(exported):
    """"None" is what `FSoftObjectPath.export_text()` gives for the null path (probed 2026-10-16)."""
    return not exported or exported == "None"


def load(paths):
    """[{path, points, bounds, size}] for the given assets, in the order given. Cached per call.

    `path`   the asset path as given (soft-object form, `/Pkg/Obj.Obj`)
    `points` a `pypcg.geo.Points`: for a `PCGDataAsset` every point of its `points` entries (each
             carrying its `Mesh`); for a `StaticMesh` one point at the origin with the mesh's bounds
    `bounds` `([min], [max])` of those points' own bounds, or None when the asset has none
    `size`   `bounds` max - min, the `AttributeMathsOp_6/7` value

    An asset that does not load, or that is neither a `PCGDataAsset` nor a `StaticMesh`, gives an
    entry with `points` empty and a `note` saying why; the caller decides whether that is fatal.
    """
    cache = {}
    out = []
    for path in paths:
        key = str(path)
        if key not in cache:
            cache[key] = _load_one(key)
        out.append(cache[key])
    return out


def _load_one(path):
    entry = {"path": path, "points": Points(), "bounds": None, "size": (0.0, 0.0, 0.0), "note": ""}
    obj = unreal.EditorAssetLibrary.load_asset(path)
    if obj is None:
        entry["note"] = "the asset did not load"
        return entry
    if isinstance(obj, unreal.PCGDataAsset):
        return _from_data_asset(entry, obj)
    if isinstance(obj, unreal.StaticMesh):
        return _from_static_mesh(entry, obj)
    entry["note"] = "not a PCGDataAsset or StaticMesh but a %s" % obj.get_class().get_name()
    return entry


def _from_data_asset(entry, obj):
    collection = obj.get_editor_property("data")
    kept = 0
    for tagged in collection.get_editor_property("tagged_data"):
        tags = [str(t) for t in tagged.get_editor_property("tags")]
        if not any(t in POINTS_TAGS for t in tags):
            continue
        data = tagged.get_editor_property("data").get_editor_property("data")
        if data is None or not isinstance(data, unreal.PCGBasePointData):
            continue
        merged = convert.points_of(data)
        entry["points"].extend(merged)
        kept += 1
    if kept == 0:
        entry["note"] = "no entry tagged %s" % (POINTS_TAGS[0],)
    entry["bounds"] = gassets.bounds_of(entry["points"])
    entry["size"] = gassets.size_of(entry["bounds"])
    return entry


def _from_static_mesh(entry, obj):
    b = obj.get_bounding_box()
    bounds = ((b.min.x, b.min.y, b.min.z), (b.max.x, b.max.y, b.max.z))
    entry["points"].declare(MESH_ATTR, "SoftObjectPath")
    entry["points"].add((0.0, 0.0, 0.0), bounds_min=bounds[0], bounds_max=bounds[1],
                        **{MESH_ATTR: entry["path"]})
    entry["bounds"] = bounds
    entry["size"] = gassets.size_of(bounds)
    return entry
