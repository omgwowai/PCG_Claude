# City Sample PCG 流水线地图

> **规划前必读。** 本文是"该动哪张图 / 该改哪个参数"的索引。
> 所有路径的挂载点是 `/CitySamplePCG/`（插件内），不是 `/Game/`。

---

## 1. 一句话架构

**18 张图 = 18 个 `PCGVolume` Actor，全部在关卡 `L_CitySamplePCG_Demo` 里，
每个 Volume 跑一张图；阶段之间靠 `Get_ActorDataByRef` 按 Actor 名取上一阶段的输出。**

```
手绘样条（7 个手工 Actor）
        │
        ▼
PCGVolume #1  ──► PCGVolume #2 ──► … ──► PCGVolume #18
（各自跑一张图，通过 Get_ActorDataByRef 读上游 Actor）
```

**关键含义**：想让城市重新生成，**不必从第一张图重跑到底**——
只要上游 Actor 的数据还在，可以从任意中间阶段单独重跑。

---

## 2. 关卡与装配

| 项 | 值 |
|---|---|
| 关卡 | `/CitySamplePCG/Levels/L_CitySamplePCG_Demo` |
| 类型 | World Partition + `LevelIsUsingExternalActors` |
| HLOD 层 | `HLODLayer_Instanced` / `HLODLayer_Merged` |
| 外部 Actor 数 | 194 |
| 关卡内 PCGVolume | **18 个**，Outliner 标签恰好等于 18 张图的名字 |
| 第 19 个相关 Actor | `BP_ShapeGrammarDefinition_C` + PCGVolume + PCGComponent |

其余 Actor 是灯光/大气，以及 1 个 `PlayerStart`。
标签 `PCG_GridSize_0` 出现 5 次。

---

## 3. 手绘样条：唯一的人工介入点

这 7 个手工 Actor 决定了城市形态。**换一座完全不同形状的城市，改这些即可，不必改图。**

| Actor 名 | 用途 |
|---|---|
| `CityShape` | 城市边界 |
| `Artery_1` / `Artery_2` / `Artery_3` | 三条主干道 |
| `Highway`（+ `Highway_Width`） | 高架高速及其宽度 |
| `MainTowerPark` | 主塔所在园区 |
| `LandmarkPark` | 地标园区 |
| `Terrain_shaping_1` | 地形形变轮廓 |

重画在 CitySample 侧用 `PCGToolset.PCGToolset.DrawSpline`（会阻塞，等用户手绘）。
**本项目没有该工具**——样条要么脚本直接构造（`unreal.SplineComponent` 的
`add_spline_point` 之类，先验证 API），要么请用户在编辑器里手画。

---

## 4. 18 张阶段图

按编号顺序执行。上游改动会引发下游重建。

| # | 图名 | 大小 | 职责 |
|---|---|---|---|
| 1 | `PCG_1_1_Terrain` | 328 KB | 用 `Terrain_shaping_1` 塑造地形岛屿（约 3km × 3km） |
| 2 | `PCG_1_2_BG_Buildings` | 156 KB | 背景城市剪影，**排除中心区** |
| 3 | `PCG_1_3_BG_Mountains` | 94 KB | 远景崖壁剪影（**唯一不调用任何原语的图**） |
| 4 | `PCG_2_1_MainTower_Footprint` | 78 KB | 主塔六边形样条足迹 → **作为排除区** |
| 5 | `PCG_2_2_CentralPark_Footprint` | 52 KB | 中央公园矩形样条 → **作为排除区** |
| 6 | `PCG_3_1_1_Districts` | 605 KB | **核心分区分块**：产出 artery/collector/local 三级路网 + district/sub-district/block |
| 7 | `PCG_3_1_2_Roads` | **1.81 MB** | **路口求解** + 形状语法 + 投影整平 + 车道宽度嵌入足迹 |
| 8 | `PCG_3_1_3_Highways` | 351 KB | 高架高速 |
| 9 | `PCG_3_1_4_Lots` | 1.42 MB | 由城市形状 + 道路足迹解出**建筑地块** |
| 10 | `PCG_3_2_1_Ground` | 1.32 MB | 人行道 / 路缘石 / 广场铺装 |
| 11 | `PCG_3_2_2_LeftOverLots` | 1.66 MB | 剩余空间：**广场 + 植被**（并分流至停车场） |
| 12 | `PCG_3_2_3_Parkings` | 1.08 MB | 停车场 |
| 13 | `PCG_3_3_1_Buildings` | 1.71 MB | **建筑主体**（形状语法中枢） |
| 14 | `PCG_3_3_2_Rooftops` | 355 KB | 屋顶装配体 |
| 15 | `PCG_4_1_MainTower_Visuals` | 2.01 MB | 主塔视觉 |
| 16 | `PCG_4_2_CentralPark_Visuals` | **2.37 MB** | 公园道路/步道/湖面/树草散布/博物馆式建筑 |
| 17 | `PCG_5_1_CityEdge` | 219 KB | 海岸码头 / 仓库 |
| 18 | `PCG_5_2_OuterForest` | 784 KB | 外围密林，向水域渐隐 |

