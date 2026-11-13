# build_menu.py -- the weather "menu" shown to the user before any scene work: candidate weathers, two reference
# photos each (Wikimedia Commons, with author / licence / link and the EXIF-derived sun position and EV100), the
# physics in a few lines, the parameters it maps to, and the effort. Self-contained HTML (thumbnails inlined).
#
#   C:\Python314\python.exe -P -E Tools/cs_weather/build_menu.py
#       -> Saved/Reports/cs_weather2/menu/weather_menu.html, picks.json, menu_sheet.jpg
import base64
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import solar  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REFS = os.path.join(ROOT, "Saved", "Reports", "cs_weather2", "refs")
OUT = os.path.join(ROOT, "Saved", "Reports", "cs_weather2", "menu")

# (cand key, index, place shown, (lat, lon, utc offset) or None, note)
MENU = [
    {
        "id": "clear_noon", "title": "夏日正午 · 晴空", "en": "Clear summer noon", "stars": 1, "rec": True,
        "time": "当地 12:00–13:30，太阳高度 ≈ 60°", "genus": "晴空 / 少量淡积云 Cu humilis",
        "refs": [("noon_aerial", 8, "芝加哥 Willis Tower 观景台", (41.879, -87.636, -5), ""),
                 ("clear_noon", 3, "芝加哥 湖滨", (41.88, -87.62, -5), "")],
        "physics": [
            "瑞利散射 σ∝λ⁻⁴：450 nm 蓝光的散射是 650 nm 红光的 ≈4.4 倍，天空呈蓝色；天顶最蓝，地平线因多次散射与气溶胶发白。",
            "太阳高 → 大气质量 m≈1.15（Kasten-Young），直射光几乎不被染色（≈5500 K），阴影最短、反差最大。",
            "地面照度 ~100 klux（直射）+ ~15 klux（天光）；摄影 Sunny-16 规则 → EV100 ≈ 15。",
        ],
        "params": ["DirectionalLight：高度 60°、120 klux（大气顶）、5800 K", "SkyAtmosphere：Mie 回到洁净值 0.004 km⁻¹",
                   "云：稀疏小积云（覆盖率↓、厚度↓）", "PPV：固定曝光 EV100 ≈ 14.5–15"],
        "risk": "最容易：在已完成的 10 点晴天上改太阳和云量即可。",
    },
    {
        "id": "golden_hour", "title": "黄金时刻 · 低太阳暖光", "en": "Golden hour", "stars": 2, "rec": True,
        "time": "日出后 / 日落前 30–60 分钟，太阳高度 3–8°", "genus": "晴空，可带一层碎高积云 Ac（底面被染红）",
        "refs": [("golden_hour", 15, "纽约 Lower Manhattan 日出（逆光）", (40.716, -74.035, -4), "HDR 合成，曝光只作参考"),
                 ("golden_hour", 11, "纽约 日出火烧云（带 GPS）", (40.6913, -74.0303, -4), "太阳刚在地平线：云底被红光从下方照亮")],
        "physics": [
            "太阳 5° 时大气质量 m≈10（是正午的 9 倍）；瑞利光学厚度 τ(450nm)≈0.22、τ(650nm)≈0.05 → 蓝光透过 ≈10%、红光 ≈60% → 阳光变成 ≈3000 K 的橙黄。",
            "受光面暖、阴影被蓝色天光填充 → 典型的冷暖对比；影子拉长到建筑高度的 10 倍以上。",
            "低云/中云底面被已染红的阳光从下方照亮 → 火烧云；太阳周围的气溶胶前向散射形成暖色光晕。",
        ],
        "params": ["DirectionalLight：高度 5°，颜色保持 5800 K（染色交给大气透射率，不手调橙色）",
                   "SkyAtmosphere：Mie 0.006–0.01 km⁻¹（适量气溶胶）", "云：3–5 km 薄层碎高积云（新 MI）",
                   "PPV：EV100 ≈ 12–14，白平衡保持日光"],
        "risk": "低太阳下云阴影图的近平面要放远（已知陷阱，LightDistanceOverride）。",
    },
    {
        "id": "blue_hour", "title": "蓝调时刻 · 民用曙暮光", "en": "Blue hour", "stars": 2, "rec": True,
        "time": "日落后 20–40 分钟，太阳高度 −4° ~ −7°", "genus": "晴空；反日方向出现地影与维纳斯带",
        "refs": [("blue_hour", 1, "芝加哥 North Avenue Beach", (41.915, -87.625, -5), ""),
                 ("blue_hour", 22, "瑞典 Brastad 维纳斯带", (58.385, 11.478, 1), "地影（深蓝带）+ 其上的粉色反曙暮光弧")],
        "physics": [
            "地面已无直射光，天空只剩照亮高层大气的单次散射；照度 ≈1–10 lux → EV100 ≈ 3–6。",
            "光线沿切线穿过臭氧层，臭氧 Chappuis 带（500–700 nm）吸收橙红 → 天顶保持深蓝（Hulburt 1953：没有臭氧，暮光天顶会偏灰黄）。",
            "反日方向：地球自身的影子投在大气上（地影），其上方被红色余晖照亮的粉色带即维纳斯带。",
        ],
        "params": ["DirectionalLight：高度 −5°（光仍照亮高层大气）", "SkyAtmosphere：臭氧层 OtherAbsorption（25 km 帐篷分布）、多次散射 1.0",
                   "SkyLight：实时捕获；PPV：EV100 ≈ 4–5"],
        "risk": "City Sample 楼宇没有可整体打开的夜间窗灯/路灯：城市会是暗剪影，照片里的灯光无法复现（天空可以）。",
    },
    {
        "id": "overcast", "title": "全阴天 · 层积云", "en": "Overcast (stratocumulus)", "stars": 2, "rec": True,
        "time": "任意白天（参考：下午 17:30，太阳 ≈ 19°）", "genus": "层积云 Sc / 层云 St，8/8 覆盖",
        "refs": [("overcast", 23, "波士顿 天际线", (42.36, -71.05, -4), "CC0"),
                 ("overcast", 24, "圣地亚哥 六月阴霾（海洋性层云）", (32.70, -117.17, -7), "")],
        "physics": [
            "云底 0.5–1.5 km、厚 0.5–1 km；液水 0.2–0.4 g/m³、有效半径 ~8 µm → 消光 β=3·LWC/(2ρ_w·r_e) ≈ 0.04–0.08 m⁻¹，光学厚度 τ≈20–60。",
            "双流近似漫透射 T≈1/(1+0.75(1−g)τ) ≈ 13–30% → 地面照度约为晴天的 1/5，没有投影，色彩饱和度低，色温 ≈6500 K。",
            "CIE 标准阴天天空：L(θ)=L_z·(1+2 sinθ)/3，地平线亮度只有天顶的 1/3。",
        ],
        "params": ["VolumetricCloud：云底 0.8 km、厚 1–1.5 km、覆盖率 1、层状（平顶）", "云材质：消光 0.04–0.08 m⁻¹、多次散射 octave 调云底亮度",
                   "SkyLight：云 AO；PPV：EV100 ≈ 11"],
        "risk": "需要层状云的新 MI；云底亮度靠多次散射近似，要和照片的明暗比对齐。",
    },
    {
        "id": "fog", "title": "雾 · 塔楼浮于雾上", "en": "Fog (towers above the mist)", "stars": 2, "rec": True,
        "time": "参考 A：下午 14:35（太阳 41°，湖雾）；参考 B：日出 08:00（太阳 8°）", "genus": "平流雾 / 辐射雾，雾顶受逆温层限制",
        "refs": [("fog", 6, "芝加哥 Willis Tower 顶部探出雾层", (41.866, -87.607, -5), ""),
                 ("fog", 18, "纽约 Lower Manhattan 晨雾", (40.716, -74.035, -5), "")],
        "physics": [
            "雾滴 5–20 µm（远大于可见光波长）→ 米氏散射几乎与波长无关，所以雾是白/灰色；前向散射强，g≈0.85。",
            "能见度 V=3.912/β（Koschmieder，2% 对比阈值）：雾 V<1 km ⇔ β>3.9×10⁻³ m⁻¹；V=300 m ⇔ β≈0.013 m⁻¹。",
            "雾层顶在逆温层（常 100–300 m），高楼顶部探出雾海；太阳在雾里成白色圆盘。",
        ],
        "params": ["ExponentialHeightFog：FogDensity≈0.2（UE 存 FogDensity/1000 每厘米、以 2 为底 → V≈56.4/FogDensity 米）",
                   "HeightFalloff 0.1–0.3（密度每 30–100 m 减半）+ 第二层薄霭", "体积雾：g=0.85、反照率 1",
                   "PPV：EV100 ≈ 13–15"],
        "risk": "指数分布没有真实雾那样锐利的雾顶：用两层雾（或局部雾体积）逼近。",
    },
    {
        "id": "haze", "title": "城市雾霾", "en": "Urban haze / smog", "stars": 1, "rec": True,
        "time": "参考：下午 14:30，太阳 ≈ 50°", "genus": "气溶胶污染（PM2.5），能见度 2–5 km",
        "refs": [("haze", 26, "洛杉矶 市中心（Hollywood 101）", (34.11, -118.34, -7), ""),
                 ("haze", 20, "北京 重度雾霾", None, "EXIF 时钟不可信")],
        "physics": [
            "细颗粒物 0.1–1 µm → 米氏散射，Ångström 指数 α≈1–1.5（散射∝λ^−α，波长依赖远弱于瑞利的 λ⁻⁴）→ 远景发白发灰。",
            "黑碳/棕碳和 NO₂ 吸收蓝光 → 透过的阳光与远景偏黄褐；单次散射反照率 ω≈0.8–0.9。",
            "能见度 3 km ⇔ 近地面消光 β≈1.3 km⁻¹（洁净空气 ≈0.01–0.05 km⁻¹）；边界层（1–2 km）以上空气变清。",
        ],
        "params": ["SkyAtmosphere：MieScattering 0.004 → ~0.8 km⁻¹、MieAbsorption 0.0004 → ~0.15 km⁻¹（偏蓝吸收）",
                   "MieExponentialDistribution 1.2 → 1.0 km、MieAnisotropy 0.7", "ExponentialHeightFog：补足地面浓度、黄灰色",
                   "PPV：EV100 ≈ 13"],
        "risk": "主要是 SkyAtmosphere 参数，风险低。",
    },
    {
        "id": "dust", "title": "沙尘暴 · 红色黎明", "en": "Dust storm", "stars": 2, "rec": False,
        "time": "参考：2009-09-23 澳大利亚东海岸，上午", "genus": "矿物尘，AOD 3–10，能见度 <1 km",
        "refs": [("dust", 18, "黄金海岸 高楼群", (-28.0, 153.43, 10), "公有领域"),
                 ("dust", 13, "悉尼 港湾大桥", (-33.85, 151.21, 10), "")],
        "physics": [
            "矿物尘 1–10 µm → 散射几乎与波长无关（α≈0–0.3），但含铁矿物（赤铁矿）强烈吸收蓝紫光：ω≈0.75@450 nm、≈0.95@650 nm → 天空与阳光都呈橙红。",
            "光学厚度极大，太阳被完全遮蔽，场景光几乎全是漫射；能见度常 <1 km。",
        ],
        "params": ["SkyAtmosphere：Mie 散射 ≈3 km⁻¹、Mie 吸收色偏蓝、高度分布 1.5–2 km",
                   "HeightFog / 体积雾：反照率由 ω(λ) 推出的橙色", "PPV：EV100 ≈ 8–12"],
        "risk": "和雾霾同一套旋钮，换光谱；可作为雾霾的延伸。",
    },
    {
        "id": "storm", "title": "远方雷暴 · 积雨云砧", "en": "Distant thunderstorm (Cb incus)", "stars": 3, "rec": False,
        "time": "参考：午后 14:07，太阳 ≈ 58°", "genus": "积雨云 Cb incus（砧状云顶）",
        "refs": [("storm", 11, "克拉科夫 积雨云砧", (50.06, 19.94, 2), ""),
                 ("storm", 22, "城市上空的雷暴云", None, "")],
        "physics": [
            "云底 1–1.5 km，云顶冲到对流层顶 10–13 km 后水平铺展成砧；含水量 1–3 g/m³ → β≈0.1–0.3 m⁻¹，τ>500。",
            "背光面与云底几乎全黑，迎光云塔边缘因前向/多次散射发亮；前景仍有阳光 → '暗天亮城'。",
        ],
        "params": ["云材质需扩展：天气图上放一个风暴单体（位置/半径）+ 砧状顶部剖面", "云层高 12 km（步数/距离↑，GPU 开销大）"],
        "risk": "需要新的云材质变体，工作量最大。",
    },
    {
        "id": "cirrus", "title": "卷云晴空 · 马尾云", "en": "Cirrus (mares' tails)", "stars": 3, "rec": False,
        "time": "参考：上午 09:25，太阳 ≈ 30°", "genus": "卷云 Ci fibratus / uncinus，7–12 km 冰晶云",
        "refs": [("cirrus", 4, "西班牙 Bardenas", (42.21, -1.516, 2), ""),
                 ("cirrus", 16, "美国 新泽西", (40.285, -74.841, -4), "")],
        "physics": [
            "冰晶 20–1000 µm，光学厚度 0.03–3（半透明）；下落冰晶被风切变拉成钩状纤维。",
            "冰晶相函数有强前向峰与 22° 晕；UE 云材质只有双瓣 HG，晕做不出来。",
        ],
        "params": ["云材质需扩展：8–10 km 薄层 + 沿风向拉伸的各向异性噪声", "UE 只渲染一个体积云组件：卷云与积云要放进同一材质分高度"],
        "risk": "需要新的云材质变体。",
    },
]


