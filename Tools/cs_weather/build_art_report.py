# build_art_report.py -- docs/citysample-cloud-art.html: the ten art-directed volumetric-cloud weathers of the City Sample
# demo level (Content/Python/cs_weather_art.py) as a teaching page: what each cloud is, how the cloud material and the
# scene parameters express it, and the renders. No reference photos: these weathers are not matched to photos.
#
#   C:\Python314\python.exe -P -E Tools/cs_weather/build_art_report.py [--tag final]
#       -> docs/citysample-cloud-art.html (self-contained: every image is inlined as JPEG)
import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "Content", "Python"))
sys.path.insert(0, os.path.dirname(__file__))
import art_text as A  # noqa: E402
import build_report as B  # noqa: E402  (img, esc, fmt, entry, CSS, SECTION_NAMES)
import cs_weather_presets as P  # noqa: E402
import report_text as T  # noqa: E402
import solar  # noqa: E402

SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "WindowsEditor")
OUT = os.path.join(ROOT, "docs", "citysample-cloud-art.html")
esc = B.esc


def short(label):
    return "hero" if label == "CS_SkyCam" else label.replace("CS_WX_", "").replace("CS_ART_", "").lower()


def shot(name, label, tag, max_w):
    path = os.path.join(SHOTS, "wx_%s_%s_%s.png" % (name, short(label), tag))
    if not os.path.exists(path):
        return None
    return B.img(path, max_w, 84)[0]


def meaning(section, key):
    for k in (section + "." + key, key):
        g = A.ART_GLOSSARY.get(k) or T.GLOSSARY.get(k)
        if g:
            return g
    return ("", "")


def is_art(why):
    return str(why).startswith("艺术处理")


def param_rows(name):
    p = P.PRESETS[name]
    night = bool(p.get("night_sky"))
    rows = [("月亮" if night else "太阳", "elevation / azimuth", "%.1f / %.0f" % (p["sun"][0], p["sun"][1]), "°",
             "高度角 / 方位角（顺时针，北 = +X）" + ("：平行光在夜景里当月亮用" if night else ""), p["sun"][2], False)]
    for key, e in p["set"].items():
        if key in P.OZONE_BAND:
            continue
        section, prop = key.split(".", 1)
        v, u, w = B.entry(e)
        unit, mean = meaning(section, prop)
        rows.append((B.SECTION_NAMES.get(section, section), prop, B.fmt(v), u or unit, mean, w, is_art(w)))
    for key, e in p["cloud"]["params"].items():
        v, u, w = B.entry(e)
        unit, mean = meaning("cloud", key)
        rows.append(("云材质 " + p["cloud"]["mi"], key, B.fmt(v), u or unit, mean, w, is_art(w)))
    for key, e in p.get("night_sky", {}).items():
        v, u, w = B.entry(e)
        unit, mean = meaning("night", key)
        rows.append(("星空穹顶 MI_CS_NightSky", key, B.fmt(v), u or unit, mean, w, is_art(w)))
    for key, e in p.get("ppv", {}).items():
        v, u, w = B.entry(e)
        unit, mean = meaning("ppv", key)
        rows.append(("后处理", key, B.fmt(v), u or unit, mean, w, is_art(w)))
    return rows


def param_table(name):
    head = "<tr><th>组件</th><th>参数</th><th>值</th><th>单位</th><th>含义</th><th>为什么是这个值（成因 → 参数）</th></tr>"
    body = "".join("<tr%s><td>%s</td><td><code>%s</code></td><td class='num'>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                   % (" class='art'" if r[6] else "", esc(r[0]), esc(r[1]), esc(r[2]), esc(r[3]), esc(r[4]), esc(r[5]))
                   for r in param_rows(name))
    note = ("<div class='baseline'>未列出的属性保持基线（上午 10:00 晴天积云）的值；云材质未列出的参数取中性值（新形态全部关闭），"
            "臭氧按相机通道平均（所有天气共用）。<span class='artkey'>黄色底</span>的行是艺术处理，不属于天气物理。</div>")
    return "<table class='params'>%s%s</table>%s" % (head, body, note)


def cam_line(label):
    c = P.CAMERAS[label]
    loc = [round(x / 100.0) for x in c["loc"]]
    if "rot" in c:
        aim = "俯仰 %.0f° · 朝向 %.0f°" % (c["rot"][0], c["rot"][1] % 360.0)
    else:
        aim = "看向 %s m" % B.fmt([round(x / 100.0) for x in c["target"]])
    return "%s：位置 %s m · %s · 水平 FOV %.0f°" % (label, B.fmt(loc), aim, c["fov"])


