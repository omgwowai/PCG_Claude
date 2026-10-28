# 建筑 PCG（W6 的建筑模块）

## 数据流（City Sample 的 BDF 路线）

1. 地块：类型、分区、聚落、宽深、朝街的边 `front`。
2. `rules.dress()`：原型 → 样式码、层数、墙色、屋顶色、坡度系数 k、种子。
3. `building.assemble(b)`：生成模块实例 `{loc, rot, scale, mesh, mat, role}`。
4. `points.module_points`：变成点，带 `Mesh`、`Mat0` 两个 SoftObjectPath 属性。
5. 原生 Static Mesh Spawner 生成，开着 `bUseAttributeMaterialOverrides`、`MaterialOverrideAttributes = ["Mat0"]`。网格按属性选，0 号槽材质也按属性选，空路径表示用网格自己的材质（trap 111）。

和 City Sample 的对应：原型 = BuildingsStyles 白名单，样式码 = BDF 一行，竖向语法 = `[LV0][LV1][LV2]*[LV3]`，水平语法 = 每层的 F0 / F1 / F2 + FLengths，外角 = C_E，高度噪声 = 高度噪声贴图。

## 样式库（`world/bdf.py`）

- `STYLES[code]` 的字段：
  - `family`：模块家族；
  - `vertical`：竖向语法，例如 `[G][TR][N][U]*[RT]`，`*` 是重复层；
  - `floors`：层数范围；
  - `min_wall`：最短墙。地块最小边必须不小于它，`test_every_lot_fits_a_style_of_its_archetype` 会检查；
  - `roof`：`k` 坡度系数范围、`dormer` 老虎窗概率、`over` 挑檐（cm）、`tints` 屋顶色；
  - `tooltip`：look / type / era。
- 7 个码：LSA、LSB（F00 石材）；PLA、PLB、PLC（F02 抹灰）；BRA、BRB（F01 砖）。
- `GRAMMARS[family]`：按墙长（两端端区之间）选水平语法，后面跟备选。
  - F02 分三档：12 m 以下 `[S][P,S]*`；24 m 以下 `[S][P,L]*[P,S]`；更长 `[S,P][L,P]*[S][P,L]*[P,S]`。
  - F01、F00 各一个 `[W][P,W]*`。
  - `band` 给腰线和檐口用。
- `FRONTS[family][use]`：朝街一面底层的语法，含门 `D`；砖房商铺用 `H`（门 + 橱窗）。两个 `*` 段均分，门就居中。
- 缩放：开间 `BAY_SCALE` (0.85, 1.2)，正面 `FRONT_SCALE` (0.8, 1.25)。放不下的余量（slack）变成两端的素墙；余量不超过 `SLACK_OK` 40 cm 时仍用该档语法。
- 接口：`levels(code, floors)`、`bays()`、`band()`、`front()`、`widths()`。

## 立面语法（`world/grammar.py`）

- 语法是 PCG 形状语法的子集：
  - `[A,B]`：一组，按顺序；
  - `*`：重复 0 次以上；`+`：1 次以上；`N`：固定次数；
  - `{A:w}`：加权。
- `solve(parts, length, widths, scalable, smin, smax, slack)`：为每个重复段选次数，让可缩放模块（S、L、W、V、D、H）的统一缩放最接近 1。
  排序键依次是：放不放得下、余量大小、|log s| + 0.05 × 两个 `*` 段的不均。
- `positions()` 给出每段的位置；`expand()` 用来展开竖向语法。

## 模块库（`world/kit.py`）

- 美术是项目里已有的 Megascans Modular_Building 套件（`/Game/Megascans/3D_Assets/Modular_Building_*`，Nanite）。三个家族：

  | 家族 | 外观 | 层 | 开间 | 端区 |
  |---|---|---|---|---|
  | F00 | 石材古典 | FND 基座、L1 拱窗一层、T1 腰线、L2 标准层、L3 山花顶层、CR 檐口 | W 300 + 壁柱 P 50 | 150 |
  | F01 | 砖房 | G 底层（W 200 窗、V 300 宽窗、H 350 门 + 橱窗）、U / U2 楼层（变体 X）、T 拱窗顶层；TR / RT 借 F02 的腰线和檐口作 band | W 200 + P 50 | 50 |
  | F02 | 抹灰百叶窗 | G、GC 粗石底层、TR、N 花饰主层、U、U3、A 阁楼、RT 檐口 | S 400 / L 500 + P 50 | 50 |

- 每层的字段：`h` 层高；`storey` 算不算一层；`mods`（符号 → `{mesh, w 槽宽, kit, fix, …}`）；`corner`（`mesh`、`cx`、`cy`）；`alt` 变体；`band`：独立求解，不对开间网格。
- **实测约定**（trap 110）：
  - 模块沿本地 +X 从 0 摆到槽宽，立面朝 +Y，墙体在 −Y，Z 从 0 向上；
  - 外角的枢轴在墙角点，覆盖当前边的前 `cx` 和上一条边的后 `cy`；
  - 足迹按**顺时针**遍历（`building.ring_cw`，边 0 = +d 侧），立面才朝外，逆时针会全部朝里；
  - F00 每层的角宽不同（144 / 129 / 115 / 106 / 150），靠 150 的端区和缩放的壁柱补齐，各层窗洞才能上下对齐。
