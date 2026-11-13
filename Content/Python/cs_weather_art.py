# cs_weather_art.py -- the art-directed volumetric-cloud weathers (2026-11-11): classic times of day where the clouds
# show each weather's own character. Not matched to photos: lighting stays physical (sun / moon, atmosphere, multiple
# scattering); cameras, exposure and grading serve the picture, and grading is flagged as art direction.
# Same format as cs_weather_presets.PRESETS (which merges these); every value is [value, why]. Data only, no unreal import.
# Heights of the 2026-11-11 material features (BaseKm, Front*, Lens*, Mamma*, Overshoot*) are km above the layer bottom.
# Directions: compass degrees, north = +X, east = +Y (a camera's UE yaw is its compass heading); the storm cell /
# front / lens positions are km in world X / Y.

ACROSS = [-30000.0, 150000.0, -1000.0]       # 14 m above the water, 1.53 km east of the main tower (cs_weather_presets)

ART_CAMERAS = {
    # wide shots from the water across to the city (heading 280 = WNW over the skyline)
    "CS_ART_Wide": {"loc": ACROSS, "rot": [16.0, -80.0, 0.0], "fov": 84.0, "aspect": 1.6, "res": [1920, 1200]},
    "CS_ART_Up": {"loc": ACROSS, "rot": [24.0, -80.0, 0.0], "fov": 84.0, "aspect": 1.6, "res": [1920, 1200]},
    "CS_ART_Towers": {"loc": ACROSS, "rot": [11.0, -80.0, 0.0], "fov": 64.0, "aspect": 1.6, "res": [1920, 1200]},
    "CS_ART_Rays": {"loc": ACROSS, "rot": [7.0, -78.0, 0.0], "fov": 62.0, "aspect": 1.6, "res": [1920, 1200]},
    # 120 m above the water east of the island: most of the skyline stays below 4 deg, the storm stands left of the tower
    "CS_ART_Storm": {"loc": [-30000.0, 150000.0, 12000.0], "rot": [8.0, -106.0, 0.0], "fov": 50.0, "aspect": 2.0,
                     "res": [2200, 1100]},
    "CS_ART_Moon": {"loc": ACROSS, "rot": [20.0, -60.0, 0.0], "fov": 84.0, "aspect": 1.6, "res": [1920, 1200]},
    # 620 m above the city's NE corner, looking SSW down at the main tower: the cloud sea from above
    "CS_ART_Sea": {"loc": [180000.0, 90000.0, 62000.0], "target": [0.0, 0.0, 26000.0], "fov": 70.0, "aspect": 1.6,
                   "res": [1920, 1200]},
    # from the water, looking WNW along the cloud streets over the skyline
    "CS_ART_Streets": {"loc": ACROSS, "rot": [18.0, -80.0, 0.0], "fov": 84.0, "aspect": 1.6,
                       "res": [1920, 1200]},
    # 4.5 km NE of the tower, telephoto SSW over the city towards the lens clouds 25 km away
    "CS_ART_Lens": {"loc": [450000.0, 250000.0, 25000.0], "rot": [5.0, -151.0, 0.0], "fov": 38.0, "aspect": 1.6,
                    "res": [1920, 1200]},
    # 21 m above the water: the demo's water renders dull below a camera height of ~19.5 m and reflective above it, so
    # the transition clips that move the camera vertically start / end here instead of crossing the switch (Task 11)
    "CS_ART_WideHi": {"loc": [-30000.0, 150000.0, -300.0], "rot": [16.0, -80.0, 0.0], "fov": 84.0, "aspect": 1.6,
                      "res": [1920, 1200]},
    "CS_ART_TowersHi": {"loc": [-30000.0, 150000.0, -300.0], "rot": [11.0, -80.0, 0.0], "fov": 64.0, "aspect": 1.6,
                        "res": [1920, 1200]},
}

# the neutral values of the art extension of M_CS_CumulusCloud (cs_sky_assets.SCALARS after CellSolid): the driver
# writes them into every cloud instance before the preset's own values, so a parameter a preset stops setting goes
# back to neutral instead of keeping a stale override (Tools/cs_weather/check_art.py checks they match the material)
CLOUD_NEUTRAL = {
    "LayerKm": 4.0, "BaseKm": 0.0, "RainDensity": 0.0, "RainX": 0.0, "RainY": 0.0, "RainRadiusKm": 5.0,
    "RainStreakKm": 0.4, "RainSlantKm": 0.0, "AnvilRamp": 1.0, "OvershootKm": 0.0, "OvershootRadiusKm": 3.0,
    "TurretAmt": 0.0, "TurretScaleKm": 2.0, "MammaAmt": 0.0, "MammaScaleKm": 1.5, "MammaDepthKm": 0.6,
    "BillowAmt": 0.0, "BillowScaleKm": 1.5, "PowderAmt": 0.0, "PowderK": 3.0, "MackerelAmt": 0.0,
    "MackerelScaleKm": 0.6, "MackerelGap": 0.45, "MackerelStretch": 1.0, "RollAmt": 0.0, "RollSpacingKm": 4.0,
    "RollAngle": 0.0, "FrontAmt": 0.0, "FrontX": 0.0, "FrontY": 0.0, "FrontAngle": 0.0, "FrontHalfLenKm": 30.0,
    "FrontBowKm": 4.0, "FrontWobbleKm": 1.0, "FrontDepthKm": 6.0, "FrontBaseKm": 0.8, "FrontTopKm": 3.0,
    "FrontSlopeKm": 2.0, "FrontTiers": 3.0, "FrontDensity": 1.5, "LensAmt": 0.0, "LensScaleKm": 60.0,
    "LensElong": 2.0, "LensBaseKm": 4.0, "LensPlates": 3.0, "LensSpacingKm": 0.35, "LensThickKm": 0.25,
    "LensShrink": 0.25, "LensJitterKm": 0.5, "LensDensity": 1.0, "StormAO": 1.0, "LensCut": 0.15,
}

# shared art grading: a light vignette on top of the camera look every weather preset already has (CAMERA_LOOK)
ART_LOOK = {
    "vignette_intensity": [0.55, "艺术处理：暗角比引擎默认的 0.4 稍重，把视线收向画面中间的云（不属于天气物理）"],
}


