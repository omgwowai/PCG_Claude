# 小区域 18 阶段 City Sample PCG 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在 `/Game/PCGArea/L_SmallArea18` 里建成一个约 600 m 的小区域，用 Epic 的 18 张 City Sample 阶段图按序生成，每阶段交付 PCG debug 与累计几何两张截图。

**Architecture:** 用 `new_level_from_template` 把 demo 关卡整份复制成新关卡（地形 `MeshPartition` 是硬依赖，空白关卡跑不出来），再用**一个相似变换**同时缩放要动的样条、机位与 Volume 位置，然后按 `gen → shot_debug → shot_geom` 的三次调用节奏逐阶段跑，最后保存新关卡并生成内嵌报告。

**Tech Stack:** UE 5.8 编辑器内嵌 Python（`unreal` 模块，经 `UnrealMcpBridge` 的 `run_unreal_script` 执行 `Content/Python/*.py`）；离线报告工具是仓库里的 Python 3.14（`C:\Python314\python.exe`，已装 Pillow 12.2.0）。**项目 venv 没有 Pillow**，报告工具必须用系统 python 跑。

**Spec:** `docs/superpowers/specs/2026-09-24-pcg-small-area-18-stage-design.md`（commit `8fbb04c`）

## Global Constraints

- **编辑器脚本必须放在 `Content/Python/` 下**，`script_path` 是相对该根的 `.py` 路径；逃出该根、非 `.py`、文件不存在一律被桥拒绝。
- **UObject 引用只许留在函数内。** 桥用 `exec(..., globals())` 在常驻的 `__main__` 里执行，任何留在全局的 world / package / actor / component 包装都会钉住旧 world，下一次切关卡必崩在 `UEditorEngine::CheckForWorldGCLeaks()`（实测引用链 `FPyReferenceCollector::AddReferencedObjects(Package …)`）。每个脚本的顶层只允许：import、常量、`try/except`、`mcp_result = ...`、`print`。
- **`mcp_result` 必须 JSON 可序列化**（`unreal.Vector` / `Name` / Actor 都不行），失败时报错无用，只能看到 `failed to produce result file`。
- **一次桥调用只发一张截图**：`take_high_res_screenshot` 在下一帧落盘，同一调用连发会互相覆盖。参数只能走关键字，签名 `(res_x, res_y, filename, camera=None, mask_enabled=False, capture_hdr=False, comparison_tolerance=..., comparison_notes="", delay=0.0, force_game_view=True)`。
- **生成是异步的**，`generate_local` 立即返回；同一次调用里读 `get_generated_graph_output()` 必为空且不报错。
- **新建/刚 spawn 的 PCGComponent 必须先 `activate(True)` 再 `generate_local`**，否则 `ShouldGenerate()` 不成立、静默零点。
- **`add_edge` 会静默失败却返回真值**；任何连线后必须用 `len(graph.get_all_edges())` 前后对比。
- **截图目录**：`Saved/Screenshots/WindowsEditor/`（UE 固定，忽略 `-log=` 之类的自定义路径）。
- **跑前跑后清空 `Saved/Autosaves/`**：影子副本会弹「Restore Packages」模态框卡住游戏线程，让桥失去响应。
- **Epic 资产零改动**：不允许出现 `save_asset` / `save_directory` / `save_all_dirty_levels` / `save_dirty_packages`；只允许 `save_current_level()`（新关卡）。demo 关卡与 `/CitySamplePCG/` 下的图资产全程不保存。
- **报告的截图落点**：原件在 `Saved/Screenshots/WindowsEditor/`（不入 git），报告内嵌 base64，自包含。

## Review Focus

1. **新城市里建筑与路段的实际尺寸仍是原尺寸**（变换只缩了样条与机位）。预期：600 m 的城市配上 20 m 宽的体量会显得密。若密到看不出街区，报告里必须写明并给出下一步参数位（`PCG_3_1_1_Districts` 的 Block grid length/width 图参数），不要悄悄调图。
2. **高架远伸**：`HighWay_2/3` 的样条在缩后仍从城市两侧各伸出约 2 km（原始设计如此）。预期：远景出现两条长高架剪影。若视觉上不可接受，报告要指出这是原关卡设计而非缩放错误。
3. **阶段 3 背景山体与阶段 9 之后的远景**：山体是 `/Game/Environment/Background_City/VistaCliffs_PCG` 的绝对位置资产，缩了城市后不一定落在机位视野内。预期：若看不到，如实标 `missing_visual`，不截图造假。
4. **数据阶段 1/4/5/6 的 `geometry` 张与前一阶段相同**（它们不产出实例化几何）。预期：报告卡片要写明这一点，避免被当成漏拍。
5. **关卡保存**：`save_current_level()` 是否连带保存 World Partition 的**外部 Actor 包**未经验证。预期：保存后必须核对 `Content/__ExternalActors__/PCGArea/` 下有文件且 mtime 是刚才；若没有，回退到 `EditorLoadingAndSavingUtils.get_dirty_map_packages()` 收集后逐个 `save_packages`，并把发现的实际情况写进技能。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `Content/Python/pcg_sa_geom.py` | 纯计算：相似变换、缩放系数、样条包围盒、机位求解。无 `unreal` 依赖，可离线 pytest |
| `Content/Python/pcg_sa_level.py` | 关卡派生：模板复制 + 依赖验证 |
| `Content/Python/pcg_sa_shape.py` | 施加变换：样条 / 机位 / Volume 位置，并读回验证 |
| `Content/Python/pcg_sa_run.py` | 逐阶段：`cleanup_all` / `gen` / `shot_debug` / `shot_geom` / `finish` / `census` |
| `Tools/sa_manifest.py` | census + 截图 → 报告清单（两图模式） |
| `Tools/build_pcg_stage_report.py` | 改：卡片支持一张或两张截图 |
| `Tools/tests/test_sa_geom.py` | `pcg_sa_geom` 的 pytest |
| `Tools/tests/test_sa_manifest.py` | `Tools/sa_manifest.py` 的 pytest |

`pcg_sa_geom.py` 放在 `Content/Python/` 而不是 `Tools/`，因为它要被编辑器脚本 import；pytest 用 `sys.path` 指过去即可。

---

## Task 1: 纯计算模块 `pcg_sa_geom`

**Files:**
- Create: `Content/Python/pcg_sa_geom.py`
- Test: `Tools/tests/test_sa_geom.py`

**Interfaces:**
- Consumes: 无
- Produces: `scale_for_target(city_bbox, target_cm) -> float`；`map_point(p, scale, src_center, dst_center) -> [float,float,float]`；`map_tangent(v, scale) -> [x,y,z]`；`bbox_of_points(points) -> (min_xyz, max_xyz)`；`city_bbox_from_splines(splines) -> (min,max)`；`orbit_camera(center, radius, az_deg, elev_deg, dist_mult, min_height) -> ([loc],[rot])`

- [x] **Step 1: 写失败的测试**

```python
# Tools/tests/test_sa_geom.py
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "Content", "Python"))

import pcg_sa_geom as G


# Measured 2026-09-24 from L_CitySamplePCG_Demo: CityShape is 213006 x 181776 cm.
CITY_MIN = [-115988.107, -83950.695, 0.0]
CITY_MAX = [97018.107, 97825.0, 0.0]


def test_scale_matches_hand_computed_value():
    # 600 m = 60000 cm over the 213006 cm long side -> 0.281682...
    s = G.scale_for_target((CITY_MIN, CITY_MAX), 60000.0)
    assert abs(s - 0.281682) < 1e-5


def test_scale_uses_the_larger_dimension_not_the_first():
    # A tall-but-narrow bbox must be driven by its long side.
    s = G.scale_for_target(([0.0, 0.0, 0.0], [100.0, 400.0, 0.0]), 200.0)
    assert abs(s - 0.5) < 1e-9


def test_center_of_bbox_is_invariant_under_the_transform():
    center = [(CITY_MIN[i] + CITY_MAX[i]) / 2.0 for i in range(3)]
    s = G.scale_for_target((CITY_MIN, CITY_MAX), 60000.0)
    out = G.map_point(center, s, center, center)
    for a, b in zip(out, center):
        assert abs(a - b) < 1e-6


def test_map_point_translates_and_scales_about_the_source_center():
    # Point 1000 cm to the +X of the source center, halved, about the origin.
    out = G.map_point([1000.0, 0.0, 0.0], 0.5, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    assert out == [500.0, 0.0, 0.0]
    # Same scale, moved so the source center lands at (10, 20, 0).
    out2 = G.map_point([1000.0, 0.0, 0.0], 0.5, [0.0, 0.0, 0.0], [10.0, 20.0, 0.0])
    assert out2 == [510.0, 20.0, 0.0]


def test_map_point_keeps_internal_distances_uniform_on_every_axis():
    s = 0.25
    a = G.map_point([0.0, 0.0, 0.0], s, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    b = G.map_point([100.0, 200.0, 300.0], s, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    d = [b[i] - a[i] for i in range(3)]
    assert d == [25.0, 50.0, 75.0]


def test_map_tangent_scales_without_translating():
    assert G.map_tangent([100.0, -50.0, 10.0], 0.5) == [50.0, -25.0, 5.0]


def test_bbox_of_points_handles_a_single_point_and_a_flat_axis():
    mn, mx = G.bbox_of_points([[3.0, 4.0, 5.0]])
    assert mn == [3.0, 4.0, 5.0] and mx == [3.0, 4.0, 5.0]
    mn2, mx2 = G.bbox_of_points([[0.0, 0.0, 7.0], [10.0, -4.0, 7.0]])
    assert mn2 == [0.0, -4.0, 7.0] and mx2 == [10.0, 0.0, 7.0]


def test_city_bbox_from_splines_takes_the_union():
    splines = [
        {"points": [[0.0, 0.0, 0.0], [10.0, 10.0, 0.0]]},
        {"points": [[-5.0, 20.0, 0.0]]},
    ]
    mn, mx = G.city_bbox_from_splines(splines)
    assert mn == [-5.0, 0.0, 0.0] and mx == [10.0, 20.0, 0.0]


def test_orbit_camera_looks_at_the_center_from_the_requested_bearing():
    import math
    loc, rot = G.orbit_camera([0.0, 0.0, 0.0], 300.0, az_deg=0.0, elev_deg=45.0,
                              dist_mult=3.0, min_height=200.0)
    # bearing 0 = +X, so the camera sits on +X at 3*300 = 900 and above the floor.
    assert abs(loc[0] - 900.0) < 1e-6
    assert abs(loc[1]) < 1e-6
    assert loc[2] >= 200.0
    pitch, yaw, roll = rot
    assert pitch < 0                    # looking downward
    assert abs(abs(yaw) - 180.0) < 1.0  # facing back toward -X
    assert roll == 0.0


def test_orbit_camera_respects_the_minimum_height_for_a_flat_view():
    loc, _ = G.orbit_camera([0.0, 0.0, 0.0], 300.0, az_deg=0.0, elev_deg=2.0,
                            dist_mult=3.0, min_height=500.0)
    assert loc[2] == 500.0
```

- [x] **Step 2: 跑测试确认它失败**

Run: `C:\Python314\python.exe -m pytest Tools/tests/test_sa_geom.py -q`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'pcg_sa_geom'`

- [x] **Step 3: 写实现**

```python
# Content/Python/pcg_sa_geom.py
# Pure geometry for the small-area run. No `unreal` import: this module is
# imported by the editor-side scripts inside the editor's embedded Python, and
# it is also imported by pytest on the system interpreter. Anything that needs
# the engine belongs in pcg_sa_shape.py / pcg_sa_run.py instead.
#
# The transform is a single similarity: scale about `src_center`, then move that
# centre to `dst_center`. Used identically for spline points, camera positions and
# volume locations, so the whole scene shrinks coherently.

