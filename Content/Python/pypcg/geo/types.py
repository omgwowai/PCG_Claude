"""The values a Python stage reads and writes (spec 2.2). World cm, no unreal import."""
from dataclasses import dataclass, field

MAX_RECORDED_POINTS = 20000          # larger point sets are recorded as a summary only


@dataclass
class Polygon:
    """An area: outer and holes are [(x, y)] rings, outer counter-clockwise (positive shoelace
    area); z is the height the area sits at."""
    outer: list
    holes: list = field(default_factory=list)
    z: float = 0.0


@dataclass
class Spline:
    """points: [(x, y, z)] control points. linear: straight segments; otherwise tangents holds
    (arrive, leave) per point, or None for automatic tangents. polyline: the dense world polyline
    the engine draws (filled on inputs, ignored on outputs). rotations: optional per-point
    (pitch, yaw, roll) in degrees, the spline point's own rotation; None writes the identity (the
    engine's default). Official `Create_Spline_Shape` output carries one per vertex and readers
    downstream see it (stage 4, measured 2026-10-19)."""
    points: list
    closed: bool = False
    linear: bool = True
    tangents: list = None
    polyline: list = None
    rotations: list = None


@dataclass
class ParamSet:
    """One attribute-set entry: values {name: value}, types {name: metadata type name}."""
    values: dict
    types: dict = field(default_factory=dict)


class Points:
    """PCG points as columns. loc/scale are (x, y, z); rot is (pitch, yaw, roll) in degrees; color is
    (r, g, b, a). attrs {name: [value per point]}, types {name: metadata type name} such as "Double",
    "String", "SoftObjectPath"."""
    DEFAULTS = {"rot": (0.0, 0.0, 0.0), "scale": (1.0, 1.0, 1.0), "density": 1.0,
                "bounds_min": (-1.0, -1.0, -1.0), "bounds_max": (1.0, 1.0, 1.0),
                "color": (1.0, 1.0, 1.0, 1.0), "steepness": 0.5, "seed": 0}
    COLUMNS = ("loc",) + tuple(DEFAULTS)

    def __init__(self):
        for c in self.COLUMNS:
            setattr(self, c, [])
        self.attrs = {}
        self.types = {}
        # Optional: the engine's own rotation quaternion (x, y, z, w) per point, filled by
        # convert._points_of. `rot` is a rotator derived from it and cannot be turned back into the
        # same bits (measured 2026-10-19), so a stage that must reproduce the engine's placement
        # bit for bit reads this. Not carried by take()/extend().
        self.quat = None

    def __len__(self):
        return len(self.loc)

    def declare(self, name, type_name, default=None):
        if name in self.COLUMNS or name in self.attrs:
            raise KeyError("point attribute %r is a point property or already declared" % name)
        self.attrs[name] = [default] * len(self)
        self.types[name] = type_name

    def add(self, loc, **kw):
        unknown = sorted(set(kw) - set(self.DEFAULTS) - set(self.attrs))
        if unknown:
            raise KeyError("undeclared point attribute(s) %s" % unknown)
        self.loc.append(tuple(float(v) for v in loc))
        # `quat` is the engine's per-point quaternion, valid only for the points convert read; a point
        # added afterwards has none, so a partial column would mislabel it -- drop the whole column.
        self.quat = None
        for c, default in self.DEFAULTS.items():
            getattr(self, c).append(kw.get(c, default))
        for name, column in self.attrs.items():
            column.append(kw.get(name))

    def take(self, indices):
        out = Points()
        for name, type_name in self.types.items():
            out.declare(name, type_name)
        for i in indices:
            kw = {c: getattr(self, c)[i] for c in self.DEFAULTS}
            kw.update({n: column[i] for n, column in self.attrs.items()})
            out.add(self.loc[i], **kw)
        return out

    def extend(self, other):
        """Append `other`'s points to this one, declaring any attribute this one does not have yet
        (a name that is a point column is skipped: the column carries it)."""
        for name, type_name in other.types.items():
            if name not in self.COLUMNS and name not in self.attrs:
                self.declare(name, type_name)
        for i in range(len(other)):
            kw = {c: getattr(other, c)[i] for c in self.DEFAULTS}
            kw.update({n: column[i] for n, column in other.attrs.items()})
            self.add(other.loc[i], **kw)
        return self


def values(items):
    """The values of a list of (value, tags) items."""
    return [v for v, _ in items]


def with_tag(items, tag):
    return [v for v, tags in items if tag in tags]


def _tuples(seq):
    return [tuple(x) if isinstance(x, list) else x for x in seq]


def to_json(v):
    if isinstance(v, Polygon):
        return {"kind": "polygon", "outer": [list(p) for p in v.outer], "holes": [[list(p) for p in h] for h in v.holes], "z": v.z}
    if isinstance(v, Spline):
        d = {"kind": "spline", "points": [list(p) for p in v.points], "closed": v.closed, "linear": v.linear,
             "tangents": [[list(a), list(b)] for a, b in v.tangents] if v.tangents else None,
             "polyline": [list(p) for p in v.polyline] if v.polyline else None}
        if v.rotations:                  # only when set, so records written before the field still compare
            d["rotations"] = [list(r) for r in v.rotations]
        return d
    if isinstance(v, ParamSet):
        return {"kind": "params", "values": dict(v.values), "types": dict(v.types)}
    if isinstance(v, Points):
        d = {"kind": "points", "n": len(v), "types": dict(v.types)}
        if len(v) > MAX_RECORDED_POINTS:
            xs, ys, zs = zip(*v.loc)
            d.update(truncated=True, bbox=[[min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]])
            return d
        d.update({c: [list(x) if isinstance(x, tuple) else x for x in getattr(v, c)] for c in Points.COLUMNS})
        d["attrs"] = {k: list(col) for k, col in v.attrs.items()}
        if v.quat:                       # only when set, so older records still compare equal
            d["quat"] = [list(q) for q in v.quat]
        return d
    return {"kind": type(v).__name__}              # e.g. a terrain surface: not recordable


def from_json(d):
    kind = d.get("kind")
    if kind == "polygon":
        return Polygon(_tuples(d["outer"]), [_tuples(h) for h in d["holes"]], d.get("z", 0.0))
    if kind == "spline":
        return Spline(_tuples(d["points"]), d["closed"], d["linear"],
                      [(tuple(a), tuple(b)) for a, b in d["tangents"]] if d.get("tangents") else None,
                      _tuples(d["polyline"]) if d.get("polyline") else None,
                      _tuples(d["rotations"]) if d.get("rotations") else None)
    if kind == "params":
        return ParamSet(dict(d["values"]), dict(d["types"]))
    if kind == "points" and not d.get("truncated"):
        p = Points()
        for c in Points.COLUMNS:
            setattr(p, c, _tuples(d[c]))
        p.types = dict(d["types"])
        p.attrs = {k: list(col) for k, col in d["attrs"].items()}
        p.quat = _tuples(d["quat"]) if d.get("quat") else None
        return p
    raise ValueError("cannot rebuild a %s value from its record" % kind)
