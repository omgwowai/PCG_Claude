# 18 张 City Sample PCG 图的计算改由 Python 节点完成，与按 18 步搭建的小城镇 — 设计

> 日期：2026-10-15。状态：待用户审阅。
> **取代** `docs/superpowers/specs/2026-10-13-pypcg-18-stage-town-design.md`（"图即代码、逐节点等价"）。
> 依据：
> - 飞书《18个核心PCG拆解》（https://omgwowai.feishu.cn/wiki/DSSwwgvfuicQblkBLGYcvpE0nab，本地副本 `Saved/feishu/pcg_doc.md`，不入库）
> - Districts 探针报告 `.superpowers/sdd/2026-10-13-pypcg-18-stage-town/spike-districts-report.md`（本设计的 §1 事实大多出自它）
> - 本设计的五节已在 2026-10-15 的对话中逐节获得用户确认。

---

## 0. 目标、决定与成功标准

**用户目标**：官方 PCG 图由大量计算节点组成，靠人手调，对 AI 不便捷。要做的是：
- 把每张图里**大量的计算节点替换成一个 Python 脚本**，只留下提供参数的节点供人工调整；
- 新建一个关卡，用这样的 18 张图，严格按 18 个步骤搭一个小城镇。

**用户拍板的决定**

| # | 决定 |
|---|---|
| E1 | 每张图 = 参数节点 + 场景输入节点 → **Python Data Processor 节点**（读 `.py` 文件）→ 引擎生成节点 → 输出 |
| E2 | **接受与官方不同的布局**：Python 用自己的随机数，不移植 PCG 的 RNG |
| E3 | **范围**：2D 布局图基本全进 Python。网格/地形/建筑类图保留引擎生成节点，由 Python 只算它们的输入 |
| E4 | **只在编辑器里生成**：结果保存进关卡，不要求打包游戏运行时重新生成 |
| E5 | **替换深度**：除参数、场景输入、引擎生成外，全部进 Python，包括批量点操作（撒点、投影、按纹理写属性、选资产） |
| E6 | **Roads 等图里重复的参数合并成一个入口** |
| E7 | **去掉分区生成**：GridPartition / LoopSpawnActorPerData 分支，以及 `Partitioned` / `PartitionGridSize` 参数 |
| E8 | 去掉调试显示分支 |

**成功标准**

1. 18 张瘦身图各自通过 V1 / V2 / 结构核对（§3）。
2. 小镇关卡 `/Game/PyPCG/L_PyTown`：
   - 用 18 张瘦身图按 1→18 逐步通过 V3（§5）；
   - 再完整重跑一遍，各步实例数与第一遍相同；
   - 保存。
3. 交付 `docs/pypcg-guide.md`：给人和 AI 的改参数 / 改 Python / 加步骤说明。

**已知偏差（用户 2026-10-21 接受，作为后续工作）**（2026-10-21 终审 I3 / I4；guide §11 末行、§12 第 5、10 条）：
- 标准 1：阶段 7 的 V2 是 **FAIL**，实例 275 523 对 286 361（-3.8 %），确定性步骤的上限是 1 %。
  根因是 local 类路段的切分粒度（上游 `Gather_0` / 地标裁切，未定位；carry 5）。
- 标准 2 / §5.1"外林 > 0"：小镇阶段 18 放 0 棵树，因为项目里没有 `/Game/Textures/Noise/T_CloudNoise_4k`
  （trap 66；carry 10）。官方 demo 上也是 0。

**不在范围内**：
- 移植 PCG 的随机数算法；
- 运行时（打包游戏）生成；
- 分区生成；
- 改 `/CitySamplePCG/`、`/PCGPrimitives/` 下的任何资产。

---

## 1. 关键事实（2026-10-15 实测）