---

## 5. 各阶段的内部结构

### 1.1 Terrain
`Get_ActorData`(CityShape, Terrain_shaping_1) → `Trace_Bound_Footprint` →
`Extract_Bounds` → `Compose_Areas_Exclusion` →
`Transform_{Areas_Expand, Offset, Project, Points_SpatialNoise}` →
经 `/Script/MeshPartition` 读写 MeshTerrain。

节点标签：`READ TERRAIN` / `Expand Footprint 600m` / `Flatten over city footprint` /
`Project City Flat Zone` / `Move City Shape Up` / `Write Mesh Terrain`。

参数 **`CityFlatness`**——图内文档：
*"Lerp between the hill-only terrain (InA) and the city-flat terrain (InB).
Ratio driven by (1 - CityFlatness)."*

### 1.2 BG Buildings
`Create_Spline_Shape` → `Compose_Areas_Exclusion` → `Fill_Areas_Randomly` →
`Filter_RandomChoice` → `Spawn_Assets`。
生成 `/Game/Environment/Background_City/Mesh/SM_bgcitya|b|b_NotNanite`，
材质 `/CitySamplePCG/Materials/BackGroundCity/MI_BackgroundCity`。

### 1.3 BG Mountains
最小的图。直接消费 `VistaCliffs_PCG`（`UPCGDataAsset`）+ `MI_MeshTerrain_CitySamplePCG`。
**完全没调用任何 PCGPrimitives 原语。**

### 2.1 / 2.2 地标足迹
`Create_Spline_Shape` + `Transform_Offset` + `Debug_PrimitiveData`。

2.1 图内文档：*"Defines the hero tower landmark footprint as a parametric
hexagonal spline shape. Consumed by downstream graphs as the boundary for the
main tower complex."*

2.2：*"Ensure footprint is set to the ground level, regardless of the PCG actor
position in Z"*。

### 3.1.1 Districts —— 路网等级在此诞生
`Subdivide_Areas_withSpline`、`Subdivide_Areas_withGrid`、
`Subdivide_Areas_WithRecursiveSplit`、`Filter_Areas_BySize`、`Create_Mesh_Planar`(debug)。

节点注释：`ARTERY ROADS` / `COLLECTOR ROADS` / `LOCAL ROADS` / `LARGE DISTRICTS` /
`MEDIUM DISTRICTS` / `Dividable districts` / `Districts Subdividing Splines`。

**参数**：
- `Block grid length for Large|Medium|Small districts (cm)`
- `Block grid width for Large|Medium|Small districts (cm)`
- `Dividable_district_Limit`
- `SubDistrictSeed`
- `Debug_DistrictCategories`

> **"新增一档街区尺度"** = 仿照现有小/中/大三档中的一支新建第四档并接回主干。
> 官方文档把这个列为"结构性改图"示例。

### 3.1.2 Roads —— 最大的结构性图
`Assign_ShapeGrammarDefinition` + `Assign_Assets` + `Spawn_Assets`、
`Compose_Spline_Cut`、`Extract_Segments`、`Place_OnSpline`、`Place_Point_AtCenter`、
`Transform_{Resample, Outline, Jitter, Level, Project, Areas_Expand}`，
以及辅助图 `Crosswalks` / `Intersection_solving` /
`Custom_Projector_with_rotation_fix` / `GridPartition` / `LoopSpawnActorPerData`。

