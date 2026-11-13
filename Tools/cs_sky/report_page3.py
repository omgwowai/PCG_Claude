"""Report sections 8-9: the blocky cloud shadows on the water (cause, verification, fixes) and god rays (physics and
the UE 5.8 implementation). Figures come from the editor A/B screenshots and from the captures' cloud shadow maps:
rdc_v2 = the capture before the fix, rdc_noldo = the fix without LightDistanceOverride, rdc = the final capture."""
import glob
import json
import os
import statistics

import numpy as np
from PIL import Image, ImageFilter

from build_report import esc, fig
from report_images import RDC_V2, ROOT, dumped, fit, grid, load, to_img
from decode_tex import srgb

SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "WindowsEditor")
DBG = os.path.join(ROOT, "Saved", "Reports", "cs_weather", "shadow_dbg")
REP = os.path.join(ROOT, "Saved", "Reports", "cs_weather")
TEX_V2 = os.path.join(RDC_V2, "tex")
TEX_NOLDO = os.path.join(REP, "rdc_noldo", "tex")


def _gpu(folder, pattern, name="CloudShadow"):
    vals = []
    for f in sorted(glob.glob(os.path.join(REP, folder, pattern))):
        with open(f, encoding="utf-8") as fh:
            for r in json.load(fh)["rows"]:
                if r["name"] == name:
                    vals.append(r["incl_ms"])
                    break
    return statistics.median(vals) if vals else float("nan")


def _shot(name):
    return Image.open(os.path.join(SHOTS, name + ".png")).convert("RGB")


def _lin(img):
    a = np.asarray(img).astype(np.float32) / 255.0
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def _bilinear_up(a, factor):
    """Bilinear upscale of a 2D float array (texel centres aligned, like a GPU sampler)."""
    h, w = a.shape
    ys = (np.arange(h * factor) + 0.5) / factor - 0.5
    xs = (np.arange(w * factor) + 0.5) / factor - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, h - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, w - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    x1 = np.clip(x0 + 1, 0, w - 1)
    fy = np.clip(ys - np.floor(ys), 0, 1)[:, None]
    fx = np.clip(xs - np.floor(xs), 0, 1)[None, :]
    top = a[y0][:, x0] * (1 - fx) + a[y0][:, x1] * fx
    bot = a[y1][:, x0] * (1 - fx) + a[y1][:, x1] * fx
    return top * (1 - fy) + bot * fy


