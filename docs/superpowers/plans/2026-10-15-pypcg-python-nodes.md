# PyPCG: each City Sample stage graph as one Python node, and an 18-stage town — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn each of the 18 official City Sample PCG graphs into a slim graph. A slim graph keeps only parameter getters, scene reads and the engine's own generation nodes; one Python Data Processor node does all the remaining computation from a `.py` file. Then build a 1 km town from those 18 slim graphs, strictly in the 18-step order.

**Architecture:**
- **Stage module.** Each stage is a pure-Python module `pypcg/stages/sNN_*.py` with `PARAMS / INPUTS / OUTPUTS / run()`. It never imports `unreal`.
- **Host.** A host shim `pypcg/host.py` runs inside the engine's Python Data Processor node. It converts PCG data to and from plain `pypcg.geo` values, and calls `run()`.
- **Graph description.** A graph description `pypcg/graphs/sNN_*.py` (DSL) lists what the slim graph keeps. The builder writes it to `/Game/PyPCG/Slim|Town/PCG_*`.
- **C++ plugin.** The `PyPCGTools` plugin gains four functions. They cover what Python cannot do: building Polygon2D data, reading Polygon2D/spline data, and setting dynamic pins.
- **Verification.** V1 is offline pytest plus in-editor checks. V2 runs each slim graph in place of the official one in the demo level and compares statistics. V3 is town acceptance.

**Tech Stack:**
- UE 5.8.2 source build at `E:\UnrealEngine`.
- PCG, PCGPythonInterop (Beta), and GeometryScript polygon functions.
- The C++ editor plugin `PyPCGTools`.
- Editor Python, driven through the MCP bridge `run_unreal_script` (port 8777).
- Offline pytest on `C:\Python314\python.exe`.

**Spec:** `docs/superpowers/specs/2026-10-15-pypcg-python-nodes-design.md` (approved 2026-10-15).

## Global Constraints

- **Git staging.** Never stage `Config/DefaultEditor.ini` (the user's own change) or anything under `Saved/`.
- **Demo level.** Never save `/CitySamplePCG/Levels/L_CitySamplePCG_Demo`. It is open with dirty actors. Whenever the editor asks, the answer is **Don't Save**.
- **Protected mounts.** Never write assets under `/CitySamplePCG/`, `/PCGPrimitives*` or `/Engine/` (`/Engine/Transient` is allowed). New assets go under `/Game/PyPCG/`.
- **Editor processes.** Never kill an editor process. Ask the user to close it, then poll `tasklist | grep -i -E "UnrealEditor|LiveCoding"` every 30 s for up to 20 min.
- **Builds.** C++ builds need **both** editors closed: `E:\PCG_Claude` and `E:\PCG_Codex` share the engine. No engine-wide workarounds (no `-NoHotReloadFromIDE`, no edits to engine files).
- **Push and PR.** `main` is protected and needs a PR. Ask the user before any push or PR.
- **Commit trailer.** Every commit message ends with exactly one trailer line: `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- **Python bridge discipline** (traps.md 25, 31–33, 38):
  - Keep UObjects in function locals only; module globals hold JSON only.
  - Start one generation per bridge call and read its result in the next call.
  - Take one screenshot per call, and judge it in a later call.
  - Regenerate stages strictly in stage order, one per call.
- **Rotators.** Always use keywords: `unreal.Rotator(pitch=…, yaw=…, roll=…)`. The positional order is (roll, pitch, yaw).
- **Pure modules.** Stage modules and `pypcg.geo`, `pypcg.stage_api`, `pypcg.v2` never `import unreal`. Engine services reach a stage only through `ctx.ops`, plus surface objects passed in `inputs`.
- **Tests.**
  - Offline: `C:\Python314\python.exe -m pytest Tools/pypcg/tests -q` (system Python 3.14; the MCP venv lacks Pillow).
  - C++: `"E:\UnrealEngine\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "E:\PCG_Claude\PCG_Claude.uproject" -ExecCmds="Automation RunTests PyPCGTools; Quit" -unattended -nopause -nosplash -nullrhi -log`. Results are in `Saved/Logs/PCG_Claude.log`.
- **Winding.**
  - `pypcg.geo` polygons are counter-clockwise in the standard sense (positive shoelace area).
  - UE splines are different. `ReverseSpline(ForceCounterClockwise)` gives *negative* standard area (traps.md 41), and the official footprint splines come out that way. Keep each stage's official vertex order when it matters downstream.
- **Units.** cm and cm². Parameters named `*Size*` / `*Limit*` / `*Threshold*` that the official graphs give in m² stay in m²; the stage converts them.

## Rulings

These are decisions made while planning, where the spec is silent or loose. Each one is written down so it can be revisited.

| # | Ruling | Why | Cost if wrong |
|---|---|---|---|
| N1 | The stage signature is `run(inputs, params, ctx)`. `ctx.rng` is the `random.Random(f"{Seed}:{STAGE}")` that spec §2.2 says the host builds; `ctx.ops` carries the engine booleans. | Spec §2.2 writes the third argument as `seed`, but also says the host builds the Random. Passing the Random keeps stages free of seeding code. | A rename in stage files. |
| N2 | GeometryScript booleans are injected as `ctx.ops`. Offline tests use `FakeOps`, which does straight cuts of convex rings. The real booleans run in the editor (V1-in-editor reruns, V2). | Spec §3 V1 puts GeometryScript-dependent checks in the editor; stages must not import `unreal`. | Some invariants are checked only in the editor. |
| N3 | V2 ignores tags that contain `:` (`Type:…`, `Primitive:…`). Stages emit them only where a downstream filter needs them (`port_brief.py` lists those filters). | They are PCGPrimitives bookkeeping; the primitives re-tag their inputs themselves. | A downstream filter on such a tag would surface as a V2 downstream failure, which is caught. |
| N4 | The Python node holds a two-line inline script (`from pypcg import host` / `host.run("sNN_x", globals())`) rather than `ScriptPath`. | Spec §2.2 already chose inline. The §2.1 sketch shows `ScriptPath`. | None. |
| N5 | Per-graph seed parameters (e.g. Districts' `SubDistrictSeed`) merge into the slim graph's `Seed`. Unused official parameters (e.g. MainTower's `NewProperty`) are dropped. `Debug*`, `Partitioned` and `PartitionGridSize` are dropped (spec E7/E8). | Spec E6–E8. | V2 copies official overrides by name; dropped names are simply not copied. |
| N6 | Tasks 10–26 (stage ports) give a contract (pins, kept nodes, tags, parameters), concrete tests and a fixed protocol. The algorithm itself is written in each task's first step, as an algorithm note derived from the official IR and the primitive internals. | Each port is research against hundreds of official nodes. Writing their code now would be guessing; the contract and tests are what can be pinned down today. | Port tasks take longer than infrastructure tasks; reviewers check the note before the code. |
| N7 | Enabling the engine plugin `PCGPythonInterop` builds its binaries into `E:\UnrealEngine\Engine\Plugins\PCGInterops\PCGPythonInterop\`. Task 1 shows the dry-run file list to the user and builds only on their yes. If the user says no, the fallback is spec §4.3: a C++ wrapper node in `PyPCGTools`. | This is a write outside the worktree, and earlier ruling T1a required that check. | A day's detour for the fallback node. |
| N8 | Asset selection (`Assign_Assets`) goes into Python, as spec §2.4 says. `pypcg/ue/assets.py` loads PCG data-asset points and mesh bounds; the choice itself lives in `pypcg.geo`. | Spec §2.4 / E5. | If the expansion of assemblies is too slow, the risk table applies: put that one node back as native, and record it. |
| N9 | Stage 0 is a probe stage (`s00_probe`). It is built to `/Game/PyPCG/Probe/PCG_PyProbe` and is not part of the 18. | It validates every host path (types, terrain, empty input, polygon output, timing) once, before the real ports. | None. |

## Review Focus

These are the failure modes most likely to bite, each pinned by a test in the task that owns the code:

1. **An empty upstream input** (e.g. the town has no lots under a highway, so there is no `UnderHighway`). The stage must run and emit empty pins rather than raise. Tested by `test_empty_inputs_*` in Task 8 (Districts), and required by the port protocol for every port.
2. **A parameter that exists in the graph but not in the module, or the reverse** (a renamed parameter). The node must fail loudly with both lists. Tested by `test_execute_reports_param_mismatch` (Task 4).
3. **Zero-area slivers from booleans.** They must be dropped and noted, never emitted. Tested by `test_auto_split_drops_slivers` (Task 3) and `test_cut_keeps_only_real_pieces` (Task 8).
4. **The seed must reproduce across editor sessions** (no `hash()`). Tested by `test_ctx_rng_is_session_independent` (Task 4).
5. **An edited stage `.py` must take effect on the next generation, without an editor restart.** Tested by `test_fresh_drops_cached_pypcg_modules` (Task 4) and by Task 6 Step 6 in the editor.

---

## File Structure

| Path | Responsibility |
|---|---|
| `Plugins/PyPCGTools/Source/PyPCGTools/{Public,Private}/PyPCGToolsLibrary.*` | Adds `MakePolygon2DData`, `Polygon2DToJson`, `SplineDataToJson`, `SetDynamicPinLabels` (Task 1) |
| `Plugins/PyPCGTools/Source/PyPCGTools/Private/Tests/PyPCGToolsTests.cpp` | +3 automation tests: 9 in total (Task 1) |
| `PCG_Claude.uproject` | Enables `PCGPythonInterop` (Task 1) |
| `Tools/pypcg/reference_drafts/` | The 18 node-by-node drafts, retired from `pypcg/stages/` (Task 2) |
| `Content/Python/pypcg/geo/{__init__,types,plane,sample,subdivide}.py` | Pure geometry and value types (Task 3, extended by ports) |
| `Content/Python/pypcg/stage_api.py` | The stage contract: `Param`, `param_specs`, `Ctx`, `execute`, `record` (Task 4) |
| `Content/Python/pypcg/host.py` | What every Python node runs (Task 4) |
| `Content/Python/pypcg/ue/{__init__,convert,ops,terrain,assets}.py` | Editor-only adapters: PCG data ↔ geo, GeometryScript booleans, terrain heights, PCG data-asset points (Tasks 4, 11) |
| `Content/Python/pypcg/dsl.py` | +`SlimGraph`, `python()`, `keep()`, `self_point()`, `official_param()` (Task 5) |
| `Content/Python/pypcg/build.py` | +`build_slim()`, Python-node class path, dynamic pins, slim layout (Task 5) |
| `Content/Python/pypcg/compare.py` | +`slim_normalize()`, `slim_diff()` (Task 5) |
| `Content/Python/pypcg/graphs/{__init__,sNN_*}.py` | One slim-graph description per stage (Task 5 onward) |
| `Content/Python/pypcg/stages/{__init__,s00_probe,sNN_*}.py` | `STAGES`, `DOWNSTREAM`; the probe; one Python stage per graph (Tasks 2, 6, 8, 10–24) |
| `Content/Python/pypcg/checks/sNN.py` | V1 invariants that need real booleans or recorded runs (Task 7 onward) |
| `Content/Python/pypcg/v2.py`, `v2_thresholds.json` | Pure V2 statistics and verdicts (Task 7) |
| `Content/Python/pypcg/census.py` | Editor-only: a volume's outputs per tag, and its instances per mesh (Task 7) |
| `Content/Python/pypcg_build_slim.py`, `pypcg_probe_node.py`, `pypcg_compare_stage.py`, `pypcg_v1_editor.py` | Bridge entry scripts (Tasks 5–7) |
| `Tools/pypcg/port_brief.py` | Per-stage contract extractor from the official IR (Task 7) |
| `Tools/pypcg/tests/{fakes,test_geo,test_stage_api,test_host,test_slim_dsl,test_v2,test_port_brief,test_sNN}.py` | Offline tests |
| `docs/pypcg/stages/sNN.md` | Per-port algorithm notes (Tasks 12–23) |
| `docs/pypcg-v2-thresholds.md` | Log of every threshold change (Task 7 onward) |
| `Content/Python/pypcg/profiles/{official,town,town_layout}.py`, `town_bindings.json` | Role bindings and the town layout (Tasks 7, 25, 26) |
| `Content/Python/pypcg/town_checks.py`, `Content/Python/pypcg_town_level.py`, `Content/Python/pypcg_town.py`, `Tools/pypcg/town_manifest.py` | The town (Tasks 25–28) |
| `docs/pypcg-guide.md` | The user guide (Task 28) |

---

## Phase P0 — Infrastructure

### Task 1: Enable PCGPythonInterop and extend `PyPCGTools`

**Files:**
- Modify: `PCG_Claude.uproject` (plugin list)
- Modify: `Plugins/PyPCGTools/Source/PyPCGTools/PyPCGTools.Build.cs`
- Modify: `Plugins/PyPCGTools/Source/PyPCGTools/Public/PyPCGToolsLibrary.h`
- Modify: `Plugins/PyPCGTools/Source/PyPCGTools/Private/PyPCGToolsLibrary.cpp`
- Test: `Plugins/PyPCGTools/Source/PyPCGTools/Private/Tests/PyPCGToolsTests.cpp`
- Modify: `CLAUDE.md` (the test count: six → nine)

**Interfaces — Produces** (Python names in brackets):
- `UPCGPolygon2DData* MakePolygon2DData(const FString& Json)` [`make_polygon2d_data(json) -> PCGPolygon2DData | None`]
  - JSON: `{"outer": [[x,y,z],...], "holes": [[[x,y,z],...],...]}` in world cm.
  - Frame and winding as `CreatePolygon2D` builds them.
- `FString Polygon2DToJson(const UPCGPolygon2DData*)` [`polygon2d_to_json(data) -> str`]: the same JSON shape, in world cm.
- `FString SplineDataToJson(const UPCGSplineData*, float MaxSquareDistance)` [`spline_data_to_json(data, tol) -> str`]
  - JSON: `{"closed": b, "polyline": [[x,y,z],...], "control": [{"p":[..],"arrive":[..],"leave":[..],"type": int}]}`, world cm.
  - `type` is `ESplinePointType`: 0 Linear, 1 Curve, 2 Constant, 3 CurveClamped, 4 CurveCustomTangent.
- `FString SetDynamicPinLabels(UPCGSettings*, const TArray<FString>& Inputs, const TArray<FString>& Outputs)` [`set_dynamic_pin_labels(settings, [..], [..]) -> str`]
  - Returns `""` on success, otherwise the error.

- [ ] **Step 1: Enable the plugin and add the module dependency**

In `PCG_Claude.uproject`, add after the `"PCGPrimitives_MeshPartitionInterop"` entry:

```json
		{
			"Name": "PCGPythonInterop",
			"Enabled": true
		},
```

In `PyPCGTools.Build.cs`, change the private dependency list to:

```csharp
		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"PCG",
			"Json",
			"JsonUtilities",
			"GeometryCore",
		});
```

- [ ] **Step 2: Write the failing automation tests** — insert before the final `#endif // WITH_DEV_AUTOMATION_TESTS` in `PyPCGToolsTests.cpp`, and add `#include "Data/PCGPolygon2DData.h"`, `#include "Data/PCGSplineData.h"`, `#include "PCGPin.h"` to the includes at the top:

```cpp
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPyPCGToolsPolygon2D, "PyPCGTools.Polygon2D",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FPyPCGToolsPolygon2D::RunTest(const FString& Parameters)
{
	using namespace PyPCGToolsTests;
	// A 10 m square at z 100 with a 2 m square hole. The outer ring is given clockwise; it must
	// come back counter-clockwise, in a frame centred on the ring like CreatePolygon2D's.
	UPCGPolygon2DData* Data = UPyPCGToolsLibrary::MakePolygon2DData(TEXT(R"({"outer":[[0,0,100],[0,1000,100],[1000,1000,100],[1000,0,100]],
		"holes":[[[400,400,100],[600,400,100],[600,600,100],[400,600,100]]]})"));
	if (!TestNotNull(TEXT("polygon made"), Data))
	{
		return false;
	}
	TestTrue(TEXT("frame origin at the centroid"), Data->GetTransform().GetLocation().Equals(FVector(500, 500, 100), 1e-6));
	TestFalse(TEXT("outer counter-clockwise"), Data->GetPolygon().OuterIsClockwise());
	TestEqual(TEXT("hole count"), Data->GetPolygon().GetHoles().Num(), 1);
	TestEqual(TEXT("area"), Data->GetPolygon().Area(), 1000.0 * 1000.0 - 200.0 * 200.0, 1e-6);

	const TSharedPtr<FJsonObject> Back = Parse(UPyPCGToolsLibrary::Polygon2DToJson(Data));
	const TArray<TSharedPtr<FJsonValue>> Outer = Back->GetArrayField(TEXT("outer"));
	TestEqual(TEXT("outer vertex count"), Outer.Num(), 4);
	for (const FVector Corner : {FVector(0, 0, 100), FVector(1000, 0, 100), FVector(1000, 1000, 100), FVector(0, 1000, 100)})
	{
		bool bFound = false;
		for (const TSharedPtr<FJsonValue>& Value : Outer)
		{
			const TArray<TSharedPtr<FJsonValue>> Xyz = Value->AsArray();
			bFound |= FVector(Xyz[0]->AsNumber(), Xyz[1]->AsNumber(), Xyz[2]->AsNumber()).Equals(Corner, 1e-6);
		}
		TestTrue(*FString::Printf(TEXT("corner %s round-trips"), *Corner.ToString()), bFound);
	}
	TestEqual(TEXT("hole round-trips"), Back->GetArrayField(TEXT("holes")).Num(), 1);
	TestNull(TEXT("two vertices refused"), UPyPCGToolsLibrary::MakePolygon2DData(TEXT(R"({"outer":[[0,0,0],[1,0,0]]})")));
	TestNull(TEXT("bad JSON refused"), UPyPCGToolsLibrary::MakePolygon2DData(TEXT("{")));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPyPCGToolsSplineJson, "PyPCGTools.SplineJson",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FPyPCGToolsSplineJson::RunTest(const FString& Parameters)
{
	using namespace PyPCGToolsTests;
	UPCGSplineData* Spline = NewObject<UPCGSplineData>(GetTransientPackage());
	TArray<FSplinePoint> Points;
	const FVector Corners[] = {FVector(0, 0, 0), FVector(1000, 0, 0), FVector(1000, 500, 0), FVector(0, 500, 0)};
	for (int32 Index = 0; Index < 4; ++Index)
	{
		FSplinePoint& Point = Points.AddDefaulted_GetRef();
		Point.InputKey = static_cast<float>(Index);
		Point.Position = Corners[Index];
		Point.Type = ESplinePointType::Linear;
	}
	Spline->K2_Initialize(Points, /*bInClosedLoop=*/true, FTransform(FVector(100, 0, 0)), {});
	const TSharedPtr<FJsonObject> Json = Parse(UPyPCGToolsLibrary::SplineDataToJson(Spline, 1.0f));
	TestTrue(TEXT("closed"), Json->GetBoolField(TEXT("closed")));
	const TArray<TSharedPtr<FJsonValue>> Control = Json->GetArrayField(TEXT("control"));
	if (!TestEqual(TEXT("control points"), Control.Num(), 4))
	{
		return false;
	}
	const TArray<TSharedPtr<FJsonValue>> P0 = Control[0]->AsObject()->GetArrayField(TEXT("p"));
	TestTrue(TEXT("control point in world space"), FVector(P0[0]->AsNumber(), P0[1]->AsNumber(), P0[2]->AsNumber()).Equals(FVector(100, 0, 0), 1e-6));
	TestEqual(TEXT("linear type"), static_cast<int32>(Control[0]->AsObject()->GetNumberField(TEXT("type"))), 0);
	const TArray<TSharedPtr<FJsonValue>> Polyline = Json->GetArrayField(TEXT("polyline"));
	for (const FVector& Corner : Corners)
	{
		bool bFound = false;
		for (const TSharedPtr<FJsonValue>& Value : Polyline)
		{
			const TArray<TSharedPtr<FJsonValue>> Xyz = Value->AsArray();
			bFound |= FVector(Xyz[0]->AsNumber(), Xyz[1]->AsNumber(), Xyz[2]->AsNumber()).Equals(Corner + FVector(100, 0, 0), 1e-3);
		}
		TestTrue(*FString::Printf(TEXT("polyline has corner %s"), *Corner.ToString()), bFound);
	}
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPyPCGToolsDynamicPins, "PyPCGTools.DynamicPins",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FPyPCGToolsDynamicPins::RunTest(const FString& Parameters)
{
	using namespace PyPCGToolsTests;
	UClass* PythonNode = FindObject<UClass>(nullptr, TEXT("/Script/PCGPythonInteropEditor.PCGPythonDataProcessorSettings"));
	if (!TestNotNull(TEXT("PCGPythonInterop is loaded"), PythonNode))
	{
		return false;
	}
	UPCGGraph* Graph = NewGraph();
	UPCGSettings* Settings = nullptr;
	UPCGNode* Node = Graph->AddNodeOfType(PythonNode, Settings);
	TestEqual(TEXT("set pins"), UPyPCGToolsLibrary::SetDynamicPinLabels(Settings,
		TArray<FString>({TEXT("Params"), TEXT("City")}), TArray<FString>({TEXT("Areas"), TEXT("Roads")})), FString());
	TArray<FString> In, Out;
	for (const TObjectPtr<UPCGPin>& Pin : Node->GetInputPins())
	{
		In.Add(Pin->Properties.Label.ToString());
	}
	for (const TObjectPtr<UPCGPin>& Pin : Node->GetOutputPins())
	{
		Out.Add(Pin->Properties.Label.ToString());
	}
	TestTrue(TEXT("Params pin"), In.Contains(TEXT("Params")));
	TestTrue(TEXT("City pin"), In.Contains(TEXT("City")));
	TestFalse(TEXT("default Input pin gone"), In.Contains(TEXT("Input")));
	TestTrue(TEXT("Areas pin"), Out.Contains(TEXT("Areas")));
	TestTrue(TEXT("Roads pin"), Out.Contains(TEXT("Roads")));
	TestFalse(TEXT("default Output pin gone"), Out.Contains(TEXT("Output")));
	TestNotEqual(TEXT("duplicate labels refused"), UPyPCGToolsLibrary::SetDynamicPinLabels(Settings,
		TArray<FString>({TEXT("A"), TEXT("A")}), TArray<FString>()), FString());
	UPCGSettings* Maths = nullptr;
	Graph->AddNodeOfType(UPCGMetadataMathsSettings::StaticClass(), Maths);
	TestNotEqual(TEXT("node without dynamic pins refused"), UPyPCGToolsLibrary::SetDynamicPinLabels(Maths,
		TArray<FString>({TEXT("A")}), TArray<FString>()), FString());
	return true;
}
```

They cannot compile yet: the four functions do not exist.

- [ ] **Step 3: Declare the functions.** In `PyPCGToolsLibrary.h`:
  - add `class UPCGPolygon2DData;` and `class UPCGSplineData;` beside the other forward declarations;
  - change the top comment's second line to: `// Every write returns an empty string on success, otherwise an error message; MakePolygon2DData returns null on bad input; nothing asserts.`;
  - insert before the closing `};`:

```cpp
	/** A Polygon2D data built the way CreatePolygon2D builds one, from {"outer": [[x,y,z],...],
	 *  "holes": [[[x,y,z],...],...]} in world cm: frame on the best-fit plane of the outer ring with its
	 *  centroid as origin, outer counter-clockwise, holes clockwise. Null (and a warning) on bad input. */
	UFUNCTION(BlueprintCallable, Category = "PyPCG")
	static UPCGPolygon2DData* MakePolygon2DData(const FString& Json);

	/** {"outer": [[x,y,z],...], "holes": [[[x,y,z],...],...]} in world cm. */
	UFUNCTION(BlueprintCallable, Category = "PyPCG")
	static FString Polygon2DToJson(const UPCGPolygon2DData* Data);

	/** {"closed": b, "polyline": [[x,y,z],...], "control": [{"p","arrive","leave","type"}, ...]} in world cm.
	 *  The polyline is the spline's own ConvertSplineToPolyLine(World, MaxSquareDistance). */
	UFUNCTION(BlueprintCallable, Category = "PyPCG")
	static FString SplineDataToJson(const UPCGSplineData* Data, float MaxSquareDistance);

	/** Replaces the dynamic input and output pins of a node whose settings provide dynamic pins (the
	 *  Python Data Processor) with Any-typed, multi-connection, multi-data pins with these labels, in order. */
	UFUNCTION(BlueprintCallable, Category = "PyPCG")
	static FString SetDynamicPinLabels(UPCGSettings* Settings, const TArray<FString>& InputLabels, const TArray<FString>& OutputLabels);
```

- [ ] **Step 4: Implement them.** In `PyPCGToolsLibrary.cpp`, add to the includes:

```cpp
#include "CompGeom/PolygonTriangulation.h"
#include "Components/SplineComponent.h"
#include "Curve/GeneralPolygon2.h"
#include "Data/PCGPolygon2DData.h"
#include "Data/PCGSplineData.h"
#include "PCGDynamicPins.h"
#include "Polygon2.h"
```

and append at the end of the file:

```cpp
namespace PyPCGTools::Private
{
	TSharedPtr<FJsonValue> VectorJson(const FVector& V)
	{
		return NumberArray({V.X, V.Y, V.Z});
	}

	bool ReadVectors(const TArray<TSharedPtr<FJsonValue>>& In, TArray<FVector>& Out)
	{
		for (const TSharedPtr<FJsonValue>& Value : In)
		{
			const TArray<TSharedPtr<FJsonValue>>* Xyz = nullptr;
			if (!Value.IsValid() || !Value->TryGetArray(Xyz) || Xyz->Num() < 2)
			{
				return false;
			}
			Out.Emplace((*Xyz)[0]->AsNumber(), (*Xyz)[1]->AsNumber(), Xyz->Num() > 2 ? (*Xyz)[2]->AsNumber() : 0.0);
		}
		return true;
	}

	UPCGPolygon2DData* RefusePolygon(const FString& Why)
	{
		UE_LOG(LogTemp, Warning, TEXT("MakePolygon2DData: %s"), *Why);
		return nullptr;
	}
}

UPCGPolygon2DData* UPyPCGToolsLibrary::MakePolygon2DData(const FString& Json)
{
	FString Error;
	const TSharedPtr<FJsonObject> Parsed = ParseObject(Json, Error);
	if (!Parsed)
	{
		return RefusePolygon(Error);
	}
	const TArray<TSharedPtr<FJsonValue>>* OuterJson = nullptr;
	TArray<FVector> Outer;
	if (!Parsed->TryGetArrayField(TEXT("outer"), OuterJson) || !ReadVectors(*OuterJson, Outer) || Outer.Num() < 3)
	{
		return RefusePolygon(TEXT("'outer' needs at least 3 [x,y,z] vertices"));
	}
	TArray<TArray<FVector>> Holes;
	const TArray<TSharedPtr<FJsonValue>>* HolesJson = nullptr;
	if (Parsed->TryGetArrayField(TEXT("holes"), HolesJson))
	{
		for (const TSharedPtr<FJsonValue>& HoleValue : *HolesJson)
		{
			const TArray<TSharedPtr<FJsonValue>>* HoleJson = nullptr;
			TArray<FVector>& Hole = Holes.AddDefaulted_GetRef();
			if (!HoleValue.IsValid() || !HoleValue->TryGetArray(HoleJson) || !ReadVectors(*HoleJson, Hole) || Hole.Num() < 3)
			{
				return RefusePolygon(TEXT("every hole needs at least 3 [x,y,z] vertices"));
			}
		}
	}

	// The frame UPCGCreatePolygon2DElement uses: best-fit plane through the outer ring, origin at its
	// centroid, normal facing up (spline data's normal), rotation MakeFromZ(normal). A degenerate ring
	// keeps the up normal, as the engine does.
	FVector Normal = FVector::UpVector;
	FVector Centroid = FVector::ZeroVector;
	const double Area = PolygonTriangulation::ComputePolygonPlane<double>(Outer, Normal, Centroid);
	const FBox Bounds(Outer);
	if (Area <= UE_SMALL_NUMBER * FMath::Square(Bounds.GetSize().GetMax()))
	{
		Normal = FVector::UpVector;
	}
	if ((Normal | FVector::UpVector) < 0)
	{
		Normal = -Normal;
	}
	FTransform Plane;
	Plane.SetRotation(FRotationMatrix::MakeFromZ(Normal).ToQuat());
	Plane.SetLocation(Centroid);

	auto ToPlane = [&Plane](const TArray<FVector>& Points)
	{
		TArray<FVector2D> Local;
		Local.Reserve(Points.Num());
		for (const FVector& Point : Points)
		{
			const FVector L = Plane.InverseTransformPosition(Point);
			Local.Emplace(L.X, L.Y);
		}
		return UE::Geometry::FPolygon2d(Local);
	};

	UE::Geometry::FGeneralPolygon2d Polygon;
	Polygon.SetOuter(ToPlane(Outer));
	if (Polygon.OuterIsClockwise())
	{
		Polygon.Reverse();
	}
	for (const TArray<FVector>& Hole : Holes)
	{
		UE::Geometry::FPolygon2d Local = ToPlane(Hole);
		if (!Local.IsClockwise())
		{
			Local.Reverse();
		}
		Polygon.AddHole(MoveTemp(Local), /*bCheckContainment=*/false, /*bCheckOrientation=*/false);
	}

	UPCGPolygon2DData* Data = NewObject<UPCGPolygon2DData>(GetTransientPackage());
	Data->SetPolygon(MoveTemp(Polygon));
	Data->SetTransform(Plane);
	return Data;
}

FString UPyPCGToolsLibrary::Polygon2DToJson(const UPCGPolygon2DData* Data)
{
	const TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	if (!Data)
	{
		Root->SetStringField(TEXT("error"), TEXT("null data"));
		return Write(Root);
	}
	const FTransform Transform = Data->GetTransform();
	auto World = [&Transform](const UE::Geometry::FPolygon2d& Ring)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
		for (const FVector2d& V : Ring.GetVertices())
		{
			Out.Add(VectorJson(Transform.TransformPosition(FVector(V.X, V.Y, 0.0))));
		}
		return Out;
	};
	const UE::Geometry::FGeneralPolygon2d& Polygon = Data->GetPolygon();
	Root->SetArrayField(TEXT("outer"), World(Polygon.GetOuter()));
	TArray<TSharedPtr<FJsonValue>> Holes;
	for (const UE::Geometry::FPolygon2d& Hole : Polygon.GetHoles())
	{
		Holes.Add(MakeShared<FJsonValueArray>(World(Hole)));
	}
	Root->SetArrayField(TEXT("holes"), Holes);
	return Write(Root);
}

FString UPyPCGToolsLibrary::SplineDataToJson(const UPCGSplineData* Data, float MaxSquareDistance)
{
	const TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	if (!Data)
	{
		Root->SetStringField(TEXT("error"), TEXT("null data"));
		return Write(Root);
	}
	TArray<FVector> Polyline;
	Data->SplineStruct.ConvertSplineToPolyLine(ESplineCoordinateSpace::World, MaxSquareDistance, Polyline);
	TArray<TSharedPtr<FJsonValue>> PolylineJson;
	for (const FVector& Point : Polyline)
	{
		PolylineJson.Add(VectorJson(Point));
	}
	const FTransform Transform = Data->GetTransform();
	TArray<TSharedPtr<FJsonValue>> Control;
	for (const FSplinePoint& Point : Data->GetSplinePoints())
	{
		const TSharedRef<FJsonObject> PointJson = MakeShared<FJsonObject>();
		PointJson->SetField(TEXT("p"), VectorJson(Transform.TransformPosition(Point.Position)));
		PointJson->SetField(TEXT("arrive"), VectorJson(Transform.TransformVector(Point.ArriveTangent)));
		PointJson->SetField(TEXT("leave"), VectorJson(Transform.TransformVector(Point.LeaveTangent)));
		PointJson->SetNumberField(TEXT("type"), static_cast<int32>(Point.Type.GetValue()));
		Control.Add(MakeShared<FJsonValueObject>(PointJson));
	}
	Root->SetBoolField(TEXT("closed"), Data->IsClosed());
	Root->SetArrayField(TEXT("polyline"), PolylineJson);
	Root->SetArrayField(TEXT("control"), Control);
	return Write(Root);
}

FString UPyPCGToolsLibrary::SetDynamicPinLabels(UPCGSettings* Settings, const TArray<FString>& InputLabels, const TArray<FString>& OutputLabels)
{
	if (!Settings)
	{
		return TEXT("null settings");
	}
	FString Error;
	if (IsProtected(Settings, Error))
	{
		return Error;
	}
	IPCGDynamicPinsProvider* Provider = Cast<IPCGDynamicPinsProvider>(Settings);
	if (!Provider)
	{
		return FString::Printf(TEXT("%s has no dynamic pins"), *Settings->GetClass()->GetName());
	}
	for (const TArray<FString>* Labels : {&InputLabels, &OutputLabels})
	{
		TSet<FString> Seen;
		for (const FString& Label : *Labels)
		{
			if (Label.IsEmpty() || Seen.Contains(Label))
			{
				return FString::Printf(TEXT("empty or duplicate pin label '%s'"), *Label);
			}
			Seen.Add(Label);
		}
	}
	Settings->Modify();
	auto Replace = [Provider](EPCGPinDirection Direction, const TArray<FString>& Labels)
	{
		FPCGDynamicPinContainer* Container = Provider->GetMutableDynamicPinContainer(Direction);
		if (!Container)
		{
			return false;
		}
		Container->PinProperties.Reset();
		for (const FString& Label : Labels)
		{
			Container->PinProperties.Emplace(FName(*Label), EPCGDataType::Any, /*bAllowMultipleConnections=*/true, /*bAllowMultipleData=*/true);
		}
		return true;
	};
	if (!Replace(EPCGPinDirection::Input, InputLabels) || !Replace(EPCGPinDirection::Output, OutputLabels))
	{
		return TEXT("settings lack an input or an output dynamic pin container");
	}
	RefreshNode(Settings);
	return FString();
}
```

- [ ] **Step 5: Ask the user to close both editors.** `E:\PCG_Claude` is open on the demo level; tell the user to answer **Don't Save**. `E:\PCG_Codex` must be closed too. Wait with the polling loop from Global Constraints.

- [ ] **Step 6: Dry-run the build and show the user what lands outside the project** (Ruling N7):

```bash
cmd //c "E:\UnrealEngine\Engine\Build\BatchFiles\Build.bat PCG_ClaudeEditor Win64 Development -Project=E:\PCG_Claude\PCG_Claude.uproject -WaitMutex -WriteOutdatedActions=E:\PCG_Claude\Saved\Reports\pypcg_ubt_actions_p0.json"
C:/Python314/python.exe -c "import json;d=json.load(open('Saved/Reports/pypcg_ubt_actions_p0.json',encoding='utf-8'));items=sorted({p for a in d.get('Actions',[]) for p in a.get('ProducedItems',[]) if not p.lower().startswith('e:\\\\pcg_claude')});print(len(items));print('\n'.join(items))"
```

Expected: the only outside items are under `E:\UnrealEngine\Engine\Plugins\PCGInterops\PCGPythonInterop\` (its DLL, PDB, `UnrealEditor.modules`, `Intermediate`). Show the user the list and ask whether to build. **Build only on a yes.** If the list contains other engine paths, show them too and ask. On a no, stop and report: the fallback is spec §4.3, a wrapper node in `PyPCGTools`.

- [ ] **Step 7: Build**

```bash
cmd //c "E:\UnrealEngine\Engine\Build\BatchFiles\Build.bat PCG_ClaudeEditor Win64 Development -Project=E:\PCG_Claude\PCG_Claude.uproject -WaitMutex"
```

Expected: exit 0, `Result: Succeeded`, no warnings from `PyPCGToolsLibrary.cpp`.

- [ ] **Step 8: Run the automation tests**

```bash
"/e/UnrealEngine/Engine/Binaries/Win64/UnrealEditor-Cmd.exe" "E:/PCG_Claude/PCG_Claude.uproject" -ExecCmds="Automation RunTests PyPCGTools; Quit" -unattended -nopause -nosplash -nullrhi -log
grep -E "Test Completed. Result=|TEST COMPLETE. EXIT CODE" Saved/Logs/PCG_Claude.log
```

Expected: 9 × `Result={Success}`, `EXIT CODE: 0`.

- [ ] **Step 9: Update CLAUDE.md.** In the Tests section, change the two places that say six tests to nine. Add `PCGPythonInterop` to the "Plugins enabled" list.

- [ ] **Step 10: Commit**

```bash
git add PCG_Claude.uproject Plugins/PyPCGTools CLAUDE.md
git commit -m "Enable PCGPythonInterop and add the Polygon2D, spline and dynamic-pin helpers to PyPCGTools" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Retire the node-by-node drafts

The new stage modules take the paths `pypcg/stages/sNN_*.py`, so the 18 codegen drafts move to `Tools/pypcg/reference_drafts/`. They stay as reference material for the ports. Their L1 test keeps running against the snapshots.

**Files:**
- Move: `Content/Python/pypcg/stages/s01_terrain.py … s18_outer_forest.py` → `Tools/pypcg/reference_drafts/`
- Create: `Tools/pypcg/reference_drafts/__init__.py`
- Modify: `Content/Python/pypcg/stages/__init__.py`, `Tools/pypcg/codegen.py`, `Tools/pypcg/tests/test_stages_l1.py`, `Content/Python/pypcg_build.py`

**Interfaces — Produces:**
- `pypcg.stages`: `STAGES`, `PROBE = (0, "PCG_PyProbe", "s00_probe", "探针")`, `entry(n)` (accepts 0), `name(n)`, `names()`, `official_path(n)`, `LABEL = name`.
- `pypcg.stages.DOWNSTREAM = {stage: [stages that read it by actor reference]}`.
- `reference_drafts.graph(n) -> dsl.Graph`.

- [ ] **Step 1: Move the files**

```bash
mkdir -p Tools/pypcg/reference_drafts
git mv Content/Python/pypcg/stages/s0[1-9]_*.py Content/Python/pypcg/stages/s1[0-8]_*.py Tools/pypcg/reference_drafts/
```

- [ ] **Step 2: Write `Tools/pypcg/reference_drafts/__init__.py`**

```python
"""The 18 node-by-node drafts of the official graphs (2026-10-14, commit fe380a1), kept as reference
for the Python ports. Each module's build() returns a pypcg.dsl.Graph equal to the official graph."""
import importlib

from pypcg import stages


def graph(n):
    return importlib.import_module("reference_drafts." + stages.entry(n)[2]).build()
```

- [ ] **Step 3: Rewrite `Content/Python/pypcg/stages/__init__.py`**

```python
"""The 18 stages in the Feishu doc's order (ruling R1), and stage 0, the host probe.

Stage modules (sNN_*.py) follow pypcg.stage_api; the slim graph that runs each one is described in
pypcg/graphs/sNN_*.py."""
import importlib

OFFICIAL_DIR = "/CitySamplePCG/Levels/PCG/"

STAGES = [
    (1, "PCG_1_1_Terrain", "s01_terrain", "地形底座"),
    (2, "PCG_1_2_BG_Buildings", "s02_bg_buildings", "远景天际线"),
    (3, "PCG_1_3_BG_Mountains", "s03_bg_mountains", "远景山体"),
    (4, "PCG_2_1_MainTower_Footprint", "s04_main_tower_footprint", "主塔占位"),
    (5, "PCG_2_2_CentralPark_Footprint", "s05_central_park_footprint", "中央公园范围"),
    (6, "PCG_3_1_1_Districts", "s06_districts", "街区骨架"),
    (7, "PCG_3_1_2_Roads", "s07_roads", "道路"),
    (8, "PCG_3_1_3_Highways", "s08_highways", "高速"),
    (9, "PCG_3_1_4_Lots", "s09_lots", "地块"),
    (10, "PCG_3_2_1_Ground", "s10_ground", "地面与人行道"),
    (11, "PCG_3_3_1_Buildings", "s11_buildings", "建筑"),
    (12, "PCG_3_3_2_Rooftops", "s12_rooftops", "屋顶设备"),
    (13, "PCG_3_2_2_LeftOverLots", "s13_leftover_lots", "余地广场与植被"),
    (14, "PCG_3_2_3_Parkings", "s14_parkings", "停车场"),
    (15, "PCG_4_1_MainTower_Visuals", "s15_main_tower_visuals", "主塔视觉"),
    (16, "PCG_4_2_CentralPark_Visuals", "s16_central_park_visuals", "中央公园视觉"),
    (17, "PCG_5_1_CityEdge", "s17_city_edge", "滨水设施"),
    (18, "PCG_5_2_OuterForest", "s18_outer_forest", "外围林地"),
]
PROBE = (0, "PCG_PyProbe", "s00_probe", "探针")

# Which stages read a stage's output through Get_ActorDataByRef (official graphs, 2026-10-15 scan).
DOWNSTREAM = {1: [7, 10, 18], 4: [7, 9, 10, 13, 15], 5: [7, 9, 10, 13, 16, 18], 6: [7, 9, 10, 13],
              7: [8, 9, 10, 13, 16, 18], 8: [9, 13, 18], 9: [10, 11, 13], 11: [12], 13: [14], 14: [16]}


def entry(n):
    if n == PROBE[0]:
        return PROBE
    for s in STAGES:
        if s[0] == n:
            return s
    raise KeyError("no stage %r" % (n,))


def name(n):
    """The graph name, which is also the label of the stage's volume in the demo and town levels."""
    return entry(n)[1]


LABEL = name


def names():
    return [s[1] for s in STAGES]


def official_path(n):
    return OFFICIAL_DIR + name(n)


def spec(n):
    """The stage's Python module (pypcg.stages.sNN_*). Imported, so an edited stage file takes effect."""
    return importlib.import_module("pypcg.stages." + entry(n)[2])
```

- [ ] **Step 4: Point codegen, the L1 test and the official builder at the drafts' new home**

In `Tools/pypcg/codegen.py`, line 273:

```python
        out = os.path.join(REPO, "Tools", "pypcg", "reference_drafts", module + ".py")
```

In `Tools/pypcg/tests/test_stages_l1.py`:
- replace `STAGE_DIR = …` with `STAGE_DIR = os.path.join(REPO, "Tools", "pypcg", "reference_drafts")`;
- add `import reference_drafts` after the `pypcg` imports;
- replace both `stages.graph(n)` with `reference_drafts.graph(n)`.

In `Content/Python/pypcg_build.py`, after the `_REPO = …` line add:

```python
_DRAFTS = os.path.join(_REPO, "Tools", "pypcg")
if _DRAFTS not in sys.path:
    sys.path.insert(0, _DRAFTS)
for _m in [m for m in sys.modules if m == "reference_drafts" or m.startswith("reference_drafts.")]:
    del sys.modules[_m]
```

and change `g = stages.graph(n)` to `g = __import__("reference_drafts").graph(n)`.

- [ ] **Step 5: Run the offline suite**

```bash
C:/Python314/python.exe -m pytest Tools/pypcg/tests -q
```

Expected: the same counts as before the move, i.e. `74 passed, 18 skipped`.

- [ ] **Step 6: Commit**

```bash
git add -A Content/Python/pypcg/stages Tools/pypcg/reference_drafts Tools/pypcg/codegen.py Tools/pypcg/tests/test_stages_l1.py Content/Python/pypcg_build.py
git commit -m "Move the node-by-node stage drafts to Tools/pypcg/reference_drafts" -m "The pypcg/stages paths now belong to the Python stage modules of the slim graphs." -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `pypcg.geo` — value types and pure geometry

The spike's `districts_core.py` helpers are promoted here, together with the value types every stage exchanges.

**Files:**
- Create: `Content/Python/pypcg/geo/__init__.py`, `types.py`, `plane.py`, `sample.py`, `subdivide.py`
- Create: `Tools/pypcg/tests/fakes.py`, `Tools/pypcg/tests/test_geo.py`

**Interfaces — Produces** (all from `pypcg.geo`):
- **Value types.**
  - `Polygon(outer, holes=[], z=0.0)`
  - `Spline(points, closed=False, linear=True, tangents=None, polyline=None)`
  - `ParamSet(values, types={})`
  - `Points` (columns `loc rot scale density bounds_min bounds_max color steepness seed`; `declare(name, type)`, `add(loc, **kw)`, `take(indices)`, `len()`)
- **Item helpers.** `values(items)`, `with_tag(items, tag)`, `to_json(v)`, `from_json(d)`. An "item" is `(value, tags)`.
- **Plane geometry.** `signed_area`, `ccw`, `bbox`, `unit`, `inside`, `path_length`, `drop_closing`, `xy`, `enclosing_polygon`, `clip_path`, `clean_points`, `longest`, `frame_box`, `at`, `split_frame`, `ngon`, `rect`, `rotate`.
- **Sampling.** `area_m2`, `contains`, `scatter(polygon, per_m2, rng)`, `choose(n, ratio, rng)`.
- **Subdivision.** `auto_split(ring, ratio, ops)`, `recursive_split(ring, ops, iterations, min_area_cm2, ratio_fn, areas, paths)` (calls `ratio_fn(ring)` per split), `grid_lines(ring, width, length, extend=100000.0)`, `SLIVER_CM2`.
- **Test fakes.** `fakes.FakeOps`: `cut_with_paths(ring, paths)` (convex rings, straight paths) and `intersection(rings_a, rings_b)` (convex rings). `fakes.FlatTerrain(z)`.

- [ ] **Step 1: Write `Tools/pypcg/tests/fakes.py`**

```python
"""Offline stand-ins for the editor services a stage reaches through ctx.ops (ruling N2)."""
from pypcg import geo


def _half(ring, a, b, side):
    def s(p):
        return side * ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]))
    out = []
    for i in range(len(ring)):
        p, q = ring[i], ring[(i + 1) % len(ring)]
        sp, sq = s(p), s(q)
        if sp >= 0:
            out.append(p)
        if (sp >= 0) != (sq >= 0):
            t = sp / (sp - sq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


class FakeOps:
    """cut_with_paths for convex rings and straight paths (the line through each path's ends), and
    intersection of convex rings (Sutherland-Hodgman)."""

    def cut_with_paths(self, ring, paths):
        pieces = [list(ring)]
        for path in paths:
            a, b = path[0], path[-1]
            nxt = []
            for r in pieces:
                for side in (1, -1):
                    part = _half(r, a, b, side)
                    if len(part) >= 3 and abs(geo.signed_area(part)) > 1e-6:
                        nxt.append(geo.ccw(part))
            pieces = nxt
        return pieces

    def intersection(self, rings_a, rings_b):
        out = []
        for a in rings_a:
            for b in rings_b:
                part, b = list(geo.ccw(a)), geo.ccw(b)
                for i in range(len(b)):
                    part = _half(part, b[i], b[(i + 1) % len(b)], 1) if len(part) >= 3 else []
                if len(part) >= 3 and abs(geo.signed_area(part)) > 1e-6:
                    out.append(geo.Polygon(geo.ccw(part)))
        return out


class FlatTerrain:
    """A surface at constant height."""

    def __init__(self, z=0.0):
        self.z = z

    def height(self, x, y):
        return self.z
```

- [ ] **Step 2: Write the failing tests** `Tools/pypcg/tests/test_geo.py`:

```python
import math
import random

import pytest

from fakes import FakeOps
from pypcg import geo
from pypcg.geo import ParamSet, Points, Polygon, Spline

RECT = [(0.0, 0.0), (10000.0, 0.0), (10000.0, 5000.0), (0.0, 5000.0)]      # 100 x 50 m, CCW


def test_signed_area_and_ccw():
    assert geo.signed_area(RECT) == pytest.approx(5.0e7)
    assert geo.signed_area(geo.ccw(list(reversed(RECT)))) == pytest.approx(5.0e7)


def test_inside_and_contains_with_hole():
    poly = Polygon(RECT, holes=[[(4000, 2000), (4000, 3000), (6000, 3000), (6000, 2000)]])
    assert geo.inside((100, 100), RECT) and not geo.inside((-1, 100), RECT)
    assert geo.contains(poly, (100, 100)) and not geo.contains(poly, (5000, 2500))
    assert geo.area_m2(poly) == pytest.approx(5000 - 200)


def test_clip_path_keeps_the_inside_part():
    parts = geo.clip_path([(-1000, 2500), (20000, 2500)], RECT)
    assert len(parts) == 1
    (x0, y0), (x1, y1) = parts[0][0], parts[0][-1]
    assert (x0, x1) == (pytest.approx(0.0), pytest.approx(10000.0)) and y0 == y1 == 2500


def test_clean_points_follows_the_auto_tangents():
    # CleanSpline judges collinearity on CurveAuto tangents (next - previous), so a vertex whose
    # neighbour's tangent points at a corner survives, and only runs well inside a straight edge go.
    assert geo.clean_points([(0, 0), (500, 0), (1000, 0), (1000, 1000)]) == [(0, 0), (500, 0), (1000, 0), (1000, 1000)]
    assert geo.clean_points([(0, 0), (250, 0), (500, 0), (750, 0), (1000, 0), (1000, 1000)]) == \
        [(0, 0), (750, 0), (1000, 0), (1000, 1000)]


def test_frame_box_of_an_axis_aligned_rectangle():
    o, X, Y, u0, u1, w0, w1 = geo.frame_box(RECT)
    assert o == (0.0, 0.0) and X == (1.0, 0.0) and Y == (-0.0, 1.0)
    assert (u0, u1, w0, w1) == (-1.0, 10001.0, -1.0, 5001.0)        # the engine's +-1 cm point bounds


def test_grid_lines_on_a_rectangle():
    # Lines sit at u0 + k*W (k >= 1) like Subdivide_Areas_withGrid: x = 999, 1999, ..., 9999 and
    # y = 999, ..., 4999; the lines past the far edge clip to nothing.
    lines = geo.grid_lines(RECT, 1000.0, 1000.0)
    xs = sorted(round(seg[0][0]) for axis, seg in lines if axis == "X")
    ys = sorted(round(seg[0][1]) for axis, seg in lines if axis == "Y")
    assert xs == [999 + 1000 * k for k in range(10)]
    assert ys == [999 + 1000 * k for k in range(5)]
    assert all(geo.path_length(seg) == pytest.approx(5000 if axis == "X" else 10000) for axis, seg in lines)


def test_recursive_split_halves_a_rectangle():
    areas, paths = [], []
    geo.recursive_split(RECT, FakeOps(), 1, 1000 * 1e4, lambda ring: 0.5, areas, paths)
    assert sorted(round(abs(geo.signed_area(a)) / 1e4) for a in areas) == [2500, 2500]
    assert len(paths) == 1 and paths[0][0][0] == pytest.approx(5000.0)


def test_recursive_split_keeps_small_areas_whole():
    areas, paths = [], []
    geo.recursive_split(RECT, FakeOps(), 1, 6000 * 1e4, lambda ring: 0.5, areas, paths)
    assert areas == [RECT] and paths == []


class SliverOps:
    def cut_with_paths(self, ring, paths):
        return [ring, [(0, 0), (1, 0), (0, 1)]]


def test_auto_split_drops_slivers():
    pieces, _ = geo.auto_split(RECT, 0.5, SliverOps())
    assert pieces == [RECT]
    areas, paths = [], []
    geo.recursive_split(RECT, SliverOps(), 1, 0, lambda ring: 0.5, areas, paths)
    assert areas == [RECT] and paths == []                 # a cut that does not divide keeps the ring whole


def test_ngon_matches_the_official_tower_hexagon():
    # PCG_2_1_MainTower_Footprint in the demo level (pyg_probe_plan_api3.py, 2026-10-15)
    pts = geo.ngon((0.0, 0.0), 8000.0, 6, start_deg=-60.0, step_deg=-60.0)
    official = [(4000, -6928.2), (-4000, -6928.2), (-8000, 0), (-4000, 6928.2), (4000, 6928.2), (8000, 0)]
    assert all(math.dist(p, q) < 0.1 for p, q in zip(pts, official))


def test_rect_matches_the_official_park():
    pts = geo.rect((60150.0, 57100.0), 50000.0, 10000.0, yaw_deg=34.222659453871444)
    official = [(13182.98, 37248.06), (95868.81, 93489.1), (107117.02, 76951.94), (24431.19, 20710.9)]
    assert all(math.dist(p, q) < 0.5 for p, q in zip(pts, official))


def test_scatter_count_containment_and_determinism():
    poly = Polygon([(0, 0), (10000, 0), (10000, 10000), (0, 10000)], holes=[[(4000, 4000), (4000, 6000), (6000, 6000), (6000, 4000)]])
    a = geo.scatter(poly, 0.01, random.Random("1"))
    assert len(a) == 96 and all(geo.contains(poly, p) for p in a)
    assert a == geo.scatter(poly, 0.01, random.Random("1")) and a != geo.scatter(poly, 0.01, random.Random("2"))


def test_choose_keeps_an_exact_share():
    picked = geo.choose(608, 0.641598, random.Random("x"))
    assert len(picked) == 390 and picked == sorted(set(picked))


def test_points_columns_attributes_and_take():
    pts = Points()
    pts.declare("Mesh", "SoftObjectPath")
    pts.add((1, 2, 3), Mesh="/Game/A.A")
    pts.add((4, 5, 6), rot=(0.0, 90.0, 0.0), Mesh="/Game/B.B")
    assert len(pts) == 2 and pts.scale[0] == (1.0, 1.0, 1.0) and pts.rot[1] == (0.0, 90.0, 0.0)
    sub = pts.take([1])
    assert len(sub) == 1 and sub.attrs["Mesh"] == ["/Game/B.B"] and sub.types == {"Mesh": "SoftObjectPath"}
    with pytest.raises(KeyError):
        pts.add((0, 0, 0), Undeclared=1)
    assert len(pts) == 2 and len(pts.attrs["Mesh"]) == 2          # a refused add leaves no partial row
    with pytest.raises(KeyError):
        pts.declare("seed", "Int32")                 # a point property, not an attribute


def test_json_round_trip_and_truncation():
    pts = Points()
    pts.declare("Label", "String")
    pts.add((1, 2, 3), Label="a")
    for v in (Polygon(RECT, z=5.0), Spline([(0, 0, 0), (1, 0, 0)], tangents=[((1, 0, 0), (1, 0, 0))] * 2, linear=False),
              ParamSet({"A": 1.5}, {"A": "Double"}), pts):
        back = geo.from_json(geo.to_json(v))
        assert geo.to_json(back) == geo.to_json(v)
    big = Points()
    for i in range(geo.MAX_RECORDED_POINTS + 1):
        big.add((i, 0, 0))
    rec = geo.to_json(big)
    assert rec["truncated"] and rec["n"] == geo.MAX_RECORDED_POINTS + 1
    with pytest.raises(ValueError):
        geo.from_json(rec)


def test_items_helpers():
    items = [("a", {"Small"}), ("b", {"Large", "Lots"}), ("c", {"Lots"})]
    assert geo.values(items) == ["a", "b", "c"] and geo.with_tag(items, "Lots") == ["b", "c"]
```

Run: `C:/Python314/python.exe -m pytest Tools/pypcg/tests/test_geo.py -q` → fails (no module `pypcg.geo`).

- [ ] **Step 3: Write `Content/Python/pypcg/geo/types.py`**

```python
"""The values a Python stage reads and writes (spec 2.2). World cm, no unreal import."""
from dataclasses import dataclass, field

MAX_RECORDED_POINTS = 20000          # larger point sets are recorded as a summary only


@dataclass
class Polygon:
    """An area: outer and holes are [(x, y)] rings, outer counter-clockwise (positive shoelace
    area); z is the height the area sits at."""
    outer: list
    holes: list = field(default_factory=list)
    z: float = 0.0


@dataclass
class Spline:
    """points: [(x, y, z)] control points. linear: straight segments; otherwise tangents holds
    (arrive, leave) per point, or None for automatic tangents. polyline: the dense world polyline
    the engine draws (filled on inputs, ignored on outputs)."""
    points: list
    closed: bool = False
    linear: bool = True
    tangents: list = None
    polyline: list = None


@dataclass
class ParamSet:
    """One attribute-set entry: values {name: value}, types {name: metadata type name}."""
    values: dict
    types: dict = field(default_factory=dict)


class Points:
    """PCG points as columns. loc/scale are (x, y, z); rot is (pitch, yaw, roll) in degrees; color is
    (r, g, b, a). attrs {name: [value per point]}, types {name: metadata type name} such as "Double",
    "String", "SoftObjectPath"."""
    DEFAULTS = {"rot": (0.0, 0.0, 0.0), "scale": (1.0, 1.0, 1.0), "density": 1.0,
                "bounds_min": (-1.0, -1.0, -1.0), "bounds_max": (1.0, 1.0, 1.0),
                "color": (1.0, 1.0, 1.0, 1.0), "steepness": 0.5, "seed": 0}
    COLUMNS = ("loc",) + tuple(DEFAULTS)

    def __init__(self):
        for c in self.COLUMNS:
            setattr(self, c, [])
        self.attrs = {}
        self.types = {}

    def __len__(self):
        return len(self.loc)

    def declare(self, name, type_name, default=None):
        if name in self.COLUMNS or name in self.attrs:
            raise KeyError("point attribute %r is a point property or already declared" % name)
        self.attrs[name] = [default] * len(self)
        self.types[name] = type_name

    def add(self, loc, **kw):
        unknown = sorted(set(kw) - set(self.DEFAULTS) - set(self.attrs))
        if unknown:
            raise KeyError("undeclared point attribute(s) %s" % unknown)
        self.loc.append(tuple(float(v) for v in loc))
        for c, default in self.DEFAULTS.items():
            getattr(self, c).append(kw.get(c, default))
        for name, column in self.attrs.items():
            column.append(kw.get(name))

    def take(self, indices):
        out = Points()
        for name, type_name in self.types.items():
            out.declare(name, type_name)
        for i in indices:
            kw = {c: getattr(self, c)[i] for c in self.DEFAULTS}
            kw.update({n: column[i] for n, column in self.attrs.items()})
            out.add(self.loc[i], **kw)
        return out


def values(items):
    """The values of a list of (value, tags) items."""
    return [v for v, _ in items]


def with_tag(items, tag):
    return [v for v, tags in items if tag in tags]


def _tuples(seq):
    return [tuple(x) if isinstance(x, list) else x for x in seq]


def to_json(v):
    if isinstance(v, Polygon):
        return {"kind": "polygon", "outer": [list(p) for p in v.outer], "holes": [[list(p) for p in h] for h in v.holes], "z": v.z}
    if isinstance(v, Spline):
        return {"kind": "spline", "points": [list(p) for p in v.points], "closed": v.closed, "linear": v.linear,
                "tangents": [[list(a), list(b)] for a, b in v.tangents] if v.tangents else None,
                "polyline": [list(p) for p in v.polyline] if v.polyline else None}
    if isinstance(v, ParamSet):
        return {"kind": "params", "values": dict(v.values), "types": dict(v.types)}
    if isinstance(v, Points):
        d = {"kind": "points", "n": len(v), "types": dict(v.types)}
        if len(v) > MAX_RECORDED_POINTS:
            xs, ys, zs = zip(*v.loc)
            d.update(truncated=True, bbox=[[min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]])
            return d
        d.update({c: [list(x) if isinstance(x, tuple) else x for x in getattr(v, c)] for c in Points.COLUMNS})
        d["attrs"] = {k: list(col) for k, col in v.attrs.items()}
        return d
    return {"kind": type(v).__name__}              # e.g. a terrain surface: not recordable


def from_json(d):
    kind = d.get("kind")
    if kind == "polygon":
        return Polygon(_tuples(d["outer"]), [_tuples(h) for h in d["holes"]], d.get("z", 0.0))
    if kind == "spline":
        return Spline(_tuples(d["points"]), d["closed"], d["linear"],
                      [(tuple(a), tuple(b)) for a, b in d["tangents"]] if d.get("tangents") else None,
                      _tuples(d["polyline"]) if d.get("polyline") else None)
    if kind == "params":
        return ParamSet(dict(d["values"]), dict(d["types"]))
    if kind == "points" and not d.get("truncated"):
        p = Points()
        for c in Points.COLUMNS:
            setattr(p, c, _tuples(d[c]))
        p.types = dict(d["types"])
        p.attrs = {k: list(col) for k, col in d["attrs"].items()}
        return p
    raise ValueError("cannot rebuild a %s value from its record" % kind)
```

- [ ] **Step 4: Write `Content/Python/pypcg/geo/plane.py`** (promoted from the spike; each block names the PCG behaviour it reproduces)

```python
"""Pure 2D geometry on (x, y) tuples in cm (promoted from the Districts spike, 2026-10-15)."""
import bisect
import math


def signed_area(p):
    return 0.5 * sum(p[i - 1][0] * p[i][1] - p[i][0] * p[i - 1][1] for i in range(len(p)))


def ccw(p):
    """CreatePolygon2D forces the outer ring counter-clockwise (positive shoelace area)."""
    return list(p) if signed_area(p) >= 0 else list(reversed(p))


def bbox(pts):
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    return (min(xs), min(ys)), (max(xs), max(ys))


def unit(x, y):
    n = math.hypot(x, y)
    return (x / n, y / n) if n > 1e-12 else (0.0, 0.0)


def inside(pt, ring):
    x, y, c, j = pt[0], pt[1], False, len(ring) - 1
    for i in range(len(ring)):
        (xi, yi), (xj, yj) = ring[i][:2], ring[j][:2]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def path_length(path):
    return sum(math.dist(path[i][:2], path[i + 1][:2]) for i in range(len(path) - 1))


def drop_closing(points):
    """A closed polyline as the engine samples it repeats its first vertex at the end; drop it."""
    return list(points[:-1]) if len(points) > 1 and math.dist(points[0], points[-1]) < 1e-6 else list(points)


def xy(points):
    return [(p[0], p[1]) for p in points]


def rotate(p, yaw_deg):
    r = math.radians(yaw_deg)
    return (p[0] * math.cos(r) - p[1] * math.sin(r), p[0] * math.sin(r) + p[1] * math.cos(r))


def ngon(center, radius, n, start_deg=0.0, step_deg=None, y_scale=1.0, yaw_deg=0.0):
    """Create_Spline_Shape's polygon: n points on a circle of `radius`, the first at start_deg,
    stepping step_deg (default 360/n), stretched by y_scale along local Y, turned by yaw_deg."""
    step = 360.0 / n if step_deg is None else step_deg
    out = []
    for k in range(n):
        a = math.radians(start_deg + k * step)
        x, y = rotate((radius * math.cos(a), radius * y_scale * math.sin(a)), yaw_deg)
        out.append((center[0] + x, center[1] + y))
    return out


def rect(center, half_x, half_y, yaw_deg=0.0, order=((-1, 1), (1, 1), (1, -1), (-1, -1))):
    """Create_Spline_Shape's 4-gon (grid corners + convex hull): corners in the official order."""
    out = []
    for sx, sy in order:
        x, y = rotate((sx * half_x, sy * half_y), yaw_deg)
        out.append((center[0] + x, center[1] + y))
    return out


# ---- Polygon2DOperation(CutWithPaths): GetEnclosingPolygonFromPath ------------------------
def enclosing_polygon(path, bb):
    """Close an open path around the polygon's box (expanded by 1 %) on its left side."""
    (x0, y0), (x1, y1) = bb
    pad = max(1.0, 0.01 * max(x1 - x0, y1 - y0))
    targets = [(x0 - pad, y0 - pad), (x1 + pad, y0 - pad), (x1 + pad, y1 + pad), (x0 - pad, y1 + pad), tuple(path[0])]
    out = [tuple(q) for q in path]
    while True:
        (ax, ay), (bx, by) = out[-2], out[-1]
        dx, dy = unit(bx - ax, by - ay)
        best, best_a = 0, None
        for k, (tx, ty) in enumerate(targets):
            ux, uy = unit(tx - bx, ty - by)
            a = math.atan2(dx * uy - dy * ux, ux * dx + uy * dy) % (2 * math.pi)
            if best_a is None or a < best_a:
                best, best_a = k, a
        if best == len(targets) - 1:
            return out
        out.append(targets.pop(best))


# ---- ClipPaths(Intersection): the parts of an open path inside a ring ----------------------
def _at(path, cum, s):
    i = min(max(bisect.bisect_right(cum, s) - 1, 0), len(path) - 2)
    span = cum[i + 1] - cum[i]
    t = 0.0 if span == 0 else (s - cum[i]) / span
    return (path[i][0] + t * (path[i + 1][0] - path[i][0]), path[i][1] + t * (path[i + 1][1] - path[i][1]))


def clip_path(path, ring):
    n = len(ring)
    edges = []
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        edges.append((a, b, min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])))
    cum = [0.0]
    for i in range(len(path) - 1):
        cum.append(cum[-1] + math.dist(path[i][:2], path[i + 1][:2]))
    cuts = []
    for i in range(len(path) - 1):
        p, q = path[i], path[i + 1]
        sx0, sx1, sy0, sy1 = min(p[0], q[0]), max(p[0], q[0]), min(p[1], q[1]), max(p[1], q[1])
        rx, ry = q[0] - p[0], q[1] - p[1]
        for a, b, ex0, ex1, ey0, ey1 in edges:
            if ex1 < sx0 or ex0 > sx1 or ey1 < sy0 or ey0 > sy1:
                continue
            sx, sy = b[0] - a[0], b[1] - a[1]
            den = rx * sy - ry * sx
            if den == 0:
                continue
            wx, wy = a[0] - p[0], a[1] - p[1]
            t, u = (wx * sy - wy * sx) / den, (wx * ry - wy * rx) / den
            if 0.0 <= t <= 1.0 and 0.0 <= u < 1.0:
                cuts.append(cum[i] + t * (cum[i + 1] - cum[i]))
    marks, spans = [0.0] + sorted(cuts) + [cum[-1]], []
    for s0, s1 in zip(marks, marks[1:]):
        if s1 - s0 > 1e-6 and inside(_at(path, cum, 0.5 * (s0 + s1)), ring):
            if spans and abs(spans[-1][1] - s0) < 1e-6:
                spans[-1][1] = s1
            else:
                spans.append([s0, s1])
    return [[_at(path, cum, s0)] + [tuple(path[k][:2]) for k in range(bisect.bisect_right(cum, s0), bisect.bisect_left(cum, s1))]
            + [_at(path, cum, s1)] for s0, s1 in spans]


