"""Editor only: PCG data <-> pypcg.geo values (spec 2.2). UObjects stay in locals (traps.md 25).

Read: Polygon2D -> Polygon, spline -> Spline (control points + the engine's polyline), points ->
Points (all attributes), param data -> ParamSet, any other spatial data -> Terrain (a surface).
Write: Polygon -> MakePolygon2DData (C++), Spline -> PCGSplineData.k2_initialize, Points ->
PCGPointData, ParamSet -> PCGParamData."""
import json
import math

import unreal

from pypcg.geo import ParamSet, Points, Polygon, Spline, drop_closing
from pypcg.ue.terrain import Terrain

L = unreal.PyPCGToolsLibrary
H = unreal.PCGMetadataAccessorHelpers
POLYLINE_TOL = 1.0         # max squared distance (cm2) for spline -> polyline, as the engine's nodes use
_LINEAR = 0                # ESplinePointType::Linear

# (PCGMetadataTypes member, geo type name, accessor suffix)
_SPEC = [("FLOAT", "Float", "float"), ("DOUBLE", "Double", "double"), ("INTEGER32", "Int32", "integer32"),
         ("INTEGER64", "Int64", "integer64"), ("VECTOR2", "Vector2", "vector2"), ("VECTOR", "Vector", "vector"),
         ("VECTOR4", "Vector4", "vector4"), ("QUATERNION", "Quat", "quat"), ("TRANSFORM", "Transform", "transform"),
         ("STRING", "String", "string"), ("BOOLEAN", "Bool", "bool"), ("ROTATOR", "Rotator", "rotator"),
         ("NAME", "Name", "name"), ("SOFT_OBJECT_PATH", "SoftObjectPath", "soft_object_path"),
         ("SOFT_CLASS_PATH", "SoftClassPath", "soft_class_path")]
_BY_ENUM = {getattr(unreal.PCGMetadataTypes, e): (name, suffix) for e, name, suffix in _SPEC
            if hasattr(unreal.PCGMetadataTypes, e)}
_SUFFIX = {name: suffix for _, name, suffix in _SPEC}
_DEFAULT = {"Float": 0.0, "Double": 0.0, "Int32": 0, "Int64": 0, "Vector2": (0.0, 0.0), "Vector": (0.0, 0.0, 0.0),
            "Vector4": (0.0, 0.0, 0.0, 0.0), "Quat": (0.0, 0.0, 0.0, 1.0),
            "Transform": ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)), "String": "", "Bool": False,
            "Rotator": (0.0, 0.0, 0.0), "Name": "None", "SoftObjectPath": "", "SoftClassPath": ""}


# ---- unreal value <-> plain value ------------------------------------------------------------
def _path(v):
    return str(v.export_text()).strip('"')


def _plain(type_name, v):
    if type_name == "Vector":
        return (v.x, v.y, v.z)
    if type_name == "Vector2":
        return (v.x, v.y)
    if type_name in ("Vector4", "Quat"):
        return (v.x, v.y, v.z, v.w)
    if type_name == "Rotator":
        return (v.pitch, v.yaw, v.roll)
    if type_name == "Transform":
        r = v.rotation.rotator()
        return (_plain("Vector", v.translation), (r.pitch, r.yaw, r.roll), _plain("Vector", v.scale3d))
    if type_name in ("SoftObjectPath", "SoftClassPath"):
        return _path(v)
    if type_name == "Name":
        return str(v)
    return v


# `FSoftObjectPath.export_text()` gives the literal string "None" for the null path (probed
# 2026-10-16). `unreal.SoftObjectPath("None")` raises, so the writer must turn it back into the null
# path rather than passing the text through. `pypcg.geo.assets` reads the same spelling.
NULL_PATH = "None"


def _rotator(r):
    return unreal.Rotator(pitch=r[0], yaw=r[1], roll=r[2])          # keywords: positional is (roll, pitch, yaw)


