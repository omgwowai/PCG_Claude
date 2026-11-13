# 《刺客信条：影》四季动态天气系统（Atmos）拆解，以及在 UE 5.8 里怎么还原

> 2026-10-30。这是选方案之前的分析，还没有任何实现。
>
> **素材**
> - 【A】Ubisoft《Behind the scenes with Anvil Engine: Simulating real weather with Atmos in Assassin's Creed Shadows》，
>   2026-04-14，6:07（https://www.youtube.com/watch?v=DUW4WajQbJQ ）。宣传向，讲 Atmos 的理念和效果。
> - 【B】GDC 2025《Rendering 'Assassin's Creed Shadows'》，Nicolas Lopez（Ubisoft），1:02:04
>   （https://www.youtube.com/watch?v=yj5pYktC3X8 ，链接停在 49:00）。天气与季节一节在 48:57–53:06，
>   季节相关内容另散在场景规模（6:28）、烘焙 GI（27:20）、cubemap（31:13）、光追加速结构（41:58）和结论（57:00）。
> - 补充：【DF】Digital Foundry《Inside Assassin's Creed Shadows - The NEW Anvil Engine Deep Dive》（对 Anvil 团队的采访，
>   11:23–13:00 讲 Atmos）；Anvil 幕后系列第 4 集（RTGI）；Wikipedia 的游戏条目。
>
> **方法**：读字幕（官方英文字幕 + 自动字幕），再看故事板缩略图（320×180，A 每 5 s 一张，B 每 10 s 一张）。
> YouTube 拒绝下载视频流（403 / 需要 PO Token），所以画面细节只能看到缩略图这一级；IGN、Fandom 页面也抓不到。
> 【A 2:27】这类标记给的是字幕段落的起点，是约数。正文只写素材里有的内容，推断单独标出。

---

## 0. 整体结构

Atmos 不是“切换天气预设”，而是三层：

1. **模拟层（Atmos）**：在玩家周围跑一个低分辨率的大气流体模拟。风场与世界的体素表示碰撞，温度、水汽、湿度随风平流、传播，
   由此决定云在哪里形成或消散、哪里下雨、哪里起风。另有“喷溅粒子”：风带着粒子走，粒子与场景碰撞。
2. **编排层（Ambiance Graph，氛围图）**：一张数据驱动、由技术美术配置的节点图，读引擎的时间和季节，以及 Atmos 的模拟量，
   驱动整个天气表现栈：特效、雾、雨、湿度、积水水位、积雪的累积与融化、灯光和后期。
3. **表现层**：
   - 体积云、风、雨雪粒子。
   - **延迟天气**：湿、积水、积雪统一改写 GBuffer，不改各个材质。
   - **深雪变形**。
   - **室内遮挡**：同一份“室内体积”数据同时用于 GI 防漏光、延迟天气和声音。
   - **四季**：靠“多状态实体”（同一物体按季节切换版本）、植被的季节材质（落叶、叶色 LUT），以及按季节准备的光照数据实现。

`时间 + 季节 + Atmos 模拟量 → 氛围图 → 所有表现`，再加上“所有东西读同一个风”。Atmos 团队把这种一致性当作它的核心价值【A 3:00】。

---

## 1. 功能拆解

### 1.1 Atmos：物理天气模拟（核心）

**游戏里的表现**
- 天气是模拟出来的：温度、水汽（vapor）、湿度（humidity）等大气量随风传播，由它们决定某处是否下雨、是否有风
  【A 1:54】【B 49:16】【DF 11:54】。
- 水循环：夏天的太阳把水蒸发，水汽上升形成云，最后变成雨，全程实时、无缝【A 1:54–2:27】。
- 云由模拟量驱动形成和消散，模拟还会形成云锋（cloud fronts）【B 49:16】【DF 11:54】。
- 天气因地而异：在伊贺能看到不同的天气状态进来又离开，中间没有加载【A 2:27】。每个地方的云景和效果都不完全相同；
  评测里有玩家为了看沿途的天气变化，干脆不用快速旅行【A 4:13】。
- 风是在玩家周围 3D 空间里做的流体模拟，湍流和流动与世界的低分辨率体素表示碰撞，所以地形、建筑会挡风、绕流
  【B 49:16】【DF 11:54】。素材原话是用“多个相互连接的流体”影响所有系统的风【A 3:37】。

**Anvil 的做法**
- 实时流体模拟，幻灯片引用 Hädrich et al. 2020，即 SIGGRAPH Asia 2020 论文《Stormscapes: Simulating Cloud Dynamics
  in the Now》。论文实时模拟浮力、水汽凝结、蒸发和降水，地形参与【B 49:07 幻灯片】。