# ---- CleanSpline (5 deg collinear, open curve spline, auto tangents) ----------------------
def clean_points(pts, angle_deg=5.0):
    n = len(pts)

    def tan(i):                       # CurveAuto tangent direction: next - previous, clamped at the ends
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
        return (b[0] - a[0], b[1] - a[1])

    thr = max(abs(math.cos(math.radians(angle_deg))), 1e-8)

    def col(v, w):
        a, b = math.hypot(*v), math.hypot(*w)
        return a > 0 and b > 0 and abs((v[0] * w[0] + v[1] * w[1]) / (a * b)) >= thr

    cp = [[tuple(pts[i]), tan(i), tan(i)] for i in range(n)]       # position, arrive, leave
    k = len(cp) - 1
    while k >= 2:                     # reverse triplet scan, as FPCGCleanSplineElement does
        s, p, c = cp[k - 2], cp[k - 1], cp[k]
        seg = (c[0][0] - s[0][0], c[0][1] - s[0][1])
        if col(s[2], seg) and col(p[1], seg) and col(p[2], seg) and col(c[1], seg):
            s[2] = c[1] = seg
            del cp[k - 1]
        k -= 1
    return [q[0] for q in cp]


# ---- the longest-edge frame + CombinePoints bounds ----------------------------------------
def longest(ring):
    n = len(ring)
    return max(range(n), key=lambda i: math.dist(ring[i], ring[(i + 1) % n]))


def frame_box(ring):
    """Frame at the longest outer edge's start vertex (X along the edge, Y its left normal) and the
    bounds of every vertex point (+-1 cm boxes turned with their segment) in that frame."""
    n, k = len(ring), longest(ring)
    o = ring[k]
    X = unit(ring[(k + 1) % n][0] - o[0], ring[(k + 1) % n][1] - o[1])
    Y = (-X[1], X[0])
    us, ws = [], []
    for i, q in enumerate(ring):
        d = unit(ring[(i + 1) % n][0] - q[0], ring[(i + 1) % n][1] - q[1])
        e = abs(d[0] * X[0] + d[1] * X[1]) + abs(d[0] * Y[0] + d[1] * Y[1])
        u = (q[0] - o[0]) * X[0] + (q[1] - o[1]) * X[1]
        w = (q[0] - o[0]) * Y[0] + (q[1] - o[1]) * Y[1]
        us += [u - e, u + e]
        ws += [w - e, w + e]
    return o, X, Y, min(us), max(us), min(ws), max(ws)


def at(o, X, Y, u, w):
    return (o[0] + X[0] * u + Y[0] * w, o[1] + X[1] * u + Y[1] * w)


def split_frame(ring):
    """AutoSplitPolygon's frame: CleanSpline the ring, force it counter-clockwise, then frame_box."""
    return frame_box(ccw(clean_points(ring)))
```

- [ ] **Step 5: Write `Content/Python/pypcg/geo/sample.py` and `subdivide.py`**

```python
"""Sampling with Python's own random numbers (spec E2: new layouts, not PCG's RNG)."""
from .plane import bbox, inside, signed_area


def area_m2(polygon):
    return (abs(signed_area(polygon.outer)) - sum(abs(signed_area(h)) for h in polygon.holes)) / 1e4


def contains(polygon, pt):
    return inside(pt, polygon.outer) and not any(inside(pt, h) for h in polygon.holes)


def scatter(polygon, per_m2, rng, max_tries_factor=50):
    """round(area * per_m2) uniform points in the polygon (holes excluded), by rejection."""
    n = int(round(area_m2(polygon) * per_m2))
    (x0, y0), (x1, y1) = bbox(polygon.outer)
    out, tries = [], 0
    while len(out) < n and tries < n * max_tries_factor + 100:
        tries += 1
        p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
        if contains(polygon, p):
            out.append(p)
    return out


def choose(n, ratio, rng):
    """Sorted indices of round(n * ratio) of n items (Filter_RandomChoice / RandomChoice)."""
    k = max(0, min(n, int(round(n * ratio))))
    return sorted(rng.sample(range(n), k))
```

```python
"""Area subdivision shared by Districts and Lots: AutoSplitPolygon (Subdivide_Areas_WithRecursiveSplit)
and the grid of Subdivide_Areas_withGrid (spike report, 2026-10-15). ops supplies cut_with_paths."""
from .plane import at, clip_path, frame_box, signed_area, split_frame

SLIVER_CM2 = 1.0e4                # pieces under 1 m2 are boolean noise and never output


def auto_split(ring, ratio, ops):
    """Cut ring with a line across its longest edge at `ratio` of the way back along it.
    Returns (pieces, [the cut clipped to ring])."""
    o, X, Y, u0, u1, w0, w1 = split_frame(ring)
    u, wc, hw = u1 - ratio * (u1 - u0), 0.5 * (w0 + w1), 2.0 * (w1 - w0)       # 4 x half-depth
    line = [at(o, X, Y, u, wc + hw), at(o, X, Y, u, wc - hw)]
    # CreateSpline -> ConvertSplineToPolyLine always halves a curve segment, so the cutting path
    # carries its midpoint; it survives as one collinear vertex per piece.
    cut = [line[0], at(o, X, Y, u, wc), line[1]]
    pieces = [r for r in ops.cut_with_paths(ring, [cut]) if abs(signed_area(r)) >= SLIVER_CM2]
    return pieces, clip_path(line, ring)


def recursive_split(ring, ops, iterations, min_area_cm2, ratio_fn, areas, paths, depth=0):
    """Split until `iterations` levels or until a piece is not larger than min_area_cm2; ratio_fn(ring)
    gives each split's ratio. A cut that does not divide the ring (fewer than 2 real pieces) keeps it whole."""
    if depth >= iterations or not abs(signed_area(ring)) > min_area_cm2:
        areas.append(ring)
        return
    pieces, cut = auto_split(ring, ratio_fn(ring), ops)
    if len(pieces) < 2:
        areas.append(ring)
        return
    paths.extend(cut)
    for r in pieces:
        recursive_split(r, ops, iterations, min_area_cm2, ratio_fn, areas, paths, depth + 1)


def grid_lines(ring, width, length, extend=100000.0):
    """[("X" | "Y", segment)]: lines across the longest-edge frame every `width` (X, perpendicular
    to the edge) and every `length` (Y, parallel to it), clipped to the ring."""
    o, X, Y, u0, u1, w0, w1 = frame_box(ring)
    out = []
    for axis, lo, hi, step in (("X", u0, u1, width), ("Y", w0, w1, length)):
        n = int((hi - lo) / step + 2)         # CreatePointsGrid(CellCorners), extents = half box + one cell
        for i in range(2, n + 1):             # FilterDataByIndex drops partitions 0 and 1
            c = lo + (i - 1) * step
            line = ([at(o, X, Y, c, w0 - extend), at(o, X, Y, c, w1 + extend)] if axis == "X" else
                    [at(o, X, Y, u0 - extend, c), at(o, X, Y, u1 + extend, c)])
            out += [(axis, seg) for seg in clip_path(line, ring)]
    return out
```

- [ ] **Step 6: Write `Content/Python/pypcg/geo/__init__.py`**

```python
"""Plain values and pure geometry for the Python stages (spec 2.3). No unreal import."""
from .plane import (at, bbox, ccw, clean_points, clip_path, drop_closing, enclosing_polygon, frame_box,  # noqa: F401
                    inside, longest, ngon, path_length, rect, rotate, signed_area, split_frame, unit, xy)
from .sample import area_m2, choose, contains, scatter  # noqa: F401
from .subdivide import SLIVER_CM2, auto_split, grid_lines, recursive_split  # noqa: F401
from .types import (MAX_RECORDED_POINTS, ParamSet, Points, Polygon, Spline, from_json, to_json,  # noqa: F401
                    values, with_tag)
```

- [ ] **Step 7: Run the tests** → `C:/Python314/python.exe -m pytest Tools/pypcg/tests/test_geo.py -q` → `16 passed`. Then the whole suite → no regressions.

- [ ] **Step 8: Commit**

```bash
git add Content/Python/pypcg/geo Tools/pypcg/tests/fakes.py Tools/pypcg/tests/test_geo.py
git commit -m "Add pypcg.geo: the stage value types and the pure geometry promoted from the Districts spike" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: The stage contract, the host, and the editor adapters

**Files:**
- Create: `Content/Python/pypcg/stage_api.py`, `Content/Python/pypcg/host.py`
- Create: `Content/Python/pypcg/ue/__init__.py`, `convert.py`, `ops.py`, `terrain.py`
- Create: `Tools/pypcg/tests/test_stage_api.py`, `Tools/pypcg/tests/test_host.py`

**Interfaces — Produces:**
- **`pypcg.stage_api`:**
  - constants `SEED = "Seed"`, `SEED_DEFAULT = 42`, `PARAMS_PIN = "Params"`, `RUNS_DIR`, `RECORD_ENV = "PYPCG_RECORD"`;
  - `Param(default, tooltip="", type=None, type_object="", category="")`;
  - `param_specs(module) -> [(name, type, default, tooltip, type_object, category)]`, Seed first;
  - `defaults(module) -> {name: default}`;
  - `Ctx(stage, seed, ops)` with `.rng .ops .seed .stage .notes`;
  - `execute(module, inputs, params, ops) -> (outputs, ctx)`;
  - `record(module, inputs, params, outputs, seconds, ctx) -> path`;
  - `StageError`.
- **Inputs and outputs.** `inputs = {pin: [(value, tags)]}`; `run()` returns `{pin: [(value, [tags])]}`.
- **`pypcg.host`:** `run(stage_name, scope)` and `_fresh()`.
- **`pypcg.ue.convert`:**
  - `read_params(data_in, pin) -> {name: value}`;
  - `read_pin(data_in, pin) -> [(value, frozenset(tags))]`;
  - `from_pcg(data)`;
  - `to_pcg(value)`;
  - `entry_values(metadata, key) -> {name: value}`.
- **`pypcg.ue.ops.Ops`:** `cut_with_paths(ring, paths)`, `intersection(a_rings, b_rings)`, `difference(a_rings, b_rings)`, `union(rings)`, each returning `[Polygon]` (except `cut_with_paths`, which returns rings).
- **`pypcg.ue.terrain.Terrain(data)`:** `height(x, y) -> float | None`.

- [ ] **Step 1: Write the failing tests** `Tools/pypcg/tests/test_stage_api.py`:

