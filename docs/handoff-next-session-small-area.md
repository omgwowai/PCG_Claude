# Handoff — 下个 session 用 PCG 搭一个小区域

> **用途**：把下面「提示词」一节整段复制给下个 session 即可。
> 后面几节是给人类看的背景与残留事项，不必复制。

---

## 提示词（复制这一段）

```
用 city-sample-pcg-city-builder 技能，在本项目（E:\PCG_Claude）搭一个小区域。

## 目标
一个 3×3 街区的小区域，约 60m × 60m，产出一张可复用的 PCG 图 + 关卡里一个 PCGVolume。
接受它是「灰盒」——本项目只有引擎自带的基础网格，没有美术资产。

## 环境现状（已就绪，不要重做）
- `PCG` 与 `PCGPrimitives` 已在 PCG_Claude.uproject 启用（commit d9b78f0），编辑器已重启过
- MCP 桥在 ws://127.0.0.1:8777，唯一工具是 run_unreal_script
- 已有一份实测过两遍的 API 笔记，全在技能里；**先读它，别自己试错**

## 第一步：探测
run_unreal_script(script_path="pcg_preflight.py")
确认 PCG 已加载、/PCGPrimitives/* 挂载点存在。

## 第二步：读技能参考
按顺序读 `.claude/skills/city-sample-pcg-city-builder/references/` 下的：
- node-classes.md —— 节点类名表、pin 标签读法、add_edge 静默失败、异步分段、参数命名约定
- tooling.md —— run_unreal_script 调用契约、原语库规模、点数公式
- traps.md —— 17 条实测坑

## 第三步：规划并给我看
搭之前先告诉我：图里准备放哪些节点、分几个簇、每簇的验收数字是多少。
特别说明你打算怎么处理「本项目没有路网/建筑美术资产」这件事。

## 第四步：分步实现 + 每步实测
严格两段式：**一次调用建图并 generate_local，下一次调用读结果**。
生成是异步的，同一次调用里读 get_generated_graph_output() 一定读到空，且不报错。

每个阶段都要给出实测数字（点数、组件数、生成的实例数），不要用「没报错」当通过。

## 交付
- 一个 PCG 图资产，路径自选（建议 /Game/PCGArea/）
- 关卡里一个 PCGVolume 挂它
- 显式 save_asset

## 注意
- 项目里可用的网格只有 /Engine/BasicShapes（Cube / Plane / Cylinder / Sphere / Cone）。
  /Game 下没有可用的建筑美术资产——先自己确认一遍再下结论。
- 全程串行，脚本跑在游戏线程且没有超时。
- 读完 references/traps.md 再动手。
```

---

## 上个 session 干了什么

| 提交 | 内容 |
|---|---|
| `d9b78f0` | 技能 + 流水线分析文档 + 三个探测/范例脚本 + 启用 PCG 插件 |
| `016136b` | 修 SKILL.md 的一处重复片段 + 加 `pcg_area_probe.py` |

交付物：

| 文件 | 说明 |
|---|---|
| `docs/city-sample-pcg-pipeline.md` | City Sample 18 阶段流水线分析（1093 行，**参考项目是 `E:\CitySample 5.8`，不是本项目的实现**） |
| `.claude/skills/city-sample-pcg-city-builder/` | 技能，含 4 个 reference 文件 |
| `Content/Python/pcg_preflight.py` | 只读能力探测，任何 PCG 会话先跑它 |
| `Content/Python/pcg_scatter_cube.py` + `pcg_scatter_read.py` | 两段式范例，实测 800 点 + ISM_Cube_0 |
| `Content/Python/pcg_area_probe.py` | 本区侦察：网格清单、TransformPoints 属性面、Spawner 网格路径 |

## 已实测、不要重新试错的事实

**已在技能里**（`references/node-classes.md` / `tooling.md` / `traps.md`），这里只列关键词：

