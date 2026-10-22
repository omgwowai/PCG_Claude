# PyPCG 使用指南 —— 18 张 City Sample 阶段图的 Python 版，与 18 步小镇

> 适用于：人和 AI。要改参数、改算法、加步骤、重跑小镇，都从这里开始。
> 设计：`docs/superpowers/specs/2026-10-15-pypcg-python-nodes-design.md`（§2.4 已换成实测节点数）。
> 计划：`docs/superpowers/plans/2026-10-15-pypcg-python-nodes.md`（29 个任务）。
> 分支 `pypcg-18-stage-town`（merge base `4f7d11e`，2026-10-14 ~ 10-21，共 107+ 个提交）。
> 逐阶段的算法说明在 `docs/pypcg/stages/sNN.md`，契约在 `sNN-brief.md`，V2 结果在 `docs/pypcg/v2/sNN.md`。
> 实测坑在技能 `.claude/skills/city-sample-pcg-city-builder/references/traps.md` 第 51–84 条。

---

## 0. 先记住这条（trap 78）

**编辑器异常退出（崩溃、卡死被结束）后，重启之前先把 `Saved/Autosaves/` 下的内容挪到
`Saved/Autosaves_bak_<日期>/`；重启时若仍弹「Restore Packages」，选不恢复。**
点了恢复，会把 demo 关卡的自动保存版本写回 `Plugins/CitySamplePCG/Content/__ExternalActors__/` 下的真实 actor
文件——等于悄悄保存了 demo（本计划实测发生过两次，18 个文件被改写、11 个探针 volume 被写成正式 actor）。
该目录被 `.gitignore` 忽略，git 救不回；原件在 `E:\CitySample 5.8\Plugins\Experimental\CitySamplePCG\Content\`，
逐文件 `cmp` 可核对（当前 194 / 194 逐字节相同）。

同类的另一条（traps 79、83）：从 Python 切关卡时**不要**先 `new_blank_map`；离开 demo 或 `L_PyTown` 这类大型
World Partition 关卡的 `load_level` 也可能在拆世界时触发 `!LevelList.Contains(TickTaskLevel)` 断言崩溃。
切关卡前确认 `EditorLoadingAndSavingUtils.get_dirty_map_packages()` 为空，崩了就按上面先挪 Autosaves 再重启。

---

## 1. 是什么

**18 张图 = 18 个纯 Python 阶段 + 18 张"瘦身图"描述。**

| 部分 | 位置 | 说明 |
|---|---|---|
| 阶段模块 | `Content/Python/pypcg/stages/sNN_*.py` | 纯 Python，**不 import unreal**。定义 `STAGE`、`DOC`、`RANDOM`、`PARAMS`、`INPUTS`、`OUTPUTS` 和 `run(inputs, params, ctx)`。一张图有多个 Python 节点时，第二个起是同目录下的 `sNN_<名字>.py`（如 `s13_leftover_plazas.py`） |
| 瘦身图描述 | `Content/Python/pypcg/graphs/sNN_*.py` | `build() -> dsl.SlimGraph`：参数 getter、场景读取、Python 节点、保留的引擎生成节点、连线 |
| 资产 | `/Game/PyPCG/Slim/PCG_*`（demo 关卡用）、`/Game/PyPCG/Town/PCG_*`（小镇用）、`/Game/PyPCG/Probe/PCG_PyProbe`（阶段 0 探针） | **由 `pypcg_build_slim.py` 从描述生成**，不要在图编辑器里手改 |
| 共享库 | `pypcg/geo/`（纯几何：面积、裁线、切分、撒点、样条、框架、`assets` 选资产…）、`pypcg/ue/`（PCG 数据 ↔ 纯结构、布尔、地形）、`pypcg/host.py`（节点 shim）、`pypcg/stage_api.py`（契约）、`pypcg/checks/sNN.py`（V1 不变量）、`pypcg/v2.py` + `v2_thresholds.json`（V2）、`pypcg/census.py`（读产出） | |
| 编辑器脚本 | `Content/Python/pypcg_build_slim.py`、`pypcg_compare_stage.py`（V2）、`pypcg_v1_editor.py`（V1）、`pypcg_town_level.py`、`pypcg_town.py` | 都经 `run_unreal_script` 调用 |
| C++ 插件 | `Plugins/PyPCGTools`（Editor 模块，13 个函数，见 §8） | |
| 引擎插件 | `PCGPythonInterop`（Beta，提供 Python Data Processor 节点），已在 `.uproject` 启用并编译进 `E:\UnrealEngine` | |

每个 Python 节点的内联脚本只有两行（ruling N4）：

```python
from pypcg import host
host.run("s06_districts", globals())
```

`host.run` 每次先丢掉缓存的 `pypcg.*` 模块（trap 55），所以**改完 `.py` 下一次生成立即生效，不用重建图、不用重启编辑器**；
它把 `data_in` 转成纯结构、调 `run()`、把结果写回 `data_out`。

阶段签名（ruling N1）：

```python
def run(inputs, params, ctx):
    # inputs: {pin: [(值, frozenset(tags))]}，值是 pypcg.geo 的 Polygon / Spline / Points / ParamSet
    # params: {名字: 值}，不含 Seed
    # ctx.rng = random.Random(f"{Seed}:{STAGE}")；ctx.ops = 引擎布尔等服务（离线测试注入 FakeOps）
    return {pin: [(值, [tags])]}
