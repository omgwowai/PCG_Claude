---
name: pyworld-scene-builder
description: Use when building, regenerating, changing or extending the PyWorld valley scene of this Unreal project (level /Game/PyPCG/L_PyWorld, graphs /Game/PyPCG/World/PCGW_01..09, code Content/Python/pypcg/stages/wNN_*.py and pypcg/world/, driver pyworld.py) - terrain and surface materials (地形 / 地表材质 / 材质通道), river and road shapes (河流 / 道路 / 桥), settlements and town layout (城镇 PCG / 聚落 / 街道 / 广场), modular buildings and style codes (建筑 PCG / 建筑模块 / 样式码), vegetation ecology and plant communities (植被生态群落 / 物种), roadside props - or when reusing these rules for another PCG world, or when a PyWorld stage fails acceptance, spawns nothing, or looks wrong in a screenshot.
---

# PyWorld 场景生成（山谷世界）

## 概览

PyWorld 是 9 张 PCG 图（`/Game/PyPCG/World/PCGW_01..09`），每张一个 Python Data Processor 节点，按序在
`/Game/PyPCG/L_PyWorld` 里生成一个 2 × 2 km 的山谷：地形、河、路、桥、聚落与建筑、植被生态、沿路道具、地表材质。
**全部生成逻辑是纯 Python**（`Content/Python/pypcg/stages/wNN_*.py` + `pypcg/world/*.py`，不 import unreal），规则写成表
（地块表、原型表、样式库、模块库、物种表、群落配比、材质通道）；图由 `pypcg/world/graphs.py` 生成，从不手改。

**核心原则：改表或改函数 → 离线测试证明 → 从第一张受影响的图起在编辑器里整链重跑 → 读验收数字 → W10 校验 → 用眼睛看截图 → 存盘。**
"没报错"不算通过：看 `read` 的 `failures` / `pass_ok` / `instances`，再看图。

不适用：City Sample 的 18 张图、PyPCG 小镇 / 单图城市（用 city-sample-pcg-city-builder）；与 PyWorld 无关的编辑器操作（用 driving-unreal-via-mcp）。

## 每次会话先确认

- 编辑器在跑、桥在 `127.0.0.1:8777`，当前关卡是 `/Game/PyPCG/L_PyWorld`（不是就拒绝执行）。`pyworld_status.py`（只读）一次看全：当前关卡、脏包、9 步是否已生成和实例数。
  仓库里的关卡不带生成结果：刚打开时 9 步都是 `generated: false`，先 1..9 依次 gen / read（约 10 分钟）再动手。
- 本机还开着**另一个项目**的编辑器（`E:\PCG_Codex`，另一个 AI 在用）。两个进程都叫 `UnrealEditor.exe`：杀进程前看命令行里的 `.uproject`，**永远不要关它**。它和本项目不共享文件，不用"等它空闲"。
- 同一时间只让一个会话驱动本项目的编辑器：`pyworld.py` 的报告文件（`pyworld_deferred.json`、`pyworld_pass<k>.json`、captures）是共用的，会互相覆盖。
- 编辑器崩溃或被杀后，重启前先把 `Saved/Autosaves/*` 挪走；出现 Restore Packages 选不恢复。
- 桥的用法见 driving-unreal-via-mcp；坑表在 city-sample-pcg-city-builder 的 `references/traps.md`（PyWorld 是 92–113）。

## 流水线：每一步、它的规则在哪

| 步 | 模块（`pypcg/stages/`） | 读 | 写 / 生成 | 改规则去 | 细节 |
|---|---|---|---|---|---|
| W1 地形 | `w01_terrain` | Base 地形、谷轴样条 | 全部顶点 z（子优先级 1）+ 原生侵蚀 | `w01_terrain` 参数；谷轴、地点在 `world/layout.py` | terrain-material.md |
| W2 地点 | `w02_locations` | 关卡里带 tag 的 TargetPoint | 地点、河端、出口 | `world/layout.py` → `layout` 阶段 | — |
| W3 河流 | `w03_river` | Intermediate 2 + W2 | 顶点（3）、一整张水面网格、River 表 | `w03_river`、`world/terraform.carve_channel` | river-roads.md |
| W4 道路 | `w04_roads` | Intermediate 4 + W2、W3 | 顶点（5）、车道模块、Roads 表 | `w04_roads` | river-roads.md |
| W5 桥 | `w05_bridges` | W3、W4 | 桥部件 | `w05_bridges` | river-roads.md |
| W6 聚落 | `w06_settlements` | Intermediate 6 + W2–W4 | 顶点（7）、建筑模块点、街面 / 广场、Buildings / Streets / Areas | 布局：`world/rules.py` `settle.py`；建筑：`bdf.py` `kit.py` `grammar.py` `building.py` | town-pcg.md、building-pcg.md |
| W7 植被 | `w07_vegetation` | Final 地形 + W3–W6 | 6 层实例（约 275 万） | `world/flora.py` `ecology.py` `grow.py` | vegetation-ecology.md |
| W8 道具 | `w08_props` | Final + W2、W4–W6 | 电线杆、电线、路灯、护栏、长椅 | `w08_props` | — |
| W9 地表材质 | `w09_surface` | Intermediate 8 + W3、W4、W6、W7 | 6 个材质通道的权重（子优先级 9） | `w09_surface`；贴图 `pyworld_terrain_material.py` | terrain-material.md |
| W10 校验 | `pyworld.py check` | 全部 | 侵入、交叉 = 桥、连通、坡度、贴地 | `world/checks.py` | — |

