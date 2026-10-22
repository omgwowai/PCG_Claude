"""Editor only: 2D polygon booleans through GeometryScript (Clipper2, the same back end PCG's own
nodes use). Rings are [(x, y)] world cm; results are pypcg.geo.Polygon (outer + holes)."""
import unreal

from pypcg.geo import Polygon, bbox, ccw, enclosing_polygon

PL = unreal.GeometryScript_PolygonList
SP = unreal.GeometryScript_SimplePolygon


def _list(rings):
    simple = [SP.conv_array_of_vector2d_to_geometry_script_simple_polygon([_v2(p) for p in r])
              for r in rings]
    return PL.create_polygon_list_from_simple_polygons(simple)


def _polygons(pl):
    out = []
    for i in range(PL.get_polygon_count(pl)):
        outer, _always_false = PL.get_polygon_vertices(pl, i, -1)      # 5.8 never sets the valid flag (spike)
        hole_count, _valid = PL.get_polygon_hole_count(pl, i)           # int return plus a bool out-param (the valid flag is not trusted)
        holes = [[(v.x, v.y) for v in PL.get_polygon_vertices(pl, i, h)[0]] for h in range(hole_count)]
        out.append(Polygon([(v.x, v.y) for v in outer], holes))
    return out


def _checked(what, out, ok, rings):
    """GeometryScript's success flag is not trusted on its own (it is read as advisory throughout this file),
    but a FALSE flag with an EMPTY result is the silent-zero case: log it, so it is in the editor log
    (final review M12). The result is returned unchanged."""
    polys = _polygons(out)
    if not ok and not polys:
        unreal.log_warning("PyPCG ops.%s: GeometryScript reported failure and returned no polygon (%d input "
                           "ring(s)); the stage sees an empty result" % (what, len(rings)))
    return polys


def _closed(path):
    return len(path) > 1 and abs(path[0][0] - path[-1][0]) < 1e-9 and abs(path[0][1] - path[-1][1]) < 1e-9


def _v2(p):
    """A path point as Vector2D. Points may carry a third coordinate from `geo.plane.clip_path`; the
    booleans are 2D, so Z is dropped here and nowhere else."""
    return unreal.Vector2D(float(p[0]), float(p[1]))


class Ops:
    def assets(self, paths):
        """The loaded kits `Assign_Assets` assigns (`pypcg.ue.assets.load`): a stage reaches the asset
        registry only through here, so its module stays pure (ruling N2). Stage 17 is the first user."""
        from pypcg.ue import assets as _assets
        return _assets.load(paths)

    def rotator_quat(self, pitch, yaw, roll):
        """`FRotator::Quaternion()` as the ENGINE computes it (its vectorised path calls SVML's sincos, which
        differs from Python's `math.sin` / `math.cos` in the last bit). The rotator is built by attribute
        assignment: `unreal.Rotator(p, y, r)` rounds every component to float32 (probed 2026-10-20, as trap 73
        found for `unreal.Quat`). Stage 16 first: the park centre's `$Rotation` is set from a rotator
        (`Place_Point_AtCenter_CoreProcess_Loop`, `CopyAttributes_4`), and the Met building reads the last bit."""
        r = unreal.Rotator()
        r.pitch, r.yaw, r.roll = float(pitch), float(yaw), float(roll)
        q = r.quaternion()
        return (q.x, q.y, q.z, q.w)

    def intersection(self, rings_a, rings_b):
        return _polygons(PL.polygons_intersection(_list(rings_a), _list(rings_b)))

    def difference(self, rings_a, rings_b):
        return _polygons(PL.polygons_difference(_list(rings_a), _list(rings_b)))

    def union(self, rings):
        return _polygons(PL.polygons_union(_list(rings), True))

    def offset(self, rings, distance, join="square", miter_limit=2.0):
        """`OffsetPolygon2D`: push each ring's edges out by `distance` (inward negative, outward
        positive). The primitive's node is Clipper2's `InflatePaths`; its settings leave the join at
        the default (square, miter limit 2), which is what every PCGPrimitives caller here uses.
        `polygons_offset` returns `(polygon_list, operation_success)` (probed 2026-10-16); the flag is
        not trusted, matching how the other booleans in this file are read, except that a false flag
        with an empty result is logged (`_checked`)."""
        opts = unreal.GeometryScriptPolygonOffsetOptions()
        opts.set_editor_property("join_type", unreal.GeometryScriptPolyOffsetJoinType.SQUARE
                                 if join == "square" else unreal.GeometryScriptPolyOffsetJoinType.MITER)
        opts.set_editor_property("miter_limit", float(miter_limit))
        out, ok = PL.polygons_offset(_list(rings), opts, float(distance), True)
        return _checked("offset", out, ok, rings)

    def path_offset(self, path, distance, end="butt", join="square", miter_limit=2.0):
        """`CreatePolygon2D(ForceOpen, OpenPolygonWidth)`: close an open path into the area within
        `distance` of it. This is `UE::Geometry::PolygonsOffset` on an open poly-path
        (`PCGCreatePolygon2D.cpp:243-269`), which GeometryScript exposes as
        `CreatePolygonsFromPathOffset` with an `FGeometryScriptOpenPathOffsetOptions`.

        `EndType` is the one thing the PCG node sets from its own settings: `Butt` caps the path
        square at both ends, which is what `Transform_Outline` leaves in place."""
        opts = unreal.GeometryScriptOpenPathOffsetOptions()
        opts.set_editor_property("join_type", unreal.GeometryScriptPolyOffsetJoinType.SQUARE
                                 if join == "square" else unreal.GeometryScriptPolyOffsetJoinType.MITER)
        opts.set_editor_property("end_type", getattr(unreal.GeometryScriptPathOffsetEndType, end.upper(),
                                                     unreal.GeometryScriptPathOffsetEndType.BUTT))
        opts.set_editor_property("miter_limit", float(miter_limit))
        ring = [_v2(p) for p in (path[:-1] if _closed(path) else path)]
        out, ok = PL.create_polygons_from_path_offset(ring, opts, float(distance), True)
        return _checked("path_offset", out, ok, [ring])

    def cut_with_paths(self, ring, paths):
        """Polygon2DOperation(CutWithPaths): the booleans run in the subject polygon's own plane frame,
        like the engine (origin at the vertex mean, yaw -90), because Clipper quantises in that frame
        and the quantisation decides each piece's start vertex (spike detail G3)."""
        n = len(ring)
        cx, cy = sum(q[0] for q in ring) / n, sum(q[1] for q in ring) / n

        def to_l(q):
            return (cy - q[1], q[0] - cx)

        def to_w(q):
            return (cx + q[1], cy - q[0])

        lring = [to_l(q) for q in ring]
        bb = bbox(lring)
        clips = [_list([enclosing_polygon([to_l(q) for q in p], bb)]) for p in paths if len(p) >= 2]
        cur = [lring]
        for c in clips:
            nxt = []
            for r in cur:
                g = _list([r])
                nxt += [p.outer for p in _polygons(PL.polygons_intersection(g, c))]
                nxt += [p.outer for p in _polygons(PL.polygons_difference(g, c))]
            cur = nxt
        return [ccw([to_w(q) for q in r]) for r in cur if len(r) >= 3]
