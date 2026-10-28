# PyWorld：按《Building Worlds with Houdini》的流程，用 PCG 图 + Python 节点生成一个山谷世界 — 设计

> 日期：2026-10-22。状态：用户已在对话中确认流程拆解与三项默认（规模 2×2 km、灰盒美术、运行时形态 = Python 节点）。
> 来源：Benoit Martinez（Ubisoft Paris）在 Houdini HIVE Paris 的演讲（https://www.youtube.com/watch?v=bQ_U1_MVKJQ ，58 min，
> 《幽灵行动：荒野 / 断点》的开放世界管线）。只有法语自动字幕，拆解按字幕 + 视频简介重建，时间点见 §1。
> 分支：`pyworld-pipeline`。

---

## 0. 目标、决定与成功标准

**用户目标**：拆解视频里的程序化场景生成流程，在 UE 里用 PCG Graph 实现。

**用户拍板的决定**

| # | 决定 |
|---|---|
| D1 | 规模：**2×2 km 山谷**，4–6 个聚落、1 条河，加路网 |
| D2 | 美术：植被/岩石用项目里已有的 Megaplants、BiomeSample、Wild_Grass、Mossy_Rock；建筑先用 PCGPrimitives 自带的灰盒建筑形状语法 |
| D3 | **运行时形态：PCG 图里放 Python Data Processor 节点**（沿用 PyPCG 的做法，"追求好写"）；地形读写、网格生成、形状语法仍是原生节点 |

**由此推出的实现原则**

| # | 原则 |
|---|---|
| P1 | 一个阶段 = 一张 PCG 图 = 关卡里的一个 PCG volume。驱动脚本按顺序逐个生成，对应视频里"按依赖链自动触发的工具" |
| P2 | 每张图 = 参数 getter + 场景读取（地形 / 控制 actor / 上游阶段产出）→ **一个 Python 节点**（逻辑全在 `.py`）→ 原生生成节点（`Write_MeshTerrain`、`Spawn_Assets`、`Assign_ShapeGrammarDefinition`）|
| P3 | 阶段逻辑是纯 Python（不 import unreal），能离线 pytest；共享算法放 `pypcg/world/`，不在两个阶段里各抄一份 |
| P4 | 图资产由 `.py` 描述生成（`pypcg.dsl`），构建后结构核对 `diffs: 0` 才保存；不手改资产 |
| P5 | 地形用项目已经在用的 MeshTerrain（Mesh Partition）：PCG 能读也能写，路基、河床、地块平台都在图里完成 |
| P6 | 每一步用数值验证（点数、实例数、坡度、连通性、侵入数）再截图，"没报错"不算完成 |

**成功标准**

1. 9 张图全部构建 `diffs: 0`；新离线测试全过，既有基线（762 passed, 18 skipped）不变。
2. 在新关卡 `/Game/PyPCG/L_PyWorld` 按 W1→W9 生成，每步的验收规则（§5）通过。
3. 校验（W10）：树/石/道具的贴地误差 > 30 cm 的实例 = 0；道路走廊、河道、建筑占地内的植被 = 0；所有地点在路网上连通；每个路×河交叉点都有桥。
4. 同 seed 跑两遍，每种网格的实例数逐项相同。
5. 俯视 / 斜视 / 街景三张总览截图 + 每步一张截图；只保存 `L_PyWorld`，单文件 < 100 MB。
6. `docs/pyworld-guide.md`：视频拆解、各阶段做法、怎么改参数和重跑、结果与已知限制。

---

## 1. 视频拆解（输入）