- 只在玩家周围模拟，用低分辨率体素数据做风的碰撞【B 49:16】。
- 模拟量随海拔分布：幻灯片右侧是一组“随高度变化”的曲线；宣传片 2:07–2:17 的调试画面是一张俯视的场，
  旁边三条高度曲线【B 49:07–49:37】【A 2:07】。
- 风模拟本身是一个独立系统，Atmos 只是它的使用者之一，云的生成要用它【A 3:00】。

### 1.2 统一风场与喷溅粒子

**表现**
- 一致性是核心：风把雨吹到角色身上，吹动衣服和头发【A 3:00】。
- 树按风力摇摆，树枝各自做二次运动；玩家和 NPC 的发丝（strand hair）在大风里翻飞；树叶、雨、雪和其它碎屑被风卷起
  【DF 12:27】。
- 画面：秋天落叶飞舞，随后起尘暴、天色变暗（A 2:41–2:46）；村里的旗帜（A 3:35）；风雪里骑马（A 5:47）。

**做法**
- “喷溅粒子系统”（spray particle system）：一个带碰撞的动态风，携带粒子运动【A 3:37】。A 3:54–3:59 的画面是雨粒子的调试视图
  （黑底白线），能看到雨丝被风吹弯。
- 有一个“DYNAMIC WIND OPTIONS”调试菜单（A 3:40）。

### 1.3 天气状态与氛围图（编排层）

**表现**
- 前一刻在森林里，阳光穿过树冠；下一刻头顶形成雷暴，气氛完全改变，中间无缝【A 4:13】。
- Atmos 像一个指挥，统筹雨、灯光和声音【A 3:00】。

**做法**
- 配方是“天气状态 + Atmos + 喷溅粒子”【A 3:37】。
- 前作用 Ambiance Manager 管昼夜、天气、调色、季节和后期，主要靠曲线，逻辑能力有限【B 49:47】。
- 本作换成 **Ambiance Graph**：建在引擎的节点图系统上，数据驱动，可视化脚本，能输出自定义 UI。它读引擎和 Atmos 的输入，
  驱动整个天气效果栈（特效、雾、雨、湿度、积水水位），表现完全由技术美术决定【B 48:57 幻灯片、49:47–50:20】。
- 雪的消退、变湿、积水、变干，这条逻辑也在这张图里【B 52:23】。
- 演讲结论：基于图的季节与天气便于做原型、调出合适的配方，但难 QA、难复现问题【B 57:00】。

### 1.4 降水粒子与遮挡

- 雨被风吹斜（A 3:05、4:58 画面）；还有雪和暴风雪（A 3:30、5:47）。
- 近距离遮挡：沿雨的方向渲染周围常规几何体的深度图，用它遮挡雨粒子和涟漪。屋檐下没有雨，但雨能从窗口飘进室内
  【B 52:53，幻灯片“Oriented depth map”】。

### 1.5 延迟雨：湿与积水

- 基于 Sébastien Lagarde 2012 的“Water drop”系列。用湿度（wetness）和积水水位（puddle level）两个量：
  湿的地方反照率变暗、粗糙度降低；积水处叠加涟漪法线【B 50:16–50:46】。
- “延迟”指不改每个材质，而是在 GBuffer 上统一改写。GBuffer 里只多存一个 float 的湿度遮罩【B 50:51】。
- 角色不走这套（幻灯片里标红），角色湿身由角色自己的动态图层系统负责【B 50:51】。
- 演示了三档：干、湿、湿加积水（0/0、100/0、100/100）【B 50:36–50:56】。
- 光追镜面反射里完整计算延迟天气，漫反射 GI 里不算，因为太贵【B 41:58】。

### 1.6 延迟雪：积雪、融化与深雪

- **深雪（deep snow）**：数据驱动的 stamper，可以压胶囊或贴图，用来变形地形或任意高度图，留下脚印和拖痕【B 51:06】。
- **动态积雪**，和延迟雨一样改材质输入【B 51:22–51:56】：
  - 反照率按雪量向雪色（一般是白）插值，粗糙度同理；
  - 雪越多，植被的透光（translucency）越低；
  - 乘微遮蔽（micro visibility），缝隙里雪少；
  - 最后按法线朝向做阈值，竖直面不积雪。
