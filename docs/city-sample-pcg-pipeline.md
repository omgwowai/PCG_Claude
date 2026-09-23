# Unreal Engine City Sample PCG 流水线框架分析

> **分析对象**：Epic 官方 City Sample 的 **PCG 版本**（非 2022 年 Houdini 版）
> **引擎**：UE 5.8.2 源码构建，`E:\UnrealEngine`（注册 GUID `{4B303DEF-4E44-1DE5-A177-09B23BCA8A5A}`）
> **参考项目**：`E:\CitySample 5.8`（流水线在此，本文所有路径以它为准）
> **落地项目**：`E:\PCG_Claude`（配套 skill 在此执行，见 §14）
> **文档性质**：基于本机磁盘资产的实测勘查 + 引擎源码阅读 + Epic 官方文档，非推测复述
> **撰写日期**：2026-09-23

---

## 0. 一句话概括

City Sample 的 PCG 版本把 2022 年那个由 **Houdini 离线生成、经 RuleProcessor 导入**的城市，
**完全用引擎内部的 PCG 框架重建**了一遍。它由 **18 张按依赖顺序编号的 PCG 图**组成，
逐阶段把「一张地形 + 一条城市边界样条」推演成一座含路网、路口、建筑、屋顶、植被、停靠车辆、
海岸码头与外围森林的完整城市，全程无外部 DCC 依赖，且**结果完全可再生成、可增删改**。

这套流水线被 Epic **显式设计为可由 LLM 经 MCP 驱动**：
图资产内嵌描述性元数据、专门的 `Edits/` 文件夹存放「对着某句 prompt 改出来的变体」，
并配套发布了若干 `Skill_*` 智能体技能资产。

---

## 1. 先厘清：存在两条互不相干的「City Sample」

这是理解本主题最容易踩的坑，必须先分清。

| | Houdini 版（2022） | **PCG 版（UE 5.8，本文主题）** |
|---|---|---|
| 城市如何产生 | Houdini 18.5 离线生成点云 | 引擎内 PCG 图运行时生成 |
| 导入机制 | `RuleProcessor` 插件消费点云 | 无导入，纯 PCG |
| 内容落点 | `/Game/Map/Big_City_LVL` 等 | `Plugins/Experimental/CitySamplePCG/` |
| 本项目状态 | 存在（`CitySample_HoudiniFiles.zip`） | 存在且独立 |

**关键点**：PCG 版城市**不复用** Houdini 版的城市几何，两者是并列的两套资产。
Houdini 版城市仍在项目里，作为**美术资产来源**
（`/Game/Building/Library/`、`/Game/Road/Kit_City_Road/`、`/Game/Prop/` 等
被 PCG 版大量引用作为「可摆放零件」）。

### 1.1 磁盘上两份 CitySample 的区别

`E:\CitySample` 与 `E:\CitySample 5.8` **都存在**，且
**`Plugins/Experimental/CitySamplePCG` 在两个项目里逐字节相同**（`diff -rq` 无输出）。
差异只在项目级：

| | `E:\CitySample` | `E:\CitySample 5.8` |
|---|---|---|
| `EngineAssociation` | `"5.8"`（启动器版） | `{4B303DEF-...}`（源码构建 `E:\UnrealEngine`） |
| `.uproject` 插件表 | 51 项，**无任何 PCG 条目** | 追加 `ModelContextProtocol` / `PCG` / `PCGToolset` / `EditorToolset` |
| 额外内容 | — | `Content\PCGTest\`、`Content\PCGTown\`、`CLAUDE.md`、`.mcp.json`、`docs\superpowers\**` |

→ **`E:\CitySample 5.8` 是工作副本**；PCG 流水线本身在两者中相同，完全位于插件内。

### 1.2 一条重要的负面事实

`CitySamplePCG` 插件**没有任何 C++ 源码**——没有 `Source\`、没有 `.Build.cs`、没有 `.h`/`.cpp`。
全项目范围 `grep -ril "PCG" Source Plugins --include=*.h --include=*.cpp --include=*.cs`
返回**零命中**。项目的三个 C++ 模块（`CitySample` / `CitySampleEditor` /
`CitySampleAnimGraphRuntime`）对 PCG 一无所知。

→ **整条流水线 100% 是内容/图作者化产物，全部 C++ 都在引擎的 PCG 插件里。**
这意味着：**要改流水线行为，只能改图，不能改代码**（除非改引擎）。

---

## 2. 插件与启用关系

### 2.1 承载插件

```
E:\CitySample 5.8\Plugins\Experimental\CitySamplePCG\CitySamplePCG.uplugin
```

- `FriendlyName`：**CitySamplePCG**
- `Description`：`City Sample rebuilt using PCG Framework and Primitives in Unreal`
- `CanContainContent: true` → **全部图与数据资产以 `.uasset` 形式装在这个插件内**，而非 `/Game/`
- `IsExperimentalVersion: true`

它声明依赖并自动启用：

| 依赖插件 | 作用 |
|---|---|
| `PCG` | PCG 框架本体 |
| `PCGPrimitives` | **原语子图库**（见 §6），城市图的词汇表 |
| `PCGPrimitives_MeshPartitionInterop` | 原语库的 Mesh Partition 互操作 |
| `PCGExternalDataInterop` | 外部数据接入 |
| `ProceduralVegetationEditor` | 程序化植被编辑器 |
| `ModelContextProtocol` | **Epic 官方 MCP 服务器**（见 §9） |
| `AllToolsets` | 聚合插件，一次性打开全部工具集（含 `PCGToolset`） |

### 2.2 项目级启用

`E:\CitySample 5.8\CitySample.uproject`（共 63 个插件）中与本主题相关者：

`PCG`、`PCGToolset`、`EditorToolset`、`ModelContextProtocol`、`PythonScriptPlugin`、
`MassAI`、`StateTree`、`ZoneGraph`、`Traffic`、`FastGeoStreaming`。

> **与 `E:\PCG_Claude` 的差异**：写作本文时 `PCG_Claude` **尚未启用 PCG**；
> 2026-09-23 已在其 `.uproject` 中加入 `PCG` 与 `PCGPrimitives`，
> 使其成为配套 skill 的落地项目（见 §14）。
> 但两项目的 **MCP 传输层不同**，这一点始终成立，见 §9.4。

---

## 3. 磁盘资产落点

```
Plugins/Experimental/CitySamplePCG/          ← 插件总重约 8.8 GB
├── CitySamplePCG.uplugin
├── Resources/
│   └── Icon128.png                          ← Resources 里仅此一项
└── Content/                                 ← 无目录名 CitySamplePCG，直接铺在 Content 下
    ├── Levels/                    23 文件
    │   ├── L_CitySamplePCG_Demo.umap         ← ★ 承载全部 18 张图的演示关卡
    │   ├── MPD_CitySamplePCG_Demo.uasset     ← World Partition 描述
    │   ├── TP_DefaultPreviewSection.uasset
    │   ├── DataLayers/                       ← DL_Late_Afternoon / DL_Vancouver_Sunset
    │   └── PCG/                              ← ★ 18 张主流水线图（§4）
    ├── PCG/                      528 文件
    │   ├── （根）13 个共享辅助图               ← §3.2
    │   ├── DataAssets/           492 文件     ← §5、§7、§8
    │   └── Primitives/            23 文件     ← CitySample 自己的原语扩展
    ├── Examples/                  33 文件     ← 教学图集（§6.3）
    ├── Meshes/                                ← Building 套件（NY A–H、CH B/H、SF D）+ Roads
    ├── Materials/  MSPresets/  Megascans/  Megaplants/  BlackAlder/
    ├── __ExternalActors__/Levels/L_CitySamplePCG_Demo/    194 文件
    └── __ExternalObjects__/Levels/L_CitySamplePCG_Demo/   （HLOD 等）