import math


def bbox_of_points(points):
    """(min_xyz, max_xyz) as plain float lists for a list of 3-element points."""
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    zs = [float(p[2]) for p in points]
    return ([min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)])


def city_bbox_from_splines(splines):
    """Union bbox over a list of {"points": [[x,y,z], ...]} dicts."""
    pts = []
    for sp in splines:
        pts.extend(sp["points"])
    return bbox_of_points(pts)


def scale_for_target(city_bbox, target_cm):
    """Scale making the bbox's LONGER horizontal side equal target_cm.

    Horizontal only: Z must not drive the scale, or a tall thin city would be
    shrunk by its height."""
    mn, mx = city_bbox
    span = max(float(mx[0]) - float(mn[0]), float(mx[1]) - float(mn[1]))
    if span <= 0.0:
        raise ValueError("degenerate city bbox: horizontal span is 0")
    return float(target_cm) / span


def map_point(p, scale, src_center, dst_center):
    """Similarity map: p -> dst_center + scale * (p - src_center)."""
    return [float(dst_center[i]) + float(scale) * (float(p[i]) - float(src_center[i]))
            for i in range(3)]


def map_tangent(v, scale):
    """Tangents are directions: they scale but never translate."""
    return [float(scale) * float(v[i]) for i in range(3)]


def orbit_camera(center, radius_cm, az_deg, elev_deg, dist_mult, min_height):
    """A camera pose looking down at `center` from a bearing.

    `radius_cm` is the subject's horizontal radius; the distance is
    dist_mult * radius_cm so the subject fills a reasonable part of the frame.
    Returns ([x,y,z], [pitch,yaw,roll]) with roll always 0.

    Why compute this at all, when the 09-23 run had to use the level's own cine
    cameras: those were authored for a 2 km city whose stage 3 vista sits 10 M
    units out, so bounds-derived poses flew away. Here the subject is 600 m of
    our own freshly-generated geometry, so a computed orbit is both safe and
    exactly framed. The cine cameras are still used as a fallback.
    """
    dist = float(dist_mult) * float(radius_cm)
    az = math.radians(float(az_deg))
    elev = math.radians(float(elev_deg))
    horiz = dist * math.cos(elev)
    x = float(center[0]) + horiz * math.cos(az)
    y = float(center[1]) + horiz * math.sin(az)
    z = float(center[2]) + dist * math.sin(elev)
    if z < float(min_height):
        z = float(min_height)
    # UE pitch is negative when looking down.
    pitch = -math.degrees(math.atan2(z - float(center[2]), horiz)) if horiz > 0 else -90.0
    yaw = math.degrees(math.atan2(float(center[1]) - y, float(center[0]) - x))
    return [x, y, z], [pitch, yaw, 0.0]
```

- [x] **Step 4: 跑测试确认通过**

Run: `C:\Python314\python.exe -m pytest Tools/tests/test_sa_geom.py -q`
Expected: `9 passed`

- [x] **Step 5: 提交**

```bash
git add Content/Python/pcg_sa_geom.py Tools/tests/test_sa_geom.py
git commit -m "Add pure similarity-transform geometry for the small-area PCG run"
```

---

## Task 2: 关卡派生 `pcg_sa_level`

**Files:**
- Create: `Content/Python/pcg_sa_level.py`
- Read for context: `Content/Python/pcg_shots.py`（`vols()` / `cam_by_name()` 的写法）、`.claude/skills/city-sample-pcg-city-builder/references/stage-run-playbook.md`

**Interfaces:**
- Consumes: 无
- Produces: 新关卡资产 `/Game/PCGArea/L_SmallArea18`；`mcp_result.data.inventory` 形状为
  `{"spline_actors": [{"label","class","tags","loc","scale","splines":[{"num_points","closed","points"}]}], "volumes": [{"label","loc","graph"}], "cameras": [{"label","loc","rot"}], "terrain": [{"label","class"}]}`
  —— **Task 3 直接消费这个形状**。

- [x] **Step 1: 写脚本（无单测；判定靠 `mcp_result` 的断言字段）**

```python
# Content/Python/pcg_sa_level.py
# Task A: derive the small-area level from the demo level's template.
#
# args: {"template": "/CitySamplePCG/Levels/L_CitySamplePCG_Demo",
#        "target":   "/Game/PCGArea/L_SmallArea18",
#        "force":    false}   # true = proceed even if the target already exists
#
# WHY A TEMPLATE COPY: the demo level's terrain is one
# /Script/MeshPartition.MeshPartition actor. Stage 1 reads it and writes it back,
# and every later stage projects onto it, so a blank level produces nothing at all
# (silent zero, no error). Copying also brings the 18 PCGVolumes with their graph
# parameters, the 11 cine cameras, lights and the water plane.
#
# GLOBAL DISCIPLINE: no UObject may survive this script. Everything lives inside
# run(); module level holds only JSON. See the Global Constraints in the plan.

import gc
import json

TEMPLATE = "/CitySamplePCG/Levels/L_CitySamplePCG_Demo"
TARGET = "/Game/PCGArea/L_SmallArea18"


def vec(v):
    return [round(float(v.x), 3), round(float(v.y), 3), round(float(v.z), 3)]


def inventory(eas, ue):
    """Everything Task B needs to transform, in JSON-safe form."""
    inv = {"spline_actors": [], "volumes": [], "cameras": [], "terrain": []}
    for a in eas.get_all_level_actors():
        cn = a.get_class().get_name()
        if cn == "PCGVolume":
            try:
                pc = a.pcg_component
                g = pc.get_graph()
                gname = str(g.get_name()) if g else None
            except Exception:
                gname = None
            inv["volumes"].append({"label": str(a.get_actor_label()),
                                   "loc": vec(a.get_actor_location()),
                                   "graph": gname})
        if cn == "CineCameraActor":
            r = a.get_actor_rotation()
            inv["cameras"].append({"label": str(a.get_actor_label()),
                                   "loc": vec(a.get_actor_location()),
                                   "rot": [round(float(r.pitch), 3),
                                           round(float(r.yaw), 3),
                                           round(float(r.roll), 3)]})
        if "MeshPartition" in cn:
            inv["terrain"].append({"label": str(a.get_actor_label()), "class": cn})
        comps = a.get_components_by_class(ue.SplineComponent)
        if not comps:
            continue
        try:
            tags = [str(t) for t in a.get_editor_property("tags")]
        except Exception:
            tags = []
        entry = {"label": str(a.get_actor_label()), "class": cn, "tags": tags,
                 "loc": vec(a.get_actor_location()), "scale": vec(a.get_actor_scale3d()),
                 "splines": []}
        for sc in comps:
            n = int(sc.get_number_of_spline_points())
            entry["splines"].append({
                "num_points": n,
                "closed": bool(sc.is_closed_loop()),
                "points": [vec(sc.get_location_at_spline_point(
                    i, ue.SplineCoordinateSpace.WORLD))
                    for i in range(min(n, 200))],
            })
        inv["spline_actors"].append(entry)
    return inv


def run(template, target, force):
    import unreal

    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ael = unreal.EditorAssetLibrary

    out = {"template": template, "target": target,
           "current_before": str(les.get_current_level())}

    if ael.does_asset_exist(target):
        if not force:
            out["abort"] = ("target level already exists; pass force=true to "
                            "close the current level and overwrite it")
            return out
        out["existed"] = True

    attempts = []
    ok = False

    # Path 1: the documented one-call copy.
    try:
        ok = bool(les.new_level_from_template(target, template))
        attempts.append({"path": "new_level_from_template", "ok": ok})
    except Exception as ex:
        attempts.append({"path": "new_level_from_template",
                         "error": "%s: %s" % (type(ex).__name__, str(ex)[:200])})

    # Path 2: explicit new-map-from-template + save-as.
    if not ok:
        try:
            world = unreal.EditorLoadingAndSavingUtils.new_map_from_template(template, False)
            saved = bool(unreal.EditorLoadingAndSavingUtils.save_map(world, target)) if world else False
            attempts.append({"path": "new_map_from_template+save_map", "ok": saved})
            ok = saved
        except Exception as ex:
            attempts.append({"path": "new_map_from_template+save_map",
                             "error": "%s: %s" % (type(ex).__name__, str(ex)[:200])})

    out["attempts"] = attempts
    if not ok:
        out["failed"] = ("both scripted copy paths failed; ask the user to run "
                         "File > Save Current Level As from the demo level")
        return out

    out["current_after"] = str(les.get_current_level())
    out["on_target"] = target.split("/")[-1] in out["current_after"]

    inv = inventory(eas, unreal)
    out["inventory"] = inv

    # Gate: every dependency the 18 graphs read must have come across.
    tagged = {}
    for a in inv["spline_actors"]:
        for t in a["tags"]:
            tagged.setdefault(t, 0)
            tagged[t] += 1
    graphs = sorted([v["graph"] for v in inv["volumes"] if v["graph"]])
    out["gate"] = {
        "level_actors": len(eas.get_all_level_actors()),
        "terrain_actors": len(inv["terrain"]),
        "volumes": len(inv["volumes"]),
        "cameras": len(inv["cameras"]),
        "spline_actors": len(inv["spline_actors"]),
        "tagged": tagged,
        "graphs": graphs,
        "pass": (len(inv["terrain"]) >= 1 and len(inv["volumes"]) == 18
                 and len(inv["cameras"]) >= 11
                 and all(t in tagged for t in
                         ("City", "Arteries", "Highway", "Highway_Width",
                          "LandmarkPark", "Terrain_shaping_1"))),
    }
    # The 18 stage volumes must be the 18 stage graphs, one each.
    expect = ["PCG_1_1_Terrain", "PCG_1_2_BG_Buildings", "PCG_1_3_BG_Mountains",
              "PCG_2_1_MainTower_Footprint", "PCG_2_2_CentralPark_Footprint",
              "PCG_3_1_1_Districts", "PCG_3_1_2_Roads", "PCG_3_1_3_Highways",
              "PCG_3_1_4_Lots", "PCG_3_2_1_Ground", "PCG_3_2_2_LeftOverLots",
              "PCG_3_2_3_Parkings", "PCG_3_3_1_Buildings", "PCG_3_3_2_Rooftops",
              "PCG_4_1_MainTower_Visuals", "PCG_4_2_CentralPark_Visuals",
              "PCG_5_1_CityEdge", "PCG_5_2_OuterForest"]
    out["gate"]["missing_graphs"] = [g for g in expect if g not in graphs]
    out["gate"]["pass"] = bool(out["gate"]["pass"] and not out["gate"]["missing_graphs"])
    return out


try:
    _args = mcp_args if isinstance(mcp_args, dict) else {}
except NameError:
    _args = {}

try:
    RESULT = {"ok": True, "data": run(str(_args.get("template", TEMPLATE)),
                                     str(_args.get("target", TARGET)),
                                     bool(_args.get("force", False)))}
except Exception as _exc:
    RESULT = {"ok": False, "error": "%s: %s" % (type(_exc).__name__, str(_exc)[:400])}

try:
    mcp_result = json.loads(json.dumps(RESULT, default=str))
except Exception as _se:
    mcp_result = {"ok": False, "serialization_failed": str(_se)[:200]}