```

每张瘦身图自动多一个 int 参数 `Seed`（排第一，默认 42 = demo 组件的 seed）。各图原有的种子参数并进 `Seed`，
`Debug*`、`Partitioned`、`PartitionGridSize` 被丢弃（ruling N5，spec E7/E8）。

---

## 2. 改一张图的流程

1. 改 `pypcg/stages/sNN_*.py`（算法）或 `pypcg/graphs/sNN_*.py`（接线 / 保留哪些原生节点）。
   **只改 `.py`，不要在图编辑器里改 `/Game/PyPCG/Slim|Town` 资产——下一次构建会整张覆盖。**
2. 离线测试：
   ```powershell
   C:/Python314/python.exe -m pytest Tools/pypcg/tests -q          # 基线 762 passed, 18 skipped
   C:/Python314/python.exe -m pytest Tools/pypcg/tests/test_s06_districts.py -q
   ```
   18 个 skip 全是 `test_stages_l1.py` 的逐节点草稿（已退役，见 §9）。`test_graphs.py` 对 18 张图都会跑：
   描述能构建、每个 Python 输入 pin 都接了线、每个输出都有人用、`Seed` 在第一位。
3. 只改了阶段模块（没动 `PARAMS` / `INPUTS` / `OUTPUTS` / `DOC`）时，**不必重建图**，直接重新生成。
   改了描述、参数或 `DOC`（`DOC` 会序列化进资产）时重建：
   ```
   run_unreal_script("pypcg_build_slim.py", {"stages": [6]})                     # -> /Game/PyPCG/Slim
   run_unreal_script("pypcg_build_slim.py", {"stages": [6], "profile": "town"})  # -> /Game/PyPCG/Town
   ```
   每行结果必须是 `diffs: 0`（构建后重新导出，与描述逐项比对；不为 0 不保存）。
4. 在 demo 关卡里跑 V2 / V1 验证（§6）。小镇里则从该步起重跑（§7）。

---

## 3. 加一个参数

1. 在阶段模块的 `PARAMS` 里加一行，带 tooltip：
   ```python
   from pypcg.stage_api import Param
   PARAMS = {
       "RectWidth": Param(16000.0, "Width of the landmark rectangle in centimeters", type="Float"),
       "DockRatio": 0.5152000188827515,          # 也可以只给默认值，类型由默认值决定
   }
   ```
2. 在 `run()` 里用 `params["RectWidth"]`。host 收到的参数名与 `PARAMS` 不一致时报错，不静默用默认值。
3. 重建瘦身图（§2 第 3 步）。构建器为每个参数加一个图参数和一个 getter，接进 Python 节点的 `Params` pin（一个参数一个 getter，spec E6）。
4. 之后关卡里每个 volume 的 PCG 组件都能覆写它（组件 → Graph Instance → 参数）。小镇的覆写写在
   `pypcg/profiles/town.py` 的 `COMPONENT_OVERRIDES`，由 `pypcg_town.py {"phase": "assign"}` 施加。
   注意 `set_graph` 会清掉组件上的覆写（trap 44），所以 assign 总是"设图 + 设参数"一起做。

只被保留的原生节点读、Python 不读的官方参数（如阶段 1 的 `HillsHeight`、阶段 18 的 `ScaleMin/Max`）不进 `PARAMS`，
在描述里用 `dsl.SlimGraph(S, extra_params=(dsl.official_param(S.STAGE, "HillsHeight"),))` 原样带过来。

---

## 4. DSL 速查（`pypcg/dsl.py`）

| 写法 | 作用 | 例 |
|---|---|---|
| `g = dsl.SlimGraph(S, extra_params=(), more_modules=())` | 一张瘦身图：按阶段模块生成参数、getter 和主 Python 节点；`more_modules` 为夹在生成节点后面的第二个 Python 节点 | `g = dsl.SlimGraph(S, more_modules=(B,))` |
| `g.py` / `g.pynodes["s13_leftover_plazas"]` | 主 Python 节点 / 按模块名取其他 Python 节点；`g.py["Footprint"]` 是它的输出 pin | `g.out(g.py["Footprint"])` |
| `g.p(name)` | 某参数 getter 的输出（同名共享一个 getter） | `g.connect(g.p("Road_Profile"), node, "Profile")` |
| `g.python(module, inputs, outputs, title)` | 手加一个 Python Data Processor（一般由 `SlimGraph` 自动建） | — |
| `g.keep(official_name, **pins)` | 原样复制官方图里的一个节点（类、子图、覆写、pin 默认值、标题），Actor 引用转成角色；引用了本图其他节点的不能 keep（会报错） | `g.connect(g.keep("Subgraph_0"), g.py, "City")` |
| `g.actor_by_tag(tag, title)` | 新建 `Get_ActorData`（按 actor tag 读） | `g.actor_by_tag("City", "Get City")` |
| `g.ref(roles, title)` | 新建 `Get_ActorDataByRef`（读上游 volume 的产出，按角色名解析到具体 actor） | `g.ref("Districts", "Get Districts")` |
| `g.self_point()` | 本 volume 自己的变换作为一个点（`Mode = GetSinglePoint`），阶段 4/5 用 | `g.connect(g.self_point(), g.py, "Volume")` |
| `dsl.official_param(stage, name)` | 原样取官方图的一个用户参数定义，给 `extra_params` | `dsl.official_param(S.STAGE, "ScaleMin")` |
| `g.connect(src, node, pin)` | 连线；src 可以是节点、`node["Pin"]` 或它们的列表 | `g.connect(g.py["Lots"], spawn, "In")` |
| `g.out(*srcs)` | 接到图的输出节点 | `for pin in S.OUTPUTS: g.out(g.py[pin])` |

完整的小例子（阶段 6）：

```python
from pypcg import dsl
from pypcg.stages import s06_districts as S

def build():
    g = dsl.SlimGraph(S)
    g.connect(g.keep("Subgraph_0"), g.py, "City")       # Get City Shape Spline
    g.connect(g.keep("Subgraph_1"), g.py, "Arteries")   # Get Arteries
    for pin in S.OUTPUTS:
        g.out(g.py[pin])
    return g