```

**关键认知**：因为 `CanContainContent: true` 且插件目录是 `Plugins/Experimental/`，
这些资产的**包路径挂载点是 `/CitySamplePCG/...`**，而不是 `/Game/...`。
本文所有路径以 `CitySamplePCG` 插件内为基准书写。

> 注意：项目 `Content/` 下**不存在** `Content/CitySamplePCG/` 目录。
> 全部 PCG 内容都在插件里。

### 3.1 资产类型（自二进制 name table 解码）

| 资产 | 实际类 |
|---|---|
| `Levels/PCG/*.uasset`、`PCG/*.uasset` | `UPCGGraph` |
| `SGD_*` | `BP_ShapeGrammarDefinition_C`（源自 `/PCGPrimitives/Grammar/BP/BP_ShapeGrammarDefinition`） |
| `RULE_*` | `BP_ShapeGrammarRule_C`（源自 `/PCGPrimitives/Grammar/BP/BP_ShapeGrammarRule`） |
| `*_PCG.uasset`（Plazas/RoofTops/Piers/VistaCliffs） | `UPCGDataAsset` |
| `DT_*` | `UDataTable` |
| `ST_*` | `UUserDefinedStruct` |

**没有**任何独立的 `PCGGraphInstance`、`PCGAssembly`、`PCGAssetSet` 资产
——图实例化是内联的。

### 3.2 `Content/PCG/` 根下的 13 个共享辅助图

这些是 18 张阶段图共同依赖的「子程序」：

| 辅助图 | 大小 | 作用 |
|---|---|---|
| `Intersection_solving` | 1.32 MB | 路口求解 |
| `Crosswalks` | 1.32 MB | 人行横道 |
| `AssignBuildingShape` | 686 KB | 建筑形体指派 |
| `Assign_BldgStyles_per_MinWallWidth` | 425 KB | 按最小墙宽指派样式码 |
| `LoopCreateExtrudedMeshActorPerData` | — | 循环挤出网格 Actor |
| `LoopCreatePlanarMeshActorPerData` | — | 循环平面网格 Actor |
| `LoopSpawnActorPerData` | — | 循环生成 Actor |
| `Custom_Projector_with_rotation_fix` | — | 带旋转修正的投影器 |
| `FilterPolygonByEdgeLength` | — | 按边长过滤多边形 |
| `FilterSquareShapes` | — | 过滤方形 |
| `GridPartition` | — | 网格分区 |
| `SetComplexBuildings` | — | 复杂建筑处理 |
| `SetComplexBuildings_InnerLoop` | — | 其内循环 |

---

## 4. 主 Demo：18 张图的分阶段流水线

这是 City Sample PCG 的**主干**。命名规则本身编码了依赖顺序：
`<阶段序号>_<子序号>_<职责>`。改一张上游图，下游全部需要重建。

### 4.1 阶段总览

| # | 图名 | 职责 |
|---|---|---|
| 1 | `PCG_1_1_Terrain` | 用 **TerrainShaping 样条**塑造地形岛屿（约 3km × 3km 网格地形） |
| 2 | `PCG_1_2_BG_Buildings` | 背景城市剪影，**排除中心区** |
| 3 | `PCG_1_3_BG_Mountains` | 远景山体/崖壁剪影，来自已烘焙的 PCG 数据 |
| 4 | `PCG_2_1_MainTower_Footprint` | 主塔六边形样条足迹 → **作为排除区** |
| 5 | `PCG_2_2_CentralPark_Footprint` | 中央公园矩形样条（纽约中央公园 1:4 缩放）→ **作为排除区** |
| 6 | `PCG_3_1_1_Districts` | **核心分区分块**：消费城市形状 + 主干道，产出 district / sub-district / block + 第一版路网 |
| 7 | `PCG_3_1_2_Roads` | **求解路口**、套用形状语法、把道路投影到地形，并**局部整平地形**保证坡度平滑 |
| 8 | `PCG_3_1_3_Highways` | 高架高速生成（两条交叉 + 环绕城市的单向高架） |
| 9 | `PCG_3_1_4_Lots` | 由城市形状 + 道路足迹解出**建筑地块（footprint）** |
| 10 | `PCG_3_2_1_Ground` | 人行道 / 地面铺装资产 |
| 11 | `PCG_3_2_2_LeftOverLots` | 剩余空间处理：**广场与植被**（并分流至停车场分支） |
| 12 | `PCG_3_2_3_Parkings` | 由地块生成**停车场** |
| 13 | `PCG_3_3_1_Buildings` | **由三类地块生成建筑主体** |
| 14 | `PCG_3_3_2_Rooftops` | 建筑顶部**装配体（Assembly）** |
| 15 | `PCG_4_1_MainTower_Visuals` | 主塔视觉实现 |
| 16 | `PCG_4_2_CentralPark_Visuals` | 公园道路、步道、带地形形变的湖面、树草散布、博物馆式建筑 |
| 17 | `PCG_5_1_CityEdge` | 海岸边界**码头 / 仓库**结构 |
| 18 | `PCG_5_2_OuterForest` | 外围**密林散布**，向水域方向渐隐 |

以上 18 个资产已在本机逐一确认为真实存在的 `.uasset`
（`CitySamplePCG/Content/Levels/PCG/`）。

### 4.2 数据流主线

```
手工样条输入（地形形变 / 城市形状 / 主干道 / 高速 / 高层区 ×2）
        │
        ▼
[1] 地形 ──────────────────────────────► 供 [7] 道路投影与整平
        │
        ▼
[2][3] 背景剪影（排除中心区）
        │
        ▼
[4][5] 主塔足迹 + 中央公园足迹 ═══════► 作为「排除区」注入后续采样
        │
        ▼
[6] Districts ──► districts / sub-districts / blocks + 首版路网
        │
        ▼
[7] Roads ──► 路口求解 + 形状语法 + 投影整平 ──► 道路足迹
        │
        ├──► [8] Highways（高架，独立支线）
        │
        ▼
[9] Lots ──► 建筑地块（三分类）
        │
        ├──► [10] Ground（人行道）
        ├──► [11] LeftOverLots ──► 广场/植被 + ──► [12] Parkings
        │
        ▼
[13] Buildings ──► [14] Rooftops
        │
        ▼
[15] MainTower_Visuals   [16] CentralPark_Visuals   [17] CityEdge   [18] OuterForest
```

### 4.3 关卡装配：18 个 PCGVolume 各跑一张图

主 Demo 关卡是 **`L_CitySamplePCG_Demo`**（`Content/Levels/`，World Partition，
`LevelIsUsingExternalActors`，含 `HLODLayer_Instanced` / `HLODLayer_Merged`，
最后保存于 `2026.08.14`，引擎 `++UE5+Release-5.8`）。

其 **194 个外部 Actor** 解码后：

- **18 个 `PCGVolume` Actor，各挂一个 `PCGComponent`**，
  Outliner 标签**恰好就是 18 张图的名字**：`PCG_1_1_Terrain` … `PCG_5_2_OuterForest`
  → **一张图 = 一个 Volume，顺序堆叠**
- 第 19 个 Actor 是 `BP_ShapeGrammarDefinition_C` + PCGVolume + PCGComponent
- 若干 Actor 是 `PCGVolume` + `SplineComponent` 组合（承载手绘样条）
- 标签 `PCG_GridSize_0` 出现 5 次

**阶段之间的数据传递靠 `Get_ActorDataByRef` 按名字引用前一阶段的 Actor**，
而非图与图之间的直接连线。这是"分阶段、可单独重跑"的实现基础。

> **工程含义**：想让城市重新生成，不必从第一张图重跑到底——
> 只要上游 Actor 的数据还在，可以从任意中间阶段单独重跑。

### 4.4 手绘样条清单（真实 Actor 名）

18 张图按名读取以下手工 Actor，它们就是全部的人工介入点：

| Actor 名 | 用途 |
|---|---|
| `CityShape` | 城市边界 |
| `Artery_1` / `Artery_2` / `Artery_3` | 三条主干道 |
| `Highway`（+ `Highway_Width`） | 高架高速及其宽度 |
| `MainTowerPark` | 主塔所在园区 |
| `LandmarkPark` | 地标园区 |
| `Terrain_shaping_1` | 地形形变轮廓 |

### 4.5 各阶段内部结构（自图资产的 import table 重建）

| 阶段 | 调用的子图 / 关键节点 | 图内注释与参数（原文摘录） |
|---|---|---|
| **1.1 Terrain** | `Get_ActorData`(CityShape, Terrain_shaping_1) → `Trace_Bound_Footprint` → `Extract_Bounds` → `Compose_Areas_Exclusion` → `Transform_{Areas_Expand, Offset, Project, Points_SpatialNoise}` → 经 `/Script/MeshPartition` 读写 MeshTerrain | 节点标签：`READ TERRAIN` / `Expand Footprint 600m` / `Flatten over city footprint` / `Project City Flat Zone` / `Move City Shape Up` / `Write Mesh Terrain`。参数 `CityFlatness`，图内文档：*"Lerp between the hill-only terrain (InA) and the city-flat terrain (InB). Ratio driven by (1 - CityFlatness)."* |
| **1.2 BG Buildings** | `Create_Spline_Shape` → `Compose_Areas_Exclusion` → `Fill_Areas_Randomly` → `Filter_RandomChoice` → `Spawn_Assets` | 生成 `/Game/Environment/Background_City/Mesh/SM_bgcitya\|b\|b_NotNanite`，材质 `/CitySamplePCG/Materials/BackGroundCity/MI_BackgroundCity` |
| **1.3 BG Mountains** | 最小的图；直接消费 `VistaCliffs_PCG`（`UPCGDataAsset`）+ `MI_MeshTerrain_CitySamplePCG` | **完全没调用任何 PCGPrimitives** |
| **2.1 / 2.2 地标足迹** | `Create_Spline_Shape` + `Transform_Offset` + `Debug_PrimitiveData` | 2.1 文档：*"Defines the hero tower landmark footprint as a parametric hexagonal spline shape. Consumed by downstream graphs as the boundary for the main tower complex."* 2.2：*"Ensure footprint is set to the ground level, regardless of the PCG actor position in Z"* |
| **3.1.1 Districts** | `Subdivide_Areas_withSpline`、`Subdivide_Areas_withGrid`、`Subdivide_Areas_WithRecursiveSplit`、`Filter_Areas_BySize`、`Create_Mesh_Planar`(debug) | 节点注释：`ARTERY ROADS` / `COLLECTOR ROADS` / `LOCAL ROADS` / `LARGE DISTRICTS` / `MEDIUM DISTRICTS` / `Dividable districts` / `Districts Subdividing Splines`。参数：`Block grid length/width for Large\|Medium\|Small districts (cm)`、`Dividable_district_Limit`、`SubDistrictSeed`、`Debug_DistrictCategories` |
| **3.1.2 Roads** | `Assign_ShapeGrammarDefinition` + `Assign_Assets` + `Spawn_Assets`、`Compose_Spline_Cut`、`Extract_Segments`、`Place_OnSpline`、`Place_Point_AtCenter`、`Transform_{Resample, Outline, Jitter, Level, Project, Areas_Expand}`，以及 `Crosswalks` / `Intersection_solving` / `Custom_Projector_with_rotation_fix` / `GridPartition` / `LoopSpawnActorPerData` | 注释：*"Collects Local, Collector, and Artery road splines into a single stream"* / *"Embed Artery Width On Footprint"* / *"Embed Collector Width On Footprint"* / *"Embed Local Width On Footprint"* / *"Downstream graphs (Lots, Buildings) read these to know road clearance distances."* / *"Clip Roads At Landmark Boundary"* / *"Blur Terrain (Road Edges)"* / *"(Intersection Edges)"* / *"(Final Pass)"*。消耗 `SGD_Road_City`、`SGD_Road_City_HighRes_NoLines`；生成 22 种 `SM_Road_SprayPaint_*_inst` 贴花 |
| **3.1.3 Highways** | `Filter_Tags` → `Assign_ShapeGrammarDefinition`(`SGD_ElevatedHighway_oneWay`) → `Transform_Resample/Project/Areas_Expand` → `Spawn_Assets` | — |
| **3.1.4 Lots** | `Subdivide_Areas_withGrid` / `_WithRecursiveSplit`、`Compose_Areas_Intersection` / `_Exclusion`、`Transform_Areas_Contract`、`Filter_Areas_BySize`、`Write_Tag` + `FilterPolygonByEdgeLength` | 参数按街区档位分：`BuildableLotMin/MaxSize{Large,Medium,Small}District`、`BuildableFootprintMinSize*`。注释：`Carve Grammar Roads From Large Lots` / `Carve Medium/Small Courtyard From Lot` / `Contract Large Footprints (Inner Building Pad)` / `Exclude Highway From Large Lots` / *"Contracts the medium lot polygon inward by 3000 units."* |
| **3.2.1 Ground** | `Assign_Rule` + `Assign_ShapeGrammarDefinition`(`SGD_Sidewalk_A`、`SGD_Sidewalk_Corners`)、`Fill_Areas_Uniformly`、`Compose_Spline_Cut`、`Transform_Splines_Reverse`、`Extract_Segments` | 生成 `/Game/Road/Kit_Sidewalk_A/Mesh/SM_Plaza_Square_A..G`、栅栏、栏杆。**含形状语法帮助文本**：*"A means to place the module with symbol A."* / *"A, B means to place modules A and B once, in sequence."*。参数注释：`ArteryWidth / 2 (Sidewalk Expansion Amount)` |
| **3.2.2 LeftOverLots** | `Fill_Areas_WithFittingAssets_CoreProcess` / `_with_Corrective` | 填充 42 个 Plaza/Storage `*_PCG` 数据资产 + 树（`SM_Black_Alder_01_A..D`、`SM_Common_Hazel_01_A/B`、`SM_European_Beech_01_A..C`、`SM_BlackAlder_Field_01..05_PP`） |
| **3.2.3 Parkings** | `Subdivide_Areas_withGrid`、`Fill_Areas_Uniformly`、`Assign_Rule`、`Place_OnSpline`、`Transform_Truncate/Outline/Resample` | — |
| **3.3.1 Buildings** | `Assign_CitySampleBuildings` → `Assign_CitySampleBuildings_CoreProcess` → `LoadCitySampleData`；`AssignBuildingShape`、`SetComplexBuildings`、`FilterSquareShapes`、`Filter_Areas_within_Areas`、`Create_Mesh_Extrude`、`Write_Noise`、`Write_DistanceFrom`、`Write_Attribute_fromTexture`、`LoopCreate{Extruded,Planar}MeshActorPerData` | **图内硬编码 19 个样式码白名单**（见 §7）。标签体系 `Building_S_` / `_M_` / `_L_`（+`_Col` 碰撞变体），`FilterTags_/AddTags_/DeleteTags_{Small,Medium,Large}Districts`。tooltip：*"Maximum height in centimeters of the spawned building"* |
| **3.3.2 Rooftops** | `Fill_Areas_WithFittingAssets_*`、`Compose_Points_Difference`、`Filter_Areas_BySize` | 消费 56 个 `RoofTops/*_PCG` 数据资产 |
| **4.1 / 4.2 视觉** | 最大的两张图，英雄资产装扮 | 4.1 拉 WFC 屋顶组 + `SGD_Sidewalk_Simple` + `Transform_Align`；4.2 拉 `SGD_Road_City`、`SGD_Sidewalk_A`、`SGD_Sidewalk_CITY_EDGE`、`SGD_WalkpathSplineMesh`、`Fill_Areas_Randomly`、`Filter_AttributeValue`、`Write_Attribute`、`Write_Noise` |
| **5.1 CityEdge** | `Assign_Assets` + `Spawn_Assets` over 5 个 Piers 数据资产 | 极简 |
| **5.2 OuterForest** | `Trace_Bound_Footprint`、`Extract_Bounds`、`Compose_Areas_Exclusion`、`Fill_Areas_Randomly`、`Write_DistanceFrom`、`Write_Attribute_fromTexture` | 用 `/Game/Textures/Noise/T_CloudNoise_4k` 驱动密度，生成 Megaplants 树集 |

**最重要的结构性事实**：18 张图几乎**完全由 `/PCGPrimitives/Primitives/<动词>/<动词>_<名词>`
子图拼成**，每个都带配套的 `Subgraphs/<name>_CoreProcess` 与共享的
`_Template_/Primitives_{InputsProcessing, InputsFallback, PrepareOutputs}` 包装。
贯穿 18 张图的动词有：

> **Assign, Compose, Copy, Create, Debug, Extract, Fill, Filter, Get, Place,
> Shared, Spawn, Subdivide, Trace, Transform, Write**

**CitySamplePCG 几乎不贡献新节点类型——它是「引擎原语库 + 13 个辅助图 + Buildings/BDF 扩展」的组合。**

### 4.6 手工输入：样条是唯一的人工介入点

流水线假定以下**手绘样条**已就位，它们是「艺术家意图」的入口：

| 样条 | 作用 |
|---|---|
| Terrain shaping | 3km×3km 网格地形上的岛屿轮廓 |
| City shape | 城市边界 |
| Arteries | 定义分区的主干道 |
| Highways | 两条交叉并环绕城市的高架单向道 |
| High rise zone ×2 | 限制高层建筑可生长的两个区域 |

**实践含义**：想换一座完全不同形状的城市，不必改图——**改这五组样条即可**。
这是整条流水线最重要的可参数化设计。

---

## 5. 形状语法定义系统（Shape Grammar Definition）

`PCG_3_1_2_Roads` 与建筑立面的核心技术，也是**模块化美术沿样条自动拼接**的通用机制。

### 5.1 概念

一个 **Shape Grammar Definition（SGD）** 数据资产把「横截面」拆成若干 **slot（槽位）**，
每个槽位引用一条 **Rule**，Rule 再按**语法串**把模块化网格沿样条重复排布。

例：一条道路横截面 = 人行道 + 车道 + 路缘石 + 车道 + 人行道。

### 5.2 制作流程

1. 建 **Rule** 资产，类 `BP_ShapeGrammarRule`（如 `RULE_MyLane`）。
2. 加入 module：引用一个静态网格 + 一个**符号**（如 `"A"`），设定尺寸或点 **Guess Size**。
3. 设定**语法串**，如 `"A*"`（`*` = 重复）——参考 `RULE_Road_Car_Lane`。
4. 建 **Shape Grammar Definition** 资产，类 `BP_ShapeGrammarDefinition`（如 `SGD_MyRoad`）。
5. 加 slot：符号（如 `"C"`）、尺寸(cm)、`scalable=true`、引用上面的 Rule。
6. 顶层字段：Main Grammar `"C"`、Use Grammar **true**、Orientation **horizontal**、
   Spawn on spline 开启。
7. 在图内：加 **`Assign_ShapeGrammarDefinition`** 节点，喂入样条，指定 SGD 资产与横截面尺寸。

### 5.3 本项目的真实资产

`CitySamplePCG/Content/PCG/DataAssets/Roads/` 下有人行道、道路、高速三套成品语法。
建筑侧同理，按样式码分目录，每目录形如：

```
Buildings/CHA/
├── RULE_CHA_L00.uasset … RULE_CHA_L20.uasset   ← 逐层规则
└── SGD_CHA_A.uasset                             ← 该样式码的立面定义
```

> 另有配套的 `Skill_PCGShapeGrammarDefinition` 智能体技能资产，
> 用于**从零引导 LLM 建一套形状语法**（见 §9.1）。

---

## 6. PCG Primitives：原语库是这套流水线的词汇表

**引擎自带**，并非项目内容：

```
E:\UnrealEngine\Engine\Plugins\Experimental\PCGPrimitives\
```

- 纯内容插件：`.uplugin` **没有任何 `Modules`**，无 C++、无 Python，共 **475 个 `.uasset`**
- `EnabledByDefault: false`，`IsExperimentalVersion: true`

### 6.1 目录结构

| 目录 | 内容 |
|---|---|
| `Content/Primitives/<类别>/` | 约 80 个成品原语 + 各自 `Subgraphs/` 内部实现 |
| `Content/Examples/<品类>/` | Basics / Buildings / City / Forest / Industrial / Park / RealWorldArchitecture / Road / Utilities |
| `Content/Grammar/` | `BP/`（含 GeometryScript 模块）、`DataAsset/`、`PCG/`、`Structure/` |
| `Content/Instants/` | Create / Place / Spawn / Transform / Shared ——「即时图」，一次调用即出结果 |
| `Content/Levels/` | `Default_Level.umap`、`ShapeGrammar_Demo.umap` |
| `Content/Meshes/`、`Materials/` | 支撑资源 |

### 6.2 原语命名体系（按动词分类）

原语命名即其语义，采用 `<动词>_<对象>_<限定>` 结构：

| 类别 | 原语 |
|---|---|
| **Assign** | `Assign_Assets`、`Assign_Rule`、`Assign_ShapeGrammarDefinition` |
| **Capture** | `Capture_Scene_withPoints` |
| **Compose** | `Compose_Areas_Exclusion`、`_Intersection`、`_Union`、`Compose_Enclose`、`Compose_NearbyArea`、`Compose_Points_Difference`、`Compose_Spline_Cut` |
| **Copy** | `CopyToPoints` |
| **Create** | `Create_ActorBounds`、`Create_Mesh_Extrude`、`Create_Mesh_Planar`、`Create_Point`、`Create_Spline_Shape`、`Create_Spline_line` |
| **Extract** | `Extract_Bounds`、`Extract_Segments` |
| **Fill** | `Fill_Areas_Randomly`、`Fill_Areas_Uniformly`、`Fill_Areas_WithFittingAssets` |
| **Filter** | `Filter_Areas_BySize`、`_Largest`、`_Smallest`、`_within_Areas`、`Filter_AttributeValue`、`Filter_Points_Overlapping`、`Filter_Points_bySegmentation`、`Filter_RandomChoice`、`Filter_RelativePosition`、`Filter_Splines_byLength`、`Filter_Splines_within_Areas`、`Filter_Tags` |
| **Get** | `Get_ActorData`、`Get_ActorDataByRef`、`Get_EditorCamera` |
| **Override** | `Override_DataByTag` |
| **Place** | `Place_Assets_OnAGrid`、`Place_OnSpline`、`Place_Point_AtCenter`、`Place_Points_AtIntersections`、`Place_RadialScatter` |
| **Spawn** | `Spawn_Assets`、`Spawn_SplineActor` |
| **Subdivide** | `Subdivide_Areas_WithRecursiveSplit`、`Subdivide_Areas_withGrid`、`Subdivide_Areas_withSpline` |
| **Trace** | `Trace_Bound_Footprint`、`Trace_Bridges`、`Trace_Connect`、`Trace_Splines_ParametricGrid` |
| **Transform** | `Transform_Align`、`Transform_Areas_Contract`、`_Expand`、`Transform_Jitter`、`Transform_Level`、`Transform_Offset`、`Transform_Outline`、`Transform_Points_SpatialNoise`、`Transform_Project`、`Transform_Resample`、`Transform_Splines_Disturb`、`_Extend`、`_Reverse`、`Transform_TrimOut`、`Transform_Truncate` |
| **Write** | `Write_Attribute`、`Write_Attribute_fromProjection`、`Write_Attribute_fromTexture`、`Write_Class`、`Write_DistanceFrom`、`Write_Noise`、`Write_Tag` |
| **Shared** | `MeasureAreas`、`PCGBP_SplitString`、`Splines_CalculateAngleToNextPoint`、`Trim_open_Spline_each_side`、`convert_point_to_polygon` |
| **Debug** | `Debug_PrimitiveData` |

**每个原语都由固定五段结构实现**（见 `_Template_/`）：
`Primitives_BaseTemplate`、`_InputsFallback`、`_InputsProcessing`、`_CoreProcess`、`_PrepareOutputs`。
理解这个约定后，任意原语的内部实现都是可预测的。

### 6.3 与本主题直接相关的两个原语

#### (a) 城市示例图 —— **引擎侧与项目侧各有一套，注意命名区分**

**引擎侧**（`/PCGPrimitives/Examples/City/`）：

```
├── City_Circular_1km_2_arteries_NoAssetLibrary.uasset   ← 基线：1km 环形城 2 条主干道
├── City_European_Medieval_1km_2_arteries.uasset          ← 变体：欧式中世纪
├── City_Generator_Steps_1_Base … _7_city_Contour.uasset  ← 七段串联版本
├── City_Generator_steps.umap                             ← 配套关卡
├── Basic_Building_Row_of_400x50m.uasset
└── Edits/
    └── City_Circular_1km_2_arteries_NoAssetLibrary_Fast.uasset
```

**项目侧**（`/CitySamplePCG/Examples/City/`，**更贴近本文主流水线**）：

```
├── City_Circular_1km_2_arteries.uasset（1.01 MB）
├── City_Circular_1km_2_arteries_slopes.uasset（1.32 MB）
├── Cities_Circular_1km_2_arteries_CombinedAndEnclosed.uasset
├── CitySample_Generator_Steps_1_Base … _7_CitySample_Contour.uasset
├── CitySample_Generator_steps.umap（57.5 MB）
├── Various_Building_Row_of_300x30m.uasset
└── Edits/                                               ← ★ 6 个 prompt 变体
    ├── …_Half_Forest      ├── …_with_Backalleys
    ├── …_with_Customized_landmarks
    ├── …_with_Highway     ├── …_with_embanked_highway
    └── …_with_embanked_river
```

**两套 `Generator_Steps_1..7` 是最有价值的教材**：
它把「一整张大图」拆成**七个顺序依赖的小图**
（Base → Districts → Lots → Ground → Buildings → Left_over_lots → Contour），
与 §4 的 18 图流水线是同一种「分阶段、可单独重跑」的思想，
但规模小得多，适合先吃透再上 18 图。

**项目侧的 `Edits/` 文件夹是 Epic 留给 LLM 的「标定集」**：
每个变体都对应一句明确的 prompt（如 `Half_Forest` 对应
*"Make half the sub-districts spawn trees instead of being subdivided for building."*），
是学习「什么样的 prompt 会改出什么样的图」的最佳素材。

#### (b) `Assign_CitySample_Buildings`

专门为 City Sample 造建筑的 PCG 原语（位于原语库建筑类）：

- 从 `LoadCitySampleData` 子图读取形状语法配置
- 输入**建筑足迹样条**，按最小/最大高度或 `@data.MaxHeight` 属性**挤出**
- 未指定时**随机分配建筑样式码**（`CHA`、`NYAA`、`SFB` …）
- 要求把 `LoadCitySampleData` 子图作为**第二路输入**，以避免重复加载数据库

---

## 7. 建筑样式码表

`Content/PCG/DataAssets/Buildings/` 下的目录名即样式码，本机实测共 **27 个样式码**：

| 地域风格 | 样式码 | 数量 |
|---|---|---|
| **芝加哥（C）** | `CHA` `CHB` `CHC` `CHD` `CHE` `CHF` `CHG` `CHH` `CHI` `CHJ` | 10 |
| **纽约（NY）** | `NYAA` `NYAB` `NYAC` `NYAD` `NYAE` `NYAF` `NYG` `NYGA` `NYH` | 9 |
| **旧金山（SF）** | `SFA` `SFB` `SFC` `SFD` `SFE` `SFJ` | 6 |
| **其他** | `QBA` `QBAA` | 2 |

每目录的**层数不一**：`CHA` 有 `L00–L20`（21 条规则），`NYAA` 有 `L00–L05`，
`SFD` 有 `L00–L04`。全部 Buildings 目录共 **240 条 RULE + 27 个 SGD**。

### 7.1 **关键**：真正参与生成的只有 19 个

`PCG_3_3_1_Buildings` 图内**硬编码了 19 个样式码的白名单**：

```
CHA,CHB,CHC,CHE,CHF,CHG,CHH,CHI,CHJ,NYG,NYGA,NYH,QBA,QBAA,SFA,SFC,SFD,SFE,SFJ
```

**未进入白名单的 8 个**：
`CHD`、`NYAA` `NYAB` `NYAC` `NYAD` `NYAE` `NYAF`、`SFB`。

→ 想让这些样式参与生成，**必须改图的白名单**，仅添加资产目录无效。

配套还有 `Bldg_SGD_level.umap`（样式码预览关卡）、`PCGD_ComplexBuildingShapes.uasset`、
`PCG_Bldg_SGD_test.uasset`。

> **LLM 交互的关键**：每套样式的数据资产里嵌有 **tooltip 元数据**，描述
> 「整体观感 / 建筑类型（住宅·商业·办公）/ 大致建造年代」。
> 因此一句「让城市看起来更老一些，只用老式建筑」可以在**不改图结构**的前提下，
> 靠这个元数据筛选样式码实现。

---

## 8. PCG 装配体与数据资产

`Content/PCG/DataAssets/` 顶层：

| 资产 | 用途 |
|---|---|
| `Buildings/` | 样式码 + 规则（§7） |
| `Roads/` | 道路/人行道/高速的形状语法定义（§5） |
| `RoofTops/` | 屋顶装配体配置 |
| `Plazas/` | 广场装配体配置 |
| `Piers/` | 码头装配体配置 |
| `PCGD_ComplexBuildingShapes.uasset` | 复杂建筑形体 |
| `VistaCliffs_PCG.uasset` | 远景崖壁 |

**PCG Assembly（装配体）** 是「一组静态网格的即用配置」——把屋顶广场、码头这类
「由多个零件拼成的复合物」打包成一个可替换单元，被 `PCG_3_3_2_Rooftops`
与 `PCG_5_1_CityEdge` 消费。

---

## 9. 控制面：MCP 与工具集

这是「用 LLM 驱动这座城市」的关键章节。

### 9.1 MCPSkill 与技能资产

Epic 把「如何用这套东西」写成了**引擎内的技能资产**，位于：

```
Engine/Plugins/Experimental/Toolsets/PCGToolset/Content/Skills/
├── Skill_PCGGraphGeneration.uasset        ← 首选技能，建图/改图总纲
├── Skill_PCGShapeGrammarDefinition.uasset ← 形状语法（§5）
├── Skill_PCGMeshPartition.uasset          ← Mesh Terrain 集成
├── Skill_PCGInstancingOnMeshActor.uasset  ← 表面细节（greeble）
├── Skill_PCGBiomeCore.uasset              ← 生物群系系统
├── Skill_PCGBiomeCoreRefinement.uasset
├── Skill_PCGAssetZoo.uasset
└── Skill_InstantLevelOperations.uasset    ← 即时图操作
```

`Skill_PCGGraphGeneration` 由 C++ 类 `UPCGGraphGenerationSkill : public UAgentSkill` 支撑，
其 `GeneratePrompt_Implementation` 会**模板替换**四个占位符为**实时查询结果**：

| 占位符 | 填充来源 |
|---|---|
| `{Subgraphs}` | `UPCGToolset::ListAvailableSubgraphs()` |
| `{Nodes}` | `UPCGToolset::ListNativeNodes(true)` |
| `{Examples}` | `FindGraphPaths(Constants::GetExamplesDirectories())` |
| `{Instant Graphs}` | `FindGraphPaths(Constants::GetInstantGraphDirectories())` |

**含义**：加载该技能后，智能体拿到的是**当前工程真实的节点/子图/示例清单**，
而非硬编码列表。

`UAgentSkill` 基类（`ToolsetRegistry/Public/ToolsetRegistry/AgentSkill.h`）的字段极简：

```cpp
UPROPERTY(EditDefaultsOnly) FString Description;   // 一句话说明
UPROPERTY(EditDefaultsOnly, meta=(MultiLine=true)) FString Instructions;  // 详细指引
```

并配有一个 `UAgentSkillToolset` 提供 `ListSkills()` / `GetSkills()` /
`CreateSkill()` / `UpdateSkill()` 四个 `AICallable` 工具——
**技能本身也能被 LLM 经 MCP 读写**。

### 9.2 官方推荐工作流（Epic 文档要点）

1. 启用并加载 Unreal MCP 服务器插件
2. **加载 PCG 工具集**（`PCGToolset` 插件，或经 LLM 请求加载）
3. **加载 PCG 图生成技能**（`Skill_PCGGraphGeneration`）——
   官方强调这是**必需的会话初始化步骤**，
   跳过会导致 LLM「误解 PCG 概念 / 过度复杂化方案 / 误用节点与参数」
4. 识别相关**示例图**
5. 在内容浏览器里**手工选中**相关资产/Actor
6. 让 LLM **先读参考再规划**
7. 执行前**先要一份计划或图结构评审**
8. **增量执行**并全程监督
9. 主动纠正

**官方给定的三条原则**：优先复用现成图 → 次选复制改造接近的图 → 万不得已才从零建新图。

**性能警示（官方）**：大图分析、多图分析、广域资产分析都**昂贵**（时间 + 上下文）；
不显式选中资产时，LLM 会「生成临时 Python 脚本来探查内容」，进一步抬高 token 消耗。
**属性检视必须走专用的 Dataview 工作流**——它在正常 token 上下文之外做重处理。

### 9.3 City Sample 与 MCP 的交互实例（官方文档）

| 提示词 | LLM 实际动作 | 触及的图 |
|---|---|---|
| 用更老的建筑风格 | 读建筑图 + 建筑 PCG 图输入，按 tooltip 元数据（观感/类型/年代）筛样式码 | 建筑图 |
| 任何建筑不超过 200m | 找到高度参数，用 **Clamp 节点**截断或写入精确值 | 建筑图 |
| 城市位于热带纬度，调整植被 | **语义搜索**找树资产，替换为热带树 | 植被分支 |
| 光照设为某地某时 | 用 `Default Lighting Outdoor` 技能调太阳位置、大气厚度、体积云材质 | 光照 |
| **道路宽度加倍** | 参数在 **Road PCG Graph** 内，可一次调整**本地/集散/主干**全部等级 | `PCG_3_1_2_Roads` |
| 增加停车位 | 已存在一条从 `PCG_3_2_2_LeftOverLots` 直通停车图的分支，加大喂入即可 | `PCG_3_2_2_LeftOverLots` |
| **新增一档街区尺度** | 识别现有**小/中/大三档分支**，仿照其中一支新建第四档并接回主干 | `PCG_3_1_1_Districts` |
| 移除所有路边停放车辆 | 识别车辆出现在**两处**（停车场 + 街道），需两处分别处理：关掉停车场生成逻辑；街道侧改形状语法定义资产，或复制一份不含车的人行道资产 | `PCG_3_2_3_Parkings` + Roads SGD |

**最后两条是「结构性改图」**，官方明言需要**更深的使用者监督**：
> You need a deeper understanding of how the PCG graph works in order to check
> the quality of the LLM's work.

### 9.4 传输层：`E:\CitySample 5.8` 与 `E:\PCG_Claude` 不同

这是勘查中发现的**最重要的工程约束**，直接决定技能怎么写。

| | `E:\CitySample 5.8` | `E:\PCG_Claude` |
|---|---|---|
| MCP 服务器 | **Epic 官方 `ModelContextProtocol`** | 自研 `UnrealMcpBridge` |
| 传输 | **HTTP + SSE** | 原始 WebSocket |
| 地址 | `http://127.0.0.1:8000/mcp` | `ws://127.0.0.1:8777` |
| Python 脚本执行 | **无 `Content/Python` 根** | `Content/Python/` + `run_unreal_script` |
| 工具暴露方式 | **工具搜索模式**：3 个元工具 | 单一工具 `run_unreal_script` |
| 自动启动 | 是（`bAutoStartServer=True`） | 是（模块加载即启动） |

CitySample 5.8 的 `.mcp.json`：

```json
{
  "mcpServers": {
    "unreal-mcp": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

官方插件 `ModelContextProtocol.uplugin`：`FriendlyName` 为 **Unreal MCP**，
`Description` 为 `Anthropic MCP (Model Context Protocol) server implementation for Unreal Engine.`，
`NoRedist: true`，`EnabledByDefault: false`，含 6 个模块
（`ModelContextProtocol` / `...Engine` / `...Editor` / 三个测试模块）。

服务器常量（`ModelContextProtocol.h`）：

```cpp
static constexpr uint32 DefaultServerPort = 8000;
static constexpr const TCHAR* DefaultServerUrlPath = TEXT("/mcp");
static constexpr const TCHAR* DefaultServerName = TEXT("unreal-mcp");
```

设置类（`ModelContextProtocolSettings.h`）：

```cpp
FString ServerUrlPath = TEXT("/mcp");
uint32  ServerPortNumber = 8000;
bool    bAutoStartServer = false;   // 项目里被显式改成 True
bool    bEnableToolSearch = true;   // 默认即开启工具搜索模式
```

**工具搜索模式**（`bEnableToolSearch = true`）意味着服务器只暴露三个元工具：

- `list_toolsets` —— 列出全部工具集
- `describe_toolset` —— 查某工具集的函数 schema
- `call_tool` —— 派发调用

PCG 工具集必须用**完整点分路径**寻址：

| 工具集 | 用途 |
|---|---|
| `PCGToolset.PCGToolset` | 建图 / 加节点 / 连线 / 图参数 / 实例 / 执行 / 检视 / 注释框 |
| `PCGToolset.PCGSpatialToolset` | `RunPCGInstantGraph`（即时图） |
| `EditorToolset.EditorAppToolset` | 视口截图等 |
| `EditorToolset.LogsToolset` | 日志 |
| `editor_toolset.toolsets.asset.AssetTools` | 资产搜索/删除/保存 |
| `editor_toolset.toolsets.object.ObjectTools` | 属性读写 |
| `editor_toolset.toolsets.actor.ActorTools` | 组件 |
| `editor_toolset.toolsets.scene.SceneTools` | 场景摆放 |
| `editor_toolset.toolsets.blueprint.BlueprintTools` | 蓝图 |
| `editor_toolset.toolsets.data_table.DataTableTools` | 数据表 |
| `editor_toolset.toolsets.static_mesh.StaticMeshTools` | 网格包围盒 |
| `editor_toolset.toolsets.programmatic.ProgrammaticToolset` | 脚本化兜底 |

编辑器控制台命令：
`ModelContextProtocol.StartServer [port]` / `.StopServer` / `.RefreshTools`。

### 9.5 `PCGToolset` 的完整工具清单（源码实测）

**图**
- `CreateGraph(Name, Path="/Game/PCG")`

**图参数**
- `GetGraphStructure(Graph)` / `GetGraphSchema(Graph)`
- `SetGraphParams(Graph, Params[])` / `RemoveGraphParams(Graph, Names[])`
- `GetGraphDescription(Graph)` / `SetGraphDescription(Graph, Description)`

**图实例**
- `ListGraphInstances()`
- `SpawnGraphInstance(Graph, Name, Transform, JsonParams="")`
- `ExecuteGraphInstance(PCGVolume)` ← 执行
- `GetGraphInstanceParams(PCGVolume)` / `SetGraphInstanceParams(PCGVolume, JsonParams)` /
  `ResetGraphInstanceParams(...)`

**节点**
- `ListNativeNodes(bCommonOnly=true)` / `ListAvailableSubgraphs()` /
  `GetNativeNodeSchema(NodeName)`
- `AddNode(Graph, NativeNodeType, NodeName, JsonParams, NodeTitle, NodeComment, XPos, YPos)`
- `AddSubgraphNode(Graph, SubGraphForNode, NodeName, JsonParams, NodeTitle, NodeComment, XPos, YPos)`
- `UpdateNode(Node, JsonParams, NodeTitle)` / `SetNodeComment(Node, Comment)` / `GetNodeInfo(Node)`
- `RepositionNode(Node, X, Y)` / `RemoveNode(Graph, Node)`
- `ConnectNodePins(FromNode, FromPin, ToNode, ToPin)` → **返回被自动插入的转换/过滤节点**
- `DisconnectNodePins(FromNode, FromPin, ToNode, ToPin)`

**数据**
- `GetNodeDataView(PCGVolume, Node, PinLabel="Out", AttributeName, StartIndex=0, EndIndex=-1)`

**注释框**
- `AddCommentBox(Graph, Nodes[], Comment, Color)` / `UpdateCommentBox(...)` / `RemoveCommentBox(...)`

**其他**
- `DrawSpline(ActorLabel, ActorTag, bRedraw, bClosedSpline)` ← 交给人手在视口画样条，**阻塞**

**`PCGSpatialToolset`**
- `RunPCGInstantGraph(Graph, Params)` —— 注意其文档注释明确写道
  *"Should be called directly: Not callable in a python context execution context"*

---

## 10. 编程接口：Python / Blueprint 可达面

**这是本次分析最有工程价值的结论。**

### 10.1 好消息：`UPCGGraph` 本体完全可脚本化

`Engine/Plugins/PCG/Source/PCG/Public/PCGGraph.h`，
类 `UPCGGraph : public UPCGGraphInterface`，
下列函数全部是 **`UFUNCTION(BlueprintCallable)`** → **PyGenUtil 会生成 Python 绑定**：

```cpp
UPCGNode* AddNodeOfType(TSubclassOf<UPCGSettings>, UPCGSettings*& OutSettings);
UPCGNode* AddNodeInstance(UPCGSettings*);
UPCGNode* AddNodeCopy(const UPCGSettings*, UPCGSettings*& OutSettings);
void      RemoveNode(UPCGNode*);
void      RemoveNodes(TArray<UPCGNode*>&);
UPCGNode* AddEdge(UPCGNode* From, const FName& FromPinLabel,
                  UPCGNode* To,   const FName& ToPinLabel);
bool      RemoveEdge(UPCGNode* From, const FName& From, UPCGNode* To, const FName& To);
UPCGNode* GetInputNode() const;
UPCGNode* GetOutputNode() const;
TArray<UPCGEdge*> GetAllEdges() const;
```

Python 侧形如：`graph.add_node_of_type(...)`、`graph.add_edge(from_node, "Out", to_node, "In")`。

**结论：建图 + 加节点 + 连线这条完整回路，不需要编辑器专用代码、
不需要工具集、不需要 MCP。**

> 注意有若干**仅 C++** 的同名/近似成员（无 `UFUNCTION`）：
> `AddLabeledEdge(...)`（唯一会返回「是否发生单引脚替换」的那个）、
> `AddNode(UPCGSettingsInterface*)`、`AddNode(UPCGNode*)`。
> Python 可达的创建路径是 `AddNodeOfType` / `AddNodeInstance` / `AddNodeCopy`。

### 10.2 `UPCGComponent` 同样可脚本化

`PCGComponent.h`，全部 `BlueprintCallable`：

```cpp
UPCGGraph* GetGraph() const;
void       SetGraph(UPCGGraphInterface*);      // NetMulticast, Reliable
void       SetGraphLocal(UPCGGraphInterface*);
void       GenerateLocal(bool bForce);
void       CleanupLocal(bool bRemoveComponents);
void       Generate(bool bForce);              // NetMulticast, Reliable
void       Cleanup(bool bRemoveComponents);    // NetMulticast, Reliable
void       CancelGeneration();
const FPCGDataCollection& GetGeneratedGraphOutput() const;
AActor*    ClearPCGLink(UClass* TemplateActor = nullptr);
```

**实践建议**：编辑器里优先用 `generate_local` / `cleanup_local`，
行为确定且立即生效（`Generate`/`Cleanup`/`SetGraph` 是 `NetMulticast`）。

注意 `GetGraphInstance()` 是**纯 C++**，无 `UFUNCTION`。

### 10.3 坏消息：`PCGToolset` 的 `AICallable` 函数**不能**直接从 Python 调

在生成代码 `PCGToolset.gen.cpp` 中实测其函数标志为：

```
EFunctionFlags = 0x00022401 = FUNC_Final | FUNC_Native | FUNC_Static | FUNC_Public
```

**不含 `FUNC_BlueprintCallable`**（`0x04000000`）。
而 `PyGenUtil.cpp` 的 `IsScriptExposedFunction` 要求
`FUNC_BlueprintCallable | FUNC_BlueprintEvent`。

→ **不存在 `unreal.PCGToolset.add_node(...)`**。
唯一 Python 路径是间接的 `unreal.ToolsetRegistry.execute_tool(...)`，或走 MCP。

### 10.4 `UToolsetRegistry`：把两者接起来的那个桥

`UToolsetRegistry : public UBlueprintFunctionLibrary`，
全部 `BlueprintCallable` / `BlueprintPure`，**因而 Python 可达**：

```cpp
static bool IsAvailable();
static void RegisterToolsetClass(TSubclassOf<UToolsetDefinition>);
static void UnregisterToolsetClass(TSubclassOf<UToolsetDefinition>);
static bool IsToolsetClassRegistered(TSubclassOf<UToolsetDefinition>);
static bool IsToolsetRegistered(const FString& InToolsetName);
static UToolCallAsyncResultString* ExecuteTool(
    const FString& ToolsetName, const FString& ToolName, const FString& JsonInput);
static FString GetToolsetJsonSchema(TSubclassOf<UToolsetDefinition>);
static FString GetAllToolsetJsonSchemas();
```

`PCGToolsetModule.cpp` 在模块启动时注册：

```cpp
UToolsetRegistry::RegisterToolsetClass(UPCGToolset::StaticClass());
UToolsetRegistry::RegisterToolsetClass(UPCGSpatialToolset::StaticClass());
```

工具集名由 `FFunctionLibraryToolset::GetToolsetClassName()` 取
**UClass 名去掉 `U` 前缀**：`"PCGToolset"` / `"PCGSpatialToolset"`。
（但**实测经验**是：MCP 侧应以 `PCGToolset.PCGToolset` 这类**完整点分路径**寻址，见 §11 坑 1。）

`ExecuteTool` 返回的 `UToolCallAsyncResultString` 是**异步**的
（内部走 `TFuture<TValueOrError<FString, FString>>`），
`ToolsetRegistry/Content/Python/toolset_registry/tests/test_execute_tool.py`
有现成用法可参考。

### 10.5 对象指针如何跨越 JSON 边界

机制在 `ToolsetRegistry/Private/ToolsetRegistry/ReferenceConverter.cpp`：

- 出站：`Reference.RefPath = SoftObjectPath->ToString()` → 对象被序列化为**软路径字符串**
- 入站：取 `RefPath` → `FSoftObjectPath(RefPath)` → `ResolveObject()`，未加载则 `TryLoad()`

**没有 GUID、没有不透明句柄。**

**工程含义（重要）**：

- **资产**（图、子图）有稳定包路径，跨多次调用可靠
- **`UPCGNode*`** 是图包的临时子对象，只在图加载期间可解析
  → 因此工具集 API 特意采用**字符串 `NodeName`** 作为节点标识
  （`AddNode` 文档写明 "Must be unique identifier in the graph"）

→ **多轮搭建时，请以自定义的 `NodeName` 为键、每轮重新解析，
不要跨调用缓存节点引用对象。**

### 10.6 明确的负面结论（同等重要）

| 能力 | 状态 |
|---|---|
| `UPCGSubsystem` 的脚本暴露 | **零**。整个头文件无 `BlueprintCallable`；`UPCGComponent::GetSubsystem()` 是纯 C++ |
| `PCGEditor` 模块的脚本面 | **几乎没有**。仅 `PCGWorldPartitionBuilder.h` 与 `PCGLevelToAsset.h` 提及 `BlueprintCallable` |
| 编辑器级图编辑库（如 `UPCGEditorGraphLibrary`） | **不存在**。节点视觉定位与注释框**只能**经 `UPCGToolset` 到达 |
| `PCGPythonInterop` 能否建图 | **不能**。它是反方向的——让 Python **在 PCG 图内部运行**（`UPCGExecutePythonScriptSettings`、`UPCGPythonDataBridge` 等），不是建图 |
| `RunPCGInstantGraph` | 文档明写**不可在 Python 执行上下文中调用** |
| `PCGPrimitives` | 纯内容插件，无 C++、无 Python |
| `UPCGToolset` 本体 | `EditorOnly: true`、`EnabledByDefault: false`、`LoadingPhase: PostEngineInit` |

### 10.7 哪些结论适用于落地项目 `PCG_Claude`

本章大部分内容是**站在 CitySample 侧**（有官方 MCP + 工具集）写的。
搬到只有单 Python 工具的 `PCG_Claude` 时，适用性如下：

| § | 结论 | 在 `PCG_Claude` 是否适用 |
|---|---|---|
| 10.1 | `UPCGGraph` 的 `AddNodeOfType` / `AddEdge` 等是 `BlueprintCallable` | **适用**，且**正是落地项目的唯一建图路径**（因为工具集不可用） |
| 10.2 | `UPCGComponent` 的 `GenerateLocal` / `CleanupLocal` / `GetGeneratedGraphOutput` 是 `BlueprintCallable` | **适用**，是落地项目的执行与读结果入口 |
| 10.3 | `PCGToolset` 的 `AICallable` 函数不能直接 Python 调 | **不适用**——落地项目**根本没启用 `PCGToolset`**，这条无意义 |
| 10.4 | `UToolsetRegistry::ExecuteTool` 是 Python 可达的桥 | **不适用**——该桥通向工具集，而落地项目没有工具集 |
| 10.5 | 对象指针以**软路径字符串**跨 JSON 边界，`UPCGNode*` 只在图加载期可解析 | **适用**，而且是落地项目里**唯一的跨调用状态传递方式**（因为工具集提供的 `NodeName` 寻址也不存在了） |
| 10.6 | `UPCGSubsystem` 零脚本暴露 | **适用** |

**对落地项目的两条实践推论**：

1. **节点定位要靠自己维护。** 工具集提供 `NodeName` 字符串寻址；
   没有工具集后，多轮搭建时要么**每轮重新遍历** `graph` 的节点重新解析，
   要么**把 `NodeName` 写进节点标题/注释**再按名字找回来。**不要跨调用缓存节点对象。**
2. **没有 `GetNodeDataView` 就等于没有官方数据检视工作流。**
   §9.2 说的"用 Dataview 检视属性"在落地项目**不成立**，
   验证只能走 `GetGeneratedGraphOutput()` + 点数据读取，或统计生成的 Actor 数。

---

## 11. 已知坑与规避手册

以下 13 条来自**本项目内一次完整的 PCG 城镇生成实践**
（`docs/superpowers/` 下的 spec 与 8 个任务的决策日志），全部为实测踩坑记录。

> **PCG 最大风险是「静默零点」**：配置错误不报错，只是不出点/不出网格。
> 以下全部是前置规避。

| # | 坑 | 规避 |
|---|---|---|
| 1 | `Surface Sampler` 必须喂**真实 Surface 数据**；`Input` 节点的 Volume 过滤成 Surface 是空的，`World Ray Hit` 在非 PIE 编辑器上下文也采不到 | 用 `Create Polygon 2D` → `Create Surface From Polygon2D` 自造表面 |
| 2 | `Static Mesh Spawner` 的网格**不能**经 `AddNode` 的 `jsonParams` 设置（实例化子对象） | 先建空参节点，再对 `DefaultSelectorInstance` 用 `ObjectTools.set_properties` 二次写入 |
| 3 | MCP **数组属性追加只能 0→1**，多元素数组写不进去 | 需要多行/多网格的地方用多分支或表行承载 |
| 4 | Spawner 需 `bSynchronousLoad=true` | 否则 MCP 触发的**首次执行因异步加载看不到结果** |
| 5 | `GetNodeDataView` **首调只是启用检视**，返回 no data；且 `attributeName` 描述说可省、schema 却标必填 | 传 `attributeName: ""`，再 `ExecuteGraphInstance` 一次后读取 |
| 6 | `Self Pruning` 前必须 `Bounds Modifier` 设**真实包围盒**（点默认包围盒极小，永不剪枝） | 在布局层用 `FootprintExtent` 作为界 |
| 7 | `Spline Intersection` 的 `bUseBestFitBox=true` 会让 PCA 使四元数绕 XY 轴翻转约 180°，**网格倒扣** | 设 `bUseBestFitBox=false`，下游保持加性旋转继承 |
| 8 | 无缝路口**不是边对边** | 套件式重叠：裁剪框（17×7）**故意小于**垫块（20×11），路伸入垫块下方，垫块抬 +3cm 盖缝 |
| 9 | `SM_ROAD` 枢轴不居中 | 垫块局部偏移 `Y=-500`；`Spawn Spline Mesh` 的 `startOffset/endOffset.x = -500` |
| 10 | `Spline Sampler` 在 Distance 模式下，当 `startOffset+endOffset ≥ 段长` 时**静默零点** | 切断后的路段可能短于 25m → `offset` 合计 ≤ 200cm |
| 11 | `Spawn Actor` 生成的建筑会**继承上游微缩尺度 → 不可见** | 生成后重置为绝对缩放并轴对齐 |
| 12 | `CaptureViewport` 必须传**完整 annotations 对象**（6 个子字段全给）；返回 base64 需解码 | 需要视口截图验证时照此处理 |
| 13 | 属性驱动解析（ByAttribute 网格选择器、Spawn Actor 按属性选类、DataTable 建行/读行）**全部需要 spike 验证** | 涉及实例化子对象时仍走第 2 条的两步法 |

### 11.1 来自决策日志的额外硬约束

| 约束 | 后果 |
|---|---|
| **无通用 Struct 创建工具** | 任何「新建自定义 Struct 资产」的设想做不到；只能用既有 struct，或塞进蓝图变量 |
| **无新建 Level 资产工具** | 只有 `load_level`/`get_current_level`/`create_level_instance`（后者建的是引用现有关卡的 Level Instance Actor）。需全新地图时只能人工 New Level，或复制现有 `.umap` |
| **`PCGVolume` 类工具拒绝蓝图 Actor** | 参数校验/执行/检视**只能作用于原生 `PCGVolume`** |
| **BP 的 `bCallInEditor` 不可经反射写入** | 「CallInEditor 按钮」方案需换实现 |
| **`GetNodeDataView` 检视状态是「图资产级」共享** | 同一图被多个 Actor 使用时，**并发调用会冻结编辑器** → 必须**全程串行** |
| **`ConnectNodePins` 会静默插入转换节点** | 不能假设「连接后节点数不变」，要检查返回值 |
| **`ListNativeNodes` 无关键词过滤** | 只能全量枚举再自行筛选；`GetNativeNodeSchema` 需先猜对节点名 |
| **`Spline Intersection` 输出角点相对精确网格坐标系统性内缩 2.5177cm** | 已知系统性偏差，验收时按此解释 |
| **5×5 规模下路段数比公式少 1** | 经复核**非缺陷**，已排除 |

---

## 12. 用 MCP 快速搭一座城市的推荐流程

综合 §4（官方流水线）、§9（官方工作流）、§10（可达面）、§11（坑表）。

### 12.1 前置

1. 打开 `E:\CitySample 5.8`，**确保编辑器在运行**
   （MCP 服务器随编辑器自启，端口 8000）
2. 确认 `ModelContextProtocol`、`PCG`、`PCGToolset`、`AllToolsets` 已启用
3. 会话初始化顺序（官方强制）：
   `list_toolsets` → `describe_toolset("PCGToolset.PCGToolset")` →
   加载 `Skill_PCGGraphGeneration`
4. **在内容浏览器里手工选中**要参考的示例图（`PCGPrimitives/Examples/City/`），
   避免 LLM 生成临时脚本探查内容、抬高 token

### 12.2 两条路线

#### 路线 A —— 复用 18 图流水线（最忠于 City Sample）

1. **不要从零建图**。复制 `CitySamplePCG/Content/Levels/PCG/` 下的图，
   或直接用现成图实例
2. 在关卡内放置 `PCGVolume`，用 `SpawnGraphInstance` 挂图
3. **调样条，不调图**：改 §4.3 的五组手工样条，即可换出一座形状完全不同的城市
4. 按编号顺序 `ExecuteGraphInstance`（`PCG_1_1` → … → `PCG_5_2`），
   上游改动会触发下游重建
5. 参数级微调用 `SetGraphInstanceParams`
   （道路宽度、高度上限、停车量、植被替换）
6. 迭代期建议**开启 PCG 暂停按钮**（编辑器偏好），避免每次编辑触发全链重建
7. 资源密集的图（road / lots / buildings）用 **debug 模式**先调布局
8. 重置：`Tools > PCG framework > Cleanup All PCG components`，
   再按 Outliner 顺序重新生成

#### 路线 B —— 自建轻量城市（对照 `City_Generator_Steps` 七段式）

适合先吃透机制。以
`Create Points Grid → Spline → Spline Intersection` 起手生成规整路网，
再逐簇加建筑/植被/街道家具。**必须走 §10.1 的 `UPCGGraph` 脚本路径**，
因为这是唯一能可靠批量建节点的方式。

### 12.3 关于 World Partition

- 逐图开启 **Partition Grid Size**（默认 128m），
  PCG 才会生成局部化分区 Actor 而非单个巨型 Actor
- **建筑图需手动勾选碰撞生成**
- 在 World Settings 开启 streaming 后，生成前需在 World Partition 编辑器里
  **手工加载**相关 Actor（所有被引用的 Actor 必须已加载）
- 完全分区后的城市约 **2600 个独立 Actor**

### 12.4 样条绘制

`PCGToolset.DrawSpline(ActorLabel, ActorTag, bRedraw, bClosedSpline)`
会把控制权交给**人类**在视口画线，**该调用会阻塞**直到画完。
让 LLM 先画骨架样条再跑图，是「人机分工」的自然切分点。

---

## 13. 未确认 / 待补充

诚实标注本次分析的边界：

| 项 | 状态 |
|---|---|
| 18 张图的**节点级连线细节** | **已重建到子图调用粒度**（见 §4.5），但未逐节点导出完整 DAG。需在运行中的编辑器里用 `GetGraphStructure` 逐图导出 |
| `Assign_CitySample_Buildings` 的**精确参数 schema** | 仅据官方文档与 import table 描述，未读节点 schema |
| `LoadCitySampleData` 子图的**内部数据结构** | 未读取 |
| `BDF_BuildingFromSpline`（1.78 MB）**内部逻辑** | 未拆解——这是建筑流水线最核心也最复杂的子图 |
| 各图的 **User Parameter 完整清单与默认值** | 只提取到部分（如 `CityFlatness`、`Block grid length…`、`BuildableLotMin/MaxSize…`）。需用 `GetGraphSchema` 逐图导出 |
| `/CitySample_PCG_Extras/` 路径 | `DefaultEditor.ini` 的 `ExampleGraphDirectories` 指向它，但**磁盘上不存在该挂载点**——上游配置残留。使用前需在编辑器内 `ListAvailableSubgraphs()` 实际确认 |
| `Edits/` 变体的**逐条 prompt 元数据文本** | 概念已确证（`Half_Forest` 对应植树 prompt），其余 5 条的具体文本未提取 |
| `ExecuteTool` 的 `JsonInput` **精确形状** | 高置信推断为「裸的具名参数对象」（无 `Args` 包裹），依据是 MCP 适配层把 `params` 整体序列化为 `ArgumentsJson`。**未实测** |
| `Reference` 结构体的**外层 JSON 键名** | `RefPath` 为内层字段名已确证，外层包装未读 |
| `UToolCallAsyncResultString` **如何同步读取** | 头文件未读。建议参考 `ToolsetRegistry/Content/Python/toolset_registry/tests/` 下的现成用法 |
| `call_tool` 的**两套参数形态** | `GetNodeDataView` 实测需 `arguments` 包裹，而更早的 `ObjectTools` 记录用直接顶层参数。**两者矛盾未排查**，遇到报错时两种都试 |

### 13.1 一处配置不一致（值得知道）

`Config/DefaultEditor.ini` 把 `PCGToolset` 的子图搜索路径指向
**`/PCGPrimitives/Primitives`**，而**不是** `/CitySamplePCG/PCG/Primitives`：

```ini
[/Script/PCGToolset.PCGToolsetSettings]
+SubgraphDirectories=(Path="/PCGPrimitives/Primitives")
+SubgraphDirectories=(Path="/PCGPrimitives_MeshPartitionInterop/Primitives")
+ExampleGraphDirectories=(Path="/PCGPrimitives/Examples")
+ExampleGraphDirectories=(Path="/CitySample_PCG_Extras/Examples")
+ExampleGraphDirectories=(Path="/PCGPrimitives_MeshPartitionInterop/Examples")
+InstantGraphDirectories=(Path="/PCGPrimitives/Instants")
```

**含义**：`ListAvailableSubgraphs()` 返回的清单**不包含** CitySamplePCG 自己的
23 个项目级原语（`Assign_CitySampleBuildings`、`BDF_*` 等）。
需要在图里用它们时，要**直接按路径引用**，不能指望从子图清单里发现。
`/CitySample_PCG_Extras/` 是**悬空路径**（见上表），会静默无贡献。

---

## 14. 参考项目 vs 落地项目

**这是使用本文前必须分清的一件事。**

| | `E:\CitySample 5.8` | `E:\PCG_Claude`（skill 实际执行处） |
|---|---|---|
| 角色 | **参考流水线**：本文描述的 18 张图、27 个样式码、全部形状语法资产都在此 | **落地项目**：配套 skill 在此搭城市 |
| MCP 服务器 | Epic 官方 `ModelContextProtocol` | 项目自研 `UnrealMcpBridge` |
| 传输 | HTTP + SSE `http://127.0.0.1:8000/mcp` | WebSocket `ws://127.0.0.1:8777` |
| 工具形态 | 工具搜索模式：`list_toolsets` / `describe_toolset` / `call_tool` | **单一工具** `run_unreal_script(script_path, args)` |
| 脚本根 | 无 `Content/Python` | `Content/Python/`（脚本必须放这里） |
| PCG 启用状态 | 已启用（`PCG` + `PCGToolset` + `AllToolsets`） | **已启用**（2026-09-23 加入 `PCG` + `PCGPrimitives`）；编辑器需重启后生效 |

### 14.1 为什么不能把 18 张图搬过来

CitySamplePCG 的图**深度依赖 CitySample 项目的美术资产**——
`/Game/Building/Library/` 的 27 个样式码建筑蓝图、`/Game/Road/Kit_City_Road/` 的路面网格、
`/Game/Prop/` 的树木道具、Megascans 材质等。
`E:\PCG_Claude` 里**没有任何这些资产**，也没有 PCG 内容。

→ **「严格按照 City Sample 的 PCG 流程」在落地项目中指的是「方法同构」，不是「资产同款」。**

### 14.2 可搬迁的部分

| 能搬 | 不能搬 |
|---|---|
| **分阶段流水线的方法论**（§4.2 的数据流主线） | 18 张图资产本身 |
| **手工样条作为唯一人工入口**的设计（§4.4） | 27 个样式码与形状语法资产 |
| **形状语法的制作者工作流**（§5.2） | `/CitySamplePCG/` 挂载点下的任何内容 |
| **引擎自带的原语库**（§6，`PCGPrimitives`，与项目无关） | — |
| **全部坑表与规避手册**（§11） | — |
| **`PCGGraph` 的 Python 可达面**（§10.1–10.2） | `PCGToolset` 的 24 个工具（那是工具集，不是 Python API） |

**落地项目的实际路线**：以引擎原语库（`PCGPrimitives`，约 80 个自含子图）为词汇表，
参照 §4.2 的分阶段思路自建轻量城市，
并对照引擎自带的 `PCGPrimitives/Examples/City/City_Generator_Steps_1..7` 七段式教学图（§6.3）。

### 14.3 落地项目缺什么工具能力

`PCG_Claude` 用的是单 Python 工具桥，**没有** CitySample 那边的 `EditorToolset` 家族
（`AssetTools` / `ObjectTools` / `SceneTools` / `BlueprintTools` / `StaticMeshTools` 等），
**也没有** `PCGToolset`。因此：

- 资产搜索、属性读写、场景摆放**都要自己写 Python 调 `unreal.*` API**
- `GetNodeDataView`（数据检视）**完全不可用**——它是 `PCGToolset` 的函数
  → 验证生成结果需改用 `UPCGComponent::GetGeneratedGraphOutput()` 或引擎端其他脚本可达面
- 官方文档里「让 LLM 用 Dataview 检视属性」的工作流**在此不适用**

→ §11 的坑表中，凡依赖工具集的解法（如坑 2 的 `ObjectTools.set_properties` 两步法）
**都需要翻译成纯 Python 等价写法**。

---

## 15. 参考来源

### Epic 官方文档

- [City Sample PCG for Unreal Engine](https://dev.epicgames.com/documentation/unreal-engine/city-sample-pcg-for-unreal-engine?lang=en-US)
- [Working with PCG and LLMs Using Unreal MCP](https://dev.epicgames.com/documentation/unreal-engine/working-with-pcg-and-llms-using-unreal-mcp-in-unreal-engine?lang=en-US)
- [City Sample PCG and MCP Server Interaction](https://dev.epicgames.com/documentation/unreal-engine/city-sample-pcg-and-mcp-server-interaction-in-unreal-engine?lang=en-US)
- [Unreal MCP in Unreal Editor](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor?lang=en-US)
- [City Sample gets a major update with PCG and Unreal MCP workflows](https://www.unrealengine.com/learning/city-sample-gets-a-major-update-with-pcg-and-unreal-mcp-workflows)

### 本机源码（只读勘查）

- `Engine/Plugins/PCG/`（`PCGGraph.h`、`PCGComponent.h`、`PCGSubsystem.h`、`PCGEditor`）
- `Engine/Plugins/Experimental/PCGPrimitives/`
- `Engine/Plugins/Experimental/Toolsets/PCGToolset/`
- `Engine/Plugins/Experimental/ToolsetRegistry/`
- `Engine/Plugins/Experimental/ModelContextProtocol/`
- `Engine/Plugins/PCGInterops/PCGPythonInterop/`

### 本机资产与既有实践

- `E:\CitySample 5.8\Plugins\Experimental\CitySamplePCG\`
- `E:\CitySample 5.8\docs\superpowers\specs\2026-09-03-pcg-town-generator-design.md`
- `E:\CitySample 5.8\docs\superpowers\plans\2026-09-03-pcg-town-decisions.md`
- `E:\CitySample 5.8\docs\superpowers\plans\2026-09-03-town-asset-map.md`
- `E:\CitySample 5.8\.superpowers\sdd\2026-09-03-pcg-town-generator\`（8 个任务的 brief/report）