```python
import json
import os
import random
import subprocess
import sys
import types

import pytest

from pypcg import geo, stage_api
from pypcg.geo import Polygon
from pypcg.stage_api import Param, StageError


def stub(**kw):
    m = types.SimpleNamespace(__name__="pypcg.stages.s09_stub", STAGE=9, DOC="d", RANDOM=True,
                              PARAMS={"A": 1.5, "B": Param(3, "tip", category="Grid"), "C": True, "D": "x"},
                              INPUTS={"In": "any"}, OUTPUTS=("Out",),
                              run=lambda inputs, params, ctx: {"Out": [(Polygon([(0, 0), (1, 0), (0, 1)]), ["Out"])]})
    for k, v in kw.items():
        setattr(m, k, v)
    return m


def test_param_specs_put_seed_first_and_infer_types():
    assert stage_api.param_specs(stub()) == [
        ("Seed", "Int32", 42, "Random seed of this step; the step number is mixed in.", "", ""),
        ("A", "Double", 1.5, "", "", ""), ("B", "Int32", 3, "tip", "", "Grid"),
        ("C", "Bool", True, "", "", ""), ("D", "String", "x", "", "", "")]


def test_seed_is_reserved():
    with pytest.raises(StageError):
        stage_api.param_specs(stub(PARAMS={"Seed": 1}))


def test_execute_reports_param_mismatch():
    params = stage_api.defaults(stub())
    params.pop("A")
    params["Renamed"] = 2.0
    with pytest.raises(StageError) as e:
        stage_api.execute(stub(), {"In": []}, params, None)
    assert "A" in str(e.value) and "Renamed" in str(e.value)


def test_execute_requires_every_input_pin():
    with pytest.raises(StageError) as e:
        stage_api.execute(stub(), {}, stage_api.defaults(stub()), None)
    assert "In" in str(e.value)


def test_execute_checks_outputs():
    bad_pin = stub(run=lambda i, p, c: {"Nope": []})
    with pytest.raises(StageError):
        stage_api.execute(bad_pin, {"In": []}, stage_api.defaults(bad_pin), None)
    bad_value = stub(run=lambda i, p, c: {"Out": [("not a value", ["Out"])]})
    with pytest.raises(StageError):
        stage_api.execute(bad_value, {"In": []}, stage_api.defaults(bad_value), None)


def test_execute_passes_params_without_seed_and_a_seeded_rng():
    seen = {}

    def run(inputs, params, ctx):
        seen.update(params=params, draw=ctx.rng.random(), seed=ctx.seed)
        return {}
    m = stub(run=run)
    stage_api.execute(m, {"In": []}, dict(stage_api.defaults(m), Seed=5), None)
    assert "Seed" not in seen["params"] and seen["seed"] == 5
    assert seen["draw"] == random.Random("5:9").random()


def test_ctx_rng_is_session_independent():
    code = ("import sys; sys.path.insert(0, %r); from pypcg import stage_api; "
            "print(repr(stage_api.Ctx(6, 42, None).rng.random()))" % os.path.join(stage_api.REPO, "Content", "Python"))
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONHASHSEED=s)).stdout for s in ("1", "2")}
    assert len(outs) == 1 and outs.pop().strip() == repr(random.Random("42:6").random())


def test_record_writes_inputs_params_and_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_api, "RUNS_DIR", str(tmp_path))
    m = stub()
    inputs = {"In": [(Polygon([(0, 0), (1, 0), (0, 1)]), frozenset({"Lots"}))]}
    params = stage_api.defaults(m)
    outputs, ctx = stage_api.execute(m, inputs, params, None)
    path = stage_api.record(m, inputs, params, outputs, 0.5, ctx)
    rec = json.load(open(path, encoding="utf-8"))
    assert rec["stage"] == 9 and rec["params"]["Seed"] == 42 and rec["seconds"] == 0.5
    assert rec["inputs"]["In"][0][1] == ["Lots"] and rec["outputs"]["Out"][0][1] == ["Out"]
    assert geo.from_json(rec["inputs"]["In"][0][0]) == inputs["In"][0][0]
```

`Tools/pypcg/tests/test_host.py`:

```python
import sys

from pypcg import host


def test_fresh_drops_cached_pypcg_modules():
    saved = {k: v for k, v in sys.modules.items() if k == "pypcg" or k.startswith("pypcg.")}
    sys.modules["pypcg.stages.s99_cached"] = object()
    try:
        host._fresh()
        assert not [k for k in sys.modules if k == "pypcg" or k.startswith("pypcg.")]
    finally:
        sys.modules.update(saved)
        sys.modules.pop("pypcg.stages.s99_cached", None)


def test_inline_script_text_matches_what_the_dsl_writes():
    assert host.inline_script("s06_districts") == 'from pypcg import host\nhost.run("s06_districts", globals())\n'
```

Run → both files fail on import.

- [ ] **Step 2: Write `Content/Python/pypcg/stage_api.py`**

```python
"""The contract between a Python stage and the node that runs it (spec 2.2). No unreal import.

A stage module defines:
  STAGE    the Feishu step number (0 = the host probe)
  DOC      one paragraph; it becomes the slim graph's description
  RANDOM   True when run() draws from ctx.rng
  PARAMS   {name: Param(...) or a plain default}; the slim graph gets one user parameter and one
           getter per entry, plus "Seed" (added here, never declared by the stage)
  INPUTS   {pin: kind}; kind documents what arrives: "spline" | "polygon" | "area" | "points" |
           "surface" | "param" | "any"
  OUTPUTS  (pin, ...)
  run(inputs, params, ctx) -> {pin: [(value, [tags])]}
           inputs is {pin: [(value, frozenset(tags))]}, values are pypcg.geo types (or a surface
           object with height(x, y)); params excludes Seed; ctx.rng is random.Random(f"{Seed}:{STAGE}")
           (ruling N1) and ctx.ops the engine services (ruling N2).
"""
import json
import os
import random

from . import geo

SEED = "Seed"
SEED_DEFAULT = 42                  # the official components' seed in the demo level
PARAMS_PIN = "Params"
RECORD_ENV = "PYPCG_RECORD"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
RUNS_DIR = os.path.join(REPO, "Saved", "PyPCG", "runs")
VALUE_TYPES = (geo.Polygon, geo.Spline, geo.Points, geo.ParamSet)


class StageError(Exception):
    pass


class Param:
    """A stage parameter. type is the graph parameter type ("Double", "Int32", "Bool", "String",
    "SoftObject", ...), inferred from the default when not given."""

    def __init__(self, default, tooltip="", type=None, type_object="", category=""):
        self.default = default
        self.tooltip = tooltip
        self.type = type or _type_of(default)
        self.type_object = type_object
        self.category = category


def _type_of(v):
    if isinstance(v, bool):
        return "Bool"
    if isinstance(v, int):
        return "Int32"
    if isinstance(v, float):
        return "Double"
    if isinstance(v, str):
        return "String"
    raise StageError("no parameter type for %r; use Param(..., type=...)" % (v,))


def param_specs(module):
    """[(name, type, default, tooltip, type_object, category)], Seed first."""
    out = [(SEED, "Int32", SEED_DEFAULT, "Random seed of this step; the step number is mixed in.", "", "")]
    for name, p in module.PARAMS.items():
        if name == SEED:
            raise StageError("%s: Seed is added automatically; do not declare it" % module.__name__)
        p = p if isinstance(p, Param) else Param(p)
        out.append((name, p.type, p.default, p.tooltip, p.type_object, p.category))
    return out


def defaults(module):
    return {s[0]: s[2] for s in param_specs(module)}


class Ctx:
    def __init__(self, stage, seed, ops):
        self.stage = stage
        self.seed = seed
        # A string seed goes through SHA-512, so the sequence does not depend on PYTHONHASHSEED.
        self.rng = random.Random("%d:%d" % (seed, stage))
        self.ops = ops
        self.notes = []


def execute(module, inputs, params, ops):
    names = [s[0] for s in param_specs(module)]
    missing = [n for n in names if n not in params]
    unknown = sorted(set(params) - set(names))
    if missing or unknown:
        raise StageError("%s: parameters missing %s, unexpected %s; the stage declares %s"
                         % (module.__name__, missing, unknown, names))
    absent = [pin for pin in module.INPUTS if pin not in inputs]
    if absent:
        raise StageError("%s: no data for input pins %s" % (module.__name__, absent))
    ctx = Ctx(module.STAGE, int(params[SEED]), ops)
    outputs = module.run(inputs, {n: params[n] for n in names if n != SEED}, ctx)
    _check_outputs(module, outputs)
    return outputs, ctx


def _check_outputs(module, outputs):
    if not isinstance(outputs, dict):
        raise StageError("%s: run() must return {pin: [(value, [tags])]}" % module.__name__)
    for pin, items in outputs.items():
        if pin not in module.OUTPUTS:
            raise StageError("%s: unknown output pin %r; outputs %s" % (module.__name__, pin, list(module.OUTPUTS)))
        for item in items:
            ok = (isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], VALUE_TYPES)
                  and all(isinstance(t, str) for t in item[1]))
            if not ok:
                raise StageError("%s: output %s holds %r; expected (Polygon | Spline | Points | ParamSet, [tags])"
                                 % (module.__name__, pin, item))


def record(module, inputs, params, outputs, seconds, ctx):
    """Write the run to Saved/PyPCG/runs/sNN.json (inputs, params with Seed, outputs, notes)."""
    os.makedirs(RUNS_DIR, exist_ok=True)
    doc = {"stage": module.STAGE, "module": module.__name__, "seconds": seconds, "params": dict(params),
           "notes": list(ctx.notes),
           "inputs": {pin: [[geo.to_json(v), sorted(t)] for v, t in items] for pin, items in inputs.items()},
           "outputs": {pin: [[geo.to_json(v), list(t)] for v, t in items] for pin, items in outputs.items()}}
    path = os.path.join(RUNS_DIR, "s%02d.json" % module.STAGE)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return path
```

- [ ] **Step 3: Write `Content/Python/pypcg/host.py`**

```python
"""What every Python Data Processor node runs (spec 2.2, ruling N4). The node's inline script is:

    from pypcg import host
    host.run("s06_districts", globals())

run() drops every cached pypcg module first, so an edited stage or library file takes effect on the
next generation. It converts the node's inputs to pypcg.geo values, runs the stage, and writes the
outputs back. UObjects stay in locals (traps.md 25). Importable offline: unreal is imported inside run().
"""
import importlib
import os
import sys
import time


def inline_script(stage_name):
    return 'from pypcg import host\nhost.run("%s", globals())\n' % stage_name


def _fresh():
    for name in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
        del sys.modules[name]


def run(stage_name, scope):
    _fresh()
    import unreal
    from pypcg import stage_api
    from pypcg.ue import convert, ops as ue_ops
    module = importlib.import_module("pypcg.stages." + stage_name)
    data_in, data_out = scope["data_in"], scope["data_out"]
    t0 = time.perf_counter()
    params = convert.read_params(data_in, stage_api.PARAMS_PIN)
    inputs = {pin: convert.read_pin(data_in, pin) for pin in module.INPUTS}
    outputs, ctx = stage_api.execute(module, inputs, params, ue_ops.Ops())
    count = 0
    for pin, items in outputs.items():
        for value, tags in items:
            data_out.add_to_collection(convert.to_pcg(value), pin, list(tags))
            count += 1
    seconds = time.perf_counter() - t0
    if os.environ.get(stage_api.RECORD_ENV):
        stage_api.record(module, inputs, params, outputs, seconds, ctx)
    unreal.log("PyPCG %s: %d outputs in %.2f s%s" % (stage_name, count, seconds,
                                                     "; notes: " + "; ".join(ctx.notes) if ctx.notes else ""))
```

- [ ] **Step 4: Write `Content/Python/pypcg/ue/__init__.py`** (`"""Editor-only adapters between PCG data and pypcg.geo values."""`), then `Content/Python/pypcg/ue/terrain.py`:

```python
"""Editor only: heights of a PCG surface (e.g. a Get_MeshTerrain output) through the data's own
SamplePoint, which casts along the surface's query ray -- no physics and no collision (spec 2.2)."""
import unreal


class Terrain:
    """Stages see only height(x, y); the PCG data object stays inside this wrapper."""

    def __init__(self, data):
        self._data = data

    def height(self, x, y):
        """Surface z under (x, y), or None where the ray misses."""
        transform = unreal.Transform(unreal.Vector(x, y, 0.0), unreal.Rotator(), unreal.Vector(1.0, 1.0, 1.0))
        box = unreal.Box(min=unreal.Vector(-1.0, -1.0, -1.0), max=unreal.Vector(1.0, 1.0, 1.0), is_valid=True)
        res = self._data.k2_sample_point(transform, box, None)
        # A bool UFUNCTION with an out parameter comes back as (ok, point) or, in some bindings, as the
        # point alone; accept both (Task 6 records which one this engine uses).
        if isinstance(res, tuple):
            ok, point = bool(res[0]), res[1]
        elif isinstance(res, unreal.PCGPoint):
            ok, point = True, res
        else:
            ok, point = bool(res), None
        return float(point.transform.translation.z) if ok and point is not None else None
```

- [ ] **Step 5: Write `Content/Python/pypcg/ue/ops.py`**

```python
"""Editor only: 2D polygon booleans through GeometryScript (Clipper2, the same back end PCG's own
nodes use). Rings are [(x, y)] world cm; results are pypcg.geo.Polygon (outer + holes)."""
import unreal

from pypcg.geo import Polygon, bbox, ccw, enclosing_polygon

PL = unreal.GeometryScript_PolygonList
SP = unreal.GeometryScript_SimplePolygon


def _list(rings):
    simple = [SP.conv_array_of_vector2d_to_geometry_script_simple_polygon([unreal.Vector2D(x, y) for x, y in r])
              for r in rings]
    return PL.create_polygon_list_from_simple_polygons(simple)


def _polygons(pl):
    out = []
    for i in range(PL.get_polygon_count(pl)):
        outer, _always_false = PL.get_polygon_vertices(pl, i, -1)      # 5.8 never sets the valid flag (spike)
        holes = [[(v.x, v.y) for v in PL.get_polygon_vertices(pl, i, h)[0]] for h in range(PL.get_polygon_hole_count(pl, i))]
        out.append(Polygon([(v.x, v.y) for v in outer], holes))
    return out


class Ops:
    def intersection(self, rings_a, rings_b):
        return _polygons(PL.polygons_intersection(_list(rings_a), _list(rings_b)))

    def difference(self, rings_a, rings_b):
        return _polygons(PL.polygons_difference(_list(rings_a), _list(rings_b)))

    def union(self, rings):
        return _polygons(PL.polygons_union(_list(rings), True))

    def cut_with_paths(self, ring, paths):
        """Polygon2DOperation(CutWithPaths): the booleans run in the subject polygon's own plane frame,
        like the engine (origin at the vertex mean, yaw -90), because Clipper quantises in that frame
        and the quantisation decides each piece's start vertex (spike detail G3)."""
        n = len(ring)
        cx, cy = sum(q[0] for q in ring) / n, sum(q[1] for q in ring) / n

        def to_l(q):
            return (cy - q[1], q[0] - cx)

        def to_w(q):
            return (cx + q[1], cy - q[0])

        lring = [to_l(q) for q in ring]
        bb = bbox(lring)
        clips = [_list([enclosing_polygon([to_l(q) for q in p], bb)]) for p in paths if len(p) >= 2]
        cur = [lring]
        for c in clips:
            nxt = []
            for r in cur:
                g = _list([r])
                nxt += [p.outer for p in _polygons(PL.polygons_intersection(g, c))]
                nxt += [p.outer for p in _polygons(PL.polygons_difference(g, c))]
            cur = nxt
        return [ccw([to_w(q) for q in r]) for r in cur if len(r) >= 3]
```

- [ ] **Step 6: Write `Content/Python/pypcg/ue/convert.py`**

```python
"""Editor only: PCG data <-> pypcg.geo values (spec 2.2). UObjects stay in locals (traps.md 25).

Read: Polygon2D -> Polygon, spline -> Spline (control points + the engine's polyline), points ->
Points (all attributes), param data -> ParamSet, any other spatial data -> Terrain (a surface).
Write: Polygon -> MakePolygon2DData (C++), Spline -> PCGSplineData.k2_initialize, Points ->
PCGPointData, ParamSet -> PCGParamData."""
import json
import math

import unreal

from pypcg.geo import ParamSet, Points, Polygon, Spline, drop_closing
from pypcg.ue.terrain import Terrain

L = unreal.PyPCGToolsLibrary
H = unreal.PCGMetadataAccessorHelpers
POLYLINE_TOL = 1.0         # max squared distance (cm2) for spline -> polyline, as the engine's nodes use
_LINEAR = 0                # ESplinePointType::Linear

# (PCGMetadataTypes member, geo type name, accessor suffix)
_SPEC = [("FLOAT", "Float", "float"), ("DOUBLE", "Double", "double"), ("INTEGER32", "Int32", "integer32"),
         ("INTEGER64", "Int64", "integer64"), ("VECTOR2", "Vector2", "vector2"), ("VECTOR", "Vector", "vector"),
         ("VECTOR4", "Vector4", "vector4"), ("QUATERNION", "Quat", "quat"), ("TRANSFORM", "Transform", "transform"),
         ("STRING", "String", "string"), ("BOOLEAN", "Bool", "bool"), ("ROTATOR", "Rotator", "rotator"),
         ("NAME", "Name", "name"), ("SOFT_OBJECT_PATH", "SoftObjectPath", "soft_object_path"),
         ("SOFT_CLASS_PATH", "SoftClassPath", "soft_class_path")]
_BY_ENUM = {getattr(unreal.PCGMetadataTypes, e): (name, suffix) for e, name, suffix in _SPEC
            if hasattr(unreal.PCGMetadataTypes, e)}
_SUFFIX = {name: suffix for _, name, suffix in _SPEC}
_DEFAULT = {"Float": 0.0, "Double": 0.0, "Int32": 0, "Int64": 0, "Vector2": (0.0, 0.0), "Vector": (0.0, 0.0, 0.0),
            "Vector4": (0.0, 0.0, 0.0, 0.0), "Quat": (0.0, 0.0, 0.0, 1.0),
            "Transform": ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)), "String": "", "Bool": False,
            "Rotator": (0.0, 0.0, 0.0), "Name": "None", "SoftObjectPath": "", "SoftClassPath": ""}


# ---- unreal value <-> plain value ------------------------------------------------------------
def _path(v):
    return str(v.export_text()).strip('"')


def _plain(type_name, v):
    if type_name == "Vector":
        return (v.x, v.y, v.z)
    if type_name == "Vector2":
        return (v.x, v.y)
    if type_name in ("Vector4", "Quat"):
        return (v.x, v.y, v.z, v.w)
    if type_name == "Rotator":
        return (v.pitch, v.yaw, v.roll)
    if type_name == "Transform":
        r = v.rotation.rotator()
        return (_plain("Vector", v.translation), (r.pitch, r.yaw, r.roll), _plain("Vector", v.scale3d))
    if type_name in ("SoftObjectPath", "SoftClassPath"):
        return _path(v)
    if type_name == "Name":
        return str(v)
    return v


def _rotator(r):
    return unreal.Rotator(pitch=r[0], yaw=r[1], roll=r[2])          # keywords: positional is (roll, pitch, yaw)


def _ue(type_name, v):
    if type_name == "Vector":
        return unreal.Vector(*v)
    if type_name == "Vector2":
        return unreal.Vector2D(*v)
    if type_name == "Vector4":
        return unreal.Vector4(*v)
    if type_name == "Quat":
        return unreal.Quat(*v)
    if type_name == "Rotator":
        return _rotator(v)
    if type_name == "Transform":
        return unreal.Transform(unreal.Vector(*v[0]), _rotator(v[1]), unreal.Vector(*v[2]))
    if type_name == "SoftObjectPath":
        return unreal.SoftObjectPath(v)
    if type_name == "SoftClassPath":
        return unreal.SoftClassPath(v)
    return v


def _infer(v):
    if isinstance(v, bool):
        return "Bool"
    if isinstance(v, int):
        return "Int32"
    if isinstance(v, float):
        return "Double"
    return "String"


# ---- metadata -----------------------------------------------------------------------------------
def _attributes(md):
    names, types = md.get_attributes()
    return [(str(n), _BY_ENUM[t]) for n, t in zip(names, types) if t in _BY_ENUM]


def entry_values(md, key):
    """{attribute: value} of one metadata entry, every supported type (getter chosen by the real
    type, traps.md 36)."""
    p = unreal.PCGPoint()
    p.set_editor_property("metadata_entry", key)
    return {name: _plain(tname, getattr(p, "get_%s_attribute" % suffix)(md, name))
            for name, (tname, suffix) in _attributes(md)}


def _create(md, name, tname):
    getattr(md, "create_%s_attribute" % _SUFFIX[tname])(name, _ue(tname, _DEFAULT[tname]), False, True)


# ---- read -----------------------------------------------------------------------------------------
def read_params(data_in, pin):
    """{parameter: value} from the getters wired into this pin. Each getter node arrives as its own
    PCGParamData holding one entry with one attribute; when the volume overrides a parameter the
    graph instance arrives as additional entries of the same attribute (the override first), so the
    first non-None value for a name wins (measured 2026-10-15 on the demo level's components)."""
    datas, _ = data_in.get_typed_inputs_by_pin_label(pin, unreal.PCGParamData)
    out = {}
    for d in datas:
        md = d.const_metadata()
        for name, _ in _attributes(md):
            value = entry_values(md, 0)[name]
            if value is not None and name not in out:
                out[name] = value
    return out


def read_pin(data_in, pin):
    datas, tagged = data_in.get_typed_inputs_by_pin_label(pin, unreal.PCGData)
    return [(from_pcg(d), frozenset(str(t) for t in td.get_editor_property("tags"))) for d, td in zip(datas, tagged)]


def from_pcg(d):
    if isinstance(d, unreal.PCGPolygon2DData):
        j = json.loads(L.polygon2d_to_json(d))
        outer = [(p[0], p[1]) for p in j["outer"]]
        z = sum(p[2] for p in j["outer"]) / len(j["outer"]) if j["outer"] else 0.0
        return Polygon(outer, [[(p[0], p[1]) for p in h] for h in j["holes"]], z)
    if isinstance(d, unreal.PCGSplineData):
        j = json.loads(L.spline_data_to_json(d, POLYLINE_TOL))
        ctrl = j["control"]
        linear = all(c["type"] == _LINEAR for c in ctrl)
        poly = [tuple(p) for p in j["polyline"]]
        return Spline([tuple(c["p"]) for c in ctrl], closed=j["closed"], linear=linear,
                      tangents=None if linear else [(tuple(c["arrive"]), tuple(c["leave"])) for c in ctrl],
                      polyline=drop_closing(poly) if j["closed"] else poly)
    if isinstance(d, unreal.PCGParamData):
        md = d.const_metadata()
        attrs = _attributes(md)
        return ParamSet(entry_values(md, 0), {name: tname for name, (tname, _) in attrs})
    if isinstance(d, unreal.PCGBasePointData):
        return _points_of(d)
    if isinstance(d, unreal.PCGSpatialData):
        return Terrain(d)
    raise TypeError("PyPCG cannot read %s" % d.get_class().get_name())


def _points_of(d):
    if not isinstance(d, unreal.PCGPointData):
        d = d.to_point_data()                       # PCGPointArrayData and friends (traps.md 46)
    md = d.const_metadata()
    attrs = _attributes(md)
    out = Points()
    for name, (tname, _) in attrs:
        out.declare(name, tname)
    for p in d.get_points():
        t = p.transform
        r = t.rotation.rotator()
        kw = {name: _plain(tname, getattr(p, "get_%s_attribute" % suffix)(md, name)) for name, (tname, suffix) in attrs}
        out.add(_plain("Vector", t.translation), rot=(r.pitch, r.yaw, r.roll), scale=_plain("Vector", t.scale3d),
                density=p.density, bounds_min=_plain("Vector", p.bounds_min), bounds_max=_plain("Vector", p.bounds_max),
                color=_plain("Vector4", p.color), steepness=p.steepness, seed=p.seed, **kw)
    return out


# ---- write ----------------------------------------------------------------------------------------
def to_pcg(v):
    if isinstance(v, Polygon):
        d = L.make_polygon2d_data(json.dumps({"outer": [[x, y, v.z] for x, y in v.outer],
                                              "holes": [[[x, y, v.z] for x, y in h] for h in v.holes]}))
        if d is None:
            raise ValueError("MakePolygon2DData refused a polygon with %d outer vertices" % len(v.outer))
        return d
    if isinstance(v, Spline):
        return _spline_data(v)
    if isinstance(v, Points):
        return _point_data(v)
    if isinstance(v, ParamSet):
        return _param_data(v)
    raise TypeError("PyPCG cannot write %r" % (v,))


def _spline_data(s):
    T = unreal.SplinePointType
    pts = []
    for i, p in enumerate(s.points):
        sp = unreal.SplinePoint()
        sp.set_editor_property("input_key", float(i))
        sp.set_editor_property("position", unreal.Vector(*p))
        if s.linear:
            sp.set_editor_property("type", T.LINEAR)
        elif s.tangents:
            sp.set_editor_property("type", T.CURVE_CUSTOM_TANGENT)
            sp.set_editor_property("arrive_tangent", unreal.Vector(*s.tangents[i][0]))
            sp.set_editor_property("leave_tangent", unreal.Vector(*s.tangents[i][1]))
        else:
            sp.set_editor_property("type", T.CURVE)
        pts.append(sp)
    d = unreal.PCGSplineData()
    d.k2_initialize(pts, bool(s.closed), unreal.Transform(), [])
    return d


def _point_data(pts):
    d = unreal.PCGPointData()
    md = d.mutable_metadata()
    for name, tname in pts.types.items():
        _create(md, name, tname)
    out = []
    for i in range(len(pts)):
        p = unreal.PCGPoint()
        p.transform = unreal.Transform(unreal.Vector(*pts.loc[i]), _rotator(pts.rot[i]), unreal.Vector(*pts.scale[i]))
        p.density = pts.density[i]
        p.bounds_min = unreal.Vector(*pts.bounds_min[i])
        p.bounds_max = unreal.Vector(*pts.bounds_max[i])
        p.color = unreal.Vector4(*pts.color[i])
        p.steepness = pts.steepness[i]
        p.seed = int(pts.seed[i])
        for name, tname in pts.types.items():
            value = pts.attrs[name][i]
            if value is not None:
                p = getattr(H, "set_%s_attribute" % _SUFFIX[tname])(p, md, name, _ue(tname, value))
        out.append(p)
    d.set_points(out)
    return d


def _param_data(ps):
    d = unreal.PCGParamData()
    md = d.mutable_metadata()
    p = unreal.PCGPoint()
    p.set_editor_property("metadata_entry", md.add_entry())
    for name, value in ps.values.items():
        tname = ps.types.get(name) or _infer(value)
        _create(md, name, tname)
        p = getattr(H, "set_%s_attribute" % _SUFFIX[tname])(p, md, name, _ue(tname, value))
    return d
```

- [ ] **Step 7: Run the offline tests** → `test_stage_api.py` 8 passed, `test_host.py` 2 passed. The whole suite has no regressions. (`pypcg.ue` cannot be imported offline; Task 6 exercises it in the editor.)

- [ ] **Step 8: Commit**

```bash
git add Content/Python/pypcg/stage_api.py Content/Python/pypcg/host.py Content/Python/pypcg/ue Tools/pypcg/tests/test_stage_api.py Tools/pypcg/tests/test_host.py
git commit -m "Add the stage contract, the Python-node host and the editor adapters" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Slim graphs in the DSL, the builder and the structural check

**Files:**
- Modify: `Content/Python/pypcg/ir.py` (+`PYTHON_NODE`, `SELF_NODE`)
- Modify: `Content/Python/pypcg/dsl.py` (+`EXTRA_CLASSES`, `dynamic` pins, `SlimGraph`, `official_node`, `official_param`, `roles_of`)
- Modify: `Content/Python/pypcg/compare.py` (+`slim_normalize`, `slim_diff`)
- Modify: `Content/Python/pypcg/build.py` (refactor into `_write`, + `build_slim`, class paths, dynamic pins, slim layout)
- Create: `Content/Python/pypcg/graphs/__init__.py`, `Content/Python/pypcg_build_slim.py`
- Create: `Tools/pypcg/tests/test_slim_dsl.py`

**Interfaces — Produces:**
- `ir.PYTHON_NODE = "PCGPythonDataProcessorSettings"` and `ir.SELF_NODE = "PCGDataFromActorSettings"`.
- `dsl.SlimGraph(stage_module, extra_params=(), more_modules=())`, with:
  - `.py` — the main Python node;
  - `.pynodes` — `{module name: node}`;
  - `.p(name) -> Port` — the getter of a declared parameter, created once and shared;
  - `.keep(official_name, title=None, **pins) -> Node`;
  - `.self_point(title=...) -> Node`.
- `dsl.Graph.python(module_name, inputs, outputs, title="")`.
- `dsl.official_node(stage, name)`, `dsl.official_param(stage, name) -> P`, `dsl.roles_of(paths) -> [role]`.
- `compare.slim_normalize(ir)` and `compare.slim_diff(built, described) -> diffs`.
- `build.build_slim(ir, path, save=True) -> diffs`.
- `graphs.exists(n)` and `graphs.graph(n) -> SlimGraph`.
- Bridge: `pypcg_build_slim.py {"stages": [n] | "all", "profile": "official" | "town", "save": true}` writes to:
  - `/Game/PyPCG/Slim/<graph>` for the official profile;
  - `/Game/PyPCG/Town/<graph>` for the town profile;
  - `/Game/PyPCG/Probe/PCG_PyProbe` for stage 0.

- [ ] **Step 1: Write the failing tests** `Tools/pypcg/tests/test_slim_dsl.py`:

```python
import copy
import types

import pytest

from pypcg import compare, dsl, host, ir as pir
from pypcg.stage_api import Param
from test_dsl import FAKE, PROFILE

STUB = types.SimpleNamespace(__name__="pypcg.stages.s06_districts", STAGE=6, DOC="Districts doc. ", RANDOM=True,
                             PARAMS={"Ratio": Param(0.5, "split ratio", category="Split")},
                             INPUTS={"City": "spline", "Arteries": "spline"}, OUTPUTS=("Areas", "Roads"))
OFFICIAL = {"graph": "/X/PCG_3_1_1_Districts.PCG_3_1_1_Districts", "params": [
    {"name": "Road_Profile", "type": "SoftObject", "value": "/P/SGD.SGD", "container": "None",
     "type_object": "/P/BP.BP_C", "category": "Road Parameters", "meta": {}}],
    "nodes": [{"name": "Subgraph_0", "class": "PCGSubgraphSettings", "title": "Get Roads",
               "subgraph": "/P/Get_ActorDataByRef.Get_ActorDataByRef",
               "overrides": {"ActorReferences": ["/Game/L.L:PersistentLevel.Roads"]}, "settings": {"Seed": 1}},
              {"name": "Spawn", "class": "PCGSubgraphSettings", "title": "Spawn Things",
               "subgraph": "/P/Filter_Tags.Filter_Tags", "overrides": {"FilteredInputTags": "A"},
               "settings": {"Seed": 2}, "pin_defaults": [{"index": 0, "type": "Double", "value": 1.0, "activated": True}]}]}


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    monkeypatch.setattr(dsl, "_LIBRARY", copy.deepcopy(FAKE))       # library() adds classes; keep FAKE intact
    monkeypatch.setattr(dsl, "_official_ir", lambda stage: OFFICIAL)
    monkeypatch.setattr(dsl, "_role_by_path", lambda: {"/Game/L.L:PersistentLevel.Roads": "Roads"})


def _node(ir, cls):
    return [n for n in ir["nodes"] if n["class"] == cls]


def wire_all(g):
    """Feed every still-unwired input pin of the Python node from an actor read (a slim graph must
    wire them all: an unwired dynamic pin culls the node)."""
    wired = {p["label"] for p in g.py._rec["inputs"] if p["edges"]}
    for pin in g.py._rec["dynamic_pins"]["inputs"]:
        if pin not in wired:
            g.connect(g.actor_by_tag(pin), g.py, pin)
    return g


def test_slim_graph_declares_seed_and_params_and_wires_every_getter():
    out = wire_all(dsl.SlimGraph(STUB)).to_ir(PROFILE)
    assert out["graph"] == "PCG_3_1_1_Districts" and out["graph_props"]["Description"] == "Districts doc."
    assert [p["name"] for p in out["params"]] == ["Seed", "Ratio"]
    ratio = out["params"][1]
    assert ratio["tooltip"] == "split ratio" and ratio["category"] == "Split" and ratio["type"] == "Double"
    py = _node(out, pir.PYTHON_NODE)[0]
    assert py["settings"]["InlineScript"] == host.inline_script("s06_districts")
    assert py["settings"]["InputDynamicPins"] == ["Params", "City", "Arteries"]
    assert py["settings"]["OutputDynamicPins"] == ["Areas", "Roads"]
    params_pin = [p for p in py["inputs"] if p["label"] == "Params"][0]
    assert len(params_pin["edges"]) == 2
    assert {n["getter_param"] for n in _node(out, "PCGUserParameterGetSettings")} == {"Seed", "Ratio"}


def test_unwired_python_pin_is_refused():
    g = dsl.SlimGraph(STUB)
    g.connect(g.actor_by_tag("City"), g.py, "City")
    with pytest.raises(ValueError) as e:
        g.to_ir(PROFILE)
    assert "Arteries" in str(e.value)


def test_python_pins_are_checked():
    g = dsl.SlimGraph(STUB)
    with pytest.raises(KeyError):
        g.connect(g.p("Ratio"), g.py, "Nope")
    with pytest.raises(KeyError):
        g.py["Nope"]
    g.out(g.py["Areas"])


def test_getters_are_shared():
    g = dsl.SlimGraph(STUB)
    g.p("Ratio")
    g.p("Ratio")
    assert len(_node(wire_all(g).to_ir(PROFILE), "PCGUserParameterGetSettings")) == 2      # Seed + Ratio, no duplicate


def test_keep_copies_the_official_node_and_turns_actor_paths_into_roles():
    g = dsl.SlimGraph(STUB)
    roads = g.keep("Subgraph_0")
    g.connect(roads, g.py, "City")
    spawn = g.keep("Spawn", PrimaryInput=g.py["Areas"])
    out = wire_all(g).to_ir(PROFILE)
    by_title = {n["title"]: n for n in out["nodes"]}
    assert by_title["Get Roads"]["overrides"]["ActorReferences"] == [PROFILE.ROLES["Roads"]]
    assert "Seed" not in by_title["Get Roads"]["settings"]
    assert by_title["Spawn Things"]["overrides"] == {"FilteredInputTags": "A"}
    assert by_title["Spawn Things"]["pin_defaults"][0]["value"] == 1.0
    assert spawn.name in {n["name"] for n in out["nodes"]}
    with pytest.raises(KeyError):
        g.keep("NoSuchNode")


def test_official_param_copies_the_descriptor():
    p = dsl.official_param(7, "Road_Profile")
    assert p.ir["type"] == "SoftObject" and p.ir["type_object"] == "/P/BP.BP_C" and p.ir["category"] == "Road Parameters"


def test_self_point_reads_the_volume_transform():
    g = dsl.SlimGraph(STUB)
    g.connect(g.self_point(), g.py, "City")
    n = _node(wire_all(g).to_ir(PROFILE), pir.SELF_NODE)[0]
    assert n["settings"] == {"Mode": "GetSinglePoint"}


def test_slim_normalize_maps_exported_pins_to_labels_and_drops_seeds():
    described = wire_all(dsl.SlimGraph(STUB)).to_ir(PROFILE)
    exported = {**described, "nodes": []}
    for n in described["nodes"]:
        e = dict(n, settings=dict(n.get("settings") or {}), pos=[1, 2])
        if n["class"] == pir.PYTHON_NODE:
            for key in ("InputDynamicPins", "OutputDynamicPins"):
                e["settings"][key] = {"PinProperties": [{"Label": label, "AllowedTypes": {}} for label in n["settings"][key]]}
        e["settings"]["Seed"] = 123
        exported["nodes"].append(e)
    assert compare.slim_diff(exported, described) == []
    py = [n for n in exported["nodes"] if n["class"] == pir.PYTHON_NODE][0]
    py["settings"]["InlineScript"] = "changed"
    assert [d["field"] for d in compare.slim_diff(exported, described)] == ["settings.InlineScript"]
```

Run → fails (`SlimGraph` and the other new names are missing).

- [ ] **Step 2: Add to `Content/Python/pypcg/ir.py`** below `IO_NODES`:

```python
PYTHON_NODE = "PCGPythonDataProcessorSettings"     # PCGPythonInterop's Python Data Processor
SELF_NODE = "PCGDataFromActorSettings"             # Get Actor Data; Mode GetSinglePoint reads the volume itself
```

- [ ] **Step 3: Extend `Content/Python/pypcg/dsl.py`**
  1. Change `library()` so it merges these classes, which the official graphs never use as top-level nodes:

```python
EXTRA_CLASSES = {
    _ir.PYTHON_NODE: {"inputs": [], "outputs": []},             # pins are per node (dynamic_pins)
    _ir.SELF_NODE: {"inputs": [], "outputs": ["Out"]},
}


def library():
    """library.json: the real pins and parameters of every subgraph and node class (Task 4), plus
    EXTRA_CLASSES."""
    if not _LIBRARY:
        with open(os.path.join(_HERE, "library.json"), encoding="utf-8") as fh:
            _LIBRARY.update(json.load(fh))
    for cls, pins in EXTRA_CLASSES.items():
        _LIBRARY.setdefault("classes", {}).setdefault(cls, pins)
    return _LIBRARY
```

  2. In `Graph._pins`, as the first check:

```python
        if "dynamic_pins" in rec:
            return rec["dynamic_pins"][which]
```

  3. Give `_add` a `dynamic=None` keyword. Store it with `if dynamic is not None: rec["dynamic_pins"] = {"inputs": list(dynamic[0]), "outputs": list(dynamic[1])}` before `self._nodes.append(rec)`.

  4. Add these methods to `Graph`:

```python
    def python(self, module_name, inputs, outputs, title=""):
        """A Python Data Processor running pypcg.stages.<module_name> through the host (ruling N4)."""
        from .host import inline_script
        settings = {"InlineScript": inline_script(module_name), "bMuteEditorToast": True,
                    "InputDynamicPins": list(inputs), "OutputDynamicPins": list(outputs)}
        return self._add(_ir.PYTHON_NODE, title, settings, {}, dynamic=(inputs, outputs))

    def self_point(self, title="Get Self (Volume Transform)", **kw):
        """The volume's own transform as one point (what Create_Spline_Shape reads when not at the origin)."""
        return self._add(_ir.SELF_NODE, title, {"Mode": "GetSinglePoint"}, kw)
```

  5. Append the official-IR helpers and `SlimGraph`:

```python
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
_OFFICIAL = {}


def _official_ir(stage):
    from . import stages
    if stage not in _OFFICIAL:
        path = os.path.join(_REPO, "Tools", "pypcg", "official_ir", stages.name(stage) + ".json")
        _OFFICIAL[stage] = _ir.load(path)
    return _OFFICIAL[stage]


