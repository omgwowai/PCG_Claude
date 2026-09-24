#!/usr/bin/env python
"""
build_pcg_stage_report.py — 把 City Sample 18 阶段 PCG 运行整理成一份自包含的
HTML 验收报告。

清单驱动：读一个 JSON 清单，描述每个阶段及其截图，再把截图降采样后以 base64
data URI 内嵌，所以产出的是一份没有外部依赖、可以直接发给别人看的单文件页面。

    python Tools/build_pcg_stage_report.py \\
        --manifest Saved/Reports/stage_manifest.json \\
        --out docs/pcg-18-stage-report.html

产出的文件是**片段形态**（只有 <title> / <link> / <style> / 内容，没有
html/head/body）：浏览器打开时会把 <title> 归入 head，页面正常渲染、标签页标题
正确；作为 Artifact 发布时，发布端会替它套上骨架，片段形态正是它要的形态。

模板用 str.replace 填 __TOKEN__，不用 %-格式化：页面 CSS 里本来就有百分号
（width:100%），%-格式化会直接炸掉。卡片同理，用 replace 而不是 f-string。
"""

import argparse
import base64
import html
import io
import json
import os
import sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    print("Pillow is required: pip install pillow", file=sys.stderr)
    raise

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 18 张图要塞进一页，同时保持图里的 PCG debug 几何看得清。
MAX_EDGE = 1200
JPEG_QUALITY = 80

STATUS_ZH = {"ok": "有画面", "empty": "数据阶段", "missing": "缺截图"}

