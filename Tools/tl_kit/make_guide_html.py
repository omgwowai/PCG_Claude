# -*- coding: utf-8 -*-
"""make_guide_html.py -- build docs/tl-building-guide.html, a self-contained
(inline base64 images, inline SVG) Chinese walkthrough of how the TL PCG
building is assembled: the Blender kit, the shape grammar, the BDF data asset,
the PCG graph, the showcase level and the numbers each stage produced.

    python Tools/tl_kit/make_guide_html.py

Sources it reads (all produced by earlier steps of this run):
  Saved/Screenshots/WindowsEditor/sc_*.png   in-editor documentation captures
  Saved/kit_catalog/*.png                    Blender kit catalogue + elevation
  Saved/kit_catalog/elevation_F1.json        module pixel boxes for the overlay
  Saved/guide_tmp/facade_L0*.json            real per-facade module sequences
  Tools/tl_kit/tl_kit_spec.json              the 43 kit parts and level heights
  Tools/tl_kit/kit_common.py                 the grammars and symbol map
"""
import base64
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import kit_common  # noqa: E402

SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "WindowsEditor")
KIT = os.path.join(ROOT, "Saved", "kit_catalog")
TMP = os.path.join(ROOT, "Saved", "guide_tmp")
OUT = os.path.join(ROOT, "docs", "tl-building-guide.html")

from PIL import Image  # noqa: E402

_cache = {}


def b64(path, width=1200, quality=76, crop=None):
    """JPEG-encoded, resized base64 of a PNG on disk."""
    key = (path, width, quality, crop)
    if key in _cache:
        return _cache[key]
    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop(crop)
    if im.width > width:
        im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    out = base64.b64encode(buf.getvalue()).decode("ascii")
    _cache[key] = out
    return out


def shot(name, caption, width=1200, quality=76, half=False):
    p = os.path.join(SHOTS, name + ".png")
    cls = "shot half" if half else "shot"
    return ('<figure class="%s"><img src="data:image/jpeg;base64,%s" alt="%s">'
            '<figcaption>%s</figcaption></figure>'
            % (cls, b64(p, width, quality), name, caption))


def kitimg(name, caption="", width=900, quality=80):
    p = os.path.join(KIT, name + ".png")
    cap = '<figcaption>%s</figcaption>' % caption if caption else ""
    return ('<figure class="kit"><img src="data:image/jpeg;base64,%s" alt="%s">%s</figure>'
            % (b64(p, width, quality), name, cap))


def partimg(mesh, width=150):
    p = os.path.join(KIT, "part_%s.png" % mesh)
    if not os.path.exists(p):
        return ""
    return ('<img class="part" src="data:image/jpeg;base64,%s" alt="%s">'
            % (b64(p, width, 72), mesh))


# --------------------------------------------------------------------------
# input data
# --------------------------------------------------------------------------
spec = json.load(open(os.path.join(HERE, "tl_kit_spec.json"), encoding="utf-8"))
elev = json.load(open(os.path.join(KIT, "elevation_F1.json"), encoding="utf-8"))
facade = {}
for lv in ("L01", "L02", "L03", "L04"):
    p = os.path.join(TMP, "facade_%s.json" % lv)
    if os.path.exists(p):
        facade[lv] = json.load(open(p, encoding="utf-8"))
if os.path.exists(os.path.join(TMP, "facade_BDF.json")):
    facade["bdf"] = json.load(open(os.path.join(TMP, "facade_BDF.json"), encoding="utf-8"))


# --------------------------------------------------------------------------
# SVG helpers -- plain boxes and orthogonal arrows, no external assets
# --------------------------------------------------------------------------
def svg_open(w, h):
    return ('<svg class="diagram" viewBox="0 0 %d %d" width="100%%" '
            'xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI,Roboto,sans-serif">'
            '<defs><marker id="ah" markerWidth="9" markerHeight="9" refX="7" refY="3" '
            'orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#5b6b7c"/></marker></defs>' % (w, h))


def box(x, y, w, h, title, sub="", kind="node"):
    """A rounded node box; `sub` may hold several lines separated by newlines."""
    fill = {"node": "#eef3f8", "db": "#fdf1dc", "vol": "#e7f3ea",
            "gen": "#f2e9f7", "out": "#eaeef2"}[kind]
    stroke = {"node": "#7f97b0", "db": "#c79a3c", "vol": "#5f9c72",
              "gen": "#9a6fb0", "out": "#8a9aa8"}[kind]
    s = ('<rect x="%d" y="%d" width="%d" height="%d" rx="6" fill="%s" stroke="%s" '
         'stroke-width="1.4"/>' % (x, y, w, h, fill, stroke))
    lines = [(title, 12.5, "#22313f", "600")] + [
        (ln, 10.5, "#5b6b7c", "400") for ln in (sub.split("\n") if sub else [])]
    step = 15
    ty = y + h / 2.0 - step * (len(lines) - 1) / 2.0
    for i, (ln, size, color, weight) in enumerate(lines):
        s += ('<text x="%.1f" y="%.1f" font-size="%.1f" font-weight="%s" fill="%s" '
              'text-anchor="middle" dominant-baseline="middle">%s</text>'
              % (x + w / 2.0, ty + i * step, size, weight, color, ln))
    return s


def label(x, y, text, anchor="middle", size=10, color="#5b6b7c"):
    return ('<text x="%.1f" y="%.1f" font-size="%s" fill="%s" text-anchor="%s">%s</text>'
            % (x, y, size, color, anchor, text))


def poly(pts, dash=False):
    d = ' stroke-dasharray="4 3"' if dash else ""
    return ('<path d="M%s" fill="none" stroke="#5b6b7c" stroke-width="1.6"%s '
            'marker-end="url(#ah)"/>' % (" L".join("%.1f,%.1f" % p for p in pts), d))


def line(pts):
    return ('<path d="M%s" fill="none" stroke="#5b6b7c" stroke-width="1.6"/>'
            % " L".join("%.1f,%.1f" % p for p in pts))


# --- diagram 1: the showcase graph (PCG_TL_Building_BDF) ------------------
def graph_top_svg():
    W, H = 1180, 560
    s = svg_open(W, H)
    # column headers
    for x, t in ((20, "① 造底面轮廓"), (330, "② 两层建筑体量"), (670, "③ 屋顶"), (960, "④ 输出")):
        s += label(x, 20, t, "start", 12, "#3f6d93")
    # column 1: footprint
    c1 = [("Create_Spline_Shape ×2", "Wing A 6000×3000 cm\nWing B 3000×6000 cm"),
          ("Transform_Align ×2", "分别对齐到 min Y / min X"),
          ("Compose_Areas_Union", "两个矩形合成 L 形"),
          ("FilterDataByType", "→ GetSplineControlPoints"),
          ("CreateSpline → CleanSpline", "闭合折线")]
    ys = [36, 112, 176, 240, 304]
    hs = [58, 46, 46, 46, 46]
    for (t, sub), y, h in zip(c1, ys, hs):
        s += box(20, y, 230, h, t, sub)
    for i in range(4):
        s += poly([(135, ys[i] + hs[i]), (135, ys[i + 1] - 2)])
    s += box(20, 400, 230, 58, "LoadCitySampleData", "BDF_WithTL\nBDF_NamesOnly_WithTL", "db")
    s += box(20, 478, 230, 58, "PCG 用户参数", "WingA/B 尺寸 → Create_Spline_Shape\nBase/SecondLayerHeight → Assign", "out")
    # column 2: the two Assign calls and the contract between them
    s += box(330, 36, 260, 70, "Assign_CitySampleBuildings",
             "AssignBase · 高度 = BaseLayerHeight (2000)\nStaggered=False · Foundation=True", "vol")
    s += box(330, 168, 260, 46, "Transform_Areas_Contract", "Contract = 240 cm")
    s += box(330, 272, 260, 70, "Assign_CitySampleBuildings",
             "AssignSecond · 高度 = SecondLayerHeight (4000)\nStaggered=True · Foundation=True", "vol")
    s += label(460, 382, "两处都重载 BuildingsStyles = \"TL\"", "middle", 11, "#2f6b45")
    # footprint -> AssignBase
    s += poly([(250, 327), (288, 327), (288, 60), (328, 60)])
    s += label(292, 196, "L 形轮廓", "start")
    # data -> both assigns
    s += line([(250, 429), (306, 429), (306, 84)])
    s += poly([(306, 84), (328, 84)])
    s += poly([(306, 318), (328, 318)])
    s += label(310, 446, "BDF 数据", "start")
    # AssignBase -> contract -> AssignSecond
    s += poly([(460, 106), (460, 166)])
    s += label(466, 140, "Rooftops Footprints", "start")
    s += poly([(460, 214), (460, 270)])
    s += label(466, 246, "缩进后的轮廓", "start")
    # column 3: roof
    s += box(670, 150, 240, 58, "Create_Mesh_Planar", "平面动态网格\nMI_Rooftop_BitumenRoofing", "gen")
    s += box(670, 400, 240, 58, "Fill_Areas_WithFittingAssets", "14 个 Rooftop_*_PCG 组合\n只用最高那片屋面", "gen")
    s += poly([(590, 52), (630, 52), (630, 170), (668, 170)])
    s += poly([(590, 300), (640, 300), (640, 190), (668, 190)])
    s += poly([(590, 326), (650, 326), (650, 429), (668, 429)])
    s += label(600, 120, "屋面轮廓", "start")
    # column 4: outputs
    s += box(960, 36, 200, 58, "墙面模块 + 道具", "主层 L0–L4 · ISM 实例", "out")
    s += box(960, 272, 200, 58, "墙面模块 + 道具", "第二层 LV2*–L4 · ISM 实例", "out")
    s += box(960, 150, 200, 58, "两块屋顶网格", "z 1770.5 / 5441.5 cm", "out")
    s += box(960, 400, 200, 58, "屋顶设备", "25 个实例", "out")
    s += poly([(590, 44), (958, 44)])
    s += poly([(590, 286), (958, 286)])
    s += poly([(910, 179), (958, 179)])
    s += poly([(910, 429), (958, 429)])
    s += "</svg>"
    return s


# --- diagram 2: inside Assign_CitySampleBuildings (the BDF route) ---------
BDF_STEPS = [
    ("DuplicateCrossSections：按竖向语法逐层复制轮廓", "BDF.VerticalGrammar · Levels.LevelHeight"),
    ("SplineToSegment → RoundSegmentAngles：轮廓切成段，转角圆整", "（轮廓本身）"),
    ("角件替换：段首尾的 FC / LC 按前后转角变成 C_E 或 C_I", "Modules 的 C_E / C_I 行"),
    ("按段长从 FLengths 选 F0 / F1 / F2 → Loop_Subdivide 细分", "Levels.F0/F1/F2 · FLengths · Modules.Size / bScalable"),
    ("PivotOffset：把每个模块挪到开间中心", "Modules.PivotOffset"),
    ("HasProps 过滤 → Loop_GroupedPropsCopy：按 Mod_Name 复制道具点", "Modules.HasProps · Props 组"),
    ("WindowHelper / Decal 过滤 → ASM_Clutter_Behavior → StaticMeshSpawner", "Props.WindowHelper · Clutter* · Probability"),
    ("屋面轮廓 + RoofOffset / RoofInset → Rooftops Footprints 输出", "BDF.RoofData"),
]