def _ppv(**kw):
    out = dict(ART_LOOK)
    out.update(kw)
    return out


def _fog_off():
    return {
        "ExponentialHeightFogComponent.fog_density": [0.0, "雾霭交给 SkyAtmosphere 的米氏项（带多次散射、会衰减阳光）"],
        "ExponentialHeightFogComponent.second_fog_data": [{"fog_density": 0.0, "fog_height_falloff": 0.006,
                                                           "fog_height_offset": 0.0}, "关掉第二层雾"],
    }


ART = {
    # 1 ------------------------------------------------------------------------------------------------------------
    "art_mackerel": {
        "title": "日出 · 鱼鳞天", "en": "Sunrise mackerel sky", "time": "日出前（太阳 −0.8°）",
        "sun": [-0.8, 228.0, "太阳还在地平线下 0.8°：地面在曙光的蓝色里，3.5–4.5 km 的高积云却已被直射——高度 h 的云在太阳低于"
                             "地平线 √(2h/R)≈2.1° 之前都看得到太阳。阳光此时从下往上照，只剩穿过上百公里低层大气的红光，云底被点成橙红；"
                             "太阳放在画面左侧外面一点，云从左到右由金红渐变到粉紫"],
        "set": dict(_fog_off(), **{
            "SkyAtmosphereComponent.mie_scattering_scale": [0.012, "清晨空气干净（AOD≈0.015）：照亮云底的红光才能穿过长长的低层大气"],
            "VolumetricCloudComponent.layer_bottom_altitude": [3.5, "高积云 Ac 在 2–6 km 的中层"],
            "VolumetricCloudComponent.layer_height": [1.0, "一层薄薄的云块，单块厚几百米"],
            "VolumetricCloudComponent.use_per_sample_atmospheric_light_transmittance":
                [True, "每个云样本按自己的位置取阳光的大气透射率：远处、低处的云先进地影，颜色随距离变化"],
            "VolumetricCloudComponent.tracing_max_distance": [80.0, "鱼鳞天铺满半个天空，一直延伸到地平线"],
        }),
        "cloud": {"mi": "MI_CS_Art_Mackerel", "params": {
            "MackerelAmt": [1.0, "打开胞状覆盖：云块由一个个 Worley 细胞组成，细胞之间是蓝天缝"],
            "MackerelScaleKm": [0.45, "单个云块≈0.3–0.5 km：高积云的单元在天顶的视角 1–5°，对应 4 km 高处几百米"],
            "MackerelGap": [0.25, "细胞边缘留一道窄缝：云块挨得很近，像鱼鳞"],
            "MackerelStretch": [1.6, "沿行的方向拉长云块"],
            "StretchAngle": [20.0, "云块拉长的方向"],
            "RollAmt": [0.5, "行：中层风切变造成的开尔文-亥姆霍兹波把云块排成一行行（波状 undulatus）；"
                             "这里借用积云街的条纹，间距更小"],
            "RollSpacingKm": [1.2, "相邻两行≈1 km"], "RollAngle": [30.0, "行的走向，与镜头方向斜交"],
            "CoverageScale": [0.5, "大尺度覆盖率只调制鱼鳞的疏密"], "CoverageBias": [0.4, ""],
            "TypeMin": [0.35, "云块薄而均匀"], "TypeMax": [0.75, ""], "TopRamp": [0.6, "圆顶"],
            "BottomRamp": [0.25, "云底也是圆的（高积云不像积云那样有平底）"],
            "DetailStrength": [0.15, "边缘轻微侵蚀"], "DetailScaleKm": [0.3, ""], "ShapeScaleKm": [1.0, ""],
            "DensityScale": [1.2, ""],
            "ExtinctionMax": [0.05, "高积云液水 0.1–0.3 g/m³、r_e≈5–8 µm → β≈0.03–0.06 m⁻¹：云块中心不透明、边缘半透明"],
            "PhaseG": [0.75, "水滴的前向散射峰：靠近太阳那一侧的云边特别亮"],
            "MSContribution": [0.6, ""], "MSOcclusion": [0.4, ""],
        }},
        "ppv": _ppv(auto_exposure_min_brightness=[9.0, "曝光按亮起来的云定：云底亮、城市沉在暗蓝里"],
                    auto_exposure_max_brightness=[9.0, "min=max 锁定曝光"],
                    local_exposure_highlight_contrast_scale=[0.75, "艺术处理：稍微压一下太阳附近最亮的云"]),
        "shots": [["CS_ART_Wide", None], ["CS_SkyCam", None]],
    },
    # 2 ------------------------------------------------------------------------------------------------------------
    "art_cloudsea": {
        "title": "清晨 · 云海", "en": "Sea of clouds at dawn", "time": "清晨（太阳 4°）",
        "sun": [4.0, 166.0, "4° 的低太阳从画面左前方擦过云顶：入射角越掠，云顶的起伏投下的阴影越长、越能看出形状；"
                            "露出云海的塔楼在云顶上投下长 (H−300 m)/tan4°≈2–3 km 的影子"],
        "set": dict(_fog_off(), **{
            "SkyAtmosphereComponent.mie_scattering_scale": [0.03, "清晨略有霭，太阳周围有暖色光晕"],
            "VolumetricCloudComponent.layer_bottom_altitude": [0.0, "层云 / 辐射雾贴着地面"],
            "VolumetricCloudComponent.layer_height": [0.4, "层顶 400 m，云顶在其中 60–75%（240–300 m）"],
            "VolumetricCloudComponent.tracing_max_distance": [60.0, "云海铺到地平线"],
            "DirectionalLightComponent.cast_shadows_on_clouds":
                [True, "让塔楼的影子落到云上：云去采样太阳的阴影图（含虚拟阴影图，VolumetricCloudRendering.cpp）"],
        }),
        "cloud": {"mi": "MI_CS_Art_CloudSea", "params": {
            "CoverageBias": [1.0, "8/8 覆盖：整层层云"], "CoverageScale": [0.0, ""],
            "TypeMin": [0.6, "云顶 240–300 m：逆温层把雾压在下面，云顶几乎齐平"], "TypeMax": [0.75, ""],
            "TopRamp": [0.3, "云顶的起伏几十米"], "BottomRamp": [0.0, "一直浓到地面"],
            "BillowAmt": [0.5, "云顶一团团的鼓包：雾顶的辐射冷却引起弱对流，顶面像棉被一样起伏"],
            "BillowScaleKm": [0.25, "鼓包≈200–300 m"],
            "ShapeScaleKm": [0.8, "云顶的波浪几百米一个"], "DetailStrength": [0.25, ""], "DetailScaleKm": [0.25, ""],
            "DensityScale": [1.0, ""],
            "ExtinctionMax": [0.02, "层云 / 浓雾：能见度≈200 m → β=3.912/V≈0.02 m⁻¹"],
            "PhaseG": [0.8, "雾滴前向散射：迎着太阳的云海发亮"],
            "MSContribution": [0.85, "光学厚度几十：亮度几乎全来自多次散射，云顶像棉被一样白"], "MSOcclusion": [0.15, ""],
            "MSEccentricity": [0.6, ""],
        }},
        "ppv": _ppv(auto_exposure_min_brightness=[12.9, "曝光按被低太阳照亮的云顶定，让云顶留住层次"],
                    auto_exposure_max_brightness=[12.9, "min=max 锁定曝光"]),
        "shots": [["CS_ART_Sea", None], ["CS_SkyCam", None]],
    },
    # 3 ------------------------------------------------------------------------------------------------------------
    "art_towers": {
        "title": "午后 · 浓积云塔", "en": "Towering cumulus", "time": "午后（太阳 38°）",
        "sun": [38.0, 195.0, "午后的太阳从画面左侧照来：向阳的云塔雪白、背阴面和平底深灰；太阳在观者身后时，糖粉效应最明显"],
        "set": dict(_fog_off(), **{
            "SkyAtmosphereComponent.mie_scattering_scale": [0.02, "对流天的空气通透"],
            "VolumetricCloudComponent.layer_bottom_altitude": [1.2, "云底在抬升凝结高度 LCL≈125 m×(T−Td)：午后约 1.2 km，所有云的底齐平"],
            "VolumetricCloudComponent.layer_height": [6.0, "浓积云 Cu congestus 长到 5–7 km"],
            "VolumetricCloudComponent.shadow_tracing_distance": [25.0, "高大云塔的自阴影要走得更远"],
        }),
        "cloud": {"mi": "MI_CS_Art_Towers", "params": {
            "WeatherScaleKm": [48.0, "天气图放大：云团更大、彼此离得更远"],
            "CoverageScale": [0.75, "一座座孤立的云塔，中间是蓝天"], "CoverageBias": [-0.1, ""],
            "TypeMin": [0.25, "小的云团只是淡积云"], "TypeMax": [1.0, "大的云团一直长到层顶"],
            "TopRamp": [0.45, "圆顶：越往上云团越窄，云塔成穹顶状"],
            "BottomRamp": [0.02, "平底"], "ShapeScaleKm": [5.0, "云团几公里"],
            "BillowAmt": [0.6, "对流泡：倒置 Worley 的等值面是一串球面——一团团上升的热泡，轮廓成为花椰菜状"],
            "BillowScaleKm": [1.0, "单个对流泡≈1 km"],
            "DetailStrength": [0.3, ""], "DetailScaleKm": [0.5, ""], "DensityScale": [3.0, ""],
            "ExtinctionMax": [0.15, "浓积云液水 0.5–1.5 g/m³ → β 0.1–0.3 m⁻¹：边界锐利（几十米内从透明变成不透明）"],
            "PowderAmt": [0.7, "糖粉效应（Horizon Zero Dawn 的 Beer-Powder）：顺光看时，薄的云边和凹处散射回来的光少，"
                               "显得发暗，云体有“粉感”；逆光时不起作用（银边）"],
            "PowderK": [4.0, ""],
            "PhaseG": [0.75, ""], "MSContribution": [0.6, ""], "MSOcclusion": [0.4, ""],
        }},
        "ppv": _ppv(auto_exposure_min_brightness=[14.2, "晴天下午"], auto_exposure_max_brightness=[14.2, ""],
                    color_contrast=[[1.12, 1.12, 1.12, 1.0], "艺术处理：加对比，强调云塔的明暗"]),
        "shots": [["CS_ART_Towers", None], ["CS_SkyCam", None]],
    },
    # 4 ------------------------------------------------------------------------------------------------------------
    "art_rays": {
        "title": "傍晚 · 雨后云隙光", "en": "Crepuscular rays after rain", "time": "傍晚（太阳 6°）",
        "sun": [6.0, 288.0, "太阳躲在层积云后面，正对镜头：光从云缝里漏出来，在湿空气里照出一束束光；"
                            "光束其实是平行的，看起来从太阳处散开是透视"],
        "set": {
            "SkyAtmosphereComponent.mie_scattering_scale": [0.12, "雨后湿空气，气溶胶吸湿长大（AOD≈0.15）：光束靠米氏散射显出来"],
            "SkyAtmosphereComponent.mie_anisotropy": [0.82, "强前向散射：越靠近太阳的光束越亮"],
            "ExponentialHeightFogComponent.fog_density": [0.006, "低空薄霭（V≈9 km），体积雾在 6 km 内接住云影，光束更清楚"],
            "ExponentialHeightFogComponent.fog_height_falloff": [0.03, ""],
            "ExponentialHeightFogComponent.second_fog_data": [{"fog_density": 0.0, "fog_height_falloff": 0.006,
                                                               "fog_height_offset": 0.0}, ""],
            "ExponentialHeightFogComponent.volumetric_fog_scattering_distribution": [0.85, "前向散射：迎着太阳的光束"],
            "VolumetricCloudComponent.layer_bottom_altitude": [1.2, "层积云 Sc，云底 1–1.5 km"],
            "VolumetricCloudComponent.layer_height": [0.9, "厚度不到 1 km"],
            "VolumetricCloudComponent.tracing_max_distance": [80.0, ""],
        },
        "cloud": {"mi": "MI_CS_Art_Rays", "params": {
            "CoverageScale": [0.7, "约 6/8 的云量，留出云缝让光漏下来"], "CoverageBias": [0.3, ""],
            "TypeMin": [0.6, "层状"], "TypeMax": [1.0, ""], "TopRamp": [0.3, ""], "BottomRamp": [0.1, ""],
            "ShapeScaleKm": [2.5, ""], "DetailStrength": [0.35, ""], "DensityScale": [2.0, ""],
            "ExtinctionMax": [0.06, "层积云 β≈0.04–0.08 m⁻¹：厚的地方完全挡住太阳"],
            "PhaseG": [0.8, "云边的银边"], "MSContribution": [0.6, ""], "MSOcclusion": [0.35, ""],
        }},
        "ppv": _ppv(auto_exposure_min_brightness=[10.7, "曝光按光束和云边定，云底压暗"],
                    auto_exposure_max_brightness=[10.7, ""],
                    local_exposure_highlight_contrast_scale=[0.7, "艺术处理：压一下太阳附近最亮的地方"]),
        "shots": [["CS_ART_Rays", None], ["CS_SkyCam", None]],
    },
    # 5 ------------------------------------------------------------------------------------------------------------
    "art_storm": {
        "title": "日落 · 远方雷暴", "en": "Sunset thunderstorm with mammatus", "time": "日落后片刻（太阳 −0.8°）",
        "sun": [-0.8, 85.0, "太阳在镜头背后、刚落到地平线下：城市和低空进入地影，50 km 外的积雨云在 1.5 km 以上仍被照亮——"
                             "这时的阳光从下往上照，正好打亮云砧的下表面和挂在下面的乳状云"],
        "set": dict(_fog_off(), **{
            "SkyAtmosphereComponent.mie_scattering_scale": [0.02, "雷暴前空气干净：照到云上的光才够红够亮"],
            "VolumetricCloudComponent.layer_bottom_altitude": [0.0, "层从地面开始，雨幕才有地方画；云本身从 BaseKm 开始"],
            "VolumetricCloudComponent.layer_height": [13.0, "积雨云顶冲到对流层顶 ≈11–13 km"],
            "VolumetricCloudComponent.tracing_max_distance": [150.0, "50 km 外的云塔和它旁边的云砧都要追踪到"],
            "VolumetricCloudComponent.shadow_tracing_distance": [40.0, "云塔的自阴影"],
            "VolumetricCloudComponent.use_per_sample_atmospheric_light_transmittance":
                [True, "每个样本自己判断是否在地影里：云底暗、上部亮"],
        }),
        "cloud": {"mi": "MI_CS_Art_Storm", "params": {
            "BaseKm": [1.2, "云底 1.2 km（抬升凝结高度）"],
            "CoverageScale": [0.25, "周围零星的淡积云"], "TypeMin": [0.03, ""], "TypeMax": [0.12, ""],
            "CellX": [-10.8, "单体中心：镜头朝 256° 方向 50 km 处（km），在城市天际线左侧"], "CellY": [-47.0, ""],
            "CellRadiusKm": [7.0, "主云塔半径 ≈7 km"], "CellStrength": [1.0, ""],
            "CellTopH": [0.82, "云顶 ≈11 km（对流层顶）"], "CellTopRamp": [0.08, "砧顶平：对流层顶的逆温挡住上升气流"],
            "AnvilBottom": [0.62, "云砧从 ≈8.5 km 开始铺开"],
            "AnvilRamp": [0.25, "云砧在一薄层里铺开：平的下表面，乳状云就挂在它下面"],
            "AnvilRadiusKm": [16.0, "云砧铺开 ≈16 km"], "AnvilShiftKm": [14.0, "高空风把云砧吹向下风方向（画面左侧）：一侧伸出长长的砧"],
            "StretchAngle": [190.0, "高空风吹向南偏西：云砧向画面左侧伸出，从侧面看得到完整的砧形和它下面的乳状云"],
            "OvershootKm": [1.2, "上冲云顶：最强的上升气流冲过对流层顶，在砧顶上鼓起一个穹顶"],
            "OvershootRadiusKm": [3.5, ""],
            "TurretAmt": [0.8, "云塔外沿由一团团对流泡组成（花椰菜状），而不是一根圆柱"], "TurretScaleKm": [3.0, ""],
            "CellLumpKm": [10.0, ""], "CellLumpAmp": [0.3, ""],
            "CellDensity": [3.0, "云塔含水量 1–3 g/m³ → β 0.2–0.4 m⁻¹"], "CellSolid": [0.5, "核心处处不透明"],
            "MammaAmt": [1.0, "乳状云：云砧下沉的冷空气形成一个个下垂的囊"],
            "MammaScaleKm": [2.0, "每个囊直径 1–2 km"], "MammaDepthKm": [1.0, "下垂几百米到 1 km"],
            "StormAO": [0.25, "天光遮蔽：厚厚的云砧挡住了来自上方的天光，云塔背阴面、云砧下表面和乳状云只剩地面和低空的反射光"],
            "RainDensity": [0.035, "雨幕：大雨能见度≈1 km → β≈0.004 m⁻¹（0.035×0.12）"],
            "RainX": [-10.7, "雨落在云塔下面"], "RainY": [-46.0, ""], "RainRadiusKm": [5.0, ""],
            "RainSlantKm": [2.5, "雨幕被低层风吹斜"], "RainStreakKm": [0.5, "雨幕里一条条的雨束"],
            "ShapeScaleKm": [3.0, ""], "DetailStrength": [0.45, ""],
            "PhaseG": [0.7, ""], "MSContribution": [0.6, ""], "MSOcclusion": [0.4, ""],
        }},
        "ppv": _ppv(auto_exposure_min_brightness=[10.0, "曝光按被晚霞照亮的云塔定，城市成剪影"],
                    auto_exposure_max_brightness=[10.0, ""]),
        "shots": [["CS_ART_Storm", None], ["CS_SkyCam", None]],
    },
    # 6 ------------------------------------------------------------------------------------------------------------
    "art_afterglow": {
        "title": "日落后 · 卷云余晖", "en": "Cirrus afterglow", "time": "日落后 15 分钟（太阳 −2.5°）",
        "sun": [-2.5, 275.0, "太阳落到地平线下 2.5°：镜头处的地影已升到 ≈6 km，低空和城市在暗蓝里；8.5–10 km 的卷云还被直射"
                             "（9 km 高的云在太阳落到 ≈−3° 前都照得到），光穿过几百公里低层大气，只剩橙红"],
        "set": dict(_fog_off(), **{
            "SkyAtmosphereComponent.mie_scattering_scale": [0.015, "干净的空气：余晖才够红"],
            "VolumetricCloudComponent.layer_bottom_altitude": [8.5, "卷云在 7–12 km 的冰晶层"],
            "VolumetricCloudComponent.layer_height": [1.5, ""],
            "VolumetricCloudComponent.tracing_max_distance": [120.0, "高云一直延伸到很远的地平线"],
            "VolumetricCloudComponent.use_per_sample_atmospheric_light_transmittance":
                [True, "每个样本自己判断是否已在地影里：靠近太阳的一侧亮得久"],
        }),
        "cloud": {"mi": "MI_CS_Art_Afterglow", "params": {
            "CoverageScale": [1.0, "大片的毛卷云"], "CoverageBias": [0.05, ""], "TypeMin": [0.6, ""], "TypeMax": [1.0, ""],
            "TopRamp": [0.6, ""], "BottomRamp": [0.3, "冰晶幡"],
            "StretchX": [5.0, "沿高空风拉长：纤维"], "StretchAngle": [255.0, "纤维指向晚霞方向"], "ShearKm": [4.0, "下落冰晶在风切变里拖出钩"],
            "ShapeScaleKm": [6.0, ""], "DetailScaleKm": [0.4, ""], "DetailStrength": [0.6, "丝缕状的边"], "DensityScale": [1.5, ""],
            "ExtinctionMax": [0.01, "比白天的卷云稍厚（光学厚度≈1–3），被染色的面积更大"],
            "PhaseG": [0.8, "冰晶强前向峰：靠近太阳一侧最亮"], "MSContribution": [0.5, ""],
        }},
        "ppv": _ppv(auto_exposure_min_brightness=[8.0, "曝光按余晖里的云定：天空深蓝、城市几乎全黑"],
                    auto_exposure_max_brightness=[8.0, ""],
                    color_saturation=[[1.2, 1.2, 1.2, 1.0], "艺术处理：余晖的颜色再饱和一点"]),
        "shots": [["CS_ART_Up", None], ["CS_SkyCam", None]],
    },
    # 7 ------------------------------------------------------------------------------------------------------------
    "art_streets": {
        "title": "上午 · 积云街", "en": "Cloud streets", "time": "上午（太阳 35°）",
        "sun": [35.0, 150.0, "上午的太阳在左后方：云的向阳面朝着镜头，阴影面在右"],
        "set": dict(_fog_off(), **{
            "SkyAtmosphereComponent.mie_scattering_scale": [0.025, "晴朗"],
            "VolumetricCloudComponent.layer_bottom_altitude": [1.1, "边界层顶的晴天积云，云底齐平"],
            "VolumetricCloudComponent.layer_height": [1.5, "淡积云到中积云，厚 0.5–1.5 km"],
            "VolumetricCloudComponent.tracing_max_distance": [80.0, "积云街一直排到地平线"],
        }),
        "cloud": {"mi": "MI_CS_Art_Streets", "params": {
            "RollAmt": [1.0, "水平对流卷：上升支上成云、下沉支上晴空，云排成平行的“街”"],
            "RollSpacingKm": [2.0, "街距≈边界层厚度的 2 倍左右（边界层顶≈云底 1.1 km）"],
            "RollAngle": [280.0, "沿平均风向（镜头正对的方向），透视汇聚到天边"],
            "WeatherScaleKm": [20.0, "天气图缩小：云更多、更密，连成一条条街"],
            "CoverageScale": [0.35, "天气图只轻微调制：云街本身连续"], "CoverageBias": [0.45, "上升支里一朵朵云接成串"],
            "TypeMin": [0.3, ""], "TypeMax": [0.5, "淡积云"],
            "TopRamp": [0.5, ""], "BottomRamp": [0.02, "平底"], "ShapeScaleKm": [0.8, "单朵云 1 km 左右"],
            "DetailStrength": [0.55, ""], "DensityScale": [2.0, ""], "ExtinctionMax": [0.1, ""],
            "BillowAmt": [0.6, "积云的花椰菜顶"], "BillowScaleKm": [0.8, ""],
            "MackerelAmt": [0.6, "云街由一朵朵分开的积云组成：用胞元场把连续的条带切成一朵朵"],
            "MackerelScaleKm": [1.1, "一朵积云≈1 km"], "MackerelGap": [0.35, ""], "MackerelStretch": [1.0, ""],
        }},
        "ppv": _ppv(auto_exposure_min_brightness=[14.0, "晴天上午"], auto_exposure_max_brightness=[14.0, ""]),
        "shots": [["CS_ART_Streets", None], ["CS_SkyCam", None]],
    },
    # 8 ------------------------------------------------------------------------------------------------------------
    "art_shelf": {
        "title": "午后 · 暴风雨前的弧状云", "en": "Shelf cloud before the storm", "time": "下午（太阳 16°，在镜头左后方）",
        "sun": [16.0, 150.0, "太阳在镜头左后方：城市还被照亮；雷暴的云砧已经伸到头顶，从下面看是它的背阴面——暗天亮城"],
        "set": {
            "SkyAtmosphereComponent.mie_scattering_scale": [0.06, "风暴前湿热的空气"],
            "ExponentialHeightFogComponent.fog_density": [0.003, "低空霭"],
            "ExponentialHeightFogComponent.second_fog_data": [{"fog_density": 0.0, "fog_height_falloff": 0.006,
                                                               "fog_height_offset": 0.0}, ""],
            "VolumetricCloudComponent.layer_bottom_altitude": [0.0, "层从地面开始，雨幕才有地方画"],
            "VolumetricCloudComponent.layer_height": [11.0, "母体雷暴到 ≈11 km"],
            "VolumetricCloudComponent.tracing_max_distance": [100.0, ""],
            "VolumetricCloudComponent.shadow_tracing_distance": [30.0, ""],
        },
        "cloud": {"mi": "MI_CS_Art_Shelf", "params": {
            "BaseKm": [1.0, "母体雷暴的云底"], "CoverageScale": [0.0, "其余天空没有零散的云"],
            "FrontAmt": [1.0, "阵风锋上的弧状云：雷暴下沉的冷空气向前铺开，把前面的暖湿空气抬升成一道云墙"],
            "FrontX": [0.57, "云墙前沿：镜头朝 280° 方向 5 km，城市后方 3.5 km"], "FrontY": [-3.42, ""],
            "FrontAngle": [100.0, "云墙朝镜头推进"], "FrontHalfLenKm": [40.0, "横贯整个视野"],
            "FrontBowKm": [6.0, "两端向后弯：弓形回波"], "FrontWobbleKm": [0.8, ""],
            "FrontDepthKm": [8.0, "楔形向后延伸到雨区"], "FrontBaseKm": [0.5, "云墙下沿 0.5 km，比母体云底低"],
            "FrontTopKm": [2.5, ""], "FrontSlopeKm": [2.5, "前沿随高度一级级后退：楔形"],
            "FrontTiers": [3.0, "三级台阶"], "FrontDensity": [2.0, ""],
            "CellX": [4.9, "母体雷暴：镜头前 30 km"], "CellY": [-28.0, ""], "CellRadiusKm": [10.0, ""],
            "CellStrength": [1.0, ""], "CellTopH": [0.95, ""], "CellTopRamp": [0.08, ""],
            "AnvilBottom": [0.55, "云砧 ≈6.5 km"], "AnvilRamp": [0.3, ""], "AnvilRadiusKm": [30.0, "云砧盖住整个天空，一直接到云墙后面"],
            "AnvilShiftKm": [14.0, "云砧伸到镜头上空：天空是云砧背阴的下表面"], "StretchAngle": [100.0, ""],
            "TurretAmt": [0.5, ""], "TurretScaleKm": [3.0, ""], "CellDensity": [3.0, ""], "CellSolid": [0.5, ""],
            "RainDensity": [0.06, "云墙后面的雨幕，黑蓝色"], "RainX": [1.96, "镜头前 13 km"], "RainY": [-11.3, ""],
            "RainRadiusKm": [6.0, ""], "RainSlantKm": [1.5, ""], "RainStreakKm": [0.6, ""],
            "StormAO": [0.06, "天光遮蔽：云砧和母体雷暴挡住了来自上方的天光，云砧下表面和云墙底部很暗——暗天"],
            "ShapeScaleKm": [3.0, ""], "DetailStrength": [0.4, ""],
            "PhaseG": [0.7, ""], "MSContribution": [0.6, ""], "MSOcclusion": [0.4, ""],
        }},
        "ppv": _ppv(auto_exposure_min_brightness=[13.3, "曝光按阳光下的城市和云墙定，天空自然压成深灰蓝"],
                    auto_exposure_max_brightness=[13.3, ""],
                    color_contrast=[[1.12, 1.12, 1.12, 1.0], "艺术处理：加对比"],
                    white_temp=[5600.0, "艺术处理：白点低于默认的 6500 K，画面略偏冷，风暴感（UE 的白点越低画面越蓝）"]),
        "shots": [["CS_ART_Wide", None], ["CS_SkyCam", None]],
    },
    # 9 ------------------------------------------------------------------------------------------------------------
    "art_lenticular": {
        "title": "日落 · 荚状云", "en": "Lenticular clouds at sunset", "time": "日落后片刻（太阳 −1°）",
        "sun": [-1.0, 29.0, "太阳在镜头背后、刚落到地平线下 1°：城市进入地影，4–6 km 的透镜状云还被照着，成粉红；"
                            "它们背后的天空低处是地影（蓝灰）和上面的维纳斯带（粉）"],
        "set": dict(_fog_off(), **{
            "SkyAtmosphereComponent.mie_scattering_scale": [0.015, "山区空气干净"],
            "VolumetricCloudComponent.layer_bottom_altitude": [2.5, ""],
            "VolumetricCloudComponent.layer_height": [4.0, "荚状云 3–7 km"],
            "VolumetricCloudComponent.tracing_max_distance": [80.0, ""],
            "VolumetricCloudComponent.use_per_sample_atmospheric_light_transmittance": [True, ""],
        }),
        "cloud": {"mi": "MI_CS_Art_Lenticular", "params": {
            "CoverageScale": [0.0, "没有别的云"],
            "LensAmt": [1.0, "荚状云：气流越过山脊后形成驻波，在波峰处冷却成云、波谷处蒸发——云停在原地不动"],
            "LensScaleKm": [40.0, "天气图上的细胞给出一片片透镜的位置和大小"],
            "LensCut": [0.5, "只取细胞的核心：一片片分开的透镜，而不是连成一片"],
            "LensElong": [2.5, "沿山脊方向拉长"], "StretchAngle": [119.0, "山脊走向（垂直于镜头方向）"],
            "LensBaseKm": [1.5, "最下面一片在 4 km"], "LensPlates": [3.0, "叠成三层：多层的驻波，像一摞盘子"],
            "LensSpacingKm": [0.35, ""], "LensThickKm": [0.25, ""], "LensShrink": [0.25, "越往上越小"],
            "LensJitterKm": [0.15, "层流：高度几乎不起伏"], "LensDensity": [1.0, ""],
            "CellX": [-17.4, "只在镜头前 25 km 一带、远山上空出现：驻波在山脊的下风方向"],
            "CellY": [-9.6, ""], "CellRadiusKm": [9.0, "只留几片"],
            "CellStrength": [1.0, ""],
            "DetailStrength": [0.0, "层流：表面光滑，几乎没有絮状细节"],
            "ExtinctionMax": [0.05, ""], "PhaseG": [0.7, ""], "MSContribution": [0.6, ""],
        }},
        "ppv": _ppv(auto_exposure_min_brightness=[9.0, "日落后：曝光按被照亮的云定"], auto_exposure_max_brightness=[9.0, ""]),
        "shots": [["CS_ART_Lens", None], ["CS_SkyCam", None]],
    },
    # 10 -----------------------------------------------------------------------------------------------------------
    "art_moonlit": {
        "title": "深夜 · 月光积云", "en": "Moonlit cumulus", "time": "深夜（满月高 35°）",
        "sun": [35.0, 272.0, "这盏平行光现在是月亮：高 35°，在画面左上，云边被它照出银边"],
        "set": dict(_fog_off(), **{
            "DirectionalLightComponent.intensity": [0.25, "满月照度 ≈0.25 lux（比白天暗约 18 档）"],
            "DirectionalLightComponent.temperature": [4100.0, "月光是被月壤反射的阳光，略偏红：≈4100 K"],
            "SkyAtmosphereComponent.mie_scattering_scale": [0.012, "干净的夜空"],
            "VolumetricCloudComponent.layer_bottom_altitude": [1.4, ""],
            "VolumetricCloudComponent.layer_height": [3.0, ""],
        }),
        "cloud": {"mi": "MI_CS_Art_Moonlit", "params": {
            "CoverageScale": [0.85, "稀疏的积云，云缝里看得到星星"], "BillowAmt": [0.4, ""], "BillowScaleKm": [1.2, ""],
            "DensityScale": [2.5, ""], "PhaseG": [0.75, "月亮附近的云边有银边"],
        }},
        "night_sky": {"StarIntensity": [2.0, "星空：复用 SeasonalWeather 的星图（天空材质会接管大气和月盘）"],
                      "StarSharp": [4.0, "星图每个像素的值取 4 次方：星星成为点而不是双线性插值的方块，暗淡的背景消失"]},
        "ppv": _ppv(auto_exposure_min_brightness=[-2.7, "夜景曝光：同样的照度比白天（13.4）暗 18.9 档，按白天的曝光应是 −5.5；"
                                                        "再暗近 3 档，画面才像夜里"],
                    auto_exposure_max_brightness=[-2.7, ""],
                    white_temp=[3300.0, "艺术处理：把白点放低让画面偏冷蓝——人眼在暗处的视觉偏蓝（浦肯野效应）"]),
        "shots": [["CS_ART_Moon", None], ["CS_SkyCam", None]],
    },
}