PAGE = """<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=Source+Sans+3:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
  /* 亮色是基准调色板：所有 token 先在裸 :root 里定义完整，再由下面两个暗色块覆盖。
     颜色一律走 token，组件样式不写死在 media / [data-theme] 块里。 */
  :root{
    color-scheme: light;
    --ground:#eef1f5; --surface:#ffffff; --surface-2:#f6f8fa;
    --ink:#0e1319; --muted:#5a6675; --line:#d5dce5;
    --accent:#0b6e7f; --accent-soft:#0b6e7f1a;
    --ok:#2d7a55; --warn:#96650e; --bad:#a03a46;
    --ok-soft:#2d7a5518; --warn-soft:#96650e18; --bad-soft:#a03a4618;
    --shadow:0 1px 2px #0e131912, 0 8px 24px -12px #0e131926;
    --sans:"Source Sans 3",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    --display:"Archivo",var(--sans);
    --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  }
  @media (prefers-color-scheme: dark){
    :root:not([data-theme="light"]){
      color-scheme: dark;
      --ground:#0d1116; --surface:#151b22; --surface-2:#111720;
      --ink:#e8edf3; --muted:#8e9aa8; --line:#232c36;
      --accent:#3fb6c9; --accent-soft:#3fb6c91f;
      --ok:#52b183; --warn:#d2a24c; --bad:#d96a76;
      --ok-soft:#52b1831f; --warn-soft:#d2a24c1f; --bad-soft:#d96a761f;
      --shadow:0 1px 2px #00000059, 0 10px 28px -14px #000000a6;
    }
  }
  :root[data-theme="dark"]{
    color-scheme: dark;
    --ground:#0d1116; --surface:#151b22; --surface-2:#111720;
    --ink:#e8edf3; --muted:#8e9aa8; --line:#232c36;
    --accent:#3fb6c9; --accent-soft:#3fb6c91f;
    --ok:#52b183; --warn:#d2a24c; --bad:#d96a76;
    --ok-soft:#52b1831f; --warn-soft:#d2a24c1f; --bad-soft:#d96a761f;
    --shadow:0 1px 2px #00000059, 0 10px 28px -14px #000000a6;
  }

  *{box-sizing:border-box}
  body{
    margin:0; background:var(--ground); color:var(--ink);
    font-family:var(--sans); font-size:16px; line-height:1.6;
    -webkit-font-smoothing:antialiased;
  }
  .wrap{max-width:1180px; margin:0 auto; padding-inline:20px; padding-block:34px 72px}
  a{color:var(--accent)}
  :focus-visible{outline:2px solid var(--accent); outline-offset:3px; border-radius:3px}
  code{font-family:var(--mono); font-size:.88em; overflow-wrap:anywhere}  /* 关卡路径是连续长串，必须允许断行，否则会把页面撑宽造成横向滚动 */

  header.run{display:flex; flex-direction:column; gap:14px; margin-bottom:30px}
  .eyebrow{
    font-family:var(--mono); font-size:11.5px; letter-spacing:.14em;
    text-transform:uppercase; color:var(--accent); margin:0;
  }
  h1{
    font-family:var(--display); font-weight:700; font-size:clamp(26px,3.6vw,38px);
    line-height:1.12; letter-spacing:-.015em; margin:0; text-wrap:balance;
  }
  .lede{margin:0; color:var(--muted); max-width:66ch; overflow-wrap:anywhere}
  .stats{
    display:flex; flex-wrap:wrap; gap:10px 26px; margin:2px 0 0;
    padding-block:14px; border-block:1px solid var(--line);
  }
  .stats div{display:flex; align-items:baseline; gap:8px}
  .stats b{
    font-family:var(--mono); font-weight:500; font-size:17px;
    font-variant-numeric:tabular-nums; color:var(--ink);
  }
  .stats span{font-size:13px; color:var(--muted)}

  ol.stages{list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:20px}
  li.stage{display:grid; grid-template-columns:46px minmax(0,1fr); gap:16px; align-items:start}
  /* 序号轨：编号是真的顺序（阶段 N 喂 N+1），所以用一条线把它画出来 */
  .rail{display:flex; flex-direction:column; align-items:center; gap:8px; height:100%}
  .num{
    font-family:var(--mono); font-size:13px; font-weight:500; font-variant-numeric:tabular-nums;
    width:40px; height:40px; flex:0 0 auto; display:grid; place-items:center;
    border-radius:10px; background:var(--accent-soft); color:var(--accent);
  }
  .rail .thread{flex:1 1 auto; width:1px; background:var(--line); min-height:18px}
  li.stage:last-child .rail .thread{background:linear-gradient(var(--line),transparent)}

  .card{
    background:var(--surface); border:1px solid var(--line); border-radius:12px;
    box-shadow:var(--shadow); overflow:hidden; min-width:0;
  }
  .card-head{display:flex; flex-wrap:wrap; align-items:baseline; gap:8px 12px; padding:15px 18px 13px}
  .card-head h2{
    font-family:var(--display); font-weight:600; font-size:18px;
    letter-spacing:-.01em; margin:0; text-wrap:balance;
  }
  .graph{font-family:var(--mono); font-size:12.5px; color:var(--muted); word-break:break-all; overflow-wrap:anywhere}
  .chip{
    margin-left:auto; flex:0 0 auto; font-size:12px; font-weight:600;
    padding:3px 10px; border-radius:999px; white-space:nowrap;
    border:1px solid currentColor;
  }
  .chip.ok{color:var(--ok); background:var(--ok-soft)}
  .chip.empty{color:var(--warn); background:var(--warn-soft)}
  .chip.missing{color:var(--bad); background:var(--bad-soft)}

  dl.metrics{
    display:flex; flex-wrap:wrap; gap:0; margin:0;
    padding:12px 18px 14px; border-top:1px solid var(--line);
  }
  dl.metrics div{display:flex; flex-direction:column; gap:1px; padding-right:26px}
  dl.metrics dt{font-size:10.5px; letter-spacing:.09em; text-transform:uppercase; color:var(--muted)}
  dl.metrics dd{margin:0; font-family:var(--mono); font-size:14.5px; font-variant-numeric:tabular-nums}

  figure.shot{margin:0; border-top:1px solid var(--line); background:#0a0d11}
  figure.shot img{display:block; width:100%; height:auto; max-width:100%}
  .noimg{padding:44px 18px; text-align:center; color:var(--muted); font-size:14px; background:var(--surface-2)}
  .note{
    margin:0; padding:11px 18px 14px; font-size:13.5px; color:var(--muted);
    border-top:1px solid var(--line); background:var(--surface-2);
  }
  /* 两张图的下标：debug / 累计几何。小字居中，压在暗色图上，保证看得懂哪张是哪张 */
  .shotcap{
    margin:0; padding:6px 18px 10px; font-size:11.5px; letter-spacing:.09em;
    text-transform:uppercase; color:var(--muted); background:#0a0d11;
    border-top:1px solid #ffffff14;
  }
  @media (max-width:520px){
    .shotcap{padding-inline:14px}
  }

  footer.run{
    margin-top:32px; padding-top:16px; border-top:1px solid var(--line);
    color:var(--muted); font-size:13px; max-width:80ch;
  }

  @media (max-width:520px){
    .wrap{padding-inline:16px; padding-block:24px 56px}
    li.stage{grid-template-columns:34px minmax(0,1fr); gap:10px}
    .num{width:32px; height:32px; font-size:12px; border-radius:8px}
    .card-head{padding:13px 14px 11px}
    dl.metrics{padding-inline:14px}
    dl.metrics div{padding-right:18px}
    .note{padding-inline:14px}
  }
  @media (prefers-reduced-motion: reduce){
    *{animation:none !important; transition:none !important}
  }
</style>

<div class="wrap">
  <header class="run">
    <p class="eyebrow">__EYEBROW__</p>
    <h1>__TITLE__</h1>
    <p class="lede">__LEDE__</p>
    <div class="stats">__STATS__</div>
  </header>

  <ol class="stages">
__CARDS__
  </ol>

  <footer class="run">__FOOTER__</footer>
</div>
"""

