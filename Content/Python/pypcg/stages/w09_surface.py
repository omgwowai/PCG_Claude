"""PyWorld W9 -- the surface materials (视频步骤 9：道路、河流、平整、手绘的遮罩合成地表材质).

One weight per material channel of the mesh terrain (MPD_Basic: Grass, Rock, ForestFloor, Dirt, Mud, Gravel) for
every vertex: Rock with slope (RockSlopeStart..RockSlopeFull), ForestFloor where W7's trees stand dense, Dirt on roads,
streets, plazas and fields, Mud on the river banks, Gravel in the river bed and on the main roads' shoulders, Grass
for the rest; the weights sum to 1. The native writer paints them (Write_MeshTerrain, Channels)."""
from pypcg.geo import Points, Polygon
from pypcg.stage_api import Param
from pypcg.stages.w03_river import river_rows, terrain_sets
from pypcg.stages.w04_roads import road_rows
from pypcg.world import CHANNELS, geom, points as WP
from pypcg.world.terraform import smoothstep

STAGE = 109
RECORD = "w09"
DOC = """PyWorld W9 Surface (地表材质): Grass, Rock, ForestFloor, Dirt, Mud and Gravel weights per vertex from the
slope, the trees, the roads, streets, plazas, fields and the river."""
RANDOM = False
PARAMS = {"RockSlopeStart": Param(28.0, "Slope where rock starts showing (degrees)", type="Double"),
          "RockSlopeFull": Param(40.0, "Slope that is all rock (degrees)", type="Double"),
          "ForestCell": Param(2000.0, "Cell over which tree density is counted (cm)", type="Double")}
INPUTS = {"Terrain": "points", "Upstream": "any"}
OUTPUTS = ("Terrain", "Summary")


def compose(raw):
    """raw {channel: 0..1} without Grass -> weights summing to 1, Grass taking what is left."""
    total = sum(raw.values())
    if total > 1.0:
        out = {c: v / total for c, v in raw.items()}
        out["Grass"] = 0.0
    else:
        out = dict(raw)
        out["Grass"] = 1.0 - total
    return out


def run(inputs, params, ctx):
    lat, sets = terrain_sets(inputs.get("Terrain", []))
    if not sets:
        return {"Terrain": [], "Summary": [(WP.summary({"channels": 0, "weight_sum_err_max": 0.0}), ["Summary"])]}
    up = inputs.get("Upstream", [])
    lines = geom.SegmentIndex(2000.0)
    for rd in road_rows(up):
        lines.add_polyline([p[:2] for p in rd["pts"]], (0.5 * rd["width"], rd["cls"] == "Main"))
    for v, tags in up:
        if isinstance(v, Points) and "Street" in tags and len(v) > 1:
            lines.add_polyline([p[:2] for p in v.loc], (0.5 * v.attrs["Width"][0], False))
    river = geom.SegmentIndex(2000.0)
    rr = river_rows(up)
    for a, b in zip(rr, rr[1:]):
        river.add(a[:2], b[:2], 0.5 * (a[3] + b[3]))
    plazas, fields = geom.RingIndex(), geom.RingIndex()
    for v, tags in up:
        if isinstance(v, Polygon):
            if "Plaza" in tags:
                plazas.add(v.outer)
            elif "Field" in tags:
                fields.add(v.outer)
    cell = params["ForestCell"]
    buckets = {}
    for v, tags in up:
        if isinstance(v, Points) and "Tree" in tags:
            for x, y, _z in v.loc:
                key = (int(x // cell), int(y // cell))
                buckets[key] = buckets.get(key, 0) + 1
    smooth = {}

    def smoothed(bx, by):
        # trees per cell averaged over the 3 x 3 cells around (bx, by)
        if (bx, by) not in smooth:
            smooth[(bx, by)] = sum(buckets.get((bx + i, by + j), 0) for i in (-1, 0, 1) for j in (-1, 0, 1)) / 9.0
        return smooth[(bx, by)]

    def density(x, y):
        # bilinear between the cell centres, so ForestFloor has no square edges
        fx, fy = x / cell - 0.5, y / cell - 0.5
        bx, by = int(fx // 1), int(fy // 1)
        u, v = fx - bx, fy - by
        a, b = smoothed(bx, by), smoothed(bx + 1, by)
        c, d = smoothed(bx, by + 1), smoothed(bx + 1, by + 1)
        return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
    cache = {}

    def weights(k):
        if k in cache:
            return cache[k]
        x, y = lat.xy(k)
        rock = smoothstep(params["RockSlopeStart"], params["RockSlopeFull"], lat.slope_deg(k))
        dirt = gravel = mud = 0.0
        hit = lines.nearest(x, y, 1500.0)
        if hit is not None:
            hw, main = lines.payload(hit[1])
            dirt = 1.0 - smoothstep(hw + 100.0, hw + 500.0, hit[0])
            if main and hw <= hit[0] < hw + 150.0:
                gravel = 0.6
        if plazas.contains(x, y):
            dirt = 1.0
        elif fields.contains(x, y):
            dirt = max(dirt, 0.8)
        hit = river.nearest(x, y, 4000.0)
        if hit is not None:
            half = river.payload(hit[1])
            if hit[0] < half:
                gravel = 1.0
            else:
                mud = 1.0 - smoothstep(half, half + 600.0, hit[0])
        dens = density(x, y)
        ff = smoothstep(1.0, 4.0, dens)
        w = compose({"Rock": rock, "ForestFloor": ff * (1.0 - rock), "Dirt": dirt, "Mud": mud * (1.0 - dirt),
                     "Gravel": gravel})
        cache[k] = w
        return w
    out, err, cover, n = [], 0.0, {c: 0.0 for c in CHANNELS}, 0
    for v, ks in sets:
        cols = {c: [] for c in CHANNELS}
        for k in ks:
            w = weights(k)
            for c in CHANNELS:
                cols[c].append(w[c])
                cover[c] += w[c]
            err = max(err, abs(sum(w.values()) - 1.0))
            n += 1
        out.append((WP.with_heights(v, lat, ks, {c: ("Float", cols[c]) for c in CHANNELS}), ["Terrain"]))
    summary = {"channels": len(CHANNELS), "weight_sum_err_max": err}
    summary.update({"cover_" + c: cover[c] / n for c in CHANNELS})
    return {"Terrain": out, "Summary": [(WP.summary(summary), ["Summary"])]}