- F01 的子网格 `_01.._04` 导入时丢了材质：`fix=True` 的模块，0 号槽一律用套件自己的 `*_inst`。F01 的窗也没有玻璃，所以每栋楼窗后放一块室内块（`K.INTERIOR` = 套件的 `M_Bldg_glass`），不然窗洞是透的（trap 109）。
- 门：
  - `DOOR_00`：F00 的门洞跨基座和一层；F02 按 400 / 650 缩小使用，`own=True` 不染色；
  - `GATE`：镇公所和教堂的大门，跨基座、一层和腰线。
- 屋顶 `ROOF`（Roof_Kit_00，trap 107）：
  - `_01` 是斜脊角，放在屋顶矩形的角上，yaw +90；`_02` 是天沟，不要用；
  - 直段 `_04`（300），带老虎窗的直段 `_03`；
  - 深 600、高 257.5；缩放 s = 进深 / 1200，Z 再乘 k；
  - 正方形足迹就是四棱锥。
- 道具（City Sample 的建筑道具）：壁灯 `LAMPS`、铭牌 `PLAQUES`、遮阳篷 `AWNINGS`（8 套 × 4，宽 287，挂在顶边上）、挑出招牌 `BANNERS`、阳台 `BALCONY`。
- 街道套件：`PAVER`（`SM_Plaza_Square_E`，带起伏的 4 cm 石块皮）、`SIDEWALK`、`PLAZA_STONE`，都是 3 m 一块的板，见 town-pcg.md。

## 颜色与材质

- `TINTS` 的调色板：
  - Plaster：Base、Ochre、Rose、Sage、Mist、Butter；
  - Brick：Base、Umber、Sand；
  - Stone：Base、Grey、Warm；
  - Roof：Slate、BlueSlate、Terracotta、Brown。板岩的反照率接近白色，所以屋顶色都压得很暗。
- `material(m, tint)`：
  - Base 或 `own` → 空路径，用网格自己的材质；
  - `fix` → 套件的 inst；
  - 其余 → `tinted(folder, tint)` = `/Game/PyPCG/World/Town/MI_<folder>_<tint>`。
- 子材质由 `pyworld_town_materials.py` 生成，覆盖 `kit.materials_needed()` 列出的全部（当前 70 个）。父材质是套件的 inst，设 `Albedo Tint`，并且必须同时设 `Albedo Tint Intensity = 1`（trap 108）。
  **新增色调后先跑它再生成**：Mat0 指向不存在的资产不会报错，只是没颜色。`test_world_kit` 会检查每个色调都在清单里。
- 色调乘在整张贴图集上（百叶窗一起变色），画不出新细节。新外观（例如半木结构的木筋）要新网格或新材质，不能只靠色调。
- **墙色从哪抽**：`rules.dress` 从样式所属**家族**的调色板（`kit.TINTS[family["palette"]]`）里抽，避开邻居的颜色；原型的 `tints` 可以覆盖（比如谷仓只用 Umber）。
  所以同一家族的样式共用一套颜色。要让一个样式有专属颜色，就给它一个家族副本（如 `dict(F02, palette="新调色板")`，并在 `FAMILIES`、`GRAMMARS`、`FRONTS` 里登记），或在原型里写 `tints`。

## 单栋装配（`world/building.py` 的 `assemble`）

1. 每条边、每层依次放：外角 → 端区壁柱 → 余量素墙 → 语法序列（开间、壁柱、门）。门洞会跨层：F00 门洞跨两层，大门跨三层。
2. `_props`：门两侧壁灯；门上一层的阳台（概率 `BALCONY_P[样式]`，商铺 × 0.6）；镇公所铭牌；商铺底层朝街每个窗洞一个遮阳篷，门旁一块招牌。
3. `_steps`：门比门前 60 cm 处的地面高出 `STEP_MIN` 20 cm 以上时加台阶：等分高差，最多 `STEP_MAX` 6 级，每级不超过 25 cm，踏面 32 cm。`door_rise` 由 W6 量。
4. `_roof`：四坡顶。
5. `_boxes`：勒脚（`PLINTH` 450 cm，石灰石，楼面以上露 5 cm）、室内块、1–2 根烟囱（`NO_CHIMNEY` 里的类型没有）。

特例表：`SPECIAL_LEVELS`（教堂、钟楼的层序列）、`SPECIAL_K`、`GATED`。
返回 `instances`、`walls`（每边每层的段，供测试检查是否铺满）、`wall_top`、`ridge`、`stats`。

## 怎么改

