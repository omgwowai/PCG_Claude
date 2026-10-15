# 18 张 City Sample PCG 图的 Python 化，与按 18 步搭建的小城镇 — 设计

> **已被取代（2026-10-15）**：用户澄清，目标是把每张图的计算节点换成一个 Python 脚本，只保留参数节点，
> 而不是逐节点重建官方图。新设计见 `docs/superpowers/specs/2026-10-15-pypcg-python-nodes-design.md`。
> 本文只作存档；§5 的小镇部分大多被新 spec 沿用。

> 日期：2026-10-13。状态：已被取代。
> 依据：飞书《18个核心PCG拆解》（https://omgwowai.feishu.cn/wiki/DSSwwgvfuicQblkBLGYcvpE0nab，
> 本地副本 `Saved/feishu/pcg_doc.md`，不入库）；技能 `city-sample-pcg-city-builder`；
> 前作 `docs/superpowers/specs/2026-09-24-pcg-small-area-18-stage-design.md`。
> 本设计的六节已在对话中逐节获得用户确认（2026-10-13）。

---

## 0. 目标、决定与成功标准

**用户目标**：官方 PCG 图的连线方式对 AI 不友好。把 City Sample 官方 Demo 的 18 张顶层 PCG 图
改造成 Python，然后新建一个关卡，用 Python 化的 PCG 严格按 18 个步骤搭建一个小城镇。

**用户拍板的决定**

| # | 决定 |
|---|---|
| D1 | **图即代码**：每张图一个可读 `.py`，由它生成 PCG 图资产，运行仍交给 PCG 引擎 |
| D2 | **等价翻译**：1509 个节点全部保留，重建图与官方图结构比对必须 0 差异 |
| D3 | **真实尺度小镇**：新画约 1 km 的城市轮廓，街区/地块参数保持官方值，只把主塔、中央公园缩到小镇量级 |
| D4 | 方案 A：翻译器生成初稿，再按飞书文档的步骤整理 |
| D5 | 新增一个小 C++ 编辑器插件 `PyPCGTools`，补齐 Python 反射写不到的私有字段 |
| D6 | 翻译基准是**本项目当前的** 18 张图，`PCG_3_3_1_Buildings` 里的 TL 样式**保留** |
| D7 | 主塔先缩到约 110 m，若第 15 步的建筑环缺失则退回官方的 160 m |
| D8 | 接受「真实尺度下 Large 档街区/地块可能为空」 |

**范围假设**（用户确认）：只翻译 18 张顶层图，它们调用的 67 个库子图当函数库直接调用；
新关卡是 demo 关卡的模板副本（地形 MeshPartition 是硬依赖，空白关卡静默零点）；
地标尺寸由小镇配置覆盖；生成的图资产放在 `/Game/PyPCG/`，不改插件里的官方资产。

**成功标准**

1. 18 个 `.py` 各自按飞书文档的步骤分节、使用语义变量名。
2. L1（离线）与 L2（编辑器内）：18 张重建图与官方图 **0 差异**（定义见 §3.2）。
3. L3（行为）：在 demo 关卡中，官方图与 PyPCG 图按 1→18 各跑一遍，**每阶段按网格分类的实例数完全相同**。
4. 小镇关卡 `/Game/PyPCG/L_PyTown`：18 步按顺序各自通过 §5.5 的验收；再完整重跑一遍，每阶段实例数与第一遍相同；保存。
5. 小镇图与官方图的差异**恰好**是配置声明的那些处（§3.3），其余全同。

**不在范围内**：改 18 张图的结构或参数含义；翻译 67 个库子图；World Partition 分区烘焙；
改 `/CitySamplePCG/`、`/PCGPrimitives/` 下的任何资产；改已交付的 `L_SmallArea18`。

---

## 1. 关键事实（2026-10-13 只读实测）

| # | 事实 | 来源 |
|---|---|---|
| F1 | 18 张图合计 **1509 节点 / 1780 边**；637 个子图调用，调用 67 个不同的库子图；43 种原生节点类 | `tl_probe_graph_dump.py` → `Saved/graph_dumps/PCG_*.json` |
| F2 | 图间连接两种：**38 处 `ActorReferences`**（写死指向 demo 关卡的 13 个 Actor 路径）+ 按 Tag 取作者数据（`City`、`Arteries`、`Terrain_shaping_1`、`HighRise`、`LAKE`、`USER_SPLINE`、`FOREST_EXCLUSION`） | `pyg_probe_export_t3d_all.py` → `Saved/graph_dumps/PCG_*.t3d` |
| F3 | Python **能写**：子图参数覆盖（整结构 import_text 精确往返，含 `ActorReferences` 数组）、节点位置与标题、标量子图参数（`set_double_parameter` 等） | `pyg_probe_write_routes.py` |
| F4 | Python **写不了**：参数读取节点的 `PropertyGuid`（95 个节点，无 Blueprint 标记）、内联 pin 默认值 `DefaultValues`（protected，约 60 个节点：Maths 50 / StringOp 6 / MakeVector 3 / Remap 1）、节点注释 `NodeComment`（protected，181 处）、评论框 `CommentNodes`（无反射暴露，158 个，分布在 16 张图） | `pyg_probe_api_gaps.py`、`pyg_probe_write_routes.py` |
| F5 | 图用户参数的整结构 import_text 只在源图已加载时成功（属性包结构体按名查找），不能当真源 | 引擎 `InstancedStruct.cpp` `ImportTextItem` |
| F6 | 上述 F4 的每一项在 C++ 都有入口：`IPCGSettingsDefaultValueProvider::SetPinDefaultValue/SetPinDefaultValueIsActivated`、`UPCGGraph::AddUserParameters`、`UPCGUserParameterGetSettings::PropertyGuid`（public）、`UPCGGraph::SetCommentNodes`、`UPCGNode::NodeComment`（public） | UE 5.8 源码 |
| F7 | UE 默认的属性文本导出把浮点写成 6 位小数（如 `-1820.424606`），按它回写会引入约 1e-7 误差 | T3D 与 `LexToString` |
| F8 | 09-24 小区域关卡（模板副本）阶段 7 实例 286,349，几乎等于全城的 286,221。**疑似**下游读到了 demo 关卡全城的旧数据——引用写死在 demo 关卡路径上，副本里理应解析不到。未证实 | `Tools/data/stage_census*.json` |

