float3 pkm = P * 1.0e-5;
float2 wind = float2(WindX, WindY);
float h = saturate(H);
float lk = max(LayerKm, 0.01);
float hk = h * lk;
float bk = clamp(BaseKm, 0.0, lk * 0.95);
float ck = max(lk - bk, 0.01);
float hc = saturate((hk - bk) / ck);
float under = hk < bk ? 1.0 : 0.0;
float sang = radians(StretchAngle);
float2 sdir = float2(cos(sang), sin(sang));
float2 sper = float2(-sdir.y, sdir.x);
float2 q = float2(dot(pkm.xy, sdir), dot(pkm.xy, sper));
q.x = q.x / max(StretchX, 0.001) + hc * ShearKm;
float4 wn = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, float3(q / WarpScaleKm, 0.37), 0.0);
float2 warp = (wn.gb - 0.5) * WarpKm;
float2 wuv = (q + wind + warp) / WeatherScaleKm;
float4 wm = Texture2DSampleLevel(WeatherTex, WeatherTexSampler, wuv, 0.0);
float4 wm2 = Texture2DSampleLevel(WeatherTex, WeatherTexSampler, wuv * 0.37 + float2(0.21, 0.63), 0.0);
float cov = saturate(wm.r * lerp(1.0, saturate(wm2.b * 1.8), 0.4) * CoverageScale + CoverageBias);
if (RollAmt > 0.0)
{
    float ra = radians(RollAngle);
    float across = dot(pkm.xy + wind + warp * 0.5, float2(-sin(ra), cos(ra)));
    float roll = 0.5 + 0.5 * cos(6.2831853 * across / max(RollSpacingKm, 0.1));
    cov *= lerp(1.0, smoothstep(0.3, 0.8, roll), RollAmt);
}
if (MackerelAmt > 0.0)
{
    float2 mq = (q + wind + warp * 0.3) / max(MackerelScaleKm, 0.01);
    mq.y *= max(MackerelStretch, 0.1);
    float wc = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, float3(mq * 0.125, 0.61), 0.0).g;
    float cm = saturate((wc - MackerelGap) / max(1.0 - MackerelGap, 0.01));
    cov = lerp(cov, cm * saturate(cov * 2.0), MackerelAmt);
}
float topH = clamp(lerp(TypeMin, TypeMax, wm.g) * lerp(0.45, 1.0, saturate(cov * 1.3)), 0.05, 1.0);
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
    float lump = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, pkm / max(CellLumpKm, 0.01) + float3(0.13, 0.71, 0.29), 3.0).r;
    rad *= 1.0 + CellLumpAmp * (lump - 0.5) * 2.0;
    float bubT = 0.5;
    if (TurretAmt > 0.0)
    {
        bubT = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, (pkm + float3(wind, 0.0)) / max(TurretScaleKm * 8.0, 0.01) + float3(0.47, 0.11, 0.83), 0.0).g;
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
    topH = lerp(topH, ctop, cell);
    topRamp = lerp(topRamp, CellTopRamp, cell);
    dens = lerp(dens, CellDensity, cell);
    if (MammaAmt > 0.0 && hc < AnvilBottom && under < 0.5)
    {
        float2 da = d0 - sdir * AnvilShiftKm;
        float inA = saturate((AnvilRadiusKm * 0.92 - length(da)) / max(AnvilRadiusKm * 0.15, 0.01));
        float outCore = saturate((length(d0) - CellRadiusKm * 1.1) / max(CellRadiusKm * 0.3, 0.01));
        float wmz = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, float3((pkm.xy + wind) / max(MammaScaleKm * 8.0, 0.01), 0.23), 0.0).g;
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
        float th = LensThickKm * sqrt(fbi) * lerp(1.0, 0.7, fi / npl);
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
    float st = Texture3DSampleLevel(DetailTex, DetailTexSampler, float3((pkm.xy + wind) / max(RainStreakKm * 4.0, 0.01), hk * 0.08), 0.0).r;
    float topF = saturate((bk + 0.4 - hk) / 0.8);
    rainD = disc * lerp(0.35, 1.0, st) * topF * RainDensity;
}
float rampB = saturate(hc / max(BottomRamp, 0.001));
rampB = rampB * rampB * (3.0 - 2.0 * rampB) * (1.0 - under);
float rampT = saturate((topH - hc) / max(topH * topRamp, 0.001));
rampT = rampT * rampT * (3.0 - 2.0 * rampT);
float consX = max(max(mammaD, lensD), max(frontM, rainD));
Cons = max(saturate(rampT * rampB * cov * 1.5), consX > 0.0 ? 1.0 : 0.0);
AO = lerp(0.35, 1.0, saturate(hc / topH));
AO *= lerp(1.0, aoCell, max(cellW, saturate(mammaD * 4.0)));
AO *= lerp(1.0, StormAO, frontM * (1.0 - smoothstep(0.5, 1.0, frontZ)));
float shadowBias = SD > 0.0 ? 1.0 : 0.0;
float foot = max(length(P - Cam) * PixelAngle, 1.0);
float mipS = max(0.0, log2(foot / (ShapeScaleKm * 1.0e5 / 128.0))) + shadowBias;
float mipD = max(0.0, log2(foot / (DetailScaleKm * 1.0e5 / 64.0))) + shadowBias;
float3 nkm = float3(q, pkm.z);
float3 suvw = (nkm + float3(wind, 0.0)) / ShapeScaleKm;
float4 s = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, suvw, mipS);
float lowFBM = s.g * 0.625 + s.b * 0.25 + s.a * 0.125;
float base = saturate((s.r + 1.0 - lowFBM) / (2.0 - lowFBM));
if (BillowAmt > 0.0)
{
    float bw = Texture3DSampleLevel(ShapeTex, ShapeTexSampler, (nkm + float3(wind, 0.0)) / max(BillowScaleKm * 8.0, 0.01) + float3(0.31, 0.57, 0.11), 0.0).g;
    base = lerp(base, saturate(base * 0.4 + bw * 0.8), BillowAmt * saturate(hc * 4.0));
}
float d = saturate((base * rampT - (1.0 - cov)) / max(cov, 0.001)) * cov * rampB;
float3 duvw = (nkm + float3(wind * 1.5, 0.0)) / DetailScaleKm;
float3 dn = Texture3DSampleLevel(DetailTex, DetailTexSampler, duvw, mipD).rgb;
float3 dn2 = Texture3DSampleLevel(DetailTex, DetailTexSampler, duvw * 2.71 + 0.37, mipD + 1.44).rgb;
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
Alb = lerp(1.0, 1.0 - exp(-outD * PowderK), PowderAmt * vf);
return outD;