def layer_text(p):
    def cfg(key):
        v = p["set"].get("VolumetricCloudComponent." + key)
        return v[0] if v else P.BASE["VolumetricCloudComponent"][key]
    bottom, height = cfg("layer_bottom_altitude"), cfg("layer_height")
    base = p["cloud"]["params"].get("BaseKm", [0.0])[0]
    txt = "%.2g–%.3g km" % (bottom, bottom + height)
    if base:
        txt += "（云底 %.2g km，以下是雨幕的空间）" % (bottom + base)
    return txt


def section(i, name, tag):
    p = P.PRESETS[name]
    label = p["shots"][0][0]
    big = shot(name, label, tag, 1180)
    hero = shot(name, "CS_SkyCam", tag, 520)
    elev = p["sun"][0]
    if p.get("night_sky"):
        sun = "月亮高 %.0f° · 方位 %.0f°" % (elev, p["sun"][1])
    elif elev < 0:
        sun = "太阳在地平线下 %.1f° · 方位 %.0f°" % (-elev, p["sun"][1])
    else:
        sun = "太阳 %.1f° · 方位 %.0f° · 大气质量 m≈%.1f" % (elev, p["sun"][1], solar.air_mass(elev))
    ev = p.get("ppv", {}).get("auto_exposure_min_brightness", [P.BASE["PPV"]["auto_exposure_min_brightness"]])[0]
    fig = ("<figure class='big'><img src='%s' alt='%s'><figcaption>设计机位 %s</figcaption></figure>"
           % (big, esc(name), esc(cam_line(label)))) if big else "<div class='missing'>缺少渲染 %s</div>" % esc(label)
    herofig = ("<figure class='tall'><img src='%s' alt='hero'><figcaption><b>主机位</b> CS_SkyCam（247 m 高、朝 155°）"
               "——所有天气同一构图</figcaption></figure>" % hero) if hero else ""
    phys = "".join("<li>%s</li>" % esc(x) for x in A.PHYSICS[name])
    expr = "".join("<li>%s</li>" % esc(x) for x in A.EXPRESS[name])
    return """
<section class='wx' id='w_%(id)s'>
<h2>%(i)d · %(title)s <span class='en'>%(en)s</span></h2>
<p class='lead'>%(lead)s</p>
<div class='cards'>
  <div class='card'><b>时刻</b><span>%(time)s · %(sun)s</span></div>
  <div class='card'><b>云层</b><span>%(layer)s</span></div>
  <div class='card'><b>曝光 EV100</b><span>%(ev)s（锁定）</span></div>
  <div class='card'><b>云材质实例</b><span>%(mi)s</span></div>
</div>
%(fig)s
<div class='row2'>
  <div class='txt'><h3>这种云是什么</h3><ul class='phys'>%(phys)s</ul>
  <h3>材质和参数怎么表达它</h3><ul class='phys'>%(expr)s</ul></div>
  %(hero)s
</div>
<h3>参数</h3>
%(table)s
</section>""" % {"id": name, "i": i, "title": esc(p["title"]), "en": esc(p.get("en", "")), "lead": esc(A.LEAD[name]),
                 "time": esc(p.get("time", "")), "sun": esc(sun), "layer": esc(layer_text(p)), "ev": "%.1f" % ev,
                 "mi": esc(p["cloud"]["mi"]), "fig": fig, "phys": phys, "expr": expr, "hero": herofig,
                 "table": param_table(name)}