- **加样式码**：
  1. `bdf.STYLES` 加一项。新家族还要 `GRAMMARS` 和 `FRONTS`。
  2. `building.BALCONY_P[新码]`，缺了会 KeyError。
  3. `rules.ARCHETYPES`：在要出现的类型、区里给权重。只在镇或村出现的过滤写在 `rules.styles_for`，参照 `STONE`。
     层数：先取分区的层数范围，村、小村的核心区和住宅区再减一层（`RANK_STOREYS`），最后截到样式的 `floors` 范围。所以一个 2–3 层的样式放在村里，基本都会是 2 层。
  4. 新色调加进 `kit.TINTS`，然后在编辑器里跑 `pyworld_town_materials.py`。
  5. `Tools/pyworld/offline.py` 的 `STYLE_RGB` 加一个颜色，平面图上好认。`--town` 只画最大的聚落（镇），看村要自己改画图的中心。
  6. 测试：
     - `test_world_bdf.py` 里 `test_seven_style_codes_with_city_sample_tooltips` 硬写了 7，要改；
     - `test_world_building.py` 按 `STYLES` 自动参数化，新码自动覆盖；
     - `test_world_w06.py` 有 every_lot_fits 和"村比镇矮一层"。
  7. 在海面预览：`pyworld_town_preview.py` 的 `SAMPLES` 加一栋，拍照看，再 `clear`。
  8. `reset {"from": 6}`，然后 6..9 依次 gen / read。
- **加模块家族**（新套件）：
  1. 先实测：`pyworld_probe_megascans_kit.py` 量包围盒和槽位；`pyworld_kit_catalog.py {"family": ...}` 在海面摆一排，认清每块是什么；`pyworld_kit_test.py {"file": ...}`（例子见 `Tools/pyworld/kit_test_items.py`）摆几块拍照，核对朝向、角和接缝。
  2. 屋顶这类斜面要读顶点（`pyworld_probe_roof_geometry.py`）：俯视截图分不出正四坡顶和倒扣的漏斗顶。
  3. 在 `kit.py` 写家族表：层、槽宽、角 `cx` / `cy`、端区 `end`、`palette`。在 `bdf.py` 写语法。
  4. `test_world_kit.py` 检查：每层有网格和宽度、各层开间对齐、角放得进端区、色调都有材质。
- **改道具、屋顶、台阶、勒脚**：改 `building.py` 的 `_props` / `_roof` / `_steps` / `_boxes` 和对应常量，用 `test_world_building.py` 测。
- **加套件里没有的细节**（木筋、雨棚、外挂楼梯……）：在 `assemble` 里加一步。
  - 沿某条边放网格：`out.put(e, x, z, mesh, mat, role, scale, y=离墙距离, yaw_add=…)`，坐标在这条边的局部系里（x 沿边，y 朝外）；
  - 放方块：`out.box(x, y, z, sx, sy, sz, yaw, mat, role)`，用的是世界坐标，z 是方块中心；`K.CUBE` 是 100 cm 的居中立方体，`_boxes` 就是这样放勒脚和烟囱的。
  - 材质可用项目里已有的，比如木头 `/Game/Building/Material/MI/Wood/MI_Bldg_Wood_Walnut`、`MI_Bldg_Wood_Cedar`。
  - 新的 `role` 进 `stats`；测试检查它贴着立面，不穿进窗洞。
  - 立面模块凸出墙线的深度，先用 `pyworld_kit_test.py` 量。
  - 拉伸的方块上贴图会拉丝，离墙太近会闪烁（z-fight）。

## 预览与核对

- `pyworld_town_preview.py`：在谷南约 1.9 km 的海面测试区摆样例楼（`SAMPLES`，每种样式一栋），actor 名 `PyWorldTown_*`。
  - `{"only": [8, 7, 0, 1], "pack": 1900, "z": -450}`：按给定顺序排成一排，楼面贴近海面（海面在 z −500）；
  - `{"door_rise": 90}`：看台阶；
  - `{"clear": true}`：清掉。**从不存盘。**
  - 拍照用行人视角：相机在楼前 50–90 m，`eye` 和 `look` 都给 z。
- 验收 `checks.accept(6)`：样式码 ≥ 5，每栋的门都在朝街一面，开间缩放在 0.8–1.25，有联排。
- 测试保证：每面墙每层的模块正好铺满墙长（误差 < 1 cm），每层 4 个外角，一扇门在朝街一面，四坡顶盖住足迹，同种子同结果。

## 坑（traps 107–113）

- Roof_Kit_00 的 `_02` 是天沟；按名字或包围盒猜，先放成蝴蝶顶，再放成漏斗顶。
- `MS_DefaultMaterial` 的 `Albedo Tint` 不配 `Albedo Tint Intensity = 1` 没有效果。
- 家族 01 的子网格丢材质、窗没玻璃。
- 沿足迹逆时针摆，立面全部朝里。
- 原生 Static Mesh Spawner 按属性覆写材质时，每种（网格，材质）组合生成一个 ISM。
- 坐在可见地面上的东西用 `tri_height`（trap 112）。
- 石块路面网格是带起伏的 4 cm 皮：Z 方向拉太长，石缝会被地面填满（trap 113）。