def figures():
    F = {}
    # --- the artifact, zoomed (baseline A) next to the fix (D), same crop
    box = (820, 300, 1340, 720)
    a = _shot("csdbg_A_extent40").crop(box)
    d = _shot("csdbg_D_extent10_nofilter").crop(box)
    F["zoom"] = grid([a.resize((a.size[0] * 3 // 2, a.size[1] * 3 // 2), Image.NEAREST),
                      d.resize((d.size[0] * 3 // 2, d.size[1] * 3 // 2), Image.NEAREST)], 2,
                     ["原设置：纹素 78 m（直边、台阶）", "修复后：纹素 9.8 m"])
    # --- four configurations on the water view
    crop = (0, 250, 1600, 780)
    cfg = [("csdbg_A_extent40", "A 原设置：半径 40 km + 滤波 1 → 78 m"),
           ("csdbg_C_extent40_nofilter", "C 半径 40 km + 滤波 0 → 39 m"),
           ("csdbg_B_extent10", "B 半径 10 km + 滤波 1 → 19.5 m"),
           ("csdbg_D_extent10_nofilter", "D 半径 10 km + 滤波 0 → 9.8 m（推荐）")]
    F["abcd"] = grid([fit(_shot(n).crop(crop), max_w=575) for n, _ in cfg], 2, [l for _, l in cfg])
    # --- the user's view before / after
    F["user"] = grid([fit(_shot("csdbg_user_view"), max_w=460), fit(_shot("csdbg_D_user_view"), max_w=460)], 2,
                     ["原设置", "修复后（前景公园和屋顶出现云隙阳光）"])
    F["wide"] = fit(_shot("csdbg_D_wideview1"), max_w=1100)
    # --- the same frame in the capture before the fix and in the final capture (tonemapper output), river crop
    box = (0, 1190, 780, 1480)
    old = to_img(load("tonemap__1783", tex_dir=TEX_V2)[..., :3]).crop(box)
    new = to_img(load(dumped("tonemap", "BufferedRT"))[..., :3]).crop(box)
    F["cap_river"] = grid([old, new], 1, ["修复前的抓帧（2026-11-09）", "最终抓帧（本报告）"], label_h=22)
    # --- light-space near plane: the fix without LightDistanceOverride vs the final capture
    noldo = load("cloud_shadow__471203", tex_dir=TEX_NOLDO)
    final = load(dumped("cloud_shadow", "Cloud.ShadowTexture0"))
    F["ldo"] = grid([fit(to_img(srgb(np.exp(-noldo[..., 2]))), max_w=470),
                     fit(to_img(srgb(np.exp(-final[..., 2]))), max_w=470)], 2,
                    ["光源距离默认 20 km：近平面切进云层（下方是朝太阳一侧）", "LightDistanceOverride 80 km：整张图都完整追踪"],
                    label_h=22)
    n = final.shape[0]
    q = lambda a: float((a[3 * n // 4:, :, 2] > 0.01).mean())
    st_ldo = {"q_noldo": q(noldo), "q_final": q(final), "all_noldo": float((noldo[..., 2] > 0.01).mean()),
              "all_final": float((final[..., 2] > 0.01).mean()), "r_noldo": float(np.median(noldo[..., 0])),
              "r_final": float(np.median(final[..., 0]))}
    # --- mechanism, from the shadow maps of the capture BEFORE the fix: a 2.5 km window near the map centre
    traced = load("cloud_shadow__46570", tex_dir=TEX_V2)[..., 2]          # B = max optical depth, 4096^2, 39 m
    filt = load("cloud_shadow_filter__47239", tex_dir=TEX_V2)[..., 2]      # 2048^2, 78 m
    n2 = filt.shape[0]
    best = None
    for y in range(n2 // 2 - 256, n2 // 2 + 256 - 32, 8):
        for x in range(n2 // 2 - 256, n2 // 2 + 256 - 32, 8):
            w = filt[y:y + 32, x:x + 32] > 1.0
            frac = w.mean()
            edges = np.abs(np.diff(w.astype(int), axis=0)).sum() + np.abs(np.diff(w.astype(int), axis=1)).sum()
            score = -abs(frac - 0.5) * 200 + edges
            if best is None or score > best[0]:
                best = (score, y, x)
    _, y0, x0 = best
    f_crop = filt[y0:y0 + 32, x0:x0 + 32]
    t_crop = traced[2 * y0:2 * y0 + 64, 2 * x0:2 * x0 + 64]
    p1 = to_img(srgb(np.exp(-np.kron(t_crop, np.ones((8, 8))))))
    p2 = to_img(srgb(np.exp(-_bilinear_up(f_crop, 16))))
    p3 = to_img(srgb(_bilinear_up(np.exp(-f_crop), 16)))
    F["mech"] = grid([p1, p2, p3], 3, ["追踪原图 4096²（39 m/纹素，最近邻放大）",
                                       "滤波后 2048²（78 m）：先插值光学厚度再 exp（现在的做法）",
                                       "同一张图：先 exp 再插值透射率（引擎级改法）"])
    st = {"od_max": float(traced.max()), "od_p99_cloud": float(np.percentile(traced[traced > 0.01], 99)),
          "od_median_cloud": float(np.median(traced[traced > 0.01]))}
    st.update(st_ldo)
    st["gpu_a"] = _gpu("gpu_fin", "profilegpu_unfixed*.json")
    st["gpu_d"] = _gpu("gpu_v3", "profilegpu_final*.json")
    st["gpu_final"] = _gpu("gpu_fin", "profilegpu_final*.json")
    # --- god ray A/B, final settings
    rays = [("csfin_G0_full", "G0 全开"), ("csfin_G1_nofogsun", "G1 关：体积雾里的太阳散射"),
            ("csfin_G2_noatmoshadow", "G2 关：大气里的云影"), ("csfin_G3_neither", "G3 两者都关")]
    F["rays"] = grid([fit(_shot(n), max_w=280) for n, _ in rays], 4, [l for _, l in rays])
    # single-frame shots carry cloud sampling noise (two shots of the same frame differ by ~0.01 per pixel), so the
    # differences are taken on box-blurred images: 9x9 for the pictures, 25x25 for the numbers
    names = ("csfin_G0_full", "csfin_G1_nofogsun", "csfin_G2_noatmoshadow", "csray3_G0_full")
    b4 = [_lin(_shot(n).filter(ImageFilter.BoxBlur(4))) for n in names]
    b12 = [_lin(_shot(n).filter(ImageFilter.BoxBlur(12))) for n in names]

    def diff(x, gain):
        v = np.clip(np.abs(x).mean(-1) * gain, 0, 1) ** (1 / 2.2)
        return to_img(v)
    F["rays_diff"] = grid([fit(diff(b4[0] - b4[1], 3.0), max_w=380), fit(diff(b4[0] - b4[2], 12.0), max_w=380),
                           fit(diff(b4[0] - b4[3], 12.0), max_w=380)], 3,
                          ["|G0−G1| ×3：体积雾的贡献（光晕 + 云下光柱）", "|G0−G2| ×12：大气云影的贡献（汇向太阳的淡条纹）",
                           "噪声参照 ×12：两张 G0 之间"])
    st["fog_mean"] = float(np.abs(b12[0] - b12[1]).mean())
    st["atmo_mean"] = float(np.abs(b12[0] - b12[2]).mean())
    st["atmo_signed"] = float((b12[0] - b12[2]).mean())
    st["noise_mean"] = float(np.abs(b12[0] - b12[3]).mean())
    return F, st


SVG = """<svg viewBox="0 0 900 330" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:900px;background:#11141a;
border:1px solid #2a2f3a;border-radius:8px">
<defs><linearGradient id="lit" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f6d98a" stop-opacity=".6"/>
<stop offset="1" stop-color="#f6d98a" stop-opacity=".22"/></linearGradient>
<marker id="ah" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#f0c674"/></marker>
<marker id="ah2" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#7fb5ff"/></marker></defs>
<text x="16" y="22" fill="#cfd6df" font-size="13">侧视示意：太阳在右上方，高度角 31°；光线平行，空气柱的斜率 = cot 31° ≈ 1.66</text>
<g stroke="#f0c674" stroke-width="2" marker-end="url(#ah)">
<line x1="890" y1="36" x2="805" y2="87"/><line x1="890" y1="58" x2="840" y2="88"/></g>
<text x="835" y="34" fill="#f0c674" font-size="13">阳光</text>
<!-- columns below the cloud base (y=110) down to the ground (y=300) -->
<polygon points="250,110 380,110 64,300 -66,300" fill="#232c3d"/>
<polygon points="380,110 470,110 154,300 64,300" fill="url(#lit)"/>
<polygon points="470,110 600,110 284,300 154,300" fill="#232c3d"/>
<polygon points="600,110 700,110 384,300 284,300" fill="url(#lit)"/>
<polygon points="700,110 820,110 504,300 384,300" fill="#232c3d"/>
<!-- clouds -->
<g fill="#d8dde6"><ellipse cx="315" cy="98" rx="66" ry="17"/><ellipse cx="300" cy="84" rx="34" ry="18"/>
<ellipse cx="535" cy="98" rx="66" ry="17"/><ellipse cx="555" cy="83" rx="36" ry="19"/>
<ellipse cx="760" cy="98" rx="61" ry="17"/><ellipse cx="745" cy="84" rx="30" ry="16"/></g>
<text x="380" y="52" fill="#cfd6df" font-size="12">积云挡住阳光 → 后面整根空气柱都在阴影里</text>
<line x1="0" y1="300" x2="900" y2="300" stroke="#6b7280" stroke-width="2"/>
<text x="16" y="320" fill="#9aa3ad" font-size="12">地面 / 河面：空气柱落到地上就是云影</text>
<!-- observer and two view rays -->
<circle cx="110" cy="298" r="6" fill="#7fb5ff"/><text x="122" y="294" fill="#7fb5ff" font-size="12">相机</text>
<g stroke="#7fb5ff" stroke-width="1.8" marker-end="url(#ah2)">
<line x1="110" y1="298" x2="424" y2="112"/><line x1="110" y1="298" x2="558" y2="112"/></g>
<text x="404" y="128" fill="#7fb5ff" font-size="12">1</text><text x="566" y="128" fill="#7fb5ff" font-size="12">2</text>
<g font-size="12"><text x="610" y="200" fill="#7fb5ff">视线 1：几乎全程在亮空气柱里</text>
<text x="610" y="216" fill="#7fb5ff">　　　　→ 屏幕上是一条亮的光柱</text>
<text x="610" y="240" fill="#7fb5ff">视线 2：大部分在阴影空气柱里</text>
<text x="610" y="256" fill="#7fb5ff">　　　　→ 屏幕上是一条暗带</text>
<text x="610" y="280" fill="#f6d98a">亮柱 = 云缝漏下的阳光被雾 / 霾散射</text></g>
</svg>"""


def section8(a, F, st):
    a("<h2 id='shadow'>8. 河面云影的块状 / 锯齿：原因、验证与解决</h2>")
    a("<h3>8.1 现象</h3><p>放大河面可以看到，云影的边缘不是积云的分瓣轮廓，而是一个个被拉宽的方块："
      "有贯穿的竖直直边、台阶状转角，边缘过渡带约一个纹素宽。这是一张低分辨率纹理被双线性放大到屏幕上的典型样子。</p>")
    a(fig(F, "zoom", "同一机位、同一裁剪（编辑器高清截图）", max_w=1180))
    a("<h3>8.2 河面的云影从哪里来</h3><ul>"
      "<li>河面不是单独的水体，而是 MeshTerrain 地形网格的一部分（<code>PreviewSection</code>，材质 "
      "<code>M_MeshTerrain_CitySamplePCG</code>，不透明、Default Lit，水面高度 z = −24.19 m）。在编辑器里沿河面像素打射线确认，"
      "抓帧里也没有任何 SingleLayerWater pass。</li>"
      "<li>它的太阳光在延迟光照 pass（第 4 节 D）里逐像素计算：<code>DeferredLightPixelShaders.usf</code> "
      "<code>GetAtmosphereAndCloudAttenuation()</code> 对每个像素调用一次 <code>GetCloudVolumetricShadow()</code>，"
      "采样第 4 节 A2 生成的云影图（Beer Shadow Map；原设置下是滤波降采样后的 <code>Cloud.ShadowTexture2</code>，"
      "修复后直接读追踪结果 <code>Cloud.ShadowTexture0</code>）。</li>"
      "<li>所以水面云影的精度，完全由这张云影图的纹素大小决定。</li></ul>")
    a("<h3>8.3 根因：云影图的纹素在地面上有 78 m × 151 m</h3>")
    a("<ol><li><b>覆盖范围是设置值的 2 倍。</b>平行光的 <code>CloudShadowExtent</code> 在注释里写的是“半径（km）”，但 "
      "<code>VolumetricCloudRendering.cpp</code> 用 <code>SphereRadius = Extent</code>、<code>SphereDiameter = 2×Extent</code>，"
      "再调用 <code>FReversedZOrthoMatrix(SphereDiameter, SphereDiameter, …)</code>；这个正交矩阵的第一个参数是<b>半宽</b>"
      "（矩阵元素 = 1/Width），所以云影图实际覆盖 ±2×Extent。本场景 Extent = 40 km，图覆盖 160 km × 160 km。</li>"
      "<li><b>空间滤波每次迭代都把分辨率减半。</b><code>r.VolumetricCloud.ShadowMap.SpatialFiltering</code>（默认 1）的说明写着"
      "“blur iterations”，但每次迭代调用 <code>MainShadowFilterCS</code> 都是 2×2 平均、输出尺寸减半。"
      "于是 4096² 的追踪结果被降到 2048²：160 km ÷ 2048 = <b>78.1 m/纹素</b>。</li>"
      "<li><b>投到地面上还会被拉长。</b>光源空间的方形纹素沿太阳方位投到地面，长度要除以 sin(31.1°)：78 m × 151 m。"
      "相机在 200 多米高处、俯视 1–2 km 外的河面时，一个纹素横向占 50–75 个像素，纵向占 12–30 个像素，看上去就是一块块横向的方块。</li>"
      "<li><b>积云太“厚”，边缘变成了硬台阶。</b>云影图存的是“前沿深度、平均消光、最大光学厚度”，"
      "<code>GetCloudVolumetricShadow</code> 先双线性插值这些值再算 exp(−光学厚度)。这片积云在云影图里的光学厚度："
      "有云纹素的中位数约 %.0f（透射率约 0.25%%），1%% 的纹素超过 %.0f，最大 %.0f，"
      "透射率在一个纹素内几乎是从 0 直接跳到 1；可见的影子边缘就是“插值后光学厚度 ≈ 1”的等值线，它贴着纹素网格走，"
      "所以出现直边和台阶。影子还会向外膨胀约一个纹素：小于两个纹素（约 150–300 m）的云缝会被填平，"
      "这也是原设置下前景公园整片都在阴影里的原因。</li>"
      "<li><b>为什么河面最显眼。</b>河面平整光滑、没有纹理细节；逆光时太阳在水面的反光是地面上最亮的东西，"
      "云影把反光切开，对比度最高；再加上掠射角把纹素拉成横条。楼和树有自身的阴影和纹理，掩盖了这个问题。</li></ol>"
      % (st["od_median_cloud"], st["od_p99_cloud"], st["od_max"]))
    a(fig(F, "mech", "用抓帧里两张真实云影图（地图中心附近 2.5 km × 2.5 km）还原地面看到的阴影。中间是现在的样子："
                     "边缘贴着 78 m 纹素网格走、出现台阶，影子比左图外扩、云缝被填平；"
                     "右边只改重建方式：硬台阶变成柔和过渡、影子不再外扩，但分辨率没变，细节仍只有 78 m（需要改引擎着色器）", max_w=1180))
    a("<table><tr><th>配置</th><th>实际覆盖</th><th>追踪</th><th>表面采样的图</th><th>光源空间纹素</th>"
      "<th>地面投影（太阳高度角 31.1°）</th><th class='num'>CloudShadow GPU ms</th></tr>"
      "<tr><td>A 原设置：Extent 40、SpatialFiltering 1</td><td>160 km</td><td>4096²</td><td>2048²</td><td>78.1 m</td>"
      "<td>78 × 151 m</td><td class='num'>%.1f</td></tr>"
      "<tr><td>C：Extent 40、SpatialFiltering 0</td><td>160 km</td><td>4096²</td><td>4096²</td><td>39.1 m</td><td>39 × 76 m</td><td class='num'>—</td></tr>"
      "<tr><td>B：Extent 10、SpatialFiltering 1</td><td>40 km</td><td>4096²</td><td>2048²</td><td>19.5 m</td><td>19.5 × 38 m</td><td class='num'>—</td></tr>"
      "<tr><td>D：Extent 10、SpatialFiltering 0</td><td>40 km</td><td>4096²</td><td>4096²</td><td>9.8 m</td>"
      "<td>9.8 × 19 m</td><td class='num'>%.1f*</td></tr>"
      "<tr><td><b>D + LightDistanceOverride 80（最终默认）</b></td><td>40 km</td><td>4096²</td><td>4096²</td><td><b>9.8 m</b></td>"
      "<td>9.8 × 19 m</td><td class='num'>%.1f</td></tr></table>"
      "<p class='meta'>GPU 时间是同一编辑器会话里 ProfileGPU 的中位数（2–3 帧）。* D 偏低是因为朝太阳一侧约四分之一的纹素根本没有追踪"
      "（见 8.6），不能算省下的。上一版报告里的 19.4–20.4 / 16.3 ms 是另一个编辑器同时占用 GPU 时测的，整体偏高。</p>"
      % (st["gpu_a"], st["gpu_d"], st["gpu_final"]))
    a("<h3>8.4 验证：每次只改一个变量</h3><p>在编辑器里用同一台相机（河面放大，水平视角 32°）拍四张。块的大小随纹素大小成比例变化，"
      "而云影的位置和总体形状不变，说明问题确实出在云影图的分辨率上，而不是水面材质、反射或体积雾。</p>")
    a(fig(F, "abcd", "A → C → B → D：纹素 78 → 39 → 19.5 → 9.8 m", max_w=1180))
    a(fig(F, "user", "你当时停留的视角：修复后河面云影变成积云轮廓，前景的云隙阳光也出来了", max_w=940))
    a(fig(F, "wide", "D 配置下全城广角：±20 km 覆盖范围内一切正常，地平线和天空没有拉伸条纹", max_w=1100))
    a(fig(F, "cap_river", "同一机位、同一帧在两份抓帧里的河面（色调映射输出，1:1 像素）：方块和直边变成了积云的轮廓，云缝里的阳光也落到了水面上",
          max_w=780))
    a("<h3>8.5 解决办法</h3><ol>"
      "<li><b>已设为默认（开销基本不变）：</b>平行光 <code>CloudShadowExtent</code> 40 → 10，"
      "<code>r.VolumetricCloud.ShadowMap.SpatialFiltering</code> 1 → 0，<code>r.VolumetricCloud.ShadowMap.SnapLength</code> 20 → 1，"
      "再加 <code>r.VolumetricCloud.ShadowMap.LightDistanceOverride 80</code>（原因见 8.6）。"
      "纹素从 78 m 降到 9.8 m；追踪的仍是 4096²，同一会话实测 <code>CloudShadow</code> %.1f → %.1f ms。"
      % (st["gpu_a"], st["gpu_final"]) +
      "<code>SnapLength</code> 默认 20 km，云影图中心按 20 km 网格吸附；覆盖缩小后要让它跟着相机走，"
      "<code>SnapToPixelGrid</code>（默认开）保证移动相机时不闪。<code>cs_clear_sky.py {\"phase\": \"apply\"}</code> 默认就套用这一组，"
      "<code>{\"phase\": \"apply\", \"fix_cloud_shadow\": false}</code> 换回原设置做对比。</li>"
      "<li><b>覆盖范围的取舍：</b>云影图外面不是“没有阴影”，所有采样器都是 Clamp，会采到边缘纹素，"
      "沿着那个方向拉出无限长的条纹。所以 2×Extent 要大于你能看到云影的距离；远处的地形和大气被空气透视盖住，一般不明显。"
      "Extent 10 km（±20 km）覆盖了整座城市，广角里没有出现条纹。缩小 Extent 时还要顾及光源近平面（8.6）。</li>"
      "<li><b>只改一项</b>也有明显改善：只缩小 Extent（B，19.5 m），或只关空间滤波（C，39 m）。"
      "千万不要把 <code>SpatialFiltering</code> 调大：2 → 1024²（156 m），4 → 256²（625 m），只会更块。</li>"
      "<li><b>性能优先：</b>在第 1 条的基础上把 <code>CloudShadowMapResolutionScale</code> 8 → 4（追踪 2048²），仍有 19.5 m，"
      "按纹素数估算追踪开销约降到 1/4（未实测）。</li>"
      "<li><b>继续提高分辨率：</b><code>r.VolumetricCloud.ShadowMap.MaxResolution 8192</code> + ResolutionScale 16，"
      "纹素再减半，但追踪开销约 ×4、多占约 256 MB 显存。缩小覆盖范围已经够用，没必要。</li>"
      "<li><b>时域滤波（实验性）：</b><code>r.VolumetricCloud.ShadowMap.TemporalFiltering.NewFrameWeight</code> 小于 1 时，"
      "每帧只追踪一半分辨率，按 4 帧抖动累积成全分辨率，单帧开销约 1/4；太阳或云移动时可能滞后，引擎注释称其为实验功能（needs more work）。</li>"
      "<li><b>材质侧：</b>降低云边缘的光学厚度（<code>DensityScale</code>、<code>ExtinctionMax</code>，或让边缘侵蚀更软），"
      "透射率过渡会变宽，但云的外观也会跟着变软。</li>"
      "<li><b>引擎级（源码版可以改，但 E:\\UnrealEngine 是多个项目共用的，会影响它们，需要单独决定）：</b>"
      "在 <code>VolumetricCloudCommon.ush</code> 的 <code>GetCloudVolumetricShadow</code> 里改成 4 点 Gather、逐点 exp 后再双线性插值"
      "（上方机理图右栏：去掉硬台阶和外扩，但不增加细节，最好与第 1 条一起用），或者按“接收点到云前沿的距离 × 太阳角半径”做 PCF / PCSS 式软半影。"
      "另外，滤波 pass 里的 <code>Mean − StandardDeviation</code> 中 Mean 是 4 个深度之和、没有除以 4，"
      "化简后正好等于普通平均；对地面接收点影响不大（无云纹素的深度是射线穿出云层的位置，仍在地面之前）。</li></ol>")
    a("<h3>8.6 缩小覆盖范围的副作用：光源近平面切进云层</h3>")
    a("<p>只做前三项（表里的 D）重抓之后，云影图朝太阳的一侧缺了一大块云。原因在云影图的投影设置"
      "（<code>VolumetricCloudRendering.cpp</code> 第 1817–1852 行）：</p>"
      "<pre><code>LightDistance = LightDistanceOverride &gt; 0 ? LightDistanceOverride : 2 × CloudShadowExtent   // 默认 20 km\n"
      "LookAt        = 相机正下方的地面点（按 SnapLength 吸附）\n"
      "LightPosition = LookAt − 光照方向 × LightDistance                                    // 朝太阳退 20 km\n"
      "NearPlane = 0（就在 LightPosition），FarPlane = 2 × LightDistance</code></pre>"
      "<p>追踪着色器（<code>VolumetricCloud.usf</code> 第 2110–2163 行）让每个纹素从近平面上的点出发，沿光线方向求与云层上下两个球壳的交点："
      "起点在云层里时 <code>TMin = max(0, TMin)</code>，只追踪近平面以下那一段；起点在云底以下时直接返回“无阴影”"
      "（注释：<i>We are inside under the cloud layer, we simply skip shadowing evaluation</i>）。"
      "近平面垂直于光线、正对太阳倾斜：以相机正下方为原点，它在光源空间里离中心 a km 的位置，海拔是 20·sin 31.1° + a·cos 31.1° = 10.3 + 0.86a km。"
      "云影图在光源空间里覆盖 a ∈ [−20, 20] km，朝太阳一侧（a 为负）的近平面低于云顶 5.4 km（a &lt; −5.8 km）、"
      "甚至低于云底 1.4 km（a &lt; −10.4 km）。换到地面上，就是朝太阳方向 11 km 以外的云影少了云顶，20 km 以外整片消失；"
      "空中的点越高，受影响的距离越远。</p>")
    a(fig(F, "ldo", "两份抓帧里的 Cloud.ShadowTexture0（透射率 exp(−B)，4096²，40 km 见方）。左：朝太阳一侧（图的下方）四分之一的纹素"
                    "有云比例只有 %.1f%%（全图 %.1f%%），R 通道的云前沿深度中位数 %.1f km；右：加上 LightDistanceOverride 80 后"
                    "这一块恢复到 %.1f%%（全图 %.1f%%），近平面退到 80 km 外，前沿深度中位数 %.1f km"
                    % (100 * st["q_noldo"], 100 * st["all_noldo"], st["r_noldo"], 100 * st["q_final"], 100 * st["all_final"],
                       st["r_final"]), max_w=960))
    a("<ul><li><b>修法：</b><code>r.VolumetricCloud.ShadowMap.LightDistanceOverride 80</code>（km），也就是原设置 Extent 40 时的光源距离。"
      "近平面要高过整张图的云顶，需要 LightDistance ≥ (云顶高度 + 2×Extent×cos 仰角) / sin 仰角，太阳 31° 时约 44 km，"
      "太阳越低要求越大，80 km 留了余量。追踪区间仍由云层的上下球壳决定，采样数不变，所以不额外花时间："
      "上表里 D 的 %.1f ms 比最终的 %.1f ms 低，正是因为约四分之一的纹素提前返回了。</li>"
      "<li><b>代价：</b>R 通道是 R11G11B10 浮点（6 位尾数），前沿深度从 0–50 km 变成 42–110 km，量化步长从约 0.25 km 变成 0.5–1 km，"
      "和原设置（Extent 40，光源距离同为 80 km）一样。它只影响位于云层里或紧贴云底的采样点，地面接收点取 min(B, …) 时基本饱和在 B 上。</li>"
      "<li><b>这个机位看不出来：</b>修复前后的同机位截图差别只是云的采样噪声。受影响的是 11 km 以外、朝太阳方向的地面和接近地平线的远处空气，"
      "在这张图里只占地平线下方二三十个像素，还盖着厚厚的空气透视。但第 4 节 A2 的云影图本身会少一块，换成更低的太阳或更远的视野就会露出来，所以一起设成默认。</li></ul>"
      % (st["gpu_d"], st["gpu_final"]))


def section9(a, F, st):
    a("<h2 id='godray'>9. God ray：成因与引擎实现</h2>")
    a("<h3>9.1 物理成因</h3><ul>"
      "<li>阳光在空气里会被散射：空气分子是瑞利散射，气溶胶、水汽、薄雾颗粒是米氏散射。"
      "沿视线看到的“空气亮度”，是视线经过的每一段空气把阳光散射进眼睛的总和（再乘上这一段到眼睛的透射率）。</li>"
      "<li>云挡住太阳的地方，云后面那一整根空气柱收不到直射阳光，几乎不散射；云缝漏下来的阳光照亮的空气柱散射很强。"
      "视线如果大段穿过亮柱就是亮条，大段穿过影子柱就是暗条，这就是光柱（crepuscular rays）。</li>"
      "<li>这些光柱在空间里其实是平行的（太阳在无穷远），因为透视才看起来从太阳位置向外放射；背对太阳时，它们会汇聚到太阳的对点，"
      "叫反曙暮光（anti-crepuscular rays）。</li>"
      "<li>要看得清楚需要四个条件：有足够的散射介质（薄霾、雾，只有瑞利散射的干净空气很弱）；有带缝隙的遮挡物（积云）；"
      "朝太阳方向看，因为气溶胶的相函数强烈前向（HG g ≈ 0.7–0.8），亮柱和暗柱的差距在太阳方向最大；"
      "以及视线里亮、暗空气柱的长度差别足够大。</li></ul>")
    a("<figure>%s<figcaption>示意图：两条视线分别大段穿过亮、暗空气柱，积分后形成明暗相间的光柱</figcaption></figure>" % SVG)
    a("<h3>9.2 UE 5.8 里的实现：三条路径，共用同一份阴影数据</h3>")
    a("<p>引擎没有一个叫 god ray 的单独功能。在“参与介质的散射”里乘上“阳光可见性”，光柱就自然出现了。可见性来自两份数据："
      "<b>云影图</b>（第 4 节 A2，Beer Shadow Map）和 <b>VSM</b>（建筑等不透明物体的阴影）。</p>")
    a("<h4>① 体积雾（本帧的主力）</h4>"
      "<p><code>VolumetricFog.usf</code> 的 <code>LightScatteringCS</code> 对每个 froxel（本帧 211×331×128，每格 4 像素，深度覆盖 6 km）"
      "累加太阳的散射：</p>"
      "<pre><code>ShadowFactor = 静态阴影 × CSM/VSM × lerp(1, GetCloudVolumetricShadow(froxel 位置), CloudShadowOnSurfaceStrength)\n"
      "LightScattering += SunColor × VolumetricScatteringIntensity × LightFunction × ShadowFactor\n"
      "                   × HenyeyGreenstein(g = VolumetricFogScatteringDistribution, dot(L, -V))\n"
      "（再乘 VBufferA 里的散射系数 σs，加上 Lumen / 天光的环境项）</code></pre>"
      "<p>然后 <code>FinalIntegrationCS</code> 沿每一列 froxel 由近到远做 Frostbite 的能量守恒积分："
      "<code>L += S·(1−e^(−σt·Δ))/σt · T</code>，<code>T *= e^(−σt·Δ)</code>；每一片存下“到这个深度为止的雾光和透射率”。"
      "最后高度雾 pass 按像素深度取值：场景色 × T + L。froxel 每帧带抖动，再用 0.9 的历史权重做时域累积，"
      "所以 4 像素的格子看起来是平滑的。注意体积雾里的云影强度用的是 <code>CloudShadowOnSurfaceStrength</code>，"
      "不是 <code>…OnAtmosphereStrength</code>。</p>")
    a("<h4>② SkyAtmosphere（天空里又长又淡的条纹）</h4>"
      "<p><code>SkyAtmosphere.usf</code> 积分单次散射时，每个采样点：</p>"
      "<pre><code>PlanetShadow0 *= VSM 阴影                                  // CastShadowsOnAtmosphere\n"
      "PlanetShadow0 *= lerp(1, GetCloudVolumetricShadow(P), CloudShadowOnAtmosphereStrength)   // 第 741 行\n"
      "S = SunIlluminance × (PlanetShadow0 × TransmittanceToSun × Phase×σs  +  MultiScatteredLuminance × σs)   // 第 746 行</code></pre>"
      "<p>云影只乘在单次散射上；多次散射项只乘云的天光 AO（第 736 行）。<code>FastSkyLUT 0</code> 时，天空每个像素都这样逐像素步进"
      "（第 4 节 H），否则先算进 192×104 的 SkyViewLut，条纹会糊。空气透视体积（CameraVolumeLut）也会采样云影。</p>")
    a("<h4>③ 屏幕空间光束（LightShafts，传统做法）</h4>"
      "<p>平行光的 <code>bEnableLightShaftOcclusion</code> / <code>bEnableLightShaftBloom</code>。"
      "把深度做成遮挡蒙版，在半分辨率下朝太阳的屏幕位置做 3 次径向模糊（<code>LightShaftShader.usf</code> "
      "<code>BlurLightShaftsMain</code>，每次模糊距离按指数增大）。Occlusion 版用结果压暗高度雾的内散射，Bloom 版把亮像素沿径向抹开叠加。"
      "它只在太阳在画面内或附近时有效，并且只认不透明物体，不认云。本帧太阳附近没有遮挡物，遮挡项几乎全是 1（第 4 节 G）。</p>")
    a("<h4>④ 体积云自身</h4><p>云层内部每个采样点都要二次步进求到太阳的透射率，所以云塔之间也会有光束；"
      "<code>HighQualityAerialPerspectiveOnCloud</code> 在相机和云之间逐像素步进大气时，同样乘了云影。</p>")
    a("<h3>9.3 本帧实测：光柱主要来自体积雾</h3><p>在报告的机位、最终设置（含第 8 节的云影修复）下，每次只关一项"
      "（高清截图，Mode 0，单帧）：</p>")
    a(fig(F, "rays", "关掉体积雾里的太阳散射（G1），光晕和云下光柱几乎全没了；关掉大气的云影（G2），画面几乎不变", max_w=1180))
    a(fig(F, "rays_diff", "差值图（线性亮度，先做 9×9 盒式模糊去掉单帧的云采样噪声；第三张是两张 G0 之间的差，"
                          "它们只差 LightDistanceOverride，这个机位里画面不受影响，用作噪声参照）。"
                          "按 25×25 模糊后统计：体积雾的平均贡献 %.3f，大气云影 %.3f（平均让天空暗 %.3f），噪声 %.3f；"
                          "体积雾约是大气云影的 %.0f 倍"
          % (st["fog_mean"], st["atmo_mean"], -st["atmo_signed"], st["noise_mean"],
             st["fog_mean"] / max(st["atmo_mean"], 1e-6)), max_w=1180))
    a("<ul><li>体积雾决定了近处、中景那几根清晰的光柱和太阳周围的光晕：它的介质是 6 km 内的高度雾（第二层一直延伸到云底），"
      "g = 0.8，散射强度 ×2。</li>"
      "<li>大气的云影产生的是汇向太阳的淡条纹，铺满整个天空，要放大 12 倍才看得清，"
      "它更像远处空气的明暗，而不是一根根光柱。</li>"
      "<li>体积雾和大气读的是同一张云影图。第 8 节的修复让它细了 8 倍，光柱的边缘也随之变利落"
      "（对照 8.4 和 8.5 的抓帧对比里远处城市上空的光柱）。</li></ul>")
    a("<h3>9.4 想让光柱更明显时可以调的</h3><ul>"
      "<li>介质：<code>FogDensity</code> / 第二层雾的密度和高度衰减（让雾延伸到云底），SkyAtmosphere 的 "
      "<code>MieScatteringScale</code>（霾）。</li>"
      "<li>强度与方向性：平行光 <code>VolumetricScatteringIntensity</code>，雾的 <code>VolumetricFogScatteringDistribution</code>"
      "（g 越大，朝太阳越亮）。</li>"
      "<li>遮挡：太阳正好在一团积云边缘后面、云缝足够多时光柱最好看；把云影图做细（第 8 节）能让光柱边缘更利落。</li>"
      "<li>精度：<code>r.VolumetricFog.GridPixelSize</code>、<code>GridSizeZ</code>、<code>VolumetricFogDistance</code>"
      "（本场景已是 4 / 128 / 6 km）。</li></ul>")


def build_sections(a):
    F, st = figures()
    section8(a, F, st)
    section9(a, F, st)
    return st