**依赖**：改了第 n 步，就从 n 起重跑到 9。每个写地形的步骤都写回全部 261 312 个顶点；W9 读 W7 的树密度；W7、W8、W9 读 W6 的足迹、街道、广场。
所以：改建筑 / 城镇 → 6..9；改植被 → 7..9；改地表规则 → 只 9；改河 / 路 → 3..9；改地形或布局 → 1..9。

## 改动流程

1. **定位规则**：上表 + 对应的 reference。能改表（`rules` `bdf` `kit` `flora` `ecology` 的表、阶段的 PARAMS）就不要改算法。
2. **测试**：改或加 `Tools/pypcg/tests/test_world_*.py`（夹具 `world_fixtures.py`），跑
   `C:\Python314\python.exe -m pytest Tools/pypcg/tests -q`（基线以 CLAUDE.md 为准）。
3. **离线跑真数据**（只覆盖 W3–W6，约 10 s 一轮）：没有 `Saved/PyPCG/captures/w03.pkl` 时先在编辑器 `gen {"stage": 3, "capture": true}`；然后
   `C:\Python314\python.exe Tools/pyworld/offline.py --tag <t> [--town]` → `Saved/Reports/pyworld_plan_<t>.png`（平面）、`pyworld_town_<t>.png`（按样式码着色，只画最大的聚落）、`pyworld_shape_<t>.json`（形状指标）。
   离线结果和编辑器略有出入（实测差 1 栋楼、2 条街）：离线用来定方向，结论以编辑器为准。
   W7、W9 要调参时 `gen {"stage": n, "capture": true}` 存它们的输入，再 `stage_api.load_capture("w0n")` + `stage_api.execute(...)` 本地跑（见 offline.py 的 `run`）。
4. **编辑器**（`run_unreal_script("pyworld.py", {...})`，一次调用一个阶段）：
   - 只改了 Python 逻辑：**不用** build，节点每次生成都重新加载模块。改了 PARAMS、输入输出、接线或 DOC：`{"phase": "build", "stages": [n], "defer": true}`（要 `diffs: 0`）→ `{"phase": "assign"}`（重建会清掉组件上的参数覆写）。
   - `{"phase": "reset", "from": n}`，然后对 n..9 依次 `{"phase": "gen", "stage": k}` → 等 → `{"phase": "read", "stage": k}`，`pass_ok: true` 才往下。gen 会拒绝上一步还没生成的；read 之前不要 gen 下一步（gen 期间关了自动保存、拉长了 GC，read 才恢复）。
   - 等多久：W6 约 45 s，W7 150–200 s，其余约 40 s。read 报 `fresh_record: false`，或 W7 报 `no vegetation instances`，都是还没生成完：等一会再 read，不要当成失败去改代码。
   - `{"phase": "check", "defer": true}`，读 `Saved/Reports/pyworld_deferred.json`：`ok: true`、侵入全 0、交叉数 = 桥数、贴地误差 > 30 cm 的为 0。
5. **看截图**（下一节）。
6. **存盘**：先清掉预览和探针（`pyworld_town_preview.py {"clear": true}`、`pyworld_kit_test.py {"clear": true}`），再 `{"phase": "save", "defer": true}`，轮询 `pyworld_deferred.json` 直到 `state: done`、`saved: true`。关卡约 450 MB，不 defer 的话桥会丢回复。
   **提交进 git 的关卡不带生成结果**：生成后 W7 一个文件 361 MB，超过 GitHub 的 100 MB 上限，push 会被拒。要提交关卡改动，先 `{"phase": "reset", "from": 1, "defer": true}`，status 里 9 步都 `generated: false` 后再 save（这时约 10 MB）；生成后存的盘只留在本地，不提交。