- **冷区和暖区**：由技术美术绘制的静态或动态雪遮罩决定（幻灯片里的红黄绿图）【B 51:16–51:30】。
- **消退**：暴风雪停后，雪按积累的反向过程慢慢消退，先变湿、积水，最后融化变干。整个过程由氛围图驱动【B 52:23】。
- **光追**：静态雪烘进地形远景，光追漫反射也能看到它【B 42:31】。

### 1.7 室内遮挡（雨、雪、声音共用）

- “室内体积”就是一组平面，同一份数据用于烘焙 GI 防漏光、延迟天气，甚至声音【B 43:38】。
- 中距离：把室内体积光栅化成一张俯视的室内深度图，用来决定湿和积雪的遮挡，室内地面不湿也不积雪。数据只有平面，渲染很便宜【B 52:36】。
- 近距离：见 1.4 的定向深度图。

### 1.8 四季

- 四季是和昼夜、天气并列的第三个维度，16×16 km 的世界全部随季节变化【B 6:28–7:18】【A 0:35】。
- **多状态实体**（multi-state entities），也叫变化状态（variation states）：实体级、数据驱动的变体逻辑，主要用于季节
  【B 31:13、48:57】。
- **植被**：材质表里有季节版本。叶子掉光后不再挡光，叶色用查找表（LUT）【B 41:58】。加速结构的四季对比图里，
  春是粉、夏是绿、秋是黄橙、冬是白【B 42:28】。
- **光照数据**：Anvil 还要支持烘焙 GI，所以光照数据要按季节准备。春夏当作同一季；亮度（Y）只存一份，色度按季节存三套；
  每个 cubemap 存三个季节变体【B 27:20–28:24、31:13】。UE 用 Lumen 实时算 GI，这部分不用做。
- **画面里的季节特征**：
  - 春：樱花，落花铺满庭院（A 2:21–2:31）。
  - 夏：绣球花、浓绿、瀑布（A 2:36、4:43）。
  - 秋：红枫、金色草地、落叶飘飞（A 1:28、1:47、2:41、2:56、5:13）。
  - 冬：积雪、雪中流动的溪水、屋檐冰柱（A 3:30、4:38、5:18）。
- **玩法**（来自 Wikipedia，不是这两个视频）：冬天池塘和浅水结冰，主角不能再潜进去躲藏。

### 1.9 玩法与生态联动

- 天气会影响人群、NPC、动物和整个“活的世界”，改变玩家能做的事和体验【A 2:27】。
- **光影潜行**（Wikipedia）：藏在阴影里，敌人就看不见；可以用手里剑打灭灯笼，制造黑暗。所以昼夜和天气造成的明暗直接影响潜行。
- **角色**：风吹动头发和衣服，雨打在身上【A 3:00】；角色湿身由角色图层系统负责【B 50:51】。
- **声音**：Atmos 统筹雨、灯光和声音【A 3:00】；室内体积也用于声音【B 43:38】。
- **素材没有证实的部分**：雨声盖住脚步、雾缩短视距、季节改变可藏身的草丛，这些宣传里常见，但这几份素材没讲，要不要做由你定。

### 1.10 光照跟随（支撑能力）

- 实时光追 GI 让光照跟得上天气和季节变化，比如暗沉的暴风雨天空、季节、动态物体【DF 12:57】【RTGI 集 3:41】。
- 在 UE 里由 Lumen 负责。本项目已经开着 Lumen GI 和 Lumen 反射（`r.DynamicGlobalIlluminationMethod=1`、`r.ReflectionMethod=1`）。

---

## 2. 在 UE 5.8 里对应什么