CARD = """    <li class="stage">
      <div class="rail"><div class="num">__N__</div><div class="thread"></div></div>
      <article class="card">
        <div class="card-head">
          <h2>__LABEL__</h2>
          <span class="graph">__GRAPH__</span>
          <span class="chip __STATUS__">__STATUS_ZH__</span>
        </div>
        <dl class="metrics">
          <div><dt>实例</dt><dd>__INSTANCES__</dd></div>
          <div><dt>debug 立方体</dt><dd>__DEBUG__</dd></div>
          <div><dt>机位</dt><dd>__CAM__</dd></div>
        </dl>
        __SHOT__
        <p class="note">__NOTE__</p>
      </article>
    </li>"""


SHOT_FIGURE = ('<figure class="shot" data-kind="__KIND__">'
               '<img loading="lazy" src="__SRC__" '
               'width="__W__" height="__H__" alt="__ALT__"></figure>'
               '<p class="shotcap">__KIND_ZH__</p>')
KIND_ZH = {"debug": "PCG debug", "geometry": "累计几何"}


def render_shots(st, max_edge, quality, repo):
    """One figure per entry in shots[]; legacy 'shot' single path still works.

    Returns (html, missing_list, total_kb).

    The two-shot path exists because the small-area run captures each stage twice: an
    isolated PCG-debug frame and a cumulative-geometry frame. The legacy single `shot`
    key is kept because the 09-23 report is rebuilt from a manifest that uses it, and
    that report must keep regenerating.

    `data-kind` on each figure is not decoration: it is what lets a reader (or a test)
    tell the two frames apart in the markup, since the visible captions are Chinese.
    """
    out, missing, kb = [], [], 0.0
    entries = st.get("shots")
    if not entries:
        single = st.get("shot")
        entries = [{"kind": None, "path": single}] if single else []
    for e in entries:
        kind = e.get("kind")
        p = e.get("path")
        if p:
            ap = p if os.path.isabs(p) else os.path.join(repo, p)
            if os.path.exists(ap):
                uri, w, h, k = encode(ap, max_edge, quality)
                kb += k
                out.append(SHOT_FIGURE
                           .replace("__SRC__", uri)
                           .replace("__W__", str(w))
                           .replace("__H__", str(h))
                           .replace("__ALT__", html.escape(str(st.get("label") or "")))
                           .replace("__KIND__", html.escape(str(kind or "")))
                           .replace("__KIND_ZH__", html.escape(KIND_ZH.get(kind, ""))))
                continue
            missing.append(str(st.get("graph")))
        out.append('<div class="noimg">无截图：' +
                   html.escape(str(e.get("img_missing") or "未捕获")) + "</div>")
    return "".join(out), missing, kb


def encode(path, max_edge, quality):
    """降采样到 max_edge，返回 (data_uri, w, h, kb)。"""
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        scale = max_edge / float(max(w, h))
        if scale < 1.0:
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                           Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        iw, ih = im.size
    raw = buf.getvalue()
    return ("data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii"),
            iw, ih, len(raw) / 1024.0)


def fmt(n):
    return "—" if n is None else format(n, ",")


def cam_from_note(note):
    """清单把机位写在 note 末尾（'机位：xxx。'），取出来单独成一列。"""
    for tok in str(note).split("。"):
        t = tok.strip()
        if t.startswith("机位："):
            return t[len("机位："):].strip()
    return "—"