---

## 2. 架构

```
                 ┌──────────────── 一次性 ─────────────────┐
 18 张官方图 ──► 提取器(编辑器内, C++ 读全字段) ──► IR JSON ──► 代码生成器 ──► .py 初稿 ──► 按飞书步骤整理
                 └─────────────────────────────────────────┘
                                                              │
     Content/Python/pypcg/stages/s01_terrain.py … s18_outer_forest.py   ← 真源：Python
                         │
                         │ + 配置(official / town)：角色→Actor 绑定、地标尺寸覆盖
                         ▼
                  构建器 ──► /Game/PyPCG/{Official,Town}/PCG_*.uasset ──► 比对器（对官方 0 差异）
                         │
                         ▼
                  L_PyTown：18 个 PCGVolume，按 1→18 生成，逐步验收
```

| 组件 | 位置 | 职责 |
|---|---|---|
| `pypcg` 包 | `Content/Python/pypcg/` | DSL、IR、库别名表、构建器、比对器、`uetext` 解析 |
| 18 个阶段文件 | `Content/Python/pypcg/stages/sNN_*.py` | 每张图一个，按飞书文档分步 |
| 配置 | `Content/Python/pypcg/profiles/{official,town}.py`、`town_layout.py` | 角色→Actor 绑定；小镇地标尺寸覆盖；小镇控制样条坐标 |
| 库表 | `Content/Python/pypcg/library.json`（入库） | 67 个库子图与 43 种原生类的真实 pin、参数名与类型；提取器生成，DSL 离线校验用 |
| 翻译器与代码生成器 | `Content/Python/pypcg_translate.py`（编辑器内）+ `Tools/pypcg/codegen.py`（纯 Python） | 一次性生成初稿 |
| 官方 IR 快照 | `Tools/pypcg/official_ir/PCG_*.json`（入库） | 从当前项目的 18 张图提取（含 TL） |
| C++ 插件 | `Plugins/PyPCGTools/` | §4 的 9 个函数 |
| 桥入口脚本 | `Content/Python/pypcg_{extract,build,behaviour,town}.py` | 经 `run_unreal_script` 调用 |

---

## 3. Python 图格式、构建与比对

### 3.1 DSL

`stages/*.py` 只描述结构，**不 import `unreal`**。执行它只在内存里产出 IR；落成资产是构建器的事。
所以 L1 比对在 pytest 里离线跑。

| 写法 | 生成 | 说明 |
|---|---|---|
| `g.sub("库别名", "标题", set={...}, **pins)` | 子图调用 | 关键字名 = 输入 pin 名，值是端口；`set=` 是子图参数覆盖 |
| `g.node("类短名", "标题", set={...}, defaults={...}, **pins)` | 原生节点 | `defaults=` 是内联 pin 默认值 |
| `n.Selected` / `n["Subdividing_splines"]` | — | 取非 `Out` 的输出端口 |
| `g.param("名")` / `g.param_path("名")` | `PCGUserParameterGetSettings` / `PCGGenericUserParameterGetSettings` | 图参数在 `Graph(..., params={...})` 中带类型声明 |
| `g.actor_by_tag("City", ...)` | `Get_ActorData` | 按 Tag 取作者数据 |
| `g.ref("Roads", ...)` | `Get_ActorDataByRef` | **按角色名**取上游；`ActorReferences` 构建时由配置填入 |
| `h = g.declare("名", port)`、`h.use()` | 命名 reroute 声明 / 使用 | 每次 `use()` 一个使用节点，与官方逐个对应 |
| `g.reroute(port)`、`g.branch(...)` | reroute / Branch | 原样保留，它们是结构的一部分 |
| `with g.step(n, "名"):` | — | 只分组：自动排版（每步一列）+ 报告定位 |
| `comment="..."` | 节点注释 | 逐字照抄官方 |

