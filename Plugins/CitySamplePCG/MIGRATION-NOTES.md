# CitySamplePCG — migration notes

Copied from `E:\CitySample 5.8\Plugins\Experimental\CitySamplePCG` on 2026-09-23 so
the City Sample PCG pipeline can be reused inside `E:\PCG_Claude`.

## What this plugin contains

| Path | Contents |
|---|---|
| `Content/Levels/PCG/PCG_1_1_Terrain` … `PCG_5_2_OuterForest` | **the 18 city-stage graphs** |
| `Content/PCG/DataAssets/Buildings/<CODE>/SGD_<CODE>_A` | **the 27 building style assets**, one per style code |
| `Content/PCG/DataAssets/Buildings/<CODE>/RULE_<CODE>_L##` | 240 shape-grammar rule assets |
| `Content/PCG/DataAssets/{RoofTops,Roads,Plazas,Piers}` | 220 further rule assets |
| `Content/PCG/` (top level) | `AssignBuildingShape`, `SetComplexBuildings`, `GridPartition`, `Crosswalks`, `Intersection_solving`, … |
| `Content/PCG/Primitives/Buildings/` | building-specific subgraphs (`BDF_BuildingFromSpline`, `LoadCitySampleData`, …) |
| `Content/Examples/` | 33 example graphs, incl. the 7-step `CitySample_Generator_Steps_*` and `City_Circular_1km_2_arteries*` |
| `Content/{Meshes,Materials,MSPresets,Megascans,Megaplants,BlackAlder}` | mesh/material/vegetation dependencies |
| `Content/Levels/L_CitySamplePCG_Demo.umap` | the demo level that hosts one PCGVolume per graph |

The **27 style codes** are `CHA…CHJ`, `NYAA…NYAF`, `NYG`, `NYGA`, `NYH`, `QBA`, `QBAA`,
`SFA…SFE`, `SFJ`.

## Descriptor change: two plugins removed

Epic's original descriptor declared seven plugins. `ModelContextProtocol` and
`AllToolsets` were **removed** here. Evidence: a byte scan of all 13061 migrated
`.uasset`/`.umap` files found **zero** references to `/Script/ModelContextProtocol`,
`/Script/AllToolsets`, or `/Script/ProceduralVegetation`.

- `ModelContextProtocol` would additionally start a **second HTTP MCP server**
  (default port 8000, `bAutoStartServer=false` by default) next to this project's
  existing `UnrealMcpBridge` on 8777.
- `AllToolsets` transitively enables **21 further toolset plugins**
  (`AIModuleToolset`, `EditorToolset`, `PCGToolset`, …), none referenced by content.

Both are editor-tooling only with no content, so dropping them reduces load cost and
an avoidable port conflict without removing anything the assets use.

The original descriptor is preserved as `CitySamplePCG.uplugin.orig`.

Modules the migrated content *does* reference, and which therefore must stay enabled:

| Module | Files referencing it |
|---|---|
| `/Script/PCG` | 266 |
| `/Script/PCGMeshPartitionInterop` | 23 |
| `/Script/GeometryScripting` | 14 |
| `/Script/PCGGeometryScriptInterop` | 6 |
| `/Script/ToolsetRegistry` | 1 |

## This plugin is content-only

No `Source/`, no `Binaries/`. Nothing to compile; enabling it is a mount, not a build.
The engine-side plugins it depends on already ship with prebuilt Win64 binaries.

## The dependency on the demo level

The 18 graphs read upstream stage data by **actor reference**, not by asset path.
Four assets reference the demo level's hand-drawn spline actors by name:

- `Examples/City/CitySample_Generator_Steps_1_Base` → `Artery_1`, `Artery_2`
- `Examples/City/CitySample_Generator_Steps_2_Districts` → `CityShape`
- `Levels/PCG/PCG_1_1_Terrain` → `Terrain_shaping_1`
- `Levels/PCG/PCG_3_1_3_Highways` → `Highway_Width`

So the graphs are inert on their own. Either work from the migrated
`L_CitySamplePCG_Demo` (which carries those actors as external actors), or draw
equivalent splines in whatever level hosts them.

## Re-fetching

The content is not tracked by git (see the root `.gitignore`). To restore it:

```powershell
.\Tools\sync-citysample-assets.ps1
```

That script robocopies from `E:\CitySample 5.8` and is byte-exact — verified on
2026-09-23 across all nine subtrees.
