# cs_weather_presets.py -- the static weather presets of the City Sample demo level, as data (no unreal import), so the
# editor driver (cs_weather.py) and the report builder (Tools/cs_weather/build_report.py) read one source.
#
# A preset = deltas on BASE, the approved 10:00 clear look (cs_clear_sky.py LOOK). Every value carries the reason
# ("why"): which physical quantity it represents and how the reference photo / the physics fixes it.
#   sun    [elevation deg, azimuth deg clockwise from north (+X), why]
#   set    {"Component.property": [value, why]}            component properties (also the VolumetricCloud layer)
#   cloud  {"mi": asset name, "params": {name: [value, why]}}  scalar parameters of the cloud material instance
#   ppv    {post-process setting: [value, why]}              on the unbound PostProcessVolume CS_ClearSky_PPV
#   cvars  {name: value}
#   shots  [[camera label, reference index in picks.json or None]]
# Units: SkyAtmosphere coefficients 1/km, altitudes km; cloud extinction 1/m (VolumetricCloud.usf 713); height fog
# FogDensity is stored /1000 per cm with base-2 transmittance (SceneCore.cpp 404, HeightFogCommon.ush 394), so the
# visibility (2 % contrast) is V = 56.4 / FogDensity m and the density halves every 10 / FogHeightFalloff m.

MATERIAL = "/Game/CitySampleSky/M_CS_CumulusCloud"
MI_DIR = "/Game/CitySampleSky"

# --- the approved 10:00 look (cs_clear_sky.py LOOK, unchanged) --------------------------------------------------------
BASE_SUN = [31.1, 146.0]
BASE = {
    "DirectionalLightComponent": {
        "intensity": 120000.0, "use_temperature": True, "temperature": 5800.0, "light_source_angle": 0.5357,
        "atmosphere_sun_light": True, "atmosphere_sun_light_index": 0, "per_pixel_atmosphere_transmittance": True,
        "cast_shadows_on_atmosphere": True, "cast_shadows_on_clouds": False, "cast_cloud_shadows": True,
        "cloud_shadow_strength": 1.0, "cloud_shadow_on_atmosphere_strength": 1.0, "cloud_shadow_on_surface_strength": 1.0,
        "cloud_shadow_extent": 10.0, "cloud_shadow_map_resolution_scale": 8.0, "cloud_shadow_ray_sample_count_scale": 4.0,
        "cast_volumetric_shadow": True, "volumetric_scattering_intensity": 2.0, "enable_light_shaft_occlusion": True,
        "enable_light_shaft_bloom": False,
    },
    "SkyAtmosphereComponent": {
        "multi_scattering_factor": 1.0, "trace_sample_count_scale": 2.0, "mie_scattering_scale": 0.012,
        "mie_anisotropy": 0.8,
    },
    "SkyLightComponent": {
        "real_time_capture": True, "cubemap_resolution": 256, "cloud_ambient_occlusion": True,
        "cloud_ambient_occlusion_strength": 1.0, "cloud_ambient_occlusion_extent": 60.0,
        "cloud_ambient_occlusion_map_resolution_scale": 2.0, "cloud_ambient_occlusion_aperture_scale": 0.05,
        "intensity": 1.0,
    },
    "VolumetricCloudComponent": {
        "layer_bottom_altitude": 1.4, "layer_height": 4.0, "tracing_max_distance": 40.0, "view_sample_count_scale": 4.0,
        "shadow_view_sample_count_scale": 4.0, "reflection_view_sample_count_scale_value": 2.0,
        "shadow_reflection_view_sample_count_scale_value": 2.0, "shadow_tracing_distance": 15.0,
        "stop_tracing_transmittance_threshold": 0.001, "sky_light_cloud_bottom_occlusion": 0.6,
    },
    "ExponentialHeightFogComponent": {
        "fog_density": 0.006, "fog_height_falloff": 0.04,
        "second_fog_data": {"fog_density": 0.003, "fog_height_falloff": 0.006, "fog_height_offset": 0.0},
        "enable_volumetric_fog": True, "volumetric_fog_scattering_distribution": 0.8,
        "volumetric_fog_albedo": [255, 255, 255, 255], "volumetric_fog_extinction_scale": 1.0,
        "volumetric_fog_distance": 600000.0, "volumetric_fog_start_distance": 0.0,
        "volumetric_fog_static_lighting_scattering_intensity": 1.0,
    },
    "PPV": {
        "auto_exposure_method": "AEM_HISTOGRAM", "auto_exposure_min_brightness": 13.4,
        "auto_exposure_max_brightness": 13.4, "auto_exposure_bias": 0.0,
    },
}
# the clear cumulus instance (MI_CS_CumulusCloud_Clear) + the neutral values of the 2026-11-11 extension
BASE_CLOUD = {
    "WeatherScaleKm": 32.0, "ShapeScaleKm": 3.5, "DetailScaleKm": 0.6, "WarpKm": 1.5, "WarpScaleKm": 15.0,
    "CoverageBias": 0.0, "CoverageScale": 0.8, "DetailStrength": 0.6, "DensityScale": 2.5,
    "TypeMin": 0.3, "TypeMax": 1.0, "BottomRamp": 0.02, "TopRamp": 0.7,
    "WindX": 21.5, "WindY": 23.5, "PixelAngle": 0.0007,
    "ExtinctionMax": 0.12, "PhaseG": 0.6, "PhaseG2": -0.2, "PhaseBlend": 0.25,
    "MSContribution": 0.6, "MSOcclusion": 0.5, "MSEccentricity": 0.5,
    "StretchX": 1.0, "StretchAngle": 0.0, "ShearKm": 0.0,
    "CellX": 0.0, "CellY": 0.0, "CellRadiusKm": 4.0, "CellStrength": 0.0, "CellTopH": 1.0, "CellTopRamp": 0.05,
    "AnvilBottom": 0.75, "AnvilRadiusKm": 15.0, "AnvilShiftKm": 8.0, "CellDensity": 3.0,
    "CellLumpKm": 4.0, "CellLumpAmp": 0.0, "CellSolid": 0.0,
}
BASE_CVARS = {
    "r.SkyAtmosphere.StateVersioning": 0, "r.SkyAtmosphere.FastSkyLUT": 0,
    "r.SkyAtmosphere.AerialPerspectiveLUT.FastApplyOnOpaque": 0, "r.SkyAtmosphere.SampleCountMax": 128,
    "r.SkyAtmosphere.MultiScatteringLUT.HighQuality": 1, "r.SkyAtmosphere.MultiScatteringLUT.SampleCount": 30,
    "r.SkyAtmosphere.TransmittanceLUT.SampleCount": 30, "r.SkyAtmosphere.AerialPerspectiveLUT.Width": 64,
    "r.SkyAtmosphere.AerialPerspectiveLUT.DepthResolution": 32,
    "r.SkyAtmosphere.AerialPerspectiveLUT.SampleCountMaxPerSlice": 4, "r.SkyAtmosphere.LUT32": 1,
    "r.VolumetricCloud.ViewRaySampleMaxCount": 1024, "r.VolumetricCloud.Shadow.ViewRaySampleMaxCount": 128,
    "r.VolumetricCloud.SampleMinCount": 4, "r.VolumetricCloud.HighQualityAerialPerspective": 1,
    "r.VolumetricCloud.ShadowMap.MaxResolution": 4096, "r.VolumetricCloud.ShadowMap.RaySampleMaxCount": 256,
    "r.VolumetricCloud.ShadowMap.SpatialFiltering": 0, "r.VolumetricCloud.ShadowMap.SnapLength": 1,
    "r.VolumetricCloud.ShadowMap.LightDistanceOverride": 80, "r.VolumetricCloud.SkyAO.MaxResolution": 2048,
    "r.VolumetricFog.GridPixelSize": 4, "r.VolumetricFog.GridSizeZ": 128,
    "r.VolumetricFog.HistoryMissSupersampleCount": 8, "r.SkyLight.RealTimeReflectionCapture.TimeSlice": 0,
    # stills: clouds traced per pixel, and 32 HighResShot run-up frames so TSR averages the per-pixel noise away
    "r.VolumetricRenderTarget.Mode": 3, "r.HighResScreenshotDelay": 32,
}