def graph_bdf_svg():
    W, H = 1180, 470
    s = svg_open(W, H)
    chain = [("LoadCitySampleData", "四组标签的 BDF 数据", "db"),
             ("…_CoreProcess", "样式名过滤\n按 BuildingToken JOIN", "node"),
             ("BDF_Input_Processor", "读 BDF / Levels 行", "node"),
             ("PartitionBDF_PerSpline", "每条轮廓一份", "node"),
             ("BDF_BuildingFromSpline", "217 个节点", "vol"),
             ("StaticMeshSpawner", "ISM 实例输出", "out")]
    x, w, gap = 14, 172, 23
    for i, (t, sub, kind) in enumerate(chain):
        s += box(x + i * (w + gap), 20, w, 62, t, sub, kind)
        if i < len(chain) - 1:
            s += poly([(x + i * (w + gap) + w, 51), (x + (i + 1) * (w + gap) - 2, 51)])
    # expand BDF_BuildingFromSpline into its steps
    bx = x + 4 * (w + gap)
    s += ('<rect x="14" y="108" width="1152" height="350" rx="8" fill="#fbfcfd" '
          'stroke="#5f9c72" stroke-dasharray="5 4"/>')
    s += line([(bx + w / 2.0, 82), (bx + w / 2.0, 108)])
    s += label(28, 130, "BDF_BuildingFromSpline 内部，按执行顺序", "start", 12, "#2f6b45")
    s += label(1150, 130, "这一步读 TL 数据表的哪些字段", "end", 12, "#8a6512")
    for i, (step, field) in enumerate(BDF_STEPS):
        y = 144 + i * 38
        s += ('<rect x="28" y="%d" width="700" height="30" rx="5" fill="%s" stroke="#b9c8d6"/>'
              % (y, "#eef3f8" if i % 2 == 0 else "#f6f8fa"))
        s += ('<circle cx="46" cy="%d" r="10" fill="#3f6d93"/>'
              '<text x="46" y="%d" font-size="11" fill="#fff" text-anchor="middle" '
              'dominant-baseline="middle">%d</text>' % (y + 15, y + 15, i + 1))
        s += ('<text x="64" y="%d" font-size="11.5" fill="#22313f" dominant-baseline="middle">%s</text>'
              % (y + 15, step))
        s += ('<rect x="744" y="%d" width="406" height="30" rx="5" fill="#fff8e8" stroke="#e8d5a8"/>'
              '<text x="756" y="%d" font-size="11" fill="#6b5212" dominant-baseline="middle">%s</text>'
              % (y, y + 15, field))
    s += "</svg>"
    return s


# --------------------------------------------------------------------------
# grammar / assembly HTML pieces
# --------------------------------------------------------------------------
SYM_NAME = {
    "W1": "墙板 Wall_01", "WS1": "可变长补长件 Wall_02", "P1": "壁柱 Column_01",
    "P2": "细壁柱 Column_02", "E1": "入口/特征窗 Entrance_01",
    "C_CE": "外角 CornerEx_01", "C_E": "外角（BDF 记号）",
    "C_I": "内角 CornerIn_01", "C_SL": "左半角（备用）", "C_SR": "右半角（备用）",
    "C_IL": "内左半角（备用）", "C_IR": "内右半角（备用）", "FS2": "基础条 Foundation_01",
}
SYM_COLOR = {"W1": "#c9553d", "WS1": "#e08b6a", "P1": "#b9c8d6", "P2": "#cfd9e2",
             "E1": "#3f6d93", "C_CE": "#8d6e63", "C_I": "#a1887f", "FS2": "#9e9e9e"}


def sym_chip(sym, width_cm=None):
    c = SYM_COLOR.get(sym, "#b9c8d6")
    light = c in ("#b9c8d6", "#cfd9e2")
    w = ' style="flex:%g"' % (width_cm or 100.0)
    txt = sym + ("<br><span class=cm>%g cm</span>" % width_cm if width_cm else "")
    return ('<div class="chip%s" style="background:%s"%s title="%s">%s</div>'
            % (" dark" if not light else "", c, w, SYM_NAME.get(sym, sym), txt))


def grammar_strip(seq):
    return '<div class="strip">%s</div>' % "".join(
        sym_chip(s, w) for s, w in seq)


# the ideal bay sequence of one F1 facade, from the kit widths
_by = {(p["level"], kit_common.PART_TO_SYMBOL[p["part"]]): p for p in spec["parts"]}
F1_SEQ = [("C_CE", _by[(1, "C_CE")]["width_m"] * 100),
          ("WS1", _by[(1, "WS1")]["width_m"] * 100),
          ("W1", _by[(1, "W1")]["width_m"] * 100),
          ("W1", _by[(1, "W1")]["width_m"] * 100),
          ("P1", _by[(1, "P1")]["width_m"] * 100),
          ("E1", _by[(1, "E1")]["width_m"] * 100),
          ("P1", _by[(1, "P1")]["width_m"] * 100),
          ("E1", _by[(1, "E1")]["width_m"] * 100),
          ("P1", _by[(1, "P1")]["width_m"] * 100),
          ("E1", _by[(1, "E1")]["width_m"] * 100),
          ("P1", _by[(1, "P1")]["width_m"] * 100),
          ("W1", _by[(1, "W1")]["width_m"] * 100),
          ("WS1", _by[(1, "WS1")]["width_m"] * 100),
          ("W1", _by[(1, "W1")]["width_m"] * 100),
          ("C_CE", _by[(1, "C_CE")]["width_m"] * 100)]


def elevation_overlay():
    """The rendered elevation with a band per storey and bay grid lines."""
    img_w, img_h = elev["size"]
    parts = []
    lv_label = {1: "L1 首层 500 cm", 2: "L2 标准层 300 cm", 3: "L3 顶层 300 cm",
                4: "L4 檐口 120 cm", 0: "L0 基础（地面以下 250 cm）"}
    seen = {}
    for m in elev["modules"]:
        x0, y0, x1, y1 = m["px"]
        seen.setdefault(m["lv"], [1e9, 1e9, -1e9, -1e9])
        b = seen[m["lv"]]
        seen[m["lv"]] = [min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1)]
    for lv, (x0, y0, x1, y1) in sorted(seen.items()):
        left = x0 / img_w * 100
        top = y0 / img_h * 100
        w = (x1 - x0) / img_w * 100
        h = (y1 - y0) / img_h * 100
        cls = "band bandbase" if lv == 0 else "band"
        parts.append('<div class="%s" style="left:%.2f%%;top:%.2f%%;width:%.2f%%;height:%.2f%%">'
                     '<span>%s</span></div>' % (cls, left, top, w, h, lv_label[lv]))
    # bay grid lines for the L1 row, labelled by symbol
    l1 = sorted([m for m in elev["modules"] if m["lv"] == 1], key=lambda m: m["px"][0])
    lines = []
    for m in l1:
        x0, y0, x1, y1 = m["px"]
        lines.append('<div class="bay" style="left:%.2f%%;top:%.2f%%;height:%.2f%%"></div>'
                     % (x0 / img_w * 100, y0 / img_h * 100, (y1 - y0) / img_h * 100))
    labels = []
    for m in l1:
        x0, y0, x1, y1 = m["px"]
        labels.append('<div class="baylbl" style="left:%.2f%%;top:%.2f%%;width:%.2f%%">%s</div>'
                      % (x0 / img_w * 100, y1 / img_h * 100, (x1 - x0) / img_w * 100, m["sym"]))
    return ('<div class="elevwrap"><img src="data:image/jpeg;base64,%s">%s%s%s</div>'
            % (b64(os.path.join(KIT, "elevation_F1.png"), 1500, 82),
               "".join(parts), "".join(lines), "".join(labels)))


def facade_strip(level, key, title):
    d = facade.get(level, {}).get(key)
    if not d:
        return ""
    seq = [(e["m"].replace("Wall_02", "WS1").replace("Wall_01", "W1")
            .replace("Column_01", "P1").replace("Entrance_01", "E1")
            .replace("CornerEx_01", "C_E").replace("CornerIn_01", "C_I"),
            round(e["a1"] - e["a0"], 1)) for e in d["seq"]]
    total = round(d["span"][1] - d["span"][0], 1)
    return ('<h4>%s <span class="muted">(%d 个模块, 共 %.0f cm)</span></h4>%s'
            % (title, d["n"], total, grammar_strip(seq)))


# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------
LV_ROLE = {0: "地坪以下基础", 1: "首层（店面 / 入口 / 石基）",
           2: "标准层（可重复）", 3: "顶层（重窗楣 + 檐带）", 4: "檐口女儿墙（topper）"}