| 步骤 | 视频里怎么做 | 要点 | 时间 |
|---|---|---|---|
| 0 地形底图 | World Machine + 真实 DEM 做高度图；Houdini 算坡度、高度、曲率、流向/侵蚀遮罩 | 地形是一切的输入 | 06:28 |
| 1 地形数据层 | 任一点可查高度、光照/朝阳、材质、道路流向；地形一改，农场 5 分钟内重算 | 地形派生数据集中提供给所有工具 | 12:51–15:45 |
| 2 地点 | 美术放兴趣点 | 人给意图，程序做几何 | 16:27 |
| 3 道路 | 地形上 A\* 寻路；普通 8 邻域网格出锯齿，**扩大邻域、看更多方向**就贴地形 | 新路接到已有路网；路定后按路平整地形 | 16:27–21:04 |
| 4 河流/铁路 | 同一寻路模型，曲率/坡度容差不同 | 交叉自然出现：河从路下过 | 19:56–20:28 |
| 5 桥 | 路跨河处由专门工具生成合适的桥 | 程序化：改主意容易更新 | 20:28、28:54 |
| 6 聚落 | 平整地形；内部路网连最近道路；从中心向外分区（中心教堂广场，外围农场）；建筑规则表定类型/分区/密度/间距 | 小村到大镇同一套规则 | 33:07–38:57 |
| 7 植被与岩石 | 试过生态模拟后放弃，改为区域遮罩 + 散布规则，按地表类型分配；沿路清空；密度热图控性能 | 可控比"真实"重要 | 22:49–28:17 |
| 8 沿路道具 | 最早的工具是电线杆间的电线；道路轨迹复用于电线、旗子 | 一条轨迹多种用途 | 03:36、22:14 |
| 9 地表材质 | 道路、河流、平整、手绘的遮罩合成地表材质 | 每一步都往地表写遮罩 | 42:37 |
| 10 校验与重跑 | 末期玩家卡石头，做检查工具；每晚整条链重跑，重新贴地防漂浮 | 链式依赖 | 25:09、40:52 |

**不移植**：Anvil/.NET 双向桥、Perforce、渲染农场分发、分析热图、AI 刷点、体积雾、特效、生态模拟（他们也放弃了）；
**隧道**（MeshTerrain 是高度场，挖不了洞）。视频里的"每晚重跑"对应驱动脚本的整链重生成，不做定时任务。

---

## 2. 架构

### 2.1 关卡与地形

- 新关卡 `/Game/PyPCG/L_PyWorld`，**从 `/Game/PyPCG/L_PyCity` 模板复制**：它带着项目里已验证过的 Mesh Partition（3 km 平底，z = -600 cm，
  顶点间距 585.9375 cm，2 km 框内 341×341 = 116 281 个顶点，见 `docs/pypcg/stages/s01.md` §0）、灯光、天空、雾和机位，且保存时不含生成结果（11 MB）。
- `layout` 阶段删掉模板里的 PCG volume 与城市控制 actor，**把 MeshPartition 的定义换成插件自带的 `MPD_Basic`**：它有 6 个材质通道
  `Grass / Rock / ForestFloor / Dirt / Mud / Gravel`（材质 `M_MeshTerrain_Basic` 按 `Weight <通道>` 混合，2026-10-22 实测资产内容）。
  换不成功时退回模板自带的 `MPD_CitySamplePCG_Demo`（通道 `Mat_GrassDry / Mat_Dirt / Mat_Mud`），W9 只写这三个通道。
- 世界：以原点为中心 2×2 km 的山谷。所有地形读写都用 3 km 查询框（261 312 个顶点，与城市阶段 1 相同的量级），
  外圈 1–1.5 km 是平滑落回 -600 的山体；道路、聚落、植被等逻辑只在 2 km 框内。

### 2.2 阶段、volume 与数据流

关卡里 9 个 PCG volume（brush 3000 × 3000 × 1000 m），各挂一张 `/Game/PyPCG/World/PCGW_NN_*`，actor tag `PyWorld_WNN`。

