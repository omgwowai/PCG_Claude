# build_report.py -- docs/citysample-weather-presets.html: the weather presets of the City Sample demo level as a
# teaching report. One source for the data (Content/Python/cs_weather_presets.py) and the prose (report_text.py);
# the photos are the Wikimedia Commons picks of Saved/Reports/cs_weather2/refs, the renders the final shots.
#
#   C:\Python314\python.exe -P -E Tools/cs_weather/build_report.py
#       -> docs/citysample-weather-presets.html (self-contained: every image is inlined as JPEG)
import base64
import html
import io
import json
import math
import os
import sys

from PIL import Image, ImageStat

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "Content", "Python"))
sys.path.insert(0, os.path.dirname(__file__))
import cs_weather_presets as P  # noqa: E402
import report_text as T  # noqa: E402
import solar  # noqa: E402

REPORTS = os.path.join(ROOT, "Saved", "Reports", "cs_weather2")
REFS = os.path.join(REPORTS, "refs", "full")
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "WindowsEditor")
COMPARE = os.path.join(REPORTS, "compare")
OUT = os.path.join(ROOT, "docs", "citysample-weather-presets.html")
PICKS = json.load(open(os.path.join(REPORTS, "menu", "picks.json"), encoding="utf-8"))
TAG = "final"


def img(path, max_w, quality=82, crop=None):
    """Inlines an image as a JPEG data URI, scaled down to max_w (crop = (l, t, r, b) in fractions)."""
    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop((round(crop[0] * im.width), round(crop[1] * im.height),
                      round(crop[2] * im.width), round(crop[3] * im.height)))
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii"), im


def short(label):
    return "hero" if label == "CS_SkyCam" else label.replace("CS_WX_", "").lower()