节点注释（**揭示了下游依赖关系**）：
- *"Collects Local, Collector, and Artery road splines into a single stream"*
- *"Embed Artery Width On Footprint"* / *"Embed Collector Width…"* / *"Embed Local Width…"*
- *"Downstream graphs (Lots, Buildings) read these to know road clearance distances."*
- *"Clip Roads At Landmark Boundary"*
- *"Blur Terrain (Road Edges)"* / *"(Intersection Edges)"* / *"(Final Pass)"*

消耗形状语法：`SGD_Road_City`、`SGD_Road_City_HighRes_NoLines`。
生成 22 种 `SM_Road_SprayPaint_*_inst` 贴花。

> **"道路宽度加倍"** = 改本图的路宽参数，可一次调整 local / collector / artery 全部等级。

### 3.1.3 Highways
`Filter_Tags` → `Assign_ShapeGrammarDefinition`(`SGD_ElevatedHighway_oneWay`) →
`Transform_Resample/Project/Areas_Expand` → `Spawn_Assets`。

### 3.1.4 Lots
`Subdivide_Areas_withGrid` / `_WithRecursiveSplit`、
`Compose_Areas_Intersection` / `_Exclusion`、`Transform_Areas_Contract`、
`Filter_Areas_BySize`、`Write_Tag` + `FilterPolygonByEdgeLength`。

**参数**（按街区档位分）：`BuildableLotMin/MaxSize{Large,Medium,Small}District`、
`BuildableFootprintMinSize*`。

注释：`Carve Grammar Roads From Large Lots` / `Carve Medium/Small Courtyard From Lot` /
`Contract Large Footprints (Inner Building Pad)` / `Exclude Highway From Large Lots` /
*"Contracts the medium lot polygon inward by 3000 units."*

### 3.2.1 Ground
`Assign_Rule` + `Assign_ShapeGrammarDefinition`(`SGD_Sidewalk_A`、`SGD_Sidewalk_Corners`)、
`Fill_Areas_Uniformly`、`Compose_Spline_Cut`、`Transform_Splines_Reverse`、`Extract_Segments`。

生成 `/Game/Road/Kit_Sidewalk_A/Mesh/SM_Plaza_Square_A..G`、栅栏、栏杆。

**含形状语法帮助文本**（很有价值）：
*"A means to place the module with symbol A."* /
*"A, B means to place modules A and B once, in sequence."*

参数注释：`ArteryWidth / 2 (Sidewalk Expansion Amount)`。

### 3.2.2 LeftOverLots
`Fill_Areas_WithFittingAssets_CoreProcess` / `_with_Corrective`。
填充 42 个 Plaza/Storage `*_PCG` 数据资产 + 树
（`SM_Black_Alder_01_A..D`、`SM_Common_Hazel_01_A/B`、`SM_European_Beech_01_A..C`、
`SM_BlackAlder_Field_01..05_PP`）。

> **"增加停车位"** = 本图已有一条直通停车图的**分支**，加大喂入即可。

### 3.2.3 Parkings
`Subdivide_Areas_withGrid`、`Fill_Areas_Uniformly`、`Assign_Rule`、`Place_OnSpline`、
`Transform_Truncate/Outline/Resample`。

### 3.3.1 Buildings —— 形状语法中枢
`Assign_CitySampleBuildings` → `Assign_CitySampleBuildings_CoreProcess` →
`LoadCitySampleData`；另加 `AssignBuildingShape`、`SetComplexBuildings`、
`FilterSquareShapes`、`Filter_Areas_within_Areas`、`Create_Mesh_Extrude`、`Write_Noise`、
`Write_DistanceFrom`、`Write_Attribute_fromTexture`、
`LoopCreate{Extruded,Planar}MeshActorPerData`。

**图内有硬编码的 19 个样式码白名单**（非全部 27 个）：
`CHA,CHB,CHC,CHE,CHF,CHG,CHH,CHI,CHJ,NYG,NYGA,NYH,QBA,QBAA,SFA,SFC,SFD,SFE,SFJ`

标签体系：`Building_S_` / `Building_M_` / `Building_L_`（+ `_Col` 碰撞变体），
`FilterTags_/AddTags_/DeleteTags_{Small,Medium,Large}Districts`。

tooltip：*"Maximum height in centimeters of the spawned building"*。