pin 名或参数名写错时，**构建前**就报错，并列出该节点真实可用的 pin/参数（来自 `library.json`）。
一个 pin 接多条边时，`SecondaryInput=[a, b]` 的列表顺序就是边序。

### 3.2 真实片段（`s09_lots.py` 前 5 步，值来自对官方图的实测读取）

```python
"""PCG_3_1_4_Lots：从街区扣除占用，生成可建候选（飞书 S04 / 节点级拆解 10 步）
官方 185 节点 / 224 边；输出按 Tag 混装 Lots、reservedLots、unbuildableLots …"""
from pypcg import Graph, SIZES

g = Graph("PCG_3_1_4_Lots", params={
    "PlazaReservationRatio": 0.9, "PlazaReservationSeed": 0,
    "BuildableLotMinSizeSmallDistrict": 1000.0, "BuildableLotMaxSizeSmallDistrict": 15000.0,
    ...                                                   # 共 15 个，原样
})

with g.step(1, "取得原材料"):
    city      = g.actor_by_tag("City", "Get City Shape")
    road_fp   = g.sub("Filter_Tags", "Filter Road Footprints",
                      set={"FilteredInputTags": "RoadFootprints"},
                      PrimaryInput=g.ref("Roads", "Get Roads")).Selected
    landmark  = g.ref("MainTower", "Get Landmark")
    park      = g.ref("CentralParkFootprint", "Get Central_Park")
    highway   = g.declare("Highway Footprint", g.ref("Highways", "Get Highway"))
    districts = g.declare("Districts", g.ref("Districts", "Get Districts"))

with g.step(2, "形成第一版候选面"):
    lots = g.sub("Compose_Areas_Exclusion", "Lots", PrimaryInput=city, SecondaryInput=road_fp)
    # 文档出入：标题与飞书文档写「扣 Landmark 和 Highway」，实际连线是主塔 + 中央公园；
    #          Highway 到步骤 8 才扣。
    lots = g.sub("Compose_Areas_Exclusion", "Exclude Landmark and Highway",
                 PrimaryInput=lots, SecondaryInput=[g.reroute(landmark), g.reroute(park)])
    ...

with g.step(3, "公共空间分流"):
    pick = g.sub("Filter_RandomChoice", "Exclude Some Lots For Plaza Use",
                 set={"Ratio": 0.9, "Seed": 0, "RandomPerDataset": True},
                 PrimaryInput=lots,
                 Ratio=g.param_path("PlazaReservationRatio"),      # 运行时以 pin 为准
                 Seed=g.param_path("PlazaReservationSeed"))
    prepared = g.declare("Prepared Lots", pick.Selected)
    reserved = g.declare("Reserved Lots", pick.Unselected)

with g.step(4, "按街区档位取交"):
    lots_in = {}
    for S in SIZES:                                       # 三档结构完全对称，所以用循环
        dist = g.sub("Filter_Tags", f"Filter {S} Districts", comment=f"{S.upper()} DISTRICTS",
                     set={"FilteredInputTags": f"{S}Districts"},
                     PrimaryInput=districts.use()).Selected
        lots_in[S] = g.sub("Compose_Areas_Intersection", f"Lots in {S} Districts",
                           PrimaryInput=prepared.use(), SecondaryInput=dist)

with g.step(5, "三档面积门槛"):
    # 不生效：Min Size 节点保存的覆盖值是 2000，但 Size pin 接了图参数（默认 1000），
    #        所以 2000 被 pin 顶掉；以步骤实测为准。
    ...                                                   # Large 先走步骤 6 的内路网格，单独写
```

### 3.3 整理规则

1. 一图一文件；开头 docstring 写职责、输入角色、输出 Tag、官方节点/边数、对应的飞书章节。
2. 按飞书文档「节点级数据处理流程」的编号分步。文档没覆盖的节点归到最近的一步；纯调试显示分支统一放在末尾的「调试显示（不影响产出）」一步。
3. 连线与文档冲突时，**代码以连线为准**，冲突处写 `# 文档出入：` 注释。
4. 变量名表达数据语义（`road_fp`、`lots_in["Small"]`），不出现 `Subgraph_37` 这类名字。
5. 标题与节点注释**逐字照抄官方**（比对会核对）；解释只写在 Python 注释里。
6. 只有结构真正对称才写循环；有不对称处（如 Large 多一条内路网格分支）单独展开。
7. 保存了但不生效的值加 `# 不生效：` 注释（被 pin 顶掉的值、禁用节点、悬空输出）。飞书文档点名的五处
   （Rooftops 的 `AVERAGE`、Roads 的 `ntersection` Tag、Ground 的 `Polygon` Tag、LeftOverLots 的
   `LargeBuildingSkirt`、公园禁用的横向路分支）都按这条落成注释。
8. 跨图引用只写角色名，stage 文件里不出现关卡路径。
9. 只写与类默认值或子图默认值不同的值（翻译器判断），文件保持精简。
10. 节点坐标不写进 `.py`；构建器按步骤自动排版，比对时忽略坐标。

### 3.4 模块与验证层