def _ue(type_name, v):
    if type_name == "Vector":
        return unreal.Vector(*v)
    if type_name == "Vector2":
        return unreal.Vector2D(*v)
    if type_name == "Vector4":
        return unreal.Vector4(*v)
    if type_name == "Quat":
        return unreal.Quat(*v)
    if type_name == "Rotator":
        return _rotator(v)
    if type_name == "Transform":
        return unreal.Transform(unreal.Vector(*v[0]), _rotator(v[1]), unreal.Vector(*v[2]))
    if type_name == "SoftObjectPath":
        return unreal.SoftObjectPath() if v == NULL_PATH else unreal.SoftObjectPath(v)
    if type_name == "SoftClassPath":
        return unreal.SoftClassPath() if v == NULL_PATH else unreal.SoftClassPath(v)
    return v


def _infer(v):
    if isinstance(v, bool):
        return "Bool"
    if isinstance(v, int):
        return "Int32"
    if isinstance(v, float):
        return "Double"
    return "String"


# ---- metadata -----------------------------------------------------------------------------------
def _attributes(md):
    names, types = md.get_attributes()
    return [(str(n), _BY_ENUM[t]) for n, t in zip(names, types) if t in _BY_ENUM]


def entry_values(md, key):
    """{attribute: value} of one metadata entry, every supported type (getter chosen by the real
    type, traps.md 36)."""
    p = unreal.PCGPoint()
    p.import_text("(MetadataEntry=%d)" % key)
    return {name: _plain(tname, getattr(p, "get_%s_attribute" % suffix)(md, name))
            for name, (tname, suffix) in _attributes(md)}


def _create(md, name, tname):
    getattr(md, "create_%s_attribute" % _SUFFIX[tname])(name, _ue(tname, _DEFAULT[tname]), False, True)


# ---- read -----------------------------------------------------------------------------------------
def read_params(data_in, pin):
    """{parameter: value} from the getters wired into this pin. Each getter node arrives as its own
    PCGParamData holding one entry with one attribute; when the volume overrides a parameter the
    graph instance arrives as additional entries of the same attribute (the override first), so the
    first non-None value for a name wins (measured 2026-10-15 on the demo level's components)."""
    datas, _ = data_in.get_typed_inputs_by_pin_label(pin, unreal.PCGParamData)
    out = {}
    for d in datas:
        md = d.const_metadata()
        for name, _ in _attributes(md):
            value = entry_values(md, 0)[name]
            if value is not None and name not in out:
                out[name] = value
    return out


def read_pin(data_in, pin):
    datas, tagged = data_in.get_typed_inputs_by_pin_label(pin, unreal.PCGData)
    return [(from_pcg(d), frozenset(str(t) for t in td.get_editor_property("tags"))) for d, td in zip(datas, tagged)]


def from_pcg(d):
    if isinstance(d, unreal.PCGPolygon2DData):
        j = json.loads(L.polygon2d_to_json(d))
        outer = [(p[0], p[1]) for p in j["outer"]]
        z = sum(p[2] for p in j["outer"]) / len(j["outer"]) if j["outer"] else 0.0
        return Polygon(outer, [[(p[0], p[1]) for p in h] for h in j["holes"]], z)
    if isinstance(d, unreal.PCGSplineData):
        j = json.loads(L.spline_data_to_json(d, POLYLINE_TOL))
        ctrl = j["control"]
        linear = all(c["type"] == _LINEAR for c in ctrl)
        poly = [tuple(p) for p in j["polyline"]]
        return Spline([tuple(c["p"]) for c in ctrl], closed=j["closed"], linear=linear,
                      tangents=None if linear else [(tuple(c["arrive"]), tuple(c["leave"])) for c in ctrl],
                      polyline=drop_closing(poly) if j["closed"] else poly)
    if isinstance(d, unreal.PCGParamData):
        md = d.const_metadata()
        attrs = _attributes(md)
        return ParamSet(entry_values(md, 0), {name: tname for name, (tname, _) in attrs})
    if isinstance(d, unreal.PCGBasePointData):
        return _points_of(d)
    if isinstance(d, unreal.PCGSpatialData):
        return Terrain(d)
    raise TypeError("PyPCG cannot read %s" % d.get_class().get_name())


def points_of(d):
    """A PCG point data's points as a plain `Points` (the public name of `_points_of`)."""
    return _points_of(d)