| 功能 | UE 现成能力 | 需要自己做 | 备注 |
|---|---|---|---|
| 昼夜、天空、雾 | Sky Atmosphere、Directional Light（日、月）、Sky Light 实时捕获、Exponential Height Fog（体积雾）、Local Fog Volume、Post Process、Lumen；SunPosition 插件按经纬度和日期算太阳轨迹，各季节的日照长短、太阳高度自然得到 | 时间、季节、天气到参数的控制器 | L_PyWorld 已有这些 actor，目前是静态的 |
| Atmos 模拟 | 没有现成的气象模拟。可用的底座：Compute Shader（C++ RDG），或 Niagara Grid2D / Grid3D（Niagara Fluids 插件，Beta，自带有温度和浮力的气体模拟模板） | 气象方程（平流、浮力、凝结、蒸发、降水、地形抬升），以及把结果读回给玩法 | 工作量最大、风险最高 |
| 体积云 | Volumetric Cloud（自定义材质，可采样 2D 天气图或 3D 体纹理）；Heterogeneous Volumes 适合局部的风暴云，但贵 | 模拟量到云覆盖、云型、密度的映射；风推云走 | — |
| 风场 | Material Parameter Collection（全局风向量）、WindDirectionalSource（布料、SpeedTree）、Niagara Fluids 3D 网格（局部 3D 风，场景碰撞需验证）、Dynamic Wind 插件（实验，供带骨骼的 Nanite 植被使用，读一张风纹理） | 一个所有系统都采样的风场（体纹理加世界坐标到 UV 的映射）；给植被材质加 WPO 风 | Megaplants 是没有骨骼的静态网格，材质里也没有风参数，所以 Dynamic Wind 直接用不上 |
| 喷溅粒子、雨雪 | Niagara GPU 粒子：采样风场体纹理，用深度缓冲或距离场碰撞；SceneCapture 深度图做遮挡 | 沿雨方向的遮挡深度图；溅落和涟漪 | — |
| 湿、积水、积雪 | ① 每个母材质里加一个全局天气材质函数，读 MPC 和世界遮罩（RVT 或 RT）；② C++ SceneViewExtension 在 base pass 之后改 GBuffer（`PostRenderBasePassDeferred_RenderThread`），等于 Anvil 的延迟做法；③ 改引擎（本项目是源码版引擎） | 母材质改造或渲染 pass；积水遮罩、冷暖区遮罩、涟漪法线 | 本项目开着 Substrate（`r.Substrate.ProjectGBufferFormat=0`），改写 GBuffer 的方式要先验证 |
| 深雪变形 | Render Target 画轨迹；Nanite 置换（tessellation，实验），或独立的雪面网格（VirtualHeightfieldMesh 插件） | stamper；贴地变形 | 地形是 MeshTerrain，不是 Landscape，置换路线要验证 |
| 室内遮挡 | SceneCapture2D 正交俯视深度；Audio Gameplay Volume（室内外声音） | 室内体积 actor，或自动生成的屋顶深度图 | — |
| 四季多状态 | World Partition Data Layers（运行时按季节切换）、PCG 参数（本项目植被就是 PCG 生成的）、ISM 每实例自定义数据、材质 LUT | 季节变体资产（冰柱、结冰水面、稻田等）、叶色 LUT、落叶 | Megaplants 材质自带 `Seasons` 开关和 `Season Color 1/2`（秋色），但没有花期、落叶和积雪 |
| 季节推进与气候 | GameInstance 或 World Subsystem、存档 | 日历；每季的气候基线和天气概率 | — |
| NPC 感知 | AI Perception（视觉、听觉）、StateTree（项目已在用）、Smart Objects（避雨点）、Mass（人群） | 天气到感知系数的映射；避雨行为 | — |
| 角色 | Groom 毛发物理的 Air Velocity；Chaos Cloth 读风源；角色材质的湿度参数 | 风场驱动发丝和布料；湿身的累积与晾干 | 模板角色 Manny / Quinn 没有头发，也没有布料 |
| 声音 | MetaSounds、Soundscape 插件、Audio Gameplay Volume | 天气到声音参数的映射 | — |
| 氛围图 | 没有直接对应。候选：StateTree（状态与过渡）加曲线或数据资产（参数映射），或者自己写节点图编辑器 | 编排层 | — |

---

## 3. 本项目现状（和这件事有关的部分）

- **候选场景 `/Game/PyPCG/L_PyWorld`**：2×2 km 的山谷，有河流、道路、城镇和 280 万植被实例。
  - 关卡里已有 SkyAtmosphere、VolumetricCloud、ExponentialHeightFog、DirectionalLight、SkyLight、PostProcessVolume，都是静态的。
  - 没有风源、Niagara 和 Water Body；河是一张动态网格，材质 `M_PyWorldStream`。
- **渲染设置**：Lumen GI 和反射、硬件光追、Substrate（blendable GBuffer）、Nanite 植被（`r.Nanite.Foliage=1`）都开着。
- **树（Megaplants，City Sample PCG 插件）**：
  - 是静态的 Nanite 装配体，共 121 个 StaticMesh，没有骨骼或风资产。
  - 母材质 `MA_Foliage_Trees` 有 `Seasons` 开关、`Season Color 1/2`、`Health Color Overlay`（City Sample 用它做秋色），
    PyWorld 的夏季副本把它关了。
  - 材质里没有风、积雪和落叶参数。
- **草和灌木（Electric Dreams Megascans）**：插件的 MS Presets 里有现成的风材质函数（`MF_SimpleWind`、`MF_AdvancedWind`、`MF_WindGust`），
  还要查它们是否接进了正在用的材质。
