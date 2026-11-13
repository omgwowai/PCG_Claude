# cs_cloud_code.py -- the parameter tables and the HLSL of the City Sample cloud material M_CS_CumulusCloud, version 2
# (2026-11-12, docs/superpowers/specs/2026-11-12-cs-cloud-motion-design.md §2). One density body is expanded into slot A
# (the parameter names every saved material instance already uses) and slot B (the same names with "B_"). Each slot has
# its own height layer, found from the sample's absolute altitude, and its own time inputs; the two are summed into one
# extinction. Pure Python, no unreal import: cs_sky_assets.py builds the graph from it, Tools/cs_weather/check_art.py and
# the offline tests (Tools/cs_weather/tests) read it, and the cloud director (cs_cloud_motion.py) names its parameters
# after it.
#
# Density parameters (km units; heights of the art features are km above the slot's layer bottom):
#   StretchX / StretchAngle / ShearKm  -- noise sampled in a frame rotated to StretchAngle (deg from +X) and stretched
#                                         StretchX times along it, sheared ShearKm per layer height (cirrus fibres / hooks)
#   CellX ... CellSolid                -- one storm cell (cumulonimbus): full coverage inside CellRadiusKm, tops at
#                                         CellTopH; above AnvilBottom the radius grows to AnvilRadiusKm and drifts
#                                         AnvilShiftKm along StretchAngle (the anvil); CellLumpKm / CellLumpAmp modulate
#                                         the radius with low-frequency noise; CellSolid fills the cell interior
#   BaseKm                             -- cloud base above the layer bottom (the rain under a storm needs the space)
#   RainDensity ... RainSlantKm        -- a rain shaft from the ground into the cloud base
#   AnvilRamp, OvershootKm, OvershootRadiusKm, TurretAmt, TurretScaleKm -- flat anvil underside, overshooting top, turrets
#   MammaAmt, MammaScaleKm, MammaDepthKm -- pouches hanging under the anvil, outside the core
#   BillowAmt, BillowScaleKm           -- inverted-Worley bubbles on ordinary cumulus
#   PowderAmt, PowderK                 -- Beer-Powder darkening of thin edges with the sun behind the viewer
#   MackerelAmt ... MackerelStretch    -- a cellular coverage field (altocumulus cells in rows)
#   RollAmt, RollSpacingKm, RollAngle  -- horizontal convective rolls (cloud streets)
#   FrontAmt ... FrontDensity          -- a shelf cloud: a wedge along a gust front whose face steps back with height
#   LensAmt ... LensCut                -- lenticular stacks on the weather map's cells above LensCut
#   StormAO                            -- sky-light occlusion inside the storm cell, its mammatus and the lower shelf cloud
# v2 per-slot inputs (SLOT_EXTRA): ExtinctionMax (moved into the node), BottomKm (absolute layer bottom, km), SlotOn,
# and the time inputs: AdvX / AdvY (km the air has moved), DetailOff* / Detail2Off* (wrapped UV offsets of the two detail
# lookups), EvoAmt / EvoScaleKm / EvoPhase (in-place evolution), Boil* and *Phase / RainFall (vertical drift or morph of
# single lookups). Every v2 default leaves every static look unchanged.
# Cons, the conservative density, is evaluated at every ray-march sample (UpdateMaterialCloudParam), so it reads an
# evolution-free upper bound of the coverage (covC = cov x (1 + 2 EvoAmt) through the same monotonic steps, topHC,
# rampTC): the evolution term's two fetches then run only where Cons > 0. At EvoAmt 0 it equals the old Cons.
import re