def _points_of(d):
    if not isinstance(d, unreal.PCGPointData):
        d = d.to_point_data()                       # PCGPointArrayData and friends (traps.md 46)
    md = d.const_metadata()
    attrs = _attributes(md)
    out = Points()
    for name, (tname, _) in attrs:
        out.declare(name, tname)
    quats = []
    for p in d.get_points():
        t = p.transform
        q = t.rotation
        quats.append((q.x, q.y, q.z, q.w))
        r = q.rotator()
        kw = {name: _plain(tname, getattr(p, "get_%s_attribute" % suffix)(md, name)) for name, (tname, suffix) in attrs}
        out.add(_plain("Vector", t.translation), rot=(r.pitch, r.yaw, r.roll), scale=_plain("Vector", t.scale3d),
                density=p.density, bounds_min=_plain("Vector", p.bounds_min), bounds_max=_plain("Vector", p.bounds_max),
                color=_plain("Vector4", p.color), steepness=p.steepness, seed=p.seed, **kw)
    out.quat = quats or None
    return out


# ---- write ----------------------------------------------------------------------------------------
def to_pcg(v):
    if isinstance(v, Polygon):
        d = L.make_polygon2d_data(json.dumps({"outer": [[x, y, v.z] for x, y in v.outer],
                                              "holes": [[[x, y, v.z] for x, y in h] for h in v.holes]}))
        if d is None:
            raise ValueError("MakePolygon2DData refused a polygon with %d outer vertices" % len(v.outer))
        return d
    if isinstance(v, Spline):
        return _spline_data(v)
    if isinstance(v, Points):
        return _point_data(v)
    if isinstance(v, ParamSet):
        return _param_data(v)
    raise TypeError("PyPCG cannot write %r" % (v,))


def _spline_data(s):
    T = unreal.SplinePointType
    pts = []
    for i, p in enumerate(s.points):
        sp = unreal.SplinePoint()
        sp.set_editor_property("input_key", float(i))
        sp.set_editor_property("position", unreal.Vector(*p))
        if s.linear:
            sp.set_editor_property("type", T.LINEAR)
        elif s.tangents:
            sp.set_editor_property("type", T.CURVE_CUSTOM_TANGENT)
            sp.set_editor_property("arrive_tangent", unreal.Vector(*s.tangents[i][0]))
            sp.set_editor_property("leave_tangent", unreal.Vector(*s.tangents[i][1]))
        else:
            sp.set_editor_property("type", T.CURVE)
        if s.rotations:
            sp.set_editor_property("rotation", _rotator(s.rotations[i]))
        pts.append(sp)
    d = unreal.PCGSplineData()
    d.k2_initialize(pts, bool(s.closed), unreal.Transform(), [])
    return d


def _point_data(pts):
    d = unreal.PCGPointData()
    md = d.mutable_metadata()
    for name, tname in pts.types.items():
        _create(md, name, tname)
    out = []
    for i in range(len(pts)):
        p = unreal.PCGPoint()
        p.transform = unreal.Transform(unreal.Vector(*pts.loc[i]), _rotator(pts.rot[i]), unreal.Vector(*pts.scale[i]))
        p.density = pts.density[i]
        p.bounds_min = unreal.Vector(*pts.bounds_min[i])
        p.bounds_max = unreal.Vector(*pts.bounds_max[i])
        p.color = unreal.Vector4(*pts.color[i])
        p.steepness = pts.steepness[i]
        p.seed = int(pts.seed[i])
        for name, tname in pts.types.items():
            value = pts.attrs[name][i]
            if value is not None:
                p = getattr(H, "set_%s_attribute" % _SUFFIX[tname])(p, md, name, _ue(tname, value))
        out.append(p)
    d.set_points(out)
    return d


def _param_data(ps):
    d = unreal.PCGParamData()
    md = d.mutable_metadata()
    p = unreal.PCGPoint()
    for name, value in ps.values.items():
        tname = ps.types.get(name) or _infer(value)
        _create(md, name, tname)
        p = getattr(H, "set_%s_attribute" % _SUFFIX[tname])(p, md, name, _ue(tname, value))
    return d