| # | 事实 | 来源 |
|---|---|---|
| G1 | 一个约 270 行的 Python 模块（只依赖 `unreal` + 标准库）复现了 Districts 的全部 7 类输出：个数全同；面积差 ≤ 0.0034 m²；道路端点差 ≤ 0.8 cm。前提是借用官方的 6 个随机切分比例。用 Python 自己的随机数时拓扑相同，各档面积偏差最多 ±23 % | 探针 |
| G2 | GeometryScript 的二维多边形函数可从 Python 调用（`unreal.GeometryScript_PolygonList.polygons_intersection / difference / union / offset`、`get_polygon_area` 等），底层与 PCG 同为 Clipper2。`get_polygon_vertices` 返回的 `valid` 恒为 False，是引擎 bug，忽略即可 | 探针 |
| G3 | 厘米级一致依赖两处隐蔽的引擎细节：<br>① 样条转折线时每段曲线固定一分为二；<br>② `Polygon2DOperation` 在被切多边形的平面坐标系里运算（原点 = 顶点均值，yaw −90°） | 探针 |
| G4 | 引擎自带插件 `PCGPythonInterop` 提供 **Python Data Processor** 节点。<br>• 脚本：内联或 `.py` 文件，文件每次执行都重新读取。<br>• 运行方式：脚本在公共 `__main__` 作用域运行，拿到 `data_in`（FPCGDataCollection）和 `data_out.add_to_collection(data, pin, tags)`；输入输出 pin 是动态的。<br>• 限制：只在编辑器、主线程、不缓存、Beta。<br>• 现成二进制的 BuildId 与本引擎不符，启用需要编译 | 探针（读源码） |
| G5 | 参数读取节点接到 Python 节点的输入 pin 上，数据以 `PCGParamData` 送达，按属性名读取；`data_in.get_typed_inputs_by_pin_label(label, cls)` 可用 | 探针 |
| G6 | Python **建不出** `PCGPolygon2DData`（多边形和变换的 setter 只有 C++）。闭合 LINEAR `PCGSplineData` 可以替代，下游原语接受 | 探针 |
| G7 | 编辑器 Python 的点吞吐（每 10 万点）：建点 0.61 s、写一个属性 0.35 s、写回 0.05 s、读回 0.09 s、逐点射线 1.12 s | `pyg_probe_point_throughput.py` |
| G8 | demo 关卡的 Districts 组件覆写了全部 13 个参数（例如可细分阈值 77499 而非 150000） | 探针 |
| G9 | 18 张图按角色分（不含输入输出节点，共 1473 个）：<br>逻辑 519、布线 455、参数读取 134、引擎生成 164、批量点操作 138、场景读取 63 | 按 IR 快照统计 |

---

## 2. 架构

### 2.1 每张图的形状

```
 图参数（图上的用户参数，可在关卡里逐 Volume 覆写）
   └─ 参数读取节点 ×N ──────────────────────► Params pin ─┐
 场景输入                                                  │
   Get_ActorData（City / Arteries / …）       ─┐           │
   Get_ActorDataByRef（上游步骤的输出）       ─┼─► 各自的输入 pin ─► [Python Data Processor，内联两行：
   Get_MeshTerrain（地形表面）                ─┤                      from pypcg import host
   LoadDataAsset / LoadCitySampleData        ─┘                      host.run("s06_districts", globals())]
                                                           │ 多个输出 pin，按 Tag 分组
                                                           ▼
                        引擎生成：Spawn_Assets / StaticMeshSpawner / Shape Grammar /
                        Assign_CitySampleBuildings / Fitting Assets / Create_Mesh /
                        Write_MeshTerrain / Crosswalks
                                                           ▼
                                                 输出（Tag 与官方兼容）
```

- **保留为节点**：参数读取、场景读取、引擎生成。
- **进 Python**：其余全部，即过滤、布尔、细分、属性运算、随机选择、布线、撒点、地形投影、按纹理写属性、选资产。
- **一张图通常 1 个 Python 节点。** 只有当引擎生成夹在中间（Python → 引擎节点 → 再 Python）时才用 2 个。估计 Buildings 和两个 Visuals 需要 2 个。

### 2.2 Python 阶段的接口