CSS = B.CSS + """
.en{font-size:14px;color:var(--mut);font-weight:400;margin-left:8px}
figure.big{margin:12px 0}figure.big img{width:100%;border-radius:8px;border:1px solid var(--line)}
.row2 .txt{flex:1 1 0;min-width:0}.row2 figure.tall{flex:0 0 30%}
tr.art td{background:#2a2410 !important}.artkey{background:#2a2410;padding:0 4px;border-radius:3px}
.missing{background:#2a1515;border:1px dashed #a55;padding:30px;text-align:center;border-radius:8px;color:#e99}
.gal{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.gal figure{margin:0}
.gal img{width:100%;aspect-ratio:16/10;object-fit:cover;border-radius:6px;border:1px solid var(--line)}
.gal figcaption{font-size:13px;color:var(--ink)}
table.feat{table-layout:fixed}
table.feat th:nth-child(1){width:15%}table.feat th:nth-child(2){width:30%}
table.feat th:nth-child(3){width:33%}table.feat th:nth-child(4){width:22%}
table.feat td{overflow-wrap:anywhere;word-break:break-word}
table.feat td:nth-child(1){font-weight:600;color:var(--acc)}
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="final")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    gal = []
    for i, n in enumerate(P.ART_ORDER, 1):
        uri = shot(n, P.PRESETS[n]["shots"][0][0], a.tag, 700)
        if uri:
            gal.append("<figure><a href='#w_%s'><img src='%s'></a><figcaption>%d · %s</figcaption></figure>"
                       % (n, uri, i, esc(P.PRESETS[n]["title"])))
    feats = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td><code>%s</code></td></tr>" % tuple(esc(x) for x in f)
                    for f in A.FEATURES)
    sections = "\n".join(section(i, n, a.tag) for i, n in enumerate(P.ART_ORDER, 1))
    toc = "".join("<li><a href='#w_%s'>%s</a></li>" % (n, esc(P.PRESETS[n]["title"])) for n in P.ART_ORDER)
    method = "".join("<li>%s</li>" % x for x in A.METHOD)          # METHOD carries inline <b>/<code>
    limits = "".join("<li>%s</li>" % esc(x) for x in A.LIMITS)
    page = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>City Sample · 十种体积云艺术天气</title><style>%(css)s</style></head><body><main>
<h1>City Sample 演示关卡 · 十种体积云艺术天气</h1>
<div class='sub'>UE 5.8.2（源码构建 <code>E:\\UnrealEngine</code>）· D3D12 / SM6 · 关卡
<code>/CitySamplePCG/Levels/L_CitySamplePCG_Demo</code> · 2026-11-12 · 在上午 10:00 晴天积云的基线上做参数增量，关卡从未保存 ·
照片还原版见 <a href='citysample-weather-presets.html'>静态天气复现</a></div>
<p class='lead'>%(intro)s</p>
<h2 id='gallery'>一览</h2><div class='gal'>%(gal)s</div>
<h2 id='method'>怎么做的</h2><ul>%(method)s</ul>
<h2 id='features'>体积云材质的新形态</h2>
<p>密度仍由一个 Custom HLSL 节点给出（当时是 <code>Content/Python/cs_sky_assets.py</code> 的 <code>CODE</code>；2026-11-12 起由 <code>Content/Python/cs_cloud_code.py</code> 生成，见 <code>docs/citysample-cloud-motion.html</code>），在原来的积云 / 卷云 / 风暴单体之上加了下面这些项。
每一项的参数默认关闭；抽查三种照片天气（基线、雷暴、卷云）重新渲染，与旧图的差别在渲染噪声以内。</p>
<table class='feat'><tr><th>形态</th><th>现实里的成因</th><th>密度项怎么做</th><th>参数</th></tr>%(feats)s</table>
<h2 id='weathers'>十种天气</h2><div class='toc'><ol>%(toc)s</ol></div>
%(sections)s
<h2 id='limits'>限制</h2><ul>%(limits)s</ul>
<h2 id='repro'>复现</h2>
<p>编辑器打开演示关卡后，通过 MCP 桥（端口 8777）执行 <code>Content/Python/</code> 下的脚本：</p>
<p><code>cs_sky_assets.py {"phase": "material"}</code> 和 <code>{"phase": "nightsky"}</code> 生成云材质和星空材质；
<code>cs_weather.py {"phase": "batch", "presets": "art", "tag": "final", "settle": 90}</code> 依次应用并拍摄十种天气；
<code>{"phase": "apply", "preset": "art_storm"}</code> 单独应用一种；<code>{"phase": "restore", "to": "original"}</code> 回到关卡原状。
之后 <code>C:\\Python314\\python.exe -P -E Tools/cs_weather/build_art_report.py</code> 重新生成本页。</p>
<p class='sub'>渲染图在 <code>Saved/Screenshots/WindowsEditor/wx_art_*_%(tag)s.png</code>；参数数据 <code>Content/Python/cs_weather_art.py</code>，
文字 <code>Tools/cs_weather/art_text.py</code>。</p>
</main></body></html>""" % {"css": CSS, "intro": esc(A.INTRO), "gal": "".join(gal), "method": method, "feats": feats,
                             "toc": toc, "sections": sections, "limits": limits, "tag": esc(a.tag)}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print("report:", a.out, "%.1f MB" % (os.path.getsize(a.out) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