| 模块 | 需要编辑器 | 职责 |
|---|---|---|
| `pypcg.dsl` / `ir` | 否 | 执行 stage `.py` → IR |
| `pypcg.uetext` | 否 | 把 UE 属性文本解析成类型化 Python 值（向量、枚举、对象路径…） |
| `pypcg.compare` | 否 | 两份 IR 求差异 |
| `pypcg.extract` | 是 + 插件 | 已有图资产 → IR（官方图与已建图都用它） |
| `pypcg.build` | 是 + 插件 | IR → 图资产 |

提取器和构建器共用同一份字段清单，「读得到就写得回、写进去就读得回」由代码保证。

### 3.5 「0 差异」的精确定义

不按节点对象名比（`Subgraph_37` 每次都不同）。规则是：**存在一个节点双射，使下列各项全部精确相同**。

| 比对（必须全同） | 排除（有意） |
|---|---|
| **图**：用户参数（名、类型、容器类型、类型对象、默认值、顺序、分类）；图级非默认属性（含 `Description`）；输入/输出节点的自定义 pin | 节点坐标；对象名；编辑器视图状态 |
| **节点**：settings 类；相对类 CDO 的**全部**非默认 UPROPERTY（含 protected，由插件导出）；子图资产路径；子图参数覆盖（哪些被覆盖 + 值）；内联 pin 默认值（值 + 激活状态）；标题；节点注释与气泡标志；enabled / debug | GUID：参数读取节点的 `PropertyGuid` 按**它解析到的参数名**比；评论框 GUID 忽略 |
| **边**：双射后的（上游节点, 输出 pin, 下游节点, 输入 pin）多重集，含命名 reroute 的不可见边；**同一输入 pin 接多条边时边序也算**（PCG 按边序拼装输入数据，影响 Gather、按索引取用和随机） | 临时 PropertyBag 结构体名 |
| **评论框**：文本、颜色、字号，以及**成员关系**（框在几何上包住了哪些节点，按双射比） | 构建器生成的「步骤 N」框（带 `pypcg:` 前缀） |
| `ActorReferences`：official 配置下必须复现 demo 关卡的 Actor 路径 | — |

**派生字段忽略清单**（每项都要在实现时写明理由，清单本身受 L3 行为验证约束）：
`CachedOverridableParams`、`CachedPins`——PCG 在 settings 变化后会重建的缓存。清单外一律不许跳过。

**数值精确比，不设容差。** 插件导出器按往返精度写 float/double 叶子（float32 9 位有效数字、
double 17 位）；代码生成写能往返的最短小数（float32 字段按 float32 精度校验），所以 `.py` 里是
`-1820.4246`，不是 17 位长数。

**找双射**：先做节点着色细化（节点自身签名 + 按 pin 区分的邻居签名，迭代到不动点），再在每个颜色类内
配对并检查所有边。仍有歧义的类（如几个一样的无标题 reroute）用有界回溯。pytest 里放包含对称结构的合成图。

### 3.6 三层验证

| 层 | 比对 | 何时 | 通过条件 |
|---|---|---|---|
| **L1 离线** | stage `.py` 执行出的 IR vs 官方 IR 快照 | pytest，每次整理后（不需要编辑器） | 0 差异 |
| **L2 编辑器内** | 从已建资产**重新提取**的 IR vs 从官方资产现场提取的 IR | 每次构建后 | 0 差异（证明构建器写全了） |
| **L3 行为** | demo 关卡里按 1→18 顺序生成两遍：官方图一遍、PyPCG 图（official 配置）一遍 | 翻译阶段的验收门槛，一次 | 每阶段**按网格**的实例数完全相同 |

L3 防的是提取器的盲区：若某字段根本没被提取，L1/L2 都会通过，但 L3 会暴露行为漂移。
demo 关卡只在内存里跑、不保存（同 09-23 做法）。切换图时先记录并补回 Volume 组件的参数覆盖
（如 `Highway_Width`，traps.md 44）。

**小镇构建**也跑 L2，对照官方 IR，但带**预期差异表**（小镇配置覆盖的那些：角色→小镇 Actor、地标尺寸），
必须得到「**恰好 N 处声明的差异，其余全同**」，证明小镇版没改结构。

### 3.7 构建流程

1. **原地重建**：资产已存在就清空节点与用户参数再建，不删再建（避免关卡里 Volume 的引用断掉，
   以及同名 `create_asset → None`，traps.md 15）。
2. 写入顺序：用户参数（C++）→ 节点（`add_node_of_type` / `set_subgraph`）→ settings 属性
   （可见的走 Python，其余走 C++）→ 子图覆盖（C++，按参数，支持数组）→ 内联 pin 默认值（C++）→
   参数读取节点绑定（C++）→ 命名 reroute 声明。**所有 settings 在连边之前**写完，因为部分 pin 要设好参数才出现。
3. 连边，**每条边立即校验**（边数必须增加）；然后标题、注释；按步骤自动排版；评论框。
4. 重新提取，跑 L2。**0 差异才保存**；失败时不保存，返回差异报告。
5. 两套资产：`/Game/PyPCG/Official/PCG_*`（只用于 L2/L3）与 `/Game/PyPCG/Town/PCG_*`（小镇关卡用）。
   要两套是因为引用烘焙在子图节点里；把它们提成图参数会改变结构、破坏等价。