- **植被是欧洲树种**（山毛榉、槭、山杨、桤木、榛、鹅耳枥），没有樱花、竹子和日本枫。春天的花期外观要么加资产，要么用材质近似。
- **已有的系统**：StateTree 插件已开；植被 W7 是 PCG 加 Python 生成的，可以加一个 Season 参数；Content/Audio 下有风声素材。
- **角色**：只有模板 Manny / Quinn，没有发丝和布料。

---

## 4. 选方案前要知道的难点

1. **Atmos 模拟的保真度**：
   - 真 3D 气象（Stormscapes 那一级）是研究级的工作量；
   - 2D 或分层近似便宜、可控；
   - 也可以不做模拟，只用“天气状态 + 区域 + 噪声”。
   物理越真越难让美术控制，Anvil 也是靠氛围图来驯服模拟的。
2. **延迟还是改材质**：Anvil 的延迟做法一个材质都不用改。UE 里不改引擎的话，要么写 C++ 渲染扩展，要么改所有母材质
   （Megaplants、ED Megascans、PyWorld 的地形、城镇和河流，以及室内）。
3. **280 万实例怎么换季**：
   - 走材质参数最便宜；
   - 重跑 W7 PCG 要 118 s，只能在换季时做；
   - Data Layer 存多份副本，占内存。
4. **资产缺口**：没有日本植被，没有冰柱、结冰水面和稻田，也没有带头发和布料的角色。
5. **风驱动 Nanite 植被**：Megaplants 的叶子是 Nanite 体素植被，WPO 风对体素叶子是否生效要验证；Dynamic Wind 需要骨骼数据。

---

## 5. 确认的范围与选定方案（2026-10-30）

**要做（14 项）**
- 天气核心：区域物理天气模拟；统一风场 + 喷溅粒子；云、雨雪与雷暴；氛围图（编排层）。
- 地表天气：雨湿与积水；积雪与融化；深雪变形；室内 / 屋檐遮挡。
- 四季：昼夜与季节日照；植被四季外观；多状态物体；季节推进与气候。
- 联动：角色联动（头发、衣服随风，淋湿、落雪）；天气声音。

**不做**：NPC 感知受环境影响；人群与动物反应。

**选定方案**

| 决定 | 选择 |
|---|---|
| 技术路线 | C++ 运行时插件 + GPU 计算：compute shader 跑大气模拟和近场风；湿、积水、积雪用延迟 GBuffer pass；StateTree 加数据资产做编排；另写一份纯 Python 参考实现做离线测试 |
| 模拟保真度 | 3D 网格（Stormscapes 简化版）：玩家周围约 8×8 km、高 6–8 km |
| 季节推进 | 离散换季，切换时有过渡 |
| 场景 | 先新建一个小型验收关卡，验收通过后再放到 L_PyWorld 山谷里测试 |
| 默认（未特别指定） | 角色用 MetaHuman（引擎自带 `MetaHumanCharacter` 插件）做发丝，衣服另配 Chaos Cloth；雨声、雷声、踩水声需要另找素材 |

**动手前要先验证的点**（在设计阶段定）
1. Substrate（blendable GBuffer）下，能否在 base pass 之后改写 GBuffer。
2. WPO 风对 Nanite 体素植被（Megaplants 的叶子）是否生效。
3. Volumetric Cloud 材质能否采样由 C++ 写入的 3D 渲染目标。
4. 能否在 MeshTerrain 上用 Nanite tessellation 做深雪置换。

**下一步**：分节走一遍设计（架构、模拟、风、延迟天气、云与降水、四季、角色与声音、测试），批准后写设计文档
（`docs/superpowers/specs/`），再写实现计划。

---

## 6. 可行性验证结果（2026-10-30）

在一个临时关卡（从 L_PyWorld 模板复制）和一个临时 C++ 插件里验证，结束后都删掉了。截图副本在 `docs/img/weather-spikes/`。

| # | 问题 | 结论 |
|---|---|---|
| 1 | Substrate 下能否在 base pass 之后改写 GBuffer | **可行** |
| 2 | WPO 风能否吹动 Megaplants 的叶子 | **照现状不行**：Nanite 装配体不计算 WPO，远处的体素叶子也不支持 WPO |
| 3 | 云能否采样 C++ 每帧写入的 3D 渲染目标 | **可行** |
| 4 | 能否在 MeshTerrain 上做深雪置换 | **一半**：运行时由 RT 驱动的 Nanite tessellation 置换可行；MeshTerrain 本身没验证成（运行时地形后来已修好，见 6.4） |
| 5 | PVE 导出的 Dynamic Wind 骨骼树能否随风摆动、能否换季（2026-11-02） | **可行**，但只接受全局风，见 6.5 |