ART_ORDER = ["art_mackerel", "art_cloudsea", "art_towers", "art_rays", "art_storm", "art_afterglow", "art_streets",
             "art_shelf", "art_lenticular", "art_moonlit"]

# --- motion (2026-11-12, docs/superpowers/specs/2026-11-12-cs-cloud-motion-design.md §3.4) ----------------------------
# How each weather's clouds change with time while the cloud director plays it (cs_cloud_director.py). Every value is
# [value, why]; "mods" is a list of [modulator, why]. Keys: cs_cloud_motion.MOTION_KEYS. Wind: speed in m/s and the
# compass heading the air moves TOWARD (north = +X, east = +Y). Lifetimes and periods in simulated minutes.
MOTION = {
    "art_mackerel": {
        "wind_ms": [15.0, "中层（3.5–4.5 km）常见风速 10–20 m/s"],
        "wind_deg": [300.0, "风横穿鱼鳞行（行沿 30°）：开尔文-亥姆霍兹波的波峰垂直于风切变，一排排云块朝画面深处移动"],
        "evo_amt": [0.35, "高积云的单元寿命短：一块块地生成、消散"],
        "evo_life_min": [12.0, "单个高积云单元约 10–15 分钟"],
        "mackerel_life_min": [12.0, "鱼鳞胞随之原地变形：合并、分裂"],
        "clip_speed": [60.0, "60 倍：10 秒片段是 10 分钟，约一个单元的寿命"],
    },
    "art_cloudsea": {
        "wind_ms": [2.0, "辐射雾里几乎无风，日出后只有 1–3 m/s 的弱流"],
        "wind_deg": [200.0, "弱的漂移方向（示意）"],
        "evo_amt": [0.1, "雾顶的覆盖几乎不变，只在边缘处起落"],
        "evo_life_min": [15.0, "雾顶起伏的时间尺度"],
        "boil_billow_ms": [0.5, "雾顶的辐射冷却驱动弱对流：顶面的鼓包缓慢翻动"],
        "mods": [[{"param": "TypeMax", "osc": [0.05, 20.0, 0.0]},
                  "雾顶整体随重力波缓慢起伏约 20 m（层高 400 m 的 5%），周期约 20 分钟"]],
        "clip_speed": [60.0, "60 倍：10 秒片段是 10 分钟"],
    },
    "art_towers": {
        "wind_ms": [6.0, "边界层的引导气流 5–8 m/s：积云整体漂移"],
        "wind_deg": [250.0, "漂移方向（示意）"],
        "evo_amt": [0.6, "一座座云塔各自长高、衰减：浓积云的生命周期"],
        "evo_life_min": [30.0, "浓积云寿命 20–40 分钟"],
        "boil_billow_ms": [3.0, "对流泡（热泡）以 2–5 m/s 上升：花椰菜顶在翻滚"],
        "boil_shape_ms": [1.0, "云体整体缓慢抬升"],
        "boil_detail_ms": [2.0, "细节随上升气流向上流动"],
        "clip_speed": [120.0, "120 倍：10 秒片段是 20 分钟，看得出云塔长高"],
    },
    "art_rays": {
        "wind_ms": [8.0, "层积云随低层风 5–10 m/s 移动"],
        "wind_deg": [300.0, "云层朝太阳那边漂：云缝从太阳前扫过，光束一束束地变化"],
        "evo_amt": [0.4, "云缝开合"],
        "evo_life_min": [25.0, "层积云块的寿命"],
        "clip_speed": [60.0, "60 倍：10 秒片段是 10 分钟"],
    },
    "art_storm": {
        "wind_ms": [5.0, "低层风：周围的淡积云和雨幕里的雨束随之漂移；单体本身保持在构图位置（真实雷暴约以 10 m/s 移动）"],
        "wind_deg": [200.0, "低层风的指向（示意）"],
        "evo_amt": [0.5, "周围的淡积云生成、消散"],
        "evo_life_min": [20.0, "淡积云寿命"],
        "boil_turret_ms": [6.0, "主塔外沿的对流泡以 5–10 m/s 上升"],
        "rain_fall_ms": [8.0, "雨滴末速度 5–9 m/s：雨束往下落"],
        "mamma_life_min": [10.0, "乳状云的囊约 10 分钟鼓出、消失"],
        "lump_life_min": [15.0, "主塔轮廓随对流泡更替而变化"],
        "mods": [[{"param": "OvershootKm", "osc": [0.4, 8.0, 0.0]}, "上冲云顶随最强上升气流的脉动起伏，周期 5–10 分钟"],
                 [{"param": "AnvilShiftKm", "osc": [1.5, 20.0, 0.0]}, "云砧随高空风伸缩"]],
        "form_window": [[0.0, 1.0], "积雨云从淡积云长到成熟，生成要占满整段过渡"],
        "clip_speed": [60.0, "60 倍：10 秒片段是 10 分钟，看得到一次上冲云顶的起伏"],
    },
    "art_afterglow": {
        "wind_ms": [40.0, "高空急流 30–60 m/s：卷云走得最快"],
        "wind_deg": [255.0, "顺着纤维（StretchAngle 255°）：毛卷云沿风拉长"],
        "evo_amt": [0.3, "纤维缓慢变化"],
        "evo_life_min": [30.0, "卷云纤维的寿命"],
        "mods": [[{"param": "ShearKm", "osc": [0.8, 15.0, 0.0]}, "冰晶幡的钩随风切变强弱摆动"]],
        "clip_speed": [30.0, "30 倍已经很快：40 m/s × 30 = 1.2 km/s"],
    },
    "art_streets": {
        "wind_ms": [8.0, "边界层平均风 5–10 m/s，云沿街移动"],
        "wind_deg": [280.0, "顺着云街（RollAngle 280°）：对流卷沿平均风排列，所以街本身不横移"],
        "evo_amt": [0.5, "云在上风端生成、下风端消散"],
        "evo_life_min": [15.0, "淡积云寿命 10–20 分钟"],
        "mackerel_life_min": [15.0, "街上一朵朵积云各自变形"],
        "boil_billow_ms": [1.5, "积云顶的对流泡上升"],
        "clip_speed": [60.0, "60 倍：10 秒片段是 10 分钟"],
    },
    "art_shelf": {
        "wind_ms": [6.0, "锋前的暖湿空气流向阵风锋（入流）"],
        "wind_deg": [280.0, "入流的指向：从镜头背后流向云墙"],
        "evo_amt": [0.0, "云墙由阵风锋决定，不做原地生灭"],
        "boil_detail_ms": [3.0, "锋前的低云碎片被抬进云墙"],
        "mods": [[{"params": ["FrontX", "FrontY", "RainX", "RainY"], "approach": [2.5, 12.0, 100.0]},
                  "阵风锋以 10–15 m/s 朝镜头推进，后面的雨幕跟着走；推进 2.5 km 后停住（锋面停滞），长时间播放也不会穿过城市"]],
        "clip_speed": [30.0, "30 倍：10 秒片段是 5 分钟，锋面推进约 2 km"],
    },
    "art_lenticular": {
        "wind_ms": [25.0, "越山气流 20–40 m/s：风从云里穿过"],
        "wind_deg": [209.0, "横穿山脊（山脊沿 119°）"],
        "evo_amt": [0.0, "透镜由驻波决定，不做原地生灭"],
        "mods": [[{"param": "LensCut", "osc": [0.03, 12.0, 0.0]}, "驻波的振幅随来流强弱变化：透镜缓慢胀缩"]],
        "clip_speed": [60.0, "60 倍：10 秒片段是 10 分钟；透镜不动，透镜的高度抖动随风流过"],
    },
    "art_moonlit": {
        "wind_ms": [5.0, "夜间低层风较弱"],
        "wind_deg": [250.0, "漂移方向（示意）"],
        "evo_amt": [0.5, "夜里积云逐渐消散、偶尔再生"],
        "evo_life_min": [20.0, "淡积云寿命"],
        "boil_billow_ms": [1.0, "残余的对流泡缓慢上升"],
        "clip_speed": [60.0, "60 倍：10 秒片段是 10 分钟"],
    },
}
for _name, _mo in MOTION.items():
    ART[_name]["motion"] = _mo