# name, default, group -- unchanged from cs_sky_assets.SCALARS as of 2026-11-11
SCALARS = [
    ("WeatherScaleKm", 32.0, "Layout"), ("ShapeScaleKm", 5.0, "Layout"), ("DetailScaleKm", 0.6, "Layout"),
    ("WarpKm", 1.5, "Layout"), ("WarpScaleKm", 15.0, "Layout"),
    ("CoverageBias", 0.0, "Coverage"), ("CoverageScale", 1.0, "Coverage"),
    ("DetailStrength", 0.5, "Shape"), ("DensityScale", 1.0, "Shape"),
    ("TypeMin", 0.3, "Shape"), ("TypeMax", 1.0, "Shape"), ("BottomRamp", 0.02, "Shape"), ("TopRamp", 0.7, "Shape"),
    ("WindX", 0.0, "Layout"), ("WindY", 0.0, "Layout"),
    ("PixelAngle", 0.0007, "Layout"),          # radians per pixel, for the distance-based noise mips
    ("StretchX", 1.0, "Stretch"), ("StretchAngle", 0.0, "Stretch"), ("ShearKm", 0.0, "Stretch"),
    ("CellX", 0.0, "StormCell"), ("CellY", 0.0, "StormCell"), ("CellRadiusKm", 4.0, "StormCell"),
    ("CellStrength", 0.0, "StormCell"), ("CellTopH", 1.0, "StormCell"), ("CellTopRamp", 0.05, "StormCell"),
    ("AnvilBottom", 0.75, "StormCell"), ("AnvilRadiusKm", 15.0, "StormCell"), ("AnvilShiftKm", 8.0, "StormCell"),
    ("CellDensity", 3.0, "StormCell"), ("CellLumpKm", 4.0, "StormCell"), ("CellLumpAmp", 0.0, "StormCell"),
    ("CellSolid", 0.0, "StormCell"),
    # art extensions (2026-11-11): every default leaves the earlier looks unchanged
    ("LayerKm", 4.0, "Layer"), ("BaseKm", 0.0, "Layer"),
    ("RainDensity", 0.0, "Rain"), ("RainX", 0.0, "Rain"), ("RainY", 0.0, "Rain"), ("RainRadiusKm", 5.0, "Rain"),
    ("RainStreakKm", 0.4, "Rain"), ("RainSlantKm", 0.0, "Rain"),
    ("AnvilRamp", 1.0, "StormCell"), ("OvershootKm", 0.0, "StormCell"), ("OvershootRadiusKm", 3.0, "StormCell"),
    ("TurretAmt", 0.0, "StormCell"), ("TurretScaleKm", 2.0, "StormCell"),
    ("MammaAmt", 0.0, "Mammatus"), ("MammaScaleKm", 1.5, "Mammatus"), ("MammaDepthKm", 0.6, "Mammatus"),
    ("BillowAmt", 0.0, "Shape"), ("BillowScaleKm", 1.5, "Shape"),
    ("PowderAmt", 0.0, "Lighting"), ("PowderK", 3.0, "Lighting"),
    ("MackerelAmt", 0.0, "Mackerel"), ("MackerelScaleKm", 0.6, "Mackerel"), ("MackerelGap", 0.45, "Mackerel"),
    ("MackerelStretch", 1.0, "Mackerel"),
    ("RollAmt", 0.0, "Rolls"), ("RollSpacingKm", 4.0, "Rolls"), ("RollAngle", 0.0, "Rolls"),
    ("FrontAmt", 0.0, "Front"), ("FrontX", 0.0, "Front"), ("FrontY", 0.0, "Front"), ("FrontAngle", 0.0, "Front"),
    ("FrontHalfLenKm", 30.0, "Front"), ("FrontBowKm", 4.0, "Front"), ("FrontWobbleKm", 1.0, "Front"),
    ("FrontDepthKm", 6.0, "Front"), ("FrontBaseKm", 0.8, "Front"), ("FrontTopKm", 3.0, "Front"),
    ("FrontSlopeKm", 2.0, "Front"), ("FrontTiers", 3.0, "Front"), ("FrontDensity", 1.5, "Front"),
    ("LensAmt", 0.0, "Lens"), ("LensScaleKm", 60.0, "Lens"), ("LensElong", 2.0, "Lens"), ("LensBaseKm", 4.0, "Lens"),
    ("LensPlates", 3.0, "Lens"), ("LensSpacingKm", 0.35, "Lens"), ("LensThickKm", 0.25, "Lens"),
    ("LensShrink", 0.25, "Lens"), ("LensJitterKm", 0.5, "Lens"), ("LensDensity", 1.0, "Lens"),
    ("StormAO", 1.0, "StormCell"), ("LensCut", 0.15, "Lens"),
]
# v2 additions per slot (spec §2.2-2.3)
SLOT_EXTRA = [
    ("ExtinctionMax", 0.12, "Lighting"),
    ("BottomKm", 1.4, "Layer"),
    ("SlotOn", 1.0, "Slot"),
    ("AdvX", 0.0, "Time"), ("AdvY", 0.0, "Time"),
    ("DetailOffU", 0.0, "Time"), ("DetailOffV", 0.0, "Time"), ("DetailOffW", 0.0, "Time"),
    ("Detail2OffU", 0.0, "Time"), ("Detail2OffV", 0.0, "Time"), ("Detail2OffW", 0.0, "Time"),
    ("EvoAmt", 0.0, "Time"), ("EvoScaleKm", 8.0, "Time"), ("EvoPhase", 0.0, "Time"),
    ("BoilShape", 0.0, "Time"), ("BoilBillow", 0.0, "Time"), ("BoilTurret", 0.0, "Time"),
    ("MammaPhase", 0.0, "Time"), ("MackerelPhase", 0.0, "Time"), ("LumpPhase", 0.0, "Time"), ("RainFall", 0.0, "Time"),
]
GLOBAL_SCALARS = [("PixelAngle", 0.0007, "Layout")]          # a custom-node pin shared by both slots
# advanced-output pins outside the custom node, shared by both slots (evaluated per pixel, VolumetricCloud.usf 746-771)
EXTRA_SCALARS = [
    ("PhaseG", 0.6, "Lighting"), ("PhaseG2", -0.2, "Lighting"), ("PhaseBlend", 0.25, "Lighting"),
    ("MSContribution", 0.5, "MultiScattering"), ("MSOcclusion", 0.5, "MultiScattering"),
    ("MSEccentricity", 0.5, "MultiScattering"),
]
NODE_INPUTS = ["P", "Cam", "Alt", "SD", "L", "WeatherTex", "ShapeTex", "DetailTex"]
SLOT_SCALARS = [s for s in SCALARS if s[0] != "PixelAngle"] + SLOT_EXTRA
SLOT_NAMES = [s[0] for s in SLOT_SCALARS]
B_PREFIX = "B_"


