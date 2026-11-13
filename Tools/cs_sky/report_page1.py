"""Page sections 1-2 of the City Sample clear-sky RenderDoc report (header, look, settings)."""
import os

from build_report import (CAPTURE, CAPTURE_GB, DIMS, ODIMS, REP, esc, fig, jload, settings_table, cloud_code)
from report_images import OUTPUT


def head(a, F, CSS, first_eid, first_end, n_actions):
    a("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
      "<meta name='viewport' content='width=device-width,initial-scale=1'>")
    a("<title>City Sample 晴朗上午 · 大气 / 体积云 / 体积雾 RenderDoc 帧分析</title><style>%s</style></head><body><main>" % CSS)
    a("<h1>City Sample 晴朗上午 · 大气 / 体积云 / 体积雾 RenderDoc 帧分析</h1>")
    a("<div class='sub'>UE 5.8.2（源码版 <code>E:\\UnrealEngine</code>）· D3D12 / SM6 · RenderDoc 1.47 · 关卡 "
      "<code>/CitySamplePCG/Levels/L_CitySamplePCG_Demo</code> · 2026-11-09，2026-11-10 修好云影（第 8 节）后重抓</div>")
    a("<div class='cards'>"
      "<div class='card'><b>时间与太阳</b><span>2026-11-09 上午 10:00（地方太阳时）、北纬 35° → 太阳高度角 31.1°、方位 146°（东南）</span></div>"
      "<div class='card'><b>天气</b><span>晴，淡积云（覆盖约 30%），淡淡的体积雾 + 云隙光柱，云影投在城市与水面</span></div>"
      "<div class='card'><b>机位</b><span>CS_SkyCam：城市上空 247 m，朝东南偏南（yaw 155°）仰 14°，水平 FOV 60°，竖幅 "
      + ODIMS + "</span></div>"
      "<div class='card'><b>分辨率</b><span>内部 " + DIMS + "（编辑器默认屏幕百分比 72%）→ TSR → " + ODIMS + "</span></div>"
      "<div class='card'><b>抓帧</b><span><code>" + esc(CAPTURE) + "</code>（%.2f GB），分析第一次渲染 EID %d–%d，全帧 %d 个 action"
      "</span></div>" % (CAPTURE_GB, first_eid, first_end, n_actions) +
      "<div class='card'><b>多次散射</b><span>大气：MS LUT（Hillaire 2020，高质量 8 个方向）；云：3 阶 octave 近似；"
      "雾：单次散射 + Lumen / 天光环境项</span></div></div>")
    a("<div class='toc'><b>目录</b><ol>"
      "<li><a href='#look'>最终效果与对比</a></li><li><a href='#settings'>天气与渲染设置</a></li>"
      "<li><a href='#frame'>帧结构与场景色演进</a></li><li><a href='#passes'>逐个 Pass 详解</a></li>"
      "<li><a href='#ms'>多次散射是怎么做的</a></li><li><a href='#gpu'>GPU 耗时</a></li>"
      "<li><a href='#repro'>复现方式、文件与注意事项</a></li><li><a href='#shadow'>河面云影的块状 / 锯齿：原因与解决</a></li><li><a href='#godray'>God ray：成因与引擎实现</a></li></ol></div>")


def look(a, F):
    a("<h2 id='look'>1. 最终效果与对比</h2>")
    a("<p>左图直接取自 RenderDoc 抓帧里 <code>Tonemap %dx%d</code> 的输出（R10G10B10A2，显示编码），就是这一帧屏幕上的画面。" % OUTPUT)
    a("太阳躲在一团积云后面，云隙里的光柱（crepuscular rays / god rays）向下扇形洒到水面和城市；天空里是带受光面、银边和"
      "菜花状细节的积云；远处城市被空气透视染成灰蓝；水面上的云影是一朵朵积云的轮廓（第 8 节的修复之前是一块块方格）。</p>")
    a("<div class='row'>%s%s</div>" % (
        fig(F, "hero", "修改后（抓帧最终画面）", max_w=560),
        fig(F, "before_portrait", "修改前（同机位，关卡原始天气：太阳 5000 lux、高度角 24°，City Sample 自带的层状云，未开体积雾）",
            max_w=560)))
    a("<div class='row'>%s%s</div>" % (
        fig(F, "land_before", "修改前：关卡自带机位 CineCameraActor_City_WideView_2", max_w=1100),
        fig(F, "land_after", "修改后：同机位（高清截图，单帧；云影投在水面，云隙光柱落在左侧水面）", max_w=1100)))