# --- cameras (cm; North = +X, East = +Y; the main tower stands at the origin, roof 438 m, water -24 m) --------------
ACROSS = [-30000.0, 150000.0, -1000.0]        # 14 m above the water, 1.53 km east of the main tower (inside the
                                              # city terrain mesh: beyond y = 1.9 km lies a flat outer water plane)
CAMERAS = {
    "CS_WX_Across": {"loc": ACROSS, "target": [0.0, 0.0, 15000.0], "fov": 40.0, "aspect": 1.6, "res": [1920, 1200]},
    "CS_WX_AcrossTele": {"loc": ACROSS, "target": [0.0, 0.0, 19500.0], "fov": 30.0, "aspect": 1.5, "res": [1800, 1200]},
    "CS_WX_AcrossWide": {"loc": ACROSS, "rot": [12.0, -78.69, 0.0], "fov": 74.0, "aspect": 1.6, "res": [1920, 1200]},
    "CS_WX_AcrossLow": {"loc": ACROSS, "rot": [-2.0, -85.0, 0.0], "fov": 74.0, "aspect": 1.6, "res": [1920, 1200]},
    "CS_WX_AcrossPano": {"loc": ACROSS, "rot": [11.0, -78.69, 0.0], "fov": 68.0, "aspect": 2.1, "res": [2100, 1000]},
    "CS_WX_Skydeck": {"loc": [150000.0, 30000.0, 45000.0], "target": [-50000.0, 0.0, 19000.0], "fov": 42.0, "aspect": 1.5,
                      "res": [1800, 1200]},
    "CS_WX_Far": {"loc": [450000.0, 250000.0, 25000.0], "target": [0.0, 0.0, 10000.0], "fov": 18.0, "aspect": 1.5,
                  "res": [1800, 1200]},
    "CS_WX_Street": {"loc": [3417.0, -4970.0, 19646.0], "rot": [-19.4, 176.15, 0.0], "fov": 50.0, "aspect": 1.3333,
                     "res": [1600, 1200]},
    # the hero camera of the 10:00 report (docs/citysample-clear-sky-renderdoc.html): 247 m above the city, yaw 155 deg,
    # 14 deg up, 60 deg horizontal FOV, portrait. Spelled out (not "existing") so cams recreates it after an editor restart.
    "CS_SkyCam": {"loc": [58471.0, 1917.0, 24700.0], "rot": [14.0, 155.0, 0.0], "fov": 60.0, "aspect": 0.6383,
                  "res": [1080, 1690]},
}

# --- camera rendition shared by every weather preset -------------------------------------------------------------------
# A camera JPEG is not a linear record: its picture style ("Standard") raises mid-tone contrast and saturation by roughly
# 5-15 %. The reference photos all carry it, so every preset gets the same mild emulation; it is not weather physics.
CAMERA_LOOK = {
    "color_saturation": [[1.12, 1.12, 1.12, 1.0], "相机照片风格（Standard）对饱和度的增强，所有天气相同，不属于天气物理"],
    "color_contrast": [[1.06, 1.06, 1.06, 1.0], "相机照片风格的中间调对比度，所有天气相同"],
}

# --- presets -----------------------------------------------------------------------------------------------------------
NO_CLOUD = {"CoverageScale": [0.0, "没有云：覆盖率为 0，云材质每个样本的密度都是 0"]}

