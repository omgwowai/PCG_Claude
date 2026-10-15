"""Editor only: 2D polygon booleans through GeometryScript (Clipper2, the same back end PCG's own
nodes use). Rings are [(x, y)] world cm; results are pypcg.geo.Polygon (outer + holes)."""
import unreal

from pypcg.geo import Polygon, bbox, ccw, enclosing_polygon

PL = unreal.GeometryScript_PolygonList
SP = unreal.GeometryScript_SimplePolygon


def _list(rings):
    simple = [SP.conv_array_of_vector2d_to_geometry_script_simple_polygon([unreal.Vector2D(x, y) for x, y in r])
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


class Ops:
    def intersection(self, rings_a, rings_b):
        return _polygons(PL.polygons_intersection(_list(rings_a), _list(rings_b)))

    def difference(self, rings_a, rings_b):
        return _polygons(PL.polygons_difference(_list(rings_a), _list(rings_b)))

    def union(self, rings):
        return _polygons(PL.polygons_union(_list(rings), True))

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