```python
# Content/Python/pypcg/stages/s06_districts.py
PARAMS = {"Dividable_district_Limit": 150000.0, "SmallMediumThreshold": 200000.0, ...}  # 名称 → 默认值，类型由默认值决定
INPUTS = ("City", "Arteries")                    # 输入 pin
OUTPUTS = ("ArteryRoads", "CollectorRoads", ...) # 输出 pin（= 输出 Tag）

def run(inputs, params, ctx):
    """inputs: {pin: [(值, frozenset(tags))]}，值都是纯 Python 结构（pypcg.geo）。
    params 不含 Seed；ctx.rng = random.Random(f"{Seed}:{STAGE}")，ctx.ops = 引擎布尔等服务。
    返回 {pin: [(数据, [tags])]}。不 import unreal。"""
```

> **实施时的定稿（ruling N1，2026-10-15 计划）**：签名是 `run(inputs, params, ctx)`，不是上面初稿里的
> `run(inputs, params, seed)`。host 构造 `random.Random(f"{Seed}:{STAGE}")` 放进 `ctx.rng`，引擎布尔
> （GeometryScript）放进 `ctx.ops`（ruling N2），这样阶段文件里没有任何播种代码，离线测试注入 `FakeOps`。
> 完整契约见 `Content/Python/pypcg/stage_api.py` 的模块说明。

- **单一来源**：图描述（`pypcg/graphs/`）从阶段模块的 `PARAMS` / `INPUTS` / `OUTPUTS` 生成图参数、参数读取节点和 pin，不重复声明。
- **host shim** `pypcg/host.py`：节点的内联脚本只有两行（见 §2.1），由 `host.run(stage, globals())` 完成：
  1. `importlib.reload` 该阶段模块和 `pypcg.geo`，改 `.py` 后下一次生成立即生效；
  2. 用 `pypcg.ue` 把 `data_in` 解包成纯结构。参数从 `Params` pin 读取：每个参数读取节点送来一个 `PCGParamData`，host 按属性名合并。收到的参数名与 `PARAMS` 不一致时报错，不静默用默认值；
  3. 调 `run()`；
  4. 把结果用 `pypcg.ue` 打包成 PCG 数据，写进 `data_out`。
- **纯结构**（`pypcg.geo`）：
  - `Polygon`：外环 + 洞，顶点为 `(x, y)`，cm，CCW；
  - `Spline`：控制点 + 是否闭合 + 是否线性；
  - `Points`：变换数组 + 属性列；
  - `ParamSet`：属性字典。
- **随机数**：
  - 每张瘦身图都有一个 int 参数 `Seed`，由图构建器自动添加，不写在 `PARAMS` 里，默认取 demo 关卡里该步组件的 seed。
  - host 用 `random.Random(f"{Seed}:{步骤号}")`。字符串种子走 SHA-512，不受 `PYTHONHASHSEED` 影响，跨会话可复现。
- **多边形输出**：给 `PyPCGTools` 加 `MakePolygon2DData(vertices, holes, transform) -> UPCGPolygon2DData`，使输出类型与官方一致。插件本来就要重编（启用 PCGPythonInterop），代价很小。
- **地形投影**：场景读取节点把 MeshTerrain 送进 Python 节点，脚本用 PCG 地形数据自身的 `project_point` / `sample_point`。不用射线，所以语义与官方投影一致，也不受地形写入后碰撞未更新的影响。这两个函数能否从 Python 调用尚未实测，由 P0 验证；退路见 §4.3。

### 2.3 共享库

| 模块 | 内容 | 是否离线可测 |
|---|---|---|
| `pypcg/geo/` | 多边形 / 样条 / 点的纯结构；面积、裁线、递归切分、网格细分、撒点（均匀 / 随机）、样条重采样与偏移、按权重选择、面积 / 边长过滤、RNG | 是（pytest） |
| `pypcg/ue/` | PCG 数据 ↔ 纯结构；GeometryScript 布尔封装（含 G3 的平面坐标系）；地形投影；纹理采样 | 否（编辑器内 V2 harness） |
| `pypcg/host.py` | 节点 shim | 否 |
| `pypcg/stages/sNN_*.py` | 18 个阶段的 `run()` | 大部分是（纯结构输入） |
| `pypcg/graphs/sNN_*.py` | 18 张瘦身图的 DSL 描述：参数、输入、Python 节点、生成节点、连线 | 是（结构核对） |