def slot_name(name, slot):
    """The material parameter name of a slot parameter: slot "A" keeps the name, slot "B" adds "B_"."""
    return name if slot == "A" else B_PREFIX + name


def scalar_pins():
    """[(pin name, default, group)] of every scalar custom-node input, in pin order: globals, slot A, slot B."""
    out = list(GLOBAL_SCALARS)
    out += [(n, d, g) for n, d, g in SLOT_SCALARS]
    out += [(B_PREFIX + n, 0.0 if n == "SlotOn" else d, "B " + g) for n, d, g in SLOT_SCALARS]
    return out


def pins():
    """Every custom-node input name, in order."""
    return NODE_INPUTS + [p[0] for p in scalar_pins()]


# The density body of one slot. Reads its slot's parameters and P, Cam, Alt (absolute altitude, cm), SD, L, the three
# textures and PixelAngle; writes oD (extinction, 1/m), oCons, oAO, oAlb (declared by generate()). Static-look
# equivalence with the 2026-11-11 CODE: with AdvX/Y = 0, pn = pkm and q0 = q; every offset / phase is 0; EvoAmt = 0
# skips the evolution term; BottomKm = the cloud layer's bottom makes hk = AltitudeInLayer = H x LayerKm.
BODY_HEAD = r"""
float3 pkm = P * 1.0e-5;
float lk = max(LayerKm, 0.01);
float hk = Alt * 1.0e-5 - BottomKm;
"""

