# 植被生态群落（W7）

## 思路

不是"按遮罩随机撒"。先在地形顶点格上算**生态场**，每个样本归入一个**群落**，再**分层放置**：每层有自己的接受率、物种配比和间距规则。
这样林内、林缘、草甸、河岸、山地、岩坡、村边各有各的样子；河岸的桤木占比约 0.6，全图只有 0.04。

## 生态场（`world/ecology.py` 的 `Fields`，每个顶点算一次）

| 场 | 含义 |
|---|---|
| `slope` | 坡度（度） |
| `rel` | 离局部谷底的高度（`hydro.min_filter`，100 格窗口） |
| `acc` | D8 汇流量（`hydro.flow_accumulation`） |
| `riv` `line` `ring` `bld` | 到河、到路街、到足迹 / 广场 / 农田（11 m 内）、到建筑中心的距离 |
| `sun` | 阴阳坡：朝 +X 的坡算阴面 |
| `moist` | 湿度：离河近、汇流大、位置低、阴坡 |
| `forest` | 森林潜势：按离谷底高度分段，再计入坡度和湿度；聚落周边 30–120 m 压低（牧场）；加两层 fbm 噪声做出曲折的林缘；最后 smoothstep(0.36, 0.70) |

**群落**（`_community`，从上往下第一个满足的）：

| 群落 | 条件 |
|---|---|
| rock | 坡度 ≥ 42° |
| riparian | 离河 < 25 m 且坡度 < 22°，或汇流 ≥ 300 且坡度 < 25° |
| montane | 离谷底 ≥ 190 m 且 forest < 0.75 |
| forest | forest ≥ 0.75 |
| edge | forest ≥ 0.15 |
| village | 离建筑中心 < 35 m |
| meadow | 其余 |

要改群落边界，就改 `Fields._community`、`_forest`、`_moisture`。

## 物种表（`world/flora.py` 的 `SPECIES`，48 种）

每个物种的字段：

| 字段 | 含义 |
|---|---|
| `meshes` | 一组网格路径，放置时随机选一个 |
| `layer` | `tree` / `shrub` / `grass` / `ground` / `debris` / `rock` |
| `scale` | 缩放范围 |
| `sink` | 下沉量（cm）；岩石是网格高度的比例，高度要登记在 `_SIZES` 里 |
| `align` | 0 = 直立，1 = 贴坡 |
| `space` | 乔木、灌木的间距半径（cm，按冠幅） |
| `clump` `spread` | 地被成丛：每丛株数范围、散布半径 |

路径用这几个辅助函数生成：`plants()`（ED 的 `Megascans/3D_Plants`）、`assets()`（ED 的 `3D_Assets`）、`megaplant()`（Megaplants 的夏季副本）、`hornbeam()`。

## 配比与接受率（`ecology.py`）

| 表 | 内容 |
|---|---|
| `TREE_MIX` | 各群落的乔木配比；另有 `forest_moist`、`young`、`hedge` |
| `SHRUB_MIX` | 各群落的灌木配比 |
| `GROUND_BASE` | 没有花斑块时的地被 |
| `PATCHES` | 花 / 草本斑块：噪声尺度、阈值、各群落的适宜度 |
| `CARPET` `CARPET_MIX` | 1.3 m 一格的草毯：各群落的概率和物种 |
| `GROUND_ACCEPT` `ROCK_ACCEPT` `DEBRIS_ACCEPT` | 各群落的接受率 |

**乔木和灌木各群落"种不种"的概率不在表里，写死在 `grow.py`**：

| 层 | 函数 | 各群落的概率 |
|---|---|---|
| 乔木 | `Grower.canopy` | forest 0.9；edge 0.1 + 0.35·forest；riparian 按噪声带 0.12–0.67；montane 0.05 + 0.5·forest；meadow 0.0025，树丛处更高；village 0.012；rock 0.03 |
| 灌木 | `Grower.understory` | edge 0.55·edgeness；forest 0.12（树下 0.015）；riparian 0.22；village 0.025；montane 0.05 |

要改"种多密"，先看这两个函数。

## 分层放置（`world/grow.py` 的 `Grower`，按 `w07_vegetation.run` 的顺序）

1. `rocks`：成簇，一块主石 + 卫星石 + 碎石。
2. `canopy`：乔木。概率按群落；冠幅间距用 `Spacing`；大树记为 mature。
3. `understory`：灌木。林缘按 edgeness，另放林窗、河岸、草甸树丛。
4. `hedgerows`：农田、菜园周边，开阔地的路两侧。
5. `tree_floor`：大树下的根、落叶、常春藤。
6. `debris`：倒木（顺坡横放）、树桩、枝、细枝。
7. `river_banks`：河岸卵石和石头。
8. `ground`：地被。先看花斑块，否则用 `GROUND_BASE`；细节区（`DetailHalf`）外更稀。
9. `carpet`：草毯。

- `clear(x, y, k, 离路距离, 离河距离, 离区域距离)`：每层自己的避让距离（路街、河、足迹 / 广场 / 农田 / 桥）。W10 会查树有没有侵入这些地方。
- `put()`：高度用 `lat.surface`（三角面），朝向按 `align` 贴坡，再下沉 `sink`。
- PARAMS：`Density`、`ShrubDensity`、`GroundDensity`、`GrassDensity`（草丛保留比例 0..1）、`RockDensity`、`DebrisDensity`、`Extent`（种植区半边长 1.35 km）、`DetailHalf`（全细节区半边长 1 km）。
  用 `assign {"overrides": {"7": {"Density": 1.3}}}` 覆写，不用改代码。