### 2.4 逐图替换清单

#### 实测（2026-10-21，取代下面的估计表）

"官方"各列来自 `docs/pypcg/stages/sNN-brief.md`（`Tools/pypcg/port_brief.py` 按 IR 快照分类，2026-10-15）：
参数读取、场景读取、carrier（只为保留节点转运数据的 reroute）、引擎生成、丢弃（调试 / 分区 / 死分支）、
计入 Python。"瘦身图"两列是 18 张 `pypcg/graphs/sNN_*.py` 实际构建出的节点数（`to_ir(official)`，**不含**
图自带的输入 / 输出节点；`pypcg_build_slim.py` 报告的 `nodes` 含这两个，即每行 +2），全部 `diffs: 0`。

| # | 图 | 官方 | 参数 | 场景读取 | carrier | 生成 | 丢弃 | 计入 Python | 瘦身图节点 | 其中 Python 节点 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Terrain | 20 | 2 | 4 | 0 | 1 | 0 | 13 | 13 | 2 |
| 2 | BG_Buildings | 7 | 0 | 0 | 0 | 1 | 0 | 6 | 8 | 1 |
| 3 | BG_Mountains | 7 | 0 | 1 | 0 | 1 | 0 | 5 | 9 | 1 |
| 4 | MainTower_Footprint | 6 | 2 | 0 | 0 | 0 | 1 | 3 | 5 | 1 |
| 5 | CentralPark_Footprint | 3 | 0 | 0 | 0 | 0 | 1 | 2 | 5 | 1 |
| 6 | Districts | 75 | 10 | 2 | 0 | 0 | 18 | 45 | 13 | 1 |
| 7 | Roads | 210 | 38 | 7 | 1 | 12 | 16 | 136 | 111 | 1 |
| 8 | Highways | 34 | 1 | 3 | 0 | 2 | 5 | 23 | 23 | 1 |
| 9 | Lots | 183 | 11 | 7 | 5 | 2 | 23 | 135 | 25 | 1 |
| 10 | Ground | 121 | 0 | 9 | 6 | 6 | 24 | 76 | 36 | 1 |
| 11 | Buildings | 176 | 14 | 4 | 3 | 23 | 35 | 97 | 53 | 3 |
| 12 | Rooftops | 22 | 0 | 1 | 0 | 5 | 3 | 13 | 9 | 2 |
| 13 | LeftOverLots | 135 | 3 | 8 | 6 | 8 | 15 | 95 | 24 | 3 |
| 14 | Parkings | 81 | 0 | 2 | 2 | 3 | 6 | 68 | 8 | 2 |
| 15 | MainTower_Visuals | 120 | 1 | 3 | 3 | 30 | 0 | 83 | 41 | 6 |
| 16 | CentralPark_Visuals | 188 | 2 | 9 | 2 | 13 | 19 | 143 | 59 | 2 |
| 17 | CityEdge | 18 | 0 | 2 | 0 | 1 | 5 | 10 | 7 | 1 |
| 18 | OuterForest | 67 | 6 | 7 | 2 | 1 | 4 | 47 | 22 | 2 |
| | **合计** | **1473** | **90** | **69** | **30** | **109** | **175** | **1000** | **471** | **32** |

- **瘦身图 471 个节点** = 82 个参数 getter（每个参数一个，含自动加的 `Seed`）+ 保留的场景读取与生成节点
  + 32 个 Python 节点 + 按裁决留原生的计算节点（见 `docs/pypcg-guide.md` "哪些留在原生"）+ 少量 reroute。