```
控制 actor（layout 写入）：PyWorld_Valley（山谷轴线样条）、PyWorld_Location ×5（TargetPoint，X 缩放 = 半径/100 m）、
                         PyWorld_RiverSource / PyWorld_RiverOutlet、PyWorld_RoadExit ×2
W1 地形      Base 地形 → Python(谷形+噪声) → 原生侵蚀 → Write(p1)
W2 地点      控制 actor + Final 地形 → Python → Locations / RoadExits / RiverEnds
W3 河流      Intermediate(p2) 地形 + W2 → Python(A*+下切) → Write(p3)；RiverPoints；水面 → Spawn_Assets
W4 道路      Intermediate(p4) 地形 + W2 + W3 → Python(16 邻域 A*+分级+纵坡) → Write(p5)；RoadPoints；路面模块 → Spawn_Assets
W5 桥        W3 + W4 → Python(交点) → BridgeParts → Spawn_Assets
W6 聚落      Intermediate(p6) 地形 + W2 + W3 + W4 → Python(平台/街道/地块/规则表) → Write(p7)；
             建筑占地 → 形状语法（按层高分 4 组）→ Spawn_Assets；屋顶/地基/街面 → Spawn_Assets
W7 植被岩石  Final 地形(点+面) + W3..W6 → Python(数据层+规则+排除) → Trees/Shrubs/Rocks/Grass → Spawn_Assets
W8 沿路道具  Final 地形 + W3..W6 → Python → 电线杆/电线/路灯/护栏/长椅 → Spawn_Assets
W9 地表材质  Intermediate(p8) 地形 + W3/W4/W6/W7 → Python(通道权重) → Write(p9, Channels)
W10 校验     驱动脚本 check 阶段（不是图）：贴地、侵入、连通、桥、确定性
```

- **上游产出**用 `Get_ActorData`（按 actor tag，`GetDataFromPCGComponentOrParseComponents`）读上游 volume 的生成输出；数据 tag 随数据走，
  Python 节点按 tag 拆（`River`、`MainRoad`、`Footprint` …）。
- **地形读写次序**按官方阶段 7 的模式：读 `Intermediate` 于 sub-priority p 只看到 p 以下的写入，本阶段写在 p+1，避免读到自己。
  只读阶段读 `Final`。
- **地形写入写全集**：每个改地形的阶段读 `Intermediate`（看到此前全部写入），改 z 后把全部顶点写回（属性原样，含
  `SourcePositions`）。写子集的行为没有实测过，不赌它；代价是改了上游必须从该步起整链重跑（`reset {"from": N}` 清 N..9），驱动就是这么做的。
- Python 节点的每个输入 pin 都接线（trap 80）。

### 2.3 Python 与原生的分工

| Python（纯函数，可离线测） | 原生节点 |
|---|---|
| 谷形高度、噪声、外圈收边；地形数据层（坡度、法线、流量累积、湿度、朝阳） | `Get_MeshTerrain`、`Extract_MeshTerrainPoints`、`Write_MeshTerrain`（含 Channels） |
| 地点吸附、河流/道路 A\*、分级、平滑、纵坡限制、下切/路基/平台/地块垫平 | `Transform_MeshTerrain_Erosion`（带遮罩，只作用于山体） |
| 路面/街面模块的逐段变换（5 m 一段，贴纵断面带俯仰）；桥的位置/跨度/构件；聚落分区、街道、地块、建筑规则表、屋顶与地基构件 | `Assign_ShapeGrammarDefinition`（建筑：`SGD_Bldg_B_Advance_Template`，按引擎示例 `BuildingBlock_StaggeredSquare` 的接法：`SpawnAssets=false` → `Points` → `Spawn_Assets`） |
| 植被/岩石规则、散布、排除、贴地；沿路道具与悬链线；地表通道权重 | `Spawn_Assets`（`UseMeshAttribute`，按点上的 `Mesh` 属性生成，阶段 15 的 `SpawnPlaza` 就是这样用的；水面用 `MaterialOverride`） |

点的贴地：W7/W8 用 Final 地形面（`Terrain.height`，射线采样，trap 52）逐点取高；地形写入用 `Extract_MeshTerrainPoints` 的点（保留 `SourcePositions`）。

### 2.4 代码位置

