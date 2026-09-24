# 用 City Sample 的 18 阶段 PCG 流水线建一个小区域 — 设计

> 日期：2026-09-24。状态：待用户审阅。
> 前置：`docs/pcg-18-stage-report.html`（09-23 在 demo 关卡上跑通 18 阶段的报告）与
> `.claude/skills/city-sample-pcg-city-builder/`（本任务遵循的技能）。

---

## 1. 目标与验收

**目标**：在本项目里新建一个真正的「小区域」——约 **600 m × 500 m、1–2 个街区**——
严格按 City Sample 的 **18 阶段 PCG 流水线**生成，**美术全部复用** City Sample 的资产，
并为 **18 个阶段各交付 2 张截图**（PCG debug 一张、几何一张），作为人工验收的依据。

**验收标准**（用户拍板）：

| 项 | 要求 |
|---|---|
| 区域 | 新关卡里的新区域，形状由本任务定义，不是重跑 Epic 的城 |
| 流程 | 18 张 Epic 阶段图**按编号顺序各跑一次**，图资产**不改** |
| 截图 | 每阶段 2 张：`debug`（该阶段节点的 PCG debug 可视化）+ `geometry`（阶段 1..N 的累计几何） |
| 数字 | 每阶段附实测「真实实例数 / debug 立方体数」，`status` 如实标 `ok / empty / missing` |
| 美术 | 100 % 来自 `/Game/{Building,Road,Prop,Megascans,…}` 与 `/CitySamplePCG/`，不用代理盒 |
| 交付 | 新关卡（含外部 Actor）+ 36 张 PNG + 内嵌 HTML 报告 + census JSON + 脚本 + 技能修正，**全部入 git** |

**不属于本任务**：改 18 张图的结构或参数、新建自己的 PCG 图、跑 World Partition 分区烘焙。

---

## 2. 关键事实（侦察实测，2026-09-24）

这些事实决定了设计，都来自对 `L_CitySamplePCG_Demo` 外部 Actor 文件与在线 API 的探测：

1. **7 条手绘样条是普通 `Actor` + `SplineComponent`，靠 Actor Tag 被图找到**
   （`CityShape`、`Artery_1/2/3`、`MainTowerPark`、`LandmarkPark`、`Terrain_shaping`；
   `Highway_Width` 挂在一个 PCGVolume 上）。不是 PCGVolume，可以直接改写样条点。
2. **地形是一个 `MeshPartition` Actor**（`/Script/MeshPartition.MeshPartition` +
   `CompiledSection` + `MeshPartitionDefinition`）。阶段 1 从它读地形再写回，
   后续阶段全部往它上面投影。**没有它，18 阶段静默零点。**
   → 新关卡必须以 demo 关卡为**模板复制**，不能从空白关卡搭。
3. **图参数存在 Volume 上**（`Highway_Width` 所在 Volume 14 MB），复制关卡时一并带走。
4. **Python 全局引用会钉住旧 world**：桥用 `exec(..., globals())` 在常驻 `__main__` 里跑脚本，
   任何留在全局的 UObject 包装（world / package / actor / component）都会让下一次
   `load_level` 在 `CheckForWorldGCLeaks()` 直接 abort（本次侦察就是这样崩的，
   引用链 `FPyReferenceCollector::AddReferencedObjects(Package /Temp/Untitled_1)`）。
   09-23 记录的「重载 demo 关卡会崩」是同一原因的误诊。
5. **可用 API**（在线确认）：`LevelEditorSubsystem.new_level_from_template(path, template)`、
   `EditorLoadingAndSavingUtils.new_map_from_template` + `save_map`、
   `SplineComponent.set_spline_points / set_closed_loop`、`PCGVolume.brush_builder` 可写、
   `AutomationLibrary.take_high_res_screenshot`。**没有** `Actor.add_component_by_class`，
   所以不能从 Python 给 Actor 新挂 SplineComponent——只能改写已有的。
6. **机位**：关卡自带 11 个 `CineCameraActor`，是唯一可靠的机位来源（算出来的机位全是天空）。
7. **PCG debug 没有全局开关**，只有 `PCGSettings.debug` 逐节点布尔；全开会生成 2000 万个
   debug 立方体把编辑器撑崩，每阶段只能 flag 少量节点。
8. **截图一次调用只能发一张**（下一帧才落盘，同一调用里连发会互相覆盖）。
9. **生成是异步的**：`generate_local` 立即返回，读结果必须在**之后的调用**里做。