> **"任何建筑不超过 200m"** = 改本图的高度参数，或用 **Clamp 节点**截断。

### 3.3.2 Rooftops
`Fill_Areas_WithFittingAssets_*`、`Compose_Points_Difference`、`Filter_Areas_BySize`。
消费 56 个 `RoofTops/*_PCG` 数据资产。

### 4.1 / 4.2 视觉
最大的两张图，英雄资产装扮。
4.1 拉 WFC 屋顶组 + `SGD_Sidewalk_Simple` + `Transform_Align`。
4.2 拉 `SGD_Road_City`、`SGD_Sidewalk_A`、`SGD_Sidewalk_CITY_EDGE`、
`SGD_WalkpathSplineMesh`、`Fill_Areas_Randomly`、`Filter_AttributeValue`、
`Write_Attribute`、`Write_Noise`。

### 5.1 CityEdge
极简：`Assign_Assets` + `Spawn_Assets` over 5 个 Piers 数据资产。

### 5.2 OuterForest
`Trace_Bound_Footprint`、`Extract_Bounds`、`Compose_Areas_Exclusion`、
`Fill_Areas_Randomly`、`Write_DistanceFrom`、`Write_Attribute_fromTexture`。
用 `/Game/Textures/Noise/T_CloudNoise_4k` 驱动密度，生成 Megaplants 树集。

---

## 6. 原语库：词汇表

18 张图几乎**完全由 `/PCGPrimitives/Primitives/<动词>/<动词>_<名词>` 子图拼成**，
每个带配套 `Subgraphs/<name>_CoreProcess` 与共享的
`_Template_/Primitives_{InputsProcessing, InputsFallback, PrepareOutputs}` 包装。

**贯穿 18 张图的动词**：

> **Assign, Compose, Copy, Create, Debug, Extract, Fill, Filter, Get,
> Place, Shared, Spawn, Subdivide, Trace, Transform, Write**

**CitySamplePCG 几乎不贡献新节点类型——它是「引擎原语库 + 13 个辅助图 +
Buildings/BDF 扩展」的组合。**

### 常用原语速查

| 想要… | 用… |
|---|---|
| 生成规则网格点 | `Create/Create_Point`、引擎 `Create Points Grid` |
| 生成样条 | `Create/Create_Spline_Shape`、`Create_Spline_line` |
| 挤出网格 | `Create/Create_Mesh_Extrude` |
| 求两条样条交点 | 引擎 `Spline Intersection`（**注意 `bUseBestFitBox=false`**） |
| 切分区域 | `Subdivide/Subdivide_Areas_{withGrid, WithRecursiveSplit, withSpline}` |
| 区域布尔 | `Compose/Compose_Areas_{Exclusion, Intersection, Union}` |
| 沿样条裁剪 | `Compose/Compose_Spline_Cut` |
| 点集求差（避让） | `Compose/Compose_Points_Difference` |
| 按面积筛 | `Filter/Filter_Areas_{BySize, Largest, Smallest, within_Areas}` |
| 按属性筛 | `Filter/Filter_AttributeValue` |
| 防重叠 | `Filter/Filter_Points_Overlapping` + 引擎 `Self Pruning` |
| 随机挑选 | `Filter/Filter_RandomChoice` |
| 填充区域 | `Fill/Fill_Areas_{Randomly, Uniformly, WithFittingAssets}` |
| 沿样条摆放 | `Place/Place_OnSpline`、`Place_Points_AtIntersections`、`Place_RadialScatter` |
| 网格摆放 | `Place/Place_Assets_OnAGrid` |
| 平移/旋转/缩放 | `Transform/Transform_{Offset, Jitter, Align, Level, Project, Resample}` |
| 区域扩缩 | `Transform/Transform_Areas_{Contract, Expand}` |
| 投影到地形 | `Transform/Transform_Project` |
| 写属性 | `Write/Write_{Attribute, Tag, Noise, DistanceFrom, Class}`、`Write_Attribute_fromTexture` |
| 取场景 Actor 数据 | `Get/Get_ActorData`、`Get_ActorDataByRef` |
| 指派资产 | `Assign/Assign_Assets`、`Assign_Rule`、`Assign_ShapeGrammarDefinition` |
| 生成资产 | `Spawn/Spawn_Assets`、`Spawn_SplineActor` |
| 追踪足迹 | `Trace/Trace_Bound_Footprint`、`Trace_Connect`、`Trace_Bridges` |

