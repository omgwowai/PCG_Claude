# 地形与地表材质（W1、W9）

## 地形是什么

- 地形是 MeshTerrain（关卡里的 `MeshPartition` actor）。PCG 用 `Get_MeshTerrain` + `Extract_MeshTerrainPoints` 读成顶点点集，`Write_MeshTerrain` 写回。
- 顶点格间距 585.9375 cm（`pypcg.world.VERTEX_CM`），全图 261 312 个顶点。`world/grid.py` 的 `Lattice` 是它的高度场：
  - `height(x, y)` 是双线性插值；`tri_height(x, y)`、`surface(x, y)`（带梯度）是**引擎自己的三角面**：每个格子沿 (i, j)–(i+1, j+1) 切开（实测误差 0.04 cm）。
  - 凡是要坐在可见地面上的东西（街道石板、植被、门前台阶）都用 `tri_height` / `surface`。在扭曲的格子上两者差约 16 cm，石板曾整片被地面盖住（trap 112）。`vertices_in(x0, y0, x1, y1)` 给盒内顶点：三角面的峰值在顶点上。
- 写地形的步骤与顺序（`world.TERRAIN`：查询类型、读的子优先级、写的子优先级）：

  | 步 | 读 | 写 |
  |---|---|---|
  | W1 | Base | 1，再过原生侵蚀（只作用在 `Mountain` 属性 = 山体上） |
  | W3 | Intermediate 2 | 3 |
  | W4 | Intermediate 4 | 5 |
  | W6 | Intermediate 6 | 7 |
  | W9 | Intermediate 8 | 9（只写材质通道） |

  W2、W7、W8 读 Final。**每个写地形的步骤都写回全部顶点**（只改 z），所以改了上游要从那一步起整链重跑。
- 地形操作在 `world/terraform.py`：
  - `fit_plane` / `platform`：聚落平台；
  - `pad`：把多边形垫平，外加过渡带；
  - `flatten_corridor`：路、街走廊；
  - `carve_channel`：河道；
  - `cut`：只降不升，把楼外高出楼面的地面切到楼面。
- W1 的形状：谷底沿 `PyWorld_Valley` 样条（控制点的 z 就是谷底高程，加 2 % 横坡和低频噪声）；两侧在 400 m 内升到山脊（域扭曲值噪声 + 脊状噪声）；离中心 1.15–1.48 km 落到海底 −600。
  参数是 `FloorHalfWidth`、`WallWidth`、`RidgeHeight`、`EdgeStart`、`EdgeEnd`。谷轴走向、地点、河端、出口在 `world/layout.py`，改了以后走 `layout` → `assign` → 从 1 重跑。

## 地表材质：6 个通道

- 通道固定为 `pypcg.world.CHANNELS = (Grass, Rock, ForestFloor, Dirt, Mud, Gravel)`，即引擎插件 `MPD_Basic`（PCGPrimitives_MeshPartitionInterop）的材质通道。
  W9 给每个顶点 6 个同名 Float 属性，由 `Write_MeshTerrain(Channels=CHANNELS)` 写进地形（trap 93）。关卡的 MeshPartition 必须用带这些通道的定义（`MPD_PyWorld` 或 `MPD_Basic`）。
- 权重和必须为 1：`w09_surface.compose` 把 Grass 以外的通道相加，和 > 1 时归一化、Grass 取 0，否则 Grass = 1 − 和。
- W9 的规则（`stages/w09_surface.py`）：

  | 通道 | 刷在哪里 | 参数 |
  |---|---|---|
  | Rock | 坡度 smoothstep(34°, 46°) | `RockSlopeStart` `RockSlopeFull` |
  | ForestFloor | W7 的树密度：20 m 格计数，3 × 3 平均，格中心间双线性（没有方格边）；smoothstep(1, 4 棵每格) × (1 − Rock) | `ForestCell` |
  | Dirt | 路、街（半宽用 Streets 表的 `Paved`，含人行道）外 1–5 m 衰减到 0；广场 = 1；农田、菜园 ≥ 0.8 | — |
  | Mud | 河岸：河的半宽外 6 m 内衰减，× (1 − Dirt) | — |
  | Gravel | 河床；弯道内岸的点沙坝（River 表的弯曲符号和 `BarW`）；干道路肩 1.5 m 内 0.6 | — |
  | Grass | 剩下的 | — |

- 上游：W9 读 W3 的 River、W4 的 Roads、W6 的 Streets / Plaza / Field 区域、W7 的 Tree 点。**改了这些步都要重跑 W9。**
- Summary：`cover_<通道>`（覆盖率）、`weight_sum_err_max`。验收 `checks.accept(9)`：通道数 = 6，权重误差 < 1e-3。
  目前的覆盖率约为 Grass 40 %、ForestFloor 40 %、Rock 19 %、Dirt 0.9 %。

## 材质资产

