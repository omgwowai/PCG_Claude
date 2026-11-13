# build_motion_report.py -- docs/citysample-cloud-motion.html: how the City Sample art clouds move with time and blend
# from one preset to another (docs/superpowers/specs/2026-11-12-cs-cloud-motion-design.md §7). Reads the director's data
# (cs_weather_art.MOTION / TRANSITION_CLIPS through cs_weather_presets, cs_cloud_motion's tracks), the encoded clips
# (encode_clips.py), the jump checks (motion_check.py) and the measurements (perf_summary.py). The videos are copied next
# to the page (docs/citysample-cloud-motion/) and linked; posters, strips and timelines are inlined.
#   C:\Python314\python.exe -P -E Tools/cs_weather/build_motion_report.py
import json
import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "Content", "Python"))
sys.path.insert(0, os.path.dirname(__file__))
import build_report as B  # noqa: E402  (img, esc, fmt, CSS)
import cs_cloud_motion as M  # noqa: E402
import cs_weather_presets as P  # noqa: E402
import cs_wx_resolve as R  # noqa: E402
import motion_text as T  # noqa: E402

BASE = os.path.join(ROOT, "Saved", "Reports", "cs_cloud_motion")
CLIPS = os.path.join(BASE, "clips")
OUT = os.path.join(ROOT, "docs", "citysample-cloud-motion.html")
MEDIA = os.path.join(ROOT, "docs", "citysample-cloud-motion")
EMPTY = {"components": {}}
esc = B.esc
EXTRA_CSS = """
video{width:100%;display:block;margin:10px 0;background:#000;border-radius:6px}
img.strip{width:100%;display:block;margin:4px 0 12px;border-radius:4px}
svg.timeline{width:100%;margin:8px 0 4px;background:#fff;border-radius:6px}
p.missing{color:#ff8a80} p.check{color:var(--mut);font-size:13px} span.en{color:var(--mut);font-weight:normal;font-size:14px}
"""


def num(v):
    return "—" if v is None else B.fmt(v)


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def video(clip):
    src = os.path.join(CLIPS, clip + "_web.mp4")       # encode_clips.py's 1280 px copy (the CRF 20 master stays in Saved)
    if not os.path.exists(src):
        return "<p class='missing'>（片段 %s 还没有编码）</p>" % esc(clip)
    os.makedirs(MEDIA, exist_ok=True)
    shutil.copy2(src, os.path.join(MEDIA, clip + ".mp4"))
    poster = os.path.join(CLIPS, clip + "_poster.jpg")
    strip = os.path.join(CLIPS, clip + "_strip.jpg")
    pattr = " poster='%s'" % B.img(poster, 1280, 84)[0] if os.path.exists(poster) else ""
    simg = ("<img class='strip' src='%s' alt='%s 的六个时刻'>" % (B.img(strip, 1900, 80)[0], esc(clip))
            if os.path.exists(strip) else "")
    return ("<video controls loop muted playsinline preload='metadata'%s src='citysample-cloud-motion/%s.mp4'></video>%s"
            % (pattr, esc(clip), simg))


def mod_text(m):
    if "osc" in m:
        return "%s 振荡 ±%s，周期 %s 分钟" % (m["param"], num(m["osc"][0]), num(m["osc"][1]))
    dist, speed, deg = m["approach"]
    return "%s 推进：%s m/s 朝 %s°，最远 %s km" % ("/".join(m["params"]), num(speed), num(deg), num(dist))


def motion_table(name):
    rows = []
    for key, e in P.PRESETS[name].get("motion", {}).items():
        label, unit = T.KEY_NAMES.get(key, (key, ""))
        if key == "mods":
            rows += [(label, mod_text(m), "", why) for m, why in e]
        else:
            v = e[0]
            rows.append((label, "–".join(num(x) for x in v) if isinstance(v, list) else num(v), unit, e[1]))
    head = "<tr><th>量</th><th>值</th><th>单位</th><th>为什么</th></tr>"
    body = "".join("<tr><td>%s</td><td class='num'>%s</td><td>%s</td><td>%s</td></tr>" % tuple(esc(x) for x in r)
                   for r in rows)
    return "<table class='params'>%s%s</table>" % (head, body)