def kit_table():
    rows = []
    for lv in (0, 1, 2, 3, 4):
        parts = [p for p in spec["parts"] if p["level"] == lv]
        lv_h = spec["levels"][str(lv)]["height_m"] * 100
        for i, p in enumerate(parts):
            sym = kit_common.PART_TO_SYMBOL[p["part"]]
            if lv == 0 and sym == "C_CE":
                sym = "C_E"  # LV0 has no corner cap; its exterior corner is only C_E
            rows.append(
                "<tr%s><td>%s</td><td>%s</td><td><code>%s</code></td><td>%s</td>"
                "<td>%s</td><td>%s</td><td class='thumb'>%s</td></tr>"
                % (' class="lvstart"' if i == 0 else "",
                   ("L%d<br><span class='muted'>%.0f cm</span>" % (lv, lv_h)) if i == 0 else "",
                   p["part"], sym, SYM_NAME.get(sym, ""),
                   "%.2f m" % p["width_m"],
                   p.get("kind", ""),
                   partimg(p["mesh_name"])))
    return ("<table class='kit'><thead><tr><th>层</th><th>部件</th><th>语法符号</th>"
            "<th>用途</th><th>开间宽</th><th>类型</th><th>预览</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


BDF_ROWS = [
    ("VerticalGrammar", "[LV0][LV1][LV2]*[LV3][LV4]",
     "`*` 是可重复标记；L2 标准层按建筑高度重复。没有可重复层的语法只能生成一个固定高度，会被所有地块拒绝。"),
    ("VerticalGrammarStaggered", "[LV2][LV2]*[LV3][LV4]",
     "错层体量叠在主体量之上，所以从 L2 起，不从首层起（与 CHJ 一致）。"),
    ("MinWallWidth", "950 cm", "TL 自己最窄的 FLengths.x；比它更短的墙 TL 建不了。"),
    ("MinBldgHeight", "1600 cm", "固定四层堆叠 500+300+300+120 cm 再加一次重复。"),
    ("MaxBldgHeight", "200000 cm",
     "作为匹配窗口被读取，不是描述性元数据。它必须与 MinBldgHeight 不等——窗口宽度为 0 会让这个样式无法被选中。"),
    ("RoofData", "(X=20, Y=-50, Z=20, W=10)",
     "XYY → RoofOffset，ZWW → RoofInset。Y 分量在全部 27 个样式上都是负值（CHA 为 −140），TL 原本写 +10，屋顶因此浮在檐口之上。"),
]

PROP_ROWS = [
    ("L1 Wall_01", "Group_Wall_1", "Awning_A01", "(2, 162.5, 355)", "yaw −90", "0.9", "70",
     "店面雨棚，压在石质腰线下"),
    ("L1 Wall_01", "Group_Wall_2", "Sign_E01", "(10, 22, 380)", "yaw 0", "1.0", "50",
     "开间边缘的招牌"),
    ("L1 Entrance_01", "Group_Door_1", "Lamp_Wall_A02 ×2", "(1, 14 / 311, 255)", "yaw −90", "1.0", "75",
     "门两侧的壁灯"),
    ("L1 Entrance_01", "Group_Door_2", "Sign_E01", "(10, 40, 380)", "yaw 0", "1.0", "85",
     "雨棚上方的招牌"),
    ("L1 Column_01", "Group_pillar_1", "Lamp_Wall_A02", "(18, 62.5, 250)", "yaw −90", "1.0", "65",
     "壁柱面壁灯"),
    ("L1 Column_01", "Group_pillar_2", "Sign_B01", "(18, 62.5, 330)", "yaw 0", "0.55", "25",
     "细长竖招牌"),
    ("L1 CornerEx_01", "Group_pillar_1", "Sign_B01 (A 面)", "(1, 90, 280)", "yaw 0", "0.75", "60",
     "转角两面各一块，两个方向都能读到"),
    ("L1 CornerEx_01", "Group_pillar_1", "Sign_B01 (B 面)", "(−90, −1, 280)", "yaw −90", "0.75", "60",
     "同上，另一面"),
    ("L1 CornerEx_01", "Group_Misc_1", "FirehoseConn_Outlet_A01", "(1, 100, 50)", "yaw −90", "1.0", "45",
     "街面消防接口"),
    ("L2 Wall_01", "Group_WallUp", "AC_Window_A02", "(21, 162.5, 85)", "yaw −90", "1.0", "35",
     "窗台空调外机"),
    ("L3 Wall_01", "Group_WallUp", "AC_Window_A02", "(21, 162.5, 85)", "yaw −90", "1.0", "35", "同上"),
    ("L3 Entrance_01", "Group_WallUp", "AC_Window_A01", "(21, 162.5, 55)", "yaw −90", "1.0", "40",
     "特征窗上的外机（L2 那个窗有栏杆，放不下）"),
]

SCRIPT_ROWS = [
    ("Tools/tl_kit/tl_kit_spec.json", "43 个部件的唯一事实来源：层高、开间宽、材质槽、枢轴约定"),
    ("Tools/tl_kit/build_tl_kit.py", "Blender 5.2 无界面建模，每个部件一个 FBX"),
    ("Tools/tl_kit/kit_common.py", "横向语法、符号映射、可拉伸符号、基础层枢轴"),
    ("Tools/tl_kit/render_kit_catalog.py", "渲染 43 张部件缩略图与 5 张分层图"),
    ("Tools/tl_kit/render_elevation.py", "渲染立面图 + 轴测图，并输出每个模块的像素框"),
    ("Content/Python/tl_kit_rebuild_meshes.py", "把 FBX 几何原地换进已有 mesh，保留资产路径与所有引用"),
    ("Content/Python/tl_make_rules.py", "生成 RULE_TL_L00..L04（SGD 路线的规则资产）"),
    ("Content/Python/tl_make_sgd.py", "生成 SGD_TL_A，把五条规则绑成一套形状语法定义"),
    ("Content/Python/tl_make_bdf.py", "把 TL 行追加进 BDF_WithTL 的 BDF / Levels / Modules / Props 四组"),
    ("Content/Python/tl_register.py", "DT_Bldg_MinWidth、DT_Bldg_LevelMinWidth 加 TL 行"),
    ("Content/Python/tl_names_with_tl.py", "把 TL 加进样式名字列表（NamesOnly 的副本）"),
    ("Content/Python/tl_whitelist_city.py", "把 TL 加进城市阶段的样式白名单（三个 Assign 调用的重载）"),
    ("Content/Python/tl_make_bdf_test_graph.py", "复制 Epic 的 L 形示例，做成只生成 TL 的单体测试图"),
    ("Content/Python/tl_showcase_setup.py", "在 Lvl_TL_Showcase 里搭地面与 PCGVolume 并触发生成"),
    ("Content/Python/tl_showcase_shot.py", "按类别显示/隐藏部件后排队高分辨率截图"),
    ("Content/Python/tl_showcase_read.py", "统计实例数、包围盒、各层 z 值与屋顶 mesh 范围"),
]

STEPS = [
    ("S1", "读清楚管线：BDF 才是入口", """
<p>先把 CitySample 的建筑生成链读一遍，而不是照着想象写数据。结论有两条推翻了最初的假设：</p>
<ul>
<li><code>SGD_&lt;CODE&gt;_A</code> <b>不是</b>城市生成的入口。27 个 <code>SGD_*</code> 只被
<code>Bldg_SGD_level.umap</code> / <code>PCG_Bldg_SGD_test</code> 这条预览路线消费。真正跑城市的是
<code>PCG_3_3_1_Buildings</code> → <code>Assign_CitySampleBuildings</code> →
<code>LoadCitySampleData</code> → <code>CitySampleBuildingBDF_Asset_PCG</code>，按 <code>BuildingToken</code> 过滤，
整条链里 <code>SGD_</code> 出现 0 次。</li>
<li>那个 BDF 数据库<b>可以从 Python 重建/扩展</b>，它不是压缩 blob：<code>UPCGDataAsset.data</code> 是
<code>BlueprintReadWrite FPCGDataCollection</code>，里面有四个标签组（BDF / Levels / Modules / Props）。</li>
</ul>
<p>于是 TL 要走的路是：造一套网格 → 写一套 BDF 行 → 注册进管线 → 新建关卡验证。</p>
"""),
    ("S2", "定套件清单与语法", """
<p>先把“需要哪些 mesh”写成清单，再动 Blender。<code>tl_kit_spec.json</code> 是唯一事实来源：
5 个层高（L0 基础 / L1 首层 500 / L2 标准层 300 / L3 顶层 300 / L4 檐口 120 cm），
每层的开间宽集合，以及 4 个材质槽。</p>
<p>开间横向语法（每个层共用同一套，所以上下对齐）：</p>
<p><code>F1 = [FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]</code></p>
<ul>
<li><code>[FC]</code>/<code>[LC]</code> 是首尾角件占位，<code>[A,B]</code> 表示 A、B 两件紧挨着成一组，<code>[X]+</code> 表示重复。</li>
<li><code>[WS1]</code>（Wall_02）是<b>可拉伸</b>的补长件，段长除不尽时由它吸收余量。</li>
<li>W1 / E1 / P1 在 L1–L4 上宽度相同（325 / 325 / 125 cm），于是壁柱永远压在壁柱上、特征窗永远压在入口上——
这就是“开间对位”。</li>
</ul>
"""),
    ("S3", "Blender 建模 43 件", """
<p><code>build_tl_kit.py</code> 在 Blender 5.2 无界面模式下用轴对齐盒子建模，
<b>每个部件一个 FBX</b>，几何直接写在 UE 坐标系里。</p>
<p>枢轴约定是这套件能不能拼上的前提：原点在部件<b>底部</b>、墙面一端；导入 UE 后一段墙沿局部 y ∈ [0, w]、z ∈ [0, h]；
建筑外侧朝局部 <b>+X</b>（实测自城市输出里 4,060 / 4,163 个实例）。</p>
<ul>
<li>外角 <code>CornerEx_01</code>：两翼从原点出发，一翼沿 +Y、一翼沿 −X，外表面在 x=+d 与 y=−d，每翼 1.5 m。</li>
<li>内角 <code>CornerIn_01</code>：两翼沿 +Y 与 +X，内角在原点。</li>
<li>L0 基础件挂在 z=0 以下（−250 cm..0），所以它们保留 NY 的 PivotOffset 而不是门面层那套 (0, −w/2, −h/2)。</li>
</ul>
"""),
    ("S4", "导入 UE：原地换几何", """
<p>不能删除再导入：删除会把 <code>BDF_WithTL</code>、<code>RULE_TL_*</code> 和关卡里已生成实例的引用置空；
用旧 FBX 工厂覆盖导入又会把材质槽追加一遍。</p>
<p><code>tl_kit_rebuild_meshes.py</code> 的做法是：每个部件先导进一个临时目录，给两个 mesh 都刷上 spec 里的 4 个材质槽，
再用 <code>set_lod_from_static_mesh(reuse_existing_material_slots=True)</code> 把临时件的 LOD0 拷到既有资产上，
最后删掉临时件。资产路径与所有引用都不动。</p>
"""),
    ("S5", "写进 BDF：四组标签", """
<p><code>tl_make_bdf.py</code> 复制 Epic 的 <code>CitySampleBuildingBDF_Asset_PCG</code> 成
<code>/Game/PCG/DataAssets/BDF/BDF_WithTL</code>，再追加 TL 行。<b>Epic 的源资产是只读的</b>——
它在 gitignore 里，没有版本回退。</p>
<p>写入路线是实测出来的：<code>UPCGDataAsset.data</code> / <code>FPCGDataPtrWrapper.data</code> 都是
<code>VisibleAnywhere</code>，Python 的 setter 会被 <code>CPF_EditConst</code> 挡掉。
可行的是 duplicate 之后去改副本自己的 <code>PCGPointData</code>，再 <code>save_asset</code>。</p>
<p>四组的含义：</p>
<ul>
<li><b>BDF</b>：每个样式一行，竖向语法、最小/最大墙宽与建筑高、屋顶参数。</li>
<li><b>Levels</b>：每个样式每层一行，包含 F0/F1/F2 三条横向语法与 FLengths（三档最小段长）。</li>
<li><b>Modules</b>：每个语法符号对应哪个 mesh、开间宽、是否可拉伸、有没有道具。</li>
<li><b>Props</b>：道具行，按 <code>ModuleName</code> 与模块行 JOIN，带相对变换、包围盒、概率与分组。</li>
</ul>
"""),
    ("S6", "注册进管线", """
<p>数据写好了，管线还看不见 TL。有三处在 TL 生成之前就会把它过滤掉，必须逐一填上：</p>
<ol>
<li><code>DT_Bldg_MinWidth</code> / <code>DT_Bldg_LevelMinWidth</code>：加 TL 行。
注意 <code>fill_from_csv_string</code> 是<b>整体替换</b>不是合并，所以要先 <code>export_to_csv_string</code> 出全部行再追加。
另外全部 27 个样式的 LV0 都用同一套角件画像（C_E / 40 / 200 / 280），TL 的 LV0 必须跟着它。</li>
<li><code>CitySampleBuildingBDF_NamesOnly_PCG</code>：这个列表把所有名字 JOIN 成一个字符串，再按“子串存在”判断样式是否可用。
不改它，TL 在任何地块上都会被静默丢弃。</li>
<li><code>PCG_3_3_1_Buildings</code> 的三处 <code>Assign_CitySampleBuildings</code> 分别在自己的
<code>subgraph_instance</code> 上重载了 <code>BuildingsStyles</code>，所以改子图默认值是没用的；TL 加进 Medium 那一档的 19 个码里。</li>
</ol>
<p>下面四个插件资产是被原地改过的（都在 gitignore 里），重同步插件会覆盖它们：
<code>PCG_3_3_1_Buildings</code>、<code>LoadCitySampleData</code>、<code>DT_Bldg_MinWidth</code>、<code>DT_Bldg_LevelMinWidth</code>。
改动前都在 <code>Saved/TL_backups/</code> 留了文件副本。</p>
"""),
    ("S7", "新建单体测试关系图", """
<p>城市那条链太长，改一次要跑全城。于是把 Epic 的单体示例
<code>Building_Staggered_LShape</code> 复制成 <code>/Game/PCG/TL/PCG_TL_Building_BDF</code>，
两处 Assign 的 <code>BuildingsStyles</code> 都改成 <code>"TL"</code>，
并打开 <code>Foundation</code>。L 形底面同时给出了一个内角，正好检验内角件。</p>
"""),
    ("S8", "新建展示关卡", """
<p><code>/Game/Map/Lvl_TL_Showcase</code> 从 <code>Template_Default</code> 新建，里面只有三样东西：
一块人行道材质的地面、一个 80 倍缩放的 PCGVolume（指向上面那张图）、以及模板自带的光照与大气。
PCGVolume 的笔刷本身是隐藏的，免得在文档截图里穿帮。</p>
<p>每次改完数据资产都要先 <code>pcg.FlushCache</code>：PCG 对子图结果的缓存是按设置做键的，
不看它加载的数据资产内容，不清缓存就会一直看到旧楼。</p>
"""),
    ("S9", "摆正立面道具", """
<p>道具第一次生成时全都躺倒、而且贴在墙里。原因有两个，都是量出来的：</p>
<ul>
<li><code>Rotator(pitch, yaw, roll)</code> 的参数顺序——原来把 (0, 0, 90) 当 yaw 传，实际落在了 roll 上。</li>
<li>每个道具 mesh 的朝向不同：灯、雨棚、空调、消防接口在各自局部 y=0 处安装、朝 +Y 伸出，
所以 TL 立面（+X）要用 <b>yaw −90</b>；竖招牌 <code>Sign_B01/E01</code> 在局部 x=0 处安装、朝 +X 伸出，保持 <b>yaw 0</b>。</li>
</ul>
<p>验证方式是先在关卡里摆四个已知朝向的测试墙片，读出每个道具正确的 yaw，再回头改表。</p>
"""),
    ("S10", "补完基础、道具、半角与屋顶", """
<p>四件事一起做掉：</p>
<ul>
<li><b>基础</b>：LV0 变成 TL 自己的一套（Foundation_01 / CornerEx_01 / CornerIn_01），
尺寸与枢轴照抄共用件的约定。基础语法是 <code>[FC][FS2]+[LC]</code>，段长除不尽时靠 FS2 拉伸收口——
FS2 若不可拉伸，转角处会留一个最多 2 m 的缺口（实测过 119 cm）。</li>
<li><b>道具</b>：13 个锚点写进 Props 组。三个坑：模块行要有 <code>HasProps=True</code>；
道具点自己的 transform 与 bounds 必须写在点上；<code>WindowHelper=True</code> 会把这一行从生成器那路引开。
还有一个坑是<b>转角</b>：管线只会把角件符号解成 <code>C_E</code>/<code>C_I</code>，从不使用 <code>C_CE</code>，
所以角件那块 mesh 的两行都要打上 <code>HasProps</code>，否则转角上的两块招牌和消防接口一个都不会生成。</li>
<li><b>半角件</b>：C_SL/C_SR/C_IL/C_IR 四件补齐，但没有任何样式的语法引用它们，属于备用件。</li>
<li><b>屋顶</b>：屋顶是管线按底面生成的平面动态网格，不是模块层。<code>RoofData.Y</code> 必须为负——
原来的 +10 让屋顶浮在檐口上方。</li>
</ul>
"""),
]


# --------------------------------------------------------------------------
# the page
# --------------------------------------------------------------------------
CSS = """
:root{--ink:#22313f;--mid:#5b6b7c;--line:#d8e0e8;--bg:#f6f8fa;--acc:#3f6d93}
*{box-sizing:border-box}
body{margin:0;background:#eef1f4;color:var(--ink);
 font:15px/1.75 "Segoe UI","PingFang SC","Microsoft YaHei",Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;background:#fff;box-shadow:0 0 24px rgba(0,0,0,.08)}
header.hero{position:relative;color:#fff}
header.hero img{width:100%;display:block}
header.hero .cap{position:absolute;left:0;right:0;bottom:0;padding:26px 34px 22px;
 background:linear-gradient(transparent,rgba(10,18,26,.82))}
header.hero h1{margin:0 0 6px;font-size:30px;letter-spacing:.5px}
header.hero p{margin:0;color:#dbe6ef;font-size:13.5px}
main{padding:26px 34px 60px}
h2{margin:46px 0 14px;font-size:22px;border-left:5px solid var(--acc);padding-left:12px}
h3{margin:30px 0 8px;font-size:17px}
h4{margin:22px 0 6px;font-size:14px;color:var(--mid);font-weight:600}
p{margin:9px 0}
code{background:#f0f3f6;border:1px solid #e0e6ec;border-radius:4px;padding:1px 5px;
 font:12.5px/1.5 Consolas,Menlo,monospace;color:#2c4050}
pre{background:#f2f5f8;border:1px solid var(--line);border-radius:8px;padding:14px 16px;
 overflow-x:auto;font:12.5px/1.7 Consolas,Menlo,monospace;color:#2c4050}
pre code{background:none;border:0;padding:0}
ul,ol{margin:8px 0 8px 22px;padding:0}
li{margin:4px 0}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:13px}
th,td{border:1px solid var(--line);padding:6px 9px;text-align:left;vertical-align:middle}
th{background:#f2f5f8;font-weight:600;color:#3b4b5b}
tr.lvstart td{border-top:2px solid #b9c8d6}
table.kit td.thumb{padding:2px;text-align:center;width:64px}
img.part{width:56px;height:56px;object-fit:contain;background:#fbfcfd;border-radius:4px}
figure{margin:16px 0}
figure img{width:100%;display:block;border-radius:6px;border:1px solid var(--line)}
figure figcaption{margin-top:6px;font-size:12.5px;color:var(--mid)}
.grid{display:grid;gap:14px}
.g2{grid-template-columns:1fr 1fr}
.g3{grid-template-columns:repeat(3,1fr)}
.muted{color:var(--mid);font-weight:400;font-size:12.5px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}
.stat{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px 14px}
.stat b{display:block;font-size:22px;color:var(--acc);line-height:1.2}
.stat span{font-size:12.5px;color:var(--mid)}
.step{border:1px solid var(--line);border-radius:10px;margin:18px 0;overflow:hidden}
.step>.head{display:flex;gap:12px;align-items:baseline;background:#f2f5f8;padding:11px 16px;
 border-bottom:1px solid var(--line)}
.step>.head .n{font-weight:700;color:var(--acc);font-size:13px;letter-spacing:.6px}
.step>.head .t{font-weight:600;font-size:16px}
.step>.body{padding:6px 16px 16px}
.strip{display:flex;align-items:stretch;gap:2px;margin:8px 0 4px;overflow-x:auto;
 background:#fbfcfd;border:1px solid var(--line);border-radius:6px;padding:8px}
.chip{flex:1;min-width:44px;height:56px;border-radius:4px;color:#fff;font-size:11.5px;
 display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;
 line-height:1.25;border:1px solid rgba(0,0,0,.12)}
.chip.dark{color:#22313f}
.chip .cm{font-size:9.5px;opacity:.85}
svg.diagram{display:block;width:100%;height:auto;background:#fbfcfd;border:1px solid var(--line);
 border-radius:8px;margin:14px 0}
.elevwrap{position:relative;margin:16px 0}
.elevwrap img{width:100%;display:block;border-radius:6px;border:1px solid var(--line)}
.elevwrap .band{position:absolute;border:1.5px dashed rgba(63,109,147,.75);border-radius:3px;
 pointer-events:none}
.elevwrap .bandbase{border:1.5px dashed rgba(120,120,120,.8)}
.elevwrap .band span{position:absolute;right:4px;top:3px;font-size:10.5px;color:#1d4a70;
 background:rgba(255,255,255,.86);padding:0 4px;border-radius:3px;white-space:nowrap}
.elevwrap .bay{position:absolute;width:1px;background:rgba(34,49,63,.25)}
.elevwrap .baylbl{position:absolute;transform:translateY(4px);font-size:9.5px;color:#2c4050;
 text-align:center;background:rgba(255,255,255,.85);border-radius:3px}
.note{background:#fff8e8;border:1px solid #e8d5a8;border-left:4px solid #d8a83c;
 border-radius:6px;padding:11px 15px;margin:14px 0;font-size:13.5px}
.note b{color:#8a6512}
.ok{background:#eef7f0;border:1px solid #bcdcc4;border-left:4px solid #5f9c72;
 border-radius:6px;padding:11px 15px;margin:14px 0;font-size:13.5px}
.ok b{color:#2f6b45}
.toc{columns:2;column-gap:26px;font-size:13.5px;background:var(--bg);border:1px solid var(--line);
 border-radius:8px;padding:14px 22px;margin:18px 0}
.toc a{color:var(--acc);text-decoration:none}
.toc a:hover{text-decoration:underline}
footer{padding:22px 34px 40px;color:var(--mid);font-size:12px;border-top:1px solid var(--line)}
@media(max-width:900px){.stats{grid-template-columns:repeat(2,1fr)}
 .g2,.g3{grid-template-columns:1fr}.toc{columns:1}}
"""

TOC = [
    ("s1", "1. 这是什么 / 关键数字"), ("s2", "2. 成果与资产清单"),
    ("s3", "3. 搭建步骤（十步）"), ("s4", "4. 套件：43 个部件"),
    ("s5", "5. 开间语法"), ("s6", "6. 建筑组装顺序"),
    ("s7", "7. PCG 关系图逻辑"), ("s8", "8. 基础 / 道具 / 屋顶"),
    ("s9", "9. 验证数据"), ("s10", "10. 脚本与文件"),
    ("s11", "11. 已知限制"),
]

ASSET_ROWS = [
    ("网格", "/Game/Building/TL/A/Kit_Bldg_TL_L0..L4_A/Mesh/", "43 个模块 mesh（+ 1 个 L4 拉伸变体）"),
    ("规则", "/Game/PCG/DataAssets/Buildings/TL/RULE_TL_L00..L04", "SGD 预览路线用的形状语法规则资产"),
    ("语法定义", "/Game/PCG/DataAssets/Buildings/TL/SGD_TL_A", "把五条规则绑成一套语法（城市路线不读它）"),
    ("数据", "/Game/PCG/DataAssets/BDF/BDF_WithTL", "BDF / Levels / Modules / Props 四组标签，TL 行追加在这里"),
    ("数据", "/Game/PCG/DataAssets/BDF/BDF_NamesOnly_WithTL", "样式名字列表的副本，加了 TL 才不会被静默过滤"),
    ("关系图", "/Game/PCG/TL/PCG_TL_Building_BDF", "单体测试图（Epic L 形示例的副本，只生成 TL）"),
    ("关卡", "/Game/Map/Lvl_TL_Showcase", "本文所有截图的关卡：地面 + 一个 PCGVolume"),
    ("材质", "/Game/Building/Material/MI/{Brick,Block,Paint}, MI_Bldg_Glass", "砖 / 石 / 金属 / 玻璃四个槽，复用 CitySample 现有材质"),
    ("道具", "/Game/Prop/BLDG/{Kit_Prop_Lamp, Kit_Prop_AC, B/Kit_Prop_BA, Kit_Prop_FirehoseConn}", "壁灯、空调、雨棚与招牌、消防接口"),
    ("屋顶材质", "/Game/Environment/RoofTop/Material/MI/MI_Rooftop_BitumenRoofing", "平面屋顶 mesh 的材质"),
    ("地面材质", "/Game/Road/Material/MI/MI_Sidewalk_Plaza_A", "展示关卡地面的铺装"),
    ("被改的插件资产", "PCG_3_3_1_Buildings / LoadCitySampleData / DT_Bldg_MinWidth / DT_Bldg_LevelMinWidth",
     "注册 TL 时原地修改的四份（都在 gitignore 里，重同步插件会覆盖）"),
]

BDF_ROWS = [
    ("VerticalGrammar", "[LV0][LV1][LV2]*[LV3][LV4]",
     "`*` 是可重复标记：LV2 标准层按建筑高度重复。没有可重复层的语法只能生成一个固定高度，会被所有地块拒绝。"),
    ("VerticalGrammarStaggered", "[LV2][LV2]*[LV3][LV4]",
     "错层体量叠在主体量之上，所以从 LV2 起，不从首层起（与 CHJ 一致）。"),
    ("MinWallWidth", "950 cm", "TL 自己最窄的 FLengths.x；比它更短的墙 TL 建不了。"),
    ("MinBldgHeight", "1600 cm", "不低于固定堆叠 500+300+300+120 = 1220 cm 再加一次 L2 重复（1520 cm）。"),
    ("MaxBldgHeight", "200000 cm",
     "作为匹配窗口被读取，不是描述性元数据；必须与 MinBldgHeight 不等——窗口宽度为 0 会让这个样式无法被选中。"),
    ("RoofData", "(X=20, Y=-50, Z=20, W=10)",
     "XYY → RoofOffset，ZWW → RoofInset。全部 27 个兄弟样式的 Y 都是负值（CHA 为 −140）；TL 原本写 +10，屋顶因此浮在檐口之上。"),
]

PROP_ROWS = [
    ("L1 Wall_01", "Group_Wall_1", "Awning_A01", "(2, 162.5, 355)", "yaw −90", "0.9", "70", "店面雨棚，压在石质腰线下"),
    ("L1 Wall_01", "Group_Wall_2", "Sign_E01", "(10, 22, 380)", "yaw 0", "1.0", "50", "开间边缘的招牌"),
    ("L1 Entrance_01", "Group_Door_1", "Lamp_Wall_A02 ×2", "(1, 14 / 311, 255)", "yaw −90", "1.0", "75", "门两侧的壁灯"),
    ("L1 Entrance_01", "Group_Door_2", "Sign_E01", "(10, 40, 380)", "yaw 0", "1.0", "85", "雨棚上方的招牌"),
    ("L1 Column_01", "Group_pillar_1", "Lamp_Wall_A02", "(18, 62.5, 250)", "yaw −90", "1.0", "65", "壁柱面壁灯"),
    ("L1 Column_01", "Group_pillar_2", "Sign_B01", "(18, 62.5, 330)", "yaw 0", "0.55", "25", "细长竖招牌"),
    ("L1 CornerEx_01", "Group_pillar_1", "Sign_B01（A 面）", "(1, 90, 280)", "yaw 0", "0.75", "60", "转角两面各一块"),
    ("L1 CornerEx_01", "Group_pillar_1", "Sign_B01（B 面）", "(−90, −1, 280)", "yaw −90", "0.75", "60", "同上，另一面"),
    ("L1 CornerEx_01", "Group_Misc_1", "FirehoseConn_Outlet_A01", "(1, 100, 50)", "yaw −90", "1.0", "45", "街面消防接口"),
    ("L2 Wall_01", "Group_WallUp", "AC_Window_A02", "(21, 162.5, 85)", "yaw −90", "1.0", "35", "窗台空调外机"),
    ("L3 Wall_01", "Group_WallUp", "AC_Window_A02", "(21, 162.5, 85)", "yaw −90", "1.0", "35", "同上"),
    ("L3 Entrance_01", "Group_WallUp", "AC_Window_A01", "(21, 162.5, 55)", "yaw −90", "1.0", "40", "特征窗上的外机（L2 那个窗有栏杆）"),
]

SCRIPT_ROWS = [
    ("Tools/tl_kit/tl_kit_spec.json", "43 个部件的唯一事实来源：层高、开间宽、材质槽、枢轴约定"),
    ("Tools/tl_kit/build_tl_kit.py", "Blender 5.2 无界面建模，每个部件一个 FBX"),
    ("Tools/tl_kit/kit_common.py", "横向语法、符号映射、可拉伸符号、基础层枢轴"),
    ("Tools/tl_kit/render_kit_catalog.py", "渲染 43 张部件缩略图与 5 张分层图"),
    ("Tools/tl_kit/render_elevation.py", "渲染立面图 + 轴测图，并输出每个模块的像素框"),
    ("Tools/tl_kit/make_guide_html.py", "生成本文档（图片全部 base64 内嵌）"),
    ("Content/Python/tl_kit_rebuild_meshes.py", "把 FBX 几何原地换进已有 mesh，保留资产路径与所有引用"),
    ("Content/Python/tl_make_rules.py", "生成 RULE_TL_L00..L04（SGD 路线的规则资产）"),
    ("Content/Python/tl_make_sgd.py", "生成 SGD_TL_A，把五条规则绑成一套形状语法定义"),
    ("Content/Python/tl_make_bdf.py", "把 TL 行追加进 BDF_WithTL 的 BDF / Levels / Modules / Props 四组"),
    ("Content/Python/tl_register.py", "DT_Bldg_MinWidth、DT_Bldg_LevelMinWidth 加 TL 行"),
    ("Content/Python/tl_names_with_tl.py", "把 TL 加进样式名字列表（NamesOnly 的副本）"),
    ("Content/Python/tl_whitelist_city.py", "把 TL 加进城市阶段的样式白名单（三处 Assign 的重载）"),
    ("Content/Python/tl_make_bdf_test_graph.py", "复制 Epic 的 L 形示例，做成只生成 TL 的单体测试图"),
    ("Content/Python/tl_showcase_setup.py", "在 Lvl_TL_Showcase 里搭地面与 PCGVolume 并触发生成"),
    ("Content/Python/tl_showcase_shot.py", "按类别显示/隐藏部件后排队高分辨率截图"),
    ("Content/Python/tl_showcase_read.py", "统计实例数、包围盒、各层 z 值与屋顶 mesh 范围"),
]

STEPS = [
    ("S1", "读清楚管线：BDF 才是入口", """
<p>先把 CitySample 的建筑生成链读一遍，而不是照着想象写数据。两条结论推翻了最初的假设：</p>
<ul>
<li><code>SGD_&lt;CODE&gt;_A</code> <b>不是</b>城市生成的入口。27 个 <code>SGD_*</code> 只被
<code>Bldg_SGD_level.umap</code> / <code>PCG_Bldg_SGD_test</code> 这条预览路线消费。真正跑城市的是
<code>PCG_3_3_1_Buildings</code> → <code>Assign_CitySampleBuildings</code> →
<code>LoadCitySampleData</code> → <code>CitySampleBuildingBDF_Asset_PCG</code>，按 <code>BuildingToken</code> 过滤；
整条链里 <code>SGD_</code> 出现 0 次。</li>
<li>那张 BDF 数据库<b>可以从 Python 重建/扩展</b>，它不是压缩 blob：
<code>UPCGDataAsset.data</code> 是 <code>BlueprintReadWrite FPCGDataCollection</code>，
里面有四个标签组（BDF / Levels / Modules / Props）。</li>
</ul>
<p>于是 TL 要走的路是：造一套网格 → 写一套 BDF 行 → 注册进管线 → 新建关卡验证。</p>
"""),
    ("S2", "定套件清单与语法", """
<p>先把“需要哪些 mesh”写成清单，再动 Blender。<code>tl_kit_spec.json</code> 是唯一事实来源：
5 个层高（L0 基础 / L1 首层 500 / L2 标准层 300 / L3 顶层 300 / L4 檐口 120 cm）、
每层的开间宽集合，以及 4 个材质槽。</p>
<p>横向语法每个层共用同一套，所以上下开间天然对齐：</p>
<p><code>F1 = [FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]</code></p>
<ul>
<li><code>[FC]</code>/<code>[LC]</code> 是首尾角件占位，<code>[A,B]</code> 表示 A、B 两件紧挨着成一组，<code>[X]+</code> 表示重复。</li>
<li><code>[WS1]</code>（Wall_02）是<b>可拉伸</b>的补长件：段长除不尽时由它吸收余量。</li>
<li>W1 / E1 / P1 在 L1–L4 上宽度相同（325 / 325 / 125 cm），于是壁柱永远压在壁柱上、特征窗永远压在入口上——这就是“开间对位”。</li>
</ul>
"""),
    ("S3", "Blender 建模 43 件", """
<p><code>build_tl_kit.py</code> 在 Blender 5.2 无界面模式下用轴对齐盒子建模，
<b>每个部件一个 FBX</b>，几何直接写在 UE 坐标系里。</p>
<p>枢轴约定是这套件能不能拼上的前提：原点在部件<b>底部</b>、墙面一端；
导入 UE 后一段墙沿局部 y ∈ [0, w]、z ∈ [0, h]，建筑外侧朝局部 <b>+X</b>
（实测自城市输出里 4,060 / 4,163 个实例）。</p>
<ul>
<li>外角 <code>CornerEx_01</code>：两翼从原点出发，一翼沿 +Y、一翼沿 −X，外表面在 x=+d 与 y=−d，每翼 1.5 m。</li>
<li>内角 <code>CornerIn_01</code>：两翼沿 +Y 与 +X，内角在原点。</li>
<li>L0 基础件挂在 z=0 以下（−250..0 cm），所以保留共用件的枢轴值，而不是门面层那套 (0, −w/2, −h/2)。</li>
</ul>
"""),
    ("S4", "导入 UE：原地换几何", """
<p>不能删除再导入：删除会把 <code>BDF_WithTL</code>、<code>RULE_TL_*</code> 和关卡里已生成实例的引用置空；
用旧 FBX 工厂覆盖导入又会把材质槽追加一遍。</p>
<p><code>tl_kit_rebuild_meshes.py</code> 的做法是：每个部件先导进临时目录，给两个 mesh 都刷上 spec 里的 4 个材质槽，
再用 <code>set_lod_from_static_mesh(reuse_existing_material_slots=True)</code> 把临时件的 LOD0 拷到既有资产上，
最后删掉临时件。资产路径与所有引用都不动。</p>
"""),
    ("S5", "写进 BDF：四组标签", """
<p><code>tl_make_bdf.py</code> 复制 Epic 的 <code>CitySampleBuildingBDF_Asset_PCG</code> 成
<code>/Game/PCG/DataAssets/BDF/BDF_WithTL</code>，再追加 TL 行。<b>Epic 的源资产全程只读</b>——
它在 gitignore 里，没有版本回退。</p>
<p>写入路线是实测出来的：<code>UPCGDataAsset.data</code> 与 <code>FPCGDataPtrWrapper.data</code> 都是
<code>VisibleAnywhere</code>，Python 的 setter 会被 <code>CPF_EditConst</code> 挡掉。
可行的是 duplicate 之后去改<b>副本自己的</b> <code>PCGPointData</code>，再 <code>save_asset</code> 落盘。</p>
<p>四组标签各管一段：</p>
<ul>
<li><b>BDF</b>：每个样式一行，竖向语法、最小/最大墙宽与建筑高、屋顶参数。</li>
<li><b>Levels</b>：每个样式每层一行，含 F0/F1/F2 三条横向语法与 FLengths（三档最小段长）。</li>
<li><b>Modules</b>：每个语法符号对应哪个 mesh、开间宽、是否可拉伸、有没有道具。</li>
<li><b>Props</b>：道具行，按 <code>ModuleName</code> 与模块行 JOIN，带相对变换、包围盒、概率与分组。</li>
</ul>
"""),
    ("S6", "注册进管线", """
<p>数据写好了，管线还看不见 TL。有三处在 TL 生成之前就会把它过滤掉，必须逐一填上：</p>
<ol>
<li><code>DT_Bldg_MinWidth</code> / <code>DT_Bldg_LevelMinWidth</code>：加 TL 行。
<code>fill_from_csv_string</code> 是<b>整体替换</b>不是合并，所以要先 <code>export_to_csv_string</code> 出全部行再追加。
另外全部 27 个样式的 LV0 都用同一套角件画像（C_E / 40 / 200 / 280），TL 的 LV0 必须跟着它。</li>
<li><code>CitySampleBuildingBDF_NamesOnly_PCG</code>：这个列表把所有名字 JOIN 成一个字符串，再按“子串是否存在”判断样式可用性。
不改它，TL 在任何地块上都会被静默丢弃，且没有任何日志。</li>
<li><code>PCG_3_3_1_Buildings</code> 的三处 <code>Assign_CitySampleBuildings</code> 分别在各自的
<code>subgraph_instance</code> 上重载了 <code>BuildingsStyles</code>，所以改子图默认值是没用的；
TL 加进 Medium 那一档的 19 个码里。</li>
</ol>
<div class="note"><b>四份被原地改过的插件资产</b>（都在 gitignore 里，重同步插件会覆盖）：
<code>PCG_3_3_1_Buildings</code>、<code>LoadCitySampleData</code>、<code>DT_Bldg_MinWidth</code>、<code>DT_Bldg_LevelMinWidth</code>。
改动前都在 <code>Saved/TL_backups/</code> 留了文件副本。</div>
"""),
    ("S7", "新建单体测试关系图", """
<p>城市那条链太长，改一次要跑全城。于是把 Epic 的单体示例 <code>Building_Staggered_LShape</code>
复制成 <code>/Game/PCG/TL/PCG_TL_Building_BDF</code>，两处 Assign 的 <code>BuildingsStyles</code> 都改成
<code>"TL"</code>，并打开 <code>Foundation</code>。L 形底面同时给出了一个内角，正好检验内角件。</p>
<p>注意这个副本是<b>唯一</b>会读 Props 组与 RoofData 的路线。项目原有的 <code>TL_Building_Volume</code> 走 SGD 路线，
既不读道具也不读屋顶参数——所以道具与屋顶只能在这张图上验证。</p>
"""),
    ("S8", "新建展示关卡", """
<p><code>/Game/Map/Lvl_TL_Showcase</code> 从 <code>Template_Default</code> 新建，里面只有三样东西：
一块人行道铺装的地面、一个 80 倍缩放的 PCGVolume（指向上面那张图）、以及模板自带的光照与大气。
PCGVolume 的笔刷本身被隐藏，免得在文档截图里穿帮。</p>
<p>每次改完数据资产都要先 <code>pcg.FlushCache</code>：PCG 对子图结果的缓存是按设置做键的，
不看它加载的数据资产内容，不清缓存就会一直看到旧楼。</p>
"""),
    ("S9", "摆正立面道具", """
<p>道具第一次生成时全都躺倒、而且贴在墙里。两个原因，都是量出来的：</p>
<ul>
<li><code>Rotator(pitch, yaw, roll)</code> 的参数顺序——原来把 (0, 0, 90) 当 yaw 传，实际落在了 roll 上。</li>
<li>每个道具 mesh 的安装朝向不同：灯、雨棚、空调、消防接口在各自局部 y=0 处安装、朝 +Y 伸出，
所以 TL 立面（+X）要用 <b>yaw −90</b>；竖招牌 <code>Sign_B01/E01</code> 在局部 x=0 处安装、朝 +X 伸出，保持 <b>yaw 0</b>。</li>
</ul>
<p>验证方式是先在关卡里摆四片已知朝向的测试墙、把每个道具按 0/90/180/−90 各放一份，读出正确的 yaw，再回头改表。</p>
"""),
    ("S10", "补完基础、道具、半角与屋顶", """
<p>四件事一起做掉：</p>
<ul>
<li><b>基础</b>：LV0 换成 TL 自己的一套（Foundation_01 / CornerEx_01 / CornerIn_01），
尺寸与枢轴照抄共用件的约定。基础语法是 <code>[FC][FS2]+[LC]</code>，段长除不尽时靠 FS2 拉伸收口——
FS2 若不可拉伸，转角处会留一个最多 2 m 的缺口（实测 119 cm）。</li>
<li><b>道具</b>：13 个锚点写进 Props 组。三个坑：模块行要有 <code>HasProps=True</code>；
道具点自己的 transform 与 bounds 必须写在点上；<code>WindowHelper=True</code> 会把这一行从生成器那一路引开。
还有一个坑在<b>转角</b>：管线只会把角件符号解成 <code>C_E</code>/<code>C_I</code>，从不使用 <code>C_CE</code>，
所以角件 mesh 的两行都要打 <code>HasProps</code>，否则转角上的两块招牌与消防接口一个都不会生成。</li>
<li><b>半角件</b>：C_SL/C_SR/C_IL/C_IR 四件补齐并注册，但没有任何样式的语法引用它们，属于备用件。</li>
<li><b>屋顶</b>：屋顶是管线按屋面轮廓生成的平面动态网格，不是模块层。<code>RoofData.Y</code> 必须为负——
原来的 +10 让屋顶浮在檐口上方。</li>
</ul>
"""),
]

STEP_EVIDENCE = [
    ("S1", "管线读图结论", "SGD_ 在城市链里出现 0 次；BDF 资产是四个标签组，不是 blob"),
    ("S2", "tl_kit_spec.json + kit_common.py", "43 件、5 层、开间宽 150/325/125 cm；自检 15 项通过"),
    ("S3", "43 个 FBX", "每件一个 FBX（LOD0），材质槽 4 个"),
    ("S4", "43 个原地替换的 mesh", "资产路径不变、引用不丢；材质槽不重复追加"),
    ("S5", "BDF_WithTL", "BDF 27→28、Levels 240→245、Modules 2916→2964、Props 1966→1979；Epic 源文件字节数与 mtime 不变"),
    ("S6", "两处 DataTable + 名字列表 + 城市白名单", "TL 出现在 DT_Bldg_MinWidth 行、19 码白名单与名字列表里"),
    ("S7", "PCG_TL_Building_BDF", "两处 Assign 的 BuildingsStyles=TL、Foundation=True"),
    ("S8", "Lvl_TL_Showcase", "1,562 模块 / 296 道具 / 25 屋顶设备；包围盒 ±3,021 × 5,549 cm"),
    ("S9", "13 行 Props 表", "灯/雨棚/空调/接口 yaw −90，招牌 yaw 0"),
    ("S10", "基础 + 道具 + 半角 + 屋顶", "基础缺口 119 cm → 0（FS2 拉伸 1.02–1.04 倍）；转角招牌 0 → 3 块"),
]

VERIFY_ROWS = [
    ("展示关卡墙面模块", "1,562 个实例，跨 25 种 TL mesh"),
    ("各层实例", "L00 120 · L01 80 · L02 1,054 · L03 154 · L04 154"),
    ("立面道具", "296 个：空调 230 · 招牌 25 · 壁灯 20 · 雨棚 19 · 消防接口 2"),
    ("屋顶设备", "25 个，来自 14 种 Rooftop_* 组合"),
    ("建筑包围盒", "x/y ±3,021 cm，z 0.25 – 5,549 cm（约 30 × 30 × 55 m）"),
    ("层顶高度", "L1 从 0 起；主层屋面 1,770；第二层体量 1,770–5,070；L4 檐口 5,370"),
    ("平面屋顶 mesh", "z 1,770.5 – 5,441.5，覆盖两片屋面轮廓"),
    ("开间对位", "100%——W1/E1/P1 在 L1–L4 同宽，壁柱压壁柱、特征窗压入口"),
    ("城市阶段 TL 实例", "6,872 个模块 + 1,042 个基础件，与 CH/SF/NY/QB 同场生成（提交 4033346 时测得）"),
    ("模块接缝吻合率", "TL 90.9%（CHA 参照值 83.7%）"),
    ("套件自检", "Tools/tl_kit/test_kit_spec.py 15 项全过"),
]

MESH_ROWS = [
    ("L00", "Foundation_01 ×114 · CornerEx_01 ×5 · CornerIn_01 ×1"),
    ("L01", "Wall_01 ×40 · Wall_02 ×8 · Column_01 ×14 · Entrance_01 ×12 · CornerEx_01 ×5 · CornerIn_01 ×1"),
    ("L02", "Wall_01 ×494 · Wall_02 ×112 · Column_01 ×196 · Entrance_01 ×168 · CornerEx_01 ×70 · CornerIn_01 ×14"),
    ("L03", "Wall_01 ×74 · Wall_02 ×16 · Column_01 ×28 · Entrance_01 ×24 · CornerEx_01 ×10 · CornerIn_01 ×2"),
    ("L04", "Wall_01 ×114 · Column_01 ×28 · CornerEx_01 ×10 · CornerIn_01 ×2"),
]

LIMITS = [
    "<b>半角件是备用件。</b> C_SL / C_SR / C_IL / C_IR 四件已造好并注册进 Modules 组，"
    "但 27 个样式的语法里没有一个引用它们，所以永远不会被放置。",
    "<b>L4 檐口没有独立补长件。</b> 该层复用 Wall_01 作为可拉伸符号（Modules 行写成 "
    "<code>..._Wall_01_N1_WS</code>），所以檐口被拉伸时石带跟着变长，而不是多出一块。",
    "<b>道具是概率的。</b> 每行都有 Probability，每个模块实例上的每个分组各自抽取，"
    "所以并不是每个开间都挂着同样的道具；想换一种分布只能改 Assign 的 Seed。",
    "<b>L2 特征窗不放空调。</b> 它有阳台栏杆挡着，空调只挂在 L3 的特征窗上。",
    "<b>被改的四份插件资产要手工复原。</b> 插件重同步会覆盖它们；"
    "重新执行 <code>tl_register.py</code> → <code>tl_names_with_tl.py {\"apply\": true}</code> → "
    "<code>tl_whitelist_city.py {\"apply\": true}</code> 即可，备份在 <code>Saved/TL_backups/</code>。",
    "<b>城市阶段最近一次改动后没有重跑。</b> FS2 可拉伸与转角道具这两处改动只验证了单体路线（本文关卡），全城重跑未做。",
    "<b><code>Content/Map/</code> 在 gitignore 里。</b> <code>Lvl_TL_Showcase</code> 与 "
    "<code>Lvl_TL_Building</code> 不随仓库走，换机器要重建。",
]


def page():
    h = []
    a = h.append
    a('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">')
    a('<meta name="viewport" content="width=device-width,initial-scale=1">')
    a('<title>TL 风格 PCG 建筑 —— 从 Blender 套件到生成结果</title>')
    a('<style>%s</style></head><body><div class="wrap">' % CSS)

    a('<header class="hero"><img src="data:image/jpeg;base64,%s">' %
      b64(os.path.join(SHOTS, "sc_hero_final2.png"), 1600, 80))
    a('<div class="cap"><h1>TL 风格 PCG 建筑：从 Blender 套件到生成结果</h1>'
      '<p>关卡 <code>/Game/Map/Lvl_TL_Showcase</code> · 关系图 '
      '<code>/Game/PCG/TL/PCG_TL_Building_BDF</code> · 数据 '
      '<code>/Game/PCG/DataAssets/BDF/BDF_WithTL</code> · 2026-10-09</p></div></header>')

    a('<main>')
    a('<div class="toc">' + "".join('<div><a href="#%s">%s</a></div>' % (i, t) for i, t in TOC) + '</div>')

    # ---------------- 1 ----------------
    a('<h2 id="s1">1. 这是什么</h2>')
    a('<p>TL 是这个项目里新增的一种 CitySample 建筑样式码。它由一套自建的 Blender 模块化套件（43 个部件）、'
      '一套横向开间语法、一张写进 <code>BDF_WithTL</code> 的数据表，以及一条 PCG 关系图组成。'
      '本文记录它是怎么一步步搭起来的、用到哪些资产、每个资产干什么，以及整栋建筑是如何拼装的。</p>')
    a('<p>展示关卡里只有一台 PCGVolume。它一生成，就产出下面这些数量：</p>')
    a('<div class="stats">'
      '<div class="stat"><b>43</b><span>Blender 套件部件</span></div>'
      '<div class="stat"><b>5</b><span>层高（含地坪以下基础）</span></div>'
      '<div class="stat"><b>1,562</b><span>展示关卡墙面模块</span></div>'
      '<div class="stat"><b>296</b><span>立面道具实例</span></div>'
      '<div class="stat"><b>5,549 cm</b><span>建筑总高</span></div>'
      '<div class="stat"><b>100%</b><span>上下层开间对位</span></div>'
      '<div class="stat"><b>90.9%</b><span>模块接缝吻合（CHA 83.7%）</span></div>'
      '<div class="stat"><b>6,872</b><span>城市阶段 TL 模块</span></div>'
      '</div>')
    a('<div class="ok"><b>一句话。</b> 一套 43 件的 Blender 套件 + 一张四组标签的数据表，'
      '让 CitySample 原有的 BDF 建筑管线把 TL 当成第 28 种建筑样式生成出来——'
      '墙面、基础、立面道具、平面屋顶与屋顶设备全由管线自动摆好，人工只提供部件和数据。</div>')

    # ---------------- 2 ----------------
    a('<h2 id="s2">2. 成果与资产清单</h2>')
    a('<p>最终成果在关卡 <code>/Game/Map/Lvl_TL_Showcase</code>：只有一块地面和一个 PCGVolume，'
      '生成出下面的建筑。这是这条链上涉及的全部资产。</p>')
    a('<table><thead><tr><th>类别</th><th>资产</th><th>用途</th></tr></thead><tbody>')
    for c, p, u in ASSET_ROWS:
        a('<tr><td>%s</td><td><code>%s</code></td><td>%s</td></tr>' % (c, p, u))
    a('</tbody></table>')
    a('<div class="grid g2">')
    a(shot("sc_p9_noprops", "只看建筑本体：管线按数据表拼出来的全部立面模块（道具与屋顶设备已隐藏）。", 1000, 74, True))
    a(shot("sc_s8_props2", "同一栋楼带上立面道具：雨棚、壁灯、招牌、空调外机。", 1000, 74, True))
    a('</div>')

    # ---------------- 3 ----------------
    a('<h2 id="s3">3. 搭建步骤（十步）</h2>')
    for n, t, body in STEPS:
        a('<div class="step"><div class="head"><span class="n">%s</span><span class="t">%s</span></div>'
          '<div class="body">%s</div></div>' % (n, t, body.strip()))
    a('<h3>步骤产出与验证数字</h3>')
    a('<table><thead><tr><th>步骤</th><th>产物</th><th>验证</th></tr></thead><tbody>')
    for n, prod, ev in STEP_EVIDENCE:
        a('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (n, prod, ev))
    a('</tbody></table>')

    # ---------------- 4 ----------------
    a('<h2 id="s4">4. 套件：43 个部件</h2>')
    a('<p>风格是砖砌商业街块：红砖墙、石灰石首层基座与腰线、黑漆窗框、玻璃。'
      '全部用轴对齐盒子建模，每个部件一个 FBX，几何直接写在 UE 坐标系里。</p>')
    a('<h3>五层划分</h3>')
    a('<div class="grid g2">')
    a(kitimg("level_L00", "L0 基础：地坪以下 250 cm，基础条 + 外角 + 内角三件。", 1000, 74))
    a(kitimg("level_L01", "L1 首层 500 cm：店面、入口、壁柱、外角/内角与两件备用半角。", 1000, 74))
    a(kitimg("level_L02", "L2 标准层 300 cm：窗、细壁柱，按高度重复。", 1000, 74))
    a(kitimg("level_L03", "L3 顶层 300 cm：重窗楣与檐带的窗。", 1000, 74))
    a(kitimg("level_L04", "L4 檐口 120 cm：檐口带 + 檐口壁柱 + 角件（topper）。", 1000, 74))
    a(kitimg("axo_stack", "轴测：L1–L4 一个完整堆叠，另一侧立面正在转过转角。", 1000, 74))
    a('</div>')
    a('<h3>部件清单</h3>')
    a(kit_table())
    a('<div class="note"><b>关于枢轴。</b> 原点在部件底部、墙面一端，建筑外侧朝局部 +X。'
      'BDF 路线给每个模块加 PivotOffset (0, −w/2, −h/2) 把原点挪到开间中心；'
      'L0 基础件挂在 z=0 以下，保留共用件的枢轴值（FS2 为 0，C_E 为 −20.17，C_I 为 −4.93）。</div>')

    # ---------------- 5 ----------------
    a('<h2 id="s5">5. 开间语法</h2>')
    a('<p>横向语法决定一段墙由哪些部件、按什么顺序拼成。三个记号：<code>[X]</code> 放一件，'
      '<code>[X,Y]</code> 两件紧挨着成一组，<code>[X]+</code> 重复；<code>[FC]</code>/<code>[LC]</code> 是首尾角件占位。</p>')
    a('<p><code>F1 = %s</code></p>' % kit_common.GRAMMAR_F1)
    a(grammar_strip(F1_SEQ))
    a('<p class="muted">上面是按部件宽度画出的“一个 + 只展开一次”的理想顺序，用它看部件之间的关系；'
      '真实建筑上 <code>+</code> 会重复到段长用完为止。下面是生成结果里读出的真实顺序。</p>')
    a('<h3>立面图（L1–L4 同一段 F1，逐件标注）</h3>')
    a(elevation_overlay())
    a('<div class="note"><b>开间对位是怎么来的。</b> W1、E1、P1 在 L1–L4 上宽度完全相同'
      '（325 / 325 / 125 cm），所以同一段 F1 在四层上逐件对齐：壁柱永远压在壁柱上，'
      '特征窗永远压在入口上（L4 把 E1 换成 W1）。改任何一个部件的宽度都会破坏这个对齐。</div>')
    a('<h3>三条语法与三档最小段长</h3>')
    a('<table><thead><tr><th></th><th>F0（短段）</th><th>F1（中段）</th><th>F2（长段）</th></tr>'
      '<tbody><tr><td>语法</td><td><code>%s</code></td><td><code>%s</code></td><td><code>%s</code></td></tr>'
      '<tr><td>最小段长</td><td>%g cm</td><td>%g cm</td><td>%g cm</td></tr></tbody></table>'
      % (kit_common.GRAMMAR_F0, kit_common.GRAMMAR_F1, kit_common.GRAMMAR_F2,
         kit_common.FLENGTHS_CM[0], kit_common.FLENGTHS_CM[1], kit_common.FLENGTHS_CM[2]))
    a('<p>管线按段长从 FLengths 里挑一条：段短用 F0，中段用 F1，长段用 F2。'
      '竖向语法则决定这些层怎么叠，其中 <code>[LV2]*</code> 是标准层，按建筑高度重复若干次。</p>')
    a('<h3>竖向语法与屋顶参数（BDF 行）</h3>')
    a('<table><thead><tr><th>字段</th><th>值</th><th>说明</th></tr></thead><tbody>')
    for k, v, why in BDF_ROWS:
        a('<tr><td><code>%s</code></td><td><code>%s</code></td><td>%s</td></tr>' % (k, v, why))
    a('</tbody></table>')

    # ---------------- 6 ----------------
    a('<h2 id="s6">6. 建筑组装顺序</h2>')
    a('<p>下面七张图是同一栋楼一层一层把部件显示出来的结果，顺序就是真正的组装顺序。'
      '前四张是同一个低机位；后三张换到高机位，才看得到檐口与屋面。</p>')
    a('<div class="grid g2">')
    for n, c in [
        ("sc_s1_found", "① 只显示 L0 基础。基础在地坪以下，所以把地面隐藏掉才看得到；它沿两片屋面轮廓各跑一圈。"),
        ("sc_s2_l1", "② 加上 L1 首层：店面玻璃与入口沿街面排开，转角是石砌隅石。"),
        ("sc_s3_l2", "③ 加上 L2 标准层：从这一层起建筑分成两段体量，第二段轮廓缩进 240 cm，并按高度重复 L2。"),
        ("sc_s4_l3", "④ 加上 L3 顶层：窗楣更重的窗与檐带，两段体量各一层。"),
    ]:
        a(shot(n, c, 1000, 74, True))
    a('</div>')
    a('<div class="grid g3">')
    for n, c in [
        ("sc_a5_l4", "⑤ 加上 L4 檐口：120 cm 的檐口带 + 檐口壁柱压顶。此时屋面还是空的。"),
        ("sc_a6_roof", "⑥ 加上屋顶：管线按屋面轮廓生成的平面动态网格（沥青卷材）。"),
        ("sc_a7_rooftop", "⑦ 加上屋顶设备：14 种 Rooftop_* 组合按可用面积填充。"),
    ]:
        a(shot(n, c, 860, 74, True))
    a('</div>')
    a('<h3>俯视：两片屋面轮廓</h3>')
    a(shot("sc_top_full", "正上方俯视。建筑是 L 形：主层体量缩进 240 cm 后成为第二层，"
                          "所以有上下两片屋面，屋顶平面网格也是两块。", 1200, 76))

    # ---------------- 7 ----------------
    a('<h2 id="s7">7. PCG 关系图逻辑</h2>')
    a('<h3>顶层：<code>PCG_TL_Building_BDF</code></h3>')
    a(graph_top_svg())
    a('<p>左边一列负责“造底面”：两个 <code>Create_Spline_Shape</code> 分别在 6000×3000 与 3000×6000 cm 上生成矩形，'
      '各自对齐到最小边，再由 <code>Compose_Areas_Union</code> 合成 L 形，'
      '经过 <code>FilterDataByType → GetSplineControlPoints → CreateSpline → CleanSpline</code> 变成一条闭合折线。</p>')
    a('<p>这条折线同时交给两处 <code>Assign_CitySampleBuildings</code>：'
      '第一处（AssignBase）用 <code>BaseLayerHeight</code> 作为最小/最大高度、<code>Staggered=False</code>、'
      '<code>Foundation=True</code>；它的 <b>Rooftops Footprints</b> 输出缩进 240 cm 后交给第二处（AssignSecond），'
      '高度用 <code>SecondLayerHeight</code>、<code>Staggered=True</code>。两处的 <code>BuildingsStyles</code> 都重载成 <code>"TL"</code>。</p>')
    a('<p>屋顶分两路：两处 Assign 的屋面轮廓都进 <code>Create_Mesh_Planar</code> 生成平面网格；'
      '只有第二处（最高那片屋面）再进 <code>Fill_Areas_WithFittingAssets</code> 摆屋顶设备。</p>')
    a('<h3>BDF 链内部</h3>')
    a(graph_bdf_svg())
    a('<p><code>Assign_CitySampleBuildings</code> 自己只是个壳：它的 <code>CoreProcess</code> 先把样式码与 BDF 数据 JOIN 起来，'
      '按 <code>BuildingToken</code> 过滤出 TL 那几行，再交给 <code>BDF_Input_Processor</code>。'
      '后者读 BDF 行（竖向语法、屋顶参数）与 Levels 行（每层语法、最小段长），'
      '按输入的每条轮廓 <code>PartitionBDF_PerSpline</code> 分一份，每份再进 <code>BDF_BuildingFromSpline</code>。</p>')
    a('<p><code>BDF_BuildingFromSpline</code> 有 217 个节点，按上图的 8 步执行。'
      'TL 数据表里的每一组都在某一步被读到：BDF 行在第 1、8 步，Levels 行在第 1、4 步，'
      'Modules 行在第 3–6 步，Props 行在第 6、7 步。任何一组漏写，对应那一步就静默产出空结果。</p>')
    a('<div class="note"><b>为什么 <code>*</code> 是必需的。</b> 竖向语法里必须有一个可重复的层。'
      '只能生成固定高度的样式，匹配窗口宽度为 0，会被所有地块拒绝——TL 早期正是因此全线零实例，而且没有任何报错。</div>')

    # ---------------- 8 ----------------
    a('<h2 id="s8">8. 基础 / 道具 / 屋顶</h2>')
    a('<h3>基础（L0）</h3>')
    a('<div class="grid g2">')
    a(shot("sc_found_corner_a", "修复前：基础语法端头收不住，转角处留下缺口。", 1000, 74, True))
    a(shot("sc_found_corner_b", "修复后：把 FS2 标成可拉伸，段尾由它吸收余量（1.02–1.04 倍），转角闭合。", 1000, 74, True))
    a('</div>')
    a('<p>基础语法是 <code>[FC][FS2]+[LC]</code>；LV0 在语法里只有 0.5 cm 高（与所有兄弟样式一致），'
      '真正的几何挂在地面以下 250 cm。转角件用共用件的枢轴值：FS2 为 0，C_E 为 −20.174，C_I 为 −4.926。</p>')
    a('<h3>立面道具</h3>')
    a(shot("sc_p10_corner", "转角：两块竖招牌各朝一面街，下面一个消防接口；首层墙面是壁灯与雨棚。", 1200, 76))
    a('<div class="grid g2">')
    a(shot("sc_p6_props", "沿街看店面：雨棚压在石质腰线下，壁灯在柱面，招牌在开间边缘。", 1000, 74, True))
    a(shot("sc_p7_shop", "近看首层：玻璃分格、石基座、转角隅石与壁灯照明。", 1000, 74, True))
    a('</div>')
    a('<p>道具不是另外摆的模型，而是数据表里的一行行记录：每行写出<b>哪个模块</b>'
      '（<code>ModuleName</code>，与 Modules 组 JOIN）、<b>挂在什么分组</b>'
      '（<code>PropGroup</code>，同组多行会一起被抽中或一起不出现）、'
      '<b>相对该模块的变换</b>、<b>概率</b>，以及要不要走生成器（<code>WindowHelper</code>/<code>Decal</code>）。</p>')
    a('<table><thead><tr><th>模块</th><th>分组</th><th>道具</th><th>局部位置 (x,y,z) cm</th>'
      '<th>朝向</th><th>缩放</th><th>概率</th><th>说明</th></tr></thead><tbody>')
    for r in PROP_ROWS:
        a('<tr><td>%s</td><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % r)
    a('</tbody></table>')
    a('<div class="note"><b>转角的坑。</b> 管线的角件解析只会产出 <code>C_E</code> / <code>C_I</code> 两个符号，'
      '从不使用 <code>C_CE</code>；而 TL 角件 mesh 的 C_CE 行与 C_E 行指向同一个 mesh。'
      '只给 C_CE 行打 <code>HasProps</code> 时，转角上的道具一块都不会生成。两行都要打上。</div>')
    a('<h3>屋顶</h3>')
    a('<p class="muted">屋顶的效果见第 6 节第 ⑥、⑦ 张图与俯视图。</p>')
    a('<p>屋顶水位由 <code>RoofData</code> 控制：<code>XYY</code> 复制到 <code>RoofOffset</code>，'
      '<code>ZWW</code> 复制到 <code>RoofInset</code>，屋面高度取 <code>MaxHeight + RoofOffset.Y</code>。'
      'TL 用的是 (20, −50, 20, 10)：Y 为负表示屋面比最高模块略低一点、坐进檐口里——'
      '所有 27 个兄弟样式的 Y 都是负值，原来的 +10 让屋顶浮在檐口之上。</p>')
    a('<h3>细节</h3>')
    a('<div class="grid g3">')
    a(shot("sc_d_bays", "开间对位：上下层的壁柱与窗洞逐件对齐。", 860, 74, True))
    a(shot("sc_d_corner3", "转角：外角件两翼各沿一个方向，隅石逐层错缝。", 860, 74, True))
    a(shot("sc_d_inner2", "内角：两翼沿 +Y 与 +X，内角在原点，正好补上 L 形底面的凹角。", 860, 74, True))
    a('</div>')
    a(shot("sc_p8_awning", "首层街道视角：一层是连续店面，二层以上是砖墙开窗。", 1200, 76))

    # ---------------- 9 ----------------
    a('<h2 id="s9">9. 验证数据</h2>')
    a('<p>下面每组数字都是在编辑器里读生成结果得到的，不是估算。</p>')
    a('<table><thead><tr><th>项目</th><th>数值</th></tr></thead><tbody>')
    for k, v in VERIFY_ROWS:
        a('<tr><td>%s</td><td>%s</td></tr>' % (k, v))
    a('</tbody></table>')
    a('<h3>模块实例明细（展示关卡）</h3>')
    a('<table><thead><tr><th>层</th><th>部件</th></tr></thead><tbody>')
    for k, v in MESH_ROWS:
        a('<tr><td>%s</td><td>%s</td></tr>' % (k, v))
    a('</tbody></table>')
    a('<h3>真实的下层立面序列（从生成结果逐件读出）</h3>')
    a(facade_strip("L01", "(0, -1)|-3000", "首层 −Y 立面（长边：一端是外角，两处补长件被拉伸）"))
    a(facade_strip("L01", "(1, 0)|3000", "首层 +X 立面（短边：段长不够 F1，用 F0）"))
    a('<p class="muted">可以看到 <code>Wall_02</code> 在两端分别被拉伸到 1.42 倍和 1.31 倍——'
      '这正是可拉伸补长件的作用：段长除不尽时由它吸收余量，而不是在角上留缝。</p>')

    # ---------------- 10 ----------------
    a('<h2 id="s10">10. 脚本与文件</h2>')
    a('<p>整条流水线都是脚本，可以重跑。脚本分两部分：<code>Tools/tl_kit/</code> 是 Blender 侧与文档侧，'
      '<code>Content/Python/</code> 是编辑器侧（MCP 桥只允许执行这个目录下的脚本）。</p>')
    a('<table><thead><tr><th>脚本</th><th>作用</th></tr></thead><tbody>')
    for k, v in SCRIPT_ROWS:
        a('<tr><td><code>%s</code></td><td>%s</td></tr>' % (k, v))
    a('</tbody></table>')
    a('<h3>重跑顺序</h3>')
    a('<pre><code># 1) Blender 侧：建模 + 渲染图鉴 / 立面图\n'
      'blender -b --factory-startup -P Tools/tl_kit/build_tl_kit.py -- \\\n'
      '    --spec Tools/tl_kit/tl_kit_spec.json --out E:/Blender/TL_Kit\n'
      'blender -b --factory-startup -P Tools/tl_kit/render_kit_catalog.py\n'
      'blender -b --factory-startup -P Tools/tl_kit/render_elevation.py -- \\\n'
      '    --spec Tools/tl_kit/tl_kit_spec.json --out E:/PCG_Claude/Saved/kit_catalog\n\n'
      '# 2) 套件自检\n'
      '.\\mcp_server\\.venv\\Scripts\\python.exe -m pytest Tools/tl_kit/test_kit_spec.py -q\n\n'
      '# 3) 编辑器侧（通过 run_unreal_script 逐个执行）\n'
      '#    tl_kit_rebuild_meshes.py -> tl_make_rules.py -> tl_make_sgd.py\n'
      '#    -> tl_make_bdf.py -> tl_register.py\n'
      '#    -> tl_names_with_tl.py {"apply": true} -> tl_whitelist_city.py {"apply": true}\n\n'
      '# 4) 展示关卡\n'
      '#    tl_make_bdf_test_graph.py -> tl_place_bdf_volume.py -> tl_showcase_setup.py\n'
      '#    -> tl_showcase_read.py（读数字）-> tl_showcase_shot.py（出图）\n\n'
      '# 5) 本文件\n'
      'python Tools/tl_kit/make_guide_html.py</code></pre>')

    # ---------------- 11 ----------------
    a('<h2 id="s11">11. 已知限制</h2>')
    a('<ul>')
    for t in LIMITS:
        a('<li>%s</li>' % t)
    a('</ul>')

    a('</main>')
    a('<footer>TL building style · 关卡 <code>Lvl_TL_Showcase</code> · '
      '本文件由 <code>Tools/tl_kit/make_guide_html.py</code> 生成，全部图片以 base64 内嵌，单文件可直接分享。</footer>')
    a('</div></body></html>')
    return "".join(h)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    html = page()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote %s  (%.2f MB, %d embedded images)"
          % (OUT, len(html.encode("utf-8")) / 1048576.0,
             html.count("data:image/jpeg;base64,")))


main()
