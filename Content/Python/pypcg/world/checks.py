"""Acceptance of each PyWorld step (spec §5) and the world checks of W10. Pure."""
import math

from . import geom, layout, rules


def accept(n, s, extra=None):
    """Failures of step n from its Summary `s` and the driver's measurements `extra` ({"instances": int, ...});
    [] passes."""
    if not s:
        return ["no Summary: the Python node did not run or its record is missing"]
    extra = extra or {}
    inst = extra.get("instances", 0)
    f = []

    def need(ok, msg):
        if not ok:
            f.append(msg)
    if n == 1:
        need(s["points"] > 0 and s["nan"] == 0, "terrain: %d vertices, %d NaN" % (s["points"], s["nan"]))
        need(s["floor_err_max_cm"] <= 500.0, "valley floor off its axis height by %.0f cm" % s["floor_err_max_cm"])
        need(s["ridge_max_cm"] >= 12000.0, "ridges only %.0f cm high" % s["ridge_max_cm"])
        if extra.get("traced_floor_err_cm") is not None:
            need(extra["traced_floor_err_cm"] <= 800.0, "traced floor off by %.0f cm" % extra["traced_floor_err_cm"])
    elif n == 2:
        need(s["locations"] == len(layout.LOCATIONS), "locations %d" % s["locations"])
        need(s["river_ends"] == 2 and s["exits"] == 2, "river ends %d, exits %d" % (s["river_ends"], s["exits"]))
        need(s["off_terrain"] == 0, "%d locations off the terrain" % s["off_terrain"])
        need(s["max_center_slope_deg"] <= 6.0, "a location centre slopes %.1f deg" % s["max_center_slope_deg"])
    elif n == 3:
        need(s["length_m"] >= 1500.0, "river only %.0f m" % s["length_m"])
        need(s["monotone"], "water line rises somewhere")
        need(s["carved"] > 0, "nothing carved")
        # 用户：水的形状应该更圆润，不应该有那么多直线 (2026-10-27): round bends, no straight reach, no kink
        need(s.get("straight_share", 1.0) < 0.15, "river %.0f %% straight" % (100.0 * s.get("straight_share", 1.0)))
        need(s.get("max_turn_deg", 99.0) < 15.0, "river kinks %.1f deg per 5 m" % s.get("max_turn_deg", 99.0))
        need(extra.get("dynamic_meshes", 0) > 0, "no water surface mesh")
    elif n == 4:
        need(s["connected"] and s["unreachable"] == 0, "network not connected (%d unreachable)" % s["unreachable"])
        need(s["max_grade_main"] <= 0.10 + 1e-6 and s["max_grade_secondary"] <= 0.14 + 1e-6,
             "grades %.3f / %.3f" % (s["max_grade_main"], s["max_grade_secondary"]))
        need(inst > 0, "no road instances")
    elif n == 5:
        need(s["bridges"] >= 1 and s["bridges"] == s["crossings"], "bridges %d for %d crossings" % (s["bridges"], s["crossings"]))
        need(inst > 0, "no bridge instances")
    elif n == 6:
        for key, kind in (("town_min", "Town"), ("village_min", "Village"), ("hamlet_min", "Hamlet")):
            need(s[key] == -1 or s[key] >= rules.MIN_BUILDINGS[kind], "%s %d < %d" % (key, s[key], rules.MIN_BUILDINGS[kind]))
        need(s["churches_min"] >= 1, "a town or village without its church")
        need(s["overlaps"] == 0 and s["on_road"] == 0, "overlaps %d, on roads %d" % (s["overlaps"], s["on_road"]))
        # 建筑模块 (2026-10-27): the style database at work -- several style codes, a door on every street side,
        # bays within their scale range, terraces in the cores
        need(s.get("styles", 0) >= 5, "only %d style codes" % s.get("styles", 0))
        need(s.get("doors_front", -1) == s["buildings"], "%d of %d buildings have their door on the street"
             % (s.get("doors_front", -1), s["buildings"]))
        need(0.8 <= s.get("bay_scale_min", 0.0) and s.get("bay_scale_max", 9.0) <= 1.25,
             "bays scaled %.2f..%.2f" % (s.get("bay_scale_min", 0.0), s.get("bay_scale_max", 9.0)))
        need(s.get("attached", 0) > 0, "no terraces")
        need(inst > 0, "no settlement instances")
    elif n == 7:
        need(s["trees"] >= 20000, "only %d trees" % s["trees"])
        need(s["alder_share_riparian"] > s["alder_share_all"], "alders not concentrated by the river")
        need(s["species_used"] >= 30, "only %d species" % s["species_used"])
        need(min(s["shrubs"], s["grass"], s["ground"], s["debris"], s["rocks"]) > 0, "a layer is empty")
        need(all(s["comm_" + c] > 0 for c in ("forest", "edge", "meadow", "riparian")), "a community is missing")
        need(inst > 0, "no vegetation instances")
    elif n == 8:
        need(s["poles"] > 0 and s["wire_segments"] > 0, "no poles or wires")
        need(35.0 <= s["pole_spacing_mean_m"] <= 45.0, "pole spacing %.1f m" % s["pole_spacing_mean_m"])
        need(inst > 0, "no prop instances")
    elif n == 9:
        need(s["channels"] == 6 and s["weight_sum_err_max"] < 1e-3, "channels %d, weight error %g" % (s["channels"], s["weight_sum_err_max"]))
    return f


def intrusions(points, exclusions):
    """How many points stand on a road or street, in the river, or inside a footprint, plaza, field or bridge."""
    out = {"on_line": 0, "in_river": 0, "in_ring": 0}
    for p in points:
        out["on_line"] += exclusions.line_gap(p[0], p[1]) < 0.0
        out["in_river"] += exclusions.river_gap(p[0], p[1]) < 0.0
        out["in_ring"] += bool(exclusions.rings.contains(p[0], p[1]))
    return out


def crossings(roads, river):
    rp = [r[:2] for r in river]
    return sum(len(geom.polyline_intersections([p[:2] for p in rd["pts"]], rp)) for rd in roads) if len(rp) > 1 else 0


def roads_connected(roads, nodes, touch=300.0):
    """Every node (x, y, radius) has a road point within its radius, and the roads form one network (two roads touch
    where a point of one is within `touch` of the other)."""
    idx = [geom.SegmentIndex(2000.0) for _ in roads]
    for i, rd in enumerate(roads):
        idx[i].add_polyline([p[:2] for p in rd["pts"]])
    parent = list(range(len(roads)))

    def find(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for i, a in enumerate(roads):
        for j in range(len(roads)):
            if j != i and any(idx[j].nearest(p[0], p[1], touch) for p in a["pts"]):
                parent[find(i)] = find(j)
    if len({find(i) for i in range(len(roads))}) > 1:
        return False
    return all(any(math.hypot(p[0] - x, p[1] - y) <= r for rd in roads for p in rd["pts"]) for x, y, r in nodes)


def max_grades(roads):
    out = {}
    for rd in roads:
        g = 0.0
        for a, b in zip(rd["pts"], rd["pts"][1:]):
            d = geom.dist2d(a, b)
            if d > 1.0:
                g = max(g, abs(b[2] - a[2]) / d)
        out[rd["cls"]] = max(out.get(rd["cls"], 0.0), g)
    return out
