"""Point-set helpers for the world stages (pypcg.geo values only)."""
from pypcg.geo import ParamSet, Points

MESH_ATTR = "Mesh"         # what the graphs' Spawn_Assets read (UseMeshAttribute, MeshAttribute "Mesh")


def copy_points(p):
    out = Points()
    for c in Points.COLUMNS:
        setattr(out, c, list(getattr(p, c)))
    out.attrs = {k: list(v) for k, v in p.attrs.items()}
    out.types = dict(p.types)
    out.quat = list(p.quat) if getattr(p, "quat", None) else None
    return out


def with_heights(src, lat, ks, attrs=None):
    """src with every point's z taken from its lattice cell (x, y and every attribute -- SourcePositions above all,
    which the terrain writer uses to find the vertex -- unchanged), plus attrs {name: (type, column)}."""
    out = copy_points(src)
    out.loc = [(p[0], p[1], lat.z[k]) for p, k in zip(src.loc, ks)]
    for name, (tname, col) in (attrs or {}).items():
        out.attrs[name] = list(col)
        out.types[name] = tname
    return out


def mesh_points(rows):
    """rows [(loc, rot (pitch, yaw, roll), scale, mesh path)] -> Points carrying each point's mesh."""
    p = Points()
    p.declare(MESH_ATTR, "SoftObjectPath")
    for loc, rot, scale, mesh in rows:
        p.add(tuple(float(v) for v in loc), rot=tuple(float(v) for v in rot), scale=tuple(float(v) for v in scale),
              **{MESH_ATTR: mesh})
    return p


def module_points(instances):
    """building.assemble's instances -> Points carrying each module's mesh and its slot-0 material ("" keeps the
    mesh's own) for the native spawner (MaterialOverrideAttributes ["Mat0"])."""
    p = Points()
    p.declare(MESH_ATTR, "SoftObjectPath")
    p.declare("Mat0", "SoftObjectPath")
    for m in instances:
        p.add(tuple(float(v) for v in m["loc"]), rot=tuple(float(v) for v in m["rot"]),
              scale=tuple(float(v) for v in m["scale"]), **{MESH_ATTR: m["mesh"], "Mat0": m["mat"]})
    return p


def table_points(rows, types):
    """rows [{"loc": (x, y, z), name: value, ...}] -> one point per row with the attributes `types` declares."""
    p = Points()
    for name, tname in types.items():
        p.declare(name, tname)
    for r in rows:
        p.add(tuple(float(v) for v in r["loc"]), **{k: r[k] for k in types})
    return p


def rows_of(points):
    return [dict({"loc": points.loc[i]}, **{n: col[i] for n, col in points.attrs.items()}) for i in range(len(points))]


def _type(v):
    if isinstance(v, bool):
        return "Bool"
    if isinstance(v, int):
        return "Int32"
    if isinstance(v, float):
        return "Double"
    return "String"


def summary(values):
    """The stage's Summary (read by pyworld.py from the run record): scalars only."""
    return ParamSet(dict(values), {k: _type(v) for k, v in values.items()})


def values_tagged(inputs, pin, tag):
    return [v for v, tags in inputs.get(pin, []) if tag in tags]