def _role_by_path():
    from .profiles import official
    return {p: r for r, p in official.ROLES.items()}


def roles_of(paths):
    paths = paths if isinstance(paths, list) else [paths]
    table = _role_by_path()
    unknown = [p for p in paths if p not in table]
    if unknown:
        raise KeyError("actor references without a role: %s" % unknown)
    return [table[p] for p in paths]


def official_node(stage, name):
    for n in _official_ir(stage)["nodes"]:
        if n["name"] == name:
            return n
    near = sorted(n["name"] for n in _official_ir(stage)["nodes"] if n["name"][:5] == name[:5])
    raise KeyError("official stage %s has no node %r; similar: %s" % (stage, name, near))


def official_param(stage, name):
    from . import compare
    for p in _official_ir(stage)["params"]:
        if p["name"] == name:
            return P(p["name"], p["type"], p["value"], p.get("container", "None"), p.get("type_object", ""),
                     p.get("category", ""), compare.tooltip_of(p), compare.advanced_of(p), p.get("meta"))
    raise KeyError("official stage %s has no parameter %r" % (stage, name))


class SlimGraph(Graph):
    """A stage's slim graph (spec 2.1). One user parameter per stage parameter (Seed first), each
    with one getter into its Python node's Params pin; the Python node(s); and whatever scene reads
    (keep, actor_by_tag, ref, self_point) and engine generation nodes (keep) the description adds.
    extra_params are official parameters only kept nodes read; more_modules add Python nodes for
    stage parts that sit after an engine generation node."""

    def __init__(self, stage_module, extra_params=(), more_modules=()):
        from . import stage_api, stages
        self.stage = stage_module
        specs = {}
        for m in (stage_module,) + tuple(more_modules):
            for spec in stage_api.param_specs(m):
                if spec[0] in specs and specs[spec[0]][1] != spec[1]:
                    raise TypeError("parameter %s is %s in one module and %s in another" % (spec[0], specs[spec[0]][1], spec[1]))
                specs.setdefault(spec[0], spec)
        params = [P(n, t, v, type_object=to, category=cat, tooltip=tip) for n, t, v, tip, to, cat in specs.values()]
        super().__init__(stages.name(stage_module.STAGE), params=params + list(extra_params),
                         description=stage_module.DOC.strip())
        self._getters = {}
        self.pynodes = {}
        for m in (stage_module,) + tuple(more_modules):
            name = m.__name__.rsplit(".", 1)[-1]
            node = self.python(name, [stage_api.PARAMS_PIN] + list(m.INPUTS), list(m.OUTPUTS), title="Python: " + name)
            for spec in stage_api.param_specs(m):
                self.connect(self.p(spec[0]), node, stage_api.PARAMS_PIN)
            self.pynodes[name] = node
        self.py = self.pynodes[stage_module.__name__.rsplit(".", 1)[-1]]

    def to_ir(self, profile=None):
        # An unwired dynamic pin is required by execution (UPCGPythonDataProcessorSettings::
        # IsInputPinRequiredByExecution) and makes the graph compiler cull the node, silently.
        for name, node in self.pynodes.items():
            wired = {p["label"] for p in node._rec["inputs"] if p["edges"]}
            missing = [pin for pin in node._rec["dynamic_pins"]["inputs"] if pin not in wired]
            if missing:
                raise ValueError("%s: Python node %s has unwired input pins %s; wire every stage input "
                                 "(an unwired dynamic pin culls the node)" % (self.name, name, missing))
        return super().to_ir(profile)
    def p(self, name):
        """The output of this parameter's getter (one getter per parameter, shared: spec E6)."""
        if name not in self._getters:
            self._getters[name] = self.param(name, name)
        return self._getters[name][name]

    def keep(self, official_name, title=None, **pins):
        """Copy official node `official_name` of this stage: class, subgraph, overrides, settings
        without Seed, pin defaults and title. Actor references become roles, so a profile can point
        them at another level."""
        off = official_node(self.stage.STAGE, official_name)
        overrides = dict(off.get("overrides") or {})
        if "ActorReferences" in overrides:
            overrides["ActorReferences"] = Role(*roles_of(overrides["ActorReferences"]))
        settings = {k: v for k, v in (off.get("settings") or {}).items() if k != "Seed"}
        defaults = [D(d["index"], d.get("type"), d.get("value"), d.get("activated", True))
                    for d in off.get("pin_defaults") or []]
        title = off.get("title", "") if title is None else title
        if off.get("subgraph"):
            return self._add(off["class"], title, settings, pins, subgraph=off["subgraph"], overrides=overrides,
                             defaults=defaults)
        return self._add(off["class"], title, settings, pins, defaults=defaults)
```

`P(...)` gains no new fields (it already takes `category`). Make sure the argument order in the `P(...)` call above matches `P.__init__(self, name, type, value, container="None", type_object="", category="", tooltip="", advanced=False, meta=None)`, which it does through keywords.

- [ ] **Step 4: Add to `Content/Python/pypcg/compare.py`** (at the end):

```python
def slim_normalize(ir):
    """A slim graph's IR in comparable form (spec 3, structural check): node seeds, positions, the
    input/output nodes' settings and comment boxes are not part of a slim graph's description, and
    the Python node's dynamic pins compare by label."""
    out = dict(ir)
    out["comment_boxes"] = []
    nodes = []
    for n in ir["nodes"]:
        st = {k: v for k, v in (n.get("settings") or {}).items() if k != "Seed"}
        if n["name"] in _ir.IO_NODES:
            st = {}
        if n.get("class") == _ir.PYTHON_NODE:
            for key in ("InputDynamicPins", "OutputDynamicPins"):
                v = st.get(key)
                if isinstance(v, dict):
                    st[key] = [str(p.get("Label")) for p in v.get("PinProperties", [])]
        nodes.append(dict(n, settings=st, pos=None))
    out["nodes"] = nodes
    return out


def slim_diff(built, described):
    return diff(slim_normalize(built), slim_normalize(described), {}, check_layout=False)
```

- [ ] **Step 5: Restructure `Content/Python/pypcg/build.py`.** Replace the body of `build()` from `g = asset(path)` down to the edge loop with a call to a new `_write`, and add `build_slim`. The complete new parts are below; `_ok`, `_v`, `_labels`, `_pin`, `asset`, `_clear`, `_resolve_refs`, `_reset_to_class_defaults` and `_layout` stay as they are.

```python
CLASS_PATHS = {_ir.PYTHON_NODE: "/Script/PCGPythonInteropEditor.PCGPythonDataProcessorSettings"}
SLIM_DX, SLIM_DY = 480, 200


def _class(name):
    return unreal.load_class(None, CLASS_PATHS.get(name, "/Script/PCG." + name))


def _write(ir, path, fresh_seeds):
    """Clear the asset at path and write ir into it: parameters, nodes, settings, overrides, pin
    defaults, getter bindings, dynamic pins, titles, comments and edges. Returns (graph, nodes by IR name)."""
    g = asset(path)
    unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(g)
    _clear(g)
    params = []
    for p in ir.get("params", []):
        # Ruling T7a: meta goes through verbatim; the panel's tooltip/advanced are their own fields.
        q = dict(p)
        q["meta"] = dict(p.get("meta") or {})
        q["tooltip"] = compare.tooltip_of(p)
        q["advanced"] = compare.advanced_of(p)
        q.pop("hier_meta", None)
        params.append(q)
    _ok(L.set_graph_user_parameters(g, json.dumps({"params": params})), "user parameters")
    if ir.get("graph_props"):
        _ok(L.set_properties_json(g, json.dumps(ir["graph_props"])), "graph_props")

    made = {_ir.IN_NODE: g.get_input_node(), _ir.OUT_NODE: g.get_output_node()}
    for n in ir["nodes"]:
        if n["name"] in made:
            continue
        cls = _class(n["class"])
        if cls is None:
            raise RuntimeError("%s: no node class %s (is its plugin enabled?)" % (n.get("src") or n["name"], n["class"]))
        node, st = g.add_node_of_type(cls)
        if n.get("subgraph"):
            sg = unreal.EditorAssetLibrary.load_asset(n["subgraph"].split(".")[0])
            if sg is None:
                raise RuntimeError("%s: missing subgraph %s" % (n.get("src") or n["name"], n["subgraph"]))
            st.set_subgraph(sg)
        made[n["name"]] = node

    resets = _reset_to_class_defaults(g, ir, made)
    LAST_CDO_RESETS[:] = resets

    for n in ir["nodes"]:
        where = n.get("src") or n.get("title") or n["name"]
        node = made[n["name"]]
        st = node.get_settings()
        settings = _resolve_refs(n.get("settings") or {}, made)
        if n["name"] in _ir.IO_NODES and "Seed" not in settings and n["class"] in fresh_seeds:
            settings["Seed"] = fresh_seeds[n["class"]]
        dyn_in, dyn_out = settings.pop("InputDynamicPins", None), settings.pop("OutputDynamicPins", None)
        if settings:
            _ok(L.set_properties_json(st, json.dumps(settings)), "%s settings" % where)
        if dyn_in is not None or dyn_out is not None:
            _ok(L.set_dynamic_pin_labels(st, list(dyn_in or []), list(dyn_out or [])), "%s dynamic pins" % where)
        if n.get("subgraph"):
            inst = st.get_editor_property("subgraph_instance")
            for k, v in (n.get("overrides") or {}).items():
                _ok(L.set_instance_parameter(inst, k, _v(v)), "%s override %s" % (where, k))
        for d in n.get("pin_defaults") or []:
            has_value = d.get("type") is not None
            _ok(L.set_pin_default_value(st, int(d["index"]), d.get("type") or "", _v(d.get("value")),
                                        has_value, bool(d.get("activated"))), "%s pin default %s" % (where, d["index"]))
        if n.get("getter_param"):
            _ok(L.bind_user_parameter_getter(st, n["getter_param"]), "%s getter" % where)
        if n.get("title"):
            node.set_editor_property("node_title", n["title"])
        if n.get("title_color"):
            node.set_editor_property("node_title_color", unreal.LinearColor(*n["title_color"]))
        if n.get("comment") or n.get("bubble_visible") or n.get("bubble_pinned"):
            _ok(L.set_node_comment(node, n.get("comment") or "", bool(n.get("bubble_visible")),
                                   bool(n.get("bubble_pinned"))), "%s comment" % where)

    for n in ir["nodes"]:
        dst = made[n["name"]]
        for p in n.get("inputs", []):
            for src_name, src_pin in p["edges"]:
                pin = _pin(dst, "input_pins", p["label"])
                before = len(pin.get_editor_property("edges")) if pin else -1
                g.add_edge(made[src_name], src_pin, dst, p["label"])
                pin = _pin(dst, "input_pins", p["label"])
                if pin is None or len(pin.get_editor_property("edges")) != before + 1:
                    raise RuntimeError("edge %s.%s -> %s.%s not created (traps.md 14); source outputs %s, target inputs %s"
                                       % (src_name, src_pin, n.get("src") or n["name"], p["label"],
                                          _labels(made[src_name], "output_pins"), _labels(dst, "input_pins")))
    return g, made


def build(ir, path, reference_ir, layout_from=None, fresh_seeds=None, check_layout=False, save=True):
    fresh_seeds = fresh_seeds or {}
    g, made = _write(ir, path, fresh_seeds)
    kept_boxes = _layout(g, ir, made, layout_from, fresh_seeds)
    # extract.export, not the raw exporter: the reference IR comes from extract.export, which makes
    # a Seed equal to the class CDO's seed explicit (ruling T3a).
    built = extract.export(g)
    diffs = compare.diff(built, reference_ir, fresh_seeds, check_layout=check_layout)
    if not diffs and save:
        if not unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False):
            raise RuntimeError("save_asset failed for " + path)
    for d in diffs:
        d.setdefault("asset", path)
    if layout_from and kept_boxes != len(layout_from[1].get("comment_boxes", [])):
        diffs.append({"kind": "layout", "where": "graph", "field": "comment_boxes.kept",
                      "a": kept_boxes, "b": len(layout_from[1].get("comment_boxes", []))})
    return diffs


def _slim_layout(g, ir, made):
    """Columns by longest path from the sources; rows in description order."""
    nodes = {n["name"]: n for n in ir["nodes"]}
    depth = {}

    def d(name, stack=()):
        if name not in depth:
            srcs = [e[0] for p in nodes[name].get("inputs", []) for e in p["edges"] if e[0] in nodes and e[0] not in stack]
            depth[name] = 1 + max((d(s, stack + (name,)) for s in srcs), default=-1)
        return depth[name]

    rows = {}
    for n in ir["nodes"]:
        k = d(n["name"])
        i = rows.get(k, 0)
        rows[k] = i + 1
        made[n["name"]].set_node_position(int(k * SLIM_DX), int(i * SLIM_DY))
    _ok(L.set_graph_comment_boxes(g, json.dumps({"boxes": []})), "comment boxes")


def build_slim(ir, path, save=True):
    """Write a slim graph and check it against its own description (spec 3, structural check);
    save only when they agree."""
    g, made = _write(ir, path, {})
    _slim_layout(g, ir, made)
    diffs = compare.slim_diff(extract.export(g), ir)
    if not diffs and save:
        if not unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False):
            raise RuntimeError("save_asset failed for " + path)
    for d in diffs:
        d.setdefault("asset", path)
    return diffs
```

- [ ] **Step 6: Write `Content/Python/pypcg/graphs/__init__.py`**

```python
"""One slim-graph description per stage (spec 2.3): pypcg/graphs/sNN_*.py defines build() -> SlimGraph."""
import importlib
import os

from pypcg import stages

_HERE = os.path.dirname(os.path.abspath(__file__))


def exists(n):
    return os.path.exists(os.path.join(_HERE, stages.entry(n)[2] + ".py"))


def graph(n):
    return importlib.import_module("pypcg.graphs." + stages.entry(n)[2]).build()
```

- [ ] **Step 7: Write `Content/Python/pypcg_build_slim.py`**

```python
import gc
import importlib
import json
import os
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
# The bridge keeps sys.modules between calls; drop pypcg so edits to it take effect.
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())

# pypcg_build_slim.py -- build slim stage graphs from pypcg/graphs/sNN_*.py and check each against its
# own description (spec 3, structural check). Saves only graphs with 0 differences.
# Args: {"stages": [n, ...] | "all", "profile": "official" | "town", "save": true}
#   official -> /Game/PyPCG/Slim/<graph>   actor references into the demo level (V2)
#   town     -> /Game/PyPCG/Town/<graph>   actor references into /Game/PyPCG/L_PyTown
#   stage 0  -> /Game/PyPCG/Probe/PCG_PyProbe


def run(args):
    from pypcg import build, compare, graphs, stages
    profile_name = args.get("profile", "official")
    profile = importlib.import_module("pypcg.profiles." + profile_name)
    if args.get("stages", "all") == "all":
        wanted = [s[0] for s in stages.STAGES if graphs.exists(s[0])]
    else:
        wanted = [int(n) for n in args["stages"]]
    rows = []
    for n in wanted:
        folder = "Probe" if n == 0 else ("Slim" if profile_name == "official" else "Town")
        target = "/Game/PyPCG/%s/%s" % (folder, stages.name(n))
        ir = graphs.graph(n).to_ir(profile)
        diffs = build.build_slim(ir, target, save=bool(args.get("save", True)))
        rows.append({"stage": n, "asset": target, "nodes": len(ir["nodes"]), "diffs": len(diffs),
                     "first": compare.format_diffs(diffs, 15)})
    path = os.path.join(_REPO, "Saved", "Reports", "pypcg_build_slim_%s.json" % profile_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, ensure_ascii=False)
    return rows


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
```

- [ ] **Step 8: Run the offline suite** → `test_slim_dsl.py` 8 passed. Every older test still passes; `test_dsl.py` is untouched because `library()` only adds classes.

- [ ] **Step 9: Commit**

```bash
git add Content/Python/pypcg/ir.py Content/Python/pypcg/dsl.py Content/Python/pypcg/compare.py Content/Python/pypcg/build.py Content/Python/pypcg/graphs Content/Python/pypcg_build_slim.py Tools/pypcg/tests/test_slim_dsl.py
git commit -m "Describe and build slim stage graphs with a Python node, and check them structurally" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: The host probe in the editor (stage 0)

This task proves every host path once, in the real editor, before any stage depends on it. The paths checked are:
- reading a spline, a surface, points, parameters and an empty pin;
- writing a polygon with a hole, a closed spline, points with attributes, and a parameter set;
- the speed of the point writer;
- hot reload of an edited stage file.

**Files:**
- Create: `Content/Python/pypcg/stages/s00_probe.py`, `Content/Python/pypcg/graphs/s00_probe.py`, `Content/Python/pypcg_probe_node.py`
- Create: `Tools/pypcg/tests/test_s00_probe.py`, `Tools/pypcg/tests/test_graphs.py`
- Create (generated, committed): `Content/PyPCG/Probe/PCG_PyProbe.uasset`

**Interfaces — Produces:**
- **`pypcg_probe_node.py` phases** (one per call):
  - `spawn {"at": [x,y,z]?, "params": {...}?}` creates the transient actor `PyPCG_Probe` in the open level, assigns the probe graph and generates it. The actor is never saved.
  - `read` returns `checks`, `all_ok`, `report`, `seconds`, `classes`.
  - `remove` destroys the actor.
- **`test_graphs.py`** is a structural test over every `pypcg/graphs/sNN_*.py` that exists. Every port task relies on it.

- [ ] **Step 1: Write the failing tests**

`Tools/pypcg/tests/test_s00_probe.py`:

```python
import pytest

from fakes import FakeOps, FlatTerrain
from pypcg import geo, stage_api
from pypcg.geo import Points, Spline
from pypcg.stages import s00_probe as S


def inputs():
    vol = Points()
    vol.add((100.0, 200.0, 300.0))
    city = Spline([(0, 0, 0), (1000, 0, 0), (1000, 1000, 0)], closed=True,
                  polyline=[(0, 0, 0), (500, 0, 0), (1000, 0, 0), (1000, 1000, 0)])
    return {"Volume": [(vol, frozenset())], "Terrain": [(FlatTerrain(55.0), frozenset())],
            "Spline": [(city, frozenset({"City"}))], "Empty": []}


def test_probe_writes_every_kind_of_value():
    out, _ = stage_api.execute(S, inputs(), stage_api.defaults(S), FakeOps())
    area = out["Area"][0][0]
    assert geo.area_m2(area) == pytest.approx((10000.0 ** 2 - 2500.0 ** 2) / 1e4) and len(area.holes) == 1
    assert out["Line"][0][0].closed and len(out["Line"][0][0].points) == 4
    pts = out["Points"][0][0]
    assert len(pts) == 3 and pts.attrs["Mesh"] == ["/Engine/BasicShapes/Cube.Cube"] * 3 and pts.attrs["Weight"] == [0.0, 0.5, 1.0]
    assert out["Params"][0][0].values == {"A": 1.5, "Name": "x"}
    assert len(out["Bench"][0][0]) == 0


def test_probe_reports_what_it_read():
    out, _ = stage_api.execute(S, inputs(), dict(stage_api.defaults(S), BenchPoints=2500), FakeOps())
    r = out["Report"][0][0].values
    assert r["TerrainZ"] == 55.0 and r["SplineCount"] == 1 and r["SplineControl"] == 3 and r["SplinePolyline"] == 4
    assert r["SplineClosed"] is True and r["EmptyCount"] == 0 and r["Label"] == "probe" and r["Version"] == S.VERSION
    assert len(out["Bench"][0][0]) == 2500
```

`Tools/pypcg/tests/test_graphs.py`:

```python
"""Every slim-graph description builds, wires every Python input, uses every Python output, and
declares Seed first (spec 3, structural check before the editor build)."""
import pytest

from pypcg import graphs, ir, stage_api, stages
from pypcg.profiles import official

ALL = [0] + [s[0] for s in stages.STAGES]


@pytest.mark.parametrize("n", ALL)
def test_graph_description(n):
    if not graphs.exists(n):
        pytest.skip("not ported yet")
    out = graphs.graph(n).to_ir(official)              # raises on an unwired Python input pin
    py = [x for x in out["nodes"] if x["class"] == ir.PYTHON_NODE]
    assert py, "no Python node"
    used = {(src, pin) for x in out["nodes"] for p in x.get("inputs", []) for src, pin in p["edges"]}
    for node in py:
        for pin in node["settings"]["OutputDynamicPins"]:
            assert (node["name"], pin) in used, "Python output %s of %s is wired to nothing" % (pin, node["title"])
    assert out["params"][0]["name"] == stage_api.SEED
    getters = {x["getter_param"] for x in out["nodes"] if x.get("getter_param")}
    assert {p["name"] for p in out["params"]} <= getters, "a parameter without a getter"
```

Run → `test_s00_probe.py` fails (no module); `test_graphs.py` fails on `s00`.

- [ ] **Step 2: Write `Content/Python/pypcg/stages/s00_probe.py`**

```python
"""Stage 0: the host probe (ruling N9). Not one of the 18 steps. It runs once in the editor to check
every path between PCG data and pypcg.geo values: it reads the volume's own point, a terrain
surface, a spline and an empty pin, and writes a polygon with a hole, a closed spline, points with
attributes, a parameter set, a report of what it read, and optionally many points (timing)."""
from pypcg.geo import ParamSet, Points, Polygon, Spline
from pypcg.stage_api import Param

STAGE = 0
VERSION = 1
DOC = "PyPCG host probe; not part of the town."
RANDOM = True
PARAMS = {"Size": Param(5000.0, "Half size of the probe square (cm)"), "Label": "probe", "Flag": True, "Count": 3,
          "BenchPoints": Param(0, "Also write this many plain points, to time the point writer")}
INPUTS = {"Volume": "points", "Terrain": "surface", "Spline": "spline", "Empty": "any"}
OUTPUTS = ("Area", "Line", "Points", "Params", "Report", "Bench")


def run(inputs, params, ctx):
    vol = inputs["Volume"][0][0]
    cx, cy, cz = vol.loc[0]
    s = params["Size"]
    ring = [(cx - s, cy - s), (cx + s, cy - s), (cx + s, cy + s), (cx - s, cy + s)]
    q = s / 4.0
    hole = [(cx - q, cy - q), (cx - q, cy + q), (cx + q, cy + q), (cx + q, cy - q)]
    surfaces = [v for v, _ in inputs["Terrain"] if hasattr(v, "height")]
    z = surfaces[0].height(cx, cy) if surfaces else None
    splines = [v for v, _ in inputs["Spline"] if isinstance(v, Spline)]
    pts = Points()
    pts.declare("Mesh", "SoftObjectPath")
    pts.declare("Weight", "Double")
    for i in range(params["Count"]):
        pts.add((cx + 1000.0 * i, cy, cz), rot=(0.0, 30.0 * i, 0.0), Mesh="/Engine/BasicShapes/Cube.Cube", Weight=0.5 * i)
    bench = Points()
    for i in range(params["BenchPoints"]):
        bench.add((cx + (i % 1000) * 10.0, cy + (i // 1000) * 10.0, cz))
    report = ParamSet({
        "Version": VERSION, "TerrainZ": z if z is not None else -1.0e9,
        "TerrainKinds": ",".join(sorted(type(v).__name__ for v, _ in inputs["Terrain"])),
        "SplineCount": len(splines), "SplineControl": len(splines[0].points) if splines else 0,
        "SplinePolyline": len(splines[0].polyline or []) if splines else 0,
        "SplineClosed": bool(splines and splines[0].closed), "EmptyCount": len(inputs["Empty"]),
        "Label": params["Label"], "Flag": params["Flag"], "Draw": ctx.rng.random()})
    return {"Area": [(Polygon(ring, [hole], z=cz), ["PyProbeArea"])],
            "Line": [(Spline([(x, y, cz) for x, y in ring], closed=True), ["PyProbeLine"])],
            "Points": [(pts, ["PyProbePoints"])],
            "Params": [(ParamSet({"A": 1.5, "Name": "x"}), ["PyProbeParams"])],
            "Report": [(report, ["PyProbeReport"])],
            "Bench": [(bench, ["PyProbeBench"])]}
```

- [ ] **Step 3: Write `Content/Python/pypcg/graphs/s00_probe.py`**

```python
"""Slim graph of the host probe: the volume itself, the final mesh terrain, the City spline and a read
that finds nothing feed the Python node; every output goes to the graph output."""
from pypcg import dsl
from pypcg.stages import s00_probe as S


def build():
    g = dsl.SlimGraph(S)
    g.connect(g.self_point(), g.py, "Volume")
    terrain = g.sub("Get_MeshTerrain", "Get Mesh Terrain (Final)",
                    set={"MeshPartitionBoundSize": {"X": 300000, "Y": 300000, "Z": 100000}, "MeshPartitionQueryType": "Final"})
    g.connect(terrain, g.py, "Terrain")
    g.connect(g.actor_by_tag("City", "Get City"), g.py, "Spline")
    g.connect(g.actor_by_tag("PyPCG_NoSuchTag", "Get Nothing"), g.py, "Empty")
    for pin in S.OUTPUTS:
        g.out(g.py[pin])
    return g
```

Run the offline tests → `test_s00_probe.py` 2 passed; `test_graphs.py` 1 passed, 18 skipped.

- [ ] **Step 4: Write `Content/Python/pypcg_probe_node.py`**

```python
import gc
import json
import os
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]

# pypcg_probe_node.py -- run the host probe (stage 0) on a transient volume of the open level (Task 6).
# Args: {"phase": "spawn", "at": [x, y, z], "params": {...}} | {"phase": "read"} | {"phase": "remove"}
# The probe actor is never saved; remove it when done. One generation per call (traps.md 38): read
# in the call after spawn.
LABEL = "PyPCG_Probe"
GRAPH = "/Game/PyPCG/Probe/PCG_PyProbe"


def _actor():
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        if a.get_actor_label() == LABEL:
            return a
    return None


def phase_spawn(args):
    from pypcg import stage_api
    a = _actor()
    if a is None:
        x, y, z = args.get("at", [0.0, 0.0, 2000.0])
        a = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(unreal.PCGVolume, unreal.Vector(x, y, z))
        a.set_actor_label(LABEL)
        a.set_actor_scale3d(unreal.Vector(25.0, 25.0, 10.0))
    pc = a.get_component_by_class(unreal.PCGComponent)
    pc.set_editor_property("regenerate_in_editor", False)
    pc.set_graph(unreal.EditorAssetLibrary.load_asset(GRAPH))
    inst = pc.get_editor_property("graph_instance")
    for k, v in (args.get("params") or {}).items():
        err = unreal.PyPCGToolsLibrary.set_instance_parameter(inst, k, json.dumps({"v": v}))
        if err:
            raise RuntimeError("parameter %s: %s" % (k, err))
    os.environ[stage_api.RECORD_ENV] = "1"
    pc.activate(True)
    pc.generate_local(True)
    loc = a.get_actor_location()
    return {"spawned": LABEL, "at": [loc.x, loc.y, loc.z]}


def _trace_z(x, y):
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    res = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, 500000.0), unreal.Vector(x, y, -500000.0),
                                                 unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [],
                                                 unreal.DrawDebugTrace.NONE, True)
    hit = res[-1] if isinstance(res, tuple) else res
    if hit is None:
        return None
    parts = unreal.GameplayStatics.break_hit_result(hit)
    return float(parts[4].z) if parts[0] else None          # (blocking, initial, time, distance, location, ...)


def phase_read(args):
    from pypcg import geo, stage_api
    from pypcg.ue import convert
    a = _actor()
    if a is None:
        return {"abort": "no probe actor; run spawn first"}
    pc = a.get_component_by_class(unreal.PCGComponent)
    items = {}
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        d = td.get_editor_property("data").get_editor_property("data")           # traps.md 46
        tags = sorted(str(t) for t in td.get_editor_property("tags"))
        key = next((t for t in tags if t.startswith("PyProbe")), "?")
        items[key] = (d.get_class().get_name(), convert.from_pcg(d))
    loc = a.get_actor_location()
    s = float((args.get("params") or {}).get("Size", 5000.0))

    def get(key):
        return items.get(key, (None, None))

    checks = {}
    cls, area = get("PyProbeArea")
    checks["area_is_polygon2d"] = cls == "PCGPolygon2DData"
    checks["area_value"] = bool(area) and abs(geo.area_m2(area) - (4 * s * s - s * s / 4) / 1e4) < 0.01 and len(area.holes) == 1
    cls, line = get("PyProbeLine")
    checks["line_closed_spline"] = cls == "PCGSplineData" and bool(line) and line.closed and len(line.points) == 4
    _, pts = get("PyProbePoints")
    checks["points_and_attributes"] = (bool(pts) and len(pts) == 3 and pts.attrs.get("Mesh") == ["/Engine/BasicShapes/Cube.Cube"] * 3
                                       and pts.attrs.get("Weight") == [0.0, 0.5, 1.0] and abs(pts.rot[1][1] - 30.0) < 1e-3)
    _, par = get("PyProbeParams")
    checks["param_set"] = bool(par) and par.values == {"A": 1.5, "Name": "x"}
    _, rep = get("PyProbeReport")
    r = rep.values if rep else {}
    trace = _trace_z(loc.x, loc.y)
    checks["terrain_height_read"] = r.get("TerrainZ", -1e9) > -1e8
    if trace is not None:
        checks["terrain_matches_trace"] = abs(r.get("TerrainZ", -1e9) - trace) < 50.0
    checks["spline_read_with_polyline"] = r.get("SplineCount", 0) >= 1 and r.get("SplinePolyline", 0) > r.get("SplineControl", 0)
    checks["empty_pin_runs"] = r.get("EmptyCount") == 0
    checks["params_reach_stage"] = r.get("Label") == "probe" and r.get("Flag") is True
    run = json.load(open(os.path.join(stage_api.RUNS_DIR, "s00.json"), encoding="utf-8"))
    _, bench = get("PyProbeBench")
    return {"all_ok": all(checks.values()), "checks": checks, "report": r, "trace_z": trace,
            "seconds": run["seconds"], "bench_points": len(bench) if bench else 0,
            "classes": {k: v[0] for k, v in items.items()}}


def phase_remove(args):
    a = _actor()
    ok = bool(a) and unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(a)
    return {"removed": ok}


def run(args):
    return {"spawn": phase_spawn, "read": phase_read, "remove": phase_remove}[args.get("phase", "read")](args)


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
```

- [ ] **Step 5: Relaunch the editor into the demo level** (it was closed for Task 1). First move `Saved/Autosaves` aside (trap 40):

```bash
[ -d Saved/Autosaves ] && mv Saved/Autosaves "Saved/Autosaves_bak_$(date +%Y%m%d_%H%M)"
("/e/UnrealEngine/Engine/Binaries/Win64/UnrealEditor.exe" "E:/PCG_Claude/PCG_Claude.uproject" "/CitySamplePCG/Levels/L_CitySamplePCG_Demo" > /dev/null 2>&1 &)
for i in $(seq 1 90); do netstat -ano | grep -q "127.0.0.1:8777.*LISTENING" && { echo up; break; }; sleep 10; done
```

- [ ] **Step 6: Build the probe graph and run the probe.**
  1. `run_unreal_script("pypcg_build_slim.py", {"stages": [0]})` → one row, `diffs: 0`.
  2. Next call: `run_unreal_script("pypcg_probe_node.py", {"phase": "spawn"})`.
  3. Next call: `{"phase": "read"}` → `all_ok: true`. All checks must hold.

  If a check fails, the cause is in the adapters (`pypcg.ue.convert` / `terrain` / `ops`) or the C++ helpers. Introspect the failing API with `dir()` (the driving-unreal-via-mcp skill) and fix the adapter. Rebuild C++ only if a helper itself is wrong, which needs both editors closed. Record each finding in `.claude/skills/city-sample-pcg-city-builder/references/traps.md` as a new numbered row. Examples: what `k2_sample_point` returns; whether `TerrainKinds` names the MeshPartition class.

  If `terrain_height_read` cannot be made to work, apply the spec §4.3 fallback:
  - `pypcg.ue.terrain.Terrain.height` traces a line instead (as `_trace_z` does);
  - trace only in the generation that follows the terrain write;
  - record this in the ledger.

- [ ] **Step 7: Time the point writer.** `{"phase": "spawn", "params": {"BenchPoints": 100000}}`, then `{"phase": "read", "params": {"BenchPoints": 100000}}`.
  - Expected: `bench_points: 100000`, `all_ok: true`, `seconds < 3.0`. G7 predicts about 0.7 s for 100k points without attributes.
  - Record the number in the ledger. If it is over 10 s, stop and report: spec §4.3's "bulk operation back to native" question then applies to every scatter stage.

- [ ] **Step 8: Hot reload.**
  1. Set `VERSION = 2` in `s00_probe.py`.
  2. Run `{"phase": "spawn"}` (no rebuild), then `{"phase": "read"}` → `report.Version == 2`.
  3. Set it back to `VERSION = 1`, then `{"phase": "remove"}` → `removed: true`.

- [ ] **Step 9: Commit**

```bash
git add Content/Python/pypcg/stages/s00_probe.py Content/Python/pypcg/graphs/s00_probe.py Content/Python/pypcg_probe_node.py Tools/pypcg/tests/test_s00_probe.py Tools/pypcg/tests/test_graphs.py Content/PyPCG/Probe .claude/skills/city-sample-pcg-city-builder/references/traps.md
git commit -m "Probe the Python-node host in the editor: every value kind, terrain heights, empty pins, hot reload" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: The V2 harness and the port tooling

This task builds the tools every port uses:
- **Census:** what a volume produced.
- **Pure V2 statistics:** the thresholds and verdicts.
- **The bridge script:** swaps a volume between the official and the slim graph, generates in strict order, and records the results.
- **Port briefs:** each stage's contract, read from its official IR.
- **Demo overrides:** the demo level's parameter overrides.

It also checks in the editor that, once `regenerate_in_editor` is off, generating one stage no longer regenerates the stages that read it (trap 33).

**Files:**
- Create: `Content/Python/pypcg/v2.py`, `Content/Python/pypcg/v2_thresholds.json`, `Content/Python/pypcg/census.py`
- Create: `Content/Python/pypcg/checks/__init__.py`, `Content/Python/pypcg_compare_stage.py`, `Content/Python/pypcg_v1_editor.py`
- Create: `Tools/pypcg/port_brief.py`, `Tools/pypcg/tests/test_v2.py`, `Tools/pypcg/tests/test_port_brief.py`
- Create (generated, committed): `Tools/pypcg/data/demo_overrides.json`, `docs/pypcg/stages/s01-brief.md … s18-brief.md`
- Create: `docs/pypcg-v2-thresholds.md`
- Modify: `Content/Python/pypcg/profiles/official.py` (`ROLE_LABELS`)

**Interfaces — Produces:**
- **`pypcg.v2`:**
  - `V2_SEEDS = (7, 13, 101, 977, 42)` (42 last: the downstream check runs on it);
  - `describe(value, tags, cls="")`, `summarize(items)`;
  - `thresholds(stage)`;
  - `verdict(official, runs, deterministic, th) -> {"pass", "failures", "rows"}`;
  - `downstream(pairs) -> failures`, `same(a, b) -> bool`;
  - `markdown(stage, verdict, down_failures, notes) -> str`.
- **`pypcg.census`:**
  - `actor_by_label`, `volume(n)`, `component(n)`;
  - `outputs(pc)`, `instances(actor)`, `record(n)`;
  - `overrides(pc)`, `apply_overrides(pc, values) -> {"set": [...], "skipped": {...}}`.
- **`pypcg.checks.sNN.check(inputs, params, outputs, ops, official) -> [failure]`**, optional per stage.
  - `inputs` is None when the run's inputs cannot be recorded (surfaces).
  - `official` is `{tag: [pypcg.geo values]}`, read live from the volume when it holds its official graph; otherwise None.
- **`pypcg_compare_stage.py`** phases:
  - `prepare`;
  - `gen {"stage", "variant": "official"|"slim", "seed"?}`;
  - `read {"stage", "as"}`;
  - `verdict {"stage"}`;
  - `fingerprint {"save"|"compare": name}`;
  - `restore`.
- **`pypcg_v1_editor.py {"stage": n}`** → `{"failures", "replayed", "deterministic"}`.
- **`port_brief.py N | all [--stdout]`** → `docs/pypcg/stages/sNN-brief.md`.

**Ruling N10 (added here):** a tag whose official item count is under 5 skips the item-count and total-area comparisons (spec §3 V2.4). Its summed length and its point count are still compared, because one data item may hold thousands of points. *Cost if wrong:* one threshold row per such tag.

- [ ] **Step 1: Write the failing tests**

`Tools/pypcg/tests/test_v2.py`:

```python
import pytest

from pypcg import geo, v2

TH = dict(v2.DEFAULTS)


def item(tags, kind="polygon", area=0.0, length=0.0, points=0, bbox=((0, 0), (100, 100))):
    return {"tags": list(tags), "class": "", "kind": kind, "area_m2": area, "length_m": length, "points": points,
            "bbox": [list(bbox[0]), list(bbox[1])]}


def rec(items, total=0, per_mesh=None, generated=True):
    return {"generated": generated, "items": items, "instances": {"total": total, "per_mesh": per_mesh or {}, "components": {}}}


def districts(scale=1.0, n=6):
    return rec([item(["SmallDistricts", "Type:Polygon2D"], area=100.0 * scale) for _ in range(n)])


def test_describe_and_summarize():
    poly = geo.Polygon([(0, 0), (10000, 0), (10000, 10000), (0, 10000)])
    d = v2.describe(poly, ["Lots", "Type:Polygon2D"], "PCGPolygon2DData")
    assert d["kind"] == "polygon" and d["area_m2"] == pytest.approx(10000.0)
    s = v2.summarize([d, d])
    assert set(s) == {"Lots"} and s["Lots"]["n"] == 2 and s["Lots"]["area_m2"] == pytest.approx(20000.0)
    line = v2.describe(geo.Spline([(0, 0, 0), (100, 0, 0)]), ["Roads"])
    assert line["kind"] == "spline" and line["length_m"] == pytest.approx(1.0)


def test_identical_runs_pass():
    v = v2.verdict(districts(), [districts()] * 5, False, TH)
    assert v["pass"] and not v["failures"]


def test_missing_tag_fails_and_bookkeeping_tags_are_ignored():
    run = rec([item(["Type:Polygon2D"], area=100.0)])
    v = v2.verdict(districts(), [run], False, TH)
    assert not v["pass"] and any("SmallDistricts" in f for f in v["failures"])


def test_median_decides():
    runs = [districts(1.0), districts(1.05), districts(0.95), districts(2.0), districts(0.1)]
    assert v2.verdict(districts(), runs, False, TH)["pass"]
    assert not v2.verdict(districts(), [districts(1.3)] * 5, False, TH)["pass"]