- `add_node_of_type` 返回 **2 元组** `(node, settings)`
- **`add_edge` 会静默失败却返回真值** —— pin 标签错或类型不兼容时不建边，必须用边数前后对比验证
- pin 标签必须**读回来**：`SurfaceSampler` 的数据输入叫 `Surface`，`BoundsModifier` 叫 `In`
- 布尔属性**去掉开头 `b`**：`bSetPointsBounds` → `set_points_bounds`
- `CellSize` / `GridExtents` 是 `unreal.Vector`，不是浮点数
- **生成是异步的**，读结果必须另发一次调用
- 读结果的路径：`get_generated_graph_output()` → `tagged_data` → `get_editor_property("data")` → `get_editor_property("data")` → `PCGPointArrayData.get_num_points()`
- `get_points()` 在 Python 侧 **AttributeError**（只能拿点数，拿不到点数组）
- `create_asset` 失败时返回 `None` 不抛异常；刚删掉的名字马上重建会返回 None
- `CreatePointsGrid` 点数公式：`(2*ext.x/cell.x) * (2*ext.y/cell.y) * (2*ext.z/cell.z)`，extent 是**全宽**且 Z 算层
- `StaticMeshSpawner` 塞网格：`mesh_selector_parameters` → 选择器对象的 `mesh_entries` → 条目的 `descriptor.static_mesh`
- 子图节点：用 `set_subgraph()`，输入 pin 是 `PrimaryInput` + 子图自己的参数 pin

**还没写进技能**（本区侦察新得，下个 session 可顺手补）：

- 本项目可用网格只有 `/Engine/BasicShapes`：`Cube` / `Cube1` / `Plane` / `Cylinder` / `Sphere` / `Cone`
- `PCGTransformPointsSettings` 属性面已确认全部可写：
  `offset_min` / `offset_max` / `scale_min` / `scale_max` / `absolute_scale` /
  `uniform_scale` / `rotation_min` / `rotation_max` / `absolute_rotation`
- `mesh.get_bounds()` 返回的 `BoxSphereBounds` **没有 `.min` / `.max` 属性**（踩坑：别按 FBox 的写法访问）
- `list_assets("/Game", recursive=True)` 会返回一堆关卡 Actor 实例路径
  （形如 `/Game/.../Lvl_ThirdPerson:PersistentLevel.StaticMeshActor_...`），
  **不是真资产**，别被计数误导

## 残留事项（需要人手工处理）

1. **`Content\PCGTest\` 下有 6 个删不掉的测试资产**：
   `PCG_ExecTest`、`PCG_ProbeMesh`、`PCG_Pts_158165`、`PCG_Scatter_158526`、
   `PCG_SmokeTest`、`PCG_Sub_158852`。
   `delete_asset` 与 `delete_directory` 都返回 `False`（同批另外 3 个能正常删）。
   没有绕过资产系统直接删文件——那会让资产注册表失同步。**请在内容浏览器里手工删掉整个 `Content\PCGTest\` 目录。**
   这 6 个目录未纳入 git（commit 时已排除）。
2. **关卡可能被标脏**。上 session 生成测试用的 `PCGVolume` 后都销毁了，净 Actor 变化为零，
   但脏标记读不到（`World.is_dirty()` 抛 `AttributeError`）。保存前看一眼。
3. **编辑器还在跑**（上次 PID 40444）。下个 session 需要它在跑，所以没关。

## 下一步的自然延伸

小区域跑通后，真正的「同构 City Sample」路线是照
`docs/city-sample-pcg-pipeline.md` §4.2 的数据流主线分阶段拆：
`骨架(路网网格+路口) → 路面 → 地块 → 建筑 → 植被 → 街道家具`，
每阶段一张图或图内一个簇，阶段间用 `Get_ActorDataByRef` 按 Actor 名取上游数据。
引擎自带的 `/PCGPrimitives/Examples/City/City_Generator_Steps_1..7` 是最贴近的教材。