- **"计入 Python" 的 1000 个不全进了 Python**：`port_brief.py` 把每个原语子图算作 1 个节点（实际内部可达
  数百，例如 Roads 经 `Intersection_solving` 170 / `Crosswalks` 75 / 投影器 34），而按裁决留原生的部分
  （阶段 1 的模糊与 GPU 投影、阶段 7 地形压平、阶段 9/10/16 的语法后点链、贴图读取、`@data` 适配器、阶段 16
  的草地）仍算在这一列里。每张图实际进 Python 的数目与留原生的理由见各自的 `docs/pypcg/stages/sNN.md`。
- Python 节点多于 1 个的图（1、11、12、13、14、15、16、18）都是因为引擎生成节点夹在中间（§2.1 末条）。

#### 初稿估计（2026-10-15，保留备查）

| # | 图 | 之前 | 之后 | 保留的引擎节点 | 进 Python | 难度 |
|---|---|---|---|---|---|---|
| 1 | Terrain | 20 | ~8 | Get/Write MeshTerrain | 起伏噪声、外圈遮罩、城市压平、LERP | 中（地形读写） |
| 2 | BG_Buildings | 7 | ~2 | Spawn_Assets | 外环布尔、撒点、随机剔除 | 低 |
| 3 | BG_Mountains | 7 | ~3 | LoadDataAsset、MeshSpawner | 拷到锚点、姿态 / 高度修正 | 低 |
| 4 | MainTower_Footprint | 6 | ~3 | — | 六边形 | 低 |
| 5 | CentralPark_Footprint | 3 | ~3 | — | 矩形（长宽改为参数，新增 2 个参数读取） | 低 |
| 6 | Districts | 75 | ~14 | — | 切分、递归切、分档、网格 | 探针已完成 |
| 7 | Roads | 210 | ~58 | Shape Grammar ×6、Spawn、Crosswalks、Write_MeshTerrain ×2 | 路口求解、裁线、外轮廓 union、贴花 | 高 |
| 8 | Highways | 34 | ~7 | Shape Grammar、Spawn | 重采样、投影、支柱接地 | 中 |
| 9 | Lots | 183 | ~22 | Shape Grammar（内路）、Spawn | 面布尔、三档过滤、庭院、内路网、账目 | 高 |
| 10 | Ground | 121 | ~16 | Shape Grammar ×2、Assign_Rule、Spawn ×3 | 人行道线段、铺装区、七类地砖、围栏 | 中高 |
| 11 | Buildings | 176 | ~46 | BDF ×3、Create_Mesh 屋顶、SetComplex / AssignShape | 纹理写高度、HighRise、轮廓预处理 | 中 |
| 12 | Rooftops | 22 | ~7 | Fitting ×4、Spawn | 尺寸分流、高度过滤、点差集 | 低中 |
| 13 | LeftOverLots | 135 | ~20 | Fitting ×5、Spawn ×3 | 广场 / 树分流、地砖、树点 | 中高 |
| 14 | Parkings | 81 | ~6 | Assign_Rule ×2、Spawn | 车位布局、入口、占用、车辆朝向 | 中 |
| 15 | MainTower_Visuals | 120 | ~36 | BDF ×17、Shape Grammar、Fitting、Create_Mesh、Spawn | 六边形 / 环 / 臂拆分、广场、树环 | 中 |
| 16 | CentralPark_Visuals | 188 | ~28 | Shape Grammar ×6、BDF、Create_Mesh、Write_MeshTerrain、Spawn | 园路网、分区、植被密度、湖 | 高 |
| 17 | CityEdge | 18 | ~4 | Spawn | 凸包、码头候选 | 低 |
| 18 | OuterForest | 67 | ~15 | Spawn | 排除区、密度、物种索引、岸边衰减 | 中 |
| | **合计** | **1473** | **~298** | 119 个引擎生成节点 | **~1121 个节点进 Python** | |