def test_few_items_skip_count_and_area_but_not_points():
    off = rec([item(["Big"], area=100.0, points=1000)])
    assert v2.verdict(off, [rec([item(["Big"], area=300.0, points=1000)])], False, TH)["pass"]
    assert not v2.verdict(off, [rec([item(["Big"], area=100.0, points=100)])], False, TH)["pass"]


def test_bbox_outside_the_official_one_fails():
    far = rec([item(["SmallDistricts"], area=100.0, bbox=((0, 0), (500000, 100)))] * 6)
    v = v2.verdict(districts(), [far], False, TH)
    assert not v["pass"] and any("outside" in f for f in v["failures"])


def test_kind_change_fails():
    off = rec([item(["Roads"], kind="spline", length=10.0)] * 6)
    run = rec([item(["Roads"], kind="points", points=10)] * 6)
    assert not v2.verdict(off, [run], False, TH)["pass"]


def test_instances_and_mesh_shares():
    off = rec([], total=1000, per_mesh={"/A": 500, "/B": 500})
    assert v2.verdict(off, [rec([], total=1100, per_mesh={"/A": 560, "/B": 540})], False, TH)["pass"]
    assert not v2.verdict(off, [rec([], total=1000, per_mesh={"/A": 800, "/B": 200})], False, TH)["pass"]


def test_deterministic_stages_use_the_tight_tolerance():
    assert not v2.verdict(districts(), [districts(1.05)], True, TH)["pass"]
    assert v2.verdict(districts(), [districts(1.005)], True, TH)["pass"]


def test_downstream_failures():
    ok = rec([item(["X"])], total=10)
    assert v2.downstream({7: (ok, ok)}) == []
    assert v2.downstream({7: (ok, rec([item(["X"])], total=0))}) == ["stage 7: no instances (official 10)"]
    assert v2.downstream({7: (ok, rec([], total=10, generated=False))})[0].startswith("stage 7: not generated")


def test_thresholds_merge_stage_overrides(tmp_path, monkeypatch):
    path = tmp_path / "t.json"
    path.write_text('{"default": {"area": 0.1}, "stages": {"6": {"area": 0.2}}}')
    monkeypatch.setattr(v2, "THRESHOLDS", str(path))
    assert v2.thresholds(6)["area"] == 0.2 and v2.thresholds(7)["area"] == 0.1 and v2.thresholds(7)["count"] == 0.25


def test_same_compares_rounded_summaries():
    assert v2.same(districts(), districts()) and not v2.same(districts(), districts(1.01))
```

`Tools/pypcg/tests/test_port_brief.py`:

```python
import port_brief


def test_districts_contract():
    ir = port_brief.load(6)
    cls = port_brief.classify(ir)
    assert {n for n, c in cls.items() if c == "input"} == {"Subgraph_0", "Subgraph_1"}
    assert not [n for n, c in cls.items() if c == "gen"]              # its 4 meshes are debug-only
    assert {"Branch_0", "Branch_SmallDebug", "Subgraph_9"} <= {n for n, c in cls.items() if c == "drop"}
    tags = {t for _, _, ts in port_brief.output_tags(ir) for t in ts}
    assert tags == {"ArteryRoads", "CollectorRoads", "localRoads", "UndividableDistricts", "SmallDistricts",
                    "MediumDistricts", "LargeDistricts"}
    readers = port_brief.consumers(6)
    assert (7, "FilterByTag 'ArteryRoads'") in readers and (9, "Filter_Tags 'SmallDistricts'") in readers


def test_roads_keep_generation_and_drop_the_partition_branch():
    cls = port_brief.classify(port_brief.load(7))
    kept = {n for n, c in cls.items() if c == "gen"}
    assert {"Subgraph_26", "Subgraph_7", "Subgraph_46", "Subgraph_37"} <= kept     # Spawn Road, Crosswalks, 2 terrain writes
    assert cls["Subgraph_4"] == "drop" and cls["Loop_0"] == "drop"                 # GridPartition, LoopSpawnActorPerData


def test_totals_over_the_18_graphs():
    import collections
    from pypcg import stages
    total = collections.Counter()
    for n, *_ in stages.STAGES:
        total.update(port_brief.classify(port_brief.load(n)).values())
    assert (total["gen"], total["input"], total["drop"]) == (109, 69, 175)
```

Run → both fail (no modules).

- [ ] **Step 2: Write `Content/Python/pypcg/v2.py`**

```python
"""V2 (spec 3): compare what a slim graph produced against the official graph, by tag and by mesh.
Pure Python: census.py feeds it plain records.

A record is {"generated": bool, "items": [describe(...)], "instances": {"total", "per_mesh", "components"}}."""
import json
import os
import statistics

from . import geo

V2_SEEDS = (7, 13, 101, 977, 42)            # 42 last: the downstream check runs on the last slim run
DEFAULTS = {"count": 0.25, "area": 0.10, "length": 0.10, "points": 0.25, "instances": 0.25, "share_pp": 10.0,
            "share_min": 0.01, "deterministic": 0.01, "min_count": 5, "bbox_margin_cm": 20000.0}
THRESHOLDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v2_thresholds.json")
COMPATIBLE = {"polygon": {"polygon"}, "spline": {"spline"}, "points": {"points"}, "param": {"param"},
              "other": {"other", "polygon", "spline", "points"}}


def _bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [[min(xs), min(ys)], [max(xs), max(ys)]] if pts else None


def describe(value, tags, cls=""):
    out = {"tags": sorted(tags), "class": cls, "kind": "other", "area_m2": 0.0, "length_m": 0.0, "points": 0, "bbox": None}
    if isinstance(value, geo.Polygon):
        out.update(kind="polygon", area_m2=geo.area_m2(value), bbox=_bbox(value.outer))
    elif isinstance(value, geo.Spline):
        pts = list(value.polyline or value.points)
        ring = pts + pts[:1] if value.closed else pts
        out.update(kind="spline", length_m=geo.path_length(ring) / 100.0, bbox=_bbox(pts))
    elif isinstance(value, geo.Points):
        out.update(kind="points", points=len(value), bbox=_bbox(value.loc))
    elif isinstance(value, geo.ParamSet):
        out.update(kind="param")
    return out


def summarize(items):
    """{tag: {"n", "area_m2", "length_m", "points", "kinds", "bbox"}}; tags with ':' are PCGPrimitives
    bookkeeping and are ignored (ruling N3)."""
    out = {}
    for it in items:
        tags = [t for t in it["tags"] if ":" not in t] or ["(untagged)"]
        for t in tags:
            s = out.setdefault(t, {"n": 0, "area_m2": 0.0, "length_m": 0.0, "points": 0, "kinds": [], "bbox": None})
            s["n"] += 1
            s["area_m2"] += it["area_m2"]
            s["length_m"] += it["length_m"]
            s["points"] += it["points"]
            if it["kind"] not in s["kinds"]:
                s["kinds"].append(it["kind"])
            if it["bbox"]:
                b = s["bbox"]
                s["bbox"] = it["bbox"] if b is None else [[min(b[0][0], it["bbox"][0][0]), min(b[0][1], it["bbox"][0][1])],
                                                          [max(b[1][0], it["bbox"][1][0]), max(b[1][1], it["bbox"][1][1])]]
    return out


def thresholds(stage):
    th = dict(DEFAULTS)
    if os.path.exists(THRESHOLDS):
        doc = json.load(open(THRESHOLDS, encoding="utf-8"))
        th.update(doc.get("default", {}))
        th.update(doc.get("stages", {}).get(str(stage), {}))
    return th


def _within(inner, outer, margin):
    return (inner[0][0] >= outer[0][0] - margin and inner[0][1] >= outer[0][1] - margin
            and inner[1][0] <= outer[1][0] + margin and inner[1][1] <= outer[1][1] + margin)


def verdict(official, runs, deterministic, th):
    so, sr = summarize(official["items"]), [summarize(r["items"]) for r in runs]
    failures, rows = [], []
    for tag, o in sorted(so.items()):
        for i, s in enumerate(sr):
            r = s.get(tag)
            if not r:
                failures.append("run %d: tag %s missing" % (i, tag))
                continue
            allowed = set().union(*(COMPATIBLE[k] for k in o["kinds"]))
            if not set(r["kinds"]) <= allowed:
                failures.append("run %d: tag %s is %s, official %s" % (i, tag, r["kinds"], o["kinds"]))
            if o["bbox"] and r["bbox"] and not _within(r["bbox"], o["bbox"], th["bbox_margin_cm"]):
                failures.append("run %d: tag %s outside the official bounds + %.0f m" % (i, tag, th["bbox_margin_cm"] / 100))
        for metric, key, tol in (("count", "n", th["count"]), ("area", "area_m2", th["area"]),
                                 ("length", "length_m", th["length"]), ("points", "points", th["points"])):
            off = o[key]
            if not off:
                continue
            if metric in ("count", "area") and o["n"] < th["min_count"]:
                rows.append({"tag": tag, "metric": metric, "official": off, "skipped": "fewer than %d items" % th["min_count"]})
                continue
            vals = [s.get(tag, {}).get(key, 0) for s in sr]
            med = statistics.median(vals)
            limit = th["deterministic"] if deterministic else tol
            rel = (med - off) / off
            ok = abs(rel) <= limit
            rows.append({"tag": tag, "metric": metric, "official": off, "median": med, "runs": vals, "rel": rel, "limit": limit, "ok": ok})
            if not ok:
                failures.append("tag %s %s: median %.4g vs official %.4g (%+.1f %%, limit %.0f %%)"
                                % (tag, metric, med, off, 100 * rel, 100 * limit))
    oi = official["instances"]
    if oi["total"]:
        totals = [r["instances"]["total"] for r in runs]
        med = statistics.median(totals)
        limit = th["deterministic"] if deterministic else th["instances"]
        rel = (med - oi["total"]) / oi["total"]
        rows.append({"tag": "(instances)", "metric": "total", "official": oi["total"], "median": med, "runs": totals,
                     "rel": rel, "limit": limit, "ok": abs(rel) <= limit})
        if abs(rel) > limit:
            failures.append("instances: median %d vs official %d (%+.1f %%)" % (med, oi["total"], 100 * rel))
        meshes = set(oi["per_mesh"]) | {m for r in runs for m in r["instances"]["per_mesh"]}
        for m in sorted(meshes):
            off_share = oi["per_mesh"].get(m, 0) / oi["total"]
            shares = [r["instances"]["per_mesh"].get(m, 0) / r["instances"]["total"] if r["instances"]["total"] else 0.0 for r in runs]
            med_share = statistics.median(shares)
            if max(off_share, med_share) < th["share_min"]:
                continue
            diff_pp = 100 * (med_share - off_share)
            ok = abs(diff_pp) <= th["share_pp"]
            rows.append({"tag": "(mesh)", "metric": m, "official": off_share, "median": med_share, "runs": shares,
                         "rel": diff_pp, "limit": th["share_pp"], "ok": ok})
            if not ok:
                failures.append("mesh %s: share %.1f %% vs official %.1f %%" % (m, 100 * med_share, 100 * off_share))
    return {"pass": not failures, "failures": failures, "rows": rows}


def downstream(pairs):
    """pairs {stage: (official record, record read with the slim upstream)}: each must still generate,
    with instances and outputs where the official one has them (spec 3, V2.3)."""
    out = []
    for k, (o, r) in sorted(pairs.items()):
        if not r["generated"]:
            out.append("stage %d: not generated" % k)
            continue
        if o["instances"]["total"] and not r["instances"]["total"]:
            out.append("stage %d: no instances (official %d)" % (k, o["instances"]["total"]))
        if o["items"] and not r["items"]:
            out.append("stage %d: no outputs (official %d)" % (k, len(o["items"])))
    return out


def same(a, b):
    """True when two records summarise identically (counts exact, sizes to 1e-6 relative)."""
    sa, sb = summarize(a["items"]), summarize(b["items"])
    if set(sa) != set(sb) or a["instances"]["per_mesh"] != b["instances"]["per_mesh"]:
        return False
    for t in sa:
        for k in ("n", "points"):
            if sa[t][k] != sb[t][k]:
                return False
        for k in ("area_m2", "length_m"):
            if abs(sa[t][k] - sb[t][k]) > 1e-6 * max(1.0, abs(sa[t][k])):
                return False
    return True


def markdown(stage, v, down_failures, notes=()):
    lines = ["# V2 -- stage %d" % stage, "", "Verdict: **%s**" % ("pass" if v["pass"] and not down_failures else "FAIL"), ""]
    lines += ["| Tag | Metric | Official | Median | Runs | Diff | Limit | OK |", "|---|---|---|---|---|---|---|---|"]
    for r in v["rows"]:
        if "skipped" in r:
            lines.append("| %s | %s | %.4g | - | - | - | %s | - |" % (r["tag"], r["metric"], r["official"], r["skipped"]))
        else:
            lines.append("| %s | %s | %.4g | %.4g | %s | %+.3g | %.3g | %s |" % (
                r["tag"], r["metric"], r["official"], r["median"], ", ".join("%.4g" % x for x in r["runs"]),
                r["rel"], r["limit"], "yes" if r["ok"] else "**no**"))
    lines += ["", "Failures:", ""] + ["- " + f for f in v["failures"] + list(down_failures)] if v["failures"] or down_failures else ["", "Failures: none"]
    lines += ["", "Notes:", ""] + ["- " + n for n in notes] if notes else []
    return "\n".join(lines) + "\n"
```

`Content/Python/pypcg/v2_thresholds.json`:

```json
{"default": {"count": 0.25, "area": 0.10, "length": 0.10, "points": 0.25, "instances": 0.25, "share_pp": 10.0,
             "share_min": 0.01, "deterministic": 0.01, "min_count": 5, "bbox_margin_cm": 20000.0},
 "stages": {}}
```

`docs/pypcg-v2-thresholds.md`:

```markdown
# V2 threshold changes

Every change to `Content/Python/pypcg/v2_thresholds.json` is listed here with its reason (spec 3, V2.4).
The defaults are the spec's: area and length ±10 %, counts ±25 %, per-mesh share ±10 percentage points,
deterministic steps ±1 %, over the median of 5 seeds; tags with fewer than 5 official items compare
structure, length and points only (ruling N10).

| Date | Stage | Key | Old | New | Why |
|---|---|---|---|---|---|
```

- [ ] **Step 3: Write `Content/Python/pypcg/census.py`**

```python
"""Editor only: what a stage volume produced, as plain records for pypcg.v2 (spec 3, V2)."""
import json

import unreal

from pypcg import stages, v2
from pypcg.ue import convert

DEBUG_MESH = "/PCG/DebugObjects/"


def actor_by_label(label):
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        try:
            if str(a.get_actor_label()) == label:
                return a
        except Exception:
            continue
    return None


def volume(n):
    a = actor_by_label(stages.LABEL(n))
    if a is None:
        raise RuntimeError("no actor labelled %s in this level" % stages.LABEL(n))
    return a


def component(n):
    return volume(n).get_component_by_class(unreal.PCGComponent)


def outputs(pc):
    items = []
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        d = td.get_editor_property("data").get_editor_property("data")            # traps.md 46
        tags = [str(t) for t in td.get_editor_property("tags")]
        try:
            value = convert.from_pcg(d)
        except TypeError:
            value = None
        items.append(v2.describe(value, tags, d.get_class().get_name()))
    return items


def instances(actor):
    per_mesh, components = {}, {}
    for c in actor.get_components_by_class(unreal.PrimitiveComponent):
        cls = c.get_class().get_name()
        if cls == "BrushComponent":
            continue
        components[cls] = components.get(cls, 0) + 1
        if isinstance(c, unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            path = sm.get_path_name() if sm else ""
            if path.startswith(DEBUG_MESH):
                continue
            per_mesh[path] = per_mesh.get(path, 0) + int(c.get_instance_count())
    return {"total": sum(per_mesh.values()), "per_mesh": per_mesh, "components": components}


def record(n):
    a = volume(n)
    pc = a.get_component_by_class(unreal.PCGComponent)
    g = pc.get_graph()
    return {"stage": n, "graph": g.get_path_name() if g else None, "generated": bool(pc.get_editor_property("generated")),
            "items": outputs(pc), "instances": instances(a)}


def overrides(pc):
    inst = pc.get_editor_property("graph_instance")
    return json.loads(unreal.PyPCGToolsLibrary.export_instance_overrides(inst)) if inst else {}


def apply_overrides(pc, values):
    """Set each value on the component's graph instance; names the graph does not have are skipped
    and reported (a slim graph drops debug, partition and merged seed parameters: ruling N5)."""
    inst = pc.get_editor_property("graph_instance")
    done, skipped = [], {}
    for k, v in values.items():
        err = unreal.PyPCGToolsLibrary.set_instance_parameter(inst, k, json.dumps({"v": v}))
        if err:
            skipped[k] = err
        else:
            done.append(k)
    return {"set": done, "skipped": skipped}
```

- [ ] **Step 4: Write `Content/Python/pypcg/checks/__init__.py`**

```python
"""V1 checks that need the editor's booleans or a recorded run: pypcg/checks/sNN.py defines
check(inputs, params, outputs, ops, official) -> [failure]. inputs is None when the run's inputs
cannot be recorded (a terrain surface); outputs are pypcg.geo values rebuilt from the run record;
official is {tag: [pypcg.geo values]} of the volume's current official output, or None."""
```

- [ ] **Step 5: Write `Content/Python/pypcg_compare_stage.py`**

```python
import gc
import json
import os
import shutil
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())

# pypcg_compare_stage.py -- V2 in the demo level (spec 3). ONE generation per call; read it in the next.
# NEVER save the level: every change here is in memory and `restore` undoes the graph swaps.
#   prepare                                 record graphs/overrides/regen flags; turn regen-in-editor off
#   gen {"stage", "variant", "seed"?}       variant "official" | "slim"; slim swaps in /Game/PyPCG/Slim/<graph>
#   read {"stage", "as"}                    census -> Saved/Reports/v2/sNN/<as>.json (+ the run record for slim)
#   verdict {"stage"}                       pypcg.v2 over the files of that stage -> verdict.json + docs/pypcg/v2/sNN.md
#   fingerprint {"save" | "compare": name}  which volumes' outputs changed between two calls
#   restore                                 official graphs, overrides and regen flags back on every volume
OUT = os.path.join(_REPO, "Saved", "Reports", "v2")
STATE = os.path.join(OUT, "_state.json")
DEMO_OVERRIDES = os.path.join(_REPO, "Tools", "pypcg", "data", "demo_overrides.json")


def _load(path, default=None):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True)


def _stage_dir(n):
    return os.path.join(OUT, "s%02d" % n)


def phase_prepare(args):
    from pypcg import census, stages
    state = _load(STATE, {})
    for n, label, *_ in stages.STAGES:
        pc = census.component(n)
        if label not in state:                                     # first prepare: the shipped state
            g = pc.get_graph()
            state[label] = {"graph": g.get_path_name() if g else None, "overrides": census.overrides(pc),
                            "regen": bool(pc.get_editor_property("regenerate_in_editor")),
                            "seed": int(pc.get_editor_property("seed"))}
        pc.set_editor_property("regenerate_in_editor", False)      # every regeneration is explicit (trap 33)
    _save(STATE, state)
    if not os.path.exists(DEMO_OVERRIDES) or args.get("refresh"):
        _save(DEMO_OVERRIDES, {label: s["overrides"] for label, s in state.items()})
    return {"volumes": len(state), "regen_off": True, "demo_overrides": DEMO_OVERRIDES}


def phase_gen(args):
    from pypcg import census, stage_api, stages
    n, variant = int(args["stage"]), args["variant"]
    state = _load(STATE)
    if state is None:
        return {"abort": "run prepare first"}
    label = stages.LABEL(n)
    pc = census.component(n)
    applied = {}
    if variant == "slim":
        pc.set_graph(unreal.EditorAssetLibrary.load_asset("/Game/PyPCG/Slim/" + label))
        values = dict(state[label]["overrides"])
        values[stage_api.SEED] = int(args.get("seed", stage_api.SEED_DEFAULT))
        applied = census.apply_overrides(pc, values)               # after set_graph (trap 44)
        os.environ[stage_api.RECORD_ENV] = "1"
    else:
        pc.set_graph(unreal.EditorAssetLibrary.load_asset(state[label]["graph"].split(".")[0]))
        applied = census.apply_overrides(pc, state[label]["overrides"])
    pc.activate(True)
    pc.generate_local(True)
    return {"stage": n, "variant": variant, "graph": pc.get_graph().get_path_name(), "overrides": applied}


def phase_read(args):
    from pypcg import census, stage_api
    n, name = int(args["stage"]), args["as"]
    rec = census.record(n)
    _save(os.path.join(_stage_dir(n), name + ".json"), rec)
    run = os.path.join(stage_api.RUNS_DIR, "s%02d.json" % n)
    if "slim" in name and os.path.exists(run):
        shutil.copyfile(run, os.path.join(_stage_dir(n), name + ".run.json"))
    tags = {}
    for it in rec["items"]:
        for t in it["tags"]:
            if ":" not in t:
                tags[t] = tags.get(t, 0) + 1
    return {"stage": n, "as": name, "generated": rec["generated"], "graph": rec["graph"], "tags": tags,
            "instances": rec["instances"]["total"]}


def phase_verdict(args):
    from pypcg import stages, v2
    n = int(args["stage"])
    d = _stage_dir(n)
    official = _load(os.path.join(d, "official.json"))
    module = stages.spec(n)
    seeds = v2.V2_SEEDS if module.RANDOM else (v2.V2_SEEDS[-1],)
    runs = [_load(os.path.join(d, "slim_%d.json" % s)) for s in seeds]
    if official is None or any(r is None for r in runs):
        return {"abort": "missing official.json or slim_<seed>.json for seeds %s" % (seeds,)}
    v = v2.verdict(official, runs, not module.RANDOM, v2.thresholds(n))
    pairs = {}
    for k in stages.DOWNSTREAM.get(n, []):
        o, r = _load(os.path.join(d, "down_%d_official.json" % k)), _load(os.path.join(d, "down_%d_slim.json" % k))
        if o is None or r is None:
            return {"abort": "missing down_%d_official.json or down_%d_slim.json" % (k, k)}
        pairs[k] = (o, r)
    down = v2.downstream(pairs)
    after = _load(os.path.join(d, "official_after.json"))
    notes = []
    if after is not None and not v2.same(official, after):
        down.append("the official graph did not reproduce its own output after restore (determinism)")
    for s in seeds:
        run = _load(os.path.join(d, "slim_%d.run.json" % s), {})
        if run.get("notes"):
            notes.append("seed %d: %s" % (s, "; ".join(run["notes"])))
        if "seconds" in run:
            notes.append("seed %d: Python %.2f s" % (s, run["seconds"]))
    result = {"stage": n, "pass": v["pass"] and not down, "failures": v["failures"], "downstream": down, "rows": v["rows"]}
    _save(os.path.join(d, "verdict.json"), result)
    md = os.path.join(_REPO, "docs", "pypcg", "v2", "s%02d.md" % n)
    os.makedirs(os.path.dirname(md), exist_ok=True)
    with open(md, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(v2.markdown(n, v, down, notes))
    return {"stage": n, "pass": result["pass"], "failures": v["failures"][:20], "downstream": down, "report": md}


def phase_fingerprint(args):
    from pypcg import census, stages
    prints = {}
    for n, label, *_ in stages.STAGES:
        coll = census.component(n).get_generated_graph_output()
        prints[label] = [td.get_editor_property("data").get_editor_property("data").get_path_name()
                         for td in coll.get_editor_property("tagged_data")][:50]
    if "save" in args:
        _save(os.path.join(OUT, "_fp_%s.json" % args["save"]), prints)
        return {"saved": args["save"], "volumes": len(prints)}
    before = _load(os.path.join(OUT, "_fp_%s.json" % args["compare"]), {})
    return {"changed": sorted(k for k in prints if prints[k] != before.get(k))}


def phase_restore(args):
    from pypcg import census, stages
    state = _load(STATE)
    if state is None:
        return {"abort": "nothing to restore"}
    out = {}
    for n, label, *_ in stages.STAGES:
        pc = census.component(n)
        s = state[label]
        if pc.get_graph() is None or pc.get_graph().get_path_name() != s["graph"]:
            pc.set_graph(unreal.EditorAssetLibrary.load_asset(s["graph"].split(".")[0]))
        res = census.apply_overrides(pc, s["overrides"])
        pc.set_editor_property("regenerate_in_editor", s["regen"])
        out[label] = {"graph": pc.get_graph().get_path_name(), "skipped": res["skipped"]}
    os.remove(STATE)
    return {"restored": len(out), "problems": {k: v for k, v in out.items() if v["skipped"]}}


PHASES = {"prepare": phase_prepare, "gen": phase_gen, "read": phase_read, "verdict": phase_verdict,
          "fingerprint": phase_fingerprint, "restore": phase_restore}


def run(args):
    if "L_CitySamplePCG_Demo" not in str(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).get_current_level()):
        return {"abort": "V2 runs in /CitySamplePCG/Levels/L_CitySamplePCG_Demo"}
    return PHASES[args["phase"]](args)


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
```

- [ ] **Step 6: Write `Content/Python/pypcg_v1_editor.py`**

```python
import gc
import importlib
import json
import os
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())

# pypcg_v1_editor.py -- V1 checks with the editor's real booleans, on the runs V2 recorded (spec 3, V1).
# Args: {"stage": n}. For every Saved/Reports/v2/sNN/slim_<seed>.run.json:
#   - replay: when the inputs were recordable, run the stage again with the same params and seed and
#     require identical outputs (determinism);
#   - pypcg.checks.sNN.check(inputs or None, params, outputs, ops, official) when that module exists;
#     official is the volume's current output when it holds its official graph (after V2's restore).


def _official_outputs(n):
    from pypcg import census, stages
    from pypcg.ue import convert
    pc = census.component(n)
    g = pc.get_graph()
    if g is None or g.get_path_name().split(".")[0] != stages.official_path(n):
        return None
    out = {}
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        d = td.get_editor_property("data").get_editor_property("data")
        try:
            value = convert.from_pcg(d)
        except TypeError:
            continue
        for t in td.get_editor_property("tags"):
            if ":" not in str(t):
                out.setdefault(str(t), []).append(value)
    return out


def run(args):
    from pypcg import geo, stage_api, stages
    from pypcg.ue.ops import Ops
    n = int(args["stage"])
    official = _official_outputs(n)
    d = os.path.join(_REPO, "Saved", "Reports", "v2", "s%02d" % n)
    files = sorted(f for f in os.listdir(d) if f.endswith(".run.json")) if os.path.isdir(d) else []
    if not files:
        return {"abort": "no recorded runs under %s; run V2 first" % d}
    try:
        checks = importlib.import_module("pypcg.checks.s%02d" % n)
    except ImportError:
        checks = None
    module, ops = stages.spec(n), Ops()
    failures, replayed, deterministic = [], 0, True
    for f in files:
        rec = json.load(open(os.path.join(d, f), encoding="utf-8"))
        outputs = {pin: [(geo.from_json(v), tags) for v, tags in items] for pin, items in rec["outputs"].items()
                   if all(not v.get("truncated") for v, _ in items)}
        try:
            inputs = {pin: [(geo.from_json(v), frozenset(tags)) for v, tags in items] for pin, items in rec["inputs"].items()}
        except ValueError:
            inputs = None
        if inputs is not None:
            again, _ = stage_api.execute(module, inputs, rec["params"], ops)
            replayed += 1
            same = {p: [[geo.to_json(v), list(t)] for v, t in items] for p, items in again.items()} == \
                {p: [[v, list(t)] for v, t in items] for p, items in rec["outputs"].items()}
            if not same:
                deterministic = False
                failures.append("%s: replay with the same seed gave different outputs" % f)
        if checks is not None:
            failures += ["%s: %s" % (f, x) for x in checks.check(inputs, {k: v for k, v in rec["params"].items()
                                                                         if k != stage_api.SEED}, outputs, ops, official)]
    return {"stage": n, "runs": len(files), "replayed": replayed, "deterministic": deterministic,
            "official_seen": official is not None, "failures": failures[:40]}


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
```

- [ ] **Step 7: Write `Tools/pypcg/port_brief.py`**

```python
#!/usr/bin/env python
"""The contract of one stage's port, read from its official IR snapshot (plan Task 7, ruling N6).

    python Tools/pypcg/port_brief.py 6            -> docs/pypcg/stages/s06-brief.md (overwrites)
    python Tools/pypcg/port_brief.py all --stdout

Classifies every official node:
  param  user-parameter getters
  input  scene reads: Get_ActorData, Get_ActorDataByRef, Get_MeshTerrain, Extract_MeshTerrainPoints,
         LoadDataAsset, LoadCitySampleData, and named reroutes that only carry them
  gen    engine generation nodes kept as nodes (spec 2.4)
  drop   debug and partitioned branches (spec E7, E8): Debug_PrimitiveData, GridPartition,
         LoopSpawnActorPerData, and everything reachable only through the debug or partitioned
         side of a Branch on a Debug*/Partitioned parameter
  python everything else -- what the Python stage computes
and lists the output tags, the tags downstream stages filter on, and the demo level's overrides.
"""
import collections
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "Content", "Python"))

from pypcg import ir as pir, stages  # noqa: E402

GEN = {"Spawn_Assets", "StaticMeshSpawner", "PCGStaticMeshSpawnerSettings", "Assign_ShapeGrammarDefinition",
       "Assign_CitySampleBuildings", "Fill_Areas_WithFittingAssets_with_Corrective", "Create_Mesh_Planar",
       "Create_Mesh_Extrude", "Write_MeshTerrain", "Crosswalks", "Assign_Rule", "SetComplexBuildings",
       "AssignBuildingShape", "LoopCreatePlanarMeshActorPerData", "LoopCreateExtrudedMeshActorPerData"}
INPUT = {"Get_ActorData", "Get_ActorDataByRef", "Get_MeshTerrain", "Extract_MeshTerrainPoints",
         "PCGLoadDataAssetSettings", "LoadCitySampleData"}
ALWAYS_DROP = {"Debug_PrimitiveData", "GridPartition", "LoopSpawnActorPerData"}
PARAM = {"PCGUserParameterGetSettings", "PCGGenericUserParameterGetSettings"}
CARRIERS = {"PCGRerouteSettings", "PCGNamedRerouteDeclarationSettings", "PCGNamedRerouteUsageSettings"}
TAG_WRITERS = {"PCGAddTagSettings": "TagsToAdd"}
DEMO_OVERRIDES = os.path.join(REPO, "Tools", "pypcg", "data", "demo_overrides.json")


def kind(n):
    return pir.alias_of(n["subgraph"]) if n.get("subgraph") else n["class"]


def load(n):
    return pir.load(os.path.join(REPO, "Tools", "pypcg", "official_ir", stages.name(n) + ".json"))


def _param_of(n):
    if n["class"] == "PCGUserParameterGetSettings":
        return n.get("getter_param") or ""
    return (n.get("settings") or {}).get("PropertyPath", "")


def _is_switch(name):
    low = name.lower()
    return "debug" in low or low == "partitioned"


def edges(ir):
    """(outs, ins): outs[src] = [(dst, label, src_pin)], ins[dst] = [(src, label, src_pin)]; named
    reroute usages read their declaration through its node_ref."""
    graph = ir.get("graph", "")
    outs, ins = collections.defaultdict(list), collections.defaultdict(list)
    for n in ir["nodes"]:
        for p in n.get("inputs", []):
            for src, pin in p["edges"]:
                outs[src].append((n["name"], p["label"], pin))
                ins[n["name"]].append((src, p["label"], pin))
        if n["class"] == "PCGNamedRerouteUsageSettings":
            ref = pir.node_refs_to_names((n.get("settings") or {}).get("Declaration"), graph)
            if isinstance(ref, dict) and ref.get("node_ref"):
                outs[ref["node_ref"]].append((n["name"], "In", "Out"))
                ins[n["name"]].append((ref["node_ref"], "In", "Out"))
    return outs, ins


def classify(ir):
    nodes = {n["name"]: n for n in ir["nodes"]}
    outs, ins = edges(ir)
    cls = {}
    for name, n in nodes.items():
        k = kind(n)
        if name in pir.IO_NODES:
            cls[name] = "io"
        elif n["class"] in PARAM:
            cls[name] = "param"
        elif k in ALWAYS_DROP:
            cls[name] = "drop"
        elif k in INPUT:
            cls[name] = "input"
        elif k in GEN:
            cls[name] = "gen"
    # Debug / partition switches: a Branch whose bOutputToB comes from a Debug*/Partitioned getter.
    # Its B side is dropped; the Branch itself becomes a pass-through and is dropped too.
    dropped_side = set()
    for name, n in nodes.items():
        if n["class"] != "PCGBranchSettings":
            continue
        ctl = [s for s, label, _ in ins[name] if label == "bOutputToB"]
        if ctl and all(nodes[s]["class"] in PARAM and _is_switch(_param_of(nodes[s])) for s in ctl):
            cls[name] = "drop"
            for s in ctl:
                cls[s] = "drop"
            dropped_side.update((name, d) for d, label, pin in outs[name] if pin == "Output B")
    # Nodes all of whose inputs come from dropped nodes or dropped Branch sides are dropped.
    changed = True
    while changed:
        changed = False
        for name in nodes:
            if cls.get(name) in ("io", "param", "drop", "input"):
                continue
            src = [(s, pin) for s, label, pin in ins[name] if label not in ("Execution Dependency",)]
            if src and all(cls.get(s) == "drop" and nodes[s]["class"] != "PCGBranchSettings"
                           or (s, name) in dropped_side for s, _ in src):
                if cls.get(name) != "drop":
                    cls[name] = "drop"
                    changed = True
    # Getters that feed only dropped nodes are dropped (their parameters go: spec E7/E8).
    for name, n in nodes.items():
        if cls.get(name) == "param" and outs[name] and all(cls.get(d) == "drop" for d, _, _ in outs[name]):
            cls[name] = "drop"
    # Reroutes that only carry scene reads count as inputs; the rest is Python.
    for name, n in nodes.items():
        if name not in cls and n["class"] in CARRIERS:
            srcs = [s for s, _, _ in ins[name]]
            if srcs and all(cls.get(s) == "input" for s in srcs):
                cls[name] = "carrier"
    for name in nodes:
        cls.setdefault(name, "python")
    return cls


def _tag_of(n):
    st, ov = n.get("settings") or {}, n.get("overrides") or {}
    if n["class"] in TAG_WRITERS:
        return st.get(TAG_WRITERS[n["class"]], "")
    if kind(n) == "Write_Tag":
        return ov.get("CustomTags") or ov.get("Tag") or json.dumps(ov)
    return None


def output_tags(ir):
    """[(node feeding the output, its title, tags)]: for each node wired to the output (through
    reroutes, Gather and Merge), the tags written by the nearest AddTag / Write_Tag nodes upstream
    of it (tags travel with the data)."""
    nodes = {n["name"]: n for n in ir["nodes"]}
    _, ins = edges(ir)
    feeders, seen, todo = [], set(), [s for s, _, _ in ins[pir.OUT_NODE]]
    while todo:
        s = todo.pop()
        if s in seen:
            continue
        seen.add(s)
        if nodes[s]["class"] in CARRIERS | {"PCGGatherSettings", "PCGMergeSettings"}:
            todo += [x for x, _, _ in ins[s]]
        else:
            feeders.append(s)
    out = []
    for f in sorted(feeders):
        tags, seen, todo = [], set(), [f]
        while todo:
            x = todo.pop()
            if x in seen:
                continue
            seen.add(x)
            t = _tag_of(nodes[x])
            if t is not None:
                tags.append(t)
                continue
            todo += [s for s, label, _ in ins[x] if label != "Execution Dependency"]
        out.append((f, nodes[f].get("title", ""), sorted(set(tags)) or ["(no tag)"]))
    return out


def consumers(n_stage):
    """[(reader stage, filter)] for every downstream graph that reads this stage by actor reference."""
    from pypcg.profiles import official
    role_paths = {official.ROLES[r] for r in ROLE_OF_STAGE.get(n_stage, [])}
    found = []
    for m, *_ in stages.STAGES:
        ir = load(m)
        nodes = {n["name"]: n for n in ir["nodes"]}
        outs, _ = edges(ir)
        for n in ir["nodes"]:
            refs = (n.get("overrides") or {}).get("ActorReferences") if kind(n) == "Get_ActorDataByRef" else None
            refs = refs if isinstance(refs, list) else [refs] if refs else []
            if not role_paths.intersection(refs):
                continue
            todo, seen = [n["name"]], set()
            while todo:
                x = todo.pop()
                if x in seen:
                    continue
                seen.add(x)
                for d, label, _ in outs[x]:
                    dn = nodes[d]
                    st, ov = dn.get("settings") or {}, dn.get("overrides") or {}
                    if dn["class"] == "PCGFilterByTagSettings":
                        found.append((m, "FilterByTag %r" % st.get("SelectedTags")))
                    elif kind(dn) == "Filter_Tags":
                        found.append((m, "Filter_Tags %r" % ov.get("FilteredInputTags")))
                    elif dn["class"] in CARRIERS | {"PCGFilterByTypeSettings", "PCGGatherSettings", "PCGMergeSettings"}:
                        todo.append(d)
                    else:
                        found.append((m, "%s (%s) via %s" % (kind(dn), dn.get("title", ""), label)))
    return sorted(set(found))


# The role a stage's volume plays for the others (profiles/official.py ROLES).
ROLE_OF_STAGE = {1: ["Terrain"], 4: ["MainTower"], 5: ["CentralParkFootprint"], 6: ["Districts"], 7: ["Roads"],
                 8: ["Highways"], 9: ["Lots"], 11: ["Buildings"], 13: ["ParkingFootprint"], 14: ["Parkings"]}