def timeline_svg(a_name, b_name):
    ra, rb = R.resolve(a_name, EMPTY), R.resolve(b_name, EMPTY)
    ma, mb = M.motion_for(ra.get("motion"), ra["cloud"]), M.motion_for(rb.get("motion"), rb["cloud"])
    fw, gw = M.effective_windows(ma["fade_window"], mb["form_window"])
    rows = [("光照", M.LIGHT_WINDOW[0], M.LIGHT_WINDOW[1], "#9a9a9a"),
            ("云层 → 并集", 0.0, gw[0], "#4f9d69"), ("云层 → 目标", fw[1], 1.0, "#4f9d69")]
    rows += [("A · " + n, fw[0] + f0 * (fw[1] - fw[0]), fw[0] + f1 * (fw[1] - fw[0]), "#e08a2e")
             for n, f0, f1, _end in M.fade_tracks(ra["cloud"])]
    rows += [("B · " + n, gw[0] + g0 * (gw[1] - gw[0]), gw[0] + g1 * (gw[1] - gw[0]), "#3a78c2")
             for n, g0, g1, _start in M.form_tracks(rb["cloud"])]
    w, lab, rh = 900, 170, 16
    h = 24 + rh * len(rows)

    def x(p):
        return lab + (w - lab - 10) * p

    out = ["<svg class='timeline' viewBox='0 0 %d %d' xmlns='http://www.w3.org/2000/svg'>" % (w, h)]
    for i in range(11):
        out.append("<line x1='%.1f' y1='14' x2='%.1f' y2='%d' stroke='#ddd'/>" % (x(i / 10), x(i / 10), h))
        out.append("<text x='%.1f' y='11' font-size='10' text-anchor='middle'>%d%%</text>" % (x(i / 10), i * 10))
    for i, (name, a, b, col) in enumerate(rows):
        y = 18 + rh * i
        out.append("<text x='%d' y='%d' font-size='11' text-anchor='end'>%s</text>" % (lab - 6, y + 11, esc(name)))
        out.append("<rect x='%.1f' y='%d' width='%.1f' height='%d' rx='3' fill='%s'/>"
                   % (x(a), y + 2, max(x(b) - x(a), 1.0), rh - 4, col))
    out.append("</svg>")
    return "".join(out)


def perf_section():
    perf = load(os.path.join(BASE, "perf.json"), {})
    if not perf:
        return "<p class='missing'>（还没有测量）</p>"
    head = "<tr><th>测量</th><th>云相关 GPU（ms）</th><th>整帧（ms）</th><th>导演每帧 CPU 平均 / 最大（ms）</th></tr>"
    body = "".join("<tr><td>%s</td><td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s / %s</td></tr>"
                   % (esc(label), num(e.get("cloud_ms")), num(e.get("frame_ms")),
                      num((e.get("tick_ms") or {}).get("mean")), num((e.get("tick_ms") or {}).get("max")))
                   for label, e in perf.items())
    return "<table class='params'>%s%s</table>" % (head, body)


def check_text(clip):
    c = load(os.path.join(BASE, "checks", clip + ".json"), None)
    if c is None:
        return ""
    verdict = "没有跳变" if not c["jumps"] else "跳变帧：%s" % c["jumps"]
    return ("<p class='check'>跳变检查（相邻帧亮度差，8× 缩小后；第 %d–%d 帧）：中位数 %s，最大 %s，%s。</p>"
            % (c["range"][0], c["range"][1], num(c["median"]), num(c["max"]), esc(verdict)))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    clips = {c["preset"]: c["clip"] for c in M.clip_list(P) if c["kind"] == "preset"}
    parts = ["<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'><title>%s</title><style>%s%s</style>"
             "</head><body><main>" % (esc(T.TITLE), B.CSS, EXTRA_CSS),
             "<h1>%s</h1><p class='sub'>%s</p>" % (esc(T.TITLE), esc(T.SUBTITLE))]
    parts += ["<p>%s</p>" % esc(p) for p in T.INTRO]
    parts.append("<h2>1. 时间怎样进入云材质</h2>")
    parts += ["<h3>%s</h3><p>%s</p>" % (esc(t), esc(x)) for t, x in T.MECHANISMS]
    parts.append("<h2>2. 十种云怎样随时间变化</h2>")
    for i, name in enumerate(P.ART_ORDER, 1):
        p = P.PRESETS[name]
        parts.append("<section><h3>2.%d %s <span class='en'>%s</span></h3>%s%s</section>"
                     % (i, esc(p["title"]), esc(p["en"]), video(clips[name]), motion_table(name)))
    parts.append("<h2>3. 从一种云过渡到另一种云</h2>")
    parts += ["<p>%s</p>" % esc(x) for x in T.TRANSITIONS_INTRO]
    for i, c in enumerate(P.TRANSITION_CLIPS, 1):
        title = "%s → %s" % (P.PRESETS[c["from"]]["title"], P.PRESETS[c["to"]]["title"])
        mode = "整套画面一起过渡" if c["light"] == "full" else "只换云，光照不变"
        parts.append("<section><h3>3.%d %s <span class='en'>%s</span></h3><p>%s</p>%s%s%s</section>"
                     % (i, esc(title), esc(mode), esc(c["why"]), video(c["clip"]), timeline_svg(c["from"], c["to"]),
                        check_text(c["clip"])))
    parts.append("<h2>4. 开销</h2>%s" % perf_section())
    parts.append("<h2>5. 局限</h2><ul>%s</ul>" % "".join("<li>%s</li>" % esc(x) for x in T.LIMITS))
    parts.append("<h2>6. 怎么用</h2><table class='params'>%s</table>" % "".join(
        "<tr><td>%s</td><td><code>%s</code></td></tr>" % (esc(a), esc(b)) for a, b in T.HOWTO))
    parts.append("</main></body></html>")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(OUT, round(os.path.getsize(OUT) / 1e6, 2), "MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