### 6.1 GBuffer 改写（可行）

- **做法**：
  - 用 `FSceneViewExtensionBase::PostRenderBasePassDeferred_RenderThread`。
  - 按名字（`GBufferA/B/C`）从 base pass 的渲染目标里取出纹理。
  - 一个全屏 pass 写 GBufferB（只写 .b，即粗糙度）和 GBufferC（底色 RGB），同时读 GBufferA（法线）和深度。
  - 用固定功能混合：雪按覆盖度把底色插值到雪色、粗糙度插值到 0.75，只作用于朝上的面；湿把底色乘 0.55、粗糙度插值到 0.08。
- **结果**：
  - 雪只出现在朝上的面（石头顶、部分叶子、地面），树干、窗框、板边这类竖直面不受影响。
  - 湿让表面变暗，还能反射天空：Lumen 反射读到了改写后的值，阴影也正常。
  - 截图：`1_gbuffer_base` / `1_gbuffer_snow` / `1_gbuffer_wet`。
- **源码依据**：Substrate 用 blendable 格式时，base pass 会把材质导出成传统 GBuffer 布局（`BasePassPixelShader.usf` 的
  `SUBSTRATE_GBUFFER_FORMAT==0` 分支）。
- **没测或要注意的**：
  - 用 stencil 排除角色这一点没测。
  - Lumen surface cache 里的离屏表面看不到湿和雪；Anvil 也一样，漫反射 GI 不计算延迟天气。
  - 正式版要按视图矩形画，不能整张纹理全画。

### 6.2 WPO 风吹 Megaplants 叶子（照现状不行）

- **母材质那一层**：Megaplants 母材质走 material attributes，直接连 WPO 引脚无效，得接进属性链。
- **换成最小叶子材质后**：
  - 同一个材质让**单独的叶子网格**抬起了 15 m，但**整棵树**（Nanite 装配体）纹丝不动；
    `r.Nanite.Visualize EvaluateWPO` 里整棵树都是红色，即不计算 WPO（`2_wpo_assembly_vs_part`、`2_wpo_evaluate_view`）。
  - 即使是 25 m 处，叶子也已经全部是体素（`2_voxels_at_25m`）。
  - 源码里体素簇固定走 fixed-function 光栅化（`NaniteAttributeDecode.ush` 的 `RemapRasterBin`），只支持骨骼蒙皮，不支持材质 WPO。
- **结论**：Megaplants 是静态 Nanite 装配体加体素叶子，靠材质 WPO 吹不动。可选的路线：
  1. 用引擎的 Procedural Vegetation Editor 把树导出成带 Dynamic Wind 数据的骨骼网格。它的导出选项里有
     SkeletalMesh + Dynamic Wind，并自带山毛榉、槭、山杨、榛的样例；导出后由 Dynamic Wind 插件读风场纹理。
  2. 不用装配体和体素的普通 Nanite 树，可以继续用 WPO。
  3. 远处的树不摇。

  具体选哪条在设计阶段定。

### 6.3 云采样 C++ 写入的 3D 渲染目标（可行）

- **做法**：
  - 渲染目标是 `UTextureRenderTargetVolume`（64×64×32，RGBA16F，开 `bSupportsUAV`）。
  - 插件在 `PreRenderViewFamily_RenderThread` 里用 compute shader 每帧写入一团绕圈运动的密度，写完调用 `UseExternalAccessMode(SRV)`。
  - Volume 域的云材质把世界坐标映射到一个 8×8×4 km 的盒子，把采样值当作消光。
- **结果**：天空里出现一团体积云，44 s 后再截一张，位置变了（`3_cloud_t0` / `3_cloud_t1`）。关掉写入时，RT 是默认的绿色清屏色，
  整个云层都变成绿色，这也说明材质确实在读这张图。
- **要注意**：采样器类型要用 Color（引擎对这种 RT 的规则），坐标引脚名是 `UVs`。

### 6.4 MeshTerrain 深雪（一半）

- **Nanite tessellation 运行时置换：可行**。
  - 测试对象是一张 40 m 的 Nanite 平面，材质开 tessellation，Displacement 读一张运行时用 Canvas 画的 RT。
    Displacement 要经 Make Material Attributes 接入，因为 Python 的 `MaterialProperty` 枚举把 `MP_Displacement` 藏起来了。
  - 脚印和 60 cm 深的拖痕都压了下去，阴影正确（`4_tessellation_footprints`、`4_tessellation_furrow`）。
  - `r.Nanite.Tessellation` 在 5.8 里默认就是 1，不用改项目设置。