def brief(n):
    ir = load(n)
    cls = classify(ir)
    nodes = {x["name"]: x for x in ir["nodes"]}
    counts = collections.Counter(cls.values())
    lines = ["# Stage %d %s -- port contract (generated by Tools/pypcg/port_brief.py)" % (n, stages.name(n)), "",
             "Official nodes: %d (excluding input/output). %s" % (len(nodes) - 2, ", ".join(
                 "%s %d" % (k, counts[k]) for k in ("param", "input", "carrier", "gen", "drop", "python"))), ""]
    lines += ["## Parameters", "", "| Name | Type | Graph default | Demo override | Kept |", "|---|---|---|---|---|"]
    demo = {}
    if os.path.exists(DEMO_OVERRIDES):
        demo = json.load(open(DEMO_OVERRIDES, encoding="utf-8")).get(stages.name(n), {})
    used = {_param_of(x).lower() for name, x in nodes.items() if cls[name] == "param"}
    for p in ir["params"]:
        kept = p["name"].lower() in used and not _is_switch(p["name"])
        lines.append("| %s | %s | %s | %s | %s |" % (p["name"], p["type"], json.dumps(p.get("value"))[:60],
                                                     json.dumps(demo.get(p["name"], "")), "yes" if kept else "dropped"))
    for title, k in (("Scene reads (keep these, by name)", "input"), ("Generation nodes (keep these, by name)", "gen")):
        lines += ["", "## " + title, "", "| Node | Kind | Title | Overrides | Fed by |", "|---|---|---|---|---|"]
        _, ins = edges(ir)
        for name in sorted(x for x in cls if cls[x] == k):
            x = nodes[name]
            ov = dict(x.get("overrides") or {})
            if "ActorReferences" in ov:
                ov["ActorReferences"] = "roles " + str(_roles(ov["ActorReferences"]))
            feeds = sorted({"%s<-%s(%s)" % (label, s, cls.get(s, "?")) for s, label, _ in ins[name]})
            lines.append("| %s | %s | %s | %s | %s |" % (name, kind(x), x.get("title", ""),
                                                         json.dumps(ov, ensure_ascii=False)[:160], ", ".join(feeds)[:200]))
    lines += ["", "## Output tags", ""] + ["- %s (%s, %s): %s" % (s, kind(nodes[s]), title, ", ".join("`%s`" % t for t in tags))
                                          for s, title, tags in output_tags(ir)]
    lines += ["", "## Downstream readers of this stage", ""] + (["- stage %d: %s" % c for c in consumers(n)] or ["- none"])
    lines += ["", "## Into Python (%d nodes; read their internals under Saved/graph_dumps or with export_graph_ir)" % counts["python"], ""]
    by_kind = collections.Counter(kind(nodes[x]) for x in cls if cls[x] == "python")
    lines += ["- %s x%d" % kv for kv in sorted(by_kind.items(), key=lambda kv: -kv[1])]
    lines += ["", "## Dropped (%d nodes)" % counts["drop"], ""]
    lines += ["- %s %s %r" % (x, kind(nodes[x]), nodes[x].get("title", "")) for x in sorted(c for c in cls if cls[c] == "drop")]
    return "\n".join(lines) + "\n", counts


def _roles(paths):
    from pypcg.profiles import official
    rev = {p: r for r, p in official.ROLES.items()}
    paths = paths if isinstance(paths, list) else [paths]
    return [rev.get(p, p) for p in paths]


def main(argv):
    which = argv[0] if argv else "all"
    wanted = [s[0] for s in stages.STAGES] if which == "all" else [int(which)]
    total = collections.Counter()
    for n in wanted:
        text, counts = brief(n)
        total.update(counts)
        if "--stdout" in argv:
            print(text)
        else:
            path = os.path.join(REPO, "docs", "pypcg", "stages", "s%02d-brief.md" % n)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            print("wrote", path, dict(counts))
    print("total", dict(total))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 8: Fill `ROLE_LABELS`** in `Content/Python/pypcg/profiles/official.py`. These were measured 2026-10-15 with `pyg_probe_plan_api2.py`:

```python
# Measured 2026-10-15 (pyg_probe_plan_api2.py): role -> actor label in L_CitySamplePCG_Demo. The town
# (a template copy) carries the same labels. Note ParkingFootprint is the LeftOverLots volume: Parkings
# reads the lot LeftOverLots set aside.
ROLE_LABELS = {"Terrain": "PCG_1_1_Terrain", "MainTower": "PCG_2_1_MainTower_Footprint",
               "CentralParkFootprint": "PCG_2_2_CentralPark_Footprint", "Districts": "PCG_3_1_1_Districts",
               "Roads": "PCG_3_1_2_Roads", "Highways": "PCG_3_1_3_Highways", "Lots": "PCG_3_1_4_Lots",
               "Buildings": "PCG_3_3_1_Buildings", "Parkings": "PCG_3_2_3_Parkings",
               "ParkingFootprint": "PCG_3_2_2_LeftOverLots", "LandmarkPark": "MainTowerPark",
               "HighwaySpline2": "HighWay_2", "HighwaySpline3": "HighWay_3"}
```

Replace the existing `# Filled in Task 8 …` comment and empty dict with this.

- [ ] **Step 9: Run the offline tests** → `test_v2.py` 12 passed, `test_port_brief.py` 3 passed. The whole suite has no failures.

- [ ] **Step 10: Prepare the demo level and check isolation in the editor.** One call each:
  1. `run_unreal_script("pypcg_compare_stage.py", {"phase": "prepare"})` → `volumes: 18`. This writes `Tools/pypcg/data/demo_overrides.json`.
  2. `{"phase": "fingerprint", "save": "before"}`.
  3. `{"phase": "gen", "stage": 6, "variant": "official"}`.
  4. Wait ~30 s, then `{"phase": "fingerprint", "compare": "before"}` → `changed` is exactly `["PCG_3_1_1_Districts"]`. Districts regenerated; Roads, Lots, Ground and LeftOverLots did not.
     - If downstream stages appear, regeneration still propagates. Stop: find what else triggers it. Candidates: the subsystem's tracking of actor references; landscape or terrain tracking. Record it as a trap before going on.
  5. `{"phase": "read", "stage": 6, "as": "official"}` → the 7 Districts tags. Counts per the spike: ArteryRoads 4, CollectorRoads 6, localRoads 57, Undividable 2, Small 3, Medium 5, Large 2.

- [ ] **Step 11: Generate the port briefs** now that the demo overrides exist:

```bash
C:/Python314/python.exe Tools/pypcg/port_brief.py all
```

Expected: 18 files under `docs/pypcg/stages/` and `total {... 'gen': 109, 'input': 69, ... 'drop': 175 ...}`.

The spec's §2.4 estimates the kept and ported node counts per stage (119 generation nodes, ~1121 into Python).
`port_brief.py` measures them instead: **109 generation, 69 scene reads, 1000 Python, 175 dropped, 30 carriers**
over the 18 graphs. Where the two disagree the brief is right, because it reads the snapshots; Task 29 Step 1
updates the spec's table to the measured numbers.

- [ ] **Step 12: Commit**

```bash
git add Content/Python/pypcg/v2.py Content/Python/pypcg/v2_thresholds.json Content/Python/pypcg/census.py Content/Python/pypcg/checks Content/Python/pypcg_compare_stage.py Content/Python/pypcg_v1_editor.py Content/Python/pypcg/profiles/official.py Tools/pypcg/port_brief.py Tools/pypcg/tests/test_v2.py Tools/pypcg/tests/test_port_brief.py Tools/pypcg/data/demo_overrides.json docs/pypcg/stages docs/pypcg-v2-thresholds.md
git commit -m "Add the V2 harness, the per-stage port briefs and the demo-level overrides" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Stage 6, Districts — the Python stage

The first real stage. Its computation is already known: the spike reproduced the official output to 0.0034 m² with the official split ratios. This task turns the spike into the stage module and its offline tests, plus the V1 checks that need real booleans.

**Files:**
- Create: `Content/Python/pypcg/stages/s06_districts.py`, `Content/Python/pypcg/checks/__init__.py`, `Content/Python/pypcg/checks/s06.py`
- Create: `Tools/pypcg/tests/test_s06_districts.py`
- Reference: `.superpowers/sdd/2026-10-13-pypcg-18-stage-town/spike-districts-report.md`, `Content/Python/spike_districts/districts_core.py`, `Saved/feishu/pcg_doc.md` lines 60–67 and 238–247, `docs/pypcg/stages/s06-brief.md`

**Interfaces — Produces:**
- `s06_districts`: `STAGE=6`, `PARAMS` (9 parameters), `INPUTS={"City": "spline", "Arteries": "spline"}`, `OUTPUTS` (7), plus `ring_of(spline)`, `flat(spline)`, `classify(area_m2, params)`, `ratio_fn(rng)`, `districts(inputs, params, ops, ratio)`, `run(inputs, params, ctx)`, and the constants `SPLIT_ITERATIONS`, `SPLIT_MIN_AREA_M2`, `SPLIT_FROM_CENTER`, `CLASSES`.
- `pypcg.checks.s06`: `check(inputs, params, outputs, ops, official=None)`, `oracle_ratio(collectors)`.

- [ ] **Step 1: Write the failing tests** `Tools/pypcg/tests/test_s06_districts.py`:

```python
import json
import os
import random

import pytest

from fakes import FakeOps
from pypcg import geo, stage_api
from pypcg.geo import Spline
from pypcg.stages import s06_districts as S

REPO = stage_api.REPO
CITY = Spline([(-100000.0, -50000.0, 500.0), (100000.0, -50000.0, 500.0), (100000.0, 50000.0, 500.0),
               (-100000.0, 50000.0, 500.0)], closed=True)                       # 2000 x 1000 m, z flattened
ARTERY = Spline([(0.0, -60000.0, 0.0), (0.0, 60000.0, 0.0)])                     # straight, across the middle
PARAMS = dict(stage_api.defaults(S))
PARAMS.pop(stage_api.SEED)
PARAMS.update(Dividable_district_Limit=100000.0, SmallMediumThreshold=300000.0, MediumLargeThreshold=400000.0)


def inputs(city=CITY, arteries=(ARTERY,)):
    return {"City": [(city, frozenset({"City"}))] if city else [], "Arteries": [(a, frozenset()) for a in arteries]}


def half(ring):
    return 0.5


def areas(out, tag):
    return [abs(geo.signed_area(p.outer)) / 1e4 for p, _ in out[tag]]