print(json.dumps(mcp_result, ensure_ascii=False, default=str)[:200000])
del RESULT, _args
gc.collect()
```

- [x] **Step 2: 运行它**

`run_unreal_script(script_path="pcg_sa_level.py", args={})`
Expected: `ok: true`，`data.gate.pass: true`，`data.gate.terrain_actors: 1`，`volumes: 18`，`cameras: 11`，`missing_graphs: []`。

若 `data.abort` 出现（目标已存在），说明是重跑：加 `args={"force": True}`。若 `data.failed` 出现，**停下来请用户手工另存**，不要试第三种脚本路径。

- [x] **Step 3: 把 inventory 存盘，供 Task 3 离线使用**

把 `data.inventory` 写入 `Saved/Reports/sa_inventory.json`（编辑器侧写盘用
`unreal.PythonScriptLibrary` 不可靠，改为**在 Step 2 的输出里取 JSON 后由 shell 写盘**）：

```bash
# 从桥返回的 stdout 里取 data.inventory，落盘给 Task 3 当基线
# （桥的输出已保存在 tool-results JSON 中；用 python 抽取）
C:\Python314\python.exe Tools/sa_extract_inventory.py \
    --tool-result "<上一步 tool-results 文件路径>" \
    --out Saved/Reports/sa_inventory.json
```

`Tools/sa_extract_inventory.py` 是本任务新增的小工具，读 tool-results JSON、取
`data.inventory`、写盘，并在 stdout 打印《样条 Actor 数 / 样条组件数 / 包围盒》。

- [x] **Step 4: 验证关卡资产真的在磁盘上**

Run:
```bash
ls -la Content/PCGArea/L_SmallArea18.umap
find Content/__ExternalActors__/PCGArea -type f 2>/dev/null | wc -l
```
Expected: `.umap` 存在且 mtime 是刚刚；外部 Actor 目录**可能还不存在**（取决于 WP 复制行为，见 Review Focus 5），若为空记下实际情况，Task 7 保存后再核对。

- [x] **Step 5: 确认 demo 关卡没被动**

Run:
```bash
ls -la Plugins/CitySamplePCG/Content/Levels/L_CitySamplePCG_Demo.umap
find Plugins/CitySamplePCG/Content -newermt "-10 minutes" -type f | head
```
Expected: demo `.umap` 的 mtime 仍是出厂日期（`Sep 1 11:58`）；第二条命令**无输出**。

- [x] **Step 6: 提交**

```bash
git add Content/Python/pcg_sa_level.py Tools/sa_extract_inventory.py
git commit -m "Add level derivation script that copies the demo level as a template"
```

---

## Task 3: 施加相似变换 `pcg_sa_shape`

**Files:**
- Create: `Content/Python/pcg_sa_shape.py`
- Read for context: `Saved/Reports/sa_inventory.json`（Task 2 产出）

**Interfaces:**
- Consumes: `pcg_sa_geom.scale_for_target / map_point / map_tangent / city_bbox_from_splines`；`Saved/Reports/sa_inventory.json`
- Produces: `mcp_result.data.report` —— 变换前后对照，形状为
  `{"scale", "src_center", "dst_center", "city_bbox_before", "city_bbox_after", "splines":[{"label","components","points_before","points_after","closed"}], "cameras":[...], "volumes":[{"label","loc_before","loc_after"}]}`
  —— **报告（Task 8）与技能修正（Task 10）消费它**。

- [x] **Step 1: 写脚本**

```python
# Content/Python/pcg_sa_shape.py
# Task B: shrink the copied city with ONE similarity transform.
#
# args: {"target_cm": 60000,          # the city's longer horizontal side
#        "dst_center": null,          # null = keep the source centre (stay on terrain)
#        "dry_run": false}            # true = report the plan, change nothing
#
# WHAT MOVES: every SplineComponent's points (24 actors carry them, including 3
# PCGVolumes whose subdivision splines live on the volume itself), every
# CineCameraActor's location, and every PCGVolume's location. Location is scaled
# even for the volumes whose brush is 200 cm, because it is a position, not a size.
#
# WHAT DOES NOT MOVE: lights, fog, sky, the water plane, the MeshPartition terrain
# actor (stage 1 reshapes it from the new CityShape), and the 200 cm brushes.
# The brushes are deliberately left alone: they are absolute 20 m generation bounds
# and a UObject similarity would scale their C++ collision-box representation, not
# their render geometry.
#
# Point types and tangents are preserved by editing per point and translating the
# tangents, rather than calling SetSplinePoints (which sets CurveAuto and discards
# custom tangents).

import gc
import json

TARGET_CM = 60000.0
TARGET = "/Game/PCGArea/L_SmallArea18"


def vec(v):
    return [round(float(v.x), 3), round(float(v.y), 3), round(float(v.z), 3)]


def rot(r):
    return [round(float(r.pitch), 3), round(float(r.yaw), 3), round(float(r.roll), 3)]


def run(target_cm, dst_center, dry_run):
    import unreal

    sys_path = unreal.Paths.project_content_dir() + "Python"
    if sys_path not in __import__("sys").path:
        __import__("sys").path.insert(0, sys_path)
    import pcg_sa_geom as G

    out = {"dry_run": bool(dry_run), "target_cm": float(target_cm)}
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    out["current_level"] = str(les.get_current_level())
    if TARGET.split("/")[-1] not in out["current_level"]:
        out["abort"] = "not on the derived level; open %s first" % TARGET
        return out

    # ---- collect ----
    spline_actors, volumes, cameras = [], [], []
    for a in eas.get_all_level_actors():
        cn = a.get_class().get_name()
        if cn == "CineCameraActor":
            cameras.append(a)
        if cn == "PCGVolume":
            volumes.append(a)
        if a.get_components_by_class(unreal.SplineComponent):
            spline_actors.append(a)

    # ---- source bbox from the CityShape spline(s) only ----
    shape_pts = []
    for a in spline_actors:
        try:
            tags = [str(t) for t in a.get_editor_property("tags")]
        except Exception:
            tags = []
        if "City" not in tags:
            continue
        for sc in a.get_components_by_class(unreal.SplineComponent):
            n = int(sc.get_number_of_spline_points())
            shape_pts.extend(vec(sc.get_location_at_spline_point(
                i, unreal.SplineCoordinateSpace.WORLD)) for i in range(n))
    if not shape_pts:
        out["abort"] = "no spline tagged 'City' found; cannot derive the source bbox"
        return out
    mn, mx = G.bbox_of_points(shape_pts)
    src_center = [(mn[i] + mx[i]) / 2.0 for i in range(3)]
    scale = G.scale_for_target((mn, mx), float(target_cm))
    dst = [float(v) for v in dst_center] if dst_center else list(src_center)
    out["city_bbox_before"] = [mn, mx]
    out["scale"] = scale
    out["src_center"] = src_center
    out["dst_center"] = dst
    out["city_bbox_after"] = [
        G.map_point(mn, scale, src_center, dst),
        G.map_point(mx, scale, src_center, dst),
    ]
    out["city_size_after_m"] = [
        round((out["city_bbox_after"][1][0] - out["city_bbox_after"][0][0]) / 100.0, 1),
        round((out["city_bbox_after"][1][1] - out["city_bbox_after"][0][1]) / 100.0, 1),
    ]

    # ---- splines ----
    rep_splines = []
    for a in spline_actors:
        entry = {"label": str(a.get_actor_label()),
                 "class": a.get_class().get_name(), "components": 0,
                 "points_before": 0, "points_after": 0, "closed": [], "moved": 0}
        for sc in a.get_components_by_class(unreal.SplineComponent):
            n = int(sc.get_number_of_spline_points())
            entry["components"] += 1
            entry["points_before"] += n
            entry["closed"].append(bool(sc.is_closed_loop()))
            if not dry_run:
                for i in range(n):
                    p = sc.get_location_at_spline_point(
                        i, unreal.SplineCoordinateSpace.WORLD)
                    np_ = G.map_point([p.x, p.y, p.z], scale, src_center, dst)
                    sc.set_location_at_spline_point(
                        i, unreal.Vector(np_[0], np_[1], np_[2]),
                        unreal.SplineCoordinateSpace.WORLD, False)
                    # tangents are directions: scale, do not translate
                    try:
                        t = sc.get_tangent_at_spline_point(
                            i, unreal.SplineCoordinateSpace.WORLD)
                        nt = G.map_tangent([t.x, t.y, t.z], scale)
                        sc.set_tangent_at_spline_point(
                            i, unreal.Vector(nt[0], nt[1], nt[2]),
                            unreal.SplineCoordinateSpace.WORLD, False)
                    except Exception:
                        pass          # LINEAR points carry no meaningful tangent
                sc.update_spline()
            entry["points_after"] += int(sc.get_number_of_spline_points())
            entry["moved"] += n
        # the actor itself is a position too: move it so the gizmo stays on the spline
        if not dry_run:
            loc = a.get_actor_location()
            nl = G.map_point([loc.x, loc.y, loc.z], scale, src_center, dst)
            a.set_actor_location(unreal.Vector(nl[0], nl[1], nl[2]), False, False)
        rep_splines.append(entry)
    out["splines"] = rep_splines

    # ---- cameras ----
    rep_cams = []
    for a in cameras:
        loc = a.get_actor_location()
        nl = G.map_point([loc.x, loc.y, loc.z], scale, src_center, dst)
        rep_cams.append({"label": str(a.get_actor_label()),
                         "loc_before": vec(loc), "loc_after": [round(v, 3) for v in nl]})
        if not dry_run:
            a.set_actor_location(unreal.Vector(nl[0], nl[1], nl[2]), False, False)
    out["cameras"] = rep_cams

    # ---- volume locations (brush deliberately untouched) ----
    rep_vols = []
    for a in volumes:
        loc = a.get_actor_location()
        nl = G.map_point([loc.x, loc.y, loc.z], scale, src_center, dst)
        rep_vols.append({"label": str(a.get_actor_label()),
                         "loc_before": vec(loc), "loc_after": [round(v, 3) for v in nl]})
        if not dry_run:
            a.set_actor_location(unreal.Vector(nl[0], nl[1], nl[2]), False, False)
    out["volumes"] = rep_vols

    out["summary"] = {
        "spline_actors": len(rep_splines),
        "spline_components": sum(e["components"] for e in rep_splines),
        "spline_points": sum(e["points_before"] for e in rep_splines),
        "cameras": len(rep_cams),
        "volumes": len(rep_vols),
    }
    return out


try:
    _args = mcp_args if isinstance(mcp_args, dict) else {}
except NameError:
    _args = {}

try:
    RESULT = {"ok": True, "data": run(_args.get("target_cm", TARGET_CM),
                                     _args.get("dst_center", None),
                                     bool(_args.get("dry_run", False)))}
except Exception as _exc:
    RESULT = {"ok": False, "error": "%s: %s" % (type(_exc).__name__, str(_exc)[:400])}

try:
    mcp_result = json.loads(json.dumps(RESULT, default=str))
except Exception as _se:
    mcp_result = {"ok": False, "serialization_failed": str(_se)[:200]}