BODY_REST = r"""
float3 pn = pkm - float3(AdvX, AdvY, 0.0);
float2 wind = float2(WindX, WindY);
float bk = clamp(BaseKm, 0.0, lk * 0.95);
float ck = max(lk - bk, 0.01);
float hc = saturate((hk - bk) / ck);
float under = hk < bk ? 1.0 : 0.0;
float sang = radians(StretchAngle);
float2 sdir = float2(cos(sang), sin(sang));
float2 sper = float2(-sdir.y, sdir.x);
float2 q = float2(dot(pn.xy, sdir), dot(pn.xy, sper));
q.x = q.x / max(StretchX, 0.001) + hc * ShearKm;
float2 q0 = float2(dot(pkm.xy, sdir), dot(pkm.xy, sper));
q0.x = q0.x / max(StretchX, 0.001) + hc * ShearKm;
float4 wn = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, float3(q / WarpScaleKm, 0.37), 0.0);
float2 warp = (wn.gb - 0.5) * WarpKm;
float2 wuv = (q + wind + warp) / WeatherScaleKm;
float4 wm = Texture2DSampleLevel(WeatherTex, WeatherTexSampler, wuv, 0.0);
float4 wm2 = Texture2DSampleLevel(WeatherTex, WeatherTexSampler, wuv * 0.37 + float2(0.21, 0.63), 0.0);
float cov = saturate(wm.r * lerp(1.0, saturate(wm2.b * 1.8), 0.4) * CoverageScale + CoverageBias);
float covC = saturate(cov * (1.0 + 2.0 * EvoAmt));
if (EvoAmt > 0.0)
{
    float2 euv = pn.xy / max(EvoScaleKm, 0.01);
    float ev = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, float3(euv, EvoPhase), 0.0).g;
    float e0 = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, float3(euv, 0.0), 0.0).g;
    cov = saturate(cov * (1.0 + 2.0 * EvoAmt * (smoothstep(0.25, 0.75, ev) - smoothstep(0.25, 0.75, e0))));
}
if (RollAmt > 0.0)
{
    float ra = radians(RollAngle);
    float across = dot(pn.xy + wind + warp * 0.5, float2(-sin(ra), cos(ra)));
    float roll = 0.5 + 0.5 * cos(6.2831853 * across / max(RollSpacingKm, 0.1));
    float rk = lerp(1.0, smoothstep(0.3, 0.8, roll), RollAmt);
    cov *= rk;
    covC *= rk;
}
if (MackerelAmt > 0.0)
{
    float2 mq = (q + wind + warp * 0.3) / max(MackerelScaleKm, 0.01);
    mq.y *= max(MackerelStretch, 0.1);
    float wc = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, float3(mq * 0.125, 0.61 + MackerelPhase), 0.0).g;
    float cm = saturate((wc - MackerelGap) / max(1.0 - MackerelGap, 0.01));
    cov = lerp(cov, cm * saturate(cov * 2.0), MackerelAmt);
    covC = lerp(covC, cm * saturate(covC * 2.0), MackerelAmt);
}
float typeH = lerp(TypeMin, TypeMax, wm.g);
float topH = clamp(typeH * lerp(0.45, 1.0, saturate(cov * 1.3)), 0.05, 1.0);
float topHC = clamp(typeH * lerp(0.45, 1.0, saturate(covC * 1.3)), 0.05, 1.0);
float topRamp = TopRamp;
float dens = DensityScale;
float cellW = 0.0;
float mammaD = 0.0;
float aoCell = 1.0;
if (CellStrength > 0.0 && LensAmt <= 0.0)
{
    float ha = saturate((hc - AnvilBottom) / max(AnvilRamp * (1.0 - AnvilBottom), 0.001));
    ha = ha * ha * (3.0 - 2.0 * ha);
    float2 d0 = pkm.xy - float2(CellX, CellY);
    float2 dc = d0 - sdir * (AnvilShiftKm * ha);
    float rad = lerp(CellRadiusKm * lerp(0.85, 1.0, hc), AnvilRadiusKm, ha);
    float lump = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, pkm / max(CellLumpKm, 0.01) + float3(0.13, 0.71, 0.29 + LumpPhase), 3.0).r;
    rad *= 1.0 + CellLumpAmp * (lump - 0.5) * 2.0;
    float bubT = 0.5;
    if (TurretAmt > 0.0)
    {
        bubT = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, (pkm + float3(wind, 0.0)) / max(TurretScaleKm * 8.0, 0.01) + float3(0.47, 0.11, 0.83 + BoilTurret), 0.0).g;
        rad *= lerp(1.0, 0.7 + 0.6 * bubT, TurretAmt);
    }
    float cell = saturate((rad - length(dc)) / max(rad * 0.35, 0.01));
    cell = cell * cell * (3.0 - 2.0 * cell) * CellStrength;
    cellW = cell;
    float ctop = CellTopH;
    if (OvershootKm > 0.0)
    {
        float od = saturate(1.0 - dot(d0, d0) / max(OvershootRadiusKm * OvershootRadiusKm, 0.01));
        ctop = min(1.0, ctop + OvershootKm / ck * sqrt(od));
    }
    if (TurretAmt > 0.0)
    {
        ctop = min(1.0, ctop * lerp(1.0, 0.94 + 0.12 * bubT, TurretAmt));
    }
    aoCell = lerp(StormAO, 1.0, saturate((hc - (ctop - 0.15)) / 0.15));
    cov = max(cov, cell);
    covC = max(covC, cell);
    topH = lerp(topH, ctop, cell);
    topHC = lerp(topHC, ctop, cell);
    topRamp = lerp(topRamp, CellTopRamp, cell);
    dens = lerp(dens, CellDensity, cell);
    if (MammaAmt > 0.0 && hc < AnvilBottom && under < 0.5)
    {
        float2 da = d0 - sdir * AnvilShiftKm;
        float inA = saturate((AnvilRadiusKm * 0.92 - length(da)) / max(AnvilRadiusKm * 0.15, 0.01));
        float outCore = saturate((length(d0) - CellRadiusKm * 1.1) / max(CellRadiusKm * 0.3, 0.01));
        float wmz = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, float3((pkm.xy + wind) / max(MammaScaleKm * 8.0, 0.01), 0.23 + MammaPhase), 0.0).g;
        float depthKm = MammaDepthKm * pow(saturate((wmz - 0.35) / 0.65), 0.7);
        float belowKm = (AnvilBottom - hc) * ck;
        float mm = saturate((depthKm - belowKm) / max(MammaDepthKm * 0.15, 0.01));
        mammaD = mm * inA * outCore * MammaAmt;
    }
}
float lensD = 0.0;
if (LensAmt > 0.0)
{
    float region = 1.0;
    if (CellStrength > 0.0)
    {
        float2 dr = pkm.xy - float2(CellX, CellY);
        region = saturate((CellRadiusKm - length(dr)) / max(CellRadiusKm * 0.3, 0.01)) * CellStrength;
    }
    float2 lq = float2(dot(pkm.xy, sdir) / max(LensElong, 0.1), dot(pkm.xy, sper));
    float4 wl = Texture2DSampleLevel(WeatherTex, WeatherTexSampler, (lq + float2(5.3, 1.7)) / max(LensScaleKm, 0.1), 0.0);
    float fb = saturate((wl.r - LensCut) / max(1.0 - LensCut, 0.01));
    float jit = (wn.r - 0.5) * 2.0 * LensJitterKm;
    float npl = clamp(LensPlates, 1.0, 5.0);
    for (int i = 0; i < 5; i++)
    {
        float fi = (float)i;
        if (fi >= npl) break;
        float shrink = saturate(1.0 - fi * LensShrink);
        float fbi = saturate((fb - (1.0 - shrink)) / max(shrink, 0.05));
        float th = LensThickKm * sqrt(fbi) * lerp(1.0, 0.7, fi / npl) * saturate(npl - fi);
        float dz = abs(hk - (LensBaseKm + jit + fi * LensSpacingKm));
        lensD = max(lensD, saturate((th - dz) / max(LensThickKm * 0.2, 0.005)));
    }
    lensD *= region * LensAmt;
}
float frontM = 0.0;
float frontZ = 0.0;
if (FrontAmt > 0.0)
{
    float fa = radians(FrontAngle);
    float2 fdir = float2(cos(fa), sin(fa));
    float2 ftan = float2(-fdir.y, fdir.x);
    float2 dp = pkm.xy - float2(FrontX, FrontY);
    float u = dot(dp, ftan) / max(FrontHalfLenKm, 0.1);
    float sf = dot(dp, fdir) + FrontBowKm * u * u + (wn.r - 0.5) * 2.0 * FrontWobbleKm;
    frontZ = (hk - FrontBaseKm) / max(FrontTopKm - FrontBaseKm, 0.01);
    float tiers = max(FrontTiers, 1.0);
    float tq = saturate(frontZ) * tiers;
    float stair = (floor(tq) + smoothstep(0.55, 1.0, frac(tq))) / tiers;
    float inFace = saturate((-FrontSlopeKm * stair - sf) / 0.4);
    float inBack = saturate((sf + FrontDepthKm) / 2.5);
    float inZ = saturate(frontZ / 0.03) * saturate((1.0 - frontZ) / 0.1);
    float inLen = saturate((1.0 - abs(u)) / 0.25);
    frontM = inFace * inBack * inZ * inLen * FrontAmt;
}
float rainD = 0.0;
if (RainDensity > 0.0 && bk > 0.0)
{
    float slantT = saturate(1.0 - hk / bk);
    float2 rp = pkm.xy - float2(RainX, RainY) - sdir * (RainSlantKm * slantT);
    float rn = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, float3((pkm.xy + wind) / 24.0, 0.17), 0.0).r;
    float disc = saturate((RainRadiusKm * (0.7 + 0.6 * rn) - length(rp)) / max(RainRadiusKm * 0.35, 0.1));
    float st = Texture3DSampleLevel(DetailTex, DetailTexSampler, float3((pn.xy + wind) / max(RainStreakKm * 4.0, 0.01), hk * 0.08 + RainFall), 0.0).r;
    float topF = saturate((bk + 0.4 - hk) / 0.8);
    rainD = disc * lerp(0.35, 1.0, st) * topF * RainDensity;
}
float rampB = saturate(hc / max(BottomRamp, 0.001));
rampB = rampB * rampB * (3.0 - 2.0 * rampB) * (1.0 - under);
float rampT = saturate((topH - hc) / max(topH * topRamp, 0.001));
rampT = rampT * rampT * (3.0 - 2.0 * rampT);
float rampTC = saturate((topHC - hc) / max(topHC * topRamp, 0.001));
rampTC = rampTC * rampTC * (3.0 - 2.0 * rampTC);
float consX = max(max(mammaD, lensD), max(frontM, rainD));
oCons = max(saturate(rampTC * rampB * covC * 1.5), consX > 0.0 ? 1.0 : 0.0);
oAO = lerp(0.35, 1.0, saturate(hc / topH));
oAO *= lerp(1.0, aoCell, max(cellW, saturate(mammaD * 4.0)));
oAO *= lerp(1.0, StormAO, frontM * (1.0 - smoothstep(0.5, 1.0, frontZ)));
float shadowBias = SD > 0.0 ? 1.0 : 0.0;
float foot = max(length(P - Cam) * PixelAngle, 1.0);
float mipS = max(0.0, log2(foot / (ShapeScaleKm * 1.0e5 / 128.0))) + shadowBias;
float mipD = max(0.0, log2(foot / (DetailScaleKm * 1.0e5 / 64.0))) + shadowBias;
float3 nkm = float3(q, pkm.z);
float3 suvw = (nkm + float3(wind, 0.0)) / ShapeScaleKm + float3(0.0, 0.0, BoilShape);
float4 s = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, suvw, mipS);
float lowFBM = s.g * 0.625 + s.b * 0.25 + s.a * 0.125;
float base = saturate((s.r + 1.0 - lowFBM) / (2.0 - lowFBM));
if (BillowAmt > 0.0)
{
    float bw = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, (nkm + float3(wind, 0.0)) / max(BillowScaleKm * 8.0, 0.01) + float3(0.31, 0.57, 0.11 + BoilBillow), 0.0).g;
    base = lerp(base, saturate(base * 0.4 + bw * 0.8), BillowAmt * saturate(hc * 4.0));
}
float d = saturate((base * rampT - (1.0 - cov)) / max(cov, 0.001)) * cov * rampB;
float3 nk0 = float3(q0, pkm.z);
float3 dbase = (nk0 + float3(wind * 1.5, 0.0)) / DetailScaleKm;
float3 dn = Texture3DSampleLevel(DetailTex, DetailTexSampler, dbase + float3(DetailOffU, DetailOffV, DetailOffW), mipD).rgb;
float3 dn2 = Texture3DSampleLevel(DetailTex, DetailTexSampler, dbase * 2.71 + 0.37 + float3(Detail2OffU, Detail2OffV, Detail2OffW), mipD + 1.44).rgb;
float hiFBM = (dn.r * 0.625 + dn.g * 0.25 + dn.b * 0.125) * 0.7 + (dn2.r * 0.625 + dn2.g * 0.25 + dn2.b * 0.125) * 0.3;
float hiMod = lerp(hiFBM, 1.0 - hiFBM, saturate(hc * 5.0));
float e = hiMod * DetailStrength;
d = saturate((d - e) / max(1.0 - e, 0.001));
d = max(d, CellSolid * cellW * cellW * rampB * rampT);
float outD = d * dens;
if (mammaD > 0.0)
{
    outD = max(outD, mammaD * CellDensity * saturate(1.0 - e * 0.5));
}
if (lensD > 0.0)
{
    outD = max(outD, lensD * LensDensity);
}
if (frontM > 0.0)
{
    float fe = e * smoothstep(0.0, 0.3, frontZ);
    float df = saturate((frontM * saturate(base * 1.3 + 0.1) - fe) / max(1.0 - fe, 0.001));
    outD = max(outD, df * FrontDensity);
}
outD = max(outD, rainD);
float3 Lw = normalize(L);
float3 V = normalize(Cam - P);
float vf = saturate(0.5 + 0.5 * dot(V, Lw));
oAlb = lerp(1.0, 1.0 - exp(-outD * PowderK), PowderAmt * vf);
oD = outD * ExtinctionMax;
"""