def test_contract_matches_the_official_graph():
    off = json.load(open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_3_1_1_Districts.json"), encoding="utf-8"))
    defaults = {p["name"]: p["value"] for p in off["params"]}
    assert set(S.PARAMS) == {n for n in defaults if not n.startswith("Debug") and n != "SubDistrictSeed"}
    assert all(S.PARAMS[n].default == defaults[n] for n in S.PARAMS)
    assert set(S.OUTPUTS) == {"ArteryRoads", "CollectorRoads", "localRoads", "UndividableDistricts", "SmallDistricts",
                              "MediumDistricts", "LargeDistricts"}


def test_cut_split_classify_and_conserve_area():
    out = S.districts(inputs(), PARAMS, FakeOps(), half)
    assert sorted(areas(out, "LargeDistricts")) == pytest.approx([500000.0] * 4)          # 2 districts x 2 halves
    assert not out["UndividableDistricts"] and not out["SmallDistricts"] and not out["MediumDistricts"]
    total = sum(sum(areas(out, t)) for t in S.OUTPUTS if t.endswith("Districts"))
    assert total == pytest.approx(2000000.0, rel=1e-9)
    assert len(out["CollectorRoads"]) == 2
    assert len(out["ArteryRoads"]) == 2                                                   # outline + 1 clipped artery
    outline = out["ArteryRoads"][0][0]
    assert outline.closed and all(p[2] == 0.0 for p in outline.points)


def test_classes_follow_the_thresholds():
    p = dict(PARAMS, Dividable_district_Limit=600000.0)
    out = S.districts(inputs(), p, FakeOps(), half)
    assert len(out["UndividableDistricts"]) == 4 and not out["localRoads"]               # nothing is gridded
    p = dict(PARAMS, Dividable_district_Limit=100000.0, SmallMediumThreshold=600000.0)
    assert len(S.districts(inputs(), p, FakeOps(), half)["SmallDistricts"]) == 4


def test_grid_lines_stay_inside_their_district():
    out = S.districts(inputs(), PARAMS, FakeOps(), half)
    rings = [p.outer for p, _ in out["LargeDistricts"]]
    assert out["localRoads"]
    for line, tags in out["localRoads"]:
        mid = [(a + b) / 2 for a, b in zip(line.points[0][:2], line.points[-1][:2])]
        assert any(geo.inside(mid, r) for r in rings) and tags == ["localRoads"]


def test_empty_inputs_give_empty_outputs():
    out = S.districts(inputs(city=None), PARAMS, FakeOps(), half)
    assert all(out[pin] == [] for pin in S.OUTPUTS)
    out = S.districts(inputs(arteries=()), PARAMS, FakeOps(), half)            # no arteries: the city is one district
    assert len(out["CollectorRoads"]) == 1 and sum(len(out[t]) for t in S.OUTPUTS if t.endswith("Districts")) == 2


class SliverOps(FakeOps):
    def cut_with_paths(self, ring, paths):
        return super().cut_with_paths(ring, paths) + [[(0.0, 0.0), (10.0, 0.0), (0.0, 10.0)]]


def test_cut_keeps_only_real_pieces():
    out = S.districts(inputs(), PARAMS, SliverOps(), half)
    assert sum(len(out[t]) for t in S.OUTPUTS if t.endswith("Districts")) == 4


def test_seeded_runs_repeat_and_differ():
    def collectors(seed):
        out, _ = stage_api.execute(S, inputs(), dict(stage_api.defaults(S), Seed=seed, **{k: v for k, v in PARAMS.items()}), FakeOps())
        return [l.points for l, _ in out["CollectorRoads"]]
    assert collectors(5) == collectors(5) and collectors(5) != collectors(6)


def test_split_ratios_stay_in_the_official_range():
    draw = S.ratio_fn(random.Random("x"))
    vals = [draw(None) for _ in range(2000)]
    assert 0.3 <= min(vals) and max(vals) <= 0.7 and min(vals) < 0.31 and max(vals) > 0.69


def test_v1_checks_pass_on_a_real_run_and_catch_a_wrong_class():
    from pypcg.checks import s06 as C
    out = S.districts(inputs(), PARAMS, FakeOps(), half)
    assert C.check(inputs(), PARAMS, out, FakeOps()) == []
    wrong = dict(out, SmallDistricts=out["LargeDistricts"][:1], LargeDistricts=out["LargeDistricts"][1:])
    assert any("its size says LargeDistricts" in x for x in C.check(inputs(), PARAMS, wrong, FakeOps()))
    lost = dict(out, LargeDistricts=out["LargeDistricts"][1:])
    assert any("add up" in x for x in C.check(inputs(), PARAMS, lost, FakeOps()))


def test_oracle_recovers_the_split_ratios():
    from pypcg.checks import s06 as C
    official = S.districts(inputs(), PARAMS, FakeOps(), lambda ring: 0.37)
    off = {t: [v for v, _ in official[t]] for t in S.OUTPUTS}
    mine = S.districts(inputs(), PARAMS, FakeOps(), half)
    assert C.check(inputs(), PARAMS, mine, FakeOps(), off) == []          # the oracle replays with 0.37
    off["CollectorRoads"] = off["CollectorRoads"][:1]
    assert any(x.startswith("oracle") for x in C.check(inputs(), PARAMS, mine, FakeOps(), off))
```

- [ ] **Step 2: Write `Content/Python/pypcg/stages/s06_districts.py`**

```python
"""Stage 6 -- Districts (PCG_3_1_1_Districts, 街区骨架).

Cuts the City outline (actor tag City) with the arteries (tag Arteries) into districts, splits each
district once near its middle (the collector roads), sorts the pieces by area into Undividable /
Small / Medium / Large districts, and lays a road grid over every dividable district (the local
roads). Replaces the official 75-node graph, about 560 nodes counting the primitives it calls. Ported
from the 2026-10-15 spike, which matched the official output to 0.0034 m2 when given the official
split ratios (spike report, table 1)."""
from pypcg import geo
from pypcg.geo import Polygon, Spline
from pypcg.stage_api import Param

STAGE = 6
DOC = """Districts (街区骨架): cuts the City outline (actor tag City) with the arteries (tag Arteries),
splits each district once, sorts the pieces by area and grids the dividable ones. Areas are in m2,
grid spacings in cm. Outputs ArteryRoads, CollectorRoads and localRoads (splines) and
UndividableDistricts, SmallDistricts, MediumDistricts and LargeDistricts (areas)."""
RANDOM = True
PARAMS = {
    "Dividable_district_Limit": Param(150000.0, "Pieces larger than this (m2) get a road grid", category="Sizes"),
    "SmallMediumThreshold": Param(200000.0, "Small / Medium boundary (m2)", category="Sizes"),
    "MediumLargeThreshold": Param(500000.0, "Medium / Large boundary (m2)", category="Sizes"),
    "SmallGridWidth": Param(6000.0, "Small districts: spacing of the roads across the long edge (cm)", category="Grid"),
    "SmallGridLength": Param(3000.0, "Small districts: spacing of the roads along the long edge (cm)", category="Grid"),
    "MediumGridWidth": Param(12000.0, "Medium districts: spacing across the long edge (cm)", category="Grid"),
    "MediumGridLength": Param(6000.0, "Medium districts: spacing along the long edge (cm)", category="Grid"),
    "LargeGridWidth": Param(24000.0, "Large districts: spacing across the long edge (cm)", category="Grid"),
    "LargeGridLength": Param(12000.0, "Large districts: spacing along the long edge (cm)", category="Grid"),
}
INPUTS = {"City": "spline", "Arteries": "spline"}
OUTPUTS = ("ArteryRoads", "CollectorRoads", "localRoads", "UndividableDistricts", "SmallDistricts",
           "MediumDistricts", "LargeDistricts")

# Fixed in the official graph (Sub_districts overrides; Filter_Areas_BySize operators are Greater).
SPLIT_ITERATIONS = 1
SPLIT_MIN_AREA_M2 = 1000.0
SPLIT_FROM_CENTER = 0.2        # MaxSplitDistancFromCenter, clamped to [0.05, 0.45]: ratios in [0.3, 0.7]
CLASSES = (("SmallDistricts", "Small"), ("MediumDistricts", "Medium"), ("LargeDistricts", "Large"))


def ring_of(spline):
    """The spline's polyline in the XY plane (the official graph sets $Position.Z to 0)."""
    return geo.drop_closing(geo.xy(spline.polyline or spline.points))


def flat(spline):
    tangents = [((a[0], a[1], 0.0), (b[0], b[1], 0.0)) for a, b in spline.tangents] if spline.tangents else None
    return Spline([(p[0], p[1], 0.0) for p in spline.points], spline.closed, spline.linear, tangents)


def _line(seg):
    return Spline([(x, y, 0.0) for x, y in seg])


def ratio_fn(rng):
    c = min(max(SPLIT_FROM_CENTER, 0.05), 0.45)
    return lambda ring: 0.5 - c + 2.0 * c * rng.random()


def classify(area_m2, params):
    if not area_m2 > params["Dividable_district_Limit"]:
        return "UndividableDistricts"
    if not area_m2 > params["SmallMediumThreshold"]:
        return "SmallDistricts"
    if not area_m2 > params["MediumLargeThreshold"]:
        return "MediumDistricts"
    return "LargeDistricts"


def districts(inputs, params, ops, ratio):
    """Everything run() does, with the split ratios supplied by ratio(ring) (run() draws them; the V1
    oracle check in pypcg/checks/s06.py supplies the official ones)."""
    out = {pin: [] for pin in OUTPUTS}
    cities = [v for v, _ in inputs["City"] if isinstance(v, Spline) and v.closed]
    arteries = [ring_of(v) for v, _ in inputs["Arteries"] if isinstance(v, Spline) and not v.closed]
    for city in cities:
        ring = geo.ccw(ring_of(city))
        out["ArteryRoads"].append((flat(city), ["ArteryRoads"]))                  # the outline itself
        for path in arteries:
            out["ArteryRoads"] += [(_line(seg), ["ArteryRoads"]) for seg in geo.clip_path(path, ring)]
        pieces = ops.cut_with_paths(ring, arteries) if arteries else [ring]
        pieces = [r for r in pieces if abs(geo.signed_area(r)) >= geo.SLIVER_CM2]
        areas, collectors = [], []
        for d in pieces:
            geo.recursive_split(d, ops, SPLIT_ITERATIONS, SPLIT_MIN_AREA_M2 * 1e4, ratio, areas, collectors)
        out["CollectorRoads"] += [(_line(seg), ["CollectorRoads"]) for seg in collectors]
        for r in areas:
            tag = classify(abs(geo.signed_area(r)) / 1e4, params)
            out[tag].append((Polygon(r), [tag]))
    for tag, size in CLASSES:
        for poly, _ in out[tag]:
            for _axis, seg in geo.grid_lines(poly.outer, params[size + "GridWidth"], params[size + "GridLength"]):
                out["localRoads"].append((_line(seg), ["localRoads"]))
    return out


def run(inputs, params, ctx):
    return districts(inputs, params, ctx.ops, ratio_fn(ctx.rng))
```

- [ ] **Step 3: Write `Content/Python/pypcg/checks/__init__.py`**

```python
"""V1 checks that need the editor's booleans or a recorded run: pypcg/checks/sNN.py defines
check(inputs, params, outputs, ops, official) -> [failure]. inputs is None when the run's inputs
cannot be recorded (a terrain surface); outputs are pypcg.geo values rebuilt from the run record;
official is {tag: [pypcg.geo values]} of the volume's current official output, or None."""
```

- [ ] **Step 4: Write `Content/Python/pypcg/checks/s06.py`**

```python
"""V1 checks of stage 6, Districts, with the editor's booleans (spec 3, V1).

check() verifies four invariants on every recorded run:
  - each area sits in the class its size says;
  - the areas add up to the City (the cut and the split lose nothing);
  - no two areas overlap;
  - every local road lies in a gridded district.
When the volume holds its official output, it also runs the oracle: it recovers the official split
ratios from the official collector roads and requires the Python cut, split, classes and grids to
match the official areas to 0.05 m2 and the official road lengths to 0.01 % (spike report, table 1)."""
import math

from pypcg import geo
from pypcg.stages import s06_districts as S

AREA_TAGS = ("UndividableDistricts", "SmallDistricts", "MediumDistricts", "LargeDistricts")
ROAD_TAGS = ("ArteryRoads", "CollectorRoads", "localRoads")


def _rings(outputs):
    return [(t, p.outer) for t in AREA_TAGS for p, _ in outputs.get(t, [])]


def _mid(spline):
    pts = spline.polyline or spline.points
    a, b = pts[0], pts[-1]
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def _length(spline):
    pts = list(spline.polyline or spline.points)
    return geo.path_length(pts + pts[:1] if spline.closed else pts)


def oracle_ratio(collectors):
    """ratio(ring) recovered from the official collector roads: the official split line of a ring is
    the collector whose midpoint lies inside it (spike: 6 of 6 recovered)."""
    def ratio(ring):
        for c in collectors:
            m = _mid(c)
            if geo.inside(m, ring):
                o, X, Y, u0, u1, w0, w1 = geo.split_frame(ring)
                u = (m[0] - o[0]) * X[0] + (m[1] - o[1]) * X[1]
                return (u1 - u) / (u1 - u0)
        return 0.5
    return ratio


def check(inputs, params, outputs, ops, official=None):
    f = []
    rings = _rings(outputs)
    for t, r in rings:
        want = S.classify(abs(geo.signed_area(r)) / 1e4, params)
        if want != t:
            f.append("an area of %.0f m2 is %s, its size says %s" % (abs(geo.signed_area(r)) / 1e4, t, want))
    if inputs:
        city = sum(abs(geo.signed_area(geo.ccw(S.ring_of(v)))) for v, _ in inputs["City"] if v.closed)
        total = sum(abs(geo.signed_area(r)) for _, r in rings)
        if city and abs(total - city) > 1e-4 * city:
            f.append("areas add up to %.6g m2, the City is %.6g m2" % (total / 1e4, city / 1e4))
    for i in range(len(rings)):
        for j in range(i + 1, len(rings)):
            overlap = sum(geo.area_m2(p) for p in ops.intersection([rings[i][1]], [rings[j][1]]))
            if overlap > 1.0:
                f.append("areas %d and %d overlap by %.1f m2" % (i, j, overlap))
    gridded = [r for t, r in rings if t != "UndividableDistricts"]
    for line, _ in outputs.get("localRoads", []):
        if not any(geo.inside(_mid(line), r) for r in gridded):
            f.append("a local road at %s lies in no gridded district" % (tuple(round(c) for c in _mid(line)),))
            break
    if inputs and official and official.get("CollectorRoads"):
        f += _oracle(inputs, params, ops, official)
    return f


def _oracle(inputs, params, ops, official):
    f = []
    again = S.districts(inputs, params, ops, oracle_ratio(official["CollectorRoads"]))
    for t in AREA_TAGS:
        mine = sorted(abs(geo.signed_area(p.outer)) / 1e4 for p, _ in again[t])
        theirs = sorted(geo.area_m2(p) for p in official.get(t, []))
        if len(mine) != len(theirs) or any(abs(a - b) > 0.05 for a, b in zip(mine, theirs)):
            f.append("oracle %s: areas %s vs official %s" % (t, [round(a, 1) for a in mine], [round(b, 1) for b in theirs]))
    for t in ROAD_TAGS:
        mine = sum(_length(s) for s, _ in again[t])
        theirs = sum(_length(s) for s in official.get(t, []))
        if len(again[t]) != len(official.get(t, [])) or (theirs and abs(mine - theirs) > 1e-4 * theirs):
            f.append("oracle %s: %d roads %.1f m vs official %d roads %.1f m"
                     % (t, len(again[t]), mine / 100, len(official.get(t, [])), theirs / 100))
    return f
```

- [ ] **Step 5: Run the tests** → `C:/Python314/python.exe -m pytest Tools/pypcg/tests/test_s06_districts.py -q` → `10 passed`. Whole suite → no regressions.

- [ ] **Step 6: Commit**

```bash
git add Content/Python/pypcg/stages/s06_districts.py Content/Python/pypcg/checks Tools/pypcg/tests/test_s06_districts.py
git commit -m "Port stage 6, Districts, into Python with its offline and V1 checks" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## The port protocol

Tasks 10–26 are the remaining stage ports. Each one follows the same six steps and ends with the same evidence. The steps are written once here; each task gives its contract, its tests and its own traps.

**Step A — the algorithm note.** From `docs/pypcg/stages/sNN-brief.md` (the contract), the official IR snapshot and the primitives' internals, write `docs/pypcg/stages/sNN.md`:
1. the contract table from the brief (inputs, outputs, kept parameters, kept generation nodes, tags);
2. the computation as numbered steps, each naming **the official nodes it replaces** and, where the work is inside a primitive, the primitive and its own node names;
3. the deliberate differences (new random numbers, merged parameters, anything dropped);
4. what could not be reproduced, and what was done instead.
The note is committed with the code. **The first V2 run decides whether the note was right:** if it fails, fix the note before the code.

**Step B — tests first.** Offline tests with real assertions, in this order of importance:
1. `test_contract_<pin>` — for every input pin a scene read exists in the graph (the brief's "Scene
   reads" tables) and the Python stage reads it by name; for every output pin the graph wires it;
   parameters and their defaults equal the official ones unless the stage's note says otherwise;
2. `test_empty_inputs_*` (Review Focus 1) — every input pin empty: no exception, every output pin empty.
   For an input whose empty form is a zero-length list, pass `[]`; for one that is a `Spline` or
   `Polygon`, the same test uses an empty list too, so the stage must tolerate a missing input, not just
   an empty value;
3. `test_<task invariant>_*` — the invariants listed in the task;
4. `test_seeded_runs_repeat_and_differ` — the same seed twice gives identical output, a different seed
   differs (skipped for `RANDOM = False` stages).
**Step C — the stage module.** Pure: `ctx.ops` for booleans, `ctx.rng` for randomness, no `unreal`. Shared helpers go to `pypcg.geo` with their own tests, never copied into two stages.

**Step D — the graph description** `pypcg/graphs/sNN_*.py`: `keep()` each listed scene read and each generation node, wire every Python input pin (the builder raises on an unwired one), wire every Python output to the generation node that consumes it or to the output. Parameters that only kept nodes read come from `dsl.official_param`. Then `run_unreal_script("pypcg_build_slim.py", {"stages": [n]})` → `diffs: 0`.

**Step E — V2 and V1.** One call each, in this order:

```
prepare                                    (once per editor session)
gen {stage: n, variant: "official"}   ->   wait -> read {stage: n, as: "official"}
for seed in V2_SEEDS:
    gen {stage: n, variant: "slim", seed: seed} -> read {stage: n, as: "slim_<seed>"}
for k in DOWNSTREAM[n]:
    gen {stage: k, variant: "official"}          (its graph is official; it now reads the slim n)
    read {stage: k, as: "down_<k>_slim", into: n}
gen {stage: n, variant: "official"}      ->   read {stage: n, as: "official_after"}
for k in DOWNSTREAM[n]:
    gen {stage: k, variant: "official"}  ->   read {stage: k, as: "down_<k>_official", into: n}
verdict {stage: n}
run_unreal_script("pypcg_v1_editor.py", {"stage": n})
```

`read` takes an optional `into` (the stage whose folder to write to) so downstream records land next to the stage they verify. After the last generation the volumes hold their official outputs again.

Result to record in the ledger: `pass`, `failures` (at most 20), `downstream` and the V1 `failures`, `replayed`, `deterministic`. A V2 failure is diagnosed in this order:
1. **the port** — check the note's step against the official nodes once more;
2. **the parameter copy** — `phase_gen`'s `overrides.skipped` lists names the slim graph does not have. A skipped name that mattered is a missing parameter, not a threshold problem;
3. **the randomness** — only then widen a threshold, and only in `v2_thresholds.json` with a row in `docs/pypcg-v2-thresholds.md` giving the old value, the new value and the reason.

**Step F — timing and commit.** If the run record's `seconds` is over 60, apply spec §4.3: move that one bulk operation back to a native node, record it in the stage's note and the ledger. Then one commit per stage: the stage module, its graph, its checks, its tests, the note, and any threshold change.

---

### Task 9: Stage 6, Districts — the slim graph, V2 and V1

**Files:**
- Create: `Content/Python/pypcg/graphs/s06_districts.py`
- Create (generated, committed): `Content/PyPCG/Slim/PCG_3_1_1_Districts.uasset`, `docs/pypcg/v2/s06.md`
- Modify: `docs/pypcg-v2-thresholds.md` and `Content/Python/pypcg/v2_thresholds.json` if a threshold moves

**Interfaces — Produces:** `graphs.s06_districts.build()`; the ledger's V2 result for stage 6.

- [ ] **Step 1: Write `Content/Python/pypcg/graphs/s06_districts.py`**

```python
"""Slim graph of stage 6, Districts (spec 2.4): the City and Arteries actor reads feed the Python node;
its seven outputs go to the graph output, where Roads, Lots, Ground and LeftOverLots read them by tag."""
from pypcg import dsl
from pypcg.stages import s06_districts as S


def build():
    g = dsl.SlimGraph(S)
    g.connect(g.keep("Subgraph_0"), g.py, "City")          # Get City Shape Spline (actor tag City)
    g.connect(g.keep("Subgraph_1"), g.py, "Arteries")      # Get Arteries (actor tag Arteries)
    for pin in S.OUTPUTS:
        g.out(g.py[pin])
    return g
```

14 nodes: 10 getters, 2 scene reads, the Python node, and the graph's input/output nodes. The official graph has 75.

- [ ] **Step 2: Build it.** `run_unreal_script("pypcg_build_slim.py", {"stages": [6]})` → `diffs: 0`, `nodes: 14`.

- [ ] **Step 3: Run the port protocol's Step E for stage 6.** `stages.DOWNSTREAM[6]` is `[7, 9, 10, 13]`, so the sequence has 4 + 10 + 8 + 2 + 8 = 32 calls; Roads takes minutes to generate, so pause between `gen` and `read` there.
  - Expected V2: the seven tags at the demo-override parameter values (from `Tools/pypcg/data/demo_overrides.json` for `PCG_3_1_1_Districts`). Official counts, per the spike: ArteryRoads 4, CollectorRoads 6, localRoads 57, Undividable 2, Small 3, Medium 5, Large 2.
  - Every tag here has fewer than 5 items except localRoads (57), Medium (5) and Small (3), so Most tags compare length and point counts only (ruling N10).
  - Expected V1 (`pypcg_v1_editor.py {"stage": 6}`): `failures: []`, `replayed: 5`, `deterministic: true`, and the oracle lines absent from `failures` — which is the real correctness evidence for this stage: with the official ratios the Python geography matches the official areas to 0.05 m².
  - Expected downstream: stages 7, 9, 10 and 13 still generate with instances.

- [ ] **Step 4: Read every failure honestly.** A `localRoads` length inside ±10 % counts as a port that agrees; a failure of `oracle` does not — that one is a bug in the port, because it replays with the official ratios.

- [ ] **Step 5: Commit**

```bash
git add Content/Python/pypcg/graphs/s06_districts.py Content/PyPCG/Slim/PCG_3_1_1_Districts.uasset docs/pypcg/v2/s06.md docs/pypcg-v2-thresholds.md Content/Python/pypcg/v2_thresholds.json
git commit -m "Build the slim Districts graph and verify it against the official graph in the demo level" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Stage 7, Roads

The hardest port: 210 official nodes, 136 of them Python, six Shape Grammar assignments to keep, two terrain writes (road flatten, intersection flatten) and crosswalks. It needs several Python nodes, because the terrain writes sit in the middle of the chain.

**Files:** stage `Content/Python/pypcg/stages/s07_roads.py` (+ `pypcg/geo/roads.py` when a helper earns its keep), graph `Content/Python/pypcg/graphs/s07_roads.py`, checks `Content/Python/pypcg/checks/s07.py`, tests `Tools/pypcg/tests/test_s07_roads.py`, note `docs/pypcg/stages/s07.md`. Then the port protocol's Steps D–F.

**Contract** (`docs/pypcg/stages/s07-brief.md`, Feishu doc lines 70–79 and 248–258):

| | |
|---|---|
| Inputs | `Districts` → ArteryRoads / CollectorRoads / localRoads *(the outline in ArteryRoads is an area, not a line: use `Polygon` where it arrives as one)*; `MainTower` (the landmark outline to cut roads with); `CentralParkFootprint`; `Terrain` (road projection surface); `MeshTerrain` (Final) |
| Outputs | `RoadFootprints` (the road occupation areas, each carrying `local_Width` / `collector_width` / `Artery_width`), `ModifiedTerrain` (the flattened terrain for the next stage) |
| Parameters | `local_Width` 1900, `collector_width` 2600, `Artery_width` 3400, `Road_Profile` (SoftObject, official `SGD_Road_Demo`, demo `SGD_Road_City_HighRes`), `simpleRoads` False, `Crosswalks` (demo True). `Partitioned` / `PartitionGridSize` go |
| Generation to keep | `Subgraph_8`, `Subgraph_9`, `Subgraph_10` (grammar: three road classes inside the landmark cut), `Subgraph_41`, `Subgraph_43`, `Subgraph_51` (grammar: the same three outside it, no lines), `Subgraph_26` (Spawn Road), `Subgraph_23` (spray paint decals), `Subgraph_39` (crosswalk white), `Subgraph_7` (Crosswalks), `Subgraph_46` (Write Terrain: road flatten), `Subgraph_37` (Write Terrain: intersection flatten) |
| Python nodes | two or three: roads → grammar points and footprints; road-zone terrain flatten; intersection-zone flatten |

**Algorithm (from the doc, to be checked against the IR in Step A):** extend each road class's line ends by half its width; make each class's outline; solve the overlaps recursively; expand the intersections into cutters; cut the road lines with them and drop the sections shorter than the module limit; publish the full footprints (union of the class outlines) with a width attribute each; distribute grammar points along the sections (inside and outside the landmark); flatten the terrain under the road zone, then under the intersection zone.

**Invariants to test offline:**
- every footprint is within the City + 200 m and its area is between `width × length` and `1.5 ×` that for each road line;
- the footprints of different classes do not overlap by more than a module;
- the number of grammar points per class is proportional to that class's total length within ±10 %;
- `simpleRoads = True` produces one class only;
- empty inputs → empty outputs, and a City with no roads at all produces no footprints and no terrain write.

- [ ] **Step A–F**: the port protocol above. `DOWNSTREAM[7]` is `[8, 9, 10, 13, 16, 18]`: 6 downstream stages, so budget the calls.

---

### Task 11: Stage 8, Highways

**Files:** `pypcg/stages/s08_highways.py`, `pypcg/graphs/s08_highways.py`, `pypcg/checks/s08.py`, `Tools/pypcg/tests/test_s08_highways.py`, `docs/pypcg/stages/s08.md`.

**Contract** (brief; Feishu doc lines 80–87 and 259–266):

| | |
|---|---|
| Inputs | `HighwaySpline2` + `HighwaySpline3` (the two highway spline actors), `Roads` (RoadFootprints as the pillar projection target), `MeshTerrain` (Final) |
| Outputs | `Highway` (the highway footprint areas) |
| Parameters | `Highway_Width` (2000 saved; the demo carries its own) |
| Generation to keep | `Assign_HighwayShapeGrammar` (grammar, footprint + points), `Subgraph_4` (Spawn Highway Support Assets) |
| Python | flatten the highway splines to Z = 0, resample at 40 m, project onto the final terrain, build the footprint from the width, place the pillars on the concrete footprints and keep the grounded ones |

**Invariants:** two straight parallel highways on flat ground → two footprints whose width equals `Highway_Width` within 1 cm and whose area equals `width × length` within 1 %; pillar points (if used) sit on Roads' footprints; empty inputs → empty outputs; `Highway` present in every run.

---

### Task 12: Asset assignment in Python (`Assign_Assets`)

Stages 10, 13, 14, 16, 17 and 18 all use the `Assign_Assets` primitive (4, 11, 4, 7, 1, 2 calls). This task ports it once, as a shared helper.

**Files:** `Content/Python/pypcg/geo/assets.py` (pure choice), `Content/Python/pypcg/ue/assets.py` (loading), `Tools/pypcg/tests/test_assets.py`.

**Interfaces — Produces:**
- `geo.assets.choose(n, assets, rng) -> [index per point]` from `Assets` (or a `UseMeshAttribute`), honouring `RandomPositionRange`, `RandomRotationRange`, `RandomScaleRange` and `UniformScale`.
- `ue.assets.load(paths) -> [{"path", "points", "bounds", "size"}]`: a `PCGDataAsset` expansions into its points (with their `Mesh`), a `StaticMesh` into one point with its bounds. Cached per call.
- `geo.assets.expand(targets, table, indices, params) -> Points` — the target points carrying `Asset` (= a mesh path) and `$Bounds`/`$Extents` from the asset, plus the assembly's own points copied onto them.

**Verified against the official primitive** in the editor: rebuild one `Assign_Assets` call from a recorded run's inputs with one target point, no random ranges, and compare the official output (points, `Asset` attribute, `$Bounds`) with the Python one — they must be equal exactly. Add that comparison to `pypcg_v1_editor.py` as a phase `{"assign": {"stage": n}}` for the first stage that uses it (Task 15).

---

### Task 13: Stages 4 and 5, the landmark footprints

The two smallest stages, and the cheapest place to settle "a Python stage that publishes a shape from the volume's own transform".

**Files:** `pypcg/stages/s04_main_tower_footprint.py`, `pypcg/stages/s05_central_park_footprint.py`, `pypcg/graphs/s04_*.py`, `pypcg/graphs/s05_*.py`, `Tools/pypcg/tests/test_s04_s05.py`, notes.

**Contract** (briefs; Feishu doc lines 46–57 and 224–236):

| | |
|---|---|
| 4 Inputs | none (the volume's own transform arrives as a point on the `Volume` pin, `Mode = GetSinglePoint`) |
| 4 Outputs | `Footprint` (the closed hexagon spline) |
| 4 Parameters | `RectWidth` 16000, `RectLength` 16000 (`NewProperty` goes: no getter reads it) |
| 5 Inputs | none (same) |
| 5 Outputs | `Footprint` (the rectangle) |
| 5 Parameters | `RectWidth` 16000, `RectLength` 16000 (new: the official graph fixes `Width` 100000 / `Length` 20000 inside the node, so the town needs them exposed) |
| Both | no generation nodes; the official debug meshes go |

**Algorithm.** Hexagon: `geo.ngon(center, RectWidth/2, 6, start_deg=-60, step_deg=-60)` matches the demo's vertices to 0.1 cm (`pyg_probe_plan_api3.py`, 2026-10-15) — the vertices are `(4000, -6928.2) …`, i.e. `R = RectWidth/2` with `y = R·√3/2`. Rectangle: `geo.rect(center, RectWidth/2, RectLength/2, yaw)` matched the demo's park corners to < 0.5 cm. Both take the yaw and location from `inputs["Volume"][0][0].loc` / `.rot[1]` and put Z at 0 (the official graph sets `$Position.Z` to 0 in stage 5 and the tower sits at Z 0).

**Invariants:** the hexagon's six vertices and the rectangle's four corners equal the official ones (the two measured cases are the test fixtures); the area matches the analytic value to 1e-6; a rotated volume rotates the shape and a moved volume moves it; the output spline is closed, linear, in the official vertex order (`ngon`'s default) and its signed area is negative (the official order, traps.md 41).

---

### Task 14: Stages 2 and 3, the background

**Files:** `pypcg/stages/s02_bg_buildings.py`, `pypcg/stages/s03_bg_mountains.py`, graphs, `Tools/pypcg/tests/test_s02_s03.py`, notes.

**Contract** (briefs; Feishu doc lines 32–43 and 209–223):

| | |
|---|---|
| 2 Inputs | none |
| 2 Outputs | `Points` (background building points) |
| 2 Parameters | new, exposed for the town: `OuterSize` 2500000, `CenterSize` 300000, `PointsPerSquaredMeter` 1e-6, `KeepRatio` 0.641598, `MaxYaw` 180 |
| 2 Generation | `SpawnAssets` (3 SM_bgcity meshes, `PositionOffset.Z` 13200, `ScaleOffset` (100,1,1)) |
| 3 Inputs | `Cliffs` (the `VistaCliffs_PCG` data asset, kept as the `PCGLoadDataAssetSettings` node) |
| 3 Outputs | `Points` (the stamped cliff points) |
| 3 Parameters | new: `AnchorZ` 0, `AnchorScaleXY` 1.75, `AnchorScaleZ` 0.5, `ZMin` -100000, `ZMax` 100000 |
| 3 Generation | `StaticMeshSpawner_0` (Mesh attribute selector) |
| Both | the official debug meshes go |

**Algorithm.** Stage 2: a ring between a 25 km square and a 4.1176984376 km square (the odd saved value comes from a `CenterSize` constant that the official graph connects to both `Width` and `Length`), `round(ring area × density)` uniform points, random yaw in ±`MaxYaw`, then a random cull to `KeepRatio`. Stage 3: `CopyPoints`'s transform composition — source point × (target translation + target scale) → translation `(0,0,-50000)`, scale `(1.75,1.75,0.5)`, roll and pitch set to 0, Z clamped to ±100000 — keeping the `Mesh` attribute so the spawner works.

**Invariants:** stage 2's point count equals `round(ring area × density × KeepRatio)` within 1 %; every point is outside the centre square and inside the outer one; the yaw is within ±`MaxYaw`; stage 3's point count equals the asset's point count and each point's Z is the source Z × `AnchorScaleZ` + `AnchorZ`, clamped; the `Mesh` attribute survives the round trip.

---

### Task 15: Stage 17, CityEdge — the first `Assign_Assets` user

**Files:** `pypcg/stages/s17_city_edge.py`, graph, `pypcg/checks/s17.py`, `Tools/pypcg/tests/test_s17_city_edge.py`, note.

**Contract** (brief; Feishu doc lines 168–173 and 356–363):

| | |
|---|---|
| Inputs | `MeshTerrain` (Final) → `Extract_MeshTerrainPoints` (kept as the `Subgraph_10` node) |
| Outputs | `Docks` (the pier/warehouse points) |
| Parameters | new: `SeaLevel` -72.639648, `DockRatio` 0.5152000188827515 |
| Generation | `Subgraph_0` (Spawn Pier & Warehouse Assemblies) |
| Python | keep terrain points above `SeaLevel` (their Z, i.e. `loc[2]`), take the 2D convex hull, build a closed linear ring from it, take its control points, `choose(n, DockRatio, rng)`, zero roll and pitch, assign the five official assets (`Dock_A/B_PCG`, `Warehouse_A/B/C_PCG`) with `PositionOffset.Y` -492.541261 |

**Invariants:** the hull is convex and contains every kept point; the dock count is `round(n × ratio)`; every dock has an `Asset`; the docks are on the hull's vertices; with no terrain points above sea level the output is empty. **This task also adds the `assign` phase to `pypcg_v1_editor.py`** that compares the Python assignment with the official primitive exactly (Task 12).

---

### Task 16: Stage 9, Lots

183 official nodes, 135 in Python: six area booleans, three size classes with their own lot-size filters, courtyards, the large-lot inner road grid, and eleven output tags.

**Files:** `pypcg/stages/s09_lots.py`, graph, `pypcg/checks/s09.py`, `Tools/pypcg/tests/test_s09_lots.py`, note.

**Contract** (brief; Feishu doc lines 90–99 and 269–281):

| | |
|---|---|
| Inputs | `Districts` (all four area classes), `Roads` (RoadFootprints + ModifiedTerrain), `Highways`, `MainTower`, `CentralParkFootprint`, `LandmarkPark`, `City` |
| Outputs and tags | `Lots`, `reservedLots`, `unbuildableLots`, `UnbuildableFootprints`, `SmallDistrictsBldgFootprints`, `MediumDistrictsBldgFootprints`, `LargeDistrictsBldgFootprints`, `Small Courtyards`, `Medium Courtyards`, `UnderHighway`, `LargeBuildingSkirt` |
| Parameters | the eleven listed in the brief (`PlazaReservationRatio` 0.9, the three classes' lot min/max and footprint min). `PlazaReservationSeed` merges into `Seed`; `debug`, `Debug_DistrictCategories`, `Partitioned`, `PartitionGridSize` go |
| Generation | `Subgraph_58` (Assign Road Grammar To Grid Splines), `Subgraph_63` (Spawn Road Grammar Assets), the `Create_Mesh_Planar` for the courtyard ground (`Subgraph_9`), `Subgraph_17`'s tag write |
| Python | subtract roads, landmarks, parks and highways from the districts; keep `UndividableDistricts` out; per class: intersect, filter by lot size, recurse, filter by footprint size, carve courtyards, build the large-lot inner grid, and decide reserved (`PlazaReservationRatio`) |

**Invariants:** every lot lies inside its district and outside roads, landmarks, parks and highways by more than 1 m; the class of each building footprint matches the class of the lot it came from; `UnderHighway` is non-empty exactly when a highway crosses a district; the reserved share is within ±10 % of `PlazaReservationRatio` (measured on items, not area — the doc warns the saved 0.9 is not an area ratio); the sum of lots + unbuildable + reserved + courtyards accounts for the districts' area within 1 %; empty inputs → all eleven outputs empty.

---

### Task 17: Stage 10, Ground

121 official nodes, 76 in Python. No parameters of its own; six generation nodes to keep.

**Files:** `pypcg/stages/s10_ground.py`, graph, `pypcg/checks/s10.py`, `Tools/pypcg/tests/test_s10_ground.py`, note.

**Contract** (brief; Feishu doc lines 102–109 and 282–291):

| | |
|---|---|
| Inputs | `Lots` (Lots + reservedLots), `Districts` (UndividableDistricts), `Roads`, `City`, `MainTower`, `LandmarkPark`, `CentralParkFootprint`, `Terrain`, `MeshTerrain` (Final) |
| Outputs | none published (the official graph's output node has no wired input); everything is generated inside. Keep the graph the same: no `out()` calls, and the Python node's outputs feed the generation nodes only |
| Parameters | none (the official graph has only `debug`, `Partitioned`, `PartitionGridSize`) |
| Generation | `Subgraph_26` (Assign Corners), `Subgraph_31` (Assign Sidewalks), `Subgraph_20` (Assign Railing And Fence Grammar), `Subgraph_32` (Spawn ground tiles), `Subgraph_35` (Spawn Sidewalk Assets), `Subgraph_36` (Spawn Fence Assets) |
| Python | sidewalk segments from the lot edges; the pedestrian area from the City grown by half the artery width (the `Polygon` tag, not an attribute: the doc corrects the node's title); exclusions around undividable districts, landmarks and parks; uniform tile points with seven random tile assets; raised and projected to the terrain; corrected prop orientation |

**Invariants:** the tile points lie inside the pedestrian area and outside the excluded areas; every sidewalk segment runs along a lot edge (its midpoint is within 1 m of a lot ring); the seven tile assets are all used across a run; no tile point is inside a building footprint; empty inputs → no outputs and no exceptions.

---

### Task 18: Stage 13, LeftOverLots

135 official nodes, 95 in Python, five fitting-asset nodes, three spawners.

**Files:** `pypcg/stages/s13_leftover_lots.py`, graph, checks, tests, note.

**Contract** (brief; Feishu doc lines 132–139 and 314–323):

| | |
|---|---|
| Inputs | `Lots` (reservedLots, unbuildableLots, UnbuildableFootprints, Small/Medium Courtyards, UnderHighway, LargeBuildingSkirt), `Districts` (UndividableDistricts), `Roads`, `Highways`, `MainTower`, `CentralParkFootprint`, `LandmarkPark`, `MeshTerrain` (Final) |
| Outputs | the plaza/tree split (`Reroute_4`; the official graph publishes only the randomly unselected plazas — keep that shape) |
| Parameters | `Ratio_Plaza_vs_Trees` 0.5, `UseMegaplantsTrees` False |
| Generation | `Subgraph_2`, `Subgraph_23`, `Subgraph_31`, `Subgraph_38`, `Subgraph_53` (the five fitting-asset calls), `Subgraph_72` (ground tiles), `Subgraph_74` (plaza), `Subgraph_76` (outer forest trees) |
| Python | subtract roads, landmarks and highways; split reserved lots into plazas and trees by `Ratio_Plaza_vs_Trees`; shrink and fit each courtyard class differently; ground tiles uniformly; tree scales and species from the texture; project to the terrain |

**Invariants:** areas are inside their source lot, shrunk (never grown); the plaza/tree split is on items and matches the ratio ±10 %; tree points are on the terrain within 5 cm (when a terrain input exists); the node titled "Only unbuildable lots" filters `LargeBuildingSkirt` — the test asserts the skirt areas are the ones used, not the unbuildable lots.

---

### Task 19: Stage 14, Parkings

81 official nodes, 68 in Python.

**Files:** `pypcg/stages/s14_parkings.py`, graph, checks, tests, note.

**Contract** (brief; Feishu doc lines 140–147 and 324–332):

| | |
|---|---|
| Inputs | `ParkingFootprint` (the LeftOverLots volume: whatever areas it published), `MeshTerrain` (Final) |
| Outputs | none published; the official output node has no input |
| Parameters | none |
| Generation | `Subgraph_53` (barrier grammar), `Subgraph_54` (chain-link fence grammar), `Subgraph_13` (Spawn All Parking Lot Assets) |
| Python | shrink the outline twice (outer parking spaces, inner aisle); grid the inner area and take each space's centre line and centre point; two rows from the outer and inner lines by shortening, resampling and ±Y offsets; cut the entrance from the boundary; arrow points on the median; randomly pick occupied spaces and the cars' facing; fences and barriers by their own rules |

**Invariants:** every space centre is inside the footprint; the number of spaces is within ±10 % of `area / (space area)` for the official space size; cars only sit on occupied spaces and face one of the two ways; the entrance cut leaves at least one boundary gap; empty inputs → no outputs.

---

### Task 20: Stage 11, Buildings

176 official nodes, 97 in Python, 23 generation nodes (three BDF assignments, thirteen rooftop meshes, two `AssignBuildingShape`, two `SetComplexBuildings`, three extruded collision loops).

**Files:** `pypcg/stages/s11_buildings.py`, graph, `pypcg/checks/s11.py`, `Tools/pypcg/tests/test_s11_buildings.py`, note.

**Contract** (brief; Feishu doc lines 112–119 and 292–304):

| | |
|---|---|
| Inputs | `Lots` (Small/Medium/Large bidistricts' building footprints), `HighRise` (actor tag), `MeshTerrain` (Final), `CitySample data` (`LoadCitySampleData`, one shared) |
| Outputs and tags | `SmallRooftops`, `MediumRooftops`, `LargeRooftops` (the rooftop areas, one per building) |
| Parameters | `MinHeightSmallDistrict` / `MaxHeightSmallDistrict` … for the three classes, `ComplexBuildingShapes`, `CollisionGeometry`. `Debug`, `Partitioned` go |
| Generation | the three `Assign_CitySampleBuildings` (`Subgraph_3`, `Subgraph_40`, `Subgraph_41`), the thirteen `Create_Mesh_Planar` rooftop meshes, `Loop_1`/`Loop_2` (`AssignBuildingShape`), `Subgraph_33`/`Subgraph_36` (`SetComplexBuildings`), `Loop_3`/`Loop_4`/`Loop_5` (extruded collision), `Loop_0`/`Loop_18`/`Loop_20` (rooftop mesh actors) |
| Python | per class: height from the texture, plus the HighRise distance/multiplier, clamped to the class range, projected and levelled to the terrain; the rooftop polygons grouped by material; the deliverable of each rooftop polygon to the right mesh node |
| Not ported | `Write_Attribute_fromTexture` stays native if the texture sampling cannot be called from Python (record the decision in the note: spec §4.3) |

**Invariants:** every building footprint's height attribute is inside its class's range; a footprint inside the HighRise zone is taller than the same footprint outside it; each input footprint produces exactly one rooftop polygon; the rooftop polygons partition their footprints (sum of areas within 1 %); the TL style code stays in the medium class's `BuildingsStyles` (traps.md 34: five separate style-code lists; do not touch any of them).

---

### Task 21: Stage 12, Rooftops

22 official nodes, 13 in Python, five generation nodes.

**Files:** `pypcg/stages/s12_rooftops.py`, graph, checks, tests, note.

**Contract** (brief; Feishu doc lines 122–129 and 305–313):

| | |
|---|---|
| Inputs | `Buildings` (Small/Medium/LargeRooftops) |
| Outputs | none published |
| Parameters | none (`Partitioned` goes) |
| Generation | `Subgraph_2`, `Subgraph_3`, `Subgraph_7`, `Subgraph_11` (the four fitting-asset placements + the unfiltered one), `Subgraph_13` (Spawn All Rooftop Assemblies) |
| Python | split by tag and area; the height filter for large roofs; the point differences that stop double placement; the small downward offset |

**Invariants:** every placement area is inside a rooftop polygon; small/WFC/skyscraper sets do not overlap; the `Average` (not max) Z reduction the doc flags is what the note describes and the code does; empty inputs → no outputs.

---

### Task 22: Stages 15 and 16, the landmark visuals

The two heaviest generation graphs: 30 and 13 generation nodes, 17 BDF assignments in the tower alone. The Python side computes what feeds each assignment.

**Files:** `pypcg/stages/s15_main_tower_visuals.py`, `pypcg/stages/s16_central_park_visuals.py`, graphs, checks, tests, notes.

**Contract** (briefs; Feishu doc lines 150–165 and 336–355). Stage 15: `MainTower` (the hero volume), `MeshTerrain` (Final), `CitySample data`; parameters `UseMegaplantsTrees` (the three footprint parameters go — the shape comes through the volume). Stage 16: `CentralParkFootprint`, `City`-tagged drawn splines (`USER_SPLINE`), `LAKE`, `FOREST_EXCLUSION`, `Roads` + `Parkings`, `MeshTerrain` (Final and Intermediate Priority 5), `CitySample Data`.

**Algorithm — stage 15:** align the input shape to the world centre and rotation; split it into the outer ring, the inner ring and three arms (±120°); per part, shrink and assign (CHC 50 m, CHA 25 m, CHJ 7–20 m by ring); lay plaza tiles, sidewalk and courtyard ground between centre and outer ring; place the tree ring on a spline with its own spacing; antennae on the rooftops above the area filter; roof assemblies and AC vents.
**Algorithm — stage 16:** four named transverse lines through the park centre plus the border road and the drawn paths; the Met footprint; lake spline projected and levelled to its lowest height, then a −50 cm lake-bed target; the `Write_MeshTerrain` at Priority 6 for the lake bed; vegetation by noise and density, excluding roads, the lake and the forest-exclusion area. Note the doc's warnings: the transverse-road grammar node and its expansions are `enabled=false` in the saved graph, and the historical snapshot has no visible edges into the lake writer — so the port must check both in the loaded demo before trusting them (Task 7's brief lists what exists).

**Invariants:** the tower's rings do not overlap the arms; the tree ring lies on the ring area; the lake mesh's area is within 1 % of the lake spline's polygon; no vegetation inside the lake, the exclusion area or a road; the Met footprint is inside the park; for both stages, an empty park or tower input gives no outputs and no exceptions.

---

### Task 23: Stage 18, OuterForest

**Files:** `pypcg/stages/s18_outer_forest.py`, graph, checks, tests, note.

**Contract** (brief; Feishu doc lines 174–181 and 364–374):

| | |
|---|---|
| Inputs | `MeshTerrain` (Final) → `Extract_MeshTerrainPoints`, `City`, `Highways`, `Roads`, `CentralParkFootprint`, `Terrain` (the city layout volume) |
| Outputs | none published |
| Parameters | `TreeDensity` 0.005, `ScaleMin` 0.6, `ScaleMax` 2.0, `CityEdgeBuffer` 100, `ParkBuffer` 1900, `UseMegaPlantsTrees` False |
| Generation | `SpawnForest_0` (Spawn Outer Forest Trees) |
| Python | grow the city and park exclusion areas, subtract the highway and road occupation, scatter on what remains, project; decide each point by water level, distance to the shore and to the deep-forest edge, and the noise density; species index and scale from the texture, jittered and normalised |

**Invariants:** no tree inside the city, the park, a road or the highway; the tree count matches `density × available area` within ±20 %; every scale is within `[ScaleMin, ScaleMax]`; a point's Z is its terrain height within 5 cm when a terrain input exists; empty terrain → no trees.

---

### Task 24: Stage 1, Terrain

The last port, because its write changes the ground every other stage projects onto.

**Files:** `pypcg/stages/s01_terrain.py`, graph, checks, tests, note.

**Contract** (brief; Feishu doc lines 24–31 and 200–208):

| | |
|---|---|
| Inputs | `MeshTerrain` (the current terrain) → `Extract_MeshTerrainPoints`, `City` (actor tag), `Terrain_shaping_1` (actor tag) |
| Outputs | the written terrain points (`WriteMeshTerrain_0`) |
| Parameters | `CityFlatness` 0.5 (the demo sets 0.6), `HillsHeight` 7001 |
| Generation | `WriteMeshTerrain_0` |
| Python | hills noise outside the city, the flat city area inside it with falloff, plus the terrain-shaping spline and the circle-minus-square exclusion the official graph applies |

**Invariants:** inside the City the height spread is under 500 cm and the mean is the `CityFlatness`-scaled value; the outer ring differs from the core by more than 1000 cm; the written point count equals the extracted point count; the same seed writes the same heights twice.

- [ ] **Step A+ — measure before porting.** The extracted terrain points can be millions. Add `{"terrain": {"bound": 200000}}` to the probe's phases (Task 6's script) to extract points inside a 2 km box, and record points per m² and the conversion time. Then:
  - points per m² × the terrain area = the stage's point count;
  - if that number is over ~300,000, port only the parts that are not per-point (the masks and the city flattening decisions), and keep `Transform_Points_SpatialNoise` and `Transform_Project` as native nodes, as spec §4.3 allows. Record which nodes stayed and why in `docs/pypcg/stages/s01.md` and the ledger.

---

## Phase P7 — The town

### Task 25: The town level and its control splines

**Files:**
- Create: `Content/Python/pypcg/profiles/town_layout.py`, `Content/Python/pypcg_town_level.py`
- Create: `Tools/pypcg/tests/test_town_layout.py`
- Create (generated): `Content/Python/pypcg/profiles/town_bindings.json`
- Create (level): `/Game/PyPCG/L_PyTown` (+ `Content/__ExternalActors__/PyPCG/`, `Content/__ExternalObjects__/PyPCG/`)
- Modify: `.gitignore`

**Interfaces — Produces:** `town_layout`: `CITY`, `TERRAIN_SHAPING`, `ARTERY_A1/A2`, `HIGHWAY_2/3`, `MAIN_TOWER`, `TOWER_HALF`, `HIGHRISE`, `LANDMARK_PARK`, `PARK_CENTER`, `PARK_YAW`, `PARK_HALF`, `park(u,v)`, `PARK_RECT`, `LAKE`, `PARK_PATHS`, `FOREST_EXCLUSION`, `PARKING_CENTER`, `PARKING_HALF`, `parking_rect()`, `SPLINES`, `DESTROY`, `VOLUME_MOVES`, `city_bbox(margin_cm=0)`, `inside`, `edge_distance`, `polyline_distance`, `crossings`; `town_bindings.json`: `{role: soft object path in L_PyTown}`; `pypcg_town_level.py` phases `layout`, `bind`, `save`.

**Two changes from the 2026-10-13 design** (the graph work of P0–P6 makes both necessary):
- **No parking-footprint volume move.** `ParkingFootprint` is the LeftOverLots volume, and Parkings consumes whatever areas LeftOverLots publishes. The town therefore cannot place a 70 × 45 m parking lot directly (spec §5.1's number); V3 requires parking instances to appear where LeftOverLots reserved lots, and the report says so. Nothing is moved or scaled for parking.
- **Landmark sizes are component overrides, not knobs.** Stages 4 and 5 expose `RectWidth` / `RectLength` (Task 13), so the town sets them on its volumes:
  - `PCG_2_1_MainTower_Footprint`: `RectWidth` = `RectLength` = 11000 (110 m; fallback 16000 = the official 160 m set, see Task 27 Step 5);
  - `PCG_2_2_CentralPark_Footprint`: `RectWidth` = 26000, `RectLength` = 9000 (260 × 90 m).

- [ ] **Step 1: Write the failing layout tests** `Tools/pypcg/tests/test_town_layout.py`:

```python
import math

from pypcg.profiles import town_layout as T

M = 100  # cm per m


def test_city_is_about_1100_by_900_m():
    (x0, y0, _), (x1, y1, _) = T.city_bbox()
    assert abs((x1 - x0) / M - 1100) <= 220 and abs((y1 - y0) / M - 900) <= 180


def test_terrain_shaping_contains_city_with_100_m_margin():
    assert all(T.inside(p, T.TERRAIN_SHAPING) for p in T.CITY)
    assert min(T.edge_distance(p, T.TERRAIN_SHAPING) for p in T.CITY) >= 100 * M


def test_arteries_cross_the_city_and_each_other():
    for a in (T.ARTERY_A1, T.ARTERY_A2):
        assert T.crossings(a, T.CITY) == 2
        assert not T.inside(a[0], T.CITY) and not T.inside(a[-1], T.CITY)
        assert min(T.edge_distance(a[0], T.CITY), T.edge_distance(a[-1], T.CITY)) >= 150 * M
    assert T.crossings(T.ARTERY_A1, [p for p in T.ARTERY_A2], closed=False) == 1


def test_highways_cut_the_north_east_corner_30_m_apart():
    for h in (T.HIGHWAY_2, T.HIGHWAY_3):
        assert T.crossings(h, T.CITY) == 2
    gap = T.polyline_distance(T.HIGHWAY_2[len(T.HIGHWAY_2) // 2], T.HIGHWAY_3)
    assert abs(gap / M - 30) < 1


def test_main_tower_and_landmarks_sit_inside_with_margins():
    tower = T.MAIN_TOWER
    assert T.inside(tower, T.CITY)
    assert T.edge_distance(tower, T.CITY) - T.TOWER_HALF >= 50 * M
    assert min(T.polyline_distance(tower, h) for h in (T.HIGHWAY_2, T.HIGHWAY_3)) - T.TOWER_HALF >= 60 * M
    assert all(T.inside(p, T.CITY) for p in T.HIGHRISE + T.LANDMARK_PARK)
    lx = [p[0] for p in T.LANDMARK_PARK]
    assert max(lx) < tower[0] - T.TOWER_HALF          # the small park does not overlap the tower


def test_central_park_and_parking_are_clear_of_edges_and_arteries():
    for shape in (T.PARK_RECT, T.parking_rect()):
        assert all(T.inside(p, T.CITY) for p in shape)
        assert min(T.edge_distance(p, T.CITY) for p in shape) >= 30 * M
        assert min(T.polyline_distance(p, a) for p in shape for a in (T.ARTERY_A1, T.ARTERY_A2)) >= 40 * M


def test_park_features_lie_inside_the_park():
    for shape in [T.LAKE, T.FOREST_EXCLUSION] + list(T.PARK_PATHS):
        assert all(T.inside(p, T.PARK_RECT) for p in shape)


def test_spline_table_is_complete():
    assert set(T.SPLINES) == {"CityShape", "TerrainShaping", "Artery_1", "Artery_2", "HighWay_2", "HighWay_3",
                              "HighRise_Zone_1", "MainTowerPark", "Lake_1", "ParkPath_1", "ParkPath_2",
                              "ForestExclusion_1"}
    for spec in T.SPLINES.values():
        assert all(len(p) == 3 for p in spec["points"])


def test_parking_rect_is_about_70_by_45_m():
    assert abs((T.PARKING_HALF[0] * 2) / M - 70) < 5 and abs((T.PARKING_HALF[1] * 2) / M - 45) < 5
```

Run → fails (no module).

- [ ] **Step 2: Write `Content/Python/pypcg/profiles/town_layout.py`** (pure data and geometry, no `unreal`; the numbers are the 2026-10-13 ones, re-checked by the tests):

```python
"""Control-spline layout of the ~1.1 x 0.9 km town (cm, world space, Z = 0). No unreal import.

Change the town by editing this file only; test_town_layout.py checks the relations the 18 stages rely
on (arteries cross the city, the highway pair cuts the north-east corner so UnderHighway lots exist,
landmarks keep clear of edges and roads)."""
import math

CITY = [(55000, 0), (42000, 33000), (8000, 45000), (-30000, 40000), (-55000, 10000),
        (-48000, -28000), (-10000, -45000), (35000, -38000)]


def ellipse(cx, cy, rx, ry, n):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


TERRAIN_SHAPING = ellipse(0, 0, 80000, 65000, 16)
ARTERY_A1 = [(-80000, -5000), (-20000, 2000), (25000, -3000), (80000, 4000)]       # east-west
ARTERY_A2 = [(-6000, -70000), (2000, -15000), (-3000, 20000), (5000, 70000)]       # north-south

_HIGHWAY_C = 65000                 # centre line x + y = 65000
_HALF_GAP = 1500 * math.sqrt(2)     # 15 m either side along the normal -> 30 m apart


def _highway(c):
    return [(x, c - x) for x in range(-25000, 90001, 11500)]


HIGHWAY_2 = _highway(_HIGHWAY_C - _HALF_GAP)
HIGHWAY_3 = _highway(_HIGHWAY_C + _HALF_GAP)

MAIN_TOWER = (25000, 15000)
TOWER_HALF = 5500                  # ~110 m footprint (spec D7); 8000 is the 160 m fallback
HIGHRISE = ellipse(MAIN_TOWER[0], MAIN_TOWER[1], 10000, 10000, 12)
LANDMARK_PARK = [(14000 + sx * 3500, 15000 + sy * 3500) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]

PARK_CENTER = (-25000, -17000)
PARK_YAW = 30.0
PARK_HALF = (13000, 4500)          # 260 x 90 m


def park(u, v):
    r = math.radians(PARK_YAW)
    return (PARK_CENTER[0] + u * math.cos(r) - v * math.sin(r), PARK_CENTER[1] + u * math.sin(r) + v * math.cos(r))


PARK_RECT = [park(sx * PARK_HALF[0], sy * PARK_HALF[1]) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
LAKE = [park(u, v) for u, v in ellipse(6000, 0, 2500, 1500, 12)]
PARK_PATHS = ([park(u, 2000 + 400 * math.sin(u / 4000.0)) for u in range(-12000, 12001, 3000)],
              [park(u, -2000 + 400 * math.cos(u / 4000.0)) for u in range(-12000, 12001, 3000)])
FOREST_EXCLUSION = [park(-7000 + su * 1500, 1500 + sv * 1250) for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]

PARKING_CENTER = (-36000, 15000)
PARKING_HALF = (3500, 2250)        # 70 x 45 m


def parking_rect():
    cx, cy = PARKING_CENTER
    return [(cx + sx * PARKING_HALF[0], cy + sy * PARKING_HALF[1]) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def _3d(points):
    return [(float(x), float(y), 0.0) for x, y in points]


SPLINES = {
    "CityShape": {"points": _3d(CITY), "closed": True, "linear": False},
    "TerrainShaping": {"points": _3d(TERRAIN_SHAPING), "closed": True, "linear": False},
    "Artery_1": {"points": _3d(ARTERY_A1), "closed": False, "linear": False},
    "Artery_2": {"points": _3d(ARTERY_A2), "closed": False, "linear": False},
    "HighWay_2": {"points": _3d(HIGHWAY_2), "closed": False, "linear": False},
    "HighWay_3": {"points": _3d(HIGHWAY_3), "closed": False, "linear": False},
    "HighRise_Zone_1": {"points": _3d(HIGHRISE), "closed": True, "linear": False},
    "MainTowerPark": {"points": _3d(LANDMARK_PARK), "closed": True, "linear": True},
    "Lake_1": {"points": _3d(LAKE), "closed": True, "linear": False},
    "ParkPath_1": {"points": _3d(PARK_PATHS[0]), "closed": False, "linear": False},
    "ParkPath_2": {"points": _3d(PARK_PATHS[1]), "closed": False, "linear": False},
    "ForestExclusion_1": {"points": _3d(FOREST_EXCLUSION), "closed": True, "linear": True},
}

# Control actors the town does not need (labels in the template copy).
DESTROY = ["Artery_3", "HighRise_Zone_2", "Lake_2", "ForestExclusion_2"]

# Volumes whose location defines a landmark. Z is kept; yaw is set when given.
VOLUME_MOVES = {
    "PCG_2_1_MainTower_Footprint": {"xy": MAIN_TOWER},
    "PCG_4_1_MainTower_Visuals": {"xy": MAIN_TOWER},
    "PCG_2_2_CentralPark_Footprint": {"xy": PARK_CENTER, "yaw": PARK_YAW},
}


def city_bbox(margin_cm=0):
    xs, ys = [p[0] for p in CITY], [p[1] for p in CITY]
    return [[min(xs) - margin_cm, min(ys) - margin_cm, -1e9], [max(xs) + margin_cm, max(ys) + margin_cm, 1e9]]


# ---- geometry
def _seg_distance(p, a, b):
    (px, py), (ax, ay), (bx, by) = p[:2], a[:2], b[:2]
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / float(dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def edge_distance(p, polygon):
    return min(_seg_distance(p, polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon)))


def polyline_distance(p, polyline):
    return min(_seg_distance(p, polyline[i], polyline[i + 1]) for i in range(len(polyline) - 1))


def inside(p, polygon):
    x, y = p[:2]
    hit = False
    for i in range(len(polygon)):
        (x1, y1), (x2, y2) = polygon[i][:2], polygon[(i + 1) % len(polygon)][:2]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / float(y2 - y1):
            hit = not hit
    return hit


def _cross(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (orient(a, b, c) > 0) != (orient(a, b, d) > 0) and (orient(c, d, a) > 0) != (orient(c, d, b) > 0)


def crossings(polyline, shape, closed=True):
    """How many times the open polyline crosses the edges of shape (closed polygon by default)."""
    edges = [(shape[i], shape[(i + 1) % len(shape)]) for i in range(len(shape) if closed else len(shape) - 1)]
    return sum(1 for i in range(len(polyline) - 1) for c, d in edges if _cross(polyline[i], polyline[i + 1], c, d))
```

- [ ] **Step 3: Run the layout tests** → `9 passed`. If one fails, adjust only coordinates (keep the sizes: tower ~110 m, park ~260×90 m, parking ~70×45 m) and note the change.

- [ ] **Step 4: Create the level.** The editor is on the demo level; one call:

```
run_unreal_script("pcg_sa_level.py", {"template": "/CitySamplePCG/Levels/L_CitySamplePCG_Demo",
                                      "target": "/Game/PyPCG/L_PyTown"})
```

Expected `gate.pass: true` (194 actors, 1 terrain, 18 volumes, 11 cameras, 19 spline actors). The script opens the new level.

- [ ] **Step 5: Write `Content/Python/pypcg_town_level.py`**

```python
# pypcg_town_level.py -- shape the template copy into the town (Task 25).
# Args: {"phase": "layout" | "bind" | "save"}
#   layout : cleanup every volume, destroy unneeded control actors, move landmark volumes, rewrite the
#            control splines from town_layout.SPLINES, place the parking footprint
#   bind   : resolve the 13 roles to actors of this level -> pypcg/profiles/town_bindings.json
# Spline points are written in WORLD space after any actor move (traps.md 30).
LEVEL = "L_PyTown"


def _actor(label):
    from pypcg import census
    a = census.actor_by_label(label)
    if a is None:
        raise RuntimeError("no actor labelled %s" % label)
    return a


def _write_spline(actor, spec):
    sc = actor.get_component_by_class(unreal.SplineComponent)
    if sc is None:
        raise RuntimeError("%s has no SplineComponent" % actor.get_actor_label())
    pts = [unreal.Vector(*p) for p in spec["points"]]
    sc.set_spline_points(pts, unreal.SplineCoordinateSpace.WORLD, False)
    sc.set_closed_loop(spec["closed"], False)
    if spec["linear"]:
        for i in range(len(pts)):
            sc.set_spline_point_type(i, unreal.SplinePointType.LINEAR, False)
    sc.update_spline()
    back = [sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD) for i in range(sc.get_number_of_spline_points())]
    err = max(abs(a.x - b[0]) + abs(a.y - b[1]) for a, b in zip(back, spec["points"])) if back else 1e9
    return {"points": len(back), "closed": bool(sc.is_closed_loop()), "max_error_cm": round(err, 3)}


def phase_layout():
    from pypcg import census
    from pypcg.profiles import town_layout as T
    out = {"cleaned": 0, "destroyed": [], "moved": {}, "splines": {}}
    for v in census.volumes():
        v.get_component_by_class(unreal.PCGComponent).cleanup_local(True)
        out["cleaned"] += 1
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for label in T.DESTROY:
        a = census.actor_by_label(label)
        if a is not None and eas.destroy_actor(a):
            out["destroyed"].append(label)
    for label, move in T.VOLUME_MOVES.items():
        a = _actor(label)
        z = a.get_actor_location().z
        a.set_actor_location(unreal.Vector(move["xy"][0], move["xy"][1], z), False, False)
        if "yaw" in move:
            r = a.get_actor_rotation()
            a.set_actor_rotation(unreal.Rotator(pitch=r.pitch, yaw=move["yaw"], roll=r.roll), False)
        out["moved"][label] = [round(x, 1) for x in a.get_actor_location().to_tuple()]
    for label, spec in T.SPLINES.items():
        out["splines"][label] = _write_spline(_actor(label), spec)
    out["ok"] = all(s["max_error_cm"] < 0.5 for s in out["splines"].values()) and len(out["destroyed"]) == len(T.DESTROY)
    return out


def phase_bind():
    from pypcg import census
    from pypcg.profiles import official
    bindings, missing = {}, []
    for role, label in official.ROLE_LABELS.items():
        a = census.actor_by_label(label)
        if a is None:
            missing.append(role)
            continue
        bindings[role] = a.get_path_name()
    bad = [r for r, p in bindings.items() if not p.startswith("/Game/PyPCG/L_PyTown")]
    path = os.path.join(_PY, "pypcg", "profiles", "town_bindings.json")
    if not missing and not bad and len(bindings) == len(official.ROLES):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(bindings, fh, indent=1, sort_keys=True)
            fh.write("\n")
    return {"bindings": bindings, "missing": missing, "not_in_town": bad, "written": not missing and not bad}


def phase_save():
    return {"saved": bool(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level())}


def run(args):
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if LEVEL not in str(les.get_current_level()):
        return {"abort": "open /Game/PyPCG/%s first" % LEVEL}
    return {"layout": phase_layout, "bind": phase_bind, "save": phase_save}[args.get("phase", "layout")]()


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
```

(Before this block, the same entry preamble as `pypcg_build_slim.py`; `census.volumes()` is added in this task: `def volumes(): return [a for a in …get_all_level_actors() if a.get_component_by_class(unreal.PCGComponent) is not None]`.)

- [ ] **Step 6: Run `layout`, then `bind`.** Expected `layout.ok: true`, 18 cleaned, 4 destroyed, every spline `max_error_cm < 0.5`; then `bind.written: true` with 13 bindings under `/Game/PyPCG/L_PyTown`. Then `{"phase": "save"}` → `saved: true`.

- [ ] **Step 7: Track the level.** Add to `.gitignore` beside the `PCGArea` exceptions:

```
!/Content/__ExternalActors__/PyPCG/
!/Content/__ExternalObjects__/PyPCG/
```

- [ ] **Step 8: Commit**

```bash
git add Content/Python/pypcg/profiles/town_layout.py Content/Python/pypcg/profiles/town_bindings.json Tools/pypcg/tests/test_town_layout.py Content/Python/pypcg_town_level.py .gitignore Content/PyPCG/L_PyTown.umap Content/__ExternalActors__/PyPCG Content/__ExternalObjects__/PyPCG
git commit -m "Create the 1 km town level from the demo template and lay out its control splines" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 26: The town profile, the town graphs and the volume assignment

**Files:**
- Create: `Content/Python/pypcg/profiles/town.py`, `Content/Python/pypcg_town.py` (phase `assign`; the other phases come in Task 27)
- Create (generated, committed): `Content/PyPCG/Town/PCG_*.uasset` (18)

**Interfaces — Produces:** `profiles.town`: `ROLES` (from `town_bindings.json`), `COMPONENT_OVERRIDES = {volume label: {param: value}}`; `pypcg_town.py {"phase": "assign"}`.

- [ ] **Step 1: Write `Content/Python/pypcg/profiles/town.py`**

```python
"""Bindings for the town level /Game/PyPCG/L_PyTown (spec 5.2).

ROLES come from town_bindings.json (pypcg_town_level.py {"phase": "bind"}).
COMPONENT_OVERRIDES are set on the volumes' PCG components after set_graph (traps.md 44), so the town's
graphs differ from the official ones only at their role bindings. The landmark sizes are ordinary
parameters of stages 4 and 5 (Task 13), which is why no knob mechanism exists any more."""
import json
import os

LEVEL = "/Game/PyPCG/L_PyTown"

with open(os.path.join(os.path.dirname(__file__), "town_bindings.json"), encoding="utf-8") as _fh:
    ROLES = json.load(_fh)

COMPONENT_OVERRIDES = {
    # 110 m tower (spec D7); the 160 m fallback is RectWidth/Length = 16000 (Task 27 Step 5)
    "PCG_2_1_MainTower_Footprint": {"RectWidth": 11000.0, "RectLength": 11000.0},
    "PCG_2_2_CentralPark_Footprint": {"RectWidth": 26000.0, "RectLength": 9000.0},
}
```

- [ ] **Step 2: Build the 18 town graphs** — `run_unreal_script("pypcg_build_slim.py", {"stages": "all", "profile": "town"})`, split into groups of 3–4 if one call is slow. Expected per row: `diffs: 0`. A diff is a town build that changed something no role declares.

- [ ] **Step 3: Write `Content/Python/pypcg_town.py` with the `assign` phase** (entry preamble, then). Tasks 27–28 add the remaining phases to this file.

```python
# pypcg_town.py -- run the 18 stages in the town level (spec 5). One phase per call.
#   assign                       volumes -> /Game/PyPCG/Town/*, keep their overrides + the town's
#   reset                        cleanup_local on every volume                     (Task 27)
#   gen {"stage"}                activate + generate_local(True)                   (Task 27)
#   read {"stage","pass"}        census + acceptance for that stage                (Task 27)
#   shot {"stage","pass"}        one screenshot of the town so far                 (Task 27)
#   overview {"view"}            top / street / wide                               (Task 27)
#   finish                       compare passes, save level, write census          (Task 28)
LEVEL = "L_PyTown"
REPORTS = os.path.join(_REPO, "Saved", "Reports")
OVERRIDES = os.path.join(REPORTS, "pypcg_town_component_overrides.json")


def _load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True)


def phase_assign():
    from pypcg import census, stages
    from pypcg.profiles import town
    saved = _load(OVERRIDES, {})
    out = {}
    for s in stages.STAGES:
        v = census.volume(s[0])
        pc = v.get_component_by_class(unreal.PCGComponent)
        if s[1] not in saved:                       # the template copy's own overrides, recorded once
            saved[s[1]] = census.overrides(pc)
        pc.set_graph(unreal.EditorAssetLibrary.load_asset("/Game/PyPCG/Town/" + s[1]))
        wanted = dict(saved[s[1]])
        wanted.update(town.COMPONENT_OVERRIDES.get(s[1], {}))
        res = census.apply_overrides(pc, wanted)
        back = census.overrides(pc)
        out[s[1]] = {"graph": pc.get_graph().get_path_name(),
                     "overrides_ok": all(back.get(k) == val for k, val in wanted.items() if k not in res["skipped"]),
                     "skipped": res["skipped"], "overrides": back}
    _save(OVERRIDES, saved)
    return out
```

and at the end of the file:

```python
PHASES = {"assign": lambda a: phase_assign()}


def run(args):
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if LEVEL not in str(les.get_current_level()):
        return {"abort": "open /Game/PyPCG/%s first" % LEVEL}
    phase = args.get("phase")
    if phase not in PHASES:
        return {"abort": "unknown phase %r; phases: %s" % (phase, sorted(PHASES))}
    return PHASES[phase](args)


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
```

- [ ] **Step 4: Run `assign`** with the editor on `L_PyTown`. Expected: 18 entries, every graph under `/Game/PyPCG/Town/`, every `overrides_ok: true`. Then `pypcg_town_level.py {"phase": "save"}` → `saved: true`.

- [ ] **Step 5: Commit**

```bash
git add Content/Python/pypcg/profiles/town.py Content/Python/pypcg_town.py Content/PyPCG/Town Content/PyPCG/L_PyTown.umap Content/__ExternalActors__/PyPCG Content/__ExternalObjects__/PyPCG
git commit -m "Build the town variants of the 18 graphs and assign them to the town volumes" -m "Town graphs differ from the official ones only at their role bindings." -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 27: The town, pass 1, with per-stage acceptance

**Files:**
- Create: `Content/Python/pypcg/town_checks.py`, `Tools/pypcg/tests/test_town_checks.py`
- Modify: `Content/Python/pypcg_town.py` (phases `reset`, `gen`, `read`, `shot`, `overview`)

**Interfaces — Produces:** `town_checks.RULES`, `town_checks.check(stage, rec, upstream, town_bbox) -> {"status", "failures", "notes"}`; `town_checks.plausibility(town, official) -> failures`; census `Saved/Reports/pypcg_town_pass<k>.json`; screenshots `pt_stage_<NN>_<graph>_p<k>.png`.

- [ ] **Step 1: Write the failing tests** `Tools/pypcg/tests/test_town_checks.py`:

```python
from pypcg import town_checks as C
from pypcg.profiles import town_layout as T

BOX = T.city_bbox(20000)
INSIDE = [[-10000, -10000, 0], [10000, 10000, 100]]


def rec(instances=10, tags=(), meshes=None, out=INSIDE, comp=INSIDE, components=None, generated=True):
    return {"generated": generated, "instances": {"total": instances, "per_mesh": meshes or {"/Game/Building/X": instances},
                                                 "components": components or {}},
            "items": [{"tags": [t], "kind": "polygon", "area_m2": 100.0, "length_m": 0.0, "points": 0, "bbox": out} for t in tags],
            "output_bounds": out, "component_bounds": comp}


def test_bbox_outside_town_fails():
    # Review Focus 1: a stage that read the demo level's whole city shows up far outside the town.
    far = [[-120000, -90000, 0], [140000, 100000, 100]]
    v = C.check(10, rec(instances=1, comp=far), {"Lots": rec(tags=["Lots", "reservedLots"])}, BOX)
    assert v["status"] == "fail" and any("outside" in f for f in v["failures"])


def test_required_tags_and_optional_tags():
    tags = ["ArteryRoads", "CollectorRoads", "localRoads", "SmallDistricts"]
    assert C.check(6, rec(instances=0, tags=tags), {}, BOX)["status"] == "ok"
    v = C.check(6, rec(instances=0, tags=tags[:3]), {}, BOX)
    assert v["status"] == "fail" and any("SmallDistricts" in f for f in v["failures"])


def test_upstream_must_be_generated_with_its_tags():
    v = C.check(7, rec(tags=["RoadFootprints", "ModifiedTerrain"]), {"Districts": rec(tags=["localRoads"])}, BOX)
    assert v["status"] == "fail" and any("Districts" in f for f in v["failures"])


def test_zero_instances_fail_for_generating_stages():
    assert C.check(12, rec(instances=0), {"Buildings": rec(tags=["SmallRooftops"])}, BOX)["status"] == "fail"


def test_buildings_need_tl():
    up = {"Lots": rec(tags=["SmallDistrictsBldgFootprints"])}
    assert C.check(11, rec(meshes={"/Game/Building/CH/Kit_A": 5}), up, BOX)["status"] == "fail"
    assert C.check(11, rec(meshes={"/Game/Building/TL/SM_TL_Wall": 5}), up, BOX)["status"] == "ok"


def test_terrain_unmeasured_is_not_a_failure():
    assert C.check(1, rec(instances=0), {}, BOX)["status"] == "unmeasured"
    flat = dict(rec(instances=0), terrain={"inner": [0.0, 120.0, -80.0], "outer": [4000.0, 2500.0]})
    assert C.check(1, flat, {}, BOX)["status"] == "ok"
    bumpy = dict(rec(instances=0), terrain={"inner": [0.0, 3000.0], "outer": [4000.0]})
    assert C.check(1, bumpy, {}, BOX)["status"] == "fail"


def test_parkings_need_no_footprint_overrides():
    # The town cannot place a parking lot: Parkings consumes whatever LeftOverLots published (Task 25).
    assert C.check(14, rec(instances=3), {"ParkingFootprint": rec(tags=["reservedLots"])}, BOX)["status"] == "ok"


def test_plausibility_compares_densities_with_the_official_city():
    town = {"area_m2": 1000000.0, "buildings": 50.0, "road_m": 20000.0}
    official = {"area_m2": 1000000.0, "buildings": 50.0, "road_m": 20000.0}
    assert C.plausibility(town, official) == []
    assert C.plausibility(dict(town, buildings=200.0), official)          # 4x the official density
    assert C.plausibility(dict(town, road_m=3000.0), official)            # 0.15x
```

- [ ] **Step 2: Write `Content/Python/pypcg/town_checks.py`** (stage numbers per the Feishu order; `LAKE_COMPONENT` is filled in from Task 7's recorded component classes for stage 16):

```python
"""Per-stage acceptance for the town run (spec 5). No unreal import."""

LAKE_COMPONENT = "DynamicMeshComponent"   # replaced with what stage 16's census recorded, if different

RULES = {
    1: {"terrain": True},
    2: {"min_instances": 1},
    3: {"min_instances": 1},
    4: {"data": True, "bbox": True},
    5: {"data": True, "bbox": True},
    6: {"tags": ["ArteryRoads", "CollectorRoads", "localRoads", "SmallDistricts"], "bbox": True},
    7: {"tags": ["RoadFootprints", "ModifiedTerrain"], "min_instances": 1, "bbox": True,
        "upstream": {"Districts": ["localRoads", "CollectorRoads", "ArteryRoads"]}},
    8: {"tags": ["Highway"], "min_instances": 1, "bbox": True, "upstream": {"Roads": ["RoadFootprints"]}},
    9: {"tags": ["Lots", "reservedLots", "SmallDistrictsBldgFootprints", "UnderHighway"], "bbox": True,
        "upstream": {"Districts": ["SmallDistricts"], "Roads": ["RoadFootprints"], "Highways": ["Highway"]}},
    10: {"min_instances": 1, "bbox": True, "upstream": {"Lots": ["Lots", "reservedLots"]}},
    11: {"min_instances": 1, "bbox": True, "meshes_any": ["/Game/Building/TL/"],
         "tags": ["SmallRooftops"], "upstream": {"Lots": ["SmallDistrictsBldgFootprints"]}},
    12: {"min_instances": 1, "bbox": True, "upstream": {"Buildings": ["SmallRooftops"]}},
    13: {"min_instances": 1, "bbox": True, "upstream": {"Lots": ["reservedLots"]}},
    14: {"min_instances": 1, "bbox": True, "upstream": {"ParkingFootprint": []}},
    15: {"min_instances": 1, "bbox": True, "meshes_all": ["CHC", "CHA", "CHJ"], "upstream": {"MainTower": []}},
    16: {"min_instances": 1, "bbox": True, "components_any": [LAKE_COMPONENT],
         "upstream": {"CentralParkFootprint": [], "Roads": []}},
    17: {"min_instances": 1},
    18: {"min_instances": 1},
}
FLAT_INNER_CM = 500        # spread allowed inside the city
RELIEF_OUTER_CM = 1000     # the outer ring must differ from the core by at least this
PLAUSIBLE_MIN, PLAUSIBLE_MAX = 0.5, 2.0    # town density / official density (spec 5.2)


def _inside(box, town):
    return all(town[0][i] <= box[0][i] and box[1][i] <= town[1][i] for i in range(2))


def check(stage, rec, upstream, town_bbox):
    rule = RULES[stage]
    failures, notes = [], []
    if rule.get("terrain"):
        t = rec.get("terrain")
        if not t or not t.get("inner") or not t.get("outer"):
            return {"status": "unmeasured", "failures": [], "notes": ["terrain heights not measurable; see the screenshot"]}
        inner, outer = t["inner"], t["outer"]
        mean = sum(inner) / len(inner)
        if max(inner) - min(inner) > FLAT_INNER_CM:
            failures.append("city core not flat: spread %.0f cm" % (max(inner) - min(inner)))
        if max(abs(z - mean) for z in outer) < RELIEF_OUTER_CM:
            failures.append("no relief outside the city")
        return {"status": "fail" if failures else "ok", "failures": failures, "notes": notes}
    if not rec.get("generated"):
        failures.append("volume not generated")
    tags = {t for it in rec.get("items", []) for t in it["tags"] if ":" not in t}
    for tag in rule.get("tags", []):
        if tag not in tags:
            failures.append("missing output tag %s" % tag)
    if rule.get("data") and not rec.get("items"):
        failures.append("no output data")
    total = rec.get("instances", {}).get("total", 0)
    if total < rule.get("min_instances", 0):
        failures.append("instances %d < %d" % (total, rule["min_instances"]))
    meshes = rec.get("instances", {}).get("per_mesh", {})
    if rule.get("meshes_any") and not any(any(s in m for m in meshes) for s in rule["meshes_any"]):
        failures.append("no mesh matching %s" % rule["meshes_any"])
    for s in rule.get("meshes_all", []):
        if not any(s in m for m in meshes):
            failures.append("no mesh matching %s" % s)
    if rule.get("components_any") and not any(c in rec.get("instances", {}).get("components", {})
                                              for c in rule["components_any"]):
        failures.append("no component of class %s" % rule["components_any"])
    if rule.get("bbox"):
        for it in rec.get("items", []):
            if it["bbox"] and not _inside(it["bbox"], town_bbox):
                failures.append("output %s outside the town (+200 m): %s" % (it["tags"], it["bbox"]))
                break
    for role, want in rule.get("upstream", {}).items():
        up = upstream.get(role)
        if up is None or not up.get("generated"):
            failures.append("upstream %s not generated" % role)
            continue
        have = {t for it in up.get("items", []) for t in it["tags"] if ":" not in t}
        missing = [t for t in want if t not in have]
        if missing:
            failures.append("upstream %s lacks tags %s" % (role, missing))
    return {"status": "fail" if failures else "ok", "failures": failures, "notes": notes}


def plausibility(town, official):
    """spec 5.2: the town's building and road densities must sit within [0.5x, 2x] of the official
    city's (both from V2 records: buildings per km2, road metres per km2)."""
    out = []
    for what, key in (("buildings per km2", "buildings"), ("road metres per km2", "road_m")):
        t, o = town[key] / (town["area_m2"] / 1e6), official[key] / (official["area_m2"] / 1e6)
        if not o:
            continue
        ratio = t / o
        if not PLAUSIBLE_MIN <= ratio <= PLAUSIBLE_MAX:
            out.append("%s: town %.1f vs official %.1f (%.2fx, allowed %.1f-%.1f)"
                       % (what, t, o, ratio, PLAUSIBLE_MIN, PLAUSIBLE_MAX))
    return out
```

- [ ] **Step 3: Add the run phases to `pypcg_town.py`** — insert above `PHASES`:

```python
SHOT = "pt_stage_%02d_%s_p%d.png"
TERRAIN_SAMPLES = {"inner": [(0, 0), (20000, 10000), (-20000, -10000), (10000, -25000), (-25000, 20000)],
                   "outer": [(75000, 0), (-75000, 0), (0, 70000), (0, -70000)]}


def _pass_file(k):
    return os.path.join(REPORTS, "pypcg_town_pass%d.json" % k)


def _trace_z(x, y):
    from pypcg import census
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    try:
        res = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, 500000.0), unreal.Vector(x, y, -500000.0),
                                                     unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [],
                                                     unreal.DrawDebugTrace.NONE, True)
        hit = res[-1] if isinstance(res, tuple) else res
        parts = unreal.GameplayStatics.break_hit_result(hit)
        return float(parts[4].z) if parts[0] else None
    except Exception:
        return None


def phase_reset(args):
    from pypcg import census
    for v in census.volumes():
        v.get_component_by_class(unreal.PCGComponent).cleanup_local(True)
    return {"cleaned": len(census.volumes())}


def phase_gen(args):
    from pypcg import census, stages
    stage = int(args["stage"])
    pc = census.component(stage)
    pc.activate(True)
    pc.generate_local(True)
    return {"stage": stage, "graph": pc.get_graph().get_path_name()}


def phase_read(args):
    from pypcg import census, stages, town_checks
    from pypcg.profiles import official, town_layout
    stage, k = int(args["stage"]), int(args.get("pass", 1))
    rec = census.record(stage)
    rec["params"] = dict(census.overrides(census.component(stage)))
    if stage == 1:
        z = {key: [_trace_z(x, y) for x, y in pts] for key, pts in TERRAIN_SAMPLES.items()}
        if all(v is not None for vals in z.values() for v in vals):
            rec["terrain"] = z
    upstream = {}
    by_graph = {s[1]: s[0] for s in stages.STAGES}
    for role in town_checks.RULES[stage].get("upstream", {}):
        upstream[role] = census.record(by_graph[official.ROLE_LABELS[role]])
    verdict = town_checks.check(stage, rec, upstream, town_layout.city_bbox(20000))
    data = _load(_pass_file(k), {})
    data[str(stage)] = {"graph": stages.name(stage), "record": rec, "verdict": verdict}
    _save(_pass_file(k), data)
    return {"stage": stage, "pass": k, "instances": rec["instances"]["total"], "tags": sorted(
        {t for it in rec["items"] for t in it["tags"] if ":" not in t}), **verdict}


def phase_shot(args):
    from pypcg import stages
    from pypcg.profiles import town_layout
    if _PY not in sys.path:
        sys.path.insert(0, _PY)
    for m in ("pcg_sa_shots", "pcg_sa_geom"):
        sys.modules.pop(m, None)
    import pcg_sa_geom as G
    import pcg_sa_shots as S
    stage, k = int(args["stage"]), int(args.get("pass", 1))
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    (x0, y0, _), (x1, y1, _) = town_layout.city_bbox()
    center, radius = [(x0 + x1) / 2, (y0 + y1) / 2, 0.0], 0.5 * max(x1 - x0, y1 - y0)
    loc, rot = G.orbit_camera(center, radius, -35, 38, 2.2, min_height=radius * 0.6)
    les.set_level_viewport_camera_info(unreal.Vector(*loc), unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]),
                                       les.get_active_viewport_config_key())
    info = S.fire(SHOT % (stage, stages.name(stage), k), les)
    data = _load(_pass_file(k), {})
    data.setdefault(str(stage), {})["shot"] = info.get("claimed")
    if "record" in data[str(stage)]:
        data[str(stage)]["params"] = data[str(stage)]["record"].get("params", {})
    _save(_pass_file(k), data)
    return {"fired": info}


OVERVIEWS = {"top": (0, 85, 2.0), "street": (-60, 8, 0.6), "wide": (20, 28, 3.0)}


def phase_overview(args):
    from pypcg.profiles import town_layout
    if _PY not in sys.path:
        sys.path.insert(0, _PY)
    for m in ("pcg_sa_shots", "pcg_sa_geom"):
        sys.modules.pop(m, None)
    import pcg_sa_geom as G
    import pcg_sa_shots as S
    az, elev, mult = OVERVIEWS[args["view"]]
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    (x0, y0, _), (x1, y1, _) = town_layout.city_bbox()
    center, radius = [(x0 + x1) / 2, (y0 + y1) / 2, 0.0], 0.5 * max(x1 - x0, y1 - y0)
    loc, rot = G.orbit_camera(center, radius, az, elev, mult, min_height=1500.0)
    les.set_level_viewport_camera_info(unreal.Vector(*loc), unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]),
                                       les.get_active_viewport_config_key())
    return S.fire("pt_overview_%s.png" % args["view"], les)