---

## 3. 总体方案

**「换个城市形状 = 改 7 个手绘样条，图完全不动」**——这是 Epic 官方列出的最推荐改法。
本设计就是它的脚本化：

```
demo 关卡 ──模板复制──► /Game/PCGArea/L_SmallArea18
                              │
                 用相似变换改写 7 条样条（缩到 ~600×500 m）
                 同步变换 11 个机位、18 个 Volume 的 brush
                              │
                 逐阶段：flag debug → generate → 隔离 → 截 debug 张 → 截 geometry 张
                              │
                 census（实例数 / debug 数）→ 清 debug flag → 保存新关卡
                              │
                 manifest → HTML 报告（36 张内嵌）
```

四个组成部分，各自可单独测试：

| 部分 | 职责 | 输入 | 输出 |
|---|---|---|---|
| A 关卡派生 | 复制 demo 关卡到新路径并验证依赖仍在 | 模板路径、目标路径 | 新关卡打开；验证报告 |
| B 区域塑形 | 用一个相似变换改写样条、机位、Volume brush | 变换参数（中心、缩放） | 改写前后的坐标对照 |
| C 阶段跑批 | 逐阶段生成 + 两种截图 + 读数 | 阶段号 | 每阶段 2 张 PNG + 数字 |
| D 报告 | manifest + 内嵌 HTML | census + PNG | `docs/pcg-small-area-18-stage-report.html` |

---

## 4. 各部分设计

### 4.1 A — 关卡派生（`Content/Python/pcg_sa_level.py`）

- **主路径**：`LevelEditorSubsystem.new_level_from_template("/Game/PCGArea/L_SmallArea18",
  "/CitySamplePCG/Levels/L_CitySamplePCG_Demo")`。文档写明它会关闭当前关卡、复制、保存、打开。
- **回退 1**：`EditorLoadingAndSavingUtils.new_map_from_template(模板, False)` 再 `save_map(world, 目标)`。
- **回退 2**：两条脚本路都失败时**停下来请用户手工** `File → Save Current Level As`，不猜第三种。
- **每条路都要验证**：新关卡里 `MeshPartition` Actor 数 = 1；7 个 Tag 各能找到 1 个带
  `SplineComponent` 的 Actor；18 个 `PCGVolume` 各挂对应图；11 个 `CineCameraActor` 在。
  任一项不满足即判失败并回退。
- **World Partition**：demo 关卡是 WP 关卡，复制后同样是。18 个 Volume 与样条都在原点附近，
  编辑器打开时默认加载；脚本仍在验证阶段用 `get_all_level_actors()` 数一遍，缺就用
  `WorldPartitionBlueprintLibrary.load_actors` 按 GUID 拉进来。
- **不做**：不改 demo 关卡；不在 demo 关卡上保存任何东西。

### 4.2 B — 区域塑形（`Content/Python/pcg_sa_shape.py`）

**变换**：一个**相似变换** `p2 = C + s * (p - C0)`，其中
`C0` = 原 `CityShape` 样条包围盒中心，`C` = 新区域中心（默认仍用 `C0`，避免离开地形），
`s` = 缩放系数。目标区域约 600 × 500 m；原城市约 3 km，所以 `s` 约 0.2，
**实际值由脚本读出原 CityShape 尺寸后算出**，不硬编码。

**为什么用相似变换而不是重画**：保住 Epic 手绘的形状关系（主干道穿过城市边界、园区落在边界内），
只改尺度。重画 7 条样条等于重新做一遍关卡设计，与「复用」目标相悖。

**要变换的东西**（同一个 `s`、同一个 `C`）：

| 对象 | 怎么变 | 为什么 |
|---|---|---|
| 7 条样条的每个点 | `set_spline_points(变换后的点, WORLD)`，保留 `closed_loop` | 决定城市形状 |
| 18 个 PCGVolume 的 `brush_builder.x/y/z` | 乘 `s`（**Z 不缩**，保持高度覆盖） | Volume 是生成范围，不缩会在小区域外算空 |
| 11 个 CineCameraActor 的位置 | 同一变换（**Z 也乘 `s`**，否则机位飞太高）；旋转不变 | 机位与城市同比例，画面才对得上 |

**不变换**：`MeshPartition` 地形（阶段 1 会按新 CityShape 重新塑形）、灯光/大气、
`PCG_GridSize` 之类的 Tag。