print(json.dumps(mcp_result, ensure_ascii=False, default=str)[:200000])
del RESULT, _args
gc.collect()
```

- [x] **Step 2: 先 dry run，核对计划**

`run_unreal_script(script_path="pcg_sa_shape.py", args={"dry_run": true})`
Expected:
- `data.abort` 不出现（若出现，先开新关卡）
- `data.scale` ≈ **0.2817**
- `data.src_center` ≈ `[-9485, 6937, 0]`
- `data.city_size_after_m` ≈ `[600, 512]`（±5 %）
- `summary.spline_actors` = **24**，`spline_components` = **95**，`spline_points` ≈ **370**
- `summary.cameras` = 11，`volumes` = 18

若 `spline_actors` 不是 24（例如 18 或 19），说明 WP 关卡里有 Actor 没加载：报出实际值并停下，先解决加载问题，不要带病继续。

- [x] **Step 3: 真施加**

`run_unreal_script(script_path="pcg_sa_shape.py", args={})`
Expected: 同 Step 2 的字段，且 `dry_run: false`、`splines[*].points_after == points_before`（点数不变）、`closed` 数组与之前一致。

- [x] **Step 4: 读回验证（独立于上一步）**

`run_unreal_script(script_path="pcg_sa_shape.py", args={"dry_run": true})`
Expected: **同一次 dry_run 现在读到的是变换后的值**——`src_center` 应≈新的城市中心、`scale` 应≈1.0（因为已经缩过了），`city_size_after_m` ≈ `[600, 512]`。这是「变换确实生效」的独立证据：如果 scale 还是 0.28，说明 Step 3 什么都没改。

- [x] **Step 5: 提交**

```bash
git add Content/Python/pcg_sa_shape.py
git commit -m "Add the similarity-transform step that shrinks the copied city to 600 m"
```

---

## Task 4: 生成前的清场与阶段生成 `pcg_sa_run`（cleanup_all / gen / apply_camera）

**Files:**
- Create: `Content/Python/pcg_sa_run.py`
- Read for context: `Content/Python/pcg_shots.py`（`comps()` / `set_vis_all()` / `take_high_res_screenshot` 的调用式样）、`Content/Python/pcg_stage_run.py`

**Interfaces:**
- Consumes: `pcg_sa_geom.orbit_camera / bbox_of_points`；新关卡里的 18 个 Volume
- Produces: `pcg_sa_run.py` 的 phase 词表与返回结构，**Task 5/6/7 都按它写**：
  - `cleanup_all` → `{"cleaned": n_volumes}`
  - `gen` → `{"stage", "graph", "cleared_flags", "flagged", "flagged_nodes", "activated", "fired"}`
  - `apply_camera` → `{"stage", "camera", "loc", "rot", "mode"}`（`mode` 是 `computed` 或 `cine`）
  - `probe` → `{"stage", "volumes", "real_components", "debug_components", "real_instances", "debug_instances", "generated"}`

- [x] **Step 1: 写脚本的骨架与四个 phase**

```python
# Content/Python/pcg_sa_run.py
# Stage runner for the small-area 18-stage run.
#
# args: {"phase": "cleanup_all" | "gen" | "apply_camera" | "probe",
#        "stage": 1..18,
#        "target_cm": 60000,        # for the computed camera
#        "debug_nodes": 4,          # how many nodes to flag per stage
#        "camera_mode": "computed"} # "computed" | "cine"
#
# ONE PHASE PER CALL. Generation is asynchronous and generate_local returns
# immediately, so a read in the same call is always empty and never errors.
# The capture phases live in pcg_sa_shots.py; the split keeps each script small
# enough to hold in context, which is where these scripts have historically gone
# wrong.
#
# DEBUG FLAGGING: there is no global PCG debug switch (every pcg.* cvar reads
# empty/0 and PCGComponent has no debug member); it is the per-node `debug` bool on
# PCGSettings. Flagging all nodes of all 18 graphs produced 20,570,859 debug cubes
# and killed the editor at 92 GB, so this flags at most `debug_nodes` per stage.
#
# GLOBAL DISCIPLINE: no UObject survives this script. See the plan's constraints.

import gc
import json
import time

TARGET = "/Game/PCGArea/L_SmallArea18"
DEBUG_CUBE = "/PCG/DebugObjects/"
ORDER = [
    "PCG_1_1_Terrain", "PCG_1_2_BG_Buildings", "PCG_1_3_BG_Mountains",
    "PCG_2_1_MainTower_Footprint", "PCG_2_2_CentralPark_Footprint",
    "PCG_3_1_1_Districts", "PCG_3_1_2_Roads", "PCG_3_1_3_Highways",
    "PCG_3_1_4_Lots", "PCG_3_2_1_Ground", "PCG_3_2_2_LeftOverLots",
    "PCG_3_2_3_Parkings", "PCG_3_3_1_Buildings", "PCG_3_3_2_Rooftops",
    "PCG_4_1_MainTower_Visuals", "PCG_4_2_CentralPark_Visuals",
    "PCG_5_1_CityEdge", "PCG_5_2_OuterForest",
]
# Which cine camera suits which stage, when camera_mode="cine".
CINE = {1: "City_WideView_1", 2: "City_WideView_1", 3: "City_WideView_1",
        4: "Building_Edit", 5: "CentralPark_1", 6: "City_WideView_2",
        7: "Street_1", 8: "HighWayEdit", 9: "Street_2", 10: "Street_3",
        11: "Street_2", 12: "Street_3", 13: "Building_Edit",
        14: "Building_Edit", 15: "City_WideView_1", 16: "CentralPark_1",
        17: "City_WideView_2", 18: "City_WideView_1"}
# The computed orbit per stage: (bearing deg, elevation deg, distance multiple).
# Wide stages look from the same bearing as Epic's City_WideView_1 (roughly +X,
# looking back toward -X); ground-level stages come down low from the south.
ORBIT = {1: (0, 32, 2.6), 2: (0, 20, 2.8), 3: (20, 12, 6.0), 4: (90, 30, 1.6),
         5: (135, 28, 1.8), 6: (0, 38, 2.4), 7: (-60, 22, 2.0), 8: (60, 18, 2.6),
         9: (170, 30, 2.0), 10: (-100, 12, 2.0), 11: (150, 18, 2.0),
         12: (150, 14, 1.8), 13: (30, 20, 2.2), 14: (30, 45, 2.2),
         15: (90, 30, 1.8), 16: (135, 24, 2.2), 17: (-30, 16, 2.2),
         18: (0, 24, 4.0)}


def vol_by_label(eas, label):
    for a in eas.get_all_level_actors():
        try:
            if a.get_class().get_name() == "PCGVolume" and str(a.get_actor_label()) == label:
                return a
        except Exception:
            continue
    return None


def comps(volume):
    """(component, instance_count, mesh_path) for every comp with instances."""
    out = []
    for c in volume.get_components_by_class(unreal.PrimitiveComponent):
        if c.get_class().get_name() == "BrushComponent":
            continue
        try:
            n = c.get_instance_count()
        except Exception:
            continue
        if not n:
            continue
        m = ""
        try:
            sm = c.get_editor_property("static_mesh")
            if sm:
                m = str(sm.get_path_name())
        except Exception:
            pass
        out.append((c, n, m))
    return out


def counted(volume):
    """(real_instances, debug_instances, real_components, debug_components)."""
    real_n = dbg_n = real_c = dbg_c = 0
    for c, n, m in comps(volume):
        if m.startswith(DEBUG_CUBE):
            dbg_n += n
            dbg_c += 1
        else:
            real_n += n
            real_c += 1
    return real_n, dbg_n, real_c, dbg_c


def all_volumes(eas):
    return [a for a in eas.get_all_level_actors()
            if a.get_class().get_name() == "PCGVolume"]


def city_bbox(eas, ue):
    """Union bbox of the splines tagged City, for framing the computed camera."""
    pts = []
    for a in eas.get_all_level_actors():
        try:
            tags = [str(t) for t in a.get_editor_property("tags")]
        except Exception:
            tags = []
        if "City" not in tags:
            continue
        for sc in a.get_components_by_class(ue.SplineComponent):
            n = int(sc.get_number_of_spline_points())
            for i in range(n):
                p = sc.get_location_at_spline_point(i, ue.SplineCoordinateSpace.WORLD)
                pts.append([p.x, p.y, p.z])
    return pts


def phase_cleanup_all(eas):
    n = 0
    for v in all_volumes(eas):
        try:
            v.pcg_component.cleanup_local(True)
            n += 1
        except Exception:
            pass
    return {"cleaned": n}


def phase_gen(eas, stage, debug_nodes):
    import unreal
    label = ORDER[stage - 1]
    vol = vol_by_label(eas, label)
    if vol is None:
        return {"err": "no volume labelled %s" % label}
    pc = vol.pcg_component
    g = pc.get_graph()
    info = {"stage": stage, "graph": label, "cleared_flags": 0, "flagged": 0,
            "flagged_nodes": [], "activated": False, "fired": False}
    if g is None:
        info["err"] = "volume %s has no graph" % label
        return info

    # 1. clear every node's flag on this graph
    nodes = g.get_editor_property("nodes")
    for nd in nodes:
        try:
            st = nd.get_settings()
            if st is not None and st.get_editor_property("debug"):
                st.set_editor_property("debug", False)
                info["cleared_flags"] += 1
        except Exception:
            continue

    # 2. flag the nodes that actually produce this stage's data: walk the output
    #    node's incoming edges and take its direct predecessors, then go one hop
    #    further back if there are not enough of them.
    chosen = []

    def predecessors(node):
        found = []
        for pin in node.get_editor_property("input_pins"):
            for e in pin.edges:
                try:
                    a = e.get_output_node()
                    b = e.get_input_node()
                except Exception:
                    continue
                other = b if a == node else a
                if other is not None and other != node and other not in found:
                    found.append(other)
        return found

    try:
        out_node = g.get_output_node()
    except Exception:
        out_node = None
    if out_node is not None:
        first = predecessors(out_node)
        chosen.extend(first)
        if len(chosen) < debug_nodes:
            for nd in list(first):
                for extra in predecessors(nd):
                    if extra not in chosen:
                        chosen.append(extra)
                    if len(chosen) >= debug_nodes:
                        break
                if len(chosen) >= debug_nodes:
                    break
    if not chosen:                     # fall back to the first few nodes
        chosen = list(nodes[:debug_nodes])
    for nd in chosen[:debug_nodes]:
        try:
            st = nd.get_settings()
            if st is None:
                continue
            st.set_editor_property("debug", True)
            info["flagged"] += 1
            try:
                info["flagged_nodes"].append(str(st.get_class().get_name()))
            except Exception:
                info["flagged_nodes"].append("?")
        except Exception:
            continue

    # 3. activate then generate. A freshly spawned/copied component needs the
    #    explicit activate() or ShouldGenerate() is false and nothing happens,
    #    silently and without error.
    try:
        pc.activate(True)
        info["activated"] = bool(pc.get_editor_property("activated"))
    except Exception as ex:
        info["activate_err"] = str(ex)[:120]
    t0 = time.time()
    try:
        pc.generate_local(True)
        info["fired"] = True
    except Exception as ex:
        info["gen_err"] = str(ex)[:160]
    info["sec"] = round(time.time() - t0, 2)
    return info


def phase_apply_camera(eas, les, stage, camera_mode, target_cm):
    import unreal
    import sys
    cdir = unreal.Paths.project_content_dir() + "Python"
    if cdir not in sys.path:
        sys.path.insert(0, cdir)
    import pcg_sa_geom as G

    if camera_mode == "cine":
        frag = CINE.get(stage, "City_WideView_1")
        for a in eas.get_all_level_actors():
            try:
                if (a.get_class().get_name() == "CineCameraActor"
                        and frag in str(a.get_actor_label())):
                    loc = a.get_actor_location()
                    les.set_level_viewport_camera_info(
                        loc, a.get_actor_rotation(),
                        les.get_active_viewport_config_key())
                    return {"stage": stage, "camera": frag, "mode": "cine",
                            "loc": [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)]}
            except Exception:
                continue
        return {"stage": stage, "camera": frag, "mode": "cine", "err": "not found"}

    pts = city_bbox(eas, unreal)
    if not pts:
        return {"stage": stage, "mode": "computed", "err": "no City spline"}
    mn, mx = G.bbox_of_points(pts)
    center = [(mn[i] + mx[i]) / 2.0 for i in range(3)]
    radius = 0.5 * max(mx[0] - mn[0], mx[1] - mn[1])
    az, elev, mult = ORBIT.get(stage, (0, 30, 2.4))
    loc, rot = G.orbit_camera(center, radius, az, elev, mult, min_height=radius * 0.6)
    les.set_level_viewport_camera_info(
        unreal.Vector(loc[0], loc[1], loc[2]),
        unreal.Rotator(rot[0], rot[1], rot[2]),
        les.get_active_viewport_config_key())
    return {"stage": stage, "mode": "computed", "center": [round(v, 1) for v in center],
            "radius": round(radius, 1), "loc": [round(v, 1) for v in loc],
            "rot": [round(v, 2) for v in rot]}