## 生成与性能（`graphs.build_w07`）

- 6 个原生 Static Mesh Spawner，按 `Mesh` 属性选网格。剔除距离：
  - 灌木 400 m、草 120 m、地被 90 m（地被不投影）、倒木 200 m；
  - 乔木和岩石不剔除。
- **不要用 `Spawn_Assets`**：140 万个点会和垃圾回收竞争，崩编辑器（trap 99，同 trap 61）。
- `gen` 期间驱动关掉自动保存、拉长 GC 间隔，`read` 再恢复。
- 规模：约 275 万实例（乔木 7.4 万），Python 75–120 s，编辑器约 24 GB。W7 的输出 actor 单个文件约 361 MB，超过 GitHub 的 100 MB 上限，
  所以仓库里的关卡不带生成结果（见 SKILL.md 改动流程第 6 步）。

## 资产

- **Electric Dreams**（`E:\ElectricDreams\ElectricDreamsEnv`）用 `Tools/pyworld/ed_closure.py` 拷：
  1. 把目录名加进 `PLANTS` / `ASSETS` / `SURFACES`；
  2. 不带参数跑一次：列出依赖闭包、大小，以及和本项目已有文件字节不同的冲突；
  3. 没有冲突再 `--copy`；
  4. 拷完对 `/Game` 做一次资产注册扫描，或重启编辑器；
  5. 新带进来的 ED 母材质跑 `pyworld_fix_aniso.py`（先 `{"dry": true}`），否则第一次画就崩（trap 98）；改过的母材质加进 `PATCHED`。
- **Megaplants**（City Sample 的山毛榉、桤木、榛、山杨、挪威槭）：
  - 它们是 Nanite 装配体，叶子是体素植被，必须开 `r.Nanite.Foliage=1`。这个 cvar 只读，要写在 `Config/DefaultEngine.ini` 的 `[ConsoleVariables]` 里，改后重启并重编 shader（trap 97）。
  - 原版是秋季色。`pyworld_megaplant_summer.py` 生成 `/Game/PyPCG/World/Trees/` 的夏季副本：装配体部件的材质映射到根网格的槽位，所以换根网格的叶子槽就能换颜色。
- 新网格放进表之前先量：`pyworld_veg_probe.py {"roots": [...], "out": "pyworld_veg_new.json"}` 报包围盒、Nanite、三角数、材质。
  不给 `out` 时写到 `Saved/Reports/pyworld_veg_meshes.json`，会覆盖上次的报告。枢轴不在根部的网格会悬空或埋进地里。
- **Electric Dreams 里有什么**：`Content/Megascans/3D_Plants` 下有 41 个植物目录，拷进来了 22 个，其中 21 个温带种：
  EuropeanHornbeam、Elderberry、BeechFern、Fern、SilverLadyFern、KikuyuGrass、CloverVarieties、GroundCover、DeadLeaves、Ivy、EnglishIvy、Periwinkle、WhiteWindflower、YellowArchangel、LilyOfTheValley、Crownbeard、RedLachenalia、PurpleShamrock、CommonPurslane、CustomMoss、Lichen，以及作为依赖带进来的 AlexandraPalm。
  剩下的大多是热带种：各种棕榈、Taro、龙血树、巴豆。**ED 里没有柳树、果树，也没有其他温带乔木**，新树种要另找资产（例如 Fab / Quixel），同样放进 `/Game`、量尺寸、修材质。

## 怎么改

- **加物种**：
  1. 资产已在 `/Game`（见上）。
  2. `SPECIES` 加一项。
  3. 在相应的 `TREE_MIX` / `SHRUB_MIX` / `GROUND_BASE` / `PATCHES` 里给权重；需要新规则（比如"离水 10 m 内"）就在 `grow.py` 那一层加条件。
  4. 测试：`test_world_flora.py` 检查每个网格文件存在、表的形状；`test_world_w07.py` 检查层、群落、间距、确定性。
  5. `reset {"from": 7}` → `gen 7` → 等 150–200 s → `read 7`，notes 里有每个物种的数量。
  6. `gen 8` → `read 8` → `gen 9` → `read 9`（W9 读树密度）。
  7. `check`，再拍对应群落的近景。
- **调密度或比例**：先用 PARAMS 覆写，再动接受率、配比和 `grow.py` 里的概率；群落边界改 `Fields`。
  注意跨步影响：W9 按树密度刷 ForestFloor（每 20 m 格 1–4 棵就开始刷），村边或草甸种多了，林下地面会刷进村里。
  乔木只按树干位置避让（离足迹约 3 m + 0.3 倍冠幅），大冠幅的树冠可能伸到屋顶上。
- **离线调参**：`gen {"stage": 7, "capture": true}` 存下输入，然后用 `stage_api.load_capture("w07")` + `stage_api.execute(w07_vegetation, inputs, params, None)` 本地跑。本地也要 1–2 分钟。
- **验收** `checks.accept(7)`：
  - 乔木 ≥ 20 000；
  - 河岸的桤木占比高于全图；
  - 物种 ≥ 30；
  - 6 层都非空；
  - forest、edge、meadow、riparian 都存在。

  W10 要求植被侵入为 0。

## 坑（traps 97–101）

- Megaplants 只剩光秃枝干：没开 `r.Nanite.Foliage`。
- ED 母材质一画就崩：Anisotropy，见上。
- 140 万个点走 `Spawn_Assets` 生成中途崩溃，改用 Static Mesh Spawner。
- Python 建材质时每次属性改动都触发重编：用 `NEVER` 通知。
- W7 的 `read` 读早了实例数为 0 或偏少，等一会再读，不要当成失败去改代码。