### 3.8 差异报告

每个 IR 节点记录它在哪个文件、哪一行、哪一步创建，差异报告直接指到代码：

```
FAIL  PCG_3_1_4_Lots  2 处差异
  s09_lots.py:58  步骤5 "Buildable Lots Min Size - Small"
      set.Size: 官方 2000.0，py 缺失
  s09_lots.py:31  步骤2 "Exclude Landmark and Highway"
      边 SecondaryInput 顺序: 官方 [MainTower, CentralParkFootprint]，py [CentralParkFootprint, MainTower]
```

桥入口：`pypcg_extract.py {"graphs":[...]}`；`pypcg_build.py {"stages":[...], "profile":"official"|"town"}`
（内含 L2）；`pypcg_behaviour.py {"phase":...}`（L3，一阶段一次调用）。

---

## 4. C++ 插件 `PyPCGTools`

### 4.1 定位与原则

- `Plugins/PyPCGTools/`，单模块 `PyPCGTools`（Editor 类型，编辑器专用）；依赖 `Core`、`CoreUObject`、
  `Engine`、`PCG`、`PCGEditor`（参数分类）、`Json`；在 `.uproject` 中启用。
- **薄**：只暴露 Python 反射够不到的东西；DSL、构建顺序、比对逻辑全在 Python。
- 每个写函数返回字符串：空 = 成功，否则是错误信息，Python 侧抛出。不静默失败、不断言崩溃。
- **保护挂载点**：所有写函数拒绝 `/CitySamplePCG/`、`/PCGPrimitives*/`、`/Engine/` 下的资产
  （临时对象允许），从机制上杜绝误改官方图。
- 写入一律 `Modify()` + 触发 settings 变更通知，节点 pin 的刷新与编辑器里手改一致。

### 4.2 接口（9 个函数，`UPyPCGToolsLibrary`）

| # | 函数 | 为什么需要 | 覆盖 |
|---|---|---|---|
| 1 | `ExportGraphIR(Graph) → JSON` | **唯一的提取器**：一次读全字段，含 protected 与精确浮点 | §3.5 全部 |
| 2 | `SetPropertyText(Obj, Path, Text)` | 按路径写任意 UPROPERTY（含 protected），如 `ActorSelector.ActorFilter`；也用于图 `Description` | Python 看不到的 settings 字段 |
| 3 | `SetSubgraphParameter(SubgraphSettings, Name, Text)` | **按名**写一个子图参数覆盖（支持数组）并标记为已覆盖；绕开 F5 | 637 个子图节点、38 处 `ActorReferences` |
| 4 | `SetPinDefaultValue(Settings, Pin, Type, Value, Activated)` | 经 PCG 自己的 `IPCGSettingsDefaultValueProvider` 设内联默认值（类型转换 → 值 → 激活） | 约 60 个节点 |
| 5 | `SetGraphUserParameters(Graph, DescsJson)` | 按声明顺序重建图用户参数（名、类型、容器、类型对象、默认值、分类） | 18 张图 |
| 6 | `BindUserParameterGetter(Getter, Name)` | 按图的参数描述写 `PropertyGuid` + `PropertyName` 并刷新输出 pin | 95 个读取节点 |
| 7 | `SetNodeComment(Node, Text, Visible, Pinned)` | 节点注释文本与气泡状态 | 181 处 |
| 8 | `SetGraphCommentBoxes(Graph, BoxesJson)` | 整体替换 `CommentNodes`（位置、尺寸、文本、颜色、字号），GUID 新生成 | 158 个官方框 + 生成的「步骤」框 |
| 9 | `ExportObjectProperties(Obj, NonDefaultOnly) → JSON` | 调试：看任意单个对象 | — |

### 4.3 `ExportGraphIR` 的 IR 形状（提取器与构建器共用）

```json
{ "graph": { "params": [{"name","type","container","type_object","value","category"}],
             "props": {...非默认...}, "description": "...", "comment_boxes": [...] },
  "nodes": [{ "name", "class", "title", "comment", "bubble", "enabled", "debug",
              "settings": {...相对类 CDO 的非默认值，含 protected...},
              "subgraph": "/PCGPrimitives/...", "overrides": {"ActorReferences": [...]},
              "pin_defaults": [{"pin","type","value","activated"}],
              "getter_param": "PlazaReservationRatio",
              "in_pins": [{"label", "edges": [["Subgraph_15","Out"], ...]}] }] }
```

编码规则：float 叶子按往返精度；枚举写名字；对象引用写路径；**指向同图内另一节点的引用**
（如命名 reroute 的 `Declaration`）写成 `{"node_ref": 名}`；instanced 子对象与属性包内联展开；
**边按输入 pin 的边序记录**（即 PCG 拼装数据的顺序）。

### 4.4 与 Python 的配合

```
提取：pypcg_extract.py ──► PyPCGTools.ExportGraphIR ──► IR JSON
构建：stage .py ──► IR ──► pypcg.build：
        可见字段 → set_editor_property（照旧）
        其余     → 函数 2–8
      ──► ExportGraphIR(新图) ──► compare(官方 IR) ──► 0 差异才保存
```