PRESETS = {
    "clear_noon": {
        "title": "夏日正午 · 晴空", "ref": "clear_noon",
        "sun": [60.1, 313.5, "参考照片 2012-08-17 12:16 CDT 摄于 Willis Tower 观景台（41.879N, 87.636W）：NOAA 算法给出高度 60.1°、"
                             "方位 161°；照片朝 NNE（≈35°）看，太阳在身后偏右约 125°。演示城市没有真实地理，保持太阳与镜头的相对方位："
                             "对比机位从城北 450 m 高处朝 188.5° 看主楼 → 太阳方位 313.5°"],
        "set": {
            "SkyAtmosphereComponent.mie_scattering_scale": [0.035, "照片里 3–5 km 的楼仍清晰、25 km 的湖面地平线发虚："
                                                            "β≈0.035 km⁻¹（AOD=β·H≈0.04，H=1.2 km）+ 瑞利 0.0136 km⁻¹ → 能见度≈80 km，"
                                                            "25 km 处透射率≈0.3（UE 默认 0.004 只对应 AOD≈0.005）"],
            "SkyAtmosphereComponent.mie_anisotropy": [0.75, "大陆型气溶胶的不对称因子 g≈0.7–0.75"],
            "ExponentialHeightFogComponent.fog_density": [0.0, "雾霾全部由 SkyAtmosphere 的米氏项表示（它同时衰减阳光）；"
                                                          "高度雾的 β=0.0693·FogDensity m⁻¹，0.0015 就有 0.1 km⁻¹，比米氏项还大"],
            "ExponentialHeightFogComponent.second_fog_data": [{"fog_density": 0.0, "fog_height_falloff": 0.006,
                                                               "fog_height_offset": 0.0}, "关掉第二层雾"],
            "VolumetricCloudComponent.layer_bottom_altitude": [1.2, "美国中西部夏季淡积云云底 1.0–1.5 km（抬升凝结高度）"],
            "VolumetricCloudComponent.layer_height": [2.0, "淡积云 Cu humilis 只有几百米厚"],
        },
        "cloud": {"mi": "MI_CS_Cloud_FairCu", "params": {
            "CoverageScale": [0.45, "晴天只有零星淡积云（1–2/8 云量）"],
            "TypeMax": [0.45, "云顶不超过层高的 45%：扁平的淡积云，不发展成浓积云"],
            "DensityScale": [2.0, "密度略低于 10 点的积云"],
        }},
        "ppv": {"auto_exposure_min_brightness": [14.0, "照片 EXIF f/4.5 1/1600 s ISO200 → EV100=13.98"],
                "auto_exposure_max_brightness": [14.0, "min=max 锁定曝光"]},
        "shots": [["CS_WX_Skydeck", 0], ["CS_SkyCam", None]],
    },
    "golden_hour": {
        "title": "黄金时刻 · 逆光日出", "ref": "golden_hour",
        "sun": [6.3, 293.5, "参考照片 2020-09-16 07:11 EDT 摄于泽西城（40.716N, 74.035W），太阳高度 5.7°、方位 91.6°，"
                            "从楼缝里露出来、刚好高出低矮楼顶。演示城市在这个方向的楼顶约 6° 高（10° 窄视场测试镜头量出），"
                            "所以太阳抬高 0.6° 到 6.3°（大气质量 9.2→8.4，影响很小）、放在 293.5° 的楼缝上方"],
        "set": {
            "SkyAtmosphereComponent.mie_scattering": [[0.456, 0.671, 1.0, 1.0], "2020-09-15/16 美国西海岸山火烟雾覆盖纽约：烟雾细粒子"
                                                    "Ångström 指数 α≈1.8，散射 ∝ λ^−1.8 → 680/550/440 nm 为 0.68:1:1.49"],
            "SkyAtmosphereComponent.mie_scattering_scale": [0.07, "AOD(550)≈0.37：β_s(550)=0.07×0.671=0.047 km⁻¹ × 标高 8 km。"
                                                            "照片是 HDR 包围曝光，最暗一帧能记录不溢出的日面，所以“能看清红色日面”不能直接推出"
                                                            "极大的光学厚度；天空仍明亮、日面呈粉橙，对应中等烟雾 AOD≈0.3–0.5（当周纽约实测 0.3–1）"],
            "SkyAtmosphereComponent.mie_exponential_distribution": [8.0, "烟雾在 3–8 km 高空输送、近地面空气相对干净；UE 的米氏层只能是"
                                                                   "从地面起的指数分布，用 8 km 标高把同样的柱总量摊到高空（4 km 标高时近地面太浓，天空一片橙色）"],
            "SkyAtmosphereComponent.mie_absorption": [[0.52, 0.715, 1.0, 1.0], "老化烟雾吸收 Ångström 指数≈1.5"],
            "SkyAtmosphereComponent.mie_absorption_scale": [0.005, "单次散射反照率 ω≈0.93 → β_a(550)=0.0036 km⁻¹"],
            "SkyAtmosphereComponent.mie_anisotropy": [0.7, "烟雾细粒子 g≈0.6–0.7：太阳周围的粉橙光晕"],
            "ExponentialHeightFogComponent.fog_density": [0.0, "气溶胶全部在 SkyAtmosphere 的米氏项里"],
            "ExponentialHeightFogComponent.second_fog_data": [{"fog_density": 0.0, "fog_height_falloff": 0.006,
                                                               "fog_height_offset": 0.0}, "关掉第二层雾"],
        },
        "cloud": {"mi": "MI_CS_Cloud_None", "params": dict(NO_CLOUD)},
        "ppv": {"auto_exposure_min_brightness": [12.8, "照片是 HDR 包围曝光合成（EXIF 中间一帧 EV100=14.3），整体偏亮（high-key）；"
                                                       "全局曝光取 12.8，再用局部曝光压缩天空"],
                "auto_exposure_max_brightness": [12.8, "min=max 锁定曝光"],
                "color_saturation": [[0.95, 0.95, 0.95, 1.0], "HDR 合成（Camera Raw）的照片色彩偏淡：此预设覆盖共用的 1.12"],
                "local_exposure_highlight_contrast_scale": [0.6, "HDR 合成相当于局部色调映射：压缩亮部（天空、太阳）的局部对比度"],
                "local_exposure_shadow_contrast_scale": [0.45, "同上：提亮逆光楼体的暗部（照片里逆光的楼面仍有细节）"],
                "white_temp": [4150.0, "EXIF WhiteBalance=0（自动白平衡）+ Camera Raw：相机只把约 2500 K 的日出光部分校正掉。白点与照片天空的色比"
                                       "（G/R≈0.9、B/R≈0.82）拟合得到 4150 K（臭氧按相机通道平均后，6° 的阳光比 UE 默认少≈20% 的红，"
                                       "所以比不改臭氧时的 3600 K 校正得少）。这是相机处理，不是天气物理"],
                "white_tint": [0.07, "Camera Raw 的色调（tint）：照片的粉桃色偏品红，白点沿等色温线向品红偏 +0.07；同样是拟合相机处理"]},
        "shots": [["CS_WX_Across", 0], ["CS_SkyCam", None]],
    },
    "golden_hour_fire": {
        "title": "黄金时刻 · 火烧云", "ref": "golden_hour",
        "sun": [1.5, 281.3, "参考照片 2014-09-12 06:37 EDT（GPS 40.691N, 74.030W，自由州立公园）朝东拍布鲁克林天际线；EXIF 时刻算出"
                            "高度 0.4°、方位 84.5°。照片里太阳在 1–3° 高的楼群背后射出曙暮光线，说明实际视高度约 1–2°（相机时钟差几分钟）；"
                            "取 1.5°：大气质量≈22，650 nm 透射率≈2%，近地面的霾还能被照亮、形成橙红光晕（0.4° 时 m≈32，光晕被霾自己吃掉）"],
        "set": {
            "SkyAtmosphereComponent.mie_scattering": [[0.456, 0.671, 1.0, 1.0], "相机通道的散射光谱（Ångström α≈1.8 的烟）："
                                                    "照片里太阳周围的橙红光晕必须有波长依赖的散射才会偏红"],
            "SkyAtmosphereComponent.mie_scattering_scale": [0.36, "清晨港口气溶胶 AOD≈0.43（β=0.36×1.2 km，与地平线上橙红光晕的亮度拟合）："
                                                             "臭氧按相机通道平均后会少吃掉一部分红，这里的气溶胶比不修正时更浓才补得回来"],
            "SkyAtmosphereComponent.mie_absorption": [[0.1, 0.45, 1.0, 1.0], "吸收光谱：把绿/蓝压下去，让天空从金黄转向火红（照片的 G/R≈0.43）"],
            "SkyAtmosphereComponent.mie_absorption_scale": [0.05, "β_a(550)=0.05×0.45=0.0225 km⁻¹ → 单次散射反照率 ω≈0.94（烟龄较老的弱吸收)"],
            "SkyAtmosphereComponent.mie_anisotropy": [0.8, "强前向散射：日出方向的光晕"],
            "ExponentialHeightFogComponent.fog_density": [0.0, "气溶胶全部在 SkyAtmosphere 的米氏项里"],
            "ExponentialHeightFogComponent.second_fog_data": [{"fog_density": 0.0, "fog_height_falloff": 0.006,
                                                               "fog_height_offset": 0.0}, "关掉第二层雾"],
            "VolumetricCloudComponent.layer_bottom_altitude": [2.5, "层积云/高积云云底 2.5 km：高度 h 处的云在太阳低于地平线 "
                                                               "√(2h/R)≈1.6° 之前都还能被直射（R=6360 km），这就是日出前后云底先被点亮的原因"],
            "VolumetricCloudComponent.layer_height": [1.0, "云层厚约 1 km"],
            "VolumetricCloudComponent.use_per_sample_atmospheric_light_transmittance":
                [True, "每个云样本按自己的高度取大气透射率：低太阳的光要穿过很长的低层大气，只有红光到得了云底"],
        },
        "cloud": {"mi": "MI_CS_Cloud_Altocumulus", "params": {
            "CoverageScale": [0.9, "照片里是 6–7/8 的成片云层，有缝隙让低太阳的光照进来"], "CoverageBias": [0.05, ""],
            "TypeMin": [0.5, "云块厚度比较一致（层状）"], "TypeMax": [1.0, ""], "TopRamp": [0.4, ""],
            "ShapeScaleKm": [4.0, "大块的层积云"], "DetailStrength": [0.5, ""],
            "DensityScale": [1.5, ""], "ExtinctionMax": [0.06, "层积云/高积云液水 0.1–0.4 g/m³、r_e≈6–8 µm → β≈0.03–0.08 m⁻¹"],
        }},
        "ppv": {"auto_exposure_min_brightness": [10.9, "照片 EXIF f/5.6 1/200 s ISO200 → EV100=11.6；成片比 EXIF 亮约 0.7 EV（作者加了曝光），取 10.9"],
                "auto_exposure_max_brightness": [10.9, "min=max 锁定曝光"],
                "color_saturation": [[1.5, 1.5, 1.5, 1.0], "照片标题 Fiery morning（Flickr），明显后期加了饱和度：此预设覆盖共用的 1.12"],
                "white_temp": [12000.0, "EXIF 是自动白平衡，相机把 2500 K 的日出光大幅校正；照片仍偏橙红，白点远离场景光色温（12000 K）等效于"
                                        "“没有校正掉多少橙”：与照片天空的色比（R/G≈2.3、B/R≈0.16）拟合"],
                "white_tint": [0.2, "Camera Raw 的色调：照片的橙红略偏品红"]},
        "shots": [["CS_WX_Across", 1], ["CS_SkyCam", None]],
    },
    "blue_hour": {
        "title": "蓝调时刻", "ref": "blue_hour",
        "ref_crop": {"0": [0.0, 0.0, 0.42, 1.0]},     # the 4:1 panorama -> its left 42 % (Hancock and the skyline), 1.68:1
        "sun": [-4.8, 56.6, "参考照片 2015-06-27 20:56 CDT 摄于 North Avenue Beach（41.915N, 87.625W）：太阳高度 −4.8°、方位 307.6°；"
                            "照片朝 SSE 看天际线，太阳在身后偏右 137.6°，所以对比机位（朝 279°）对应方位 56.6°"],
        "set": {
            "SkyAtmosphereComponent.mie_scattering_scale": [0.05, "晴朗傍晚 AOD≈0.06"],
            "SkyAtmosphereComponent.mie_anisotropy": [0.75, ""],
            "ExponentialHeightFogComponent.fog_density": [0.0015, "高度雾很薄"],
            "ExponentialHeightFogComponent.second_fog_data": [{"fog_density": 0.0, "fog_height_falloff": 0.006,
                                                               "fog_height_offset": 0.0}, "关掉第二层雾"],
        },
        "cloud": {"mi": "MI_CS_Cloud_None", "params": dict(NO_CLOUD)},
        "ppv": {"auto_exposure_min_brightness": [4.0, "照片 EXIF f/8 4 s ISO100 → EV100=4.0"],
                "auto_exposure_max_brightness": [4.0, "min=max 锁定曝光"]},
        "shots": [["CS_WX_Across", 0], ["CS_SkyCam", None]],
    },
    "overcast": {
        "title": "全阴天 · 层积云", "ref": "overcast",
        "sun": [18.5, 230.0, "参考照片 2016-04-09 17:34 EDT 波士顿：太阳高度 18.5°（被云完全遮住，方向只影响云层亮度分布）"],
        "set": {
            "SkyAtmosphereComponent.mie_scattering_scale": [0.10, "阴天湿度高，AOD≈0.12，远景发灰"],
            "SkyAtmosphereComponent.sky_and_aerial_perspective_luminance_factor": [[0.25, 0.25, 0.25, 1.0],
                "云层下的空气只被云底的漫射光照亮（双流近似透射率≈20–25%）。UE 用云阴影图压暗大气的单次散射，"
                "但多次散射项不受云遮挡，云下的霾会亮得像晴天：按透射率把大气（天空+空气透视）亮度乘 0.25"],
            "ExponentialHeightFogComponent.fog_density": [0.002, "云下薄霭（雾的环境光取自天空捕获，不受上面那个系数影响，所以减半）"],
            "VolumetricCloudComponent.layer_bottom_altitude": [0.8, "层积云云底 0.5–1.5 km"],
            "VolumetricCloudComponent.layer_height": [1.0, "层积云厚 0.5–1 km"],
            "VolumetricCloudComponent.tracing_max_distance": [150.0, "从 247 m 高看 800 m 的云底，云层要到 ≈100 km 外才落到地平线（地球曲率）；"
                                                                 "40 km 的追踪距离会在地平线上留出一条晴空亮带"],
        },
        "cloud": {"mi": "MI_CS_Cloud_Stratocumulus", "params": {
            "CoverageBias": [0.8, "8/8 覆盖：覆盖率整体抬到 1 附近"], "CoverageScale": [0.3, "只留很弱的起伏：层云底部几乎没有结构"],
            "TypeMin": [0.8, "层状：云顶高度一致"], "TypeMax": [1.0, ""], "TopRamp": [0.25, "平顶"], "BottomRamp": [0.08, "平底"],
            "ShapeScaleKm": [3.0, ""], "DetailStrength": [0.3, "细节侵蚀弱：均匀的层状云"], "DensityScale": [1.0, ""],
            "ExtinctionMax": [0.05, "层积云液水 0.2–0.4 g/m³、r_e≈8 µm → β=3·LWC/(2ρ_w r_e)≈0.04–0.08 m⁻¹；1 km 厚 → τ≈40"],
            "MSContribution": [0.8, "厚云的出射光几乎全来自高阶散射：octave 贡献 a=0.8"],
            "MSOcclusion": [0.15, "octave 近似 Σaⁱ·σ·P(cⁱg)·T(bⁱτ)：τ=40 时 b=0.15 让第 3 个 octave 还有 T=e^(−40·0.0225)=0.4，"
                                  "云底亮度≈2400 cd/m²（地面照度 7.5 klux / π），与照片里接近白色的天空一致；b=0.3 时云底暗 3 EV"],
            "MSEccentricity": [0.6, "高阶散射更接近各向同性：octave i 的 g 乘 0.6ⁱ"],
        }},
        "ppv": {"auto_exposure_min_brightness": [10.7, "照片 EXIF f/4.5 1/320 s ISO400 → EV100=10.66"],
                "auto_exposure_max_brightness": [10.7, "min=max 锁定曝光"],
                "white_temp": [4300.0, "相机自动白平衡把阴天光校正成中性灰。UE 的天光在云下捕获，只看得到云底，云的环境光拿不到"
                                       "云层上方的蓝天，整片云被 18° 的阳光（≈4500 K）染黄；白点设 4300 K 等效于相机的 AWB"]},
        "shots": [["CS_WX_Across", 0], ["CS_SkyCam", None]],
    },
    "fog": {
        "title": "雾 · 塔楼浮于雾上", "ref": "fog",
        "sun": [41.2, 191.6, "参考照片 2022-03-15 14:35 CDT 摄于 Adler 天文馆（41.866N, 87.607W）：高度 41.2°、方位 212.6°；"
                             "照片朝 300° 看 Willis Tower，太阳在左侧 87°，所以对比机位（朝 279°）对应方位 191.6°"],
        "set": {
            "SkyAtmosphereComponent.mie_scattering_scale": [0.06, "雾层以上是潮湿的霭（照片里塔顶背后的天空发白发淡），AOD≈0.07"],
            "ExponentialHeightFogComponent.fog_density": [0.004, "雾团之外只有轻霭 V≈14 km：照片前景的湖面和天文馆是清楚的"],
            "ExponentialHeightFogComponent.second_fog_data": [{"fog_density": 0.0, "fog_height_falloff": 0.006,
                                                               "fog_height_offset": 0.0}, "关掉第二层雾"],
            "VolumetricCloudComponent.layer_bottom_altitude": [0.0, "雾就是贴地的层云：云层从地面开始"],
            "VolumetricCloudComponent.layer_height": [0.4, "层顶 400 m，雾顶在其中 75% 处（≈300 m）"],
        },
        "cloud": {"mi": "MI_CS_Cloud_FogBank", "params": {
            "CoverageScale": [0.0, "雾团之外没有云"],
            "CellX": [0.0, "雾团中心在主楼以西 0.6 km（km）"], "CellY": [-0.6, ""],
            "CellRadiusKm": [1.6, "雾团东缘在主楼和机位之间：机位前 0.5 km 的水面是清楚的（照片前景的湖面和天文馆也清楚）"],
            "CellStrength": [1.0, "打开雾团"], "CellTopH": [0.7, "雾顶 ≈280 m（层高 400 m 的 70%，地面以上 ≈240 m）：照片里 Willis Tower（442 m）"
                                                               "露出上面 40–50%，逆温层把雾压在 200–250 m 以下"],
            "CellTopRamp": [0.15, "雾顶起伏的厚度"], "AnvilBottom": [1.0, "没有云砧"], "CellDensity": [1.0, ""],
            "BottomRamp": [0.0, "一直浓到地面"], "ShapeScaleKm": [1.0, "雾顶起伏的尺度几百米"], "DetailStrength": [0.35, ""],
            "ExtinctionMax": [0.008, "雾内能见度 V≈490 m：β=3.912/V=0.008 m⁻¹（照片里雾后的低楼还隐约可见：穿过 ≈0.4 km 雾，"
                                     "τ≈3、透射率≈5%；V=330 m 的浓雾会把整片城市完全遮住）"],
            "PhaseG": [0.8, "雾滴米氏相函数的前向峰 g≈0.8–0.85"], "PhaseG2": [-0.2, ""], "PhaseBlend": [0.2, ""],
            "MSContribution": [0.85, "浓雾里多次散射把光变得接近各向同性，雾从哪个方向看都是亮白的：光学厚的被照亮雾团 "
                                     "L≈E·R/π≈100 klux×0.75/π≈24000 cd/m²（EV15 下比中灰亮 2.5 EV，接近白）。UE 的体积雾只有单次散射，"
                                     "侧向看浓雾会发暗发褐，所以雾团用带多次散射近似的体积云来做，并提高高阶 octave"],
            "MSOcclusion": [0.15, "高阶 octave 的消光只算 15%：光在雾里扩散得更深"], "MSEccentricity": [0.6, ""],
        }},
        "ppv": {"auto_exposure_min_brightness": [15.0, "照片 EXIF f/5 1/2200 s ISO160 → EV100=15.07"],
                "auto_exposure_max_brightness": [15.0, "min=max 锁定曝光"],
                "white_temp": [5600.0, "照片整体偏蓝是相机（富士 X-T4）白平衡的结果，雾本身是中性白；白点 5600 K 模拟这层偏色"]},
        "shots": [["CS_WX_AcrossTele", 0], ["CS_SkyCam", None]],
    },
    "fog_sunrise": {
        "title": "雾 · 日出晨雾", "ref": "fog",
        "sun": [8.1, 257.0, "参考照片 2017-12-04 08:00 EST 泽西城（40.716N, 74.035W）：太阳高度 8.1°、方位 128.7°；"
                            "24 mm 广角（水平 74°），太阳在画面左起 26% 处 → 在镜头中心左侧 18°；对比机位朝 275° → 太阳方位 257°"],
        "set": {
            "SkyAtmosphereComponent.mie_scattering_scale": [0.06, ""],
            "ExponentialHeightFogComponent.fog_density": [0.26, "贴水面的辐射雾/平流轻雾：雾高度基准在 z=−68.5 m，水面（高 44.5 m 处）"
                                                          "密度为 0.26×2^(−0.05×44.5)=0.056 → V=56.4/0.056≈1 km"],
            "ExponentialHeightFogComponent.fog_height_falloff": [0.5, "密度每 20 m 减半：雾只有几十米厚——水面以上 50 m 处 V≈6 km、100 m 处 V≈30 km（照片里楼的上半截清楚）"],
            "ExponentialHeightFogComponent.second_fog_data": [{"fog_density": 0.0, "fog_height_falloff": 0.01,
                                                               "fog_height_offset": 0.0},
                "不要第二层高空霭：它在 6 km 内由体积雾渲染，只有单次散射（g=0.85），背光一侧几乎不被照亮，"
                "会把后面明亮的天空压成褐色（0.003 时仰角 20° 的光学厚度≈0.9）；高空的霭交给 SkyAtmosphere 的米氏项（带多次散射）"],
            "ExponentialHeightFogComponent.volumetric_fog_scattering_distribution": [0.85, "雾滴前向散射：太阳周围的亮晕"],
        },
        "cloud": {"mi": "MI_CS_Cloud_None", "params": dict(NO_CLOUD)},
        "ppv": {"auto_exposure_min_brightness": [14.5, "照片 EXIF f/8 1/800 s ISO100 → EV100=15.6，但成片明显经过提亮（high-key，同一作者的"
                                                       "曼哈顿系列多为 HDR/Camera Raw 处理）：取 14.5，再用局部曝光提亮暗部"],
                "auto_exposure_max_brightness": [14.5, "min=max 锁定曝光"],
                "local_exposure_highlight_contrast_scale": [0.7, "模拟 HDR/Camera Raw 的高光压缩"],
                "local_exposure_shadow_contrast_scale": [0.6, "模拟暗部提亮"],
                "white_temp": [4500.0, "8° 的太阳穿过 m≈6.8 的大气：RGB 透射率约 1:0.6:0.32（≈3200 K）。EXIF 为自动白平衡，"
                                       "相机把这层暖色部分校正掉，水面的反光在照片里是银白偏黄；白点 4500 K 模拟 AWB"],
                "color_saturation": [[1.0, 1.0, 1.0, 1.0], "照片色彩偏淡（高调处理）：此预设覆盖共用的 1.12"]},
        "shots": [["CS_WX_AcrossLow", 1], ["CS_SkyCam", None]],
    },
    "haze": {
        "title": "城市雾霾", "ref": "haze",
        "sun": [49.7, 301.6, "参考照片 2016-09-18 14:28 PDT 摄于好莱坞（34.114N, 118.337W）：高度 49.7°、方位 221.3°；"
                             "照片朝 129° 看洛杉矶市中心（11 km），太阳在右侧 92.6°，对比机位（朝 209°）对应方位 301.6°"],
        "set": {
            "SkyAtmosphereComponent.mie_scattering": [[0.568, 0.748, 1.0, 1.0], "Ångström 指数 α=1.3：散射 ∝ λ^−α，"
                                                    "在 680/550/440 nm 为 0.76:1:1.34（再归一到最大值 1）"],
            "SkyAtmosphereComponent.mie_scattering_scale": [0.267, "照片里 11 km 外的市中心高楼还剩约 40–50% 的视对比度 → 视线光学厚度"
                                                             "τ≈0.7–0.9（C=C₀e^−τ），平均 β≈0.07 km⁻¹，对应能见度≈50 km 的轻度污染日。演示城市的天际线离机位只有 5 km，"
                                                             "要得到同样的 τ：近地面 β_s(550)=0.267×0.748=0.2 km⁻¹（标高 0.45 km）"],
            "SkyAtmosphereComponent.mie_absorption": [[0.27, 0.51, 1.0, 1.0], "棕碳 + NO₂ 的吸收随波长变短急剧增大（吸收 Ångström 指数≈3："
                                                     "680/550/440 nm 为 0.53:1:1.95）→ 透过的光和地平线上的霾带发黄褐"],
            "SkyAtmosphereComponent.mie_absorption_scale": [0.06, "β_a(550)=0.06×0.51=0.03 km⁻¹ → 单次散射反照率 ω≈0.87"],
            "SkyAtmosphereComponent.mie_exponential_distribution": [0.45, "洛杉矶海洋性逆温层把污染压在 0.5 km 左右以下：照片里霾带上沿"
                                                                    "很清楚，其上是蓝天（UE 只能用指数分布，标高取小一点来逼近“盖子”）"],
            "SkyAtmosphereComponent.mie_anisotropy": [0.7, "城市细粒子 g≈0.65–0.7"],
            "ExponentialHeightFogComponent.fog_density": [0.0, "霾全部在 SkyAtmosphere 的米氏项里（高度雾 0.002 就有 β=0.14 km⁻¹，"
                                                       "而且不衰减阳光、没有光谱）"],
            "ExponentialHeightFogComponent.second_fog_data": [{"fog_density": 0.0, "fog_height_falloff": 0.006,
                                                               "fog_height_offset": 0.0}, "关掉第二层雾"],
        },
        "cloud": {"mi": "MI_CS_Cloud_None", "params": dict(NO_CLOUD)},
        "ppv": {"auto_exposure_min_brightness": [14.3, "照片 EXIF f/9 1/500 s ISO200 → EV100=14.31"],
                "auto_exposure_max_brightness": [14.3, "min=max 锁定曝光"]},
        "shots": [["CS_WX_Far", 0], ["CS_SkyCam", None]],
    },
    "dust": {
        "title": "沙尘暴", "ref": "dust",
        "sun": [61.0, 336.0, "参考照片 2009-09-23 11:06 AEST 黄金海岸（28.0S, 153.43E）：太阳高度 61°、方位 17°（南半球，太阳在北边）"],
        "set": {
            "SkyAtmosphereComponent.mie_scattering": [[0.957, 0.978, 1.0, 1.0], "矿物尘粒子大（1–10 µm），散射几乎与波长无关 α≈0.1"],
            "SkyAtmosphereComponent.mie_scattering_scale": [4.14, "照片里 150–300 m 的楼清楚、600 m 左右只剩剪影 → 能见度≈830 m："
                                                            "β_ext(550)=3.912/0.83=4.7 km⁻¹，其中散射 β_s(550)=4.14×0.978=4.05"],
            "SkyAtmosphereComponent.mie_absorption": [[0.094, 0.453, 1.0, 1.0], "澳洲红土富含赤铁矿，强烈吸收蓝紫光：ω(680/550/440)="
                                                     "0.95/0.80/0.65 → β_a=β_s(1−ω)/ω=0.21/1.01/2.23 km⁻¹（照片的棕褐色 G/R≈0.8、B/R≈0.6）"],
            "SkyAtmosphereComponent.mie_absorption_scale": [2.23, ""],
            "SkyAtmosphereComponent.multi_scattering_factor": [0.15, "沙尘层光学厚度≈7，相机高度处直射阳光只剩 e^(−7.1)≈8×10⁻⁴，"
                                                               "画面亮度几乎全靠多次散射。UE 的多次散射 LUT 假设局部光场近似各向同性、均匀；"
                                                               "扩散理论里漫射光随深度按 e^(−kτ) 衰减（k=√(3(1−ω)(1−ωg))≈0.2–0.5，红→蓝），层底只剩 3–20%，"
                                                               "LUT 高估了 5–10 倍（画面发白过曝）：多次散射乘 0.15"],
            "SkyAtmosphereComponent.mie_exponential_distribution": [1.5, "沙尘被抬升到 1–3 km"],
            "SkyAtmosphereComponent.mie_anisotropy": [0.75, "粗粒子强前向散射 g≈0.7–0.8"],
            "ExponentialHeightFogComponent.fog_density": [0.0, "沙尘全部由 SkyAtmosphere 的米氏项表示"],
            "ExponentialHeightFogComponent.second_fog_data": [{"fog_density": 0.0, "fog_height_falloff": 0.006,
                                                               "fog_height_offset": 0.0}, ""],
        },
        "cloud": {"mi": "MI_CS_Cloud_None", "params": dict(NO_CLOUD)},
        "ppv": {"auto_exposure_min_brightness": [12.7, "照片 EXIF f/3.3 1/500 s ISO80 → EV100=12.73（晴天同一时刻约 EV 15：沙尘把照度压低 ≈2.3 EV）"],
                "auto_exposure_max_brightness": [12.7, "min=max 锁定曝光"],
                "white_temp": [3800.0, "沙尘里的光被赤铁矿吸收掉蓝绿，色温只有 ≈2500–3000 K；照片是卡片机自动白平衡，会把橙色校正掉一大半 → "
                                       "照片是棕褐色而不是鲜橙色；白点 3800 K 模拟 AWB"],
                "color_saturation": [[1.0, 1.0, 1.0, 1.0], "卡片机直出，不额外加饱和（覆盖共用的 1.12）"]},
        "shots": [["CS_WX_Street", 0], ["CS_SkyCam", None]],
    },
    "storm": {
        "title": "远方雷暴 · 积雨云砧", "ref": "storm",
        "sun": [57.8, 59.0, "参考照片 2020-06-07 14:07 CEST 克拉科夫：太阳高度 57.8°、方位 220°；积雨云被顺光照亮（太阳在身后偏右）"],
        "set": {
            "SkyAtmosphereComponent.mie_scattering_scale": [0.05, ""],
            "ExponentialHeightFogComponent.fog_density": [0.002, ""],
            "ExponentialHeightFogComponent.second_fog_data": [{"fog_density": 0.0, "fog_height_falloff": 0.006,
                                                               "fog_height_offset": 0.0}, ""],
            "VolumetricCloudComponent.layer_bottom_altitude": [1.0, "积雨云云底 1–1.5 km"],
            "VolumetricCloudComponent.layer_height": [12.0, "云顶冲到对流层顶 ≈13 km"],
            "VolumetricCloudComponent.tracing_max_distance": [100.0, "单体在 25 km 外、云砧向远处铺开"],
            "VolumetricCloudComponent.shadow_tracing_distance": [30.0, "高大云塔的自阴影"],
        },
        "cloud": {"mi": "MI_CS_Cloud_Cumulonimbus", "params": {
            "CoverageScale": [0.35, "周围零星淡积云"], "TypeMin": [0.04, ""], "TypeMax": [0.12, "淡积云只有 1.4 km 厚（层高 12 km 的 12%）"],
            "CellX": [6.56, "单体中心：机位朝 281.3° 方向 35 km 处（km）。照片里砧顶仰角≈25°、张角≈37°：12 km 高的云顶在 25–35 km 外"],
            "CellY": [-32.8, ""],
            "CellRadiusKm": [6.0, "主云塔（多个对流泡合成的云团）半径 ≈6 km"], "CellStrength": [1.0, "打开风暴单体"],
            "CellTopH": [0.9, "云顶 ≈11.8 km（对流层顶）"], "CellTopRamp": [0.1, "云砧顶部较平：对流层顶的逆温层挡住上升气流"],
            "AnvilBottom": [0.62, "云砧从 ≈8.4 km 开始外扩（砧厚 ≈3 km）"], "AnvilRadiusKm": [14.0, "云砧半径 ≈14 km"],
            "AnvilShiftKm": [9.0, "高空风把云砧吹向下风方（砧在画面左侧，与照片一致）"], "StretchAngle": [191.0, "下风方向：画面左侧"],
            "CellLumpKm": [10.0, "低频噪声（Perlin-Worley，10 km 一个周期）调制半径：几 km 大小的一簇簇上升对流泡（turret）"],
            "CellLumpAmp": [0.3, "半径 ±30% 的起伏，云体轮廓成为花椰菜状而不是圆柱"],
            "CellDensity": [3.0, "云塔含水量 1–3 g/m³ → β 0.2–0.4 m⁻¹（ExtinctionMax 0.12 × 3 = 0.36 m⁻¹）"],
            "CellSolid": [0.5, "积雨云核心处处是高含水量的不透明云体：覆盖率=1 时基础噪声本身仍有接近 0 的空洞，"
                               "用 cell² 加权把内部填到至少 0.5 的密度（仍不透明），表面保留噪声起伏、外缘保留花椰菜轮廓；"
                               "填到 1 时云体会变成光滑的“塑料片”"],
            "ShapeScaleKm": [3.0, ""], "DetailStrength": [0.45, "边缘的花椰菜状侵蚀；内部由 CellSolid 保证不透明"],
        }},
        "ppv": {"auto_exposure_min_brightness": [14.9, "照片 EXIF f/5.6 1/1000 s ISO100 → EV100=14.94"],
                "auto_exposure_max_brightness": [14.9, "min=max 锁定曝光"]},
        "shots": [["CS_WX_AcrossPano", 0], ["CS_SkyCam", None]],
    },
    "cirrus": {
        "title": "卷云晴空 · 马尾云", "ref": "cirrus",
        "sun": [29.8, 349.0, "参考照片 2016-06-09 09:25 CEST 西班牙 Bardenas（42.21N, 1.52W）：太阳高度 29.8°、方位 85°（右侧来光）"],
        "set": {
            "SkyAtmosphereComponent.mie_scattering_scale": [0.04, "干燥晴空"],
            "ExponentialHeightFogComponent.fog_density": [0.0015, ""],
            "ExponentialHeightFogComponent.second_fog_data": [{"fog_density": 0.0, "fog_height_falloff": 0.006,
                                                               "fog_height_offset": 0.0}, ""],
            "VolumetricCloudComponent.layer_bottom_altitude": [8.5, "卷云在 7–12 km 的冰晶层"],
            "VolumetricCloudComponent.layer_height": [1.5, "卷云层厚 0.5–2 km"],
        },
        "cloud": {"mi": "MI_CS_Cloud_Cirrus", "params": {
            "CoverageScale": [1.0, "卷云成片：照片里约 4–5/8"], "CoverageBias": [0.0, ""], "TypeMin": [0.6, ""], "TypeMax": [1.0, ""],
            "TopRamp": [0.6, ""], "BottomRamp": [0.3, "底部拖出下落的冰晶幡"],
            "StretchX": [8.0, "沿风向拉长 8 倍：纤维状"], "StretchAngle": [120.0, "高空风向"],
            "ShearKm": [3.0, "随高度错切：下落冰晶在风切变里拖出钩（Ci uncinus）"],
            "ShapeScaleKm": [6.0, ""], "DetailScaleKm": [0.4, ""], "DetailStrength": [0.5, "丝缕状边缘（0.85 时纤维几乎被侵蚀光）"],
            "DensityScale": [1.5, ""], "ExtinctionMax": [0.006, "照片里能看清的毛卷云纤维光学厚度≈0.5–2：冰水含量 0.01–0.05 g/m³、"
                                                         "冰晶有效半径 30–50 µm → β≈0.002–0.01 m⁻¹（0.002 时与太阳成 90° 方向几乎看不见）"],
            "PhaseG": [0.8, "冰晶强前向峰"], "MSContribution": [0.5, "光学厚度 1 左右，多次散射已不可忽略"],
        }},
        "ppv": {"auto_exposure_min_brightness": [14.9, "照片 EXIF f/11 1/500 s ISO200 → EV100=14.88"],
                "auto_exposure_max_brightness": [14.9, "min=max 锁定曝光"]},
        "shots": [["CS_WX_AcrossWide", 0], ["CS_SkyCam", None]],
    },
}