记录在 `Saved/PyPCG/runs/wNN.json`（节点的 Summary 与 notes）、`Saved/Reports/pyworld_pass<k>.json`（read 结果）、`Saved/Logs/PCG_Claude.log`。

## 截图例行

1. `tl_editor_no_throttle.py {"throttle": false}`：编辑器在后台时，不关节流截图不落盘。
2. `pyworld_deselect.py`：选中的 actor 会在图里留一个黄框。
3. 拍：`{"phase": "shot", "view": "top" | "wide" | "valley" | "street", "tag": "x"}`。近景加
   `"centre": [x, y(, z)], "radius": cm, "az": 度, "elev": 度`（`az` 是相机相对中心的方位角）。行人视角用
   `"eye": [x, y, z], "look": [x, y, z], "eye_h": 0, "look_h": 0`：给 z 就不往下打射线（不给会打到树冠和屋顶）。
4. 等约 8 s，用 Read 打开 `Saved/Screenshots/WindowsEditor/pyworld_<view>_<tag>.png` 看。**数字对不等于看着对**：石块被地面盖住、悬空、黄框，只有看图才知道。
5. 拍完 `{"throttle": true}`。

## 红旗

| 想法 | 实际 |
|---|---|
| "只改了 Python，先 build 一下图" | 不用；只有 PARAMS / 接线 / DOC 变了才 build，build 之后必须 assign。 |
| "只重跑改的那一步" | 下游读它的输出：建筑 6..9，植被 7..9，河路 3..9。 |
| "gen 完马上 read" | W7 至少等 150 s；早读会报没实例。 |
| "save 直接调" | 用 `defer` 并轮询；先清预览和探针 actor，它们绝不能存进关卡。 |
| "生成完了存盘，一起提交" | 仓库里的关卡不带生成结果：先 reset from 1，再 save，再提交。W7 一个文件 361 MB，push 会被拒。 |
| "截图不用准备" | 不关节流不落盘；不取消选中会留黄框；拍完要用眼睛看。 |
| "调个色调就是新外观" | 色调乘在整张贴图集上（百叶窗一起变色），画不出新细节；新外观要新模块或新材质。 |
| "加个地表通道就是加个名字" | 通道由 MPD 定义（MPD_Basic 的 6 个）；加第 7 个要改 MPD、材质、`CHANNELS`、验收、重建 W9，本项目没走通过——先探针。 |
| "这个 UnrealEditor.exe 卡住了，杀掉" | 先看命令行；PCG_Codex 的编辑器永远不动。 |
| "子材质 / 资产稍后再建" | 先建：Mat0 或网格路径指向不存在的资产不会报错，只是没颜色或不出东西。 |

## 复用到新场景

架构本身可以照搬：控制点是关卡里带 tag 的 actor（`world/layout.py`）；每个阶段模块是 `INPUTS / OUTPUTS / PARAMS / run(inputs, params, ctx)` 的纯 Python；
每张图是"参数 getter → 读地形和上游 volume（按 tag）→ 一个 Python 节点 → 原生写地形 / 生成器"（`world/graphs.py`）；阶段之间按 volume tag 传数据，数据 tag（River、Road、Street、Building…）随数据走；
规则放表、用离线测试锁住；驱动按 `build / layout / assign / reset / gen / read / check / shot / save` 走。
DSL 与节点外壳见 `docs/pypcg-guide.md`，PyWorld 的整体说明见 `docs/pyworld-guide.md`。

## 参考

- `references/terrain-material.md`：地形格与写地形的顺序、6 个材质通道和权重规则、Megascans 层材质；怎么换贴图、改刷的范围、加通道。
- `references/vegetation-ecology.md`：生态场、7 个群落、分层放置、物种表、资产拷贝与修复、性能；怎么加物种、调群落。
- `references/town-pcg.md`：聚落布局，包括平台、广场、地标、有机街道、分区、地块表、联排、剩余地块、地形处理顺序、街道断面；怎么改城镇规则。
- `references/building-pcg.md`：样式库、立面语法、模块库约定、单栋装配、屋顶、颜色材质、海面预览；怎么加样式码、加模块家族。
- `references/river-roads.md`：河曲、水面网格与水材质、路网、桥、形状度量。
- 项目文档：`docs/pyworld-guide.md`（§6 植被、§7 河路、§8 城镇）；设计 `docs/superpowers/specs/2026-10-2*-pyworld-*.md`。