def means(im):
    top = ImageStat.Stat(im.crop((0, 0, im.width, im.height // 2))).mean
    bot = ImageStat.Stat(im.crop((0, im.height // 2, im.width, im.height))).mean
    return [round(x) for x in top], [round(x) for x in bot]


def esc(s):
    return html.escape(str(s))


def fmt(v):
    if isinstance(v, bool):
        return "开" if v else "关"
    if isinstance(v, float):
        return ("%.4f" % v).rstrip("0").rstrip(".")
    if isinstance(v, dict):
        return "{" + "、".join("%s=%s" % (k, fmt(x)) for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(fmt(x) for x in v) + "]"
    return str(v)


def entry(e):
    """A preset entry is [value, why] or [value, unit, why]."""
    if isinstance(e, list) and len(e) == 3 and isinstance(e[1], str) and not isinstance(e[0], str):
        return e[0], e[1], e[2]
    if isinstance(e, list) and len(e) == 2:
        return e[0], None, e[1]
    return e, None, ""


def effective(name, section, key):
    """(value, unit, why, source) of a managed property for one preset."""
    p = {} if name == "base" else P.PRESETS[name]
    if section == "cloud":
        if key in p.get("cloud", {}).get("params", {}):
            v, u, w = entry(p["cloud"]["params"][key])
            return v, u, w, "预设"
        return P.BASE_CLOUD.get(key), None, "", "基线"
    if section == "ppv":
        if key in p.get("ppv", {}):
            v, u, w = entry(p["ppv"][key])
            return v, u, w, "预设"
        if key in P.BASE["PPV"]:
            return P.BASE["PPV"][key], None, "", "基线"
        return P.CAMERA_LOOK.get(key, [None])[0], None, "", "共用"
    full = section + "." + key
    if full in p.get("set", {}):
        v, u, w = entry(p["set"][full])
        return v, u, w, "预设"
    if key in P.BASE.get(section, {}):
        return P.BASE[section][key], None, "", "基线"
    return None, None, "", "—"


SECTION_NAMES = {
    "DirectionalLightComponent": "DirectionalLight（太阳）",
    "SkyAtmosphereComponent": "SkyAtmosphere（大气）",
    "SkyLightComponent": "SkyLight（天光）",
    "VolumetricCloudComponent": "VolumetricCloud（云层）",
    "ExponentialHeightFogComponent": "ExponentialHeightFog（高度雾）",
}


def managed_keys(name):
    """Every managed property of one preset, grouped, in a readable order."""
    p = {} if name == "base" else P.PRESETS[name]
    out = []
    for section in ("DirectionalLightComponent", "SkyAtmosphereComponent", "SkyLightComponent",
                    "VolumetricCloudComponent", "ExponentialHeightFogComponent"):
        keys = list(P.BASE.get(section, {}))
        for k in p.get("set", {}):
            s, prop = k.split(".", 1)
            if s == section and prop not in keys:
                keys.append(prop)
        out.append((section, [k for k in keys if k in P.BASE.get(section, {}) or (section + "." + k) in p.get("set", {})]))
    cloud = list(P.BASE_CLOUD)
    out.append(("cloud", cloud))
    ppv = list(P.BASE["PPV"]) + list(P.CAMERA_LOOK)
    for k in p.get("ppv", {}):
        if k not in ppv:
            ppv.append(k)
    out.append(("ppv", ppv))
    return out


def param_table(name, full=False):
    """The properties this weather sets, with unit, meaning and reason; untouched baseline properties are summarised
    (full=True lists them too: the baseline section's complete inventory)."""
    rows, n_base = [], 0
    if not full:
        sun = P.PRESETS[name]["sun"][:2]
        rows.append(("<b>太阳</b>", "sun.elevation / azimuth", "%.1f / %.1f" % (sun[0], sun[1]), "°",
                     T.GLOSSARY["sun"][1], esc(P.PRESETS[name]["sun"][2]), "预设"))
    else:
        rows.append(("<b>太阳</b>", "sun.elevation / azimuth", "%.1f / %.1f" % tuple(P.BASE_SUN), "°",
                     T.GLOSSARY["sun"][1], "10:00 晴天（上一份报告的太阳位置，北纬 35° 夏日上午）", "基线"))
    for section, keys in managed_keys(name):
        for key in keys:
            v, u, w, src = effective(name, section, key)
            if v is None:
                continue
            if src != "预设" and not full:
                n_base += 1
                continue
            g = T.GLOSSARY.get(key) or T.GLOSSARY.get(section + "." + key)
            unit = u or (g[0] if g else "")
            meaning = g[1] if g else ""
            label = SECTION_NAMES.get(section, {"cloud": "云材质 M_CS_CumulusCloud", "ppv": "后处理 CS_ClearSky_PPV"}[section]
                                      if section in ("cloud", "ppv") else section)
            rows.append((label, esc(key), esc(fmt(v)), esc(unit), esc(meaning), esc(w), src))
    head = ("<tr><th>组件</th><th>参数</th><th>值</th><th>单位</th><th>含义</th><th>为什么是这个值（照片 → 物理 → 参数）</th></tr>")
    body = "".join("<tr><td>%s</td><td><code>%s</code></td><td class='num'>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                   % r[:6] for r in rows)
    rest = ("<div class='baseline'>其余 %d 个受管属性保持基线值（10:00 晴天，完整清单见“基线”一节）。</div>" % n_base) \
        if n_base else ""
    return "<table class='params'>%s%s</table>%s" % (head, body, rest)


def ref_meta(name):
    p = P.PRESETS[name]
    label, idx = next((l, r) for l, r in p["shots"] if r is not None)
    ref = PICKS[p["ref"]][idx]
    return label, idx, ref


def section(name):
    p = P.PRESETS[name]
    label, idx, ref = ref_meta(name)
    crop = p.get("ref_crop", {}).get(str(idx))
    photo_uri, photo_im = img(os.path.join(REFS, "%s_%d.jpg" % (p["ref"], idx)), 1000, 84, crop)
    photo_top, photo_bot = means(photo_im)
    render_path = os.path.join(SHOTS, "wx_%s_%s_%s.png" % (name, short(label), TAG))
    render_uri, render_im = img(render_path, 1000, 84)
    r_top, r_bot = means(render_im)
    hero_path = os.path.join(SHOTS, "wx_%s_hero_%s.png" % (name, TAG))
    hero_uri, hero_im = img(hero_path, 520, 84)
    sheet_uri, _ = img(os.path.join(COMPARE, "%s_%s.jpg" % (name, TAG)), 1500, 84)
    date = (ref.get("date") or "")[:16].replace(":", "-", 2)
    exif = []
    if date:
        exif.append(date)
    if ref.get("model"):
        exif.append(ref["model"])
    if ref.get("fnumber") and ref.get("exposure") and ref.get("iso"):
        t = ref["exposure"]
        exif.append("f/%g · %s · ISO %d → EV100 %.1f"
                    % (ref["fnumber"], ("1/%d s" % round(1 / t)) if t < 1 else ("%g s" % t), ref["iso"], ref["ev100"]))
    if ref.get("sun"):
        exif.append("太阳高度 %.1f° 方位 %.0f°" % tuple(ref["sun"]))
    cam_photo = P.CAMERAS[label]
    cam_line = ("%s：%s，%s%s，水平 FOV %.0f°"
                % (label, "位置 " + fmt([round(x) for x in cam_photo["loc"]]),
                   "朝向 " + fmt(cam_photo.get("rot") or "看向城市中心"),
                   "，%d×%d" % tuple(cam_photo["res"]), cam_photo["fov"]))
    gaps = [abs(a - b) for a, b in zip(photo_top, r_top)]
    stats = ("<div class='stats'>画面上半幅平均 sRGB：<b>照片 %s</b> · <b>渲染 %s</b> · 各通道差 %s / 255；"
             "下半幅：照片 %s · 渲染 %s。</div>"
             % (photo_top, r_top, [round(x) for x in gaps], photo_bot, r_bot))
    physics = "".join("<li>%s</li>" % esc(x) for x in T.PHYSICS[name])
    notes = "".join("<li>%s</li>" % esc(x) for x in T.NOTES.get(name, []))
    return """
<section class='wx' id='w_%(id)s'>
<h2>%(title)s</h2>
<p class='lead'>%(lead)s</p>
<div class='cards'>
  <div class='card'><b>时间与太阳</b><span>高度 %(elev).1f°（%(mtext)s）· 方位 %(azim).1f°</span></div>
  <div class='card'><b>照片</b><span>%(where)s · %(date)s</span></div>
  <div class='card'><b>曝光 EV100</b><span>%(ev)s · 锁定（下限 = 上限）</span></div>
  <div class='card'><b>对位机位</b><span>%(camline)s</span></div>
  <div class='card'><b>云材质</b><span>%(mi)s</span></div>
</div>
<div class='sheet'><img src="%(sheet)s" alt="photo vs render"><div class='cap'>照片（左）· 对位机位渲染（中）· 主机位 CS_SkyCam（右）</div></div>
%(stats)s
<h3>现实物理</h3><ul class='phys'>%(physics)s</ul>
<h3>参数：含义与目的</h3>
%(table)s
<div class='row2'>
  <figure><img src="%(photo)s" alt="photo"><figcaption><b>参考照片</b> %(ptitle)s<br>%(pexif)s<br>
  %(artist)s · <a href='%(page)s'>%(lic)s</a></figcaption></figure>
  <figure><img src="%(render)s" alt="render"><figcaption><b>对位渲染</b> wx_%(id)s_%(short)s_%(tag)s.png<br>
  同一机位、同一曝光，相机风格（饱和度 / 对比度）单独模拟</figcaption></figure>
  <figure class='tall'><img src="%(hero)s" alt="hero"><figcaption><b>主机位</b> CS_SkyCam（247 m，城市上空，向东南）<br>
  所有天气共用，用来横向比较</figcaption></figure>
</div>
<h3>照片与渲染的对比</h3><ul class='notes'>%(notes)s</ul>
</section>""" % {
        "id": name, "title": esc(p["title"]), "en": "", "lead": esc(T.LEAD[name]),
        "elev": p["sun"][0], "azim": p["sun"][1],
        "mtext": ("太阳在地平线下，没有直射光" if p["sun"][0] <= -2.0
                  else "Kasten–Young 大气质量 m≈%.1f" % solar.air_mass(p["sun"][0])),
        "where": esc(ref.get("where") or ""), "date": esc(date),
        "ev": "%.1f" % ref.get("ev100", 0) if ref.get("ev100") else "—",
        "camline": esc(cam_line), "mi": esc(p["cloud"]["mi"]),
        "sheet": sheet_uri, "stats": stats, "physics": physics,
        "table": param_table(name),
        "photo": photo_uri, "ptitle": esc(ref.get("title", "")), "pexif": esc(" | ".join(exif)),
        "artist": esc((ref.get("artist") or "")[:70]), "page": esc(ref.get("page") or ""),
        "lic": esc(ref.get("license") or ""), "render": render_uri, "hero": hero_uri,
        "short": short(label), "tag": TAG, "notes": notes,
    }


CSS = """
:root{--bg:#0f1115;--card:#171a21;--ink:#e8e6e3;--mut:#9aa3ad;--acc:#f0c674;--acc2:#7fb5ff;--line:#2a2f3a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 "Microsoft YaHei","PingFang SC",
"Segoe UI",sans-serif}main{max-width:1180px;margin:0 auto;padding:28px 22px 90px}
h1{font-size:30px;margin:6px 0 4px}h2{font-size:22px;margin:46px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line);color:var(--acc)}
h3{font-size:17px;margin:26px 0 6px;color:var(--acc2)}p{margin:8px 0}a{color:var(--acc2)}
code{font-family:Consolas,"Cascadia Mono",monospace;font-size:12.5px;background:#232834;padding:1px 5px;border-radius:4px;color:#ffd99a}
.sub{color:var(--mut);margin-bottom:18px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin:14px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:9px 12px}
.card b{display:block;color:var(--acc);font-size:13px;font-weight:600}.card span{font-size:13.5px}
.sheet img{width:100%;border-radius:8px;border:1px solid var(--line);display:block}
.cap{color:var(--mut);font-size:12.5px;margin-top:4px}
.stats{background:#14171d;border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:13px;color:#cfd6df;margin:8px 0}
.row2{display:flex;gap:14px;align-items:flex-start;margin:14px 0}
.row2 figure{margin:0;flex:1 1 0;min-width:0}figure img{width:100%;border-radius:6px;border:1px solid var(--line)}
.row2 figure.tall{flex:0 0 22%}figcaption{color:var(--mut);font-size:12.5px;margin-top:5px}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px}
th,td{border:1px solid var(--line);padding:5px 7px;vertical-align:top;text-align:left}
th{background:#1c2029;color:#cfd6df}tr:nth-child(even) td{background:#14171d}
td.num{text-align:right;font-family:Consolas,monospace;white-space:nowrap}
table.params td:nth-child(2) code{font-size:11.5px}
table.params{table-layout:fixed}
table.params th:nth-child(1){width:13%}table.params th:nth-child(2){width:17%}
table.params th:nth-child(3){width:10%}table.params th:nth-child(4){width:6%}
table.params th:nth-child(5){width:25%}table.params th:nth-child(6){width:29%}
table.params td{overflow-wrap:anywhere;word-break:break-word}
table.params td.num{white-space:normal}
.baseline{color:var(--mut);font-size:13px;margin:-2px 0 8px}
ul{margin:6px 0 6px 20px;padding:0}li{margin:3px 0}
.phys li{margin:5px 0}.notes li{margin:4px 0;color:#dfe3e8}
.lead{color:#d7dbe0}
.toc{columns:2;font-size:14px}.toc a{text-decoration:none}
.note{background:#1e1a10;border-left:3px solid var(--acc);padding:8px 12px;border-radius:6px;margin:10px 0;font-size:13.5px}
.hero img{width:100%;border-radius:8px;border:1px solid var(--line)}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.grid3 figure{margin:0}
.grid3 img{width:100%;height:220px;object-fit:cover;border-radius:6px;border:1px solid var(--line)}
.grid3 figcaption{font-size:12px;color:var(--mut)}
"""


def main():
    base_hero = img(os.path.join(SHOTS, "wx_base_hero_%s.png" % TAG), 640, 84)
    strip = []
    for name in P.ORDER:
        uri, _ = img(os.path.join(SHOTS, "wx_%s_hero_%s.png" % (name, TAG)), 340, 80)
        strip.append("<figure><img src='%s'><figcaption>%s</figcaption></figure>" % (uri, esc(P.PRESETS[name]["title"])))
    sections = "\n".join(section(n) for n in P.ORDER)
    toc = "".join("<li><a href='#w_%s'>%s</a></li>" % (n, esc(P.PRESETS[n]["title"])) for n in P.ORDER)
    comps = "".join("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (esc(a), esc(b), esc(c)) for a, b, c in T.COMPONENTS)
    forms = "".join("<tr><td><b>%s</b></td><td><code>%s</code></td></tr>" % (esc(a), esc(b)) for a, b in T.FORMULAS)
    limits = "".join("<li>%s</li>" % esc(x) for x in T.LIMITS)
    method = "".join("<li>%s</li>" % x for x in T.METHOD)       # METHOD contains inline <b>/<code>
    material = "".join("<p>%s</p>" % x for x in T.MATERIAL_NOTE)
    baseline = """
<h2 id='baseline'>基线 · 上午 10:00 晴天积云</h2>
<p class='lead'>%(lead)s</p>
<table class='params'><tr><th>组件</th><th>参数</th><th>值</th><th>单位</th><th>含义</th><th>为什么是这个值</th></tr>
%(rows)s
</table>""" % {"lead": esc(T.LEAD["base"]), "rows": param_table("base", full=True).split(">", 1)[1].rsplit("</table>", 1)[0]}
    page = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>City Sample 静态天气复现 · 照片 → 物理 → 参数 → 渲染</title><style>%(css)s</style></head><body><main>
<h1>City Sample 演示关卡 · 11 种静态天气的复现</h1>
<div class='sub'>UE 5.8.2（源码构建 <code>E:\\UnrealEngine</code>）· D3D12 / SM6 · 关卡
<code>/CitySamplePCG/Levels/L_CitySamplePCG_Demo</code> · 2026-11-11 · 在上午 10:00 晴天积云（
<a href='citysample-clear-sky-renderdoc.html'>上一份报告</a>）的基线上做参数增量，关卡从未保存</div>
<div class='cards'>
<div class='card'><b>做法</b><span>每张参考照片按 EXIF 的时刻与地点定太阳，按曝光定 EV100，按能见度定消光，按颜色定光谱，再拆到 SkyAtmosphere / 体积云材质 / 高度雾 / 后处理的参数</span></div>
<div class='card'><b>天气</b><span>正午晴空、黄金时刻、火烧云、蓝调时刻、全阴天、雾、日出晨雾、城市雾霾、沙尘暴、雷暴云砧、卷云（11 种）</span></div>
<div class='card'><b>对比</b><span>每种天气一台“照片对位机位”（复现照片的视角与太阳相对方位）+ 同一台主机位 CS_SkyCam；渲染与照片同曝光</span></div>
<div class='card'><b>渲染设置</b><span>云逐像素追踪（<code>r.VolumetricRenderTarget.Mode 3</code>），截图前渲 32 帧（<code>r.HighResScreenshotDelay 32</code>），大气高精度 LUT，臭氧按相机通道平均</span></div>
<div class='card'><b>不做的事</b><span>没有雨、雪粒子和风；没有夜间城市灯光；冰晶晕；真实地理（演示城市不是芝加哥 / 纽约）</span></div>
<div class='card'><b>驱动</b><span><code>Content/Python/cs_weather.py</code>（apply / shoot / batch / restore），参数数据 <code>cs_weather_presets.py</code>，报告 <code>Tools/cs_weather/build_report.py</code></span></div>
</div>
<div class='hero'><img src="%(base)s" alt="baseline"></div>
<div class='cap'>基线：上午 10:00 晴天积云（太阳 31.1° / 146°、EV100 13.4）。这台主机位在所有天气下拍同一构图。</div>
<h2 id='gallery'>一览</h2>
<div class='grid3'>%(strip)s</div>
<h2 id='method'>怎么做的</h2><ul>%(method)s</ul>
<h2 id='components'>用到的组件与它们负责什么</h2>
<table><tr><th>组件</th><th>负责</th><th>调整的参数</th></tr>%(comps)s</table>
<h2 id='formulas'>公式与单位</h2><table><tr><th>量</th><th>公式 / 约定</th></tr>%(forms)s</table>
%(baseline)s
<h2 id='weathers'>11 种天气</h2><div class='toc'><ol>%(toc)s</ol></div>
%(sections)s
<h2 id='ozone'>附录 A · 臭氧为什么按相机通道平均</h2><p>%(ozone)s</p>
<h2 id='material'>附录 B · 云材质的扩展（2026-11-11）</h2>%(material)s
<h2 id='limits'>限制</h2><ul>%(limits)s</ul>
<h2 id='repro'>复现</h2>
<p>编辑器打开演示关卡后，在 <code>Content/Python/</code> 下用 MCP 桥（端口 8777）执行：</p>
<p><code>cs_weather.py {"phase": "batch", "tag": "final", "settle": 90}</code> 依次应用并拍摄全部天气；
<code>{"phase": "apply", "preset": "fog"}</code> 单独应用一种；
<code>{"phase": "restore", "to": "base"}</code> 回到 10:00，<code>{"phase": "restore", "to": "original"}</code> 回到关卡原状。
结束后 <code>C:\\Python314\\python.exe -P -E Tools/cs_weather/build_report.py</code> 重新生成本页。</p>
<p class='sub'>参考照片来自 Wikimedia Commons，作者与许可见每张图下方；渲染图在 <code>Saved/Screenshots/WindowsEditor/wx_*_final.png</code>。</p>
</main></body></html>""" % {
        "css": CSS, "base": base_hero[0], "strip": "".join(strip), "method": method, "comps": comps,
        "forms": forms, "toc": toc, "sections": sections, "ozone": esc(T.OZONE_NOTE), "material": material,
        "limits": limits, "baseline": baseline,
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print("report:", OUT, "%.1f MB" % (os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()