```

**硬规则：Python 节点的每个输入 pin 都必须接线。** 动态输入 pin 对执行是"必需"的，没接线的话图编译器会把整个
Python 节点静默剔除（trap 80）；`SlimGraph.to_ir` 因此对未接线的 pin 直接抛错。

---

## 5. 移植一张新图（本计划的移植协议）

完整版在计划的 "port protocol"（`.superpowers/sdd/2026-10-15-pypcg-python-nodes/port-protocol.md`，临时工作区，会被删除；
要点抄在这里）。

1. **契约**：`C:/Python314/python.exe Tools/pypcg/port_brief.py N` → `docs/pypcg/stages/sNN-brief.md`
   （参数、场景读取、生成节点、输出 tag、下游读者；按 IR 快照 `Tools/pypcg/official_ir/` 分类）。
   注意它的两个已知盲点：把原语子图算 1 个节点；下游只按 tag 检测、看不到 `ActorReferences` 角色（§9）。
2. **Step A 算法说明** `docs/pypcg/stages/sNN.md`：每一步写清**它替代了哪些官方节点**（原语内部的也要写），
   有意的差异、复现不了的部分和替代做法。**第一次 V2 决定说明对不对；失败时先改说明再改代码。**
3. **Step B 测试先行**（`Tools/pypcg/tests/test_sNN_*.py`）：契约测试 → 全空输入不抛错 → 任务不变量 →
   同 seed 相同、不同 seed 不同（`RANDOM = False` 的跳过）。
4. **Step C 阶段模块**：纯函数；布尔用 `ctx.ops`，随机用 `ctx.rng`，不 import unreal；共享的帮手进 `pypcg.geo` 并带测试，
   不在两个阶段里各抄一份。
5. **Step D 图描述**：`keep()` 契约里的每个场景读取和生成节点，接好每个 Python 输入，每个 Python 输出接到消费它的生成节点或输出；
   `pypcg_build_slim.py {"stages": [N]}` → `diffs: 0`。
6. **Step E V2 + V1**（§6）。
7. **Step F 计时与提交**：run record 的 `seconds` > 60 时，把那一个批量操作放回原生节点并在说明里记下（spec §4.3）。
   一张图一个提交：阶段、描述、checks、测试、说明、阈值改动。

经验（详见 traps 58–77）：

- 会被下游采样的几何要**逐位**复现引擎的运算顺序和原始输入位（trap 62）——差 1e-12 cm 就能改几百个下游实例。
  用 `geo.place` / `stage_api.volume_quat` / `geo.frames`，判一致用 `==`。
- 原样交回的输入多边形会被转发成引擎自己的数据对象（`convert.passed_through`，trap 68），框架保住；
  新造的多边形走 `MakePolygon2DData`，框架是自己质心的——这是已知限制（§9）。
- 样条写回要带控制点旋转，转角语法和建筑节点读它（traps 63、75）。

---

## 6. V2 与阈值

V2 在 demo 关卡 `/CitySamplePCG/Levels/L_CitySamplePCG_Demo` 里跑，一次只换一步，上下游仍是官方图。
**demo 关卡绝不保存**；所有改动都在内存里，`restore` 撤销。每次调用只做**一次**生成，下一次调用再读（生成是异步的）。

```
run_unreal_script("pypcg_compare_stage.py", {"phase": "prepare"})                       # 每个编辑器会话一次
run_unreal_script("pypcg_compare_stage.py", {"phase": "gen",  "stage": N, "variant": "official"})
run_unreal_script("pypcg_compare_stage.py", {"phase": "read", "stage": N, "as": "official"})
# 对 V2_SEEDS = (7, 13, 101, 977, 42) 各一次：
run_unreal_script("pypcg_compare_stage.py", {"phase": "gen",  "stage": N, "variant": "slim", "seed": 7})
run_unreal_script("pypcg_compare_stage.py", {"phase": "read", "stage": N, "as": "slim_7"})
# 对 stages.DOWNSTREAM[N] 里的每个 k（官方图读 slim 的 N）：
run_unreal_script("pypcg_compare_stage.py", {"phase": "gen",  "stage": k, "variant": "official"})
run_unreal_script("pypcg_compare_stage.py", {"phase": "read", "stage": k, "as": "down_%d_slim" % k, "into": N})
# 再生成一次官方 N（official_after），以及各下游的官方基准 down_<k>_official
run_unreal_script("pypcg_compare_stage.py", {"phase": "verdict", "stage": N})     # -> docs/pypcg/v2/sNN.md
run_unreal_script("pypcg_v1_editor.py", {"stage": N})                             # V1：重放 + 不变量
run_unreal_script("pypcg_compare_stage.py", {"phase": "restore"})                 # 官方图、覆写、regen 标志全部换回
```

记录落在 `Saved/Reports/v2/sNN/`。读之前的三条纪律：

- 慢阶段 `gen` 和 `read` 之间等 100–240 s；读到 `items` 对而 `instances` 少一个数量级就是"读早了"（traps 59、65）。
- slim 连续换 seed 时 `generate_local` 会隔一次空跑（trap 71）：`read` 现在会拒收 Seed 对不上的 run record，但仍要看日志里有新的 `PyPCG sNN` 行。
- 任何改了组件 seed 的探针跑完都要 `gen official` 或 `restore`（trap 67）。

**判据**（spec §3，`pypcg/v2.py`）：

| 类别 | 指标 | 默认阈值 |
|---|---|---|
| 区域 | 总面积 / 个数 | ±10 % / ±25 % |
| 线 | 总长 | ±10 % |
| 点 / 实例 | 总数 | ±25 % |
| | 各网格类别占比 | ±10 **个百分点**（pp，绝对差，不是相对 %） |
| 纯确定性步骤（`RANDOM = False`） | 同上 | ±1 % |

- 有随机的步骤拿官方值和 5 个 seed 的**中位数**比；无随机的跑 1 次。
- **只比契约 tag**（ruling T7c）：`port_brief.output_tags(ir)` 抽出的官方输出 tag；含 `:` 的忽略（N3）；
  不带 tag 的步骤整体作为 `(all)`。
- 官方 item 数 < 5 的 tag 不比个数和面积，只比结构、总长、点数（ruling N10）。
- 包围盒：输出要落在官方同 tag 包围盒 + `bbox_margin_cm`（默认 200 m）内。
- 下游：下游官方步骤读 slim 输出照常运行且实例非零。**`downstream: []` 不看量级**，要自己比下游实例数（trap 62）。

**阈值**：默认值在 `Content/Python/pypcg/v2_thresholds.json` 的 `default`；按步覆写在 `stages.<N>`，按 tag 覆写在
`stages.<N>.tags.<tag>`。**每次改动都要在 `docs/pypcg-v2-thresholds.md` 加一行**（日期、步骤、键、旧值、新值、理由与证据）。
V2 失败时按这个顺序查：① 移植本身（对照官方节点）；② 参数拷贝（`gen` 返回的 `overrides.skipped`）；③ 才轮到随机性、放宽阈值。

注意区分两种"比例"：

- 份额阈值的单位是**百分点**（mesh A 占 1.2 % → 2.0 % 是 +0.8 pp），不是相对变化。
- `Ratio_Plaza_vs_Trees`、`DockRatio`、`PlazaReservationRatio` 这类比例是 **按 item 的伯努利**（`Filter_RandomChoice`
  `RandomPerDataset`：每个地块 / 区域抽一次），**不是面积比**——一块大地块抽中与否能让面积摆动 50 % 以上（trap 84）。

**V1**（`pypcg_v1_editor.py`）：对每份 `slim_<seed>.run.json` 用同样参数和 seed 重放，要求输出逐项相同；再跑
`pypcg/checks/sNN.py` 的不变量（用编辑器的真布尔）。带地形输入的阶段 `replayed` 恒为 0（trap 60），确定性改由多 seed
记录逐项相同佐证。V1 的 oracle 比的是 volume 的**当前**输出——先重新生成官方阶段再相信 oracle 失败。

---

## 7. 小镇 `/Game/PyPCG/L_PyTown`

1 km 左右的岛上小镇，用 18 张 `/Game/PyPCG/Town/PCG_*` 按 1→18 生成。布局全部在
`Content/Python/pypcg/profiles/town_layout.py`（城市轮廓、两条干道、东北角的高速对、主塔、中央公园、地形塑形），
由 `Tools/pypcg/tests/test_town_layout.py` 校验。

```
# 0. 只在第一次：从 demo 的模板副本建关卡（demo 必须是干净的；只读 demo）
run_unreal_script("pypcg_town_level.py", {"phase": "make"})
# 1. 改布局后：清理 volume、按 town_layout 重写控制样条、移动地标
run_unreal_script("pypcg_town_level.py", {"phase": "layout"})
run_unreal_script("pypcg_town_level.py", {"phase": "bind"})     # 13 个角色 -> pypcg/profiles/town_bindings.json
run_unreal_script("pypcg_town_level.py", {"phase": "save"})     # 只存 L_PyTown
# 2. 建小镇版瘦身图并挂上
run_unreal_script("pypcg_build_slim.py", {"stages": "all", "profile": "town"})
run_unreal_script("pypcg_town.py", {"phase": "assign"})         # 设图 + 组件覆写（town.COMPONENT_OVERRIDES）
run_unreal_script("pypcg_town.py", {"phase": "reset"})          # cleanup_local，并把每个 volume 的 regenerate_in_editor 关掉
# 3. 18 步，每步两次调用，中间等 60–240 s
run_unreal_script("pypcg_town.py", {"phase": "gen",  "stage": 1})
run_unreal_script("pypcg_town.py", {"phase": "read", "stage": 1, "pass": 1})   # census + 该步的验收规则
run_unreal_script("pypcg_town.py", {"phase": "shot", "stage": 1, "pass": 1})
#    ... 2..18；中途改了某步：{"phase": "reset", "from": s} 只清 s..18，再从 s 重跑
# 4. 收尾
run_unreal_script("pypcg_town.py", {"phase": "overview", "view": "top"})       # top / street / wide
run_unreal_script("pypcg_town.py", {"phase": "landed"})
#    第二遍（pass 2）同第 3 步，然后：
run_unreal_script("pypcg_town.py", {"phase": "finish"})        # 两遍比较、合理性范围、写 census（dry_run 不写）、只存 L_PyTown
#    finish 只在每个 PCG volume 都是阶段 volume、图都在 /Game/PyPCG/Town/ 下时才存；"unmeasured" 只对
#    {"allow_unmeasured": [1]} 列出的阶段放行。assign 遇到 town.COMPONENT_OVERRIDES 里的键被跳过（拼错）就失败。
C:/Python314/python.exe Tools/pypcg/town_manifest.py --out Saved/Reports/pypcg_town_manifest.json
C:/Python314/python.exe Tools/build_pcg_stage_report.py --manifest Saved/Reports/pypcg_town_manifest.json --out docs/pypcg-town-report.html
```

**为什么要关 `regenerate_in_editor`**（trap 81）：`assign` 给每个 volume `set_graph`，组件会立刻**自己**重新生成，
18 个乱序并发（实测 05:35 一次全跑），下游会读到上游半成品。`reset` 会把它关掉；关掉后只有显式的 `gen` 才生成，
保存的关卡加载时也不会自己连锁重生成（`CentralPark_Footprint` 与 `Roads` 原本带 `GENERATE_ON_LOAD`，已改为按需）。

**结果**（`Tools/data/pypcg_town_census.json`、`docs/pypcg-town-report.html`）：两遍在 `v2.same` 比较的量上相同：
18 步每种 mesh 的实例数、各 tag 的 item 数、面积与长度合计（不比位置与包围盒），共 **545 666** 个实例；保存后重开关卡，每个 volume 与两遍一致。

| 步 | 实例 | 说明 |
|---|---|---|
| 1 Terrain | 0 | 城心起伏 1 630 cm（修正后的上限 4 413，T27b），外圈起伏 5 102 cm；9 个采样点两遍逐位相同 |
| 2 BG_Buildings | 373 | |
| 3 BG_Mountains | 59 | |
| 4 / 5 / 6 | 0 | 数据步；6 出 50 个 item：Small 4 / Medium 2 / Large 2 个区 |
| 7 Roads | 127 631 | 路口 89 片 / 116 216 m²（T27g 修复后） |
| 8 Highways | 15 999 | T27f 包围盒 |
| 9 Lots | 3 110 | 471 个 item |
| 10 Ground | 76 017 | |
| 11 Buildings | 164 244 | 215 栋；TL 404 个实例 / 21 种 mesh（T27i） |
| 12 Rooftops | 12 453 | |
| 13 LeftOverLots | 17 242 | 外围树林 0（trap 66） |
| 14 Parkings | 8 370 | 2 块停车场、460 个车位、355 辆车 |
| 15 MainTower_Visuals | 11 710 | 天线 0 点（塔顶 18.8 m² < 1 000 m² 门槛） |
| 16 CentralPark_Visuals | 85 324 | 湖由 `SimpleWriteModifier` 写入 |
| 17 CityEdge | 23 134 | 29 个码头 |
| 18 OuterForest | 0 | trap 66，按 T27a 预期为 0 |

合理性（spec §5.2）：每 km² 建筑 261.0（官方 186.4，1.40×），每 km² 道路 18 803 m（官方 15 604，1.21×），都在 [0.5×, 2×] 内。
最大的文件是 Roads volume 45.9 MB，没有文件超过 95 MB，`.gitignore` 未改；地形写入存在各 volume 的
`SimpleWriteModifier` 里，并不存在预估的 ~1 GB mesh-partition 文件。

小镇特有的几点：

- **区的分档阈值为小镇重调（T27h）**：demo 的阈值是给大得多的城市定的，小镇 8 个区（7.8–14.0 ha）全落在 Small，
  于是没有 Medium / Large 建筑、也就没有 TL。`town.COMPONENT_OVERRIDES["PCG_3_1_1_Districts"]` 设
  `SmallMediumThreshold = 95 000`、`MediumLargeThreshold = 120 000`（m²），得到 4 / 2 / 2。
- **阶段 11 的 TL 规则是有条件的（T27i）**：TL 只在 Medium 样式列表里、按随机抽，只有发布了 `MediumRooftops` 时才要求出现 TL。
- **阶段 18 放 0 棵树**：官方图读 `/Game/Textures/Noise/T_CloudNoise_4k`，本项目没有这张贴图，整条链静默产出 0（trap 66）；
  阶段 13 的外围树林同理。官方 demo 上也是 0，这是预期，不是回归。
- **停车场出现在 LeftOverLots 保留的地块上**：`ParkingFootprint` 角色就是 LeftOverLots 的 volume，阶段 14 消费阶段 13
  发布的保留地块；`town_layout.parking_rect()` 只是名义上的 70×45 m，不被摆放。阶段 13 没发布任何地块时，0 个停车场才算正常。
- **阶段 8 的包围盒（T27f）**：小镇的高速对故意越过城市两次（x -25 000..90 000），所以阶段 8 的包围盒 = 城市框 ∪ 两条高速样条
  自身的范围，再各加 200 m。这条规则原本防的是"读到 demo 整座城"（约 -120 000..140 000），仍然有效。
- **阶段 7 的路口修复（T27g）**：小镇的城市轮廓是闭合环，道路带是"带洞的环"，以前只有外环进了路口求解，整个城盘被算成一个 70 ha
  路口；`geo.sections` 已修，demo 上不受影响。
- 阶段 11 日志里有 137 条 `Debug` / `Partitioned` 参数包错误：保留的原生节点读被丢弃的参数（N5），回退到默认值，产出完整；demo 的瘦身图同样。

---

## 8. C++ 插件 `PyPCGTools`（13 个函数）

`Plugins/PyPCGTools/Source/PyPCGTools/Public/PyPCGToolsLibrary.h`，Editor 模块。Python 里是 `unreal.PyPCGToolsLibrary.<snake_case>`。
写操作成功返回空串、失败返回错误信息；拒绝写 `/CitySamplePCG/`、`/PCGPrimitives*`、`/Engine/` 下的资产（关卡里的 actor / 组件除外）。

| 函数 | 一句话 |
|---|---|
| `ExportGraphIR(Graph)` | 整张图导出成 IR JSON（schema 1）：`Tools/pypcg/official_ir/` 快照和结构核对都靠它 |
| `ExportInstanceOverrides(Instance)` | 一个图实例上标记为覆写的参数 `{名字: 值}` |
| `SetPropertiesJson(Object, Json)` | 按 JSON 写属性（含 protected 的），`"$text:<t>"` 按 UE 文本导入 |
| `SetInstanceParameter(Instance, Name, ValueJson)` | 设图实例的一个参数并标记为覆写 |
| `SetPinDefaultValue(Settings, PinIndex, Type, ValueJson, bHasValue, bActivated)` | 输入 pin 的内联默认值 |
| `SetGraphUserParameters(Graph, Json)` | 整体替换图的用户参数（含 tooltip），并重建分类 |
| `BindUserParameterGetter(Getter, ParamName)` | 把一个 Get Graph Parameter 节点绑到图参数上并刷新 pin |
| `SetNodeComment(Node, Comment, bBubbleVisible, bBubblePinned)` | 节点注释 |
| `SetGraphCommentBoxes(Graph, Json)` | 整体替换图的注释框 |
| `MakePolygon2DData(Json)` | 按 `CreatePolygon2D` 的方式建 `UPCGPolygon2DData`（外环 CCW、洞 CW、框架在外环质心）；坏输入返回 null |
| `Polygon2DToJson(Data)` | 多边形读回世界坐标 `{"outer", "holes"}` |
| `SplineDataToJson(Data, MaxSquareDistance)` | 样条读回：闭合标志、折线、控制点（不含控制点旋转，trap 63） |
| `SetDynamicPinLabels(Settings, Inputs, Outputs)` | 给 Python Data Processor 设动态输入 / 输出 pin（只用于新节点，已连线时拒绝） |

自动化测试 9 个，在 `Plugins/PyPCGTools/Source/PyPCGTools/Private/Tests/`：

```powershell
& "E:\UnrealEngine\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "E:\PCG_Claude\PCG_Claude.uproject" -ExecCmds="Automation RunTests PyPCGTools; Quit" -unattended -nopause -nosplash -nullrhi -log
```

**改插件要重编译，重编译要先关掉两个编辑器**（本项目的和 `E:\PCG_Codex` 的，都锁 UBT）：

```powershell
& "E:\UnrealEngine\Engine\Build\BatchFiles\Build.bat" PCG_ClaudeEditor Win64 Development -Project="E:\PCG_Claude\PCG_Claude.uproject" -WaitMutex
```

---

## 9. 哪些留在原生，为什么

目标是"大量计算进 Python，只留参数、场景读取和引擎生成"（spec E1–E5）。下面这些计算**按实测或裁决留在原生节点里**：

| 留原生的 | 理由 | 出处 |
|---|---|---|
| 阶段 1 的模糊（`SpatialNoise_Hills` 里的 `BlurElement_1`） | 实测每点 852 µs（1 261 个邻点）→ 两轮 **445 s**；求和顺序是八叉树的，复现不了 | `s01.md` §0，`Tools/pypcg/data/s01_native_measurements.json` |
| 阶段 1 的 GPU 投影（`FlattenProject_AroundCircle`、`Subgraph_5` 的 `Transform_Project`） | 最近目标搜索在 GPU 上（float32），仅搜索就 138 µs/点 → 两次 **72 s**，且末位复现不了（trap 76）。Python 只算掩码与混合，写回的 261 312 个高度与官方逐位相同 | `s01.md`，`s01_tap_comparison.json` |
| 阶段 7 的地形一半（两个 `Write_MeshTerrain` 与压平） | Task 10c 留下；链路已接（Python 出 `IntersectionsPlanar`，原生写地形），但 V2 看不见（`ModifiedTerrain` 无面积无点），**未验证** | `s07.md` §8，`task-10b-report.md` §7 |
| 阶段 9 / 10 / 16 的语法后点链（投影器、道具 roll/pitch 修正、透明车辆复制、gather） | 裁决 T17a：作用在语法**生成的**点上，要搬进 Python 得给每个语法节点后面再挂一个 Python 节点并往返整套属性；阶段 10 有 19 个、阶段 16 同链 | `s10.md` §2.5，`s16.md` §3.3 |
| 阶段 16 的草地：投影器 + 选资产（6 个节点） | Step F：约 210 万填充点、~500 万次地形查询，估计 70 s 以上 > 60 s | 裁决 T22b，`s16.md` §3.2 |
| 阶段 16 的草地：填充 / 噪声 / 密度过滤（9 个节点） | **范围裁剪**（裁决 T22c），不是 Step F：用扫描线填充估计 25–30 s 能进 Python，但没做 | `s16.md` §3.2 |
| 贴图读取（阶段 11、13、18 的 `Write_Attribute_fromTexture`） | 纯 Python 读不到贴图像素（spec §4.3） | `s11.md` §4.1，`s13.md`，`s18.md` |
| `@data` 读写适配器（阶段 10 的 2 个、阶段 11 的 3 + 8 个 `ExtractAttribute` / `CopyAttributes`、阶段 18 的 2 个） | 本引擎版本里 Python 节点读写不了 data 域属性（`PCGMetadataDomainHandle` 无 Python 读法，`*OnDomain` 不可调，已探测） | `s10.md` §2.5，`s11.md` §4.2 |
| 所有引擎生成节点（Shape Grammar、BDF、`Assign_CitySampleBuildings`、Fitting、Spawner、`Create_Mesh`、`Write_MeshTerrain`、Crosswalks） | 设计就保留（spec E3），Python 只算它们的输入 | spec §2.1 |

---

## 10. 逐步结果

V2 = demo 关卡上与官方对照（5 个 seed 的中位数，`docs/pypcg/v2/sNN.md`）；V1 = 重放 + 不变量（`pypcg_v1_editor.py`）。

| 步 | V2 | V1 |
|---|---|---|
| 1 Terrain | pass（只有一个 surface item，V2 近乎空检；实证是 261 312 个写回高度、1 045 248 个 tap 位置与官方逐位相同） | 1 次运行，replayed 0（surface），确定，0 失败 |
| 2 BG_Buildings | pass：373 对 394（-5.3 %，限 25 %），份额在 5 pp 内 | 确定，0 失败 |
| 3 BG_Mountains | pass：59 = 59，位置逐位相同 | 确定，0 失败 |
| 4 MainTower_Footprint | pass：顶点与官方逐位相同 | replayed 5，确定，0 失败 |
| 5 CentralPark_Footprint | pass：角点逐位相同（用 actor 自存的四元数） | replayed 5，确定，0 失败 |
| 6 Districts | pass（长度、包围盒两行放宽，见阈值文档） | replayed 5，确定，0 失败 |
| 7 Roads | **FAIL 一行**：实例 275 523 对 286 361（-3.8 %，确定性步骤限 1 %），根因是 local 类路段切分粒度（上游 `Gather_0` / 地标裁切，未定位）；另有官方自身不可复现（trap 58） | replayed 5，确定，0 失败 |
| 8 Highways | pass：面积 +0.30 %、实例 +0.25 % | replayed 0（surface），五份记录逐项相同 |
| 9 Lots | pass（按 tag 放宽的随机性行，见阈值文档）；oracle 复现官方保留抽样后 Lots 等多个 tag 精确相等 | replayed 5，确定，0 失败 |
| 10 Ground | pass：+0.15 %，53 种非地砖 mesh 逐 mesh 等于官方 | replayed 0，确定，0 失败 |
| 11 Buildings | pass：屋顶数每个 seed 都等于官方，实例 -0.27 %；阶段 12 下游逐 mesh 相同 | replayed 0，确定，0 失败 |
| 12 Rooftops | pass：5 个 seed 都是 27 661，46 种 mesh 逐 mesh 等于官方 | replayed 5，确定，0 失败 |
| 13 LeftOverLots | pass（个数 0.60 / 面积 0.75 / 包围盒 300 m 的放宽行，199 个 seed 的研究支撑） | replayed 0，确定，0 失败 |
| 14 Parkings | pass：地砖、线、箭头、围栏逐 mesh 等于官方，路障 558 对 557 | replayed 5，确定，0 失败 |
| 15 MainTower_Visuals | pass：35 276 对 35 239（+0.105 %） | 部分重放，0 失败 |
| 16 CentralPark_Visuals | pass：+15.5 %（实例阈值 0.35，官方自己跨 seed 就有 -4.4..+26.1 %）；119 种非植被 mesh 逐 mesh 相等 | replayed 0，确定，0 失败 |
| 17 CityEdge | pass：+15.4 %（官方这个 seed 的码头抽得偏少，-1.2 sd）；`Assign_Assets` 逐点精确 | replayed 0，确定，0 失败 |
| 18 OuterForest | pass 但近乎空检（0 对 0，trap 66）；用替换贴图的 oracle：34 711 对 34 659（+0.15 %），每种 mesh 份额在 2 pp 内 | 0 失败，部分重放复现每个撒点集 |

V3（小镇）见 §7：18 步全过，两遍在 `v2.same` 比较的量上相同（每种 mesh 的实例数、tag 个数、面积与长度合计；不比位置）。阶段 7 的 FAIL 与小镇阶段 18 的 0 棵树尚未经用户裁决接受，见 §11 末行。

---

## 11. 本计划的裁决（ledger 是临时工作区，这里留底）

| 裁决 | 内容 |
|---|---|
| N1 | 阶段签名 `run(inputs, params, ctx)`；`ctx.rng`、`ctx.ops` |
| N2 | GeometryScript 布尔注入为 `ctx.ops`；离线用 `FakeOps` |
| N3 | V2 忽略含 `:` 的 tag |
| N4 | Python 节点用两行内联脚本，不用 `ScriptPath` |
| N5 | 各图种子参数并入 `Seed`；`Debug*`、`Partitioned`、`PartitionGridSize` 及无用参数丢弃 |
| N6 | 阶段移植任务给契约 + 测试 + 协议，算法在各自 Step A 写 |
| N7 | `PCGPythonInterop` 编进引擎目录前给用户看清单（用户 2026-10-16 批准 268 项，P1） |
| N8 | `Assign_Assets` 进 Python（`pypcg.geo.assets`），已对 8 组官方调用逐点精确核对（`Tools/pypcg/data/assign_oracle_rows.json`） |
| N9 | 阶段 0 是探针，不在 18 张之内 |
| N10 | 官方 item < 5 的 tag 不比个数和面积 |
| T7c | V2 只比契约 tag |
| T9a–T9d | 阶段 6 的放宽以 V1 oracle 为放置证据；种子研究入库；V2 缺 tag 规则没有稀有度豁免（150 个 seed 里 8 个丢 `UndividableDistricts`，潜在偶发失败，未修） |
| T10c | 阶段 7 地形一半另立（未做） |
| T13a | 阶段 4 下游 -0.66 % 是末位差异，不是噪声 → 逐位复现 |
| T15a | `Assign_Assets` 的各设置对活的官方原语实测，不靠推导 |
| T17a | 语法后点链留原生，记为偏差 |
| T17b | `in_frame` 排除实验没达到 107 块，不采用，限制记录在案 |
| T20a | 碰撞流在丢弃 `Partitioned` 时恒为空（否则会写进 `/CitySamplePCG/Levels/Collision`）；三份框架实现的合并推迟 |
| T22a | `MakePolygon2DData` 的框架修复推迟（要关编辑器编译） |
| T22b / T22c | 草地：投影 + 选资产按 Step F 留原生；填充 / 噪声 / 过滤为范围裁剪 |
| T27a–T27i | 小镇验收：阶段 18 接受 0 棵树；阶段 1 用修正后的起伏上限；`_trace_z` 用 `hit.to_tuple()`；湖组件类取自官方 census；阶段 8 包围盒并上高速范围；阶段 7 路口 bug 修复；区分档阈值重调；TL 规则有条件 |
| T28a–T28c | 第二遍用 `v2.same` 逐 mesh 比较（原生步骤 7/10/11 的已知波动带）；第二遍前关 `regenerate_in_editor`；>95 MB 文件按路径忽略（实际没有） |
| U1（用户 2026-10-21） | 两条 spec 成功标准未达成，用户接受合并、留作后续（spec 成功标准下的"已知偏差"）：阶段 7 V2 FAIL，实例 -3.8 % 对 1 % 上限，根因是 local 类路段切分粒度（§12 第 5 条）；小镇阶段 18 放 0 棵树，因为项目里没有 `/Game/Textures/Noise/T_CloudNoise_4k`（trap 66，§12 第 10 条） |

---

## 12. 已知限制 / 后续工作

**平台限制**

- Python Data Processor 节点**只在编辑器里**运行、在主线程、**不缓存**；`PCGPythonInterop` 是 **Beta**。打包游戏里不能重新生成，
  小镇靠保存进关卡的结果（spec E4）。
- 生成的 actor 文件超过 100 MB 不入库（GitHub 限制），靠确定性重生成；当前最大 45.9 MB。
- 逐节点草稿（旧方案"图即代码"的 18 个文件）在 `Tools/pypcg/reference_drafts/`，只备查；`test_stages_l1.py` 的 18 个 skip 就是它们。
- 退役的逐节点资产 `/Game/PyPCG/Official/`（18 个）仍在库里，spec §4.1 计划删除，尚未删除。

**后续工作（ledger 的 carry 清单）**

1. **`MakePolygon2DData` 的可选框架**：Python 新造的多边形框架以自身质心为原点，官方的继承来源多边形的框架（trap 68）。
   阶段 15 屋顶通风 / 组合件因此净多 57 个。要在 `PyPCGTools` 里加可选框架参数并让 `Spline.frame` 也带过去（T22a；需关两个编辑器重编译）。
2. **合并三份 `CreatePolygon2D` 框架实现**（`geo.areas.in_frame`、`ops.cut_with_paths`、`geo.frames.polygon_frame`，末位不一致），
   之后要重新验证阶段 9 / 10 / 13 / 14（T20a）。
3. **`port_brief.py` 的下游检测只看 tag**，看不到 `ActorReferences` 角色：`s14-brief.md` 写"无下游"，实际阶段 16 读 Roads / Parkings 角色；
   `DOWNSTREAM[1] = [7, 10, 18]` 列的是无人使用的读取，真正读地形的是 7、8、10、11、13–18（`Get_MeshTerrain`）。
4. **`port_brief.py` 把原语子图算 1 个节点**，"计入 Python"的数字因此偏低于真实计算量（Roads 的 `Intersection_solving` 170 个节点等）。
5. **阶段 7 的地形一半（Task 10c）与 V2 的 -3.8 % 一行**：local 类路段个数 -9.2 %、长度 -5.2 %，collector / artery 个数偏多；
   oracle 的 local 总长比移植的整份输入还多 1 274 m，指向 `Gather_0` 或地标裁切（`s07.md` §6.2、§9.2、§10）。
   这条 FAIL 没有裁决接受，见 §11 末行。小镇路口面积曾比官方在小镇输入上的结果多 32 %（154 054 对 116 358 m²），
   但那是 T27h 之前的布局；最终布局是 89 片 / 116 216 m²（task-27 报告），官方没有在最终布局上重新探测，差距未知。
6. **阶段 13 的 density-0 与 steepness**：差集不丢 density 0 的源点，tile 6 元组假定 steepness 1（引擎默认 0.5）。demo 上 0 影响（515 = 515），
   小镇地形上可能不同；要一次阶段 13 的编辑器实测，绿色的 V1 证明不了（trap 60）。
7. **`convert` 的 Quat / Transform 属性写入器丢精度**（`unreal.Quat(*q)` 舍成 float32，trap 73）；目前没有阶段受影响。
8. **`Subgraph_56` 的决定性测试**：阶段 15 CHJ 少 20 面墙（官方第三圈在 80 m 臂上收缩 1.5 m 时留下一个没动的顶点，521.0 对 498.87 m²）；
   假设是 Clipper2 凹角连接残点，需要一张 1e-6° 探针图验证。
9. **阶段 16 草地的填充 / 噪声 / 过滤**（9 个节点，范围裁剪 T22c）：扫描线填充估计 25–30 s；投影器 + 选资产（6 个节点）的 ~70 s 也只是估计，
   援引 Step F 之前要先实测计时（T22b）。
10. **补上 `T_CloudNoise_4k`**：否则阶段 13 / 18 在任何关卡（含小镇）都不放外围树（trap 66）。只在 oracle / tap 图里换贴图，别改出货图。
    小镇阶段 18 因此放 0 棵树，没有裁决接受，见 §11 末行。
11. **同一阶段两个 Python 节点共用 `Seed:NN` 随机流**（阶段 11 的 `s11_buildings` / `s11_buildings_rooftops`、阶段 13、阶段 18；
    `stage_api.Ctx` 只用 `"%d:%d" % (seed, stage)` 播种，同阶段的节点拿到同一条流）：应按节点加盐（例如模块名）。加盐会改变产出、要重做 V2，所以没改。
12. **`@data` 读写**：给 `PyPCGTools` 加读写 data 域属性的包装，就能去掉阶段 10 / 11 / 18 的适配器；语法后点链（T17a）要搬进 Python 则需
    `more_modules` 往返语法点的全部属性。
13. **V2 缺 tag 规则没有稀有度豁免**（T9d）：阶段 6 有 8 / 150 个 seed 不出 `UndividableDistricts`；协议的 5 个 seed 都有，所以没触发。
14. **阶段 11 的 137 条参数包错误**：保留的原生节点读被丢弃的 `Debug` / `Partitioned`；产出完整，若复杂建筑外形要紧值得一看。
15. 本计划推迟的小项（不影响结果）：`to_point_data()` 已弃用（仍可用，trap 56）；host 的 `PYPCG_RECORD` 把 `"0"` 也当开启；
    `stage_api.record()` 信任调用方带 Seed；`read_params` 的"第一个非 None"其实是"第一个 data item"（trap 36）；`extract._default_seed`
    每次导出都记一条类加载失败；`test_slim_dsl` 有几条断言不会失败；`plane.xy` / `plane.drop_closing` 无直接测试；`MakePolygon2DData`
    的平面 / 质心只用外环（有洞时 `$LocalPosition` 不同，世界几何相同）。
16. **`geo.plane.clip_path` 给切点用路径首顶点的 z**，不插值：z 变化的 3D 路径上切点高度不对；没在坡上样条上对照引擎的 `ClipPaths`（final review M5）。

## 13. 单图版：一张 PCG 图生成整座小镇（`/Game/PyPCG/City/PCG_PyCity`）

把 18 张瘦身图合成**一张** PCG 图，挂在**一个** PCG volume 上一次生成整座小镇。核心业务逻辑仍全部在 Python 里（32 个 Python 节点
运行 `pypcg/stages/` 下的模块，和 18 卷版是同一份代码）；配置和控制区域都还是传统方式。

| | 位置 |
|---|---|
| 合并图 | `/Game/PyPCG/City/PCG_PyCity`（473 个节点、82 个参数；`pypcg/combined.py` 描述，结构核对 0 diff） |
| 关卡 | `/Game/PyPCG/L_PyCity`（L_PyTown 的模板副本，只留 1 个 volume `PCG_PyCity` + 控制 actor） |
| 驱动 | `Content/Python/pypcg_city.py`（`build` / `make` / `layout` / `bind` / `assign` / `reset` / `gen` / `read` / `overview` / `save`） |
| 绑定 | `pypcg/profiles/city.py`、`city_bindings.json` |
| 测试 | `Tools/pypcg/tests/test_combined.py`（离线） |

**配置（传统方式，可手调）。** 每个阶段的参数都是合并图的用户参数，改名为 `SNN_<原名>`（如 `S06_SmallMediumThreshold`、`S07_local_Width`），
在 Details 面板按 `NN <阶段>` 分类（`06 Districts`、`07 Roads|Road Parameters` ……）。选中 `PCG_PyCity`，在 PCG 组件的 graph instance
里勾选覆盖、改值、点 Generate 即可，和改官方图的覆盖一样。每个 Python 节点只接自己阶段的参数，host 读参数时去掉 `SNN_` 前缀
（`stage_api.unprefixed`；收到别的阶段的参数会报错）。

**控制区域（传统方式）。** 全是关卡里的 actor，照旧按 tag 或引用读取：
- tag：`City`（城市外轮廓）、`Arteries`、`Terrain_shaping_1`、`HighRise`、`USER_SPLINE`、`LAKE`、`FOREST_EXCLUSION`；
- `LandmarkPark`（主塔小公园样条 `MainTowerPark`）、`Highway`（高速样条 `HighWay_2` / `HighWay_3`）：官方图对这三个用 actor 引用，
  合并图改成按 tag 读（`combined.ROLE_TAGS`）——actor 引用写死某个关卡里的 actor，换个关卡就读空；按 tag 读，合并图在任何带这些 tag 的关卡里都能用；
- 主塔、中央公园的位置与朝向：原来的两个 footprint volume 留在关卡里当**控制 actor**（不再挂图），按 tag
  `PyCity_MainTowerFootprint` / `PyCity_CentralParkFootprint` 读；挪动、旋转它们就是挪主塔 / 公园。尺寸仍是参数（`S04_RectWidth` 等）。

**合并时改了什么（只有这四类）。**
1. 读**另一个阶段 volume 输出**的 `Get_ActorDataByRef`（31 个）换成 **Gather**，接上游阶段送进 Output 的那些边。tag 随数据走，
   下游的 tag 过滤原样不动。（不能用 Reroute：PCG 的 Reroute 输入只收一条边。）
2. 阶段 4 / 5 的"读自身 volume"改成按 tag 读上面的控制 actor（`combined.CONTROL_TAGS`）。
3. **地形是共享资源**：18 卷版靠"按阶段顺序生成"保证读写次序，单图里没有阶段顺序、只有数据边。所以每个阶段的 `Get_MeshTerrain`
   都用 `Execution Dependency` 等前面所有阶段的 `Write_MeshTerrain`，每个写入也等前面所有阶段的读取——每次读到的地形与 18 卷版相同。
4. 读控制样条的 3 处 actor 引用（阶段 8、9、10、13 共 4 个节点）改成按 tag 读（见上）。在 L_PyCity 上实测与引用版逐网格相同。

**流程**（一次一个 phase；长 phase 用 `{"defer": true}`，结果写到 `Saved/Reports/pypcg_city_deferred.json`）：

```
pypcg_city.py {"phase": "build", "defer": true}     # 描述 → 资产，0 diff 才保存
pypcg_city.py {"phase": "make"}                      # 新建 / 打开 L_PyCity
pypcg_city.py {"phase": "layout", "defer": true}     # 删 15 个阶段 volume，留 PCG_PyCity + 2 个控制 actor
pypcg_city.py {"phase": "assign"}                    # 挂图 + 小镇的覆盖（改名后）；每次 build 之后都要重做（trap 91）
pypcg_city.py {"phase": "reset"} / {"phase": "gen", "pass": 1}   # 生成约 10–17 分钟
pypcg_city.py {"phase": "read", "pass": 1, "defer": true}        # 逐网格对照 18 卷小镇
pypcg_city.py {"phase": "save"}                      # 只存 L_PyCity，且只在唯一的图是合并图时
```

**结果（2026-10-22）。** 32 个 Python 节点全部运行；**545 671** 个实例、1 270 种网格（18 卷小镇 545 666、1 270 种）；两遍逐网格完全相同。
与小镇不同的只有阶段 12 的 8 种屋顶小件、合计 15 个实例：阶段 11 / 12 的 Python 产出逐条相同，差在原生的屋顶填充节点——
单图里它们的输入多边形直接来自阶段 11 的节点，而不是经 `Get_ActorDataByRef` 从 volume 输出读回。差异稳定、可复现。

**关卡里不存生成结果。** 生成后整座小镇都在一个 actor 里（149 MB），超过 GitHub 的 100 MB 单文件上限；所以 `L_PyCity` 存的是 cleanup 后的状态
（这个 actor 30 KB），打开后 Generate（或 `gen`）即可重建，结果确定。注意 `cleanup_local` 之后立刻保存仍会把旧组件写进包（trap 86），
`save` 因此先 `modify()` 一下 volume。

**重建图会清掉组件上的覆盖（trap 91）。** `build` 重写 `PCG_PyCity` 资产后，volume 的 graph instance 覆盖全部回到图的默认值
（实测：地形比例 0.5 代替 0.4，阶段 9 只出 11 个而不是 479 个）。所以 build 之后先 `assign` 再生成；`gen` 会检查 profile 的覆盖
是否都在，不在就拒绝。`save` 也会拒绝在生成组件还没清掉时保存（清理要过几帧才完成）。

### 13.1 小区域 `/Game/PyPCG/L_PyCitySmall`

同一张 `PCG_PyCity`，换一个关卡、换控制区域和覆盖，不改图——这正是"配置和控制区域用传统方式"的意思。

| | |
|---|---|
| 关卡 | `/Game/PyPCG/L_PyCitySmall`（`L_PyCity` 的模板副本） |
| 控制布局 | `pypcg/profiles/small_layout.py`：约 560 × 440 m 的城市轮廓、两条干道切成四块、东北角一对高速、东北区主塔 + 高层区 + 小公园、西南区中央公园（湖、两条小径、林地排除区） |
| 覆盖 | `pypcg/profiles/small.py`：主塔 110 m（`S04_RectWidth/Length` 11000）、公园 120 × 50 m（`S05_*` 12000 / 5000）、`S06_Dividable_district_Limit` 20000、`S06_SmallMediumThreshold` 24000、`S06_MediumLargeThreshold` 30000 |
| 测试 | `Tools/pypcg/tests/test_small_layout.py`（地标在城内、离干道 / 水边够远，tag 覆盖合并图读的每个 tag） |

```
pypcg_city.py {"phase": "make",   "profile": "small"}    # 复制 L_PyCity
pypcg_city.py {"phase": "layout", "profile": "small"}    # 写控制样条、挪主塔 / 公园控制 actor、核对 tag
pypcg_city.py {"phase": "assign", "profile": "small"}
pypcg_city.py {"phase": "reset",  "profile": "small"} / {"phase": "gen", "pass": 1, "profile": "small"}   # 约 4–5 分钟
pypcg_city.py {"phase": "read",   "pass": 1, "profile": "small", "defer": true}
```

**分区阈值按面积定。** 阶段 6 在这个布局上切出 8 个街区：20 116、21 567、22 098、22 426、25 438、26 239、35 043、35 586 m²。
小镇的 95 000 / 120 000 会让它们全是 Small（第一次实测：55 栋全是 Small）；24 000 / 30 000 得到和小镇一样的 4 Small / 2 Medium / 2 Large。
主塔用 80 m 时阶段 15 只建出底层（没有 CHJ 环、没有上两层），所以保留小镇的 110 m。

**结果（2026-10-22）。** 162 574 个实例、1 027 种网格；23 Small / 15 Medium / 6 Large 栋建筑，1 个停车场（120 个车位、93 辆车），
三层主塔，中央公园、21 个码头、高速。外围林地仍是 0（`T_CloudNoise_4k`，trap 66）。两遍逐网格相同。
生成结果**存进了关卡**（`save` 加 `{"keep_generated": true}`）：那个 actor 85.4 MB，在 GitHub 的 100 MB 上限以内，打开就能看；
整座小镇的 149 MB 超限，所以 `L_PyCity` 只存清理后的状态。