- **MeshTerrain 本身：没验证成**。
  - 编辑器里，MeshTerrain 由 MeshPartition 自己的预览 proxy 绘制（`FMegaMeshCustomPreviewSceneProxy`，普通顶点工厂，不是 Nanite），
    不可能做 tessellation。
  - 运行时它靠 compiled sections（Nanite 静态网格）。用 `WorldPartitionMeshPartitionBuilder` commandlet 构建后，日志写着
    “Built 2”，但没有保存任何包；进 Simulate 后 compiled section 只有一个空的远景组件，**地形根本不显示**（`4_meshterrain_runtime_empty`）。
  - 这说明本项目的 MeshTerrain 在运行时（PIE / 打包）可能是空的。这比深雪更基础，需要单独排查，L_PyWorld 很可能也一样。
- **建议**：深雪先做成玩家周围一块跟随地形的可变形 Nanite 雪面（已验证可行），MeshTerrain 的运行时构建另外排查。
- **后续（2026-11-02，另一个会话）**：运行时地形为空的原因是 `MPD_PyWorld` 没有 compiled-section 构建变体。加上 `MPD_Default`
  的碰撞变体和 Nanite 渲染变体后，L_PyWorld 的运行时地形是 Nanite 静态网格（traps 128–131，`docs/pyworld-guide.md` §3，未提交）。
  所以深雪也可以考虑直接在地形材质上开 tessellation，在设计里再定。

### 6.5 树的风：PVE 导出的 Dynamic Wind 骨骼树（2026-11-02，可行，但只接受全局风）

在一个临时工程 `E:\WindSpike` 里验证（只开了 PythonScriptPlugin、DynamicWind、ProceduralVegetationEditor 和 MCP 桥），
PCG_Claude 工程和引擎插件都没动。截图是 `5_*.jpg`。

- **导出**：
  - 源图是 PVE 自带的落叶乔木样例 `PVE_Sample_Deciduous_Tree_01`，Export 节点设为 Skeletal Mesh + Nanite Foliage（Voxelize）+
    `DefaultTreeWindSettings`。
  - 得到一个带 `DynamicWindSkeletalData` 的骨骼网格：1445 根骨骼，Nanite 619 万三角形。
  - 文件大小：根网格 6.7 MB，4 个叶片部件网格各 0.9–1.7 MB，骨架 0.27 MB；无叶版 23.6 MB。都远低于 GitHub 单文件 100 MB 的限制。
- **PVE 没有脚本接口**：
  - Export 是编辑器工具栏命令，会弹模态对话框。脚本在"无人值守"模式下运行，Slate 会直接取消模态窗口。
  - 临时写了一个 C++ 小工具：把命令排到下一帧执行，再在模态循环里点对话框的 Export 按钮。导出一次 13–15 s。
- **导出的资产只在内存里**：骨骼网格、骨架，以及装配体用到的叶片部件网格（`SKM_/SK_Leaf_Twig_*`）都不存盘。
  部件网格生成在源叶片网格旁边，这次就落在引擎插件目录里。正式流程要先把叶片源网格复制到 /Game，导出后再保存。
- **风**：
  - 树放在 `InstancedSkinnedMeshComponent` 上，Transform Provider 用 PVE 样例的 `Wind_TransformProvider`（`DynamicWindData`），
    由 `DynamicWindSubsystem.update_wind_parameters`（方向、速度、幅度、阵风纹理）驱动。
  - 风开时两帧之间有 33–35% 的像素变化，风关时 9–11%（剩下的是云和 TSR 噪声）。风向反过来，树也往反方向弯（`5_wind_direction`）。
  - **远处的体素叶子也跟着弯**（`5_wind_voxel_trees_bend`）：骨骼蒙皮作用在体素 brick 上
    （`NaniteRasterizer.usf` 的 `SampleVoxelPerBrickSkinningTransform`），不像 WPO 那样被跳过。
  - 屏幕占比小于 `AnimationMinScreenSize`（默认取 `r.Skinning.DefaultAnimationMinScreenSize = 0.1`）的树会停止摆动；
    按组件调低这个值，远处的树也会动（`5_wind_animation_cutoff`）。
  - Simulate 里也一样，在游戏世界的子系统上设风即可。