| 部分 | 位置 |
|---|---|
| 阶段模块 | `Content/Python/pypcg/stages/w01_terrain.py` … `w09_surface.py`（`STAGE` 101–109，避开城市阶段号；`host.run` 原样可用） |
| 共享库 | `Content/Python/pypcg/world/`：`__init__`（阶段表、tag、资产路径）、`noise`、`grid`、`astar`、`polyline`、`terraform`、`rules`、`settle`、`scatter`、`points`、`layout`、`checks` |
| 图描述 | `Content/Python/pypcg/world/graphs.py`（每阶段一个 `build_wNN()`） |
| 驱动 | `Content/Python/pyworld.py`：`build / make / layout / assign / reset / gen / read / shot / check / save`，一次调用一个阶段，长调用 `{"defer": true}` |
| 测试 | `Tools/pypcg/tests/test_world_*.py` |
| 小改动 | `pypcg/dsl.py`：`SlimGraph(name=...)`；`pypcg_library.py` + `library.json`：加入 `Transform_MeshTerrain_Erosion`；`pypcg/level.py`：`WORLD` |

---

## 3. 各阶段

参数都进图的用户参数（带 tooltip），volume 可覆写；随机只用 `ctx.rng`（`Seed` 参数）。

### W1 地形（`w01_terrain`）
- 输入：`MeshTerrain`（Base，3 km 框的顶点）、`Valley`（山谷轴线样条，控制点 z = 谷底高程）。
- 高度 = 谷形 + 噪声：到轴线距离 d 上，谷底半宽内是缓坡谷底（+ 1–2 m 起伏），向外以 smoothstep 升到山脊（默认 180 m），山体叠加
  域扭曲 fBm 与脊状噪声；|x| 或 |y| 超过 1.2 km 后平滑落回 -600。另写 `Mountain` 属性（0 谷底 … 1 山体）作侵蚀遮罩。
- 原生 `Transform_MeshTerrain_Erosion`（`MaskAttribute = Mountain`）→ `Write_MeshTerrain`（sub-priority 1，3 km 框）。

### W2 地点（`w02_locations`）
- 输入：三类 TargetPoint（GetSinglePoint）与 Final 地形点。每个地点在半径 60 m 内找坡度最小的点吸附；按半径定级：≥ 200 m 镇，
  ≥ 120 m 村，否则小村。输出 `Locations`（Kind、Radius、Id）、`RoadExits`、`RiverEnds`。

### W3 河流（`w03_river`）
- 在地形网格隔一取一（11.7 m）的格点上做 A\*：上坡代价重、聚落中心半径一半内加罚。路径 Chaikin 平滑、每 10 m 重采样。
- 水位沿程取地形最小值的累计最小（单调不升）再平滑；河宽按沿程 6 → 20 m；河床 = 水位 - 1.5 m（抛物线断面），岸坡 8 m 过渡。
- 输出：`RiverPoints`（Width、WaterZ、BedZ、S）、`WaterPlanes`（引擎 Plane 网格分段铺水面，`MI_ocean`）、`Terrain`（下切顶点子集）→ Write p3。

### W4 道路（`w04_roads`）
- 同一网格上 **16 邻域** A\*（8 邻 + 马步，视频的"扩大邻域"）：边代价 = 长度 × (1 + a·(纵坡/限坡)²)，超过硬限坡不可走；
  河道格加罚（鼓励垂直短跨）；已有道路格打折（复用）。
- 分级：先连两个出口与镇、镇与最大的村（干道），其余地点按重要度依次用多目标 Dijkstra 接到已有路网（支路）。
- 纵断面：沿路采样地形，60 m 滑动平均，前后两遍夹纵坡（干道 10 %、支路 14 %）；过河处取两岸高与水面 + 2.5 m 的较大值。
- 输出：`RoadPoints`（RoadId、Class、Width、Order、Bridge）；`RoadModules`（干道两条 `SM_Lane_Car_400_500` + 中线
  `SM_Lane_Divider_15_500`，支路一条横向缩放到路宽的 `SM_Lane_Path_300_160`，每 5 m 一段，按纵断面带俯仰，z + 8 cm，桥跨内不放）→ `Spawn_Assets`；
  `Terrain`（全部顶点；路基走廊：半宽 + 6 m 内压到纵断面，外 10 m 过渡；河道内不填）→ Write p5。