def settings(a, F, LOOK, CVARS, O, ocv):
    a("<h2 id='settings'>2. 天气与渲染设置</h2>")
    a("<p>全部改动都在内存里作用于关卡自带的五个天空 actor（DirectionalLight、SkyAtmosphere、SkyLight、VolumetricCloud、"
      "ExponentialHeightFog），另外新增一个无边界 PostProcessVolume（<code>CS_ClearSky_PPV</code>）和一个相机（<code>CS_SkyCam</code>），"
      "并隐藏了关卡的天空球 <code>SM_SkySphere</code>。<b>演示关卡没有保存</b>（Epic 原始内容），"
      "用 <code>cs_clear_sky.py</code> 可一键套用 / 还原；新建的云材质与噪声贴图保存在 <code>/Game/CitySampleSky/</code>。</p>")
    a("<div class='note'>太阳方向：以 +X 为北，方位角 146° 直接对应 UE yaw；平行光朝向 = 太阳的反方向，即 Rotator(pitch −31.1°, yaw −34°)。"
      "强度取大气层顶的太阳照度 120 000 lux，由 SkyAtmosphere 按逐像素透射率衰减（到地面约 9 万 lux）；曝光固定在 EV100 13.4。</div>")
    a(settings_table("2.1 太阳（DirectionalLight）", "DirectionalLightComponent", LOOK["DirectionalLightComponent"], O, {
        "intensity": "大气层顶照度，物理量级", "per_pixel_atmosphere_transmittance": "太阳光色按每个像素自己的大气透射率计算",
        "cast_shadows_on_atmosphere": "VSM 阴影进入大气步进（建筑在空气里的阴影）",
        "cast_cloud_shadows": "开启云影图（地表、大气、体积雾都会用）",
        "cloud_shadow_on_atmosphere_strength": "云影作用于大气 → 大气中的光柱",
        "cloud_shadow_on_surface_strength": "云影作用于地表",
        "cloud_shadow_extent": "云影图实际覆盖 ±2×10 km（40 km 见方），纹素 9.8 m；第一版用 40 km，纹素 78 m，河面云影成块（第 8 节）",
        "cloud_shadow_map_resolution_scale": "512×8 = 4096²（追踪分辨率）", "cloud_shadow_ray_sample_count_scale": "云影步进采样 ×4",
        "volumetric_scattering_intensity": "体积雾里的太阳散射 ×2 → 光柱更亮", "light_source_angle": "真实的太阳角直径",
        "enable_light_shaft_occlusion": "屏幕空间光束遮挡（结果喂给雾 pass）"}))
    a(settings_table("2.2 天空大气（SkyAtmosphere）", "SkyAtmosphereComponent", LOOK["SkyAtmosphereComponent"], O, {
        "multi_scattering_factor": "多次散射 LUT 全量参与（1 = 物理正确）", "trace_sample_count_scale": "大气步进采样数 ×2",
        "mie_scattering_scale": "米氏散射 ×3：清晨薄霾，让光柱看得见", "mie_anisotropy": "米氏前向散射（太阳周围的光晕）"}))
    a(settings_table("2.3 天光（SkyLight）", "SkyLightComponent", LOOK["SkyLightComponent"], O, {
        "real_time_capture": "每帧实时捕获天空与云", "cubemap_resolution": "捕获立方体 256²",
        "cloud_ambient_occlusion": "开启云对天光的遮蔽图（CloudSkyAO）", "cloud_ambient_occlusion_extent": "AO 图覆盖 60 km",
        "cloud_ambient_occlusion_map_resolution_scale": "512×2 = 1024²"}))
    a(settings_table("2.4 体积云组件（VolumetricCloud）", "VolumetricCloudComponent", LOOK["VolumetricCloudComponent"], O, {
        "material": "新的积云材质实例", "layer_bottom_altitude": "云底 1.4 km（相对城市约 1.34 km）", "layer_height": "云层厚 4 km",
        "tracing_max_distance": "追踪距离 40 km（地平线附近的云更实）", "view_sample_count_scale": "主视图采样 ×4",
        "shadow_view_sample_count_scale": "云自阴影二次步进采样 ×4", "stop_tracing_transmittance_threshold": "透射率降到 0.1% 才停止",
        "sky_light_cloud_bottom_occlusion": "云底的天光遮蔽"}))
    a(settings_table("2.5 指数高度雾 + 体积雾（ExponentialHeightFog）", "ExponentialHeightFogComponent",
                     LOOK["ExponentialHeightFogComponent"], O, {
                         "fog_density": "地面附近的淡雾", "fog_height_falloff": "每升高约 250 m 密度减半",
                         "second_fog_data": "第二层：稀薄、每 1.67 km 减半，一直延伸到云底，让光柱在空中可见",
                         "enable_volumetric_fog": "开启体积雾",
                         "volumetric_fog_scattering_distribution": "HG g = 0.8，强前向散射（朝太阳看光柱最亮）",
                         "volumetric_fog_distance": "froxel 覆盖 6 km"}))
    ppv = LOOK["PPV"]
    a("<h4>2.6 曝光（CS_ClearSky_PPV，无边界）</h4><table><tr><th>属性</th><th>值</th><th>说明</th></tr>"
      "<tr><td><code>auto_exposure_method</code></td><td>%s</td><td>直方图测光</td></tr>"
      "<tr><td><code>auto_exposure_min / max_brightness</code></td><td>%s / %s</td><td>EV100 上下限相同 = 固定曝光，抓帧和截图亮度一致</td></tr>"
      "</table>" % (esc(ppv["auto_exposure_method"]), ppv["auto_exposure_min_brightness"], ppv["auto_exposure_max_brightness"]))
    mi = LOOK["CloudMI"]
    a("<h4>2.7 积云材质 <code>/Game/CitySampleSky/M_CS_CumulusCloud</code>（实例 <code>MI_CS_CumulusCloud_Clear</code>）</h4>")
    a("<p>City Sample 原来的 <code>MI_VolumetricCloud_Vancouver</code> 是一层扁平的剖面云。为了得到<b>有很多形状细节的积云</b>，"
      "我新做了一个 Volume 域、Additive、Default Lit、勾选 Used With Volumetric Cloud 的材质，"
      "密度函数写在一个 Custom 节点里（见下方代码），用到三张离线生成的可平铺噪声（<code>Tools/cs_sky/gen_cloud_noise.py</code>）：</p><ul>"
      "<li><b>VT_CS_CloudShape</b> 128³ RGBA：R = Perlin-Worley（Perlin FBM 重映射到反转 Worley FBM 之上，GPU Pro 7 的做法），"
      "G/B/A = 三档频率的反转 Worley FBM；负责云的主体形状，每 %s km 平铺一次。</li>"
      "<li><b>VT_CS_CloudDetail</b> 64³ RGB：三档 Worley FBM，每 %s km 平铺；云底用它做丝状侵蚀，云顶用 1−FBM 做菜花状鼓包，"
      "再叠一层 2.71 倍频率的细节。</li>"
      "<li><b>T_CS_CloudWeather</b> 512² 天气图，每 %s km 平铺：R = 一个个独立的积云单体（大小随机、部分格子留空、中心高四周低），"
      "G = 云高（大云更高，接近浓积云），B = 第二尺度的覆盖率扰动；再用形状噪声对采样坐标做 %s km 的域扭曲，让云底轮廓不规则。</li></ul>"
      % (mi["ShapeScaleKm"], mi["DetailScaleKm"], mi["WeatherScaleKm"], mi["WarpKm"]))
    a("<div class='row'>%s%s%s</div>" % (
        fig(F, "noise_slices", "形状体积 R/G/B/A 与细节体积 R/G/B 的切片", max_w=520),
        fig(F, "noise_weather", "天气图：R 积云单体 / G 云高 / B 第二尺度覆盖率", max_w=520),
        fig(F, "coverage", "相机周围 ±15 km 的覆盖率（红圈 = 相机，黄线 = 云层内的太阳视线，蓝线 = 视野）；"
                           "风偏移 (21.5, 23.5) km 是脚本搜出来的，保证有一团积云挡在太阳前面", max_w=330)))
    rows = [("CoverageScale", "整体覆盖率（0.8 → 约 30% 天空有云，晴间多云）"), ("DetailStrength", "细节侵蚀强度"),
            ("DensityScale", "密度倍率（边缘更硬朗）"), ("ExtinctionMax", "最大消光系数 1/m（真实积云约 0.05–0.1）"),
            ("TypeMin", "最矮的云占层厚的比例"), ("TypeMax", "最高的云占层厚的比例（4 km 浓积云）"),
            ("BottomRamp", "云底过渡高度（平底）"), ("TopRamp", "云顶收缩比例（圆顶）"),
            ("PhaseG", "HG 前向波瓣 g（逆光银边）"), ("PhaseG2", "后向波瓣 g"), ("PhaseBlend", "两个波瓣的混合"),
            ("MSContribution", "多次散射 a：每阶的散射贡献"), ("MSOcclusion", "多次散射 b：每阶的消光（遮挡）衰减"),
            ("MSEccentricity", "多次散射 c：每阶相函数向各向同性靠拢的程度")]
    a("<table><tr><th>参数</th><th>值</th><th>含义</th></tr>%s</table>" % "".join(
        "<tr><td><code>%s</code></td><td class='num'>%s</td><td>%s</td></tr>" % (k, mi[k], t) for k, t in rows))
    a("<p>材质的 VolumetricAdvancedMaterialOutput：<code>MultiScatteringApproximationOctaveCount = 2</code>（共 3 阶，为最大值），"
      "<code>bGroundContribution</code> 开（地面反照率照亮云底），<code>bRayMarchVolumeShadow</code> 开（云自阴影用二次步进，不用阴影图），"
      "<code>ConservativeDensity</code> 接“剖面 × 覆盖率”（让步进跳过空区）。噪声采样的 mip 按到相机的距离计算，远处的云不会闪烁。</p>")
    a("<pre><code>%s</code></pre>" % esc(cloud_code()))
    rows = []
    for k, v in CVARS.items():
        o = ocv.get(k)
        rows.append("<tr><td><code>%s</code></td><td class='num'>%s</td><td class='num'><b>%s</b></td></tr>" % (
            esc(k), "%g" % o if o is not None else "—", v))
    a("<h4>2.8 控制台变量（原值来自项目的 Epic 画质档位；全部只往更高质量的方向改）</h4>"
      "<table><tr><th>CVar</th><th>原值</th><th>新值</th></tr>%s</table>" % "".join(rows))
    a("<ul><li><code>r.SkyAtmosphere.StateVersioning 0</code>、<code>r.SkyLight.RealTimeReflectionCapture.TimeSlice 0</code>："
      "Transmittance / MultiScattering LUT 和天光捕获的 6 个面<b>每帧都重算</b>，否则它们只在状态变化时更新，抓帧里会缺。</li>"
      "<li><code>r.SkyAtmosphere.FastSkyLUT 0</code> + <code>AerialPerspectiveLUT.FastApplyOnOpaque 0</code>：天空和不透明物体的空气透视"
      "都改成逐像素光线步进（每个采样点都查云影图和 VSM），不再从 192×104 / 64×64×32 的 LUT 里插值。</li>"
      "<li><code>r.VolumetricRenderTarget.Mode 3</code>（Cinematic）：体积云在全分辨率下逐像素追踪，"
      "不再是 1/4 分辨率追踪 + 时域重建，所以帧里没有 VolumetricReconstruct pass。</li>"
      "<li><code>r.VolumetricCloud.HighQualityAerialPerspective 1</code>：云上的空气透视也逐像素步进（见 Pass F2）。</li>"
      "<li><code>r.VolumetricCloud.ShadowMap.SpatialFiltering 0</code>、<code>SnapLength 1</code>、"
      "<code>LightDistanceOverride 80</code>：和平行光的 <code>CloudShadowExtent 10</code> 一起，把云影图从 78 m 一个纹素"
      "细化到 9.8 m，并让整张图都从云层上方开始追踪（第 8 节）。<code>cs_clear_sky.py</code> 默认就套用这一组；"
      "<code>{\"fix_cloud_shadow\": false}</code> 换回第一版（40 km、滤波 1、默认光源距离）做对比。</li>"
      "<li>隐藏天空球 <code>SM_SkySphere</code>：它的材质 <code>/Engine/EngineSky/M_SimpleSkyDome</code> 是 IsSky 材质，"
      "只读 SkyViewLut 画天空；它可见时 SkyAtmosphere pass 会跳过天空像素，<code>FastSkyLUT 0</code> 对天空不起作用"
      "（第一次抓帧里实测到的，见第 7 节）。</li></ul>")
    a("<div class='note'>抓帧时为了让 pass 按顺序排在图形队列上、不让 DXR 加速结构把抓帧撑大，临时设置了 "
      "<code>r.RDG.AsyncCompute 0</code>、<code>r.Lumen.HardwareRayTracing 0</code>（Lumen 改用软件追踪）和 "
      "<code>renderdoc.CaptureCallstacks 0</code>，抓完已恢复。这三项不影响大气、云、雾的任何 pass。</div>")