# --- ozone: band-averaged instead of single-wavelength --------------------------------------------------------------------
# UE's default OtherAbsorption is Bruneton's ozone cross-section at 680 / 550 / 440 nm (1.21 / 3.50 / 0.158 e-21 cm^2 ->
# 0.346 : 1 : 0.045 of 0.001881 /km). A camera's red channel is centred near 600 nm, on the Chappuis peak (5.0e-21), so
# at twilight - sunlight crossing the ozone layer on tangent paths hundreds of km long - the 680 nm value lets far too
# much orange through and the sky turns purple. Box averages of the same table over the camera bands: red 580-660 nm
# 3.57, green 500-580 nm 3.10, blue 430-490 nm 0.43 (e-21 cm^2) -> coefficients 0.001919 / 0.001666 / 0.000231 /km.
# In daylight the ozone optical depth is ~0.03 and the change is invisible; every weather preset gets it.
OZONE_BAND = {
    "SkyAtmosphereComponent.other_absorption": [[1.0, 0.868, 0.120, 1.0],
        "臭氧吸收按相机通道带宽平均（红 580–660、绿 500–580、蓝 430–490 nm）：Chappuis 吸收峰在 600 nm，正落在红通道里；"
        "UE 默认用 680/550/440 nm 单波长（红只有绿的 0.35 倍），暮光时天空会偏紫"],
    "SkyAtmosphereComponent.other_absorption_scale": [0.001919, "红通道系数 0.001919 km⁻¹（= 0.001881 × 3.57/3.50），"
                                                     "臭氧层 25 km 处的峰值；整层柱光学厚度≈0.03"],
}
for _p in PRESETS.values():
    for _k, _v in OZONE_BAND.items():
        _p["set"].setdefault(_k, _v)

ORDER = ["clear_noon", "golden_hour", "golden_hour_fire", "blue_hour", "overcast", "fog", "fog_sunrise", "haze", "dust",
         "storm", "cirrus"]

# --- the art-directed cloud weathers (2026-11-11, cs_weather_art.py) ------------------------------------------------------
# Not matched to photos: same format, merged here so the driver handles them like the presets above (they also get the
# band-averaged ozone, which decides the twilight colours). P.ORDER stays the photo presets; P.ART_ORDER lists these.
import importlib as _importlib

import cs_weather_art as _ART

_importlib.reload(_ART)
for _p in _ART.ART.values():
    for _k, _v in OZONE_BAND.items():
        _p["set"].setdefault(_k, _v)
PRESETS.update(_ART.ART)
CAMERAS.update(_ART.ART_CAMERAS)
ART_ORDER = list(_ART.ART_ORDER)
CLOUD_NEUTRAL = dict(_ART.CLOUD_NEUTRAL)
TRANSITION_CLIPS = list(_ART.TRANSITION_CLIPS)