### W5 桥（`w05_bridges`）
- 路线与河中线求交；跨度 = 河宽 / sin(夹角) + 两端各 6 m；桥面高 = 道路纵断面在交点的高。
- 构件（灰盒）：桥面板（Cube）、两侧护栏（`Modular_Rail_Guard_4m` 连续排）、跨度 > 14 m 时加桥墩（Cylinder 到河床）、两端桥台（Cube）。

### W6 聚落（`w06_settlements`）
- **平台**：半径内拟合平面（坡度夹到 ≤ 4°）、外 25 % 过渡；道路走廊内不改（保住 W4 的路面）。
- **街道**：从中心沿现有道路之外的方向伸出辐射街（镇 5、村 3、小村 1–2 条，局部 A\*），镇再加 0.55 R 环街；街宽 4 m。
- **分区**：核心 < 0.35 R、住宅 0.35–0.75 R、外围 > 0.75 R；镇和村中心留 18 m 广场。
- **地块**：沿街与穿过聚落的道路两侧按规则表的面宽/进深取矩形，拒绝重叠、压路、入水、过陡的。
- **建筑规则表**（`world/rules.py`，相当于视频里的大表）：类型 → 允许的分区与聚落等级、占地范围、层高组、最小间距、每聚落上限、
  "靠近中心/广场"约束。例：教堂（镇/村各 1，核心，面向广场，带 6×6 m 钟楼）、镇公所（镇 1）、商铺/大宅（核心）、住宅（住宅区）、
  农舍 + 谷仓 + 棚屋（外围）。外围再划农田（矩形，坡度 ≤ 8°）。
- **生成**：占地多边形按层高分 4 组（低 / 中 / 高 / 塔，具体高度在 W6 实测语法的层高后定）各接一个
  `Assign_ShapeGrammarDefinition(SGD_Bldg_B_Advance_Template, SpawnAssets=false)` → `Spawn_Assets`；
  坡屋顶（绕屋脊转 45° 的 Cube，下半截埋进顶层）、教堂尖顶（Cone）、地基（Cube，向下 2 m 埋进地形）、街面模块 → `Spawn_Assets`；每个地块垫平（占地 + 2 m）。
- 输出：`Buildings`（每栋一点：中心、尺寸、朝向、类型）、`StreetPoints`、`Footprints_*`、`Plazas`、`Fields`、`BuildingParts`、
  `Terrain`（全部顶点）→ Write p7。

### W7 植被与岩石（`w07_vegetation`）
- 数据层：坡度、相对高程、湿度（流量累积 + 离河距离）、离路/离建筑距离。
- 规则表（`world/rules.py` 的 BIOMES）：河岸 → 桤木 + 榛；谷底草甸 → 草 + 零星树丛（噪声成簇）；山坡 → 山毛榉 / 挪威槭 / 欧洲山杨混交林；
  高处 → 松、云杉（BiomeSample）；陡坡（> 30°）→ 巨石（`PCG_Boulder_01`、`Mossy_Rock`）。全局密度倍数参数（视频的密度热图）。
- 排除：路与街走廊 + 3 m、河道、地块与占地、广场、农田、桥。
- 散布：抖动网格（格 = 最小间距）按密度概率接受；逐点用 Final 地形面取高。

### W8 沿路道具（`w08_props`）
- 干道与支路一侧每 40 m 立电线杆（灰盒 Cylinder + 横担 Cube），桥上跳过；两根电线按悬链线（垂度 0.8 m）每 2.5 m 一段细圆柱。
- 镇/村街道每 30 m 一盏路灯（`Kit_StreetLamp_A`）；路侧高差 > 1.5 m 处连续护栏；广场边长椅。

### W9 地表材质（`w09_surface`）
- 每个顶点：草地为底；`Rock` 随坡度 28°→40°；`ForestFloor` 随 W7 树木密度（20 m 格核密度）；`Dirt` 在路、街、广场走廊与农田；
  `Mud` 在河岸；`Gravel` 在河床与干道路肩。归一化后 `Write_MeshTerrain(Channels=[…])`，sub-priority 9。

