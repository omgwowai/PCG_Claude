# PyWorld 植被生物群落 —— 设计（2026-10-23）

目标（用户 /goal）：把 PyWorld 山谷（`L_PyWorld`）的植被做成像 3A 游戏一样自然、丰富的生态群落，资产用 UE 的高面数资产，
主要来自 Electric Dreams（`E:\ElectricDreams\ElectricDreamsEnv`）。仍是 W7 一张图、一个 Python 节点（"追求好写"）。

## 1. 资产

- `Tools/pyworld/ed_closure.py --copy`：按包引用闭包从 Electric Dreams 拷入 690 个文件（9.3 GB，路径不变，
  `/Game/Megascans/3D_Plants|3D_Assets/...`、`/Game/MSPresets/...`、`/Game/Custom/CustomMaterials`、`/Game/PhysicalMaterials`），
  与本项目已有文件 0 冲突；不进 git（`.gitignore`）。
- 实测（`pyworld_veg_probe.py`）：266 个网格全部 Nanite。尺寸表在 `Saved/Reports/pyworld_veg_meshes.json`。
- 乔木：Megaplants（CitySamplePCG：黑桤木、榛、欧洲山杨、欧洲山毛榉、挪威槭，A/B 成树、C/D 幼树）+ Electric Dreams 的欧洲鹅耳枥
  （Forest 01–10 林木、Field 01–04 孤立木、Sapling、Seedling）、枯树 DeadTree。灌木：接骨木 Elderberry、榛 C/D、鹅耳枥幼树。
  草本：Kikuyu 草、Wild_Grass、三叶草、蕨（Fern、SilverLadyFern、BeechFern）、银莲花 WhiteWindflower、黄芩 YellowArchangel、
  铃兰、长春花、金光菊 Crownbeard、紫酢浆草、马齿苋、红花 Lachenalia、苔、地被、常春藤、落叶。倒木 / 树桩 / 枝 / 细枝、苔石 / 巨石 / 碎石。
  热带种（棕榈、芋、变叶木、龙血树等）不用：山谷是温带。

## 2. 生态场（每个地形顶点算一次）

坡度、离谷底高度、D8 汇流、离河 / 离路街 / 离建筑距离、朝向（阳坡 / 阴坡）→
- **湿度**：河边、汇流沟、谷底、阴坡高；
- **森林潜势**：谷底（农牧地）低、山腰高、山上 150 m 以上降到稀疏的山地草甸、> 34° 为岩石；离村镇近的地清出来做牧场；
  加两层噪声（250 m、60 m）让林缘曲折；`forest = smoothstep(潜势 + 噪声)`。
- **群落**：林内（forest ≥ 0.75）、林缘（0.15–0.75，过渡带）、草甸、河岸、山地、岩坡。

## 3. 分层

| 层 | 输出 | 做法 |
|---|---|---|
| 乔木 | `Trees`（tag Tree） | 4.5 m 抖动网格，概率随 forest；按物种冠幅做间距（网格哈希）；群落决定物种配比；林内成树为主、林缘幼树和先锋种（山杨、榛）多；草甸零星孤立木和小树丛；田边树篱里隔段一棵 |
| 灌木 | `Shrubs` | 林缘带、河岸密；林内只在林窗（附近 4 m 无树）放幼树、幼苗；田块四周和村外道路一侧的树篱 |
| 地被 | `Ground` | 2.5 m 抖动网格，每个点一丛（同种 1–6 株）：草甸以草为主，各种花各有自己的斑块噪声；林下落叶、蕨（湿、阴多）、林地花（银莲花、黄芩、铃兰）、苔；河岸草、蕨、紫酢浆草；路肩马齿苋；山地稀草和碎石 |
| 草 | `Grass` | 草甸 / 河岸的草丛（`Ground` 里的草单独出，便于调密度） |
| 倒木 | `Debris` | 林内 10 m 网格：倒木（沿等高线摆、贴坡）、树桩、断枝、细枝；大树根部放根系 / 常春藤 |
| 岩石 | `Rocks` | 成簇：一块主石 + 2–6 块副石 + 碎石，陡坡、山上、河岸多；按大小埋 20–35 %，贴坡 + 随机倾斜 |

- 高度：地形三角形沿 (i, j)–(i+1, j+1) 对角线切（`pyworld_tri_probe.py` 实测误差 0.04 cm，双线性最大 42 cm），
  所以直接用顶点格精确插值，不再逐点问引擎。
- 小植物、石头、倒木贴坡（按法线混合），树竖直。
- 清空：路、街、河、桥、建筑、广场、农田照旧；树离路 3 m、灌木 1.5 m、地被 0.5 m。
- 参数：`Density`（乔木）、`ShrubDensity`、`GroundDensity`、`GrassDensity`、`RockDensity`、`Extent`、`DetailHalf`（地被只铺在
  这个半径的方块内，默认 1 km）。

## 4. 验收

- W7 Summary：每层数量、用到的物种数 ≥ 30、各群落样本数、林缘带有灌木。
- 编辑器：W7、W8、W9、W10 check 通过（树侵入 0、贴地抽查），截图：林内、林缘、草甸花、河岸、山地、村边树篱、远景。
- 性能：W7 Python 时间、实例总数、关卡存盘大小记录在指南里。