- **之后的 ~298 个节点** = 89 个参数读取（合并重复后 87 个，加中央公园新增 2 个）+ 69 个输入节点（场景读取与数据资产加载）+ 119 个生成节点 + 约 21 个 Python 节点。
- **之前的 1473 个节点的去向** = 87 个保留为参数读取 + 69 个输入 + 119 个生成 + 1121 个进 Python + 77 个丢弃（调试与分区分支）。
- 这些数字都是估计；实测值见上方"实测"表。

---

## 3. 验证标准

### V1：算法单元测试（离线 pytest）

**不变量**：
- 细分后各块面积之和 = 原面积（±0.01 %）；
- 区域两两不重叠；
- 网格线全部落在原多边形内；
- 撒点都在区域内；
- 同 seed 同结果，不同 seed 不同结果。

**边界**：
- 空输入 → 空输出；
- 退化多边形（零面积、自交）跳过并记录；
- 极端参数（例如网格大于区域）仍有合理结果。

只依赖纯数学的部分（鞋带公式、裁线、RNG）离线测；依赖 GeometryScript 的部分放进编辑器内的 V2 harness。

### V2：逐步与官方对照（编辑器内，demo 关卡，迁移时每步一次）

一次只替换一步，上下游仍是官方图：

1. **上游不变**，输入完全相同。
2. **跑两版并记录**：先跑官方版，记录各输出 Tag；再在内存里把该 Volume 的图换成瘦身图，跑一遍并记录。
   - 换图前，把官方组件上的参数覆写按名称抄到瘦身图的同名参数上（G8；合并过的参数取官方第一个入口的值）；
   - 结束后换回官方图。
   - **demo 关卡绝不保存。**
3. **结构性等价**（必须成立）：
   - 官方有的 Tag 都有；
   - 数据类型兼容；
   - 全部输出落在官方同 Tag 输出的包围盒 +200 m 内；
   - 下游官方步骤用 Python 输出照常运行，且实例数非零。
4. **统计一致**：以官方为参照。
   - 初始阈值见下表，迁移时可按步调整，每次调整连同原因记入 `docs/pypcg-v2-thresholds.md`。
   - 官方个数 < 5 的 Tag 只做结构检查，不比个数和面积：这种 Tag 由随机波动主导，G1 里单个 seed 的各档面积偏差就达到 ±23 %。

| 类别 | 指标 | 初始阈值 |
|---|---|---|
| 区域 | 总面积 | ±10 % |
| | 个数 | ±25 % |
| 线 | 总长 | ±10 % |
| 点 / 实例 | 总数 | ±25 % |
| | 各网格类别占比 | ±10 个百分点 |
| 纯确定性步骤 | 同上 | ±1 % |

5. **多 seed**：
   - 有随机的步骤跑 5 个 seed，拿官方值与 5 次结果的**中位数**比较阈值。
   - 不用"官方值落在 5 次结果的最小 / 最大值之间"作为关卡：即使移植完全正确，官方值落在 5 次范围外的概率也有 1/3。
   - 无随机的步骤只跑 1 次。

不通过时：先怀疑移植（对照官方 IR 的子图内部），再考虑放宽阈值。

**实施时定下的三条比较口径**（计划 rulings，已写进 `pypcg/v2.py` 与 `pypcg_compare_stage.py`）：

- **N3**：名字里含 `:` 的 tag（`Type:…`、`Primitive:…`）是 PCGPrimitives 的簿记，V2 一律忽略。
- **T7c（取代"官方有的 Tag 都有"的字面读法）**：官方输出里还有大量**不含** `:` 的簿记 tag（`X`、`Y`、`City`、
  `PCG Generated Component`、`Selected`/`Unselected`、`SubdivideAreasWith*` 等，Districts 的 79 个官方 item 全被覆盖），
  照 N3 比会让完美的移植 79 处失败。所以 V2 **只比该步的"契约 tag"**：`port_brief.output_tags(ir)` 从官方 IR
  抽出的、真正到达输出的 `AddTag`/`Write_Tag` 值。输出不带 tag 的步骤（1、4、5、13）整体作为一组 `(all)` 比较。