def phase_probe(eas, stage):
    label = ORDER[stage - 1]
    vol = vol_by_label(eas, label)
    if vol is None:
        return {"err": "no volume labelled %s" % label}
    real_n, dbg_n, real_c, dbg_c = counted(vol)
    gen = None
    try:
        gen = bool(vol.pcg_component.get_editor_property("generated"))
    except Exception:
        pass
    return {"stage": stage, "graph": label, "generated": gen,
            "real_instances": real_n, "debug_instances": dbg_n,
            "real_components": real_c, "debug_components": dbg_c,
            "suspect_zero": bool(real_n == 0 and stage not in (1, 4, 5, 6))}


def run(phase, stage, debug_nodes, camera_mode, target_cm):
    import unreal
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    cur = str(les.get_current_level())
    if TARGET.split("/")[-1] not in cur:
        return {"abort": "not on %s (current: %s)" % (TARGET, cur)}
    if phase == "cleanup_all":
        return phase_cleanup_all(eas)
    if stage is None:
        return {"abort": "phase %s needs a stage" % phase}
    s = int(stage)
    if not 1 <= s <= 18:
        return {"abort": "stage out of range: %s" % stage}
    if phase == "gen":
        return phase_gen(eas, s, debug_nodes)
    if phase == "apply_camera":
        return phase_apply_camera(eas, les, s, camera_mode, target_cm)
    if phase == "probe":
        return phase_probe(eas, s)
    return {"abort": "unknown phase %s" % phase}


try:
    _args = mcp_args if isinstance(mcp_args, dict) else {}
except NameError:
    _args = {}

try:
    RESULT = {"ok": True, "data": run(str(_args.get("phase", "probe")),
                                     _args.get("stage", None),
                                     int(_args.get("debug_nodes", 4)),
                                     str(_args.get("camera_mode", "computed")),
                                     float(_args.get("target_cm", 60000.0)))}
except Exception as _exc:
    RESULT = {"ok": False, "error": "%s: %s" % (type(_exc).__name__, str(_exc)[:400])}

try:
    mcp_result = json.loads(json.dumps(RESULT, default=str))
except Exception as _se:
    mcp_result = {"ok": False, "serialization_failed": str(_se)[:200]}

print(json.dumps(mcp_result, ensure_ascii=False, default=str)[:200000])
del RESULT, _args
gc.collect()
```

- [x] **Step 2: 清场**

`run_unreal_script(script_path="pcg_sa_run.py", args={"phase": "cleanup_all"})`
Expected: `data.cleaned: 18`

- [x] **Step 3: 生成阶段 1 并核对**

`run_unreal_script(script_path="pcg_sa_run.py", args={"phase": "gen", "stage": 1})`
Expected: `data.fired: true`，`data.activated: true`，`data.flagged: 4`，`data.flagged_nodes` 有 4 个类名，`data.err` 不出现。

- [x] **Step 4: 下一次调用读阶段 1**

`run_unreal_script(script_path="pcg_sa_run.py", args={"phase": "probe", "stage": 1})`
Expected: `data.generated: true`；阶段 1 是数据阶段，`real_instances` 可能是 0（地形写进 MeshTerrain，不是实例），`debug_instances` **必须 > 0**（否则 debug flag 没生效）。

- [x] **Step 5: 机位验证**

`run_unreal_script(script_path="pcg_sa_run.py", args={"phase": "apply_camera", "stage": 1})`
Expected: `mode: computed`，`center` ≈ 新城市中心（≈ `[-9485, 6937, 0]`），`radius` ≈ **30000 cm**（600 m 城市的一半），`loc` 在 `center` 之外 2.6×半径 的方向上、z 大于 0。

- [x] **Step 6: 提交**

```bash
git add Content/Python/pcg_sa_run.py
git commit -m "Add the small-area stage runner: cleanup, generate, camera, probe"
```

---

## Task 5: 截图与收尾 `pcg_sa_shots`（shot_debug / shot_geom / finish / census）

**Files:**
- Create: `Content/Python/pcg_sa_shots.py`
- Read for context: `Content/Python/pcg_shots.py` 的 `shot` / `run` 两个 phase（隔离与截图式样）、`Content/Python/pcg_stage_run.py` 的 `debug_off`

**Interfaces:**
- Consumes: `pcg_sa_run.py` 的 `ORDER` / `DEBUG_CUBE` / `comps()` / `counted()` / `vol_by_label()` / `phase_apply_camera()`（用 `import pcg_sa_run` 复用，不复制代码）
- Produces: `Saved/Screenshots/WindowsEditor/sa_stage_NN_<graph>_debug.png` 与 `_geometry.png`；`Saved/Reports/sa_census.json` 累积文件；`finish` → `{"saved", "debug_flags_cleared", "packages_after", "epic_touched"}`

- [x] **Step 1: 写脚本**

```python
# Content/Python/pcg_sa_shots.py
# Capture + teardown for the small-area run. Imports the runner rather than
# copying it, so the volume/instance logic has exactly one definition.
#
# args: {"phase": "shot_debug" | "shot_geom" | "finish" | "census",
#        "stage": 1..18,
#        "max_debug_shown": 3,
#        "target_cm": 60000}
#
# TWO KINDS OF PICTURE, and why they differ:
#   debug    - isolated: only this stage's volume is visible, and only the first
#              max_debug_shown debug-cube components. This is the evidence that
#              THIS stage's flagged nodes produced data.
#   geometry - cumulative: volumes 1..stage visible with all real geometry, every
#              debug cube hidden. The difference between consecutive geometry
#              shots is what each stage added to the city.
# The 09-23 run's manual visibility toggling was the fragile part; it is the same
# primitive here, just applied with the two rules above.
#
# ONE SHOT PER CALL, ALWAYS. take_high_res_screenshot writes on a later frame, so a
# second call in the same script overwrites the first.

import gc
import json
import os
import sys

TARGET = "/Game/PCGArea/L_SmallArea18"
SHOT_DIR = "Screenshots/WindowsEditor"
CENSUS = "Reports/sa_census.json"


def ensure_import_path():
    import unreal
    cdir = unreal.Paths.project_content_dir() + "Python"
    if cdir not in sys.path:
        sys.path.insert(0, cdir)
    import pcg_sa_run
    return pcg_sa_run


def visible_set(run, eas, show_upto, hide_debug=True, only_vol=None,
                max_debug_shown=3):
    """Show exactly the components the rule asks for; return what was done."""
    shown = 0
    hidden = 0
    for v in run.all_volumes(eas):
        label = str(v.get_actor_label())
        try:
            idx = run.ORDER.index(label) + 1
        except ValueError:
            idx = 0
        keep_volume = (only_vol is not None and v == only_vol) or \
                      (only_vol is None and 0 < idx <= show_upto)
        real = [(c, n, m) for c, n, m in run.comps(v) if not m.startswith(run.DEBUG_CUBE)]
        dbg = [(c, n, m) for c, n, m in run.comps(v) if m.startswith(run.DEBUG_CUBE)]
        for c, _n, _m in real:
            try:
                c.set_visibility(keep_volume, True)
                shown += 1 if keep_volume else 0
                hidden += 0 if keep_volume else 1
            except Exception:
                pass
        dbg.sort(key=lambda e: -e[1])
        for i, (c, _n, _m) in enumerate(dbg):
            want = (keep_volume and only_vol is not None and not hide_debug
                    and i < max_debug_shown)
            try:
                c.set_visibility(want, True)
                shown += 1 if want else 0
                hidden += 0 if want else 1
            except Exception:
                pass
    return {"shown": shown, "hidden": hidden}


def fire(name):
    import unreal
    try:
        t = unreal.AutomationLibrary.take_high_res_screenshot(
            1600, 900, name, None, False, False, force_game_view=False)
        return {"fired": name, "valid": str(t.is_valid_task()) if t else None}
    except Exception as ex:
        return {"fired": name, "shot_err": "%s: %s" % (type(ex).__name__, str(ex)[:180])}


def shot_path(name):
    import unreal
    return os.path.join(unreal.Paths.project_saved_dir(), SHOT_DIR, name)


def update_census(stage, graph, real_n, dbg_n):
    import unreal
    p = os.path.join(unreal.Paths.project_saved_dir(), CENSUS)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    data = {}
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            data = {}
    data.setdefault("order", run_order())
    data.setdefault("real_instances", {})
    data.setdefault("debug_instances", {})
    data["real_instances"][str(stage)] = int(real_n)
    data["debug_instances"][str(stage)] = int(dbg_n)
    data["_level"] = TARGET
    data["_note"] = ("real = non-debug instanced geometry; debug = PCG debug cubes "
                     "under /PCG/DebugObjects/")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    return p


def run_order():
    return ["PCG_1_1_Terrain", "PCG_1_2_BG_Buildings", "PCG_1_3_BG_Mountains",
            "PCG_2_1_MainTower_Footprint", "PCG_2_2_CentralPark_Footprint",
            "PCG_3_1_1_Districts", "PCG_3_1_2_Roads", "PCG_3_1_3_Highways",
            "PCG_3_1_4_Lots", "PCG_3_2_1_Ground", "PCG_3_2_2_LeftOverLots",
            "PCG_3_2_3_Parkings", "PCG_3_3_1_Buildings", "PCG_3_3_2_Rooftops",
            "PCG_4_1_MainTower_Visuals", "PCG_4_2_CentralPark_Visuals",
            "PCG_5_1_CityEdge", "PCG_5_2_OuterForest"]


def run(phase, stage, max_debug_shown, target_cm):
    import unreal
    run_mod = ensure_import_path()
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    cur = str(les.get_current_level())
    if TARGET.split("/")[-1] not in cur:
        return {"abort": "not on %s (current: %s)" % (TARGET, cur)}

    if phase == "finish":
        out = {}
        cleared = 0
        for label in run_order():
            v = run_mod.vol_by_label(eas, label)
            if v is None:
                continue
            try:
                g = v.pcg_component.get_graph()
                for nd in g.get_editor_property("nodes"):
                    st = nd.get_settings()
                    if st is not None and st.get_editor_property("debug"):
                        st.set_editor_property("debug", False)
                        cleared += 1
            except Exception:
                continue
        out["debug_flags_cleared"] = cleared
        out["restored"] = visible_set(run_mod, eas, 18, hide_debug=True,
                                      only_vol=None)["shown"]
        # Only the derived level is saved, never a graph asset or the demo level.
        try:
            out["saved"] = bool(les.save_current_level())
        except Exception as ex:
            out["save_err"] = "%s: %s" % (type(ex).__name__, str(ex)[:200])
        try:
            dirty = unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
            out["still_dirty_map_packages"] = sorted(str(p.get_name()) for p in dirty)
        except Exception as ex:
            out["dirty_err"] = str(ex)[:120]
        out["epic_touched"] = [p for p in out.get("still_dirty_map_packages", [])
                               if "CitySamplePCG" in p]
        return out

    if phase == "census":
        out = {"stages": {}}
        for i, label in enumerate(run_order(), start=1):
            v = run_mod.vol_by_label(eas, label)
            if v is None:
                out["stages"][str(i)] = {"graph": label, "err": "no volume"}
                continue
            real_n, dbg_n, real_c, dbg_c = run_mod.counted(v)
            gen = None
            try:
                gen = bool(v.pcg_component.get_editor_property("generated"))
            except Exception:
                pass
            out["stages"][str(i)] = {"graph": label, "generated": gen,
                                     "real_instances": real_n,
                                     "debug_instances": dbg_n,
                                     "real_components": real_c,
                                     "debug_components": dbg_c,
                                     "suspect_zero": bool(
                                         real_n == 0 and i not in (1, 4, 5, 6))}
            update_census(i, label, real_n, dbg_n)
        return out

    if stage is None:
        return {"abort": "phase %s needs a stage" % phase}
    s = int(stage)
    label = run_order()[s - 1]
    vol = run_mod.vol_by_label(eas, label)
    if vol is None:
        return {"abort": "no volume labelled %s" % label}

    # the camera is re-applied on every capture: visibility changes do not move the
    # view, but a previous stage's camera may still be set, and a wrong camera is
    # the single easiest way to produce an unreadable frame.
    cam = run_mod.phase_apply_camera(eas, les, s, "computed", float(target_cm))

    if phase == "shot_debug":
        vis = visible_set(run_mod, eas, 0, hide_debug=False, only_vol=vol,
                          max_debug_shown=int(max_debug_shown))
        name = "sa_stage_%02d_%s_debug.png" % (s, label)
        r = fire(name)
        r.update({"stage": s, "graph": label, "kind": "debug", "vis": vis,
                  "cam": cam})
        p = shot_path(name)
        r["exists"] = os.path.exists(p)
        r["bytes"] = os.path.getsize(p) if r["exists"] else 0
        return r

    if phase == "shot_geom":
        vis = visible_set(run_mod, eas, s, hide_debug=True, only_vol=None)
        real_n, dbg_n, real_c, dbg_c = run_mod.counted(vol)
        name = "sa_stage_%02d_%s_geometry.png" % (s, label)
        r = fire(name)
        r.update({"stage": s, "graph": label, "kind": "geometry", "vis": vis,
                  "cam": cam, "real_instances": real_n, "debug_instances": dbg_n,
                  "real_components": real_c, "debug_components": dbg_c,
                  "suspect_zero": bool(real_n == 0 and s not in (1, 4, 5, 6))})
        p = shot_path(name)
        r["exists"] = os.path.exists(p)
        r["bytes"] = os.path.getsize(p) if r["exists"] else 0
        r["census"] = update_census(s, label, real_n, dbg_n)
        return r

    return {"abort": "unknown phase %s" % phase}