### W10 校验（驱动 `check`）
- 实例贴地误差（树/石/道具/桥墩底）、走廊/河道/占地内的植被、建筑占地互相重叠或压路、路网连通、桥数 = 交叉数、纵坡上限、
  两遍确定性；写 `Saved/Reports/pyworld_check.json`。

---

## 4. 驱动与运行

```
pyworld.py {"phase": "build", "stages": "all", "defer": true}   # 描述 → 资产，0 diff 才保存
pyworld.py {"phase": "make"}                                     # L_PyCity → L_PyWorld（模板复制）并打开
pyworld.py {"phase": "layout"}                                   # 清模板、换 MPD、放 9 个 volume 与控制 actor
pyworld.py {"phase": "assign"}                                   # 挂图 + 覆写，regenerate_in_editor 关
pyworld.py {"phase": "reset", "from": 1}
pyworld.py {"phase": "gen", "stage": N}  →  等  →  {"phase": "read", "stage": N}  →  {"phase": "shot", "stage": N}
pyworld.py {"phase": "check"} / {"phase": "shot", "view": "top|wide|street"} / {"phase": "save"}
```

驱动只在 `L_PyWorld` 是当前关卡时写（`pypcg.level.require`）；`save` 只存 `L_PyWorld`。

---

## 5. 每步验收（`read` 自动判）

| 步 | 规则 |
|---|---|
| W1 | 写回点数 = 提取点数；谷底沿轴线在设定高程 ±5 m；山脊最高 ≥ 120 m；无 NaN |
| W2 | 5 个地点、2 个出口、2 个河端；地点中心坡度 ≤ 6° |
| W3 | 河长 ≥ 1.5 km；水位单调不升；河宽 6→20 m；下切顶点 > 0；水面实例 > 0 |
| W4 | 所有地点与出口连通；干道纵坡 ≤ 10 %、支路 ≤ 14 %；路面实例 > 0 |
| W5 | 桥数 = 路×河交叉数 ≥ 1；每座有桥面与护栏 |
| W6 | 镇 ≥ 60 栋、每村 ≥ 20、每小村 ≥ 5；镇/村各 1 座教堂；占地两两不重叠；占地不压路/街/河；建筑实例 > 0 |
| W7 | 树 ≥ 20 000；走廊/河/占地内 0 棵；河岸桤木占比高于全图 |
| W8 | 干道每 40 ± 5 m 一根杆；电线段数与杆距一致 |
| W9 | 写入 6 个通道；每点权重和 = 1 |

---

## 6. 风险与应对

| 风险 | 应对 |
|---|---|
| 从当前的大关卡切走时编辑器断言崩溃（traps 79、83） | 切前确认无脏包；崩了按 trap 78 先挪 `Saved/Autosaves/` 再请用户重启，之后直接 `load_level` |
| `Get_ActorData` 按 tag 读另一个 volume 的生成输出尚未在本项目实测 | W2→W3 是第一次用，W3 的 `read` 核对拿到的 item 与 tag |
| `Transform_MeshTerrain_Erosion` 的效果与强度单位未实测 | W1 读回谷底高程与山脊高度；破坏谷底就降强度或从图里去掉（记偏差） |
| 换 MPD 失败或材质不认通道 | 退回 demo MPD 的三个通道 |
| `Spawn_Assets` 按属性取网格、点缩放/旋转是否原样生效 | W3 水面是第一个用户，按实例变换核对 |
| 建筑语法的层高与 `Size` 含义 | W6 先用一张探针图实测，再定 4 组高度 |
| 顶点间距 5.86 m 对 5–8 m 宽的路偏粗 | 路基压平带放宽到半宽 + 6 m，路面抬 10 cm |
| Python 节点耗时 | 单节点目标 < 60 s（I/O 实测 18.7 / 23.6 µs 每点）；超了把那一步下沉为原生或降分辨率 |
| BiomeSample 针叶树与 Megaplants 风格不一 | 截图检查，必要时高处只留岩石与草 |