- **N10**：官方 item 数 < 5 的 tag 跳过 **item 个数**和**总面积**两项（上表第 4 条的落实），但**总长**和**点数**照比——
  一个 item 里可以有成千上万个点。

阈值的每次改动（含按 tag 的覆写）都在 `Content/Python/pypcg/v2_thresholds.json` 与 `docs/pypcg-v2-thresholds.md` 里成对记录。

### 结构核对（取代旧 L1 / L2）

瘦身图构建后重新导出，与该步的 DSL 描述比对：参数、输入、Python 节点、生成节点、连线逐项相同（用 `compare.py`）。不再与官方图比。

### V3：小镇验收（§5）

---

## 4. 迁移顺序与已有工作

### 4.1 已有工作（分支 `pypcg-18-stage-town` 上 16 个提交）

| 工作 | 状态 | 新角色 |
|---|---|---|
| C++ 插件 `PyPCGTools`（9 个函数 + 6 个测试） | 保留、扩展 | 仍用于从 Python 建图；加 `MakePolygon2DData` |
| 18 张官方图的 IR 快照（`Tools/pypcg/official_ir/`） | 保留 | Python 移植的算法规格 |
| `compare.py` | 保留 | 瘦身图的结构核对 |
| `dsl.py` + `build.py` | 保留，小改 | 描述和构建瘦身图；加 Python Data Processor 节点与动态 pin |
| codegen + 18 个逐节点草稿（`pypcg/stages/s*.py`） | 退役 | 移到 `Tools/pypcg/reference_drafts/` 备查；`pypcg/stages/` 这个路径给新阶段 |
| `/Game/PyPCG/Official/` 的 18 个逐节点资产 | 退役 | 新图验证通过后删除 |
| 旧 L1 / L2 / L3 | 取代 | 改为 V1 / V2 / 结构核对 / V3 |
| Districts 探针（`Content/Python/spike_districts/`，未入库） | 转正 | 第一个阶段实现 + 共享库雏形；对照 harness 成为 V2 工具 |
| 旧 spec / 旧 plan | 存档 | 顶部标明已被本 spec 取代 |

### 4.2 迁移顺序

| 期 | 步骤 | 理由 |
|---|---|---|
| P0 基础 | — | 启用 PCGPythonInterop 并加 `MakePolygon2DData`（一次编译）；host shim、ue 适配层、DSL / 构建器支持 Python 节点、V2 harness |
| P1 全链路 | 6 Districts | 探针转正，第一张真正的"Python 节点图"，走通 V1 / V2 |
| P2 简单步骤 | 4、5、2、3、17 | 节点少，打磨 host 与生成节点的接法 |
| P3 布局骨架 | 7 → 8 → 9 | 最难、最核心；共享库在这里成形 |
| P4 地表层 | 10、13、14 | 以铺装、撒点、投影为主 |
| P5 建筑 | 11、12 | BDF 保留原生 |
| P6 地标与外围 | 15、16、18、1 | Terrain 最后切，因为它写的地形影响一切 |
| P7 小镇 | 1→18 | §5 |
| P8 收尾 | — | 指南、技能 traps、回归、删除退役资产、PR |

每一步的完成标准：
- V1 过；
- V2 过（5 个 seed 的中位数在阈值内，下游官方步骤照常运行）；
- 结构核对过；
- 一个提交。

V2 时上游始终是官方图，所以任何一步都可以单独迁移和验证。P3 内仍按 7 → 8 → 9 的顺序做，因为共享库在 Roads 里成形。

### 4.3 风险与退路

| 风险 | 退路 |
|---|---|
| Python Data Processor 节点有阻塞缺陷（例如读不到参数 pin） | 阶段脚本不变，改由 `PyPCGTools` 扩展的 C++ 包装节点调用 |
| 某步太慢（单步 Python > 60 s） | 先 profile；仍不行就把那一个批量操作放回原生节点，在该步说明里记下原因 |
| 地形数据的 `project_point` / `sample_point` 不能从 Python 调用 | 改用射线投影（G7：每 10 万点 1.12 s），并且只在地形写入完成后的下一次调用里投影 |
| 隐蔽的引擎细节（类似 G3） | 由 V2 暴露，记入 traps.md |
| 合并 Roads 的重复参数后下游读不到 | 合并只发生在 Python 一侧，图的输出 Tag 与类型不变，下游不受影响 |