### 4.5 验证

1. **编译**：`Build.bat PCG_ClaudeEditor`，exit 0，新模块零警告。
2. **C++ 自动化测试** `PyPCGTools.*`（`#if WITH_DEV_AUTOMATION_TESTS`），headless 跑
   `Automation RunTests PyPCGTools`。这是本项目第一批 C++ 测试，CLAUDE.md 的「Tests」一节同步更新。
   - 函数 2–8 各自：在临时图上写 → `ExportGraphIR` 读回精确相等；
   - 对保护挂载点写入必须被拒绝；错误的 pin 名/参数名必须返回错误；
   - **保存 → 重新加载 → 再导出不变**（证明落盘）。
3. **Spike**（计划第一个任务），在批量翻译前先确认三个最大风险点：
   - 写进 `CommentNodes` 的评论框在打开图编辑器时确实出现；
   - 用户参数 + 读取节点绑定经保存、重载后仍有效；
   - 经 provider API 设的内联 pin 默认值与官方行为一致（一张图的 L3）。

### 4.6 代价

- 加模块需要**关编辑器编译**（编辑器当前开着 `Lvl_TL_Spline`）；编译后直接启动进目标关卡
  （编辑器内切关卡有已知崩溃风险）。
- 插件后续改动同样要重编译并重启，所以接口刻意做小。

---

## 5. 小镇关卡与 18 步搭建

### 5.1 角色表（38 处引用 → 12 个角色）

| 角色 | demo 中的 Actor | 读取方（节点标题） |
|---|---|---|
| `Terrain` | PCG_1_1_Terrain Volume `…2022633615` | Roads、Ground、OuterForest（"Get Base Terrain" / "Get City Layout Volume"） |
| `MainTower` | PCG_2_1 Volume `…1290570802` | Roads、Lots、Ground、LeftOverLots、MainTower_Visuals |
| `CentralParkFootprint` | `1_CentralPark_Footprint` `…1296577182` | Roads、Lots、Ground、LeftOverLots、CP_Visuals、OuterForest |
| `Districts` | `…2022637616` | Roads、Lots、Ground、LeftOverLots |
| `Roads` | `…1944600151` | Highways、Lots、Ground、LeftOverLots、CP_Visuals、OuterForest |
| `Highways` | `…1377087312` | Lots、LeftOverLots、OuterForest |
| `Lots` | `…2022641618` | Ground、LeftOverLots、Buildings |
| `Buildings` | `…2022648621` | Rooftops |
| `Parkings` | `…1886871024` | CP_Visuals（与 `Roads` 同一个数组） |
| `ParkingFootprint` | `…2022646620` | Parkings。**具体是哪个 Actor 要现场确认** |
| `LandmarkPark` | `MainTowerPark` 样条 `…1392886487` | Lots、Ground、LeftOverLots |
| `HighwaySplines` | `HighWay_2` + `HighWay_3`（一个数组） | Highways |

角色的「demo 中的 Actor」一列是从外部 Actor 文件按 UAID 反查的，计划里第一个关卡任务要在编辑器里
逐个复核。F8 的疑点意味着：**本设计把「每个引用都指到小镇自己的 Actor」列为硬验收项**（§5.5）。

### 5.2 关卡来源与清理

1. 模板复制出 `/Game/PyPCG/L_PyTown`，带过来 `MeshPartition` 地形、18 个 Volume、灯光、水面和机位。
   沿用 `pcg_sa_level.py` 的两条路（`new_level_from_template`，目标已存在时退到
   `new_map_from_template` + `save_map`）。
2. 每个 Volume `cleanup_local`，清掉模板残留的生成物（如 Districts 上的 67 条样条）。
3. 按 §5.3 重写控制样条：`set_spline_points` + 闭合 + 点类型；多余控制 Actor（`Artery_3`、第二个
   `HighRise_Zone` 等）销毁。样条读写顺序遵守 traps.md 30（读点在动 Actor 之前，写点在动 Actor 之后）。
4. 移动/缩放两个地标 Volume；按小镇范围重新放置机位。
5. 解析 12 个角色在小镇里的真实路径，写进 `profiles/town.py`；构建 `/Game/PyPCG/Town/*`，挂到对应 Volume。
6. 重新 `set_graph` 后**补回组件级参数覆盖**（traps.md 44），如 `Highway_Width`、主塔 Width/Length。

### 5.3 小镇布局

所有点坐标集中在纯数据文件 `profiles/town_layout.py`，AI 改布局只改这一个文件。
小镇中心在原点（Terrain 读写范围 ±1.5 km 内）。

```
                    N
         Highway ×2 (平行, 间距约 30 m, 长约 1.8 km)
            ╲╲
   ┌─────────╲╲────────────┐      City 轮廓：不规则八边形，约 1.1 km × 0.9 km
   │          ╲╲  HighRise │      Terrain_shaping_1：约 1.6 × 1.3 km 椭圆，包住小镇
   │   Artery A2 ╲╲ (r≈100m)│
───┼──────┼───────╲╲──[⬡]──┼─── Artery A1（东西向缓弯，两端各伸出轮廓约 250 m）
   │      │         ╲╲ 主塔+小公园
   │ [中央公园 ~260×90 m, │      ⬡ 主塔 footprint，见 §5.4
   │  斜 30°, 湖+2 园路]  │ [P] 停车场约 70×45 m
   └──────┼────────────────┘
          │ （南北向，伸出轮廓）
```