try:
    _args = mcp_args if isinstance(mcp_args, dict) else {}
except NameError:
    _args = {}

try:
    RESULT = {"ok": True, "data": run(str(_args.get("phase", "census")),
                                     _args.get("stage", None),
                                     int(_args.get("max_debug_shown", 3)),
                                     float(_args.get("target_cm", 60000.0)))}
except Exception as _exc:
    RESULT = {"ok": False, "error": "%s: %s" % (type(_exc).__name__, str(_exc)[:400])}

try:
    mcp_result = json.loads(json.dumps(RESULT, default=str))
except Exception as _se:
    mcp_result = {"ok": False, "serialization_failed": str(_se)[:200]}

print(json.dumps(mcp_result, ensure_ascii=False, default=str)[:200000])
del RESULT, _args
gc.collect()
```

- [x] **Step 2: 阶段 1 的 debug 张**

`run_unreal_script(script_path="pcg_sa_shots.py", args={"phase": "shot_debug", "stage": 1})`
Expected: `data.fired` 是文件名，`data.cam.mode: computed`，`data.vis.hidden` > 0（别的阶段被隐藏），`data.exists` 可能仍是 `false`（下一帧才写盘）。

- [x] **Step 3: 确认图落地并看图**

Run:
```bash
ls -la Saved/Screenshots/WindowsEditor/sa_stage_01_PCG_1_1_Terrain_debug.png
```
Expected: 文件存在且 > 50 KB。**用 Read 工具打开这张 PNG 亲眼看一眼**：600 m 的城市应该占据画面中部，不是空天、不是贴脸。若不对，调 `pcg_sa_run.ORBIT[stage]` 的仰角/距离后重截（只改常量，不改逻辑）。

- [x] **Step 4: 阶段 1 的 geometry 张**

`run_unreal_script(script_path="pcg_sa_shots.py", args={"phase": "shot_geom", "stage": 1})`
Expected: `data.exists: true`（这一步之前有一个完整往返，上一张已落盘），`data.real_instances` 为 0（数据阶段），`data.suspect_zero: false`（阶段 1 在豁免名单里），`data.census` 指向 `Saved/Reports/sa_census.json`。

- [x] **Step 5: 提交**

```bash
git add Content/Python/pcg_sa_shots.py
git commit -m "Add the capture and teardown script for the small-area run"
```

---

## Task 6: 跑完 18 阶段

**Files:**
- Create: `Tools/run_sa_stages.ps1`（驱动脚本，把逐阶段的三次调用与核对固化下来）
- Modify: 无
- Output: 36 张 PNG；`Saved/Reports/sa_census.json`

**Interfaces:**
- Consumes: `pcg_sa_run.py` 的 `gen` / `probe` / `apply_camera`；`pcg_sa_shots.py` 的 `shot_debug` / `shot_geom`；由我（执行者）逐次经 `run_unreal_script` 调用
- Produces: `Saved/Reports/sa_run_log.json` —— 每个阶段的 `gen` / `shot_debug` / `shot_geom` 返回原文，**Task 7/8 消费它**

- [ ] **Step 1: 写驱动脚本**

```powershell
# Tools/run_sa_stages.ps1
# 18 stages x 3 calls, in the order the async pipeline requires:
#   gen N  ->  shot_debug N  ->  shot_geom N
# The gap between gen and shot_debug is a full MCP round trip, which is what lets
# generation settle; shot_geom then also reads the instance counts, so the numbers
# in the census come from a settled state.
#
# It does NOT talk to the bridge itself: run_unreal_script is a tool the agent
# calls. This script prints the exact sequence with the args to use, so the run is
# reproducible by hand and the log file has one line per call.
param([switch]$PrintOnly)

$stages = 1..18
$lines = @()
foreach ($n in $stages) {
    $lines += "pcg_sa_run.py  phase=gen         stage=$n"
    $lines += "pcg_sa_shots.py phase=shot_debug stage=$n"
    $lines += "pcg_sa_shots.py phase=shot_geom  stage=$n"
}
$lines += "pcg_sa_run.py  phase=cleanup_all   (only if a stage must be redone)"
$lines += "pcg_sa_shots.py phase=census"
$lines += "pcg_sa_shots.py phase=finish"

if ($PrintOnly) { $lines | ForEach-Object { Write-Output $_ }; exit 0 }
$lines | Set-Content -Encoding utf8 Saved/Reports/sa_call_sequence.txt
Write-Output "wrote Saved/Reports/sa_call_sequence.txt ($($lines.Count) calls)"
```

- [ ] **Step 2: 打印调用序列**

Run: `powershell -File Tools/run_sa_stages.ps1 -PrintOnly`
Expected: 56 行（18×3 + 2 条收尾），每条一眼看清用哪个脚本、哪个 phase、哪个 stage。

- [ ] **Step 3: 逐阶段执行，把返回原文追加到 `Saved/Reports/sa_run_log.json`**

执行者循环 18 次，每次三步，并把三次返回的 JSON 追加进 log：
`{"stage": n, "gen": {...}, "shot_debug": {...}, "shot_geom": {...}}`

**每阶段结束后的判定**（任一不满足就停下处理，不要继续堆）：
- `gen.fired == true` 且 `gen.activated == true`
- `shot_debug.exists == true` 且 `bytes > 50000`
- `shot_geom.exists == true` 且 `bytes > 50000`
- `shot_geom.suspect_zero == false`，除非该阶段是 1/4/5/6

- [ ] **Step 4: 抽看三个关键阶段的图**

用 Read 工具打开这三张，确认画面合理：
- `sa_stage_07_PCG_3_1_2_Roads_geometry.png`（路网是否成网）
- `sa_stage_13_PCG_3_3_1_Buildings_geometry.png`（建筑是否成片）
- `sa_stage_13_PCG_3_3_1_Buildings_debug.png`（debug 立方体是否可见）

若这三张里有任何一张是空天或只有地形，回到 `pcg_sa_run.ORBIT` 调机位重截该阶段，并把调整写进 log。

- [ ] **Step 5: 收尾并核对**

`run_unreal_script(script_path="pcg_sa_shots.py", args={"phase": "census"})`
Expected: 18 个阶段的数字齐；`suspect_zero` 只可能出现在因美术而空的数据阶段之外——若有，记下阶段号。

`run_unreal_script(script_path="pcg_sa_shots.py", args={"phase": "finish"})`
Expected: `saved: true`，`epic_touched: []`（**空的**，表示没有任何 `/CitySamplePCG/` 的包被标脏）。

- [ ] **Step 6: 验证保存真的落地了**

Run:
```bash
ls -la Content/PCGArea/L_SmallArea18.umap
find Content/__ExternalActors__/PCGArea -type f 2>/dev/null | wc -l
du -sh Content/__ExternalActors__/PCGArea 2>/dev/null
ls -la Plugins/CitySamplePCG/Content/Levels/L_CitySamplePCG_Demo.umap
```
Expected: 新关卡 mtime 是刚刚；外部 Actor 目录**有文件**（若为 0，说明 `save_current_level()` 没带外部 Actor 包，按 Review Focus 5 回退：用 `get_dirty_map_packages()` 收集后 `save_packages` 逐个保存，并把结论写进 Task 10 的技能修正）；demo 关卡 mtime 不变。

- [ ] **Step 7: 提交**

```bash
git add Tools/run_sa_stages.ps1 Content/PCGArea/L_SmallArea18.umap
git add Content/__ExternalActors__/PCGArea 2>/dev/null || true
git commit -m "Run all 18 City Sample PCG stages on the 600 m area and capture each"
```

---

## Task 7: 报告清单工具 `Tools/sa_manifest.py`

**Files:**
- Create: `Tools/sa_manifest.py`
- Test: `Tools/tests/test_sa_manifest.py`

**Interfaces:**
- Consumes: `Saved/Reports/sa_census.json`（Task 5 产出，键是 `"1".."18"` 字符串）、`Saved/Screenshots/WindowsEditor/sa_stage_*.png`
- Produces: 报告清单 JSON，形状为
  `{"title","subtitle","level","stages":[{"n","graph","label","shots":[{"kind","path","img_missing"?}],"metrics":{"instances","debug_instances","status"},"notes"}],"footer"}`，
  且 **`stages[i].shots` 永远是两个元素**（`kind` 为 `"debug"` 与 `"geometry"`），缺图时该元素只有 `img_missing`。Task 8 直接消费它。

- [ ] **Step 1: 写失败的测试**

```python
# Tools/tests/test_sa_manifest.py
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import sa_manifest as M


def test_two_shot_names_are_suffixed_by_kind():
    assert M.shot_name(7, "PCG_3_1_2_Roads", "debug") == \
        "sa_stage_07_PCG_3_1_2_Roads_debug.png"
    assert M.shot_name(13, "PCG_3_3_1_Buildings", "geometry") == \
        "sa_stage_13_PCG_3_3_1_Buildings_geometry.png"


def test_status_is_empty_only_for_data_stages_with_zero_geometry():
    # stage 6 is a data stage: zero geometry is expected, not a failure
    assert M.status_for(6, 0, shots_present=True) == "empty"
    # stage 7 with zero geometry is a real problem
    assert M.status_for(7, 0, shots_present=True) == "empty_expected_geometry"
    assert M.status_for(7, 1234, shots_present=True) == "ok"
    assert M.status_for(7, 1234, shots_present=False) == "missing"