---

## 5. 小镇

### 5.1 沿用旧 spec §5 的部分

- **关卡来源**：demo 关卡的模板副本 `/Game/PyPCG/L_PyTown`（MeshPartition 地形是硬依赖）。
- **清理**：每个 Volume 执行 `cleanup_local`，销毁多余的控制 Actor。
- **布局**（坐标集中在 `pypcg/profiles/town_layout.py`，由 pytest 校验）：
  - City 约 1100×900 m，两条十字相交的干道；
  - 两条平行高速掠过东北角，保证出现 UnderHighway 地块；
  - 1 个 HighRise 区；
  - 主塔约 110 m（退路 160 m）+ 小公园；
  - 中央公园约 260×90 m、斜 30°（1 片湖、2 条园路、1 块排除区）；
  - 停车场约 70×45 m。
- **真实尺度**：街区和地块参数取官方值，Large 档可能为空。
- **角色绑定**：13 个跨步骤引用解析到小镇自己的 Actor，用包围盒硬性校验。
- **执行**：1→18 顺序，每步两次调用（先生成，下次调用再读）。
- **逐步通用检查**：
  - 引用正确：第 4–16 步的产物包围盒在小镇 +200 m 内；第 1–3、17、18 步本来就在城外；
  - 非零；
  - 截图。
- **逐步专属判据**：例如 Buildings 含 TL、主塔各环都有建筑、外林 > 0。
- **收尾**：确定性第二遍、3 张总览图、HTML 报告 + census JSON。
- **git 策略**：超过 100 MB 的生成 Actor 不入库，靠确定性重生成。

### 5.2 改变的部分

1. **用的图**：小镇各 Volume 挂 `/Game/PyPCG/Town/PCG_*` 的瘦身图。
2. **随机**：每步按 §2.2 由图参数 `Seed` 与步骤号派生，可复现。
   - 改某一步的 `Seed`：只重抽这一步自己的随机选择，下游步骤随之重跑；
   - 改 `town_layout.py`：改城镇形状。
3. **地标尺寸**：主塔宽 / 长、中央公园长 / 宽都是 Python 脚本暴露的普通参数，小镇只在 Volume 组件上设值。旧的 knob / 预期差异表机制退役。
4. **合理性范围**：没有官方对照，V3 在硬性规则之外再加宽松的合理性范围：
   - 每公顷建筑数在官方城市密度的 [0.5×, 2×] 内；
   - 每平方公里道路长度在官方的 [0.5×, 2×] 内；
   - 官方密度取自 V2 的基线。
5. **人工调参**：验收报告列出每步的关键参数及当前值；调参后只需从该步起重跑。

### 5.3 交付物

- 18 张瘦身图 + 18 个 Python 阶段 + 共享库 + host shim；
- 小镇关卡；
- V1 测试；
- V2 逐步对照报告（18 步官方 vs Python 的统计）；
- V3 小镇报告（18 张步骤截图 + 3 张总览 + 参数表）；
- `docs/pypcg-guide.md`。

---

## 6. 已知取舍

| 项 | 说明 |
|---|---|
| 布局与官方不同 | E2 的直接结果；V2 用统计一致 + 多 seed 衡量"做的是同一件事" |
| 只在编辑器 | E4；Python Data Processor 是 Beta 且只在编辑器 |
| 批量点操作进 Python | E5；按 G7 的实测吞吐，1 km 小镇每步秒级到数十秒级。超过 60 s 时把那一个操作放回原生节点（§4.3） |
| 引擎生成节点保留 | BDF、Shape Grammar、网格生成、地形写入在 Python 中无法复现，也不该复现 |
| 逐节点草稿退役 | 它们解决的是"描述图"，不是"替换计算"；保留备查 |