```

and replace the `PHASES` line with:

```python
PHASES = {"assign": lambda a: phase_assign(), "reset": phase_reset, "gen": phase_gen,
          "read": phase_read, "shot": phase_shot, "overview": phase_overview}
```

- [ ] **Step 4: Prepare** — editor on `L_PyTown`; run `Content/Python/tl_editor_no_throttle.py` once (a backgrounded editor stalls screenshots); `pypcg_town.py {"phase": "reset"}`.

- [ ] **Step 5: Run the 18 stages, pass 1.** For s = 1..18, three calls each, strictly in order:
  1. `{"phase": "gen", "stage": s}`
  2. `{"phase": "read", "stage": s, "pass": 1}` — if `generated` is false, repeat `gen` once then `read` (trap 38). If `status` is `fail`, **stop**: read `failures`. Upstream/bbox failures are reference problems (check `town_bindings.json` and the upstream volume); tag/instance failures are layout problems (adjust `town_layout.py`, rerun Task 25 Steps 3/6 and Task 26 Step 4, then `reset` and restart from stage 1). Fix the cause, never the rule. `unmeasured` (stage 1 only) is acceptable; say so in the report.
  3. `{"phase": "shot", "stage": s, "pass": 1}`. The capture lands 1–2 minutes later (trap 31); the next `shot` call lists what has landed.
  If stage 15 fails `meshes_all`, a tower ring vanished: apply the fallback — set `TOWER_HALF = 8000` in `town_layout.py` and `RectWidth`/`RectLength` = 16000 in `town.COMPONENT_OVERRIDES`, rerun Task 25 Step 6 and Task 26 Steps 2 and 4, `reset`, restart from stage 1. Record the fallback.

- [ ] **Step 6: Three overview shots** — one call each for `{"phase": "overview", "view": "top"}`, `"street"`, `"wide"`. Wait ~2 minutes, then confirm all 18 `pt_stage_*_p1.png` and the 3 `pt_overview_*.png` exist under `Saved/Screenshots/WindowsEditor/` and are over 50 KB (`pcg_sa_shots.promote_variants()` renames any `_rN` variant on the next capture call).

- [ ] **Step 7: Commit**

```bash
git add Content/Python/pypcg/town_checks.py Tools/pypcg/tests/test_town_checks.py Content/Python/pypcg_town.py
git commit -m "Run the 18 stages in the town with per-stage acceptance checks" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 28: Pass 2, the census, the report and git tracking

**Files:**
- Modify: `Content/Python/pypcg_town.py` (phase `finish`)
- Create: `Tools/pypcg/town_manifest.py`, `Tools/pypcg/tests/test_town_manifest.py`
- Create (generated): `Tools/data/pypcg_town_census.json`, `docs/pypcg-town-report.html`
- Modify: `.gitignore` (generated files over 95 MB, by path)

**Interfaces — Produces:** `town_manifest.build(census, shots_dir) -> manifest` in the shape `Tools/build_pcg_stage_report.py` reads.

- [ ] **Step 1: Add `finish` to `pypcg_town.py`** — above `PHASES`:

```python
def phase_finish(args):
    from pypcg import stages, town_checks, v2
    p1, p2 = _load(_pass_file(1), {}), _load(_pass_file(2), {})
    rows, same_all = [], True
    for s in stages.STAGES:
        a, b = p1.get(str(s[0])), p2.get(str(s[0]))
        same = bool(a and b and v2.same(a["record"], b["record"]))
        same_all = same_all and same
        rows.append({"stage": s[0], "graph": s[1], "title": s[3],
                     "instances": a and a["record"]["instances"]["total"],
                     "instances_pass2": b and b["record"]["instances"]["total"],
                     "status": a and a["verdict"]["status"], "failures": a and a["verdict"]["failures"],
                     "notes": a and a["verdict"]["notes"], "params": a and a.get("params"),
                     "tags": a and sorted({t for it in a["record"]["items"] for t in it["tags"] if ":" not in t}),
                     "meshes": a and len(a["record"]["instances"]["per_mesh"]), "shot": a and a.get("shot"),
                     "deterministic": same})
    same_all = same_all and plaus["failures"] == []
    census = {"_level": "/Game/PyPCG/L_PyTown", "_note": "pass 1 numbers; deterministic = pass 2 per-mesh counts equal pass 1",
              "all_ok": all(r["status"] in ("ok", "unmeasured") for r in rows), "deterministic": same_all, "stages": rows}
    _save(os.path.join(_REPO, "Tools", "data", "pypcg_town_census.json"), census)
    saved = False
    if census["all_ok"] and same_all and not args.get("dry_run"):
        saved = bool(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level())
    return {"all_ok": census["all_ok"], "deterministic": same_all, "saved": saved,
            "plausibility": plaus, "rows": [{k: r[k] for k in ("stage", "graph", "instances", "instances_pass2",
                                                               "status", "deterministic")} for r in rows]}
```

with, just above it:

```python
def _plausibility():
    """spec 5.2: compare the town's densities with the official city's, from the V2 records of stages 6
    and 11 (the official city's area and building count) and 6/7 (its road length)."""
    from pypcg import town_checks
    d = os.path.join(_REPO, "Saved", "Reports", "v2")
    official_area = sum(it["area_m2"] for it in _load(os.path.join(d, "s06", "official.json"), {"items": []})["items"])
    official_roads = sum(it["length_m"] for it in _load(os.path.join(d, "s07", "official.json"), {"items": []})["items"])
    official_bldgs = sum(1 for it in _load(os.path.join(d, "s11", "official.json"), {"items": []})["items"])
    p1 = _load(_pass_file(1), {})
    town_area = sum(it["area_m2"] for it in p1.get("6", {}).get("record", {"items": []})["items"])
    town_bldgs = sum(1 for it in p1.get("11", {}).get("record", {"items": []})["items"])
    town_roads = sum(it["length_m"] for it in p1.get("7", {}).get("record", {"items": []})["items"])
    return {"failures": town_checks.plausibility(
        {"area_m2": town_area, "buildings": town_bldgs, "road_m": town_roads},
        {"area_m2": official_area, "buildings": official_bldgs, "road_m": official_roads}),
        "town": {"area_m2": town_area, "buildings": town_bldgs, "road_m": town_roads},
        "official": {"area_m2": official_area, "buildings": official_bldgs, "road_m": official_roads}}
```

Place `plaus = _plausibility()` as the first line of `phase_finish`.

- [ ] **Step 2: Write `Tools/pypcg/tests/test_town_manifest.py`**

```python
import town_manifest


def census():
    return {"_level": "/Game/PyPCG/L_PyTown", "stages": [
        {"stage": 1, "graph": "PCG_1_1_Terrain", "title": "地形底座", "instances": 0, "status": "unmeasured",
         "notes": ["terrain heights not measurable; see the screenshot"], "params": {"CityFlatness": 0.6},
         "shot": "pt_stage_01_PCG_1_1_Terrain_p1.png"},
        {"stage": 11, "graph": "PCG_3_3_1_Buildings", "title": "建筑", "instances": 1234, "status": "ok",
         "notes": [], "params": {"ComplexBuildingShapes": True}, "shot": "pt_stage_11_PCG_3_3_1_Buildings_p1.png"}]}


def test_manifest_shapes_stages_for_the_report(tmp_path):
    (tmp_path / "pt_stage_11_PCG_3_3_1_Buildings_p1.png").write_bytes(b"x")
    m = town_manifest.build(census(), str(tmp_path))
    assert m["level"] == "/Game/PyPCG/L_PyTown" and len(m["stages"]) == 2
    s1, s11 = m["stages"]
    assert s1["metrics"]["status"] == "empty" and "terrain" in s1["notes"] and "CityFlatness" in s1["notes"]
    assert s11["metrics"] == {"instances": 1234, "debug_instances": 0, "status": "ok"}
    assert s11["shots"][0]["kind"] == "geometry" and s11["shots"][0]["path"].endswith("_p1.png")
    assert s1["shots"][0].get("img_missing")
```

- [ ] **Step 3: Write `Tools/pypcg/town_manifest.py`**

```python
#!/usr/bin/env python
"""Town census + screenshots -> the manifest Tools/build_pcg_stage_report.py renders.

    C:/Python314/python.exe Tools/pypcg/town_manifest.py --out Saved/Reports/pypcg_town_manifest.json
    C:/Python314/python.exe Tools/build_pcg_stage_report.py --manifest Saved/Reports/pypcg_town_manifest.json --out docs/pypcg-town-report.html

Each stage's notes carry its key parameters (spec 5.2.5), so a reader can retune a step and rerun from it.
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_ONLY = (1, 4, 5, 6, 9)


def _params(params):
    if not params:
        return ""
    return "; ".join("%s=%s" % (k, json.dumps(v)) for k, v in sorted(params.items()))


def build(census, shots_dir):
    stages = []
    for r in census["stages"]:
        path = os.path.join(shots_dir, r["shot"]) if r.get("shot") else ""
        shot = {"kind": "geometry", "path": path}
        if not path or not os.path.exists(path):
            shot["img_missing"] = "未捕获"
        status = "ok" if r["instances"] else ("empty" if r["stage"] in DATA_ONLY else "missing")
        if r.get("status") == "unmeasured":
            status = "empty"
        notes = "; ".join(r.get("notes") or [])
        if r["stage"] in DATA_ONLY and not r["instances"]:
            notes = (notes + "; " if notes else "") + "数据阶段：产出数据，几何与前一阶段相同。"
        if r.get("params"):
            notes = (notes + "; " if notes else "") + "参数：" + _params(r["params"])
        stages.append({"n": r["stage"], "graph": r["graph"], "label": r.get("title", ""), "shots": [shot],
                       "metrics": {"instances": r["instances"], "debug_instances": 0, "status": status},
                       "notes": notes})
    return {"title": "PyPCG 小城镇 · 18 步", "level": census["_level"],
            "subtitle": "每张 City Sample PCG 图的计算节点都已换成一个 Python 脚本，只留参数节点与引擎生成节点；"
                        "这 18 张瘦身图按飞书文档的 18 步顺序在 1 km 小镇里逐步生成，每步一张累计几何截图。",
            "footer": "生成的 Actor 中超过 GitHub 100 MB 单文件上限的未入库（见 .gitignore）；"
                      "pypcg_town.py 可按顺序重新生成。",
            "stages": stages}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default=os.path.join(REPO, "Tools", "data", "pypcg_town_census.json"))
    ap.add_argument("--shots", default=os.path.join(REPO, "Saved", "Screenshots", "WindowsEditor"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.census, encoding="utf-8") as fh:
        manifest = build(json.load(fh), a.shots)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)
    print("stages", len(manifest["stages"]), "missing shots",
          sum(1 for s in manifest["stages"] if s["shots"][0].get("img_missing")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Pass 2.** `{"phase": "reset"}`, then for s = 1..18: `{"phase": "gen", "stage": s}` and next call `{"phase": "read", "stage": s, "pass": 2}` (no screenshots). Every verdict must again be `ok` (or `unmeasured` for stage 1).

- [ ] **Step 5: Finish** — `{"phase": "finish"}`. Expected `all_ok: true`, `deterministic: true`, `saved: true`, `plausibility.failures: []`. If `deterministic` is false for a stage, report that stage and its two counts before going on (do not save).

- [ ] **Step 6: Build the report**

```bash
C:/Python314/python.exe Tools/pypcg/town_manifest.py --out Saved/Reports/pypcg_town_manifest.json
C:/Python314/python.exe Tools/build_pcg_stage_report.py --manifest Saved/Reports/pypcg_town_manifest.json --out docs/pypcg-town-report.html
```

Expected `stages 18 missing shots 0`. Look at every stage picture yourself before claiming a stage is right.

- [ ] **Step 7: Exclude generated files over GitHub's limit**

```bash
find Content/__ExternalActors__/PyPCG Content/__ExternalObjects__/PyPCG -type f -size +95M -printf "%s %p\n"
```

For each, add its exact path to `.gitignore`:

```
# PyPCG town (Task 28): generated actor packages over GitHub's 100 MB per-file limit. Reproduce with
# pypcg_town.py reset + gen 1..18 in order (docs/pypcg-guide.md).
/Content/__ExternalActors__/PyPCG/L_PyTown/<path>.uasset
```

- [ ] **Step 8: Commit**

```bash
git add Content/Python/pypcg_town.py Tools/pypcg/town_manifest.py Tools/pypcg/tests/test_town_manifest.py Tools/data/pypcg_town_census.json docs/pypcg-town-report.html .gitignore Content/PyPCG/L_PyTown.umap Content/__ExternalActors__/PyPCG Content/__ExternalObjects__/PyPCG
git commit -m "Generate the PyPCG town through all 18 stages, twice, and record the result" -m "Both passes give identical per-mesh counts; every stage passes its acceptance check." -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Phase P8 — Wrap-up

### Task 29: The guide, the skill, the regressions and the PR

**Files:** create `docs/pypcg-guide.md`; modify `.claude/skills/city-sample-pcg-city-builder/SKILL.md` and `references/traps.md`, `CLAUDE.md`.

- [ ] **Step 1: Write `docs/pypcg-guide.md`** (Chinese, like the repo's other docs), with real commands from this plan.

  Also update the spec `docs/superpowers/specs/2026-10-15-pypcg-python-nodes-design.md`: in §2.4 replace the
  estimated per-stage counts and totals with the measured ones from `docs/pypcg/stages/sNN-brief.md`
  (2026-10-15: 109 generation, 69 scene reads, 1000 Python, 175 dropped, 30 carriers), and note in §2.2 that
  the stage signature is `run(inputs, params, ctx)` (ruling N1) and in §3 that V2 ignores tags containing `:`
  (ruling N3) and skips count and area for tags under 5 items (ruling N10). Structure the guide as:
  1. 是什么：18 张图 = `Content/Python/pypcg/stages/sNN_*.py`（纯 Python，无 unreal）+ `pypcg/graphs/sNN_*.py`（瘦身图描述）；资产由 `pypcg_build_slim.py` 生成。
  2. 改一张图的流程：改 stage 或 graph 文件 → `pytest Tools/pypcg/tests -q` → `pypcg_build_slim.py {"stages": [N]}`（`diffs: 0`）→ 在 V2 里验证。
  3. 加一个参数：`PARAMS` 加一行 + tooltip → 重建瘦身图 → 组件上可覆写。
  4. DSL 速查：`SlimGraph`、`p()`、`python()`、`keep()`、`actor_by_tag()`、`ref()`、`self_point()`、`official_param()`、`out()`，各一行示例。
  5. 移植一张新图：`port_brief.py N` → 算法说明 → 测试 → stage → graph → V2（本计划的移植协议）。
  6. V2 与阈值：命令序列、判据、`v2_thresholds.json` 与 `docs/pypcg-v2-thresholds.md` 的用法。
  7. 小镇：`town_layout.py` 改布局 → `pypcg_town_level.py layout` → `pypcg_town.py assign` → 18 步 → 报告。
  8. C++ 插件 13 个函数一句话说明；改插件需关两个编辑器重编译。
  9. 已知限制：Python 节点只在编辑器、不缓存；`PCGPythonInterop` 是 Beta；生成 Actor 超 100 MB 不入库；逐节点草稿在 `Tools/pypcg/reference_drafts/`。

- [ ] **Step 2: Update the skill.** In `SKILL.md`, replace the路线 D section with a pointer to `docs/pypcg-guide.md` and this rule: change a stage graph by editing its `.py`, never in the graph editor (the asset is regenerated). In `references/traps.md`, add a numbered section for what this plan measured, at least: an unwired dynamic pin on the Python node culls the whole node; `regenerate_in_editor` off is what keeps a generation from cascading; what `k2_sample_point` returns; the `Point.MetadataEntry` route for Name attributes; that `pp` (percentage points) and item-based ratios (`Ratio_Plaza_vs_Trees`) are not area ratios.

- [ ] **Step 3: Regressions**
  - `C:/Python314/python.exe Tools/pypcg/baseline.py check` → `0 changed` (the 745 official assets are untouched).
  - `C:/Python314/python.exe -m pytest Tools/pypcg/tests -q` → all pass.
  - Relaunch into `/Game/ThirdPerson/Lvl_ThirdPerson`, run `pcg_postmigration_regression.py` → the 3×3 area still reports 41 instances.
  - Relaunch into `/Game/Map/Lvl_TL_Showcase`, run `tl_showcase_read.py` → 1,562 module instances.
  - Headless C++ tests → 9 × `Result={Success}`, exit 0.
  - The old pipeline: relaunch into `/CitySamplePCG/Levels/L_CitySamplePCG_Demo` and confirm `pcg_sa_census_cmp.py` still matches the shipped census (nothing in P0–P8 wrote to a shipped asset).

- [ ] **Step 4: Update `CLAUDE.md`.** Under "Driving the editor", add a **PyPCG** paragraph: `Content/Python/pypcg/` (stage modules, graph descriptions, host, checks, V2, census), `Content/Python/pypcg_build_slim.py`, `pypcg_compare_stage.py`, `pypcg_v1_editor.py`, `pypcg_town*.py`; that `PyPCGTools` is a project plugin (Editor module) with 13 functions; that `PCGPythonInterop` is an enabled engine plugin; and that `/Game/PyPCG/Slim|Town|Probe` assets are generated from the stage files. In Tests, list the three suites (pypcg pytest, PyPCGTools automation, MCP server).

- [ ] **Step 5: Update memory.** Rewrite `C:\Users\JianjunChi\.claude\projects\E--PCG-Claude\memory\pypcg-18-stage-town.md` with the final state: the branch and commit range, the 18 slim graphs with their node counts, the V2/V1/V3 results, the town numbers, the fallbacks that were applied, and the files excluded from git. Keep its `MEMORY.md` line accurate.

- [ ] **Step 6: Commit**

```bash
git add docs/pypcg-guide.md .claude/skills/city-sample-pcg-city-builder CLAUDE.md
git commit -m "Document PyPCG and record what it taught in the skill" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 7: Ask the user** whether to push `pypcg-18-stage-town` and open a PR into `main` (main requires a PR). Only on a yes: `git push -u origin pypcg-18-stage-town`, then `gh pr create --base main --title "PyPCG: one Python node per City Sample stage graph, and an 18-stage town" --body-file <file>` with a body listing the slim-node counts, the V2/V1/V3 results, the town census table, the excluded files, and ending with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Then follow the ccd_pr instructions (`get_status`, bind if needed, offer Auto-fix).