def test_build_stages_always_emits_both_kinds_in_order(tmp_path):
    census = {"order": ["PCG_A", "PCG_B"],
              "real_instances": {"1": 0, "2": 55},
              "debug_instances": {"1": 10, "2": 20}}
    cpath = tmp_path / "sa_census.json"
    cpath.write_text(json.dumps(census), encoding="utf-8")
    shots = tmp_path / "shots"
    shots.mkdir()
    for kind in ("debug", "geometry"):
        (shots / M.shot_name(2, "PCG_B", kind)).write_bytes(b"x" * 60000)

    stages = M.build_stages(str(cpath), str(shots),
                            order=["PCG_A", "PCG_B"], min_bytes=50000)
    assert [s["n"] for s in stages] == [1, 2]
    assert [s["shots"][0]["kind"], s["shots"][1]["kind"]] == ["debug", "geometry"]
    # stage 1 has no files -> both entries carry img_missing, not a crash
    assert "img_missing" in stages[0]["shots"][0]
    assert "img_missing" in stages[0]["shots"][1]
    # stage 2 has both -> both carry a path and a size
    assert stages[1]["shots"][0]["path"].endswith("_debug.png")
    assert stages[1]["shots"][1]["bytes"] > 50000
    assert stages[1]["metrics"]["instances"] == 55
    assert stages[1]["metrics"]["status"] == "ok"


def test_a_too_small_file_counts_as_missing(tmp_path):
    census = {"order": ["PCG_A"], "real_instances": {"1": 5},
              "debug_instances": {"1": 5}}
    cpath = tmp_path / "c.json"
    cpath.write_text(json.dumps(census), encoding="utf-8")
    shots = tmp_path / "shots"
    shots.mkdir()
    (shots / M.shot_name(1, "PCG_A", "debug")).write_bytes(b"x" * 100)
    stages = M.build_stages(str(cpath), str(shots), order=["PCG_A"],
                            min_bytes=50000)
    assert "img_missing" in stages[0]["shots"][0]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `C:\Python314\python.exe -m pytest Tools/tests/test_sa_manifest.py -q`
Expected: FAIL / ERROR with `No module named 'sa_manifest'`

- [ ] **Step 3: 写实现**

```python
#!/usr/bin/env python
"""sa_manifest.py — build the report manifest for the small-area 18-stage run.

Two shots per stage, not one: `_debug.png` (this stage's flagged nodes, isolated)
and `_geometry.png` (the city accumulated through stage N). Both are required for
a stage to count as captured.

    python Tools/sa_manifest.py \\
        --census Saved/Reports/sa_census.json \\
        --shots Saved/Screenshots/WindowsEditor \\
        --out Saved/Reports/sa_manifest.json
"""

import argparse
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_BYTES = 50000

ORDER = ["PCG_1_1_Terrain", "PCG_1_2_BG_Buildings", "PCG_1_3_BG_Mountains",
         "PCG_2_1_MainTower_Footprint", "PCG_2_2_CentralPark_Footprint",
         "PCG_3_1_1_Districts", "PCG_3_1_2_Roads", "PCG_3_1_3_Highways",
         "PCG_3_1_4_Lots", "PCG_3_2_1_Ground", "PCG_3_2_2_LeftOverLots",
         "PCG_3_2_3_Parkings", "PCG_3_3_1_Buildings", "PCG_3_3_2_Rooftops",
         "PCG_4_1_MainTower_Visuals", "PCG_4_2_CentralPark_Visuals",
         "PCG_5_1_CityEdge", "PCG_5_2_OuterForest"]

LABELS = ["地形", "背景建筑", "背景山体", "主塔轮廓", "中央公园轮廓", "街区划分",
          "道路", "高架", "地块", "地面", "剩余地块", "停车", "建筑", "屋顶",
          "主塔视觉", "中央公园视觉", "城市边缘", "外林"]

# Stages whose graphs emit data rather than instanced geometry, so a zero instance
# count is correct and their geometry shot repeats the previous stage's picture.
DATA_ONLY = {1, 4, 5, 6}

KINDS = ("debug", "geometry")


def shot_name(n, graph, kind):
    return "sa_stage_%02d_%s_%s.png" % (n, graph, kind)


def status_for(n, instances, shots_present):
    if not shots_present:
        return "missing"
    if instances and instances > 0:
        return "ok"
    return "empty" if n in DATA_ONLY else "empty_expected_geometry"


def build_stages(census_path, shots_dir, order=None, min_bytes=MIN_BYTES):
    with open(census_path, encoding="utf-8") as fh:
        census = json.load(fh)
    order = list(order or census.get("order") or ORDER)
    real = census.get("real_instances", {})
    dbg = census.get("debug_instances", {})

    stages = []
    for i, graph in enumerate(order):
        n = i + 1
        shots = []
        for kind in KINDS:
            name = shot_name(n, graph, kind)
            p = os.path.join(shots_dir, name)
            if os.path.exists(p) and os.path.getsize(p) >= min_bytes:
                shots.append({"kind": kind, "path": p,
                              "bytes": os.path.getsize(p)})
            else:
                shots.append({"kind": kind, "img_missing": p})
        present = all("path" in s for s in shots)
        inst = int(real.get(str(n), 0) or 0)
        stages.append({
            "n": n,
            "graph": graph,
            "label": LABELS[i] if i < len(LABELS) else graph,
            "shots": shots,
            "metrics": {
                "instances": inst,
                "debug_instances": int(dbg.get(str(n), 0) or 0),
                "status": status_for(n, inst, present),
            },
            "notes": ("数据阶段：图产出的是数据而不是实例化几何，"
                      "本阶段的 geometry 张与前一张相同。" if n in DATA_ONLY else ""),
        })
    return stages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default=os.path.join(
        REPO, "Saved", "Reports", "sa_census.json"))
    ap.add_argument("--shots", default=os.path.join(
        REPO, "Saved", "Screenshots", "WindowsEditor"))
    ap.add_argument("--out", default=os.path.join(
        REPO, "Saved", "Reports", "sa_manifest.json"))
    ap.add_argument("--title", default="City Sample PCG 18 阶段 · 600 m 小区域")
    args = ap.parse_args()

    stages = build_stages(args.census, args.shots)
    man = {
        "title": args.title,
        "subtitle": ("由 demo 关卡模板复制出的 600 m 区域，逐阶段生成并隔离拍摄；"
                     "每阶段两张：PCG debug 与累计几何。美术全部复用 City Sample 资产。"),
        "level": "/Game/PCGArea/L_SmallArea18",
        "stages": stages,
        "footer": ("地形来自复制过来的 MeshPartition Actor，阶段 1 按新的 CityShape "
                   "重新塑形；18 张图资产未做任何修改。实例合计 %d；debug 立方体合计 %d。"
                   % (sum(s["metrics"]["instances"] for s in stages),
                      sum(s["metrics"]["debug_instances"] for s in stages))),
    }
    out = args.out if os.path.isabs(args.out) else os.path.join(REPO, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1, ensure_ascii=False)

    n_shots = sum(len([s for s in st["shots"] if "path" in s]) for st in stages)
    n_stages = sum(1 for st in stages if all("path" in s for s in st["shots"]))
    print("manifest: %d stages, %d/%d complete, %d shots -> %s"
          % (len(stages), n_stages, len(stages), n_shots, out))
    bad = [st["n"] for st in stages if not all("path" in s for s in st["shots"])]
    if bad:
        print("stages missing a shot: %s" % ", ".join(map(str, bad)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `C:\Python314\python.exe -m pytest Tools/tests/test_sa_manifest.py -q`
Expected: `4 passed`

- [ ] **Step 5: 用真数据生成清单**

Run: `C:\Python314\python.exe Tools/sa_manifest.py`
Expected: `36 shots`、`18/18 complete`；若列出缺失阶段，先补截图再继续。

- [ ] **Step 6: 提交**

```bash
git add Tools/sa_manifest.py Tools/tests/test_sa_manifest.py Saved/Reports/sa_manifest.json
git commit -m "Add the two-shot manifest builder for the small-area report"
```

---

## Task 8: 报告生成器支持两张图

**Files:**
- Modify: `Tools/build_pcg_stage_report.py`（`CARD` 模板、`card()`、`__SHOT__` 填充处）
- Test: `Tools/tests/test_sa_report.py`

**Interfaces:**
- Consumes: Task 7 的清单（`stages[i].shots` 为列表）
- Produces: `docs/pcg-small-area-18-stage-report.html`；**同时保持旧的单图清单可用**（`stages[i].shot` 单值路径仍在），因为 09-23 的报告要靠它重建

- [ ] **Step 1: 写失败的测试**

```python
# Tools/tests/test_sa_report.py
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import build_pcg_stage_report as R


def test_two_shot_manifest_renders_two_figures_with_kind_captions(tmp_path):
    png = _tiny_png(tmp_path)
    man = {"title": "t", "subtitle": "s", "level": "/Game/X",
           "stages": [{"n": 1, "graph": "PCG_A", "label": "地形",
                       "shots": [{"kind": "debug", "path": png},
                                 {"kind": "geometry", "path": png}],
                       "metrics": {"instances": 0, "debug_instances": 9,
                                   "status": "empty"},
                       "notes": "n"}],
           "footer": "f"}
    doc = R.build_html(man, max_edge=64, quality=50)
    assert doc.count("<figure") == 2
    assert "debug" in doc and "geometry" in doc
    assert doc.count("data:image/jpeg;base64,") == 2


def test_legacy_single_shot_manifest_still_renders_one_figure(tmp_path):
    png = _tiny_png(tmp_path)
    man = {"title": "t", "subtitle": "s", "level": "/Game/X",
           "stages": [{"n": 1, "graph": "PCG_A", "label": "地形",
                       "shot": png,
                       "metrics": {"instances": 1, "debug_instances": 2,
                                   "status": "ok"},
                       "notes": "n"}],
           "footer": "f"}
    doc = R.build_html(man, max_edge=64, quality=50)
    assert doc.count("<figure") == 1


def test_a_missing_shot_renders_the_placeholder_not_a_broken_img(tmp_path):
    man = {"title": "t", "subtitle": "s", "level": "/Game/X",
           "stages": [{"n": 1, "graph": "PCG_A", "label": "地形",
                       "shots": [{"kind": "debug", "img_missing": "/nope.png"},
                                 {"kind": "geometry", "img_missing": "/nope2.png"}],
                       "metrics": {"instances": 0, "debug_instances": 0,
                                   "status": "missing"},
                       "notes": ""}],
           "footer": "f"}
    doc = R.build_html(man, max_edge=64, quality=50)
    assert doc.count("<figure") == 0
    assert doc.count("noimg") == 2


def _tiny_png(tmp_path):
    from PIL import Image
    p = tmp_path / "shot.png"
    Image.new("RGB", (120, 80), (10, 20, 30)).save(p)
    return str(p)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `C:\Python314\python.exe -m pytest Tools/tests/test_sa_report.py -q`
Expected: FAIL with `AttributeError: module 'build_pcg_stage_report' has no attribute 'build_html'`

- [ ] **Step 3: 改实现**

在 `Tools/build_pcg_stage_report.py` 里：

1. 把 `CARD` 的 `__SHOT__` 保留为「一个装 figure 的容器」，新增 `SHOT_FIGURE` 模板：

```python
SHOT_FIGURE = ('<figure class="shot"><img loading="lazy" src="__SRC__" '
               'width="__W__" height="__H__" alt="__ALT__"></figure>'
               '<p class="shotcap">__KIND_ZH__</p>')
KIND_ZH = {"debug": "PCG debug", "geometry": "累计几何"}
```

2. 把 `card(st)` 里拼 `shot` 的那段抽成 `render_shots(st, encode_fn, max_edge, quality)`：

```python
def render_shots(st, max_edge, quality, repo):
    """One figure per entry in shots[]; legacy 'shot' single path still works.

    Returns (html, missing_list, total_kb)."""
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
                           .replace("__KIND_ZH__", html.escape(KIND_ZH.get(kind, ""))))
                continue
            missing.append(str(st.get("graph")))
        out.append('<div class="noimg">无截图：' +
                   html.escape(str(e.get("img_missing") or "未捕获")) + "</div>")
    return "".join(out), missing, kb
```

3. `card(st, max_edge, quality, repo)` 改为调用它；`main()` 里的循环改为收集 `missing` 与 `total_kb`。