- `pyworld_terrain_material.py`（在编辑器里跑，会存盘）：
  - 复制插件材质 `M_MeshTerrain_Basic` → `/Game/PyPCG/World/M_PyWorldTerrain`，`MPD_Basic` → `MPD_PyWorld`；
  - 把每个通道 `BlendMaterialAttributes` 的 B 输入上的色块（`TextureTextColor`，纹理名 `Text_<通道>`）换成一层 Megascans 扫描材质。每层：世界坐标 UV、两种尺度（tile 和 tile × 3.7，按 0.4 混合）防止重复，乘色调，Rock 和 ForestFloor 去饱和，接法线、粗糙度、AO；
  - `{"assign": true}` 同时把 `MPD_PyWorld` 设给关卡的 MeshPartition（`layout` 阶段也会优先用 `MPD_PyWorld`）；
  - 插件自己的资产不动。
- 当前每个通道的贴图（脚本里的 `LAYERS`，都在 `/Game/Megascans/Surfaces/`，由 `Tools/pyworld/ed_closure.py` 从 Electric Dreams 拷进来）：

  | 通道 | 贴图 |
  |---|---|
  | Grass | MossyGrass |
  | Rock | IcelandicQuarryRock（法线用 RockCliff） |
  | ForestFloor | NordicMoss |
  | Dirt | DriedGrassOnDampSoil |
  | Mud | JungleGround |
  | Gravel | Gravel_Pebbledash |

- 写材质表达式时，所有属性都用 `PropertyAccessChangeNotifyMode.NEVER`，最后只 `recompile_material` 一次。逐个通知会每改一次就整材质重编，100 次能把内存推到 100 GB（trap 100）。
- 纹理采样类型要按纹理设置选（脚本里的 `sampler()`：虚拟纹理、法线、掩码、线性）。选错会编译失败。

## 怎么改

- **换某个通道的贴图、色调或尺度**：改 `LAYERS`（和 `DESAT`），重跑 `pyworld_terrain_material.py`。重跑只删带 `pyworld_layer` 标签的节点再重建。
  这只改材质，不用重生成；拍近景看贴图尺度和接缝。新贴图先确认已经在 `/Game` 里，不在就用 `ed_closure.py` 拷进来。
- **改通道刷在哪里**（比如岩石从更缓的坡开始、河岸泥更宽）：
  - 调参数：`{"phase": "assign", "overrides": {"9": {"RockSlopeStart": 30}}}`，只覆写组件参数；
  - 改规则：改 `w09_surface.py` 的函数，先加 `test_world_w09.py`。改 PARAMS 的默认值要 `build {"stages": [9]}` → `assign`。
  - 然后 `reset {"from": 9}` → `gen 9` → `read 9`，拍 `top` 和近景看分布。
- **加一个新通道**（比如独立的 Moss）：通道表在 MPD 里，材质和 W9 都要跟着改。

  已知事实：
  - `M_PyWorldTerrain` 是插件材质的副本，里面的通道采样节点**仍指向插件的 `MPD_Basic`**：资产里引用的是 `MPD_Basic`，不是 `MPD_PyWorld`。脚本只换了色块，没碰它们。
  - `pyworld_probe_channels.py` 只读插件的 `MPD_Basic` / `MPD_Default` 的字段（`channel_map` 等）和关卡当前用的定义。它查不了 `MPD_PyWorld`，也证明不了 Python 能写通道表。要查或试写，就先扩展这个探针，在 MPD 副本上试。
  - 测试 `test_world_w09.py` 和验收 `checks.accept(9)` 都写死了 6 个通道。

  来自引擎源码、本项目**没有验证过**的说法：
  - 材质按 MPD 通道表的顺序取通道，新通道要追加在通道表**末尾**；
  - `Write_MeshTerrain` 写入通道表里没有的名字时会静默丢弃；
  - 改通道表会让地形的已编译分段失效，整片重建。

  步骤：
  1. 探针确认 `MPD_PyWorld` 的通道表可写，然后在末尾加一项，名字和 W9 的属性名、`CHANNELS` 一致。
  2. 材质：采样节点改指 `MPD_PyWorld`，再加新通道的采样和混合（脚本里新节点都打 `pyworld_layer` 标签）。
  3. `CHANNELS` 加名字；W9 算它的权重，并保持总和为 1（例如从 ForestFloor 里分出来）。
  4. `checks.accept(9)` 和 `test_world_w09.py` 里的 6 改掉。
  5. `build {"stages": [9]}` → `assign` → `reset {"from": 9}` → gen / read 9，再看 `cover_<新通道>`，拍照。

  **本项目还没走通过这条路。** 探针写不进时，退路是在已有通道里做（ForestFloor 已经是 NordicMoss 苔藓地面，可以调它的权重或换贴图）。
  项目里还有一套没被占用的 Megascans 地面贴图：`/Game/Megascans/Surfaces/MossyRockyGround`。

## 坑

- 关卡的 MeshPartition 没换成带通道的 MPD 就写通道，颜色不对（trap 93）。
- 从 Electric Dreams 拷进来的母材质，在本项目的 Substrate 混合 GBuffer 下连着 Anisotropy，第一次画就断言崩溃。拷完先跑 `pyworld_fix_aniso.py`，先加 `{"dry": true}` 看一遍（trap 98）。
- River 表的宽度是**全宽**。W9 曾把它当半宽用，Gravel 往两岸各溢出半个河宽。
- 地表是逐顶点权重，5.86 m 一格：比格子窄的东西（1.5 m 的路肩、窄巷）在地表上画不细，要用网格（街道石板、路的车道模块）表现。