**验证**：改写后读回每条样条点数、包围盒；报告新 CityShape 包围盒尺寸（应在 600 × 500 m 的 ±20 % 内）。

**Highway_Width**：它是图参数不是样条；保持原值（一条高架的宽度不随城市缩放）。
若阶段 8 因区域过小而生成为空，报告里如实标 `empty`，不改图。

### 4.3 C — 阶段跑批（`Content/Python/pcg_sa_run.py`）

**一次调用干一件事，每阶段 3 次调用**，总计 18 × 3 + 收尾 ≈ 57 次桥调用：

| 调用 | phase | 做什么 |
|---|---|---|
| 1 | `gen` | 清本图所有 `debug`；从**输出节点反查边**取末端最多 4 个节点 flag；`activate(True)`；`generate_local(True)` |
| 2 | `shot_debug` | 隔离：隐藏其他 17 个 Volume 全部组件；本 Volume 真实几何可见 + 最多 3 个 debug 组件可见；机位 → 截 `sa_stage_NN_<graph>_debug.png` |
| 3 | `shot_geom` | 累计：显示 Volume 1..N 的真实几何、隐藏所有 debug 组件；同机位 → 截 `sa_stage_NN_<graph>_geometry.png`；同时读本阶段实例数与 debug 数写入 census |

- **调用 2 与调用 1 之间**生成有一整次往返的时间完成；调用 3 再读数，读到的是稳定值。
  若调用 3 读到实例数 0 且该阶段不在数据阶段集合 `{1,4,5,6}` 内，脚本返回 `suspect_zero=true`
  并**不自动重试**；处理顺序固定为 §6 的「先重截、再重生成一次、仍 0 则标 `empty`」。
- **debug 节点挑选**：`get_all_edges()` 找连到 `DefaultOutputNode` 的边，取其上游节点；
  不够 4 个再沿边往上一层。比 `nodes[:4]` 更接近「产出本阶段结果的节点」。
- **机位表**：沿用 09-23 的 `CAM` 表（阶段 → 机位名片段），机位已随 B 变换。
- **截图签名**：`take_high_res_screenshot(1600, 900, name, None, False, False, force_game_view=False)`，
  关键字传 `force_game_view`。
- **UObject 引用纪律**：所有 Actor / 组件 / world 只在函数局部持有；脚本末尾 `del` 并
  `gc.collect()`；全局只放 JSON。这是事实 4 的直接后果。
- **收尾** `finish`：清 18 张图所有 `debug` flag（它们是内存态，但保存关卡前清掉最稳）；
  `set_visibility(True)` 恢复全部；`save_current_level()` **只保存新关卡**；
  报告本次改动的包列表，确认里面没有 `/CitySamplePCG/` 路径。

### 4.4 D — 报告（`Tools/build_stage_manifest.py`、`Tools/build_pcg_stage_report.py` 扩展）

- census 落到 `Tools/data/stage_census_smallarea.json`（git 跟踪，可从干净克隆重建报告）。
- manifest 生成器加 `--prefix sa_stage_` 与 `--two-shots`：每阶段找 `_debug.png` 与 `_geometry.png`。
- 报告生成器：卡片从 1 图改成 2 图并排（窄屏纵排），每图下标 `debug` / `geometry`。
  数据阶段（1/4/5/6）`geometry` 张与前一阶段相同属正常，卡片备注写明。
- 产物：`docs/pcg-small-area-18-stage-report.html`，自包含，长边 1200 px、JPEG 80。
- 现有 18 阶段报告不动。

---

## 5. 数据流与顺序依赖

```
[A] 复制关卡 ──验证──► [B] 改写样条/机位/brush ──验证──►
[C] stage 1 gen → shot_debug → shot_geom ──► stage 2 … ──► stage 18 ──► finish(save)
                                                              │
[D] census + 36 PNG ──► manifest ──► HTML
```

- 阶段严格顺序：阶段 N 的图靠 `Get_ActorDataByRef` 读阶段 < N 的 Volume 输出，所以不能并行、不能跳。
- 阶段 1 必须在 B 之后：它按新 `CityShape` 与 `Terrain_shaping` 重塑地形。
- 保存只在最后一次；中途崩溃则新关卡仍是复制时的样子（A 保存过一次），重跑 B、C 即可。

---

## 6. 错误处理