# the five transition clips of spec §6.3 (cs_cloud_motion.clip_list reads them through cs_weather_presets)
TRANSITION_CLIPS = [
    {"clip": "trans_towers_storm", "from": "art_towers", "to": "art_storm", "light": "full",
     "cams": ["CS_ART_TowersHi", "CS_ART_Storm"],
     "why": "积云长成积雨云：主塔一路长高，到对流层顶后云砧铺开，上冲云顶、乳状云和雨最后出现；太阳同时从午后落到地平线下"},
    {"clip": "trans_mackerel_cloudsea", "from": "art_mackerel", "to": "art_cloudsea", "light": "full",
     "cams": ["CS_ART_WideHi", "CS_ART_Sea"],
     "why": "中层的高积云从边缘蒸发散去，贴地的雾海从下面长起来（云层临时扩成 0–4.5 km）；太阳从地平线下升到 4°"},
    {"clip": "trans_streets_afterglow", "from": "art_streets", "to": "art_afterglow", "light": "full",
     "cams": ["CS_ART_Streets", "CS_ART_Up"],
     "why": "低空的积云街散去，8.5 km 以上的卷云出现（云层临时扩成 1.1–10 km）；上午到日落后的余晖"},
    {"clip": "trans_rays_moonlit", "from": "art_rays", "to": "art_moonlit", "light": "full",
     "cams": ["CS_ART_Rays", "CS_ART_Moon"],
     "why": "傍晚到深夜：光强降 19 档，曝光跟着降；光照暗到 10 lux 以下时星空球出现，星星逐渐亮起"},
    {"clip": "trans_lenticular_shelf", "from": "art_lenticular", "to": "art_shelf", "light": "clouds",
     "cams": ["CS_ART_Lens", "CS_ART_WideHi"],
     "why": "只换云：驻波透镜收缩消失，阵风锋从上风方向推进过来；光照保持荚状云的日落不变"},
]