| 控制项 | 官方 | 小镇 |
|---|---|---|
| City / Terrain_shaping_1 | 2130×1818 m / 3107×2324 m | 约 1100×900 m / 约 1600×1300 m |
| Arteries | 3 条 | 2 条，十字相交 |
| Highway | 2 条平行，横穿全城 | 2 条平行，掠过东北角并部分进入轮廓，保证出现 `UnderHighway` 地块 |
| HighRise_Zone | 2 个，约 600–700 m | 1 个，半径约 100 m，围绕主塔 |
| LandmarkPark（小公园） | 250×231 m | 约 70×70 m，紧邻主塔 |
| 中央公园内 LAKE / USER_SPLINE / FOREST_EXCLUSION | 各 2 | 1 片湖、2 条园路、1 块排除区，全部落在新公园内 |

**街区和地块参数全部保持官方值。** 按官方阈值估算，1 km 小镇以 Small 档街区（60×30 m 街块）为主，
可能有少量 Medium，**Large 很可能没有**。因此 `LargeBuildingSkirt`、大地块内路等 Tag 可空（D8）。

### 5.4 地标尺寸

原则：**能不改图就不改图**。
- 尺寸若由 Volume 变换或组件参数决定（`Highway_Width` 如此，主塔 Width/Length 很可能也是），只改关卡，
  图与官方完全一致。
- 只有尺寸确实写死在节点里（中央公园 `Park Footprint 1000x200m` 那个 `Create_Spline_Shape` 是候选），
  才在小镇配置里覆盖，并登记进预期差异表。
- 具体属于哪种，由计划里的一个探查任务确定。

**主塔**（D7）：`MainTower_Visuals` 里写死了 10/15/30/32.5 m 的收缩与约 25 m 的六边形边长，
footprint 小于约 100 m 时内外环会收缩到消失。先从 160 m 缩到 **约 110 m**；第 15 步实测若有建筑环缺失，
退回 160 m。**中央公园** 1000×200 m → 约 260×90 m。

### 5.5 严格的 18 步执行与逐步验收

**执行规则**：按 1→18 顺序；**每阶段两次调用**（先生成，下一次调用再读，traps.md 33）；
上一阶段没过验收不进入下一阶段。

**每步通用检查**

1. **引用正确性（硬性）**：该阶段读取的上游 Volume 本轮确实已生成并产出了所需 Tag（例如第 7 步前，
   Districts 输出里有 `localRoads` / `CollectorRoads` / `ArteryRoads`）。**第 4–16 步的产物包围盒必须
   落在小镇范围 +200 m 以内**——读到全城旧数据会直接失败。
2. **非零**：数据型阶段（4、5、6、9）查输出 Tag 数量；生成型阶段查实例数，并按网格目录分类
   （Building / Road / Prop / Megascans…）。
3. **截图**：每阶段一张累计几何截图（新机位）；全部完成后补总览、街景、俯视三张。

**专属判据**

| 步 | 判据 |
|---|---|
| 1 Terrain | 地形写入：小镇中心与外圈的高度剖面符合「城内平坦、城外起伏」 |
| 2–3 远景 | 远景建筑全部在约 4.1 km 中心排除区之外；山体实例 > 0 |
| 4–5 地标轮廓 | 各 1 个闭合面，位置和尺寸与布局一致 |
| 6 Districts | 必需：Artery / Collector / local 三类道路 + Small 街区；其余可空。街区面积之和 ≈ 轮廓面积减干道 |
| 7–8 道路 / 高速 | `RoadFootprints`、`ModifiedTerrain`、`Highway` 三个 Tag 都存在；实例 > 0 |
| 9 Lots | `Lots`、`reservedLots`、Small 档建筑轮廓 > 0，`UnderHighway` > 0；其余可空 |
| 10–14 | 都 > 0；第 13 步建筑样式**包含 TL** |
| 15–16 地标视觉 | 主塔各环都有建筑；公园有树、有湖面 |
| 17–18 外围 | 码头 > 0；**外林 > 0**（09-24 小区域此步为 0，重点盯） |

**完成定义**：18 步全部过验收；再按 1→18 完整重跑一遍，每阶段实例数**与第一遍相同**（确定性）；保存关卡。

---

## 6. 错误处理、测试、交付

### 6.1 错误处理

