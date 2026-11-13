"""Page sections 3-7 of the City Sample clear-sky RenderDoc report (frame, passes, multi-scattering, GPU, repro)."""
import glob
import json
import os
import statistics

from build_report import CAPTURE, CAPTURE_GB, DIMS, ODIMS, REP, esc, fig, pass_block
from report_images import FOG, HALF, VIEW, dumped, meta, scene_pair

GPU_DIR = os.path.join(REP, "gpu_fin")       # ProfileGPU of the final settings, same session as the capture


def gpu_runs(pattern="profilegpu_final*.json"):
    out = []
    for f in sorted(glob.glob(os.path.join(GPU_DIR, pattern))):
        with open(f, encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


def gpu_ms(name, prefix=False, pattern="profilegpu_final*.json"):
    vals = []
    for d in gpu_runs(pattern):
        for r in d["rows"]:
            if r["name"] == name or (prefix and r["name"].startswith(name)):
                vals.append(r["incl_ms"])
                break
    return statistics.median(vals) if vals else None


def t(name, prefix=False):
    v = gpu_ms(name, prefix)
    return "—" if v is None else ("%.2f" % v if v >= 0.1 else "%.3f" % v)


FLOW = """TransmittanceLut ─┬─► MultiScatteringLut ─┐
 (256×64)         │    (32×32, Ψms)       │
                  ▼                       ▼
CloudShadow 4096² ─► 不滤波 ──────┬──► SkyViewLut / CameraVolumeLut / RealTimeCapture LUTs ─► 天光实时捕获 ─► SH 漫反射 + 反射立方体
                                  │                                                              │
                                  ├──► 太阳延迟光照（地表云影 + 逐像素大气透射）                  │
                                  ├──► 体积雾 LightScattering（VSM × 云影 × HG）─► FinalIntegration ─┐
                                  ├──► SkyAtmosphere 逐像素步进（天空 + 不透明空气透视）             │
                                  └──► 云上逐像素空气透视（HQ AP）                                   │
VT_CS_CloudShape / Detail / Weather ─► CloudView 844×1321（3 阶多次散射）─► + AP ─► + 雾 ─► 合成 ◄─┘（高度雾 pass 读积分体）
CloudSkyAO 1024² ─► 滤波 ─► 只进大气积分的多次散射项（地表天光那一路在 UE 5.8 里是 #if 0）"""


def frame(a, F, P, first_eid, first_end, second_eid):
    a("<h2 id='frame'>3. 帧结构与场景色演进</h2>")
    a("<p>抓帧里有两次完整的场景渲染。<b>第一次（EID %d–%d）</b>是引擎这一帧正常的 tick：有 TSR、运动模糊、天光实时捕获，"
      "最后画 Slate UI 并 Present，也就是屏幕上真正显示的画面。第二次（EID %d 起）是 RenderDoc 插件为了抓帧额外调用的 "
      "<code>Viewport-&gt;Draw()</code>：它的视图不带历史，抗锯齿退化成 FXAA + 直接放大，也没有天光捕获。下面所有分析都以第一次渲染为准。</p>"
      % (first_eid, first_end, second_eid))
    rows = [
        ("A", "VolumetricCloudShadow", "CloudSkyAO → 空间滤波 → CloudShadow（SpatialFiltering 0，不再降采样）", t("VolumetricCloudShadow")),
        ("B", "SkyAtmosphereLUTs", "Transmittance → MultiScattering → DistantSkyLight → 2 张天光捕获 LUT → SkyView → CameraVolume",
         t("SkyAtmosphereLUTs")),
        ("C", "CaptureConvolveSkyEnvMap", "6 面云 → 6 面天空 → MipGen → Convolve → 漫反射 SH", t("CaptureConvolveSkyEnvMap")),
        ("D", "Lights › RenderLight StandardDeferred: DirectionalLight", "太阳直射：VSM 阴影 × 云影 × 大气透射",
         t("RenderLight Light::StandardDeferred(Single): DirectionalLight", True)),
        ("E", "ComputeVolumetricFog", "InitialiseVolume → LightScattering → FinalIntegration", t("ComputeVolumetricFog")),
        ("F", "VolumetricCloud", "CloudView %s → HighQualityAerialPerspectiveOnCloud → ExponentialHeightFog on Clouds" % DIMS,
         t("VolumetricCloud")),
        ("G", "LightShafts (Occlusion)", "下采样 → TAA → 3 次径向模糊 → 遮挡项", t("LightShafts (Occlusion)")),
        ("H", "SkyAtmosphere", "逐像素大气步进：天空像素 + 不透明物体空气透视", t("SkyAtmosphere")),
        ("I", "ExponentialHeightFog", "解析高度雾 + 体积雾积分体 + 光束遮挡", t("ExponentialHeightFog")),
        ("J", "VolCloudComposeOverScene", "把云的渲染目标按深度合成到场景色", t("VolCloudComposeOverScene")),
        ("K", "PostProcessing", "TSR %s→%s → 局部曝光 / 直方图 → Bloom → Tonemap" % (DIMS, ODIMS), t("PostProcessing")),
    ]
    eid = {"A": P["cloud_skyao"]["eid"], "B": P["atmo_transmittance"]["eid"], "C": P["cap_cloud_face0"]["eid"],
           "D": P["sun_light"]["eid"], "E": P["fog_init"]["eid"], "F": P["cloud_view"]["eid"], "G": P["shafts"]["eid"],
           "H": P["sky_draw"]["eid"], "I": P["fog_draw"]["eid"], "J": P["cloud_compose"]["eid"], "K": P["tsr"]["eid"]}
    a("<table><tr><th>#</th><th>RDG 事件</th><th>首个 EID</th><th>内容</th><th class='num'>GPU ms（中位数）</th></tr>%s</table>" % "".join(
        "<tr><td>%s</td><td><code>%s</code></td><td class='num'>%s</td><td>%s</td><td class='num'>%s</td></tr>"
        % (k, esc(n), eid[k], esc(d), ms) for k, n, d, ms in rows))
    a("<h4>数据流</h4><div class='flow'>%s</div>" % esc(FLOW.replace("844×1321", DIMS)))
    a("<h4>场景色在一帧里的演进（同一曝光）</h4>")
    a(fig(F, "stages", "按编号顺序：①太阳光照之前，场景色只有自发光；②加上太阳直射（这里大多是逆光面，又处在云影里，所以很暗）；"
                       "③加上 Lumen 间接光与反射，城市亮起来，天空仍是黑的；④SkyAtmosphere 逐像素画出天空，天空里已经有云影造成的光柱条纹，"
                       "远处城市加上空气透视；⑤高度雾 / 体积雾叠上放射状光柱；⑥体积云合成；⑦TSR 与色调映射后的最终画面", max_w=1180))


def section_passes(a, F, P):
    a("<h2 id='passes'>4. 逐个 Pass 详解</h2>")
    a("<p>每个 pass 的 EID、着色器入口、Dispatch 尺寸、输入与输出资源都是用 RenderDoc Python API 回放抓帧时读出来的"
      "（<code>Tools/cs_sky/rdc_export.py</code>）；图是对应资源在该 pass 执行后的内容，由原始像素解码得到"
      "（HDR 数据用同一个滤镜曲线显示，LUT 放大时用最近邻，保留像素格）。</p>")

    # ---------------------------------------------------------------------------------------------------- A ---
    a("<h3>A. VolumetricCloudShadow —— 云的阴影图与天光遮蔽图</h3>")
    a(pass_block(P, "cloud_skyao", "A1. CloudSkyAO（+ CloudDataSpatialFilter）",
                 "<p>从天顶正上方，对云层做一次正交光线步进，记录每个地面位置上空云层的光学厚度，生成"
                 "<b>云对天光的遮蔽图</b>。只有 SkyLight 勾选 <code>Cloud Ambient Occlusion</code> 时才会执行。"
                 "范围 = <code>CloudAmbientOcclusionExtent</code> 60 km，分辨率 = 512 × <code>MapResolutionScale</code> 2 = 1024²，"
                 "格式 R11G11B10（R = 云前沿深度 km，G = 平均消光，B = 最大光学厚度）。随后的空间滤波只做膨胀 / 平滑，不降采样。"
                 "在 UE 5.8 里它只有一个读者：大气积分的多次散射项（<code>SkyAtmosphere.usf</code> 第 736 行），让云下大气的多次散射变暗。地表天光那一路（<code>ReflectionEnvironmentPixelShader.usf</code> 第 299 行）被 <code>#if 0</code> 关掉了，云的环境光和体积雾也不读它，所以它不会让城市变暗。</p>",
                 fig(F, "skyao", "Cloud.SkyAOTexture（1024²）", max_w=780)))
    a(pass_block(P, "cloud_shadow", "A2. CloudShadow —— Beer Shadow Map",
                 "<p>沿太阳方向，对云层做正交光线步进（每像素 16 × 平行光的 <code>CloudShadowRaySampleCountScale</code> 4 = 64 个采样，太阳越低按 "
                 "<code>ShadowMap.RaySampleHorizonMultiplier</code> 加得越多，太阳高度 31° 时约 89 个；<code>ShadowMap.RaySampleMaxCount</code> 256 只是上限），追踪分辨率 512×8 = 4096²。正交投影覆盖 "
                 "±2×<code>CloudShadowExtent</code> = ±20 km（40 km 见方），每个纹素 9.8 m；投影的近平面（每个纹素的追踪起点）"
                 "放在朝太阳方向 <code>LightDistanceOverride</code> 80 km 处，整张图都从云层上方开始追踪（第 8 节）。"
                 "输出的三个通道是 <b>R = 云前沿深度（km，从近平面量起）、G = 平均消光（1/m）、B = 最大光学厚度</b>。"
                 "<code>SpatialFiltering 0</code>，不再做 2×2 降采样，<code>Cloud.ShadowTexture0</code> 直接供后面所有使用者读取。"
                 "读取方式（<code>VolumetricCloudCommon.ush</code> <code>GetCloudVolumetricShadow</code>）："
                 "光学厚度 = min(B, G × max(0, 采样点深度 − R))，阴影 = exp(−光学厚度)。在这一帧里它有四个用户："
                 "D 的太阳延迟光照（地表云影）、B 的 SkyView / CameraVolume LUT 与 H 的逐像素大气（大气里的光柱）、"
                 "E 的体积雾（体积光柱）、F2 的云上空气透视。<b>它也是全帧最贵的 pass</b>（见第 6 节）。</p>",
                 fig(F, "cshadow", "Cloud.ShadowTexture0（4096²，40 km 见方）", max_w=1160)))

    # ---------------------------------------------------------------------------------------------------- B ---
    a("<h3>B. SkyAtmosphereLUTs —— 天空大气查找表（每帧重算，StateVersioning = 0）</h3>")
    a(pass_block(P, "atmo_transmittance", "B1. TransmittanceLut",
                 "<p>纵轴是高度（地面到大气顶，100 km），横轴是光线方向的天顶角余弦（越往右越接近地平线、光程越长）。每个像素沿该方向积分"
                 "瑞利 + 米氏 + 臭氧吸收的消光（<code>r.SkyAtmosphere.TransmittanceLUT.SampleCount</code> 30），"
                 "存从该点到大气顶的透射率 T = exp(−∫σt) 的<b>平方根</b>（<code>EncodeTransmittance</code>：让地平线附近的低透射率多分到精度，读的时候再平方）。它决定太阳光到达地面、云和雾时的颜色（太阳越低越黄、越红），"
                 "也是太阳圆盘的亮度来源；后面几乎所有大气、云、雾的 pass 都要读它。</p>",
                 fig(F, "trans", "SkyAtmosphere.TransmittanceLut 256×64（×3 放大；显示的是存的 √T）", fmt="PNG", max_w=780, nearest=True)))
    a(pass_block(P, "atmo_multiscattering", "B2. MultiScatteringLut —— 多次散射",
                 "<p>这是“多次大气散射”的核心：Hillaire 2020《A Scalable and Production Ready Sky and Atmosphere Rendering Technique》。"
                 "对每个（高度，太阳天顶角），向球面上的多个方向（<code>MultiScatteringLUT.HighQuality 1</code> 用 8 个方向，默认只有 2 个）"
                 "积分二阶散射亮度 L₂ 以及“散射一次后又被散射回来”的比例 f_ms，再按级数 L₂ ×（1 + f + f² + f³ + f⁴）"
                 "累加更高阶的散射（UE 5.8 默认展开到 5 项，闭式 L₂ / (1 − f) 是备用分支，见第 5 节），"
                 "存为各向同性的多次散射贡献 Ψms（32×32）。之后每一次大气积分，在每个采样点都加上 σs·Ψms × "
                 "<code>MultiScatteringFactor</code>（=1）。没有它，天空的地平线会偏暗、偏饱和，阴影里的大气也会过黑。</p>",
                 fig(F, "ms", "SkyAtmosphere.MultiScatteredLuminanceLut 32×32（×8 放大；左半边太阳在地平线以下）", fmt="PNG",
                     max_w=300, nearest=True)))
    a(pass_block(P, "atmo_distantskylight", "B3. DistantSkyLightLut",
                 "<p>在 6 km 高度（<code>r.SkyAtmosphere.DistantSkyLightLUT.Altitude</code>）对上半球积分天空亮度，得到一个平均的天光颜色，"
                 "写进一个小缓冲区。体积云用它做环境光（场景里有 SkyAtmosphere 时，<code>VolumetricCloud.usf</code> 第 732 行），指数高度雾用它作为雾的内散射颜色"
                 "（<code>SkyAtmosphereAmbientContributionColorScale</code>），所以雾的颜色会随大气与太阳自动变化。</p>"))
    a(pass_block(P, "atmo_rt_skyview", "B4. RealTimeCaptureSkyViewLut / RealTimeCaptureCamera360VolumeLut",
                 "<p>给 C 组天光实时捕获专用的两张 LUT：以天光捕获点而不是相机为视点的 SkyView（192×104），以及 360° 的空气透视体积"
                 "（64×64×32）。它们同样读取云影图和云天光 AO，所以捕获到的天空里也带着云影。</p>",
                 fig(F, "rt_skyview", "RealTimeSkyCapture SkyView 192×104（×3）", max_w=600, nearest=True)
                 + fig(F, "rt360", "RealTimeSkyCapture 360° 体积第 31 片", max_w=420, nearest=True)))
    a(pass_block(P, "atmo_skyview", "B5. SkyViewLut",
                 "<p>以相机为中心的天空全景：横轴方位角，纵轴仰角（非线性参数化，地平线附近分辨率更高），每个像素沿视线积分"
                 "单次散射 + 多次散射 LUT，并按 <code>CloudShadowOnAtmosphereStrength</code> 采样云影。"
                 "它每个视图每帧都会算，不受 <code>FastSkyLUT</code> 影响：<code>FastSkyLUT 1</code> 时主视图的天空直接从它插值，"
                 "天空球这类 IsSky 材质的 <code>SkyAtmosphereViewLuminance</code> 节点也读它；"
                 "本帧关了 FastSkyLUT、又隐藏了天空球，主视图天空改由 H 逐像素步进，不再从它取值。</p>",
                 fig(F, "skyview", "SkyAtmosphere.SkyViewLut 192×104（×3）：上半部是天空，可见太阳光晕与云影条纹", max_w=600,
                     nearest=True)))
    a(pass_block(P, "atmo_cameravolume", "B6. CameraVolumeLut —— 空气透视体积",
                 "<p>相机视锥里的 froxel 体积（<code>AerialPerspectiveLUT.Width</code> 64，<code>DepthResolution</code> 32 层，"
                 "覆盖 96 km，<code>LUT32</code> 用 RGBA32F 存）：RGB = 从相机到该深度累计的内散射亮度，A = 平均透射率。"
                 "它同样采样云影图与 VSM，所以体积里能看到云影压出的暗条纹（就是大气中的光柱）。"
                 "半透明物体和 CloudView 的空气透视读它；不透明物体因 <code>FastApplyOnOpaque 0</code> 改走 H 的逐像素步进。</p>",
                 fig(F, "apvol", "SkyAtmosphere.CameraAPVolume 64×64×32 的几个深度切片（×3）；切片越远内散射越强、透射率越低",
                     max_w=1160, nearest=True)))

    # ---------------------------------------------------------------------------------------------------- C ---
    a("<h3>C. CaptureConvolveSkyEnvMap —— 天光实时捕获（TimeSlice = 0，6 个面每帧都画）</h3>")
    a(pass_block(P, "cap_cloud_face0", "C1. Capture Volumetric Cloud Face=0…5 —— CloudView (CS) 128×128",
                 "<p>先为立方体的每个面在 128² 低分辨率下追踪一次体积云（<code>SkyLight.LowResCloudTexture</code>，RGB 亮度 + A 透射率），"
                 "读的是 B4 的天光捕获 LUT 与同一套云材质贴图。面数多、分辨率低，所以用较少的采样"
                 "（<code>ReflectionRaySampleMaxCount</code> × <code>reflection_view_sample_count_scale</code>）。</p>",
                 fig(F, "cap_cloud", "Face 0 的低分辨率云", max_w=520, nearest=True)))
    a(pass_block(P, "cap_face0", "C2. Capture Face=0…5 —— 天空大气 + 远处高度雾 + 合成云",
                 "<p>每个面三步写入 256² 的 <code>SkyRenderTarget</code> 立方体："
                 "<code>RenderSkyAtmosphereRayMarchingPS</code> 用 B4 的 LUT 画天空；"
                 "<code>RenderRealTimeReflectionHeightFogPS</code> 叠加远处的指数高度雾；"
                 "<code>ApplyLowerHemisphereColorPS</code> 把 C1 的云按透射率合成进来，并处理下半球颜色。</p>",
                 fig(F, "cap_faces", "SkyRenderTarget 的 6 个面（同一曝光）", max_w=1160)))
    a(pass_block(P, "cap_convolve", "C3. MipGen ×8 → Convolve（FilterCS）→ ComputeSkyEnvMapDiffuseIrradianceCS",
                 "<p>先为立方体生成 mip 链，再按 GGX 粗糙度逐 mip 预滤波（反射用的 <code>ConvolvedSkyRenderTarget</code>），"
                 "最后把卷积结果投影成三阶球谐，写进 <code>SkyIrradianceEnvironmentMap</code>（漫反射天光）。"
                 "这样，经过多次散射的大气与云的颜色就作为环境光照亮了城市和体积雾（有大气时体积云不读它，用的是 B3 的远景天光）。</p>"))

    # ---------------------------------------------------------------------------------------------------- D ---
    a("<h3>D. 太阳的延迟光照 —— 地表上的云影</h3>")
    a(pass_block(P, "sun_light", "D. Lights › RenderLight Light::StandardDeferred(Single): DirectionalLight",
                 "<p><code>DeferredLightPixelMain</code> 对 GBuffer 计算太阳直射。它同时读三样大气相关的东西："
                 "<code>ShadowMaskTexture</code>（VSM 阴影）、<code>Cloud.ShadowTexture0</code>（地表云影，"
                 "强度 <code>CloudShadowOnSurfaceStrength</code>）、<code>SkyAtmosphere.TransmittanceLut</code>"
                 "（<code>PerPixelAtmosphereTransmittance</code> 打开后，每个像素按自己的高度和太阳角查透射率，高楼顶比地面更白）。"
                 "下图是这个 pass 前后场景色之差，也就是太阳直射的贡献：这个逆光机位下，前景城区大多在云影里，"
                 "只有左下方的公园和几处楼顶、楼的侧边直接受光。</p>",
                 fig(F, "sun_contrib", "太阳直射贡献（光照后 − 光照前，单独曝光）", max_w=330)))

    # ---------------------------------------------------------------------------------------------------- E ---
    a("<h3>E. ComputeVolumetricFog —— 体积雾与体积光（froxel %d×%d×128）</h3>" % FOG)
    a("<p>体积雾把视锥切成 froxel：XY 每 4 像素一格（<code>r.VolumetricFog.GridPixelSize 4</code>，默认 16），"
      "Z 分 128 层（<code>GridSizeZ</code>），按指数分布排到 6 km（<code>VolumetricFogDistance</code>）。"
      "先跑 <code>VolumetricFog::ConservativeDepth</code> 求每格的保守深度，用来跳过不透明物体后面的 froxel。</p>")
    a(pass_block(P, "fog_init", "E1. InitializeVolumeAttributes（MaterialSetupCS）",
                 "<p>按两层指数高度雾的密度公式（以及 Local Fog Volume、体积材质，这一帧里没有）填两张 3D 纹理："
                 "<code>VBufferA</code> = (散射 RGB = albedo × 消光, 消光)，<code>VBufferB</code> = 自发光（为 0）。"
                 "下图是 VBufferA 的消光通道：每张切片从下到上随高度指数衰减，近处切片在相机高度（247 m）附近较稀，"
                 "远处切片覆盖从地面到高空的整段，第二层雾让密度一直延伸到云底。</p>",
                 fig(F, "vbuffer", "VolumetricFog.VBufferA 消光（同一色阶）", max_w=1160)))
    a(pass_block(P, "fog_scatter", "E2. %s（LightScatteringCS）—— 体积光" % esc(" ".join(P["fog_scatter"]["marker"].split())),
                 "<p>体积光就在这里产生。对每个 froxel（带时域抖动，<code>SS:8</code> 表示历史缺失时补 8 个样本），计算到达这里、"
                 "并散射进视线的光：太阳光 × HG 相函数（g = 0.8）× <b>VSM 阴影</b>（建筑的阴影光束）× <b>云影图</b>"
                 "（<code>GetCloudVolumetricShadow</code>，云隙光柱）× 大气透射率 × <code>VolumetricScatteringIntensity</code> 2；"
                 "再加上环境项 <code>LF Lumen</code>：从 Lumen 半透明 GI 体积取间接光与带阴影的天光（二阶 SH），近似多次散射。"
                 "结果与上一帧的历史做时域混合（<code>HistoryWeight</code> 0.9）。切片图里，近处是太阳方向的强前向散射，"
                 "中远处的暗斑就是云影。</p>",
                 fig(F, "lscatter", "VolumetricFog.LightScattering 各深度切片（同一曝光）", max_w=1160)))
    a(pass_block(P, "fog_integrate", "E3. FinalIntegration（FinalIntegrationCS）",
                 "<p>沿每一列 froxel 由近到远积分：累计内散射 += 当前散射 × 当前透射率 × 层厚，透射率 ×= exp(−消光 × 层厚)，"
                 "写进 <code>IntegratedLightScattering</code>。第 z 片 = 从相机到该深度的总雾光与透射率，"
                 "所以最后一片就是 6 km 内体积雾的完整结果：放射状的光柱清清楚楚，被建筑挡住的列提前截止。"
                 "后面的高度雾 pass（I）和云上的雾（F3）都按像素深度从这张体积里取值。</p>",
                 fig(F, "integ", "VolumetricFog.IntegratedLightScattering（同一曝光）与最后一片的透射率", max_w=1160)))

    # ---------------------------------------------------------------------------------------------------- F ---
    a("<h3>F. VolumetricCloud —— 主视图体积云（VolumetricRenderTarget.Mode 3，全分辨率）</h3>")
    a(pass_block(P, "cloud_view", "F1. CloudView (CS) %s（VolumetricCloud.usf MainCS）" % DIMS,
                 "<p>每个像素沿视线穿过 1.4–5.4 km 的云层步进（最多 96 × 组件的 <code>ViewSampleCountScale</code> 4 = 384 个采样，"
                 "<code>ViewRaySampleMaxCount</code> 1024 只是上限；保守密度为 0 处按步长跳过），每个采样点执行一次云材质"
                 "（天气图 → 剖面 → Perlin-Worley 主体 → Worley 侵蚀），然后计算光照："
                 "<ul><li>太阳：二次光线步进求云自阴影（10 × <code>ShadowViewSampleCountScale</code> 4 = 40 步，<code>Shadow.ViewRaySampleMaxCount</code> 128 只是上限），"
                 "乘逐采样的大气透射率（<code>UsePerSampleAtmosphericLightTransmittance</code>）；</li>"
                 "<li><b>3 阶多次散射近似</b>：每阶的散射系数、消光系数、相函数按材质的 a / b / c 衰减（见第 5 节）；</li>"
                 "<li>双瓣 HG 相函数（g = 0.6 / −0.2，混合 0.25），逆光时云边出现银边；</li>"
                 "<li>环境光：场景里有 SkyAtmosphere 时取 B3 的远景天光颜色（<code>VolumetricCloud.usf</code> 第 732 行；没有大气时才退回天光 SH）× 材质 AO × 云底遮蔽 saturate(1 − 0.6 + 高度比例)，只加在第 0 阶；地面反照率照亮云底（Ground Contribution）；</li>"
                 "<li>读取 <code>SceneDepthZ</code>，在建筑前停止步进。</li></ul>"
                 "输出 <code>Cloud.HighQualityAPIntermediate</code>（RGBA16F：RGB 亮度、A 灰度透射率）和 "
                 "<code>VolumetricRenderTarget.TracingDepth</code>（RG16F：云前沿深度，用于后面的空气透视、雾和合成）。</p>",
                 fig(F, "cloud_view", "云的 RGB、透射率与深度", max_w=820)))
    a(pass_block(P, "cloud_hqap", "F2. HighQualityAerialPerspectiveOnCloud（RenderSkyAtmosphereRayMarchingPS）",
                 "<p><code>r.VolumetricCloud.HighQualityAerialPerspective 1</code> 时，从相机到每个像素的云深度逐像素步进大气"
                 "（同样采样云影和 VSM），把空气透视叠到云上，取代从 CameraVolumeLut 插值的版本。远处的云因此带上正确的蓝灰色与雾化。</p>"))
    a(pass_block(P, "cloud_fog", "F3. ExponentialHeightFog on Clouds（ExponentialPixelMain）",
                 "<p><code>r.VolumetricCloud.ApplyFogLate 1</code>：按云的深度，把解析高度雾和体积雾积分体（E3）叠到云的渲染目标上，"
                 "结果写进 <code>VolumetricRenderTarget.Tracing</code>，等待 J 合成。</p>",
                 fig(F, "cloud_ap", "云渲染目标的三个阶段（同一曝光）", max_w=820)))

    # ---------------------------------------------------------------------------------------------------- G ---
    a(pass_block(P, "shafts", "G. LightShafts (Occlusion) —— 屏幕空间光束遮挡",
                 "<p>平行光开了 <code>bEnableLightShaftOcclusion</code>（Bloom 版没开）。半分辨率（%d×%d）里，" % HALF +
                 "<code>DownsampleLightShaftsPixelMain</code> 由深度生成遮挡蒙版，做一次 TAA，再朝太阳的屏幕位置做 3 次径向模糊，"
                 "<code>FinishOcclusionMain</code> 得到 <code>LightShaftOcclusion</code>。它在 I 里被高度雾读取，"
                 "压暗被遮挡方向上的雾与大气内散射，这就是传统意义上的屏幕空间 god ray 遮挡。"
                 "这一帧太阳附近没有不透明物体，所以遮挡项几乎全为 1，效果很弱，主要的光柱来自 E2 的体积雾和 H 的大气云影。</p>",
                 fig(F, "shafts", "光束遮挡的中间结果（0–1）", max_w=760)))

    # ---------------------------------------------------------------------------------------------------- H ---
    a(pass_block(P, "sky_draw", "H. SkyAtmosphere（RenderSkyAtmosphereRayMarchingPS，逐像素）",
                 "<p>全屏 pass。<b>天空像素</b>：沿视线逐像素步进大气（最多 32 × <code>TraceSampleCountScale</code> 2 = 64 个采样，"
                 "<code>SampleCountMax</code> 128 只是上限），每个采样点 = 单次散射（TransmittanceLut 给出太阳到该点的透射率，"
                 "瑞利 + 米氏相函数）+ 多次散射（MultiScatteringLut）× 云影 × VSM 阴影，再加太阳圆盘。"
                 "<b>不透明像素</b>：同样步进到表面深度，得到内散射 L 与透射率 T，场景色 = 原色 × T + L（空气透视）。"
                 "这一步让远处城市变成蓝灰色，也在天空里画出云影造成的光柱条纹。</p>",
                 fig(F, "sky_ba", "SkyAtmosphere 前后（同一曝光）", max_w=700)))

    # ---------------------------------------------------------------------------------------------------- I ---
    a(pass_block(P, "fog_draw", "I. ExponentialHeightFog › Fog（ExponentialPixelMain）",
                 "<p>按每个像素的深度：6 km 内从 E3 的 <code>IntegratedLightScattering</code> 取体积雾的内散射与透射率，"
                 "6 km 外用解析的两层指数高度雾积分（颜色取 B3 的远处天光），再乘 G 的光束遮挡，"
                 "最后 场景色 = 场景色 × 雾透射率 + 雾光。天空像素同样会被叠上 6 km 内的体积雾，所以光柱会一直延伸到天空背景前。</p>",
                 fig(F, "fog_ba", "Fog 前后（同一曝光）", max_w=700)))

    # ---------------------------------------------------------------------------------------------------- J ---
    a(pass_block(P, "cloud_compose", "J. VolCloudComposeOverScene › VolumetricComposeCloudOverScene",
                 "<p><code>ComposeVolumetricRTOverScenePS</code> 把 F3 的云渲染目标按深度测试合成到场景色：场景色 = 场景色 × 云透射率 + 云亮度"
                 "（预乘），云深度比场景深度远的像素不合成（建筑挡住云）。Mode 3 是全分辨率，"
                 "所以这里用最近点加深度测试（UpsamplingMode 2），不需要重建 / 双边上采样。</p>",
                 fig(F, "comp_ba", "合成前后（同一曝光）", max_w=700)))

    # ---------------------------------------------------------------------------------------------------- K ---
    a(pass_block(P, "tsr", "K. PostProcessing —— TSR、曝光、Bloom、Tonemap",
                 "<p>TSR 把 %s 的场景色时域超分到 %s；局部曝光与直方图测光（这里上下限固定 EV100 13.4）；"
                 "Bloom 让太阳附近与云的亮边泛光；<code>Tonemap %s</code> 输出到 R10G10B10A2 的 <code>BufferedRT</code>，"
                 "即第 1 节的最终画面。云和雾在 TSR 之前完成，所以全分辨率云追踪的逐帧抖动噪声由 TSR 累积消除。</p>"
                 % (DIMS, ODIMS, ODIMS.replace("×", "x"))))


def section_ms(a):
    a("<h2 id='ms'>5. 多次散射是怎么做的</h2>")
    a("<h3>5.1 大气：Multi-Scattering LUT（Hillaire 2020）</h3>")
    a("<p>单次散射只算“太阳光被散射一次进入眼睛”。真实大气里光会被散射很多次，正是这些高阶散射让地平线发白、"
      "阴影中的大气仍有亮度。UE 的做法（<code>SkyAtmosphere.usf</code> <code>RenderMultiScatteredLuminanceLutCS</code>）是假设"
      "二阶及以上散射都是各向同性的，于是可以离线成表：</p>")
    a("<pre><code>// 对 (高度, 太阳天顶角) 的每个格子，向 8 个方向积分（HighQuality；默认 2 个）：\n"
      "//   InScatteredLuminance = ∫ 二阶散射亮度 L₂（单次散射 × 各向同性相函数）\n"
      "//   MultiScatAs1 (f)     = 光被散射一次后，又散射回同一点的比例 f_ms\n"
      "#define MULTI_SCATTERING_POWER_SERIE 0                  // 第 785 行：UE 5.8 编译的就是这个分支\n"
      "float3 MultiScatAs1SQR = MultiScatAs1 * MultiScatAs1;\n"
      "float3 L = InScatteredLuminance * (1.0f + MultiScatAs1 + MultiScatAs1SQR\n"
      "         + MultiScatAs1 * MultiScatAs1SQR + MultiScatAs1SQR * MultiScatAs1SQR);   // 1 + f + f² + f³ + f⁴，展开到 5 项\n"
      "// 备用分支（POWER_SERIE 1）：L = InScatteredLuminance / (1 - f)，即无穷几何级数，f 用解析积分求\n"
      "// Ψms = L 写进 32×32 LUT</code></pre>")
    a("<p>引擎注释说明了为什么默认不用闭式：无穷级数要求 f &lt; 1，极端参数下 f 会变大、画面出错；展开到第 5 阶已经够用，"
      "更高阶的贡献很小。所以常见资料里的 L₂ / (1 − f) 是 Hillaire 论文的形式，不是 UE 5.8 实际运行的代码。</p>")
    a("<p>之后每一次大气积分（SkyView、CameraVolume、天光捕获的 LUT，以及 H 与 F2 的逐像素步进），每个采样点的内散射 = "
      "σs_rayleigh·P_r·太阳 + σs_mie·P_m·太阳 + (σs_rayleigh + σs_mie)·Ψms × <code>MultiScatteringFactor</code>。"
      "本场景 <code>MultiScatteringFactor = 1</code>，<code>MultiScatteringLUT.HighQuality = 1</code>（8 个方向，"
      "<code>SampleCount</code> 30）。<code>LUT32</code> 只把空气透视体积换成 RGBA32F，多次散射 LUT 本帧仍是 R11G11B10。</p>")
    a("<h3>5.2 体积云：Octave 近似（Wrenninge 2013 / Hillaire 2016）</h3>")
    a("<p>云的反照率接近 1，光在云里要散射几十次，直接模拟太贵。UE 把每个采样点的光照拆成几阶 octave，"
      "高阶 octave 的散射更弱、消光更小（光“更容易穿透”）、相函数更接近各向同性（<code>VolumetricCloud.usf</code>）：</p>")
    a("<pre><code>// a = MultiScatteringContribution, b = MultiScatteringOcclusion, c = MultiScatteringEccentricity\n"
      "PMC.ScatteringCoefficients[ms] = PMC.ScatteringCoefficients[ms - 1] * MsSFactor;   // σs × a, × a², …\n"
      "PMC.ExtinctionCoefficients[ms] = PMC.ExtinctionCoefficients[ms - 1] * MsEFactor;   // σt × b, × b², …\n"
      "MsSFactor *= MsSFactor;  MsEFactor *= MsEFactor;\n"
      "PMPC.Phase0[ms] = lerp(IsotropicPhase(), PMPC.Phase0[0], MsPhaseFactor);              // 相函数 → 各向同性\n"
      "MsPhaseFactor *= MsPhaseFactor;\n"
      "// 每个采样点：L += Σ_ms σs[ms] · Phase[ms] · exp(-∫σt[ms]) · 太阳 · 大气透射率</code></pre>")
    a("<p>本材质 <code>MultiScatteringApproximationOctaveCount = 2</code>（共 3 阶，引擎上限），a = 0.6、b = 0.5、c = 0.5："
      "第 1 阶 σs×0.6、σt×0.5；第 2 阶 σs×0.6³、σt×0.5³。效果是云体内部不会死黑、背光面有柔和的透光，逆光的云边仍保持亮边。"
      "此外还有环境项（B3 的远景天光 × 材质 AO × 云底遮蔽，只加在第 0 阶）和地面反照率项（Ground Contribution），后者相当于“地面—云”之间又一次反弹。</p>")
    a("<h3>5.3 体积雾与天光</h3>")
    a("<ul><li>体积雾对太阳只算单次散射（HG g = 0.8，乘 VSM 阴影和云影），更高阶的散射由环境项近似："
      "开 Lumen 时取 Lumen 半透明 GI 体积（含间接光与带阴影的天光），就是 pass 名里的 <code>LF Lumen</code>。</li>"
      "<li>6 km 外的解析高度雾，颜色取自 B3 的 DistantSkyLightLut，也就是已经包含多次散射的天空平均亮度。</li>"
      "<li>天光实时捕获（C）画的是含多次散射的大气与云，卷积成 SH 与反射立方体后照亮城市、云和雾，相当于整个天空又贡献了一次反弹。</li></ul>")


def section_gpu(a):
    a("<h2 id='gpu'>6. GPU 耗时</h2>")
    frames = [d["frame_ms"] for d in gpu_runs()]
    a("<p>RenderDoc 1.47 对这份抓帧的 <code>EventGPUDuration</code> 计数器返回空结果，所以耗时用引擎自带的 <code>ProfileGPU</code> 测："
      "抓帧之后在同一编辑器会话、同一机位与设置下（Lumen 软件追踪、关 async compute，与抓帧一致），连测 %d 帧取中位数。"
      "编辑器帧还包含编辑器自身的开销（整帧 GPU 时间 %s ms），只看相对大小即可。"
      "这一轮测量时机器上没有别的编辑器；上一版报告的数字（整帧 56–73 ms）是在另一个项目的编辑器同时占用 GPU 时测的，"
      "GPU 时间戳把被抢占的时间也算了进去，所以普遍偏高。</p>"
      % (len(frames), " / ".join("%.1f" % f for f in frames)))
    items = [("VolumetricCloudShadow（A）", "VolumetricCloudShadow"), ("　CloudSkyAO", "CloudSkyAO"),
             ("　CloudShadow 4096²", "CloudShadow"), ("SkyAtmosphereLUTs（B）", "SkyAtmosphereLUTs"),
             ("　TransmittanceLut", "TransmittanceLut"), ("　MultiScatteringLut", "MultiScatteringLut"),
             ("　RealTimeCaptureCamera360VolumeLut", "RealTimeCaptureCamera360VolumeLut"), ("　CameraVolumeLut", "CameraVolumeLut"),
             ("CaptureConvolveSkyEnvMap（C）", "CaptureConvolveSkyEnvMap"),
             ("太阳延迟光照（D）", "RenderLight Light::StandardDeferred(Single): DirectionalLight"),
             ("ComputeVolumetricFog（E）", "ComputeVolumetricFog"), ("　InitialiseVolume", "VolumetricFog::InitialiseVolume"),
             ("　LightScattering", "VolumetricFog::LightScattering"), ("　FinalIntegration", "VolumetricFog::FinalIntegration"),
             ("VolumetricCloud（F）", "VolumetricCloud"), ("　CloudView " + DIMS, "CloudView (CS) " + DIMS.replace("×", "x")),
             ("　HighQualityAerialPerspectiveOnCloud", "HighQualityAerialPerspectiveOnCloud"),
             ("　ExponentialHeightFog on Clouds", "ExponentialHeightFog on Clouds"), ("LightShafts (Occlusion)（G）", "LightShafts (Occlusion)"),
             ("SkyAtmosphere（H）", "SkyAtmosphere"), ("ExponentialHeightFog（I）", "ExponentialHeightFog"),
             ("VolCloudComposeOverScene（J）", "VolCloudComposeOverScene"), ("PostProcessing（K）", "PostProcessing")]
    a("<table><tr><th>Pass</th><th class='num'>GPU ms</th></tr>%s</table>" % "".join(
        "<tr><td>%s</td><td class='num'>%s</td></tr>" % (esc(lbl), t(n, prefix=n.startswith("RenderLight"))) for lbl, n in items))
    cs = gpu_ms("CloudShadow") or 0.0
    cs_old = gpu_ms("CloudShadow", pattern="profilegpu_unfixed*.json") or 0.0
    vc = gpu_ms("VolumetricCloud") or 0.0
    vc0 = gpu_ms("VolumetricCloud", pattern=os.path.join("..", "gpu_vrt", "mode0.json")) or 0.0
    cap = gpu_ms("CaptureConvolveSkyEnvMap") or 0.0
    a("<ul><li><b>云影图是最大的一项（约 %.0f ms）</b>：4096² × 每像素约 89 个采样（16 × 4 = 64，太阳 31° 时按地平线倍率再加约 25 个），每帧重追踪。"
      "第 8 节的修复前后同一会话实测 %.1f → %.1f ms，几乎不变。要省，就把平行光的 <code>CloudShadowMapResolutionScale</code> 降到 4（2048²，"
      "纹素 19.5 m）、<code>CloudShadowRaySampleCountScale</code> 降到 1，按纹素数和采样数估算能省下大部分（未实测）。</li>"
      "<li>全分辨率体积云（Mode 3）约 %.1f ms；换回默认 Mode 0（每个方向 1/4 分辨率追踪 + 时域重建）实测约 %.1f ms：追踪的像素少 16 倍，时间只少不到 3 倍。</li>"
      "<li>天光实时捕获约 %.1f ms，TimeSlice 1 时分摊到多帧。</li>"
      "<li>大气 LUT、逐像素大气、体积雾（%d×%d×128）、雾与合成都在 1 ms 以内。</li></ul>"
      % (cs, cs_old, cs, vc, vc0, cap, FOG[0], FOG[1]))


def section_repro(a):
    def pool(tag):
        m = meta(tag)
        return "%dx%d" % (m["w"], m["h"])
    crops = " ".join("%s:%dx%d" % (pool(tag), size[0], size[1]) for tag, size in (
        (scene_pair("cloud_compose")[1], VIEW), (dumped("fog_init", "VolumetricFog.VBufferA"), FOG),
        (dumped("shafts", "LightShaftDownsample"), HALF)))
    a("<h2 id='repro'>7. 复现方式、文件与注意事项</h2>")
    a("<h3>7.1 复现</h3><pre><code>"
      "# 1. 生成噪声（系统 Python 3.14 + numpy / Pillow）\n"
      "C:\\Python314\\python.exe Tools/cs_sky/gen_cloud_noise.py --preview\n"
      "# 2. 编辑器内（打开 /CitySamplePCG/Levels/L_CitySamplePCG_Demo，经 run_unreal_script）\n"
      "cs_sky_assets.py      {\"phase\": \"all\"}        # 导入噪声、建体积纹理与云材质（延迟到下一帧执行）\n"
      "cs_clear_sky.py       {\"phase\": \"apply\"}      # 套用本报告的天气与 cvar（首次会快照原值；含第 8 节的云影修复）\n"
      "                      {\"phase\": \"apply\", \"fix_cloud_shadow\": false}   # 换回修复前的云影设置做对比\n"
      "cs_sky_shot.py        {\"name\": \"x\", \"loc\": [58471, 1917, 24700], \"rot\": [14, 155, 0], \"fov\": 60, \"aspect\": 0.6383, \"no_shot\": true}\n"
      "cs_viewport.py        {\"phase\": \"frame\"}      # 视口锁到 CS_SkyCam，游戏视图 + 实时\n"
      "cs_renderdoc_capture.py {\"phase\": \"prepare\"} / {\"phase\": \"capture\"} / {\"phase\": \"restore\"}   # 编辑器需带 -AttachRenderDoc 启动\n"
      "cs_cvar.py            {\"set\": {\"ProfileGPU\": \"\"}}   # 测 GPU 耗时，再用 Tools/cs_sky/parse_profilegpu.py 解析日志\n"
      "cs_clear_sky.py       {\"phase\": \"restore\"}    # 还原关卡原始天气\n"
      "# 3. 离线分析（关掉编辑器腾出显存，qrenderdoc 内置 Python）\n"
      "set CS_RDC=…capture.rdc & set CS_OUT=Saved/Reports/cs_weather/rdc & set CS_FROM=0\n"
      "qrenderdoc.exe --python Tools/cs_sky/rdc_tree.py      # 事件树\n"
      "qrenderdoc.exe --python Tools/cs_sky/rdc_export.py    # 各 pass 的资源与原始像素（视图尺寸从抓帧里读）\n"
      "C:\\Python314\\python.exe Tools/cs_sky/decode_tex.py --crop " + crops + "\n"
      "C:\\Python314\\python.exe Tools/cs_sky/build_report.py # 生成本页"
      "</code></pre>")
    a("<h3>7.2 文件</h3><ul>"
      "<li>抓帧：<code>%s</code>（%.2f GB，可直接用 RenderDoc 打开，按上表的 EID 定位）。RenderDoc 插件按编辑器启动时间给文件命名，"
      "同一次启动的第二份抓帧带 <code>_2</code> 后缀</li>"
      "<li>资产：<code>/Game/CitySampleSky/M_CS_CumulusCloud</code>、<code>MI_CS_CumulusCloud_Clear</code>、"
      "<code>Textures/VT_CS_CloudShape</code>、<code>VT_CS_CloudDetail</code>、<code>T_CS_CloudWeather</code>（及两张图集源图）</li>"
      "<li>脚本：<code>Content/Python/cs_clear_sky.py</code>、<code>cs_sky_assets.py</code>、<code>cs_sky_shot.py</code>、"
      "<code>cs_viewport.py</code>、<code>cs_renderdoc_capture.py</code>、<code>cs_cvar.py</code>、<code>cs_weather_probe.py</code>；"
      "<code>Tools/cs_sky/*.py</code></li>"
      "<li>原值快照：<code>Saved/Reports/cs_weather/original_state.json</code>；GPU 耗时：<code>Saved/Reports/cs_weather/gpu_fin/</code></li></ul>"
      % (esc(CAPTURE), CAPTURE_GB))
    a("<h3>7.3 注意事项</h3><ul>"
      "<li><b>演示关卡没有保存。</b>它是 Epic 的原始内容（外部 actor 文件被 git 忽略）。会话期间在内存里关掉了编辑器自动保存，"
      "重启编辑器后恢复为原设置。重新打开关卡后，运行 <code>cs_clear_sky.py apply</code> 即可重现本报告的天气。</li>"
      "<li><b>这是第四份抓帧。</b>第一份发现关卡自带天空球 <code>SM_SkySphere</code>（<code>M_SimpleSkyDome</code>）会在 BasePass 之后的 "
      "<code>SkyPassParallel</code> 里读 SkyViewLut 画出天空像素，同时让 SkyAtmosphere pass 跳过天空，"
      "编辑器还会多出一个 <code>SkyAtmosphereEditor</code> 提示 pass；当时 <code>SampleCountMax</code> 也误设成 64"
      "（低于项目原值 128；不过实际采样数是 min(32 × <code>TraceSampleCountScale</code> 2, SampleCountMax) = 64，这一项其实没有影响）。隐藏天空球、改回 128 后抓了第二份（2026-11-09）。第 8 节查出云影图的纹素太粗，"
      "修好后的第三份又暴露出光源近平面切进云层（8.6），加上 <code>LightDistanceOverride</code> 后抓了这一份。"
      "第 8 节的机理图仍取自第二份，8.6 的对比图取自第三份。</li>"
      "<li>屏幕百分比改成 100%% 的抓帧把编辑器带崩了（显存：两个编辑器 + 桌面合成已占用约 13 GB，再加抓帧开销）。"
      "所以抓帧用编辑器默认的 72%%（%s）+ TSR，和视口里看到的一致。</li>"
      "<li>高清截图（<code>HighResShot</code>）只渲染单帧，没有 TSR 历史，全分辨率云会带颗粒噪点；横幅对比图和第 9 节的对比图因此在 Mode 0 下拍摄，"
      "最终画面则直接取自抓帧。</li></ul>" % DIMS)