完整清单（约 80 个原语）见
`E:\UnrealEngine\Engine\Plugins\Experimental\PCGPrimitives\Content\Primitives\`。

---

## 7. 教学图集：先吃透再上 18 图

**两套都存在，注意区分命名：**

### 7.1 引擎侧（PCGPrimitives）
`/PCGPrimitives/Examples/City/`
- `City_Circular_1km_2_arteries_NoAssetLibrary` — 基线：1km 环形城 2 条主干道
- `City_European_Medieval_1km_2_arteries` — 欧式中世纪变体
- **`City_Generator_Steps_1_Base` → `_2_Districts` → `_3_Lots` → `_4_Ground` →
  `_5_Buildings` → `_6_Left_over_lots` → `_7_city_Contour`** — 七段串联版
- `City_Generator_steps.umap`
- `Basic_Building_Row_of_400x50m`
- `Edits/City_Circular_1km_2_arteries_NoAssetLibrary_Fast`

### 7.2 项目侧（CitySamplePCG，更贴近本流水线）
`/CitySamplePCG/Examples/City/`
- `City_Circular_1km_2_arteries`（1.01 MB）与 `..._slopes`（1.32 MB）
- `Cities_Circular_1km_2_arteries_CombinedAndEnclosed`
- **`CitySample_Generator_Steps_1_Base` → `_2_Districts` → `_3_Lots` → `_4_Ground` →
  `_5_Buildings` → `_6_Left_over_lots` → `_7_CitySample_Contour`**
- `Various_Building_Row_of_300x30m`
- `CitySample_Generator_steps.umap`（57.5 MB）
- **`Edits/`（6 个变体，每个都是"对着某句 prompt 改出来"的）**：
  `_Half_Forest`、`_with_Backalleys`、`_with_Customized_landmarks`、`_with_Highway`、
  `_with_embanked_highway`、`_with_embanked_river`
  （另有 `Edits/edits/City_Circular_1km_2_arteries_with_drawn_embanked_river_hand_drawn`）

其余示例：`Examples/Building/`（7 种 Staggered 形体 + 2 个带树与广场的街区）、
`Examples/ParkingLot/Parking_Lot`、`Examples/Plaza/`（4 个）。

> **`Edits/` 文件夹是 Epic 留给 LLM 的"标定集"**：
> 每个变体都对应一句明确的 prompt，是学习"什么样的 prompt 会改出什么样的图"的最佳素材。

---

## 8. 形状语法

### 8.1 概念

**Shape Grammar Definition（SGD）** 把"横截面"拆成若干 **slot**，
每个 slot 引用一条 **Rule**，Rule 按**语法串**把模块化网格沿样条重复排布。

### 8.2 资产格式（自二进制解码）

`SGD_*` = `BP_ShapeGrammarDefinition_C`，属性：
`Symbol`、`Slots`(`STC_Slot`)、`Main Grammar`、`Minimum Size`、`Use Grammar`、
`Spawn on`(`EGrammarSpawnMode`)、`orientation`(`EGrammarOrientation`)、
`Mirror`、`offset`、`scalable`、`size`、`ShapeGrammarRules`、`Description`。

`RULE_*` = `BP_ShapeGrammarRule_C`，属性：
`Symbol`、`grammar`、`Rule`、`ModulesInfos`(`STC_Module`)、`Mesh`、`Size`、
`Scalable`、`RandPosRange`、`Overrideprofilegrammar`。

支撑结构体在 `/PCGPrimitives/Grammar/Structure/`：
`STC_Slot`、`STC_Module`、`STC_Rule`、`EGrammarOrientation`、`EGrammarSpawnMode`。

### 8.3 实例

`SGD_Road_City` 的 Description 原文：

> *"A simple city road profile with a 2 ways split with a yellow stripes in the middle,
> and asphalt ground. minimum size is 841 cm"*

它引用 4 条规则：`RULE_Road_Car_Lane`、`RULE_Road_Separator_Lane`、
`RULE_Road_Yellow_Line_L/R`。`RULE_Road_Car_Lane` 指向
`/CitySamplePCG/Meshes/Roads/SM_Lane_Car_400`。

### 8.4 制作流程

1. 建 **Rule** 资产，类 `BP_ShapeGrammarRule`（如 `RULE_MyLane`）
2. 加 module：引用静态网格 + 一个**符号**（如 `"A"`），设尺寸或点 **Guess Size**
3. 设**语法串**，如 `"A*"`（`*` = 重复）——参考 `RULE_Road_Car_Lane`
4. 建 **SGD** 资产，类 `BP_ShapeGrammarDefinition`（如 `SGD_MyRoad`）
5. 加 slot：符号、尺寸(cm)、`scalable=true`、引用上面的 Rule
6. 顶层字段：Main Grammar、**Use Grammar = true**、Orientation = **horizontal**、
   Spawn on spline = 开启
7. 图内加 **`Assign_ShapeGrammarDefinition`** 节点，喂样条，指定 SGD 与横截面尺寸

> 配套还有引擎技能资产 `Skill_PCGShapeGrammarDefinition`，用于从零引导。

---

## 9. 数据资产

`/CitySamplePCG/PCG/DataAssets/` 共 **492 个文件**。

| 分类 | 数量 | 内容 |
|---|---|---|
| **Buildings** | 270 | 27 个样式码目录，每目录 `RULE_<CODE>_Lnn` + `SGD_<CODE>_A`。**240 RULE + 27 SGD** |
| **Roads** | 65 | 8 个 profile 目录，每目录 `Rules/RULE_*` + `SGD_*`。**46 RULE + 16 SGD** |
| **RoofTops** | 105 | `Rooftop_{Skyscraper,Medium,Small}_*`、`WFC3x3/3x6/6x6_*`、`AC_Vent_*`、`Roof_Pipe_*`、`Roof_Platform_*`、`Roof_Window_*`、`Roof_House_*`、`Roof_Metal_*`、`Antenna_A` |
| **Plazas** | 42 | `Plaza_{Large,Medium,Small}_*`、`Plaza_Triangle_B`、`Plaza_PlayerStart`、`Park_Curb_*`、`Park_Debris_*`、`Storage_*` |
| **Piers** | 9 | `Dock_A/B_PCG`、`Warehouse_A/B/C_PCG` + 4 个 authoring `.umap` |
| 根 | 3 | `VistaCliffs_PCG`、`PCGD_ComplexBuildingShapes`(1.23 MB `UPCGDataAsset`)、`PCG_Bldg_SGD_test` |

### Roads 的 8 个 profile
`BackAlley`、`City_river`、`ElevatedHighway`（含 `_oneWay`）、
`Road_City`（4 个 SGD：`SGD_Road_City`、`_HighRes`、`_HighRes_NoLines`、`SGD_Road_Simple`）、
`Sidewalk_A`（3）、`Sidewalk_Basic`、`Sidewalk_CITY_EDGE`（2）、`Walkpath`（2）。

### 配套预览关卡
`Bldg_SGD_level.umap`（6.2 MB）、`Road_SGD_level.umap`（6.68 MB）。

---

## 10. 建筑样式码

27 个目录，按地域风格分：

| 地域 | 样式码 | 数量 |
|---|---|---|
| **芝加哥（C）** | `CHA` `CHB` `CHC` `CHD` `CHE` `CHF` `CHG` `CHH` `CHI` `CHJ` | 10 |
| **纽约（NY）** | `NYAA` `NYAB` `NYAC` `NYAD` `NYAE` `NYAF` `NYG` `NYGA` `NYH` | 9 |
| **旧金山（SF）** | `SFA` `SFB` `SFC` `SFD` `SFE` `SFJ` | 6 |
| **其他** | `QBA` `QBAA` | 2 |

**但 `PCG_3_3_1_Buildings` 图内只硬编码了其中 19 个**：
`CHA,CHB,CHC,CHE,CHF,CHG,CHH,CHI,CHJ,NYG,NYGA,NYH,QBA,QBAA,SFA,SFC,SFD,SFE,SFJ`

**未进入白名单的 8 个**：`CHD`、`NYAA` `NYAB` `NYAC` `NYAD` `NYAE` `NYAF`、`SFB`。
→ 想让它们参与生成，需要**改图的样式码白名单**。

### 每目录的层数不一
`CHA` 有 `L00–L20`（21 条规则），`NYAA` 有 `L00–L05`，`SFD` 有 `L00–L04`。

> **LLM 交互关键**：每套样式的数据资产里嵌有 **tooltip 元数据**，描述
> "整体观感 / 建筑类型（住宅·商业·办公）/ 大致建造年代"。
> 一句"让城市看起来更老一些，只用老式建筑"可以**不改图**、靠元数据筛选实现。

---

## 11. 共享辅助图（13 个）

`/CitySamplePCG/PCG/` 根下，被 18 张阶段图共同依赖：

| 辅助图 | 大小 | 作用 |
|---|---|---|
| `Intersection_solving` | 1.32 MB | **路口求解**（Roads 的核心依赖） |
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

## 12. Buildings/BDF 扩展（23 个）

`/CitySamplePCG/PCG/Primitives/`：「BDF」= Building Definition pipeline。

- `Fill_Areas_WithFittingAssets_CoreProcess`（902 KB，图 + 内嵌 `PCGDataAsset`）
- `Fill_Areas_WithFittingAssets_with_Corrective`
- `Buildings/Assign_CitySampleBuildings`
- `Buildings/Subgraphs/`（20 个）：
  `BDF_BuildingFromSpline`（**1.78 MB**）、`BDF_Input_Processor`、`BDF_ModulePreprocessor`、
  `PartitionBDF_PerSpline`、`Assign_CitySampleBuildings_CoreProcess`、
  `Filter_Footprints_for_bldgs`（1.32 MB）、`ASM_Clutter_Behavior`、**`LoadCitySampleData`**、
  `Loop_Building_Actor`、`Loop_GroupedPropsCopy`、`Loop_Subdivide`、
  `RoundSegmentAngles`、`SpawntoBuildingActor`、`Skill_BDF_LevelMinWidth`
- 数据：`CitySampleBuildingBDF_Asset_PCG`（2.96 MB `UPCGDataAsset`）、
  `CitySampleBuildingBDF_NamesOnly_PCG`、`DT_Bldg_LevelMinWidth` / `DT_Bldg_MinWidth`（DataTable）、
  `ST_Bldg_MinWidth` / `ST_Level_MinWidth`（UserDefinedStruct）

`BDF_BuildingFromSpline` 携带形状语法 tooltip 原文：
*"An encoded string that represents how to apply a set of rules to a series of defined modules."*

> `Assign_CitySample_Buildings` 要求把 **`LoadCitySampleData` 子图作为第二路输入**，
> 以避免重复加载数据库。

---

## 13. World Partition 注意事项

- 逐图开启 **Partition Grid Size**（默认 128m），
  PCG 才会生成局部化分区 Actor 而非单个巨型 Actor
- **建筑图需手动勾选碰撞生成**
- 在 World Settings 开启 streaming 后，生成前需在 World Partition 编辑器里
  **手工加载**相关 Actor（**所有被引用的 Actor 必须已加载**）
- 完全分区后的城市约 **2600 个独立 Actor**

---

## 14. 官方示例提示词 → 该动哪里

| 用户说 | 动哪里 |
|---|---|
| 让城市更老 / 只用老式建筑 | 建筑图的样式码白名单 + tooltip 元数据筛选（**不改结构**） |
| 任何建筑不超过 200m | 建筑图的高度参数或用 Clamp 节点（**不改结构**） |
| 道路宽度加倍 | `PCG_3_1_2_Roads` 的路宽参数（一次改 local/collector/artery 全部） |
| 城市位于热带纬度 | 语义搜索找树资产，替换植被（`PCG_3_2_2` / `PCG_5_2`） |
| 增加停车位 | `PCG_3_2_2_LeftOverLots` 已有的停车分支，加大喂入 |
| 移除所有路边停车 | **两处**：`PCG_3_2_3_Parkings` 关生成 + 街道侧改 SGD 或换不含车的人行道资产 |
| **新增一档街区尺度** | `PCG_3_1_1_Districts`，仿照小/中/大现有三支新建第四档并接回主干 ← **结构性改图** |
| 换个城市形状 | **改 7 个手绘样条**，图完全不动 ← 最推荐 |

> 前 6 条是参数级/资产级改动；**最后两条是结构性改图，必须经用户确认**。
> 官方原话：*"You need a deeper understanding of how the PCG graph works in order
> to check the quality of the LLM's work."*