def card(st, shot):
    """One stage card. `shot` is the already-rendered figure HTML from render_shots."""
    e = html.escape
    m = st.get("metrics") or {}
    status = str(m.get("status") or "missing").lower()
    return (CARD
            .replace("__N__", str(st.get("n", "?")))
            .replace("__LABEL__", e(str(st.get("label") or st.get("graph"))))
            .replace("__GRAPH__", e(str(st.get("graph"))))
            .replace("__STATUS__", e(status))
            .replace("__STATUS_ZH__", e(STATUS_ZH.get(status, status)))
            .replace("__INSTANCES__", fmt(m.get("instances")))
            .replace("__DEBUG__", fmt(m.get("debug_instances")))
            .replace("__CAM__", e(cam_from_note(st.get("notes", ""))))
            .replace("__SHOT__", shot)
            .replace("__NOTE__", e(str(st.get("notes") or ""))))


def build_html_with_stats(man, max_edge=MAX_EDGE, quality=JPEG_QUALITY, repo=None):
    """Render the manifest to the report document, plus the stats main() prints.

    This is the single rendering pass. build_html() delegates here and keeps only the
    document, so the two entry points cannot render the stage list twice or disagree
    about it, and main() still gets total_kb and missing without a second pass.
    """
    repo = repo or REPO
    stages = man.get("stages", [])
    cards, missing = [], []
    total_kb = 0.0
    for st in stages:
        st = dict(st)
        shot_html, miss, kb = render_shots(st, max_edge, quality, repo)
        total_kb += kb
        missing.extend(miss)
        cards.append(card(st, shot_html))

    n_total = len(stages)
    n_shot = n_total - len(missing)
    n_ok = sum(1 for s in stages if (s.get("metrics") or {}).get("status") == "ok")
    n_data = sum(1 for s in stages
                 if (s.get("metrics") or {}).get("status") == "empty")
    tot_inst = sum((s.get("metrics") or {}).get("instances") or 0 for s in stages)
    tot_dbg = sum((s.get("metrics") or {}).get("debug_instances") or 0 for s in stages)

    stats = "".join([
        '<div><b>%d</b><span>个阶段</span></div>' % n_total,
        '<div><b>%d</b><span>张截图</span></div>' % n_shot,
        '<div><b>%s</b><span>真实实例</span></div>' % format(tot_inst, ","),
        '<div><b>%s</b><span>debug 立方体</span></div>' % format(tot_dbg, ","),
        '<div><b>%d / %d</b><span>有画面 / 数据阶段</span></div>' % (n_ok, n_data),
    ])

    doc = (PAGE
           .replace("__EYEBROW__", "City Sample PCG · 阶段验收")
           .replace("__TITLE__", html.escape(str(man.get("title", "PCG 阶段报告"))))
           .replace("__LEDE__", html.escape(str(man.get("subtitle", ""))) +
                    ' 关卡 <code>' + html.escape(str(man.get("level", ""))) + "</code>。")
           .replace("__STATS__", stats)
           .replace("__CARDS__", "\n".join(cards))
           .replace("__FOOTER__", html.escape(str(man.get("footer", "")))))
    return doc, total_kb, missing


def build_html(man, max_edge=MAX_EDGE, quality=JPEG_QUALITY, repo=None):
    """The report document only. Thin wrapper so callers and tests need one value."""
    doc, _kb, _missing = build_html_with_stats(man, max_edge, quality, repo)
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-edge", type=int, default=MAX_EDGE,
                    help="内嵌图像长边像素（默认 %d）" % MAX_EDGE)
    ap.add_argument("--quality", type=int, default=JPEG_QUALITY,
                    help="内嵌 JPEG 质量（默认 %d）" % JPEG_QUALITY)
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as fh:
        man = json.load(fh)

    doc, total_kb, missing = build_html_with_stats(man, args.max_edge,
                                                  args.quality)

    n_total = len(man.get("stages", []))
    n_shot = n_total - len(missing)

    out = args.out if os.path.isabs(args.out) else os.path.join(REPO, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(doc)

    print("wrote %s" % out)
    print("stages=%d captured=%d embedded=%.1f KB html=%.1f KB"
          % (n_total, n_shot, total_kb, os.path.getsize(out) / 1024.0))
    if missing:
        print("WARNING stages without an image: %s" % ", ".join(map(str, missing)))


if __name__ == "__main__":
    main()