| 情况 | 处理 |
|---|---|
| 编辑器未连接 | 停下请用户启动，不重试 |
| 插件编译失败 | 修到 Build.bat exit 0。**不绕过**：Python 侧不退回「复制官方节点」 |
| L1 / L2 有差异 | **不保存**，返回带文件行号的报告；修 `.py` 或提取器后重跑 |
| L3 计数不同 | 说明提取器有盲区。找出缺的字段（对比该阶段按网格计数 → 缩小到节点 settings），补进提取器与 IR，重跑 L1–L3。**不进入小镇阶段** |
| 小镇某步验收失败 | 停在该步。先查上游（引用、Tag、包围盒），再查布局（太小、位置不对）。修在 `town_layout.py` 或小镇配置，不改 stage `.py` 的结构；从该步起按顺序重跑 |
| 包围盒越界（读到全城旧数据） | 按引用错误处理：重新解析角色绑定并核对上游 Volume 路径 |
| 编辑器崩溃 | 挪走 `Saved/Autosaves`，直接启动进目标关卡（不在编辑器内切关卡）；关卡只在最后保存，崩溃只丢内存态；从最后一个通过的阶段重跑 |
| 桥不响应 | 不重试；查 `netstat`、日志尾 |

**常驻纪律**（traps.md）：一个脚本一次往返，改动编辑器的调用严格串行；UObject 只放函数局部；
截图在下一次调用核验、文件名一次性；生成后下一次调用再读。

### 6.2 测试

| 层 | 内容 | 运行方式 |
|---|---|---|
| pytest（离线） | DSL / IR、`uetext` 解析、比对器（含对称图、边序、精确浮点）、代码生成器，以及 **L1：18 个 stage `.py` vs 官方 IR = 0 差异** | `C:\Python314\python.exe -m pytest Tools/pypcg/tests -q` |
| C++ 自动化 | `PyPCGTools.*` 的 9 个函数（§4.5） | `UnrealEditor-Cmd … -ExecCmds="Automation RunTests PyPCGTools; Quit" -unattended -nullrhi` |
| 编辑器内 | L2（每张图一次构建调用）、L3（一阶段一次调用）、小镇 18 步验收 + 确定性第二遍 | `pypcg_build.py` / `pypcg_behaviour.py` / `pypcg_town.py` |
| 回归 | 3×3 区域仍 41 实例；TL 展示关卡仍 1,562 | 现有 `pcg_postmigration_regression.py`、TL 探针 |

### 6.3 交付物与 git

**入库**：`Plugins/PyPCGTools/`（源码）；`Content/Python/pypcg/`（DSL、构建器、比对器、库表、18 个 stage、
2 个配置、布局）；桥入口脚本；`Tools/pypcg/`（代码生成器、官方 IR 快照、测试）；`.uproject` 的插件条目；
`Content/PyPCG/` 下的 36 个图资产；本 spec 与计划；**`docs/pypcg-guide.md`**（AI 如何改图与重建、
DSL 速查、整理规则）；小镇验收报告与 census JSON。

**小镇关卡**：`.gitignore` 加 `/Content/__ExternalActors__/PyPCG/` 与 `__ExternalObjects__` 的例外后，
关卡与外部 Actor 入库，做法同 `PCGArea`。600 m 区域当时生成了 507 MB、3 个超过 50 MB 的文件，
至少一个超过 100 MB；1 km 小镇的生成 Actor 很可能也会超过 GitHub 的 100 MB 上限。
**做法**：只把关卡定义（布局、Volume、图挂载）入库，**生成的 Actor 不入库**（逐个按 GUID 路径排除并注明）；
18 步是确定性的，`pypcg_town.py` 可以在干净克隆上重新生成。报告里如实写明。

**分支**：`main` 受保护、要求 PR。工作在 `pypcg-18-stage-town` 分支，按任务提交，完成后 PR 合并。

**不碰**：18 张官方图、`/CitySamplePCG/`、`/PCGPrimitives/`（插件也会拒绝写入）、demo 关卡（L3 只在内存里跑、
不保存）、现有的 `L_SmallArea18`。

### 6.4 计划分期（交给 writing-plans）

每期验证通过后才进入下一期：

1. C++ 插件 + spike
2. 提取器 + 库表 + 官方 IR 快照
3. DSL / 比对器 / 代码生成器（pytest）
4. 构建器 + L2
5. 18 个 stage 出初稿并整理到 L1 = 0，由简到繁：2_2 → 2_1 → 1_x → 5_1 → … → 3_1_2 Roads
6. L3 行为等价
7. 小镇关卡与布局
8. 18 步验收与报告
9. 文档、技能 traps、PR

---

## 7. 已知取舍与风险

| 项 | 说明 |
|---|---|
| 两套图资产 | 引用烘焙在子图节点里，official 与 town 各建一套；代价是 36 个资产，换来结构与官方完全等价 |
| 插件是硬依赖 | 没有 `PyPCGTools`，构建器写不了 F4 的四类字段。插件刻意只做 9 个函数 |
| F8 疑点 | 若 09-24 的阶段确实读的是 demo 关卡的旧数据，那次的数字不能当本次的参照；本设计用包围盒硬验收防止重蹈 |
| Large 档可能为空 | 真实尺度的必然结果（D8），验收里列为可空 |
| 主塔缩放 | 内部写死的收缩距离可能让 110 m 主塔缺环（D7 有退路） |
| 生成 Actor 不入库 | GitHub 100 MB 单文件上限；靠确定性重生成补偿，报告写明 |
| L3 只在 demo 关卡跑一次 | 证明的是「official 配置下与官方等价」；小镇的正确性靠 §3.6 的预期差异表 + §5.5 逐步验收 |