- **PCG 生成**：
  - 3 个节点的图：CreatePointsGrid → AddAttribute(Mesh) → Skinned Mesh Spawner（模板描述里设 Transform Provider）。
    生成了 900 棵和 40 000 棵会动的树（`5_pcg_grid_900_trees`）。
  - 从 Python 设属性选择器要用 `import_text('(Selection=Attribute,AttributeName="Mesh")')`；`set_attribute_name` 写出来的是
    `@Source`，节点会报错。
- **开销**：
  - 40 000 棵时 `DynamicWind Simulate` 只要 0.027 ms（184 个 block），和棵数无关。整帧 10.75 ms，对比风幅度为 0 时 10.29 ms，在噪声范围内。
  - **原因也是限制**（源码，`DynamicWindData.cpp`）：
    - Dynamic Wind 按"骨架 × 8 个朝向桶"批量计算。同一树种、朝向落在同一个 45° 桶里的树，动作完全一样。
    - 它只接受一个全局风（方向、速度、幅度，加一张 2D 阵风纹理），不按树的位置取风。
  - 要让树跟着我们的风场走（局部阵风、背风处不动），得把它改造成自己的 Transform Provider，在设计里展开。
- **换季**：
  - **秋**：复制叶片材质实例、改底色（关 `Seasons`、开 `Tint BaseColor`），运行时换到组件的叶片槽上。
    近处的三角形和远处的体素一起变色。
  - **冬，材质路线不行**：用材质把叶子遮掉（Opacity Mask = 0）只对近处三角形有效，远处的体素照样画（`5_leaf_mask_near_vs_voxel`）。
  - **冬，可行的路线**：同一张图关掉 Foliage Distributor 节点再导出一份无叶版本，得到 20.8 万三角形、同样 1445 根骨骼，风数据还在。
    运行时换组件的网格，900 实例的组件只要 0.2–0.4 ms，无叶的树照样随风摆（`5_season_swap_bare_autumn`）。
- **没验证的**：PVE 自带的山毛榉、槭、山杨、榛（和 Megaplants 同种）的 JSON 生长数据，能否直接生成对应树种。
- **剩下的**：`E:\WindSpike`（524 MB）因为是盘符下的顶层目录，被安全检查挡住没删，需要你手动删除。

### 6.6 顺带发现和改动

- **ISPC 权限**：引擎的 `ispc.exe` 权限被单独设成 Everyone 只读，导致项目重新生成 makefile 时 UBT 运行不了它。
  经你同意，已用 `icacls /reset` 恢复成继承权限（Users 可读、可执行）。
- **和 PCG_Codex 编辑器的冲突**：
  - PCG_Codex 编辑器开着时，两者共用引擎的 `UnrealEditor.exe`，UBT 会因为 Live Coding 互斥锁拒绝编译本项目；
    这次用 `-NoHotReloadFromIDE` 绕过。
  - UBT 顺带要重编引擎的 NetCore 模块，但 DLL 被 PCG_Codex 占用，链接失败。结果是引擎的 `UnrealEditor-NetCore.dll` 没变，
    `.lib` 重新生成了，`.pdb` 被删掉了。
  - 以后编译 C++ 最好先关掉 PCG_Codex 编辑器。
- **清理**：临时关卡、`/Game/Spikes` 资产、临时插件和脚本都已删除。当时被编辑器占用的那个孤儿文件
  （`Content/__ExternalActors__/Spikes/...`，被 gitignore 忽略）也在 2026-11-02 编辑器关闭后删掉了。

### 6.7 对设计的影响

- **地表天气**：确定走延迟 GBuffer pass，不用改任何材质；只有植被透光、积雪厚度这类需要几何或透光的效果才进材质。
- **Atmos 模拟到云**：确定由 compute shader 写 3D 渲染目标、云材质直接采样。
- **风吹树**：用 PVE 导出的 Dynamic Wind 骨骼树，用 PCG 的 Skinned Mesh Spawner 种。要按位置响应风场，
  得把 Dynamic Wind 改造成自己的 Transform Provider。换季时，秋天换叶片材质参数，冬天换无叶网格。
  草和灌木（ED Megascans，不是装配体）可以继续用 WPO，但要先单独确认。
- **深雪**：独立的可变形雪面网格（已验证），或者直接在地形材质上开 tessellation（运行时地形现在是 Nanite 静态网格，待验证）。

---

## 7. 参考

- Hädrich, Banuti, Pałubicki, Pirk, Michels. *Stormscapes: Simulating Cloud Dynamics in the Now*. ACM TOG 39(6), SIGGRAPH Asia 2020.
- Sébastien Lagarde. *Water drop* 系列博客（2012），关于雨和湿表面的物理渲染。
