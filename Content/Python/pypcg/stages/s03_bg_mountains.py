"""Stage 3 -- BG_Mountains (PCG_1_3_BG_Mountains, 远景山体).

Stamps the vista cliffs onto one anchor: every point of the `VistaCliffs_PCG` data asset (read by the
kept `PCGLoadDataAsset_0`) is composed with the anchor transform -- translation (0, 0, AnchorZ),
scale (AnchorScaleXY, AnchorScaleXY, AnchorScaleZ), no rotation -- its roll and pitch are zeroed and
its Z is clamped to [ZMin, ZMax]. Every attribute, `Mesh` above all, is carried through, so the kept
`StaticMeshSpawner_0` (mesh selector by the `Mesh` attribute) spawns the same cliffs. Replaces the
official graph's five computation nodes: `CreatePoints_0` (the anchor), `CopyPoints_0` and the three
`PCGMetadataMathsSettings` (`AttributeMathsOp_0` roll, `_1` pitch, `_2` Z clamp).
See docs/pypcg/stages/s03.md."""
from pypcg.geo import Points
from pypcg.geo.assets import compute_seed
from pypcg.stage_api import Param

STAGE = 3
DOC = """BG_Mountains (远景山体): stamps the vista cliff points (the VistaCliffs_PCG data asset) onto one
anchor at the world origin: each point's X and Y are multiplied by AnchorScaleXY, its Z by AnchorScaleZ
and then moved by AnchorZ; its scale is multiplied the same way; its pitch and roll are set to 0 and
its Z is clamped to [ZMin, ZMax]. The points keep their Mesh attribute for the cliff mesh spawner.
Sizes in cm."""
RANDOM = False
PARAMS = {
    "AnchorZ": Param(-50000.0, "Height of the anchor the cliffs are stamped onto (cm); the official "
                               "CreatePoints_0 translation Z", category="Anchor"),
    "AnchorScaleXY": Param(1.75, "Anchor scale on X and Y: spreads the cliffs out and widens each one",
                           category="Anchor"),
    "AnchorScaleZ": Param(0.5, "Anchor scale on Z: flattens the cliffs and their heights", category="Anchor"),
    "ZMin": Param(-100000.0, "Lowest cliff point Z after the stamp (cm)", category="Clamp"),
    "ZMax": Param(100000.0, "Highest cliff point Z after the stamp (cm)", category="Clamp"),
}
INPUTS = {"Cliffs": "points"}
OUTPUTS = ("Points",)

ANCHOR_SEED = 0                 # CreatePoints_0's point seed; CopyPoints' SeedInheritance is Relative
MESH_ATTR = "Mesh"


def anchor(params):
    """(translation, scale) of the official anchor point, from the parameters."""
    s, sz = float(params["AnchorScaleXY"]), float(params["AnchorScaleZ"])
    return (0.0, 0.0, float(params["AnchorZ"])), (s, s, sz)


def clamp(z, lo, hi):
    """`AttributeMathsOp_2` Clamp: max(lo, min(z, hi))."""
    return max(lo, min(z, hi))


def stamp(src, params):
    """`CopyPoints_0` with one target (Relative rotation and scale, SourceOnly attributes):
    `SourceTransform * TargetTransform` with an identity target rotation is location x target scale +
    target translation, scale x target scale, the source rotation unchanged. Then the three maths
    nodes: roll 0, pitch 0, Z clamped."""
    out = Points()
    for name, tname in src.types.items():
        out.declare(name, tname)
    (tx, ty, tz), (sx, sy, sz) = anchor(params)
    lo, hi = float(params["ZMin"]), float(params["ZMax"])
    for i in range(len(src)):
        x, y, z = src.loc[i]
        a, b, c = src.scale[i]
        kw = {name: column[i] for name, column in src.attrs.items()}
        out.add((x * sx + tx, y * sy + ty, clamp(z * sz + tz, lo, hi)),
                rot=(0.0, src.rot[i][1], 0.0), scale=(a * sx, b * sy, c * sz),
                density=src.density[i], bounds_min=src.bounds_min[i], bounds_max=src.bounds_max[i],
                color=src.color[i], steepness=src.steepness[i],
                seed=compute_seed(int(src.seed[i]), ANCHOR_SEED), **kw)
    return out


def run(inputs, params, ctx):
    out = []
    for value, _tags in inputs.get("Cliffs", []):
        if isinstance(value, Points) and len(value):
            out.append((stamp(value, params), ["Points"]))
    return {"Points": out}