4. 让 `main()` 与渲染逻辑可被测试调用：把原来 `main()` 里从 `man` 到 `doc` 的那段抽成

```python
def build_html(man, max_edge=MAX_EDGE, quality=JPEG_QUALITY):
    stages = man.get("stages", [])
    cards, missing, total_kb = [], [], 0.0
    for st in stages:
        shot_html, miss, kb = render_shots(st, max_edge, quality, REPO)
        total_kb += kb
        missing.extend(miss)
        st = dict(st)
        cards.append(card(st, shot_html))
    ...前略（stats 计算保持原样）...
    return (PAGE.replace("__EYEBROW__", "City Sample PCG · 阶段验收")
            .replace("__TITLE__", html.escape(str(man.get("title", "PCG 阶段报告"))))
            .replace("__LEDE__", html.escape(str(man.get("subtitle", ""))) +
                     ' 关卡 <code>' + html.escape(str(man.get("level", ""))) + "</code>。")
            .replace("__STATS__", stats)
            .replace("__CARDS__", "\n".join(cards))
            .replace("__FOOTER__", html.escape(str(man.get("footer", "")))))
```

`main()` 变成：读清单 → `doc = build_html(man, args.max_edge, args.quality)` → 写文件 → 打印统计。

5. 在 `PAGE` 的 `<style>` 里加 `.shotcap` 的样式（小字、居中、来自 `--muted`），保证两张图下标看得懂。

- [ ] **Step 4: 跑测试确认通过**

Run: `C:\Python314\python.exe -m pytest Tools/tests/test_sa_report.py -q`
Expected: `3 passed`

- [ ] **Step 5: 用真清单生成报告**

Run:
```bash
C:\Python314\python.exe Tools/build_pcg_stage_report.py ^
  --manifest Saved/Reports/sa_manifest.json ^
  --out docs/pcg-small-area-18-stage-report.html --max-edge 1200 --quality 80
```
Expected: `wrote docs/...html`，`stages=18 captured=18`，`embedded≈` 数 MB。

- [ ] **Step 6: 回归检查旧报告仍能重建**

Run:
```bash
C:\Python314\python.exe Tools/build_stage_manifest.py --out Saved/Reports/stage_manifest.json
C:\Python314\python.exe Tools/build_pcg_stage_report.py ^
  --manifest Saved/Reports/stage_manifest.json ^
  --out Saved/Reports/regression-18-stage.html
ls -la Saved/Reports/regression-18-stage.html
```
Expected: 生成成功、字节数与 `docs/pcg-18-stage-report.html` 同量级（约 2.9 MB）。这证明单图路径没被改坏。**注意不要覆盖 `docs/pcg-18-stage-report.html`。**

- [ ] **Step 7: 提交**

```bash
git add Tools/build_pcg_stage_report.py Tools/tests/test_sa_report.py docs/pcg-small-area-18-stage-report.html
git commit -m "Render two captures per stage in the PCG report and keep the single-shot path"
```

---

## Task 9: 入库范围与 .gitignore

**Files:**
- Modify: `.gitignore`（`/Content/__ExternalActors__/*` 那一段）
- Modify: `Content/Python/pcg_area_demo_recon.py`（已按新纪律改好，本任务只提交它）

**Interfaces:**
- Consumes: Task 6 产出的 `Content/__ExternalActors__/PCGArea/`
- Produces: 入库的新关卡与外部 Actor

- [ ] **Step 1: 加放行规则**

在 `.gitignore` 的 `/Content/__ExternalActors__/*` 之后、`/Content/__ExternalObjects__/` 之前插入一行：

```
!/Content/__ExternalActors__/PCGArea/
```

同时把 `/Content/__ExternalObjects__/` 改成 `/Content/__ExternalObjects__/*`，
并加 `!/Content/__ExternalObjects__/PCGArea/`，因为外部**对象**（不是 Actor）
也要跟着关卡入库；若该目录不存在则跳过这一条。

- [ ] **Step 2: 核对入库内容与体积**

Run:
```bash
git add -A && git status --short | head -20
git status --short | wc -l
find Content/__ExternalActors__/PCGArea -type f -size +90M 2>/dev/null
```
Expected: 只有 `Content/PCGArea/`、`Content/__ExternalActors__/PCGArea/`、脚本与报告被 staged；
**最后一条命令必须无输出**——任何超过 90 MB 的单个文件都会让 GitHub 拒收，若出现就把它加回
`.gitignore` 并在报告里注明该资产未入库。

- [ ] **Step 3: 确认 demo 关卡与图资产没被改动**

Run:
```bash
git status --short Plugins/CitySamplePCG/Content 2>/dev/null | head
ls -la Plugins/CitySamplePCG/Content/Levels/L_CitySamplePCG_Demo.umap
```
Expected: 第一条无输出；第二条 mtime 仍是 `Sep 1 11:58`。

- [ ] **Step 4: 提交**

```bash
git add .gitignore Content/Python/pcg_area_demo_recon.py
git add Content/PCGArea Content/__ExternalActors__/PCGArea 2>/dev/null || true
git commit -m "Track the new small-area level and its external actors"
```

---

## Task 10: 技能修正与交付小结

**Files:**
- Modify: `.claude/skills/city-sample-pcg-city-builder/references/stage-run-playbook.md`（§3.2）
- Modify: `.claude/skills/city-sample-pcg-city-builder/references/traps.md`（加第 25 条）
- Modify: `.claude/skills/city-sample-pcg-city-builder/references/migrated-citysample-library.md`（§2.1 末尾）
- Modify: `docs/handoff-next-session-small-area.md`（更新为本次的结论）

**Interfaces:**
- Consumes: Task 3 的 `report`、Task 6 的 log 与观测、Task 9 的入库结论
- Produces: 无代码产物；技能文档与交接文档

- [ ] **Step 1: 改 playbook §3.2**

把「重载这个关卡会让编辑器崩溃」这一节整段替换为**真实原因**：
不是重载，而是**上一次脚本把 UObject 留在 Python 全局里**。内容要点：
- 桥用 `exec(..., globals())` 在常驻的 `__main__` 里跑，顶层变量跨调用存活；
- 存活的对象包装会钉住旧 world，下一次关卡切换 aborts 在
  `UEditorEngine::CheckForWorldGCLeaks()`；
- 实测引用链：`GCObjectReferencer -> FPyReferenceCollector::AddReferencedObjects(Package /Temp/Untitled_1)`，
  `Script Stack: /Script/LevelEditor.LevelEditorSubsystem.LoadLevel`；
- **正确的规则**：UObject 只放函数局部；全局只放 JSON；切关卡前
  `del` 掉 `unreal.Object` 类型的全局并 `gc.collect()`；
- 2026-09-24 的复现：`pcg_area_demo_recon.py` 的第一版就是这么崩的，改函数作用域后同一关卡可正常加载。

- [ ] **Step 2: 给 traps.md 加第 25 条**

在 `## 4. 2026-09-23 第二次实测新增` 表后新增 `## 5. 2026-09-24 第三次实测新增`，含：

| # | 坑 | 规避 |
|---|---|---|
| **25** | **Python 全局里的 UObject 会钉住旧 world，让下一次切关卡 abort 在 `CheckForWorldGCLeaks()`。** 实测引用链 `FPyReferenceCollector::AddReferencedObjects(Package /Temp/Untitled_1)`，脚本栈指向 `LevelEditorSubsystem.LoadLevel`。09-23 记的「重载 demo 关卡会崩」是误诊 | 顶层只放 JSON；UObject 全放函数内；切关卡前清理并 `gc.collect()` |
| **26** | **`Actor.add_component_by_class` 不存在**（`AttributeError`），所以**不能从 Python 给 Actor 新挂 SplineComponent**。样条只能改写已有的：`SplineComponent.set_location_at_spline_point / set_tangent_at_spline_point / set_closed_loop / update_spline`（都是 `UFUNCTION`，实测可用） | 要新样条就走「复制带样条的 Actor」或请用户手画；不要指望运行时挂组件 |
| **27** | **`set_spline_points()` 会把所有点重设为 `CurveAuto` 并丢弃自定义切线。** 原样条是 `CURVE_CUSTOM_TANGENT` 时形状会变 | 逐点 `set_location_at_spline_point(i, p, WORLD, False)` + `set_tangent_at_spline_point(i, 变换后的切线, WORLD, False)`，最后 `update_spline()` 一次 |
| **28** | **demo 关卡的样条不止「7 个手绘样条」。** 实测 24 个 Actor 带 `SplineComponent`，其中 `PCG_3_1_1_Districts` 一个 Volume 就带 **67 个**细分样条；另有 `HighRise_Zone_*`、`HighWay_2/3`、以及一批 `PCG Generated Actor` 产生的 `ForestExclusion_*` / `Lake_*` / `ParkPath_*` | 缩放城市必须**遍历所有 SplineComponent**，只改「7 个」会漏掉整张街区细分图 |
| **29** | **`PCGComponent` 上没有 `is_generating()`**（实测 `hasattr` 为 False），只有 `generated` 布尔 | 判断「生成好了没」用 `generated` 加实例数两次读数是否相同；不要找不存在的 API |

- [ ] **Step 3: 给 migrated-citysample-library.md §2.1 追加**

在「硬约束：这些图不是自含的」一节末尾加两条：
- **地形是第 3 个依赖，也是最容易漏的**：demo 关卡的 MeshPartition Actor 是阶段 1 读写、后续阶段投影的目标。**空白关卡跑不出任何东西**。
- **因此新区域要走模板复制**：`LevelEditorSubsystem.new_level_from_template(新路径, "/CitySamplePCG/Levels/L_CitySamplePCG_Demo")`，一条调用就带上地形、18 个 Volume（含图参数）、11 个机位、灯与水面。实测见 2026-09-24 的 `pcg_sa_level.py`。

- [ ] **Step 4: 更新交接文档**

把 `docs/handoff-next-session-small-area.md` 里已过时的两段（「本项目只有 `/Engine/BasicShapes`」「没有建筑美术资产」）改掉——迁移的 62 GB 美术已经到位，`/Game/Building`、`/Game/Road`、`/CitySamplePCG/` 都能用；并把本次的路径、脚本名、census 与报告位置写进去。

- [ ] **Step 5: 提交**

```bash
git add .claude/skills/city-sample-pcg-city-builder/references docs/handoff-next-session-small-area.md
git commit -m "Correct the level-switch crash cause and record the small-area run in the skill"
```

---

## 自审记录

- **规格覆盖**：设计的 A/B/C/D 四部分分别对应 Task 2、3、4+5+6、7+8；交付物清单里的
  `.gitignore` 是 Task 9；技能修正三处是 Task 10；「每阶段两张截图」是 Task 5 的两个 phase 加 Task 7 的双 shot 清单。
- **占位符扫描**：无 TBD/TODO；每个代码步骤都是完整可粘贴的实现；每个验证步骤都给了确切命令与预期值。
- **类型一致性**：`pcg_sa_geom` 的函数名在 Task 1 定义、Task 3 与 Task 4 消费，签名一致；
  `pcg_sa_run` 的 `ORDER` / `comps` / `counted` / `vol_by_label` / `phase_apply_camera` 在 Task 4 定义、
  Task 5 通过 `import pcg_sa_run` 复用（不复制）；清单里的 `shots[]` 形状在 Task 7 定义、Task 8 消费。
- **Review Focus 的测试落点**：第 1、2、5 条由 Task 6 Step 4/6 的看图与 mtime 核对兜住；
  第 4 条由 `Tools/tests/test_sa_manifest.py::test_status_is_empty_only_for_data_stages_with_zero_geometry`
  与 `test_build_stages_always_emits_both_kinds_in_order` 钉住；第 3 条在 Task 6 Step 4 的抽看里判定。