def _load(key):
    with open(os.path.join(REFS, "cand", key + ".json"), encoding="utf-8") as f:
        return json.load(f)


def _b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _sun(c, place):
    import datetime as dt
    if not place or not c.get("date"):
        return None
    try:
        t = dt.datetime.strptime(c["date"][:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    lat, lon, tz = place
    elev, az, _, _ = solar.sun_position(t, tz, lat, lon)
    return round(elev, 1), round(az, 1)


def main():
    os.makedirs(OUT, exist_ok=True)
    cache, picks = {}, {}
    cards = []
    for w in MENU:
        figs = []
        for key, idx, where, place, note in w["refs"]:
            if key not in cache:
                cache[key] = _load(key)
            c = cache[key][idx]
            sun = _sun(c, place)
            thumb = os.path.join(REFS, "cand", key, "%02d.jpg" % idx)
            exif = []
            if c.get("date"):
                exif.append(c["date"][:16].replace(":", "-", 2))
            if c.get("fnumber") and c.get("exposure") and c.get("iso"):
                t = c["exposure"]
                ts = ("1/%d s" % round(1 / t)) if t < 1 else ("%g s" % t)
                exif.append("f/%g · %s · ISO %d → EV100 %.1f" % (c["fnumber"], ts, c["iso"], c["ev100"]))
            if sun:
                exif.append("太阳高度 %.1f° 方位 %.0f°" % sun)
            picks.setdefault(w["id"], []).append(dict(c, where=where, place=place, note=note, sun=sun, cand=[key, idx]))
            figs.append(
                '<figure><a href="%s"><img src="data:image/jpeg;base64,%s"></a><figcaption><b>%s</b><br>%s<br>'
                '<span class="lic">%s · %s</span>%s</figcaption></figure>'
                % (html.escape(c["page"] or ""), _b64(thumb), html.escape(where), html.escape(" | ".join(exif)),
                   html.escape(c["artist"][:60]), html.escape(c["license"]),
                   ("<br><i>%s</i>" % html.escape(note)) if note else ""))
        cards.append(
            '<section class="card%s"><h2>%s <small>%s</small> <span class="stars">%s</span>%s</h2>'
            '<p class="meta">%s　·　%s</p><div class="figs">%s</div>'
            '<div class="cols"><div><h3>现实物理</h3><ul>%s</ul></div><div><h3>主要组件与参数</h3><ul>%s</ul>'
            '<p class="risk">%s</p></div></div></section>'
            % (" rec" if w["rec"] else "", html.escape(w["title"]), html.escape(w["en"]),
               "★" * w["stars"] + "☆" * (3 - w["stars"]), ' <span class="tag">推荐</span>' if w["rec"] else "",
               html.escape(w["time"]), html.escape(w["genus"]), "".join(figs),
               "".join("<li>%s</li>" % html.escape(p) for p in w["physics"]),
               "".join("<li>%s</li>" % html.escape(p) for p in w["params"]), html.escape(w["risk"])))
    page = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>City Sample 静态天气菜单</title>
<style>
body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;margin:24px auto;max-width:1180px;color:#1d2433;background:#f6f7f9;line-height:1.55}
h1{font-size:24px;margin:0 0 4px} .lead{color:#556;margin:0 0 18px}
.card{background:#fff;border:1px solid #dde2ea;border-radius:10px;padding:14px 18px;margin:0 0 16px}
.card.rec{border-left:5px solid #2b6cb0}
h2{font-size:19px;margin:0} h2 small{font-weight:normal;color:#667;font-size:14px}
.stars{color:#b86e00;font-size:15px;margin-left:6px} .tag{background:#2b6cb0;color:#fff;border-radius:4px;font-size:12px;padding:1px 7px;margin-left:6px;vertical-align:2px}
.meta{color:#445;margin:4px 0 10px;font-size:14px}
.figs{display:flex;gap:12px} figure{margin:0;flex:1} figure img{width:100%;height:250px;object-fit:cover;border-radius:6px}
figcaption{font-size:12.5px;color:#334;margin-top:4px} .lic{color:#778}
.cols{display:flex;gap:22px;margin-top:8px} .cols>div{flex:1} h3{font-size:14.5px;margin:6px 0 2px;color:#2b6cb0}
ul{margin:0;padding-left:18px;font-size:13.5px} .risk{font-size:13px;color:#8a5a00;background:#fff7e6;border-radius:5px;padding:5px 8px;margin:8px 0 0}
.base{background:#eef4fb;border-radius:8px;padding:8px 14px;font-size:14px;margin-bottom:16px}
</style></head><body>
<h1>City Sample 演示关卡 · 静态天气候选</h1>
<p class="lead">每种天气两张真实照片（Wikimedia Commons，点击图片看原图、作者与许可）。太阳高度/方位由 EXIF 时间 + 拍摄地点按 NOAA 太阳位置算法算出，
EV100 = log₂(N²/t) − log₂(ISO/100)。★ 为工作量（★ 只调参，★★ 要新的云材质实例或机位，★★★ 要扩展云材质本身）。蓝框为推荐的第一批。</p>
<div class="base"><b>已完成的基线：</b>上午 10:00 晴天积云（太阳 31°，120 klux，EV100 13.4，自制积云材质 + 两层薄雾 + 云阴影）。所有新天气都在它之上做参数增量，关卡本身不保存。</div>
{{CARDS}}
<p class="lead">本轮不建议：满月夜、阴雨湿街（需要城市灯光或湿润材质，City Sample 内容里没有全局开关；降雨/降雪粒子与风按你的要求先不做）。</p>
</body></html>""".replace("{{CARDS}}", "\n".join(cards))
    with open(os.path.join(OUT, "weather_menu.html"), "w", encoding="utf-8") as f:
        f.write(page)
    with open(os.path.join(OUT, "picks.json"), "w", encoding="utf-8") as f:
        json.dump(picks, f, indent=1, ensure_ascii=False)
    # contact sheet of the picks, for a quick look
    from PIL import Image
    tiles = []
    for w in MENU:
        for key, idx, *_ in w["refs"]:
            im = Image.open(os.path.join(REFS, "cand", key, "%02d.jpg" % idx)).convert("RGB")
            im.thumbnail((480, 300))
            tiles.append(im)
    cols, cw, ch = 4, 480, 300
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * ch), (20, 20, 20))
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % cols) * cw, (i // cols) * ch))
    sheet.save(os.path.join(OUT, "menu_sheet.jpg"), quality=85)
    print("menu:", os.path.join(OUT, "weather_menu.html"), "cards", len(cards))


if __name__ == "__main__":
    main()
