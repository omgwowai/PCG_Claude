"""Stage 11 -- Buildings, last Python node: the rooftops (`s11_buildings_rooftops`).

After the kept native building nodes: `Tag_SmallRooftops` / `Tag_MediumRooftops` / `Tag_LargeRooftops` add the
class tag the rooftop stage filters on (stage 12: FilterByTag), the medium and large ones gathered as
officially (`Gather_6`: `SetComplexBuildings` footprints first, then `Assign_CitySampleBuildings` rooftops;
`Gather_3` the same); `Gather_4` puts the three classes together and `Branch_3` (Partitioned false) sends them
down a chain of twelve `Filter_RandomChoice` nodes (`Subgraph_4` .. `Subgraph_19`, one Bernoulli per rooftop,
ratios 1/13 .. 1/2), the selected side of each to one of the thirteen kept `Create_Mesh_Planar` rooftop meshes,
the last unselected to the thirteenth. Every rooftop is handed back as the very spline the building node made
(`FORWARD_SPLINES`: stage 12 reads their last bits, traps.md 62). `docs/pypcg/stages/s11.md` step 6."""
from pypcg import geo
from pypcg.geo import Polygon, Spline

STAGE = 11
RECORD = "s11_rooftops"
DOC = """Buildings (建筑), rooftops: the class tag on every rooftop outline, and one rooftop material each."""
RANDOM = True
FORWARD_SPLINES = True
PARAMS = {}
INPUTS = {"SmallRoofs": "spline", "MediumRoofs": "spline", "LargeRoofs": "spline"}
CLASS_TAGS = (("SmallRoofs", "SmallRooftops"), ("MediumRoofs", "MediumRooftops"), ("LargeRoofs", "LargeRooftops"))
# The chain in order: (Filter_RandomChoice node, Ratio, its Selected side's mesh node, material); the last
# node's Unselected side goes to Subgraph_31 (TarPebbles_WFC). The Seeds (2000, 2031, ...) are the engine's;
# the draws here are Python's own (spec E2).
CHAIN = (("Subgraph_4", 0.076923, "Subgraph_0", "BitumenRoofing"),
         ("Subgraph_8", 0.083333, "Subgraph_20", "BitumenRoofing_QBAA"),
         ("Subgraph_9", 0.090909, "Subgraph_21", "BitumenRoofing_WFC"),
         ("Subgraph_11", 0.1, "Subgraph_22", "DirtyConcreteTiles"),
         ("Subgraph_12", 0.111111, "Subgraph_23", "DirtyConcreteTiles_WFC"),
         ("Subgraph_13", 0.125, "Subgraph_24", "PebbleDash"),
         ("Subgraph_14", 0.142857, "Subgraph_25", "PebbleDash_WFC"),
         ("Subgraph_15", 0.166667, "Subgraph_26", "PebbleDashLines"),
         ("Subgraph_16", 0.2, "Subgraph_27", "PebbleDashLines_WFC"),
         ("Subgraph_17", 0.25, "Subgraph_28", "RoofTile"),
         ("Subgraph_18", 0.333333, "Subgraph_29", "RoofTile_WFC"),
         ("Subgraph_19", 0.5, "Subgraph_30", "TarPebbles"))
LAST = ("Subgraph_31", "TarPebbles_WFC")
MESHES = tuple((mesh, "Roof_" + mat) for _n, _r, mesh, mat in CHAIN) + ((LAST[0], "Roof_" + LAST[1]),)
OUTPUTS = tuple(tag for _pin, tag in CLASS_TAGS) + tuple(pin for _mesh, pin in MESHES)


class Draws:
    """The rooftop materials' draws (stage 9's design): `keep(step, items, ratio)` is one
    `Filter_RandomChoice` (`RandomPerDataset`: one Bernoulli per rooftop, `geo.keep_each`)."""

    def __init__(self, rng):
        self.rng = rng

    def keep(self, step, items, ratio):
        return geo.keep_each(len(items), ratio, self.rng)


def materials(items, draws):
    """[(mesh pin, [(value, tags)])] in the chain's order: each node keeps its share, the rest go on."""
    out = []
    rest = list(items)
    for node, ratio, _mesh, mat in CHAIN:
        flags = draws.keep(node, rest, ratio)
        out.append(("Roof_" + mat, [it for it, f in zip(rest, flags) if f]))
        rest = [it for it, f in zip(rest, flags) if not f]
    out.append(("Roof_" + LAST[1], rest))
    return out


def rooftops(inputs, draws):
    out = {pin: [] for pin in OUTPUTS}
    gathered = []
    for pin, tag in CLASS_TAGS:
        items = [(v, sorted(set(t) | {tag})) for v, t in inputs.get(pin, []) if isinstance(v, (Spline, Polygon))]
        out[tag] = items
        gathered += items
    for mesh_pin, items in materials(gathered, draws):
        out[mesh_pin] = items
    return out


def run(inputs, params, ctx):
    out = rooftops(inputs, Draws(ctx.rng))
    ctx.notes.append("rooftops: %s; materials %s" % (
        ", ".join("%s %d" % (tag, len(out[tag])) for _p, tag in CLASS_TAGS),
        " ".join(str(len(out[pin])) for _m, pin in MESHES)))
    return out