_NAME_RE = re.compile(r"\b(%s)\b" % "|".join(sorted(SLOT_NAMES, key=len, reverse=True)))


def slot_body(slot):
    """The density body of one slot, its parameters named for that slot; skipped outside the slot's own layer."""
    body = BODY_HEAD.strip() + "\nif (hk >= 0.0 && hk <= lk)\n{\n" + BODY_REST.strip() + "\n}"
    if slot == "B":
        body = _NAME_RE.sub(lambda m: B_PREFIX + m.group(1), body)
    return body


def generate():
    """The custom node's code: slot A and slot B, each skipped while its SlotOn is 0, summed into one extinction;
    Cons is the larger conservative density, AO and Alb are extinction-weighted (1 where there is no cloud)."""
    lines = ["float sig = 0.0;", "float consM = 0.0;", "float aoS = 0.0;", "float albS = 0.0;"]
    for slot in ("A", "B"):
        lines += ["{", "float oD = 0.0;", "float oCons = 0.0;", "float oAO = 1.0;", "float oAlb = 1.0;",
                  "if (%s > 0.0)" % slot_name("SlotOn", slot), "{", slot_body(slot), "}",
                  "sig += oD;", "consM = max(consM, oCons);", "aoS += oAO * oD;", "albS += oAlb * oD;", "}"]
    lines += ["Cons = consM;", "AO = sig > 0.0 ? aoS / sig : 1.0;", "Alb = sig > 0.0 ? albS / sig : 1.0;", "return sig;"]
    return "\n".join(lines)