| 情况 | 处理 |
|---|---|
| 复制关卡两条路都失败 | 停下，请用户手工另存；不试第三种 |
| 复制后依赖缺失（地形/样条/Volume/机位） | 判失败，报告缺哪个；不带病继续 |
| 某阶段实例数 0 且非数据阶段 | 标 `suspect_zero`，先重截再重生成一次；仍 0 则报告 `empty` 并写明 |
| 编辑器崩溃 | 请用户重启；因为只在 finish 保存，重跑 B + C 即可 |
| 截图未落盘 | 调用 3 前检查调用 2 的文件存在；缺则重发一次 |
| `Saved/Autosaves/` 出现影子包 | 跑前跑后清空，避免「Restore Packages」弹窗卡死桥 |
| 桥断连 | 不重试脚本；先查 `netstat`、看日志尾部再决定 |

---

## 7. 测试与验证

- **A**：复制后的验证清单（§4.1）全绿才算过。
- **B**：改写后读回坐标；`CityShape` 包围盒在目标范围内；7 条样条点数与闭合状态与原来一致。
- **C**：每阶段 `real_instances`、`debug_instances`、两张 PNG 文件存在且大小 > 50 KB。
  36 张齐、census 18 行齐才算完成。
- **D**：`python Tools/build_stage_manifest.py --prefix sa_stage_ --two-shots` 报 `36 captured, 0 missing`；
  HTML 用浏览器打开一次确认。
- **不破坏现有**：`git status` 里 `Plugins/CitySamplePCG/Content/` 与 demo 关卡 0 变更；
  跑 `pcg_postmigration_regression.py` 确认 3×3 区域仍 41 实例。
- **本项目没有 C++ 自动化测试**（见 CLAUDE.md），MCP 服务端测试与本任务无关，不跑。

---

## 8. 文件清单

**新增**

| 文件 | 内容 |
|---|---|
| `Content/PCGArea/L_SmallArea18.umap` + `Content/__ExternalActors__/PCGArea/…` | 新关卡 |
| `Content/Python/pcg_sa_level.py` | A：模板复制 + 验证 |
| `Content/Python/pcg_sa_shape.py` | B：相似变换 |
| `Content/Python/pcg_sa_run.py` | C：`gen` / `shot_debug` / `shot_geom` / `finish` |
| `Tools/data/stage_census_smallarea.json` | 实测数字 |
| `docs/pcg-small-area-18-stage-report.html` | 报告 |
| `Saved/Screenshots/WindowsEditor/sa_stage_*.png` | 36 张原件（`Saved/` 不入库；报告内嵌） |

**修改**

| 文件 | 改什么 |
|---|---|
| `.gitignore` | 加 `!/Content/__ExternalActors__/PCGArea/`，新关卡外部 Actor 放行 |
| `Tools/build_stage_manifest.py` | `--prefix`、`--two-shots`、`--census` 三个参数 |
| `Tools/build_pcg_stage_report.py` | 双图卡片 |
| `.claude/skills/…/references/stage-run-playbook.md` | §3.2 改成真实原因（Python 全局钉住 world） |
| `.claude/skills/…/references/traps.md` | 加第 25 条：UObject 全局引用 → `CheckForWorldGCLeaks` |
| `.claude/skills/…/references/migrated-citysample-library.md` | §2.1 加：MeshPartition 地形是硬依赖；新区域走模板复制 |
| `Content/Python/pcg_area_demo_recon.py` | 改成不持全局引用的版本（本次侦察脚本，保留作为复现证据） |

**删除**：无。上次的 `pcg_shots.py` 保留不动（它服务 demo 关卡的报告）。

---

## 9. 已知取舍

- **相似变换而非重画样条**：形状复用 Epic 的，尺度是新的。若用户想要不同形状，改 B 里的点即可，A/C/D 不动。
- **每阶段 3 次调用而非 2 次**：多一次往返换来 debug / geometry 两张分开截、读数稳定。18 阶段多 18 次调用，可接受。
- **只在最后保存**：中途崩溃丢的是内存态，不会把半成品写进关卡。
- **`Highway_Width` 不缩**：高架宽度是物理尺寸，不该随城市缩；阶段 8 可能因此为空，如实报告。
- **不动 18 张图**：图内参数（街区尺寸、地块尺寸）仍按 3 km 城市调，小区域里街区分档可能退化；
  这是「图完全不动」的代价，报告里注明，改参数是后续任务。
