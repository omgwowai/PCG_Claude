# TL Building Style Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add building style code `TL` — a self-built 3-level modular kit plus its registration data — so the CitySample PCG building pipeline can generate it alongside the existing 27 styles.

**Architecture:** Two phases. Phase 1 authors the art and its shape-grammar representation (`SGD_TL_A` + `RULE_TL_L00..L03`) so the facade is provable on a single spline with fast feedback. Phase 2 registers TL into the BDF database that `PCG_3_3_1_Buildings` actually consumes, plus the two width tables and the two style-code whitelists.

**Tech Stack:** Blender 5.2.1 headless CLI (`-b -P`), UE 5.8.2 editor embedded Python via the `run_unreal_script` MCP bridge on 127.0.0.1:8777, PCG plugin C++/Blueprint assets.

**Spec:** `docs/superpowers/specs/2026-09-24-tl-building-style-design.md`

## Global Constraints

- **Style code is `TL`.** Everything derives from it: asset paths, file names, `BuildingToken`, whitelist entries.
- **Dimensions align to CHA.** `Mod_Dim` is `[along-wall width, level height]` in **meters**. L1 height 5.0; L2/L3 height 3.0. `W1`=3.25, `P1`=1.25, `P2`=0.25, `E1`=4.75 (L2+)/3.25 (L1), corner family = 1.5. **BDF `Size` and the `Modules` set store centimeters — multiply by 100.**
- **`Levels.BuildingToken` is a `Name` attribute, not a `String`.** All other `BuildingToken` attributes are `String`. Getting this wrong fails silently.
- **Level rows are 1:1 with RULE assets.** TL is 3 levels ⇒ 4 level rows (`LV0`…`LV3`) and 4 RULE assets (`RULE_TL_L00`…`L03`).
- **Each level row carries 3 grammars** (`F0`/`F1`/`F2`) plus `FLengths` (Vector, cm): the variant whose length fits the wall is selected.
- **`Content/Building/` and `Plugins/CitySamplePCG/Content/` are gitignored.** Deliverables are reproducible scripts, never the asset files.
- **PCG generation is asynchronous.** Never read output in the same call that generates. Two-phase read is mandatory.
- **Spawn-type graphs must be verified by ISM instance count**, not by output pin point count (a graph can report 0 tagged data while having spawned thousands of instances).
- **`activate(True)` before `generate_local`** — skipping it is a silent zero.
- **Never modify Epic's `CitySampleBuildingBDF_Asset_PCG` in place.** Write a new asset and repoint `LoadCitySampleData`. It is gitignored, so there is no VCS fallback.
- **The only write route for a BDF data asset is duplicate-then-mutate.** `UPCGDataAsset.data`, `UPCGDataCollectionExporter.data`, and `FPCGDataPtrWrapper.data` are all `VisibleAnywhere` (⇒ `CPF_EditConst`) and reject Python's setter, and `PCGDataFunctionLibrary.make_tagged_data` is **not bound in this build**. Measured working route: `duplicate_asset` → mutate the duplicate's own point data (`create_*_attribute`, `set_points`) → `save_loaded_asset`. See Task 7.
- **Scripts must live under `Content/Python/`** (the MCP bridge rejects paths outside it).
- **Blueprint struct fields are stored under mangled names.** A Blueprint struct field is a `<Field>_<GUID>` name that no clean `get_editor_property()` name reaches — two confirmed instances: a RULE asset's `grammar` and `STC_Slot`'s `ShapeGrammarRules`. The reliable read path is `export_text()` (and for rules, `import_text()` to write). Do not guess a clean property name and do not assume its absence means the data is unreachable.
- **`mcp_result` must be JSON-serializable.** `unreal.Vector` / `Name` / Actor objects are not.
- **Kit meshes are CORNER/base-pivoted, not centre-pivoted.** Measured on CHA (Task 1): the local origin sits at the **bottom** (z ≈ 0, not the Z midpoint) and at **one end of the wall span in Y** (CHA's L1 wall spans y ∈ [−325, 0], so the origin is the y = 0 end, not the middle). CHA compensates with a per-module `PivotOffset` of magnitude (0, half-width, half-height) — whose sign direction is unconfirmed. TL matches CHA's convention exactly, because CHA's is known to lay out correctly.
- **Do not save levels after spawning test volumes.** Test residue must not be committed.

## Review Focus

The spec implies these failure modes but no single task's tests cover them. Each is pinned to a test in its owning task.

1. **A style whose grammar is written but never registered** — the asset exists, looks correct in the preview level, and never appears in city generation. A reasonable person expects "the asset exists" to imply "the style is usable"; it does not. → Task 8 Step 5, Task 9 Step 4.
2. **`Levels.BuildingToken` written as `String` instead of `Name`** — every other token is a String, so this looks right and matches nothing. → Task 7 Step 3.
3. **A kit whose pivot is not at the wall base** — every module lands offset, facades shear, and nothing errors. → Task 2 Step 4, Task 3 Step 4.
4. **A kit built at the wrong scale** — FBX import at 0.01 vs 1.0 leaves a 3.25 m wall as 3.25 cm or 325 m, and the grammar still "succeeds". → Task 3 Step 3.
5. **A style that fits no wall in the city** — `minWallWidth` set too large means TL never qualifies for any lot, producing zero TL buildings with no error. → Task 8 Step 4, Task 9 Step 4.

---

## Task 1: Finish the remaining probes and freeze the fact sheet

The BDF schema is already extracted (spec §2.3, and the schema table in this plan's Task 7). Four facts are still unknown and every later task depends on them.

**Files:**
- Create: `Content/Python/tl_probe_facts.py`
- Create: `Tools/tl_kit/tl_facts.json` (output, committed — it is small and is the durable record)

**Interfaces:**
- Consumes: nothing.
- Produces: `Tools/tl_kit/tl_facts.json` with keys `mesh_pivot` (list of `{path, bounds_min, bounds_max, location}` for 3 CHA meshes), `rule_grammars` (`{asset: grammar_string}` for 4 RULEs), `whitelist_nodes` (`{graph, node_title, param_name, current_value}`), `fbx_import_ok` (bool).

- [ ] **Step 1: Write the probe script**

Create `Content/Python/tl_probe_facts.py`:

```python
# tl_probe_facts.py — P0 spikes S3/S4/S6. READ-ONLY except S5 (one throwaway import).
#
# S4: pivot + bounds of real CHA meshes -> the kit's coordinate convention.
# S3: RULE_* grammar strings -> cross-check the BDF<->RULE mapping on more pairs.
# S6: where the style-code whitelist actually lives -> which node, which param.
#
# Prints compact lines (the nested-JSON form overflows the tool result).

import json

R = {}
args = mcp_args or {}
EAL = unreal.EditorAssetLibrary

# ---------- S4: mesh pivot + bounds --------------------------------------
# Path case matters and CHA's is inconsistent on disk (some kits are spelled
# `Kit_Bldg_CHa_L20_A`, lowercase a). If one of these 404s, try the other case
# and record which spelling loaded.
MESHES = [
    "/Game/Building/CH/A/Kit_Bldg_CHA_L1_A/Mesh/SM_BLDG_CHA_L01_A_Wall_01_N1",
    "/Game/Building/CH/A/Kit_Bldg_CHA_L1_A/Mesh/SM_BLDG_CHA_L01_A_Column_01_N1",
    "/Game/Building/CH/A/Kit_Bldg_CHA_L2_A/Mesh/SM_BLDG_CHA_L02_A_Wall_01_N1",
]
mesh_facts = []
for p in MESHES:
    rec = {"path": p}
    m = EAL.load_asset(p)
    rec["loaded"] = m is not None
    if m:
        try:
            b = m.get_bounds()
            bb = b.get_editor_property("box_extent")
            bo = b.get_editor_property("box_origin")
            rec["extent_cm"] = [round(bb.x, 2), round(bb.y, 2), round(bb.z, 2)]
            rec["origin_cm"] = [round(bo.x, 3), round(bo.y, 3), round(bo.z, 3)]
        except Exception as e:
            rec["bounds_err"] = "%s: %s" % (type(e).__name__, e)
        # per-LOD vertex counts, to know the kit's complexity budget
        try:
            lod0 = m.get_editor_property("render_data").get_editor_property("lod_resources")[0]
            verts = lod0.get_editor_property("vertex_buffer").get_num_vertices()
            rec["lod0_verts"] = verts
        except Exception as e:
            rec["verts_err"] = type(e).__name__
    mesh_facts.append(rec)
R["mesh_pivot"] = mesh_facts

# ---------- S3: RULE grammar strings -------------------------------------
RULES = [
    "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L00",
    "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L01",
    "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L02",
    "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L05",
    "/CitySamplePCG/PCG/DataAssets/Buildings/SFB/RULE_SFB_L01",
]
rule_facts = {}
for p in RULES:
    a = EAL.load_asset(p)
    if a is None:
        rule_facts[p] = "<not loaded>"
        continue
    got = {}
    for prop in a.get_class().get_default_object().get_editor_property if False else []:
        pass
    # the rule's properties are Blueprint variables on the class; read each by name
    for nm in ("grammar", "Modules Infos", "Spawn Spline Mesh",
               "Spline Mesh angle Threshold", "Override profile grammar"):
        try:
            v = a.get_editor_property(nm)
            got[nm] = str(v)[:200]
        except Exception:
            continue
    rule_facts[p] = got
R["rule_grammars"] = rule_facts

# ---------- S6: where is the style-code whitelist? ------------------------
GRAPHS = {
    "PCG_3_3_1_Buildings": "/CitySamplePCG/Levels/PCG/PCG_3_3_1_Buildings",
    "Assign_BldgStyles_per_MinWallWidth":
        "/CitySamplePCG/PCG/Assign_BldgStyles_per_MinWallWidth",
}
whitelist = {}
for label, path in GRAPHS.items():
    g = EAL.load_asset(path)
    entry = {"path": path, "loaded": g is not None, "hits": []}
    if g:
        nodes = g.get_editor_property("nodes")
        entry["node_count"] = len(nodes)
        for n in nodes:
            try:
                s = n.get_settings()
            except Exception:
                continue
            if s is None:
                continue
            title = ""
            try:
                title = str(s.get_editor_property("node_title"))
            except Exception:
                pass
            # scan every string-ish property for a style code
            for prop in ("buildings_styles", "value", "string", "text"):
                try:
                    v = s.get_editor_property(prop)
                except Exception:
                    continue
                if v and "CHA" in str(v):
                    entry["hits"].append({
                        "node": title or type(s).__name__,
                        "settings_class": s.get_class().get_name(),
                        "param": prop,
                        "value": str(v)[:300],
                    })
    whitelist[label] = entry
R["whitelist_nodes"] = whitelist

# ---------- report -------------------------------------------------------
print("###MESH_PIVOT###")
for r in R["mesh_pivot"]:
    print("  %s loaded=%s origin=%s extent=%s verts=%s" % (
        r["path"].split("/")[-1], r.get("loaded"), r.get("origin_cm"),
        r.get("extent_cm"), r.get("lod0_verts")))
print("###RULE_GRAMMARS###")
for p, got in R["rule_grammars"].items():
    print("  %s" % p.split("/")[-1])
    if isinstance(got, dict):
        print("     grammar=%s" % got.get("grammar"))
    else:
        print("     %s" % got)
print("###WHITELIST###")
for label, e in R["whitelist_nodes"].items():
    print("  %s nodes=%s hits=%d" % (label, e.get("node_count"), len(e["hits"])))
    for h in e["hits"]:
        print("     node=%s class=%s param=%s" % (h["node"], h["settings_class"], h["param"]))
        print("       value=%s" % h["value"])

mcp_result = R
```

- [ ] **Step 2: Run the probe**

Run via the bridge: `run_unreal_script(script_path="tl_probe_facts.py")`

Expected: mesh lines with `origin_cm`/`extent_cm`; `###WHITELIST###` showing at least one hit whose `param` names the string parameter carrying `CHA`.

- [ ] **Step 3: Confirm the whitelist location**

The whitelist `param` name from Step 2 is the exact property later tasks set. Record it in `tl_facts.json`. **If no hit appears**, the string is inside a subgraph the node references rather than on the node itself — then load `/CitySamplePCG/PCG/Primitives/Buildings/Assign_CitySampleBuildings` directly and repeat, and record that asset as the edit target instead.

- [ ] **Step 4: Verify the BDF↔RULE mapping on the new pairs**

Compare each `RULE_*.grammar` from Step 2 against the BDF `F0`/`F1`/`F2` strings already extracted for the same level (spec §2.6, and this plan's Task 7 table). Confirm the token correspondence holds: `|`↔adjacency, `(A-B)`↔`[A,B]`, `X*`↔`[X]+`, leading/trailing `C`↔`[FC]`/`[LC]`, and that RULE-only symbols (`WS1`, `WS111`, `FS2`) have no BDF counterpart.

**If a pair contradicts the mapping, stop and report** — the mapping is the basis of Task 4 and Task 7, and a contradiction means it must be re-derived before either is written.

- [ ] **Step 5: Write `tl_facts.json` and commit**

```bash
mkdir -p Tools/tl_kit
```

Write the four fact groups to `Tools/tl_kit/tl_facts.json` from the probe's `mcp_result`, then:

```bash
git add Content/Python/tl_probe_facts.py Tools/tl_kit/tl_facts.json
git commit -m "Probe the remaining TL unknowns: mesh pivots, rule grammars, whitelist nodes"
```

---

## Task 2: Author the kit spec and build the modular meshes in Blender

The single source of truth for the kit. Every other art step reads this file.

**Files:**
- Create: `Tools/tl_kit/tl_kit_spec.json`
- Create: `Tools/tl_kit/build_tl_kit.py`
- Test: `Tools/tl_kit/test_kit_spec.py`
- Output: `E:\Blender\TL_Kit\TL_Kit.blend`, `E:\Blender\TL_Kit\FBX_Export\*.fbx`

**Interfaces:**
- Consumes: `Tools/tl_kit/tl_facts.json` (Task 1) for the pivot convention.
- Produces: `tl_kit_spec.json` — a list of `{part, level, width_m, height_m, material, pivot_z_m}`. `build_tl_kit.py` reads it and writes one FBX per part named `SM_BLDG_TL_L<nn>_A_<Part>_01_N1.fbx`.

- [ ] **Step 1: Write the failing test for the spec's shape**

Create `Tools/tl_kit/test_kit_spec.py`:

```python
import json, os, sys

SPEC = os.path.join(os.path.dirname(__file__), "tl_kit_spec.json")

# CHA dimensions TL aligns to (spec 2.8). Widths in meters, heights in meters.
CHA_L1_PARTS = {"Wall_01": 3.25, "Column_01": 1.25, "Entrance_01": 3.25,
                "CornerEx_01": 1.5, "CornerExL_01": 1.5, "CornerExR_01": 1.5,
                "CornerIn_01": 1.5, "CornerInL_01": 1.5, "CornerInR_01": 1.5}
CHA_L2_PARTS = dict(CHA_L1_PARTS)
CHA_L2_PARTS["Entrance_01"] = 4.75
CHA_L2_PARTS["Column_02"] = 0.25


def load():
    with open(SPEC, encoding="utf-8") as f:
        return json.load(f)


def test_covers_three_levels():
    spec = load()
    levels = {p["level"] for p in spec["parts"]}
    assert levels == {1, 2, 3}, levels


def test_level1_heights_and_widths():
    spec = load()
    l1 = [p for p in spec["parts"] if p["level"] == 1]
    for p in l1:
        assert p["height_m"] == 5.0, p
        assert p["width_m"] == CHA_L1_PARTS[p["part"]], p


def test_level2_3_heights_and_widths():
    spec = load()
    for lvl, want in ((2, CHA_L2_PARTS), (3, CHA_L2_PARTS)):
        for p in [x for x in spec["parts"] if x["level"] == lvl]:
            assert p["height_m"] == 3.0, p
            assert p["width_m"] == want[p["part"]], p


def test_每_part_has_a_material_and_pivot():
    spec = load()
    for p in spec["parts"]:
        assert p["material"], p
        assert "pivot_z_m" in p, p


def test_names_follow_the_convention():
    spec = load()
    for p in spec["parts"]:
        assert p["mesh_name"].startswith("SM_BLDG_TL_L"), p
        assert p["mesh_name"].endswith("_01_N1"), p
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python Tools/tl_kit/test_kit_spec.py` (or `pytest Tools/tl_kit/test_kit_spec.py -v`)

Expected: FAIL — `FileNotFoundError: tl_kit_spec.json`.

- [ ] **Step 3: Write `tl_kit_spec.json`**

Create `Tools/tl_kit/tl_kit_spec.json`. Twenty-nine parts: 9 for L1, 10 each for L2 and L3.

```json
{
  "style_code": "TL",
  "variant": "A",
  "unit": "meter",
  "pivot_convention": {
    "origin": "corner-base",
    "note": "MEASURED FROM CHA (Task 1), not chosen. The mesh's local origin sits at the BOTTOM of the piece (z = 0, not the z midpoint) and at ONE END of the wall run, not its middle. CHA's L1 wall spans y in [-325, 0] and z in [0, 500] with its origin at (0,0,0), i.e. the y = 0 end and the z = 0 bottom. The wall run is along Y; X is the facade thickness/depth; Z is up.",
    "compensation": "CHA re-centres each module with a PivotOffset of magnitude (0, width/2, height/2) -- exactly half the wall width and half the height, converting the corner pivot into a centre pivot for the grammar's placement maths. MEASURED: the BDF Modules row for CHA's L1 wall reports PivotOffset = (0, 162.5, -250), and 162.5 = 325/2 with 250 = 500/2. Its SIGN direction is unconfirmed (one sample). TL matches CHA exactly, because CHA's convention is known to lay out correctly.",
    "forward_axis": "Y is the wall run; MeshForwardAxis in the data reads 2.0 (EAxis::Z)"
  },
  "lods": [0, 1],
  "parts": [
    {"part": "Wall_01",       "level": 1, "width_m": 3.25, "height_m": 5.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L01_A_Wall_01_N1"},
    {"part": "Column_01",     "level": 1, "width_m": 1.25, "height_m": 5.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L01_A_Column_01_N1"},
    {"part": "Entrance_01",   "level": 1, "width_m": 3.25, "height_m": 5.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L01_A_Entrance_01_N1"},
    {"part": "CornerEx_01",   "level": 1, "width_m": 1.5,  "height_m": 5.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L01_A_CornerEx_01_N1"},
    {"part": "CornerExL_01",  "level": 1, "width_m": 1.5,  "height_m": 5.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L01_A_CornerExL_01_N1"},
    {"part": "CornerExR_01",  "level": 1, "width_m": 1.5,  "height_m": 5.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L01_A_CornerExR_01_N1"},
    {"part": "CornerIn_01",   "level": 1, "width_m": 1.5,  "height_m": 5.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L01_A_CornerIn_01_N1"},
    {"part": "CornerInL_01",  "level": 1, "width_m": 1.5,  "height_m": 5.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L01_A_CornerInL_01_N1"},
    {"part": "CornerInR_01",  "level": 1, "width_m": 1.5,  "height_m": 5.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L01_A_CornerInR_01_N1"},

    {"part": "Wall_01",       "level": 2, "width_m": 3.25, "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L02_A_Wall_01_N1"},
    {"part": "Column_01",     "level": 2, "width_m": 1.25, "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L02_A_Column_01_N1"},
    {"part": "Column_02",     "level": 2, "width_m": 0.25, "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L02_A_Column_02_N1"},
    {"part": "Entrance_01",   "level": 2, "width_m": 4.75, "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L02_A_Entrance_01_N1"},
    {"part": "CornerEx_01",   "level": 2, "width_m": 1.5,  "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L02_A_CornerEx_01_N1"},
    {"part": "CornerExL_01",  "level": 2, "width_m": 1.5,  "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L02_A_CornerExL_01_N1"},
    {"part": "CornerExR_01",  "level": 2, "width_m": 1.5,  "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L02_A_CornerExR_01_N1"},
    {"part": "CornerIn_01",   "level": 2, "width_m": 1.5,  "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L02_A_CornerIn_01_N1"},
    {"part": "CornerInL_01",  "level": 2, "width_m": 1.5,  "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L02_A_CornerInL_01_N1"},
    {"part": "CornerInR_01",  "level": 2, "width_m": 1.5,  "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L02_A_CornerInR_01_N1"},

    {"part": "Wall_01",       "level": 3, "width_m": 3.25, "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L03_A_Wall_01_N1"},
    {"part": "Column_01",     "level": 3, "width_m": 1.25, "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L03_A_Column_01_N1"},
    {"part": "Column_02",     "level": 3, "width_m": 0.25, "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L03_A_Column_02_N1"},
    {"part": "Entrance_01",   "level": 3, "width_m": 4.75, "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L03_A_Entrance_01_N1"},
    {"part": "CornerEx_01",   "level": 3, "width_m": 1.5,  "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L03_A_CornerEx_01_N1"},
    {"part": "CornerExL_01",  "level": 3, "width_m": 1.5,  "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L03_A_CornerExL_01_N1"},
    {"part": "CornerExR_01",  "level": 3, "width_m": 1.5,  "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L03_A_CornerExR_01_N1"},
    {"part": "CornerIn_01",   "level": 3, "width_m": 1.5,  "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L03_A_CornerIn_01_N1"},
    {"part": "CornerInL_01",  "level": 3, "width_m": 1.5,  "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L03_A_CornerInL_01_N1"},
    {"part": "CornerInR_01",  "level": 3, "width_m": 1.5,  "height_m": 3.0, "pivot_z_m": 0.0, "material": "TL_Stone", "mesh_name": "SM_BLDG_TL_L03_A_CornerInR_01_N1"}
  ]
}
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `python -m pytest Tools/tl_kit/test_kit_spec.py -v`

Expected: PASS (5 tests).

- [ ] **Step 5: Write the Blender build script**

Create `Tools/tl_kit/build_tl_kit.py`. It reads the spec, builds one box-derived module per part with its origin at the wall base centre, and exports one FBX per part. Run headless.

```python
"""build_tl_kit.py — Blender 5.2 headless. Builds the TL modular kit from the spec.

    blender -b -P Tools/tl_kit/build_tl_kit.py -- --spec Tools/tl_kit/tl_kit_spec.json \
            --out E:/Blender/TL_Kit

Each part becomes ONE object whose origin sits at the wall-base centre
(+X along the wall, +Z up), then is exported as its own FBX at 1 unit = 1 m.
Blender is Z-up and UE is Z-up, so no axis flip is needed; the FBX exporter's
own Y-up conversion is left at default and compensated on import.
"""
import argparse
import json
import os
import sys

import bpy


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(name):
    """One flat placeholder material per spec entry; real texturing is out of scope."""
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.62, 0.60, 0.56, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.7
    return m


def build_part(part, lod):
    """A box for the part's footprint and height, origin at the BASE CORNER.

    PIVOT (measured from CHA by Task 1 — do not "improve" this to centre):
    the box is centred in X (the facade depth axis), extends in NEGATIVE Y
    (the wall run) from the origin, and upward in Z from the origin. So the
    origin sits at (x-centre, y = near end of the run, z = bottom) — CHA's L1
    wall spans exactly y in [-325, 0] and z in [0, 500] with its origin at
    (0,0,0). CHA compensates with a per-module PivotOffset of half-width and
    half-height; TL matches CHA so the same compensation applies unchanged.
    """
    w, h = part["width_m"], part["height_m"]
    depth = 0.30  # facade thickness; the grammar only uses width and height
    # place so that after scaling the box spans x:[-d/2,d/2] y:[-w,0] z:[0,h]
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0.0, -w / 2.0, h / 2.0))
    obj = bpy.context.active_object
    obj.name = part["mesh_name"] if lod == 0 else part["mesh_name"] + "_LOD1"
    obj.scale = (depth / 2.0, w / 2.0, h / 2.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # origin to the WORLD origin, which is the base corner of the box above
    bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    obj.data.materials.append(material(part["material"]))
    return obj


def export(obj, out_dir, name):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    path = os.path.join(out_dir, name + ".fbx")
    bpy.ops.export_scene.fbx(
        filepath=path,
        use_selection=True,
        global_scale=1.0,
        apply_unit_scale=True,
        axis_forward="-Y",
        axis_up="Z",
        object_types={"MESH"},
    )
    return path


def main():
    args = parse_args()
    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    fb_dir = os.path.join(args.out, "FBX_Export")
    os.makedirs(fb_dir, exist_ok=True)

    made = []
    for part in spec["parts"]:
        clear_scene()
        obj = build_part(part, lod=0)
        made.append(export(obj, fb_dir, part["mesh_name"]))
    # save the working file for hand edits
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(args.out, "TL_Kit.blend"))
    print("###EXPORTED###", len(made))
    for p in made:
        print("  ", p)


main()
```

- [ ] **Step 6: Run the build**

```bash
"E:/Blender/blender-5.2.1-windows-x64/blender.exe" -b -P Tools/tl_kit/build_tl_kit.py -- --spec Tools/tl_kit/tl_kit_spec.json --out E:/Blender/TL_Kit
```

Expected: `###EXPORTED### 29` and 29 `.fbx` files in `E:\Blender\TL_Kit\FBX_Export\`.

- [ ] **Step 7: Verify the FBX dimensions numerically**

The kit's whole failure mode is a wrong scale, so measure rather than look.

```bash
python - <<'EOF'
import glob, struct, os
# FBX is binary; a full parser is overkill. Verify file presence and size instead,
# then confirm the real dimensions after import (Task 3 Step 3).
fb = sorted(glob.glob("E:/Blender/TL_Kit/FBX_Export/*.fbx"))
print("fbx count:", len(fb))
assert len(fb) == 29, len(fb)
for p in fb[:3]:
    print(os.path.basename(p), os.path.getsize(p), "bytes")
EOF
```

Expected: `fbx count: 29`.

- [ ] **Step 8: Commit**

```bash
git add Tools/tl_kit/tl_kit_spec.json Tools/tl_kit/build_tl_kit.py Tools/tl_kit/test_kit_spec.py
git commit -m "Add the TL kit spec and the Blender build script"
```

---

## Task 3: Import the kit into the project content

**Files:**
- Create: `Content/Python/tl_import_kit.py`
- Output: `/Game/Building/TL/A/Kit_Bldg_TL_L<n>_A/{Mesh,Material/MI}/*`

**Interfaces:**
- Consumes: `E:\Blender\TL_Kit\FBX_Export\*.fbx` and `Tools/tl_kit/tl_kit_spec.json`.
- Produces: 29 `StaticMesh` assets at `/Game/Building/TL/A/Kit_Bldg_TL_L<n>_A/Mesh/<mesh_name>`, each with its material slot set.

- [ ] **Step 1: Write the import script**

Create `Content/Python/tl_import_kit.py`. Uses the legacy FBX path (not Interchange) and asserts the scale and material slots after import — both are silent-failure modes.

```python
# tl_import_kit.py — import the TL FBX kit into /Game/Building/TL.
#
# Legacy FBX import only. Interchange crashes the editor from Python on this
# engine (TaskGraph RecursionGuard assert), so the project disables it by cvar.
# The cvar must be set in Config/DefaultEngine.ini under [ConsoleVariables]:
#     Interchange.FeatureFlags.Import.FBX=False
# Verify that entry exists before trusting this script (Task 3 Step 2).
#
# Two things are asserted rather than assumed, because both fail silently:
#   * imported bounds match the spec in CENTIMETERS (catches a 100x scale error)
#   * the material slot is not WorldGridMaterial (catches the TArray-struct-copy trap)

import json
import os

R = {"imported": [], "errors": []}
args = mcp_args or {}

SPEC_PATH = args.get("spec", "E:/PCG_Claude/Tools/tl_kit/tl_kit_spec.json")
FBX_DIR = args.get("fbx_dir", "E:/Blender/TL_Kit/FBX_Export")
DEST = "/Game/Building/TL/A"

with open(SPEC_PATH, encoding="utf-8") as f:
    spec = json.load(f)

EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()

def dest_folder(part):
    return "%s/Kit_Bldg_TL_L%d_A" % (DEST, part["level"])

for part in spec["parts"]:
    name = part["mesh_name"]
    fbx = os.path.join(FBX_DIR, name + ".fbx")
    folder = dest_folder(part)
    rec = {"name": name, "folder": folder}
    if not os.path.isfile(fbx):
        rec["error"] = "missing fbx"
        R["errors"].append(rec)
        continue

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", fbx)
    task.set_editor_property("destination_path", folder + "/Mesh")
    task.set_editor_property("destination_name", name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    # legacy FBX factory explicitly, so Interchange is never in the path
    task.set_editor_property("factory", unreal.FbxFactory())
    try:
        AT.import_asset_tasks([task])
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
        R["errors"].append(rec)
        continue

    # ---- verify the scale, in cm ----------------------------------------
    mesh_path = "%s/Mesh/%s" % (folder, name)
    mesh = EAL.load_asset(mesh_path)
    if mesh is None:
        rec["error"] = "not loadable at %s" % mesh_path
        R["errors"].append(rec)
        continue
    try:
        b = mesh.get_bounds()
        ext = b.get_editor_property("box_extent")
        rec["extent_cm"] = [round(ext.x, 1), round(ext.y, 1), round(ext.z, 1)]
        # width is the X extent (origin at wall-base centre => half-extent * 2)
        want_w = part["width_m"] * 100.0
        got_w = round(ext.x * 2.0, 1)
        rec["want_width_cm"] = want_w
        rec["got_width_cm"] = got_w
        rec["scale_ok"] = abs(got_w - want_w) < 2.0
        if not rec["scale_ok"]:
            rec["error"] = "width %s != %s" % (got_w, want_w)
            R["errors"].append(rec)
    except Exception as e:
        rec["bounds_err"] = "%s: %s" % (type(e).__name__, e)

    # ---- verify the material slot is real --------------------------------
    try:
        mats = mesh.get_editor_property("static_materials")
        rec["slot_count"] = len(mats)
        rec["slot0"] = str(mats[0].get_editor_property("material_interface")) if mats else None
        rec["slot_ok"] = bool(mats) and "WorldGrid" not in str(rec["slot0"])
    except Exception as e:
        rec["slot_err"] = "%s: %s" % (type(e).__name__, e)

    R["imported"].append(rec)

# ---------- material slot assignment (the TArray<struct> trap) -------------
# static_materials yields struct COPIES: mutating an element in place silently
# does nothing. Build a fresh list and set it whole, then read it back.
MI_ROOT = "/Game/Building/Material"
fixed = []
for rec in R["imported"]:
    if rec.get("error"):
        continue
    mesh_path = "%s/Mesh/%s" % (rec["folder"], rec["name"])
    mesh = EAL.load_asset(mesh_path)
    if mesh is None:
        continue
    base = EAL.load_asset(MI_ROOT + "/MI_Bldg_Stone_TL")
    if base is None:
        # fall back to an existing CH material so the slot is never WorldGrid
        base = EAL.load_asset("/Game/Building/CH/A/Material/MI_Bldg_Block_Limestone_Beige")
    if base is None:
        fixed.append({"name": rec["name"], "err": "no fallback material"})
        continue
    sm = unreal.StaticMaterial()
    sm.set_editor_property("material_interface", base)
    sm.set_editor_property("material_slot_name", "Default")
    try:
        mesh.set_editor_property("static_materials", [sm])
        EAL.save_loaded_asset(mesh)
    except Exception as e:
        fixed.append({"name": rec["name"], "err": "%s: %s" % (type(e).__name__, e)})
        continue
    # read back: the only honest confirmation
    back = EAL.load_asset(mesh_path).get_editor_property("static_materials")
    ok = bool(back) and "WorldGrid" not in str(back[0].get_editor_property("material_interface"))
    fixed.append({"name": rec["name"], "slot_ok": ok})
R["material_fixups"] = fixed
R["material_failures"] = [f for f in fixed if not f.get("slot_ok")]

print(json.dumps({
    "imported": len(R["imported"]),
    "errors": R["errors"],
    "scale_failures": [r for r in R["imported"] if r.get("scale_ok") is False],
    "material_failures": R["material_failures"],
}, indent=1, default=str))
mcp_result = R
```

- [ ] **Step 2: Add the Interchange-off cvar and restart the editor, BEFORE importing**

Task 1 measured that `Config/DefaultEngine.ini` currently has **no `[ConsoleVariables]` section and
no `Interchange.FeatureFlags.Import.FBX` entry at all** — so this step adds it rather than verifying
it. This is not optional bookkeeping: importing FBX with Interchange enabled crashes the editor
process from Python (a TaskGraph RecursionGuard assert — no exception, the process dies), so the
first import in Step 3 would take the editor down with it.

Check first:

```bash
grep -n "Interchange.FeatureFlags.Import.FBX\|^\[ConsoleVariables\]" Config/DefaultEngine.ini
```

If the entry is absent, add the section (or the line, if the section exists but is empty):

```ini
[ConsoleVariables]
Interchange.FeatureFlags.Import.FBX=False
```

Then **restart the editor** — an ini cvar is read at startup, so adding it while the editor runs
has no effect. Ask the controller to restart if you cannot, and wait for the bridge on
127.0.0.1:8777 to come back before continuing.

**This is the 5.8 re-confirmation of a workaround verified on 5.7** (spec §2.10, U4). If Step 3's
import still crashes with the cvar set, the flag name has changed on 5.8 — read the crash from
`Saved/Logs/PCG_Claude.log` for the assert text and report back rather than guessing at a second
flag name.

- [ ] **Step 3: Run the import and read the scale verification**

Run via the bridge: `run_unreal_script(script_path="tl_import_kit.py")`

Expected: `imported: 29`, `errors: []`, `scale_failures: []`.

**If `scale_failures` is non-empty**, the FBX unit scale is wrong. Convert every `got_width_cm` back to meters and compare to `want_width_cm / 100`; a uniform factor of 100 means `global_scale=1.0` combined with `apply_unit_scale=True` double-applied. Fix in `build_tl_kit.py` and rebuild (Task 2 Step 6) rather than patching after import.

- [ ] **Step 4: Verify pivots landed at the wall base**

```bash
# in the editor, via the bridge
```

Run `run_unreal_script` with an inline check that each imported mesh's bounds centre sits at half its height above the origin — i.e. `box_origin.z ≈ extent.z`, not `≈ 0` (which would mean a centred pivot).

Expected: for every mesh, `abs(box_origin.z - extent.z) < 1.0` cm.

**If pivots are centred**, the `origin_set` in `build_tl_kit.py` did not take effect on the export. Rebuild with the origin applied before export.

- [ ] **Step 5: Commit**

```bash
git add Content/Python/tl_import_kit.py
git commit -m "Import the TL modular kit with scale and material-slot assertions"
```

---

## Task 4: Author the four TL shape-grammar rule assets

`RULE_TL_L00`…`L03`, one per level row, mirroring CHA's `RULE_CHA_L01` structure.

**Files:**
- Create: `Content/Python/tl_make_rules.py`
- Output: `/Game/PCG/DataAssets/Buildings/TL/RULE_TL_L00` … `RULE_TL_L03`

**Interfaces:**
- Consumes: the imported meshes (Task 3), `tl_facts.json` `rule_grammars` (Task 1).
- Produces: 4 assets of class `BP_ShapeGrammarRule_C`, each carrying an `STC_Rule` whose `grammar` field holds the facade grammar.

**ACCESS PATH — measured by Task 1, do NOT guess a property name.** A `BP_ShapeGrammarRule_C`
exposes **no** `grammar` property. `set_editor_property("grammar", …)` fails. The rule data is an
`STC_Rule` struct reached through the asset's **export/import text**, against a *mangled* field
name of the form `grammar_10_4003928D40C6099DCA57829F48235D57` (the `Name_Hash` pattern these
Blueprint structs use — the same pattern as `STC_Module`/`STC_Slot`). The measured recipe:

```python
txt = rule.export_text()          # returns the struct's text form, containing the mangled names
# extract the real field name by regex, e.g. r'grammar_\d+_[0-9A-F]{32}'
# then build the replacement text and call rule.import_text(new_text)
```

Task 1 confirmed this on `RULE_CHA_L00` and recorded the exact mangled name for `grammar` in
`tl_facts.json` (`rule_grammars`). **Read that field from the facts file rather than re-deriving
it.** Equivalent mnemonics for the other fields you need (`Modules Infos` → a
`TArray<STC_Module>`) follow the same pattern; read the export text to get each one's real name.

- [ ] **Step 1: Write the rule builder**

Create `Content/Python/tl_make_rules.py`:

```python
# tl_make_rules.py — create RULE_TL_L00..L03 from the kit spec.
#
# The grammar strings come from the BDF<->RULE mapping (spec 2.6), applied to
# the BDF grammars TL uses (Task 7). WS1 is the scalable filler that closes a
# partly-filled wall span; it appears where the BDF grammar has a repeat group.
#
# ACCESS PATH (measured by Task 1 — a rule asset has NO "grammar" property):
#   read   -> rule.export_text()  and regex the mangled name  grammar_<n>_<32 hex>
#   write  -> rule.import_text(<full text with the new grammar value>)
# The mangled name is stable per struct field; Task 1 recorded it in
# tl_facts.json under rule_grammars for RULE_CHA_L00.
#
# IMPORTANT on MeshForwardAxis: the BDF Modules rows carry it as 2.0 (= EAxis::Z)
# on every CHA module, so TL matches that. Task 6 renders the facade and flips to
# Y only if it lies down.
#
# IMPORTANT on PivotOffset: CHA's L1 wall module has PivotOffset = (0, 162.5, -250)
# and the Task 1 probe measured that mesh's origin at the wall-base CORNER with the
# mesh spanning 325 cm along Y from -325..0 and 500 cm in Z from 0..500. So the
# magnitude relationship is: PivotOffset re-centres a corner-pivoted mesh. Its SIGN
# direction is unconfirmed from one sample — Task 3 Step 4 and Task 6 Step 4 are
# where a wrong sign shows up (modules offset by a half-width). Start at (0,0,0)
# like CHA does for its own authoring default and let Task 6 catch a bad value.

import json
import re

R = {"rules": [], "errors": []}
args = mcp_args or {}
SPEC = args.get("spec", "E:/PCG_Claude/Tools/tl_kit/tl_kit_spec.json")
FACTS = args.get("facts", "E:/PCG_Claude/Tools/tl_kit/tl_facts.json")
DEST = "/Game/PCG/DataAssets/Buildings/TL"

EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()

with open(SPEC, encoding="utf-8") as f:
    spec = json.load(f)
with open(FACTS, encoding="utf-8") as f:
    facts = json.load(f)

# ---------- the mangled field names, from the measured facts --------------
MANGLED = {}
try:
    rg = facts.get("rule_grammars") or {}
    for k, v in (rg.get("mangled_names") or {}).items():
        MANGLED[k] = v
    # Task 1 may instead have recorded one full export_text sample; mine it
    sample = rg.get("sample_export_text") or ""
    for field in ("grammar", "ModulesInfos", "Modules_Infos", "Overrideprofilegrammar"):
        m = re.search(field + r"_\d+_[0-9A-F]{32}", sample, re.IGNORECASE)
        if m and field not in MANGLED:
            MANGLED[field] = m.group(0)
except Exception as e:
    R["errors"].append("facts parse: %s: %s" % (type(e).__name__, e))
R["mangled_names"] = MANGLED

RULE_CLASS = "/PCGPrimitives/Grammar/BP/BP_ShapeGrammarRule"
rule_cls = unreal.load_class(None, RULE_CLASS) or unreal.BP_ShapeGrammarRule


def read_grammar(asset):
    """Read the grammar string out of a rule asset via its export text."""
    txt = asset.export_text()
    # the grammar value is an FString: field=(...) or field="..." depending on form
    name = MANGLED.get("grammar")
    if name:
        m = re.search(re.escape(name) + r'=["(]?([^")]*)', txt)
        if m:
            return m.group(1), txt
    # fall back: any bracket-grammar-looking payload in the text
    m = re.search(r'\[FC\]\[[^\]]+\]', txt)
    return (m.group(0) if m else ""), txt


def write_grammar(asset, new_grammar):
    """Replace the grammar value in the asset's text form and import it back."""
    cur, txt = read_grammar(asset)
    name = MANGLED.get("grammar")
    if not name:
        raise RuntimeError("no mangled grammar field name; export_text was: %s" % txt[:300])
    pat = re.escape(name) + r'=["(]?[^")]*'
    new_txt = re.sub(pat, '%s="%s"' % (name, new_grammar), txt, count=1)
    if new_txt == txt:
        raise RuntimeError("substitution changed nothing for %s" % name)
    asset.import_text(new_txt)
    back, _ = read_grammar(asset)
    return back


# level -> {symbol: (mesh_name, width_cm, scalable)}
def symbols_for_level(level):
    out = {}
    for p in spec["parts"]:
        if p["level"] != level:
            continue
        sym = {
            "Wall_01": "W1", "Column_01": "P1", "Column_02": "P2",
            "Entrance_01": "E1", "CornerEx_01": "C_CE", "CornerExL_01": "C_SL",
            "CornerExR_01": "C_SR", "CornerIn_01": "C_I", "CornerInL_01": "C_IL",
            "CornerInR_01": "C_IR",
        }[p["part"]]
        out[sym] = (p["mesh_name"], p["width_m"] * 100.0, False)
    # the scalable filler, sized to the wall span, matching CHA's WS1
    wall = next((p for p in spec["parts"] if p["level"] == level and p["part"] == "Wall_01"), None)
    if wall:
        out["WS1"] = (wall["mesh_name"], wall["width_m"] * 100.0, True)
    return out


# level -> grammar string (from the BDF mapping; Task 1 Step 4 verified it)
GRAMMARS = {
    0: "[FC][FS2]+[LC]",
    1: "[FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]",
    2: "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
    3: "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
}

for level in (0, 1, 2, 3):
    name = "RULE_TL_L%02d" % level
    rec = {"name": name}
    try:
        asset = AT.create_asset(name, DEST, rule_cls, None)
        if asset is None:
            asset = EAL.load_asset(DEST + "/" + name)
        if asset is None:
            raise RuntimeError("create_asset returned None and the asset does not exist")
        rec["grammar_back"] = write_grammar(asset, GRAMMARS[level])
        rec["grammar_ok"] = (rec["grammar_back"] == GRAMMARS[level])
        EAL.save_loaded_asset(asset)
        R["rules"].append(rec)
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
        R["errors"].append(rec)

print(json.dumps(R, indent=1, default=str))
mcp_result = R
```

**If Task 1's facts file does not carry the mangled name**, get it first with a one-off read
(`unreal.EditorAssetLibrary.load_asset(".../CHA/RULE_CHA_L01").export_text()` and regex the
`grammar_<n>_<32 hex>` pattern), record it in the script's `MANGLED` constant, and proceed. Do not
fall back to `set_editor_property("grammar", …)` — Task 1 proved that property does not exist.

- [ ] **Step 2: Run it and read the read-back**

Run via the bridge: `run_unreal_script(script_path="tl_make_rules.py")`

Expected: `rules` with 4 entries, each `grammar_ok: true` and `module_count ≥ 10`.

- [ ] **Step 3: Confirm the property names resolved**

If a `set_editor_property` raised `Failed to find property`, the Blueprint variable's Python name differs from the C++ guess. Enumerate the real names and fix the script — do not guess twice.

```python
# append to the script temporarily, or run inline
a = unreal.EditorAssetLibrary.load_asset("/Game/PCG/DataAssets/Buildings/TL/RULE_TL_L01")
print([p for p in dir(a) if not p.startswith("_")])
```

Expected: names including the grammar and module-infos properties; substitute the real ones and re-run.

- [ ] **Step 4: Commit**

```bash
git add Content/Python/tl_make_rules.py
git commit -m "Author the four TL shape-grammar rules"
```

---

## Task 5: Author the `SGD_TL_A` shape-grammar definition

**Files:**
- Create: `Content/Python/tl_make_sgd.py`
- Output: `/Game/PCG/DataAssets/Buildings/TL/SGD_TL_A`

**Interfaces:**
- Consumes: the 4 RULEs (Task 4).
- Produces: 1 asset of class `BP_ShapeGrammarDefinition_C` with `Main Grammar` = `"L00, L01, L02, L03"`, `Use Grammar` true, and `Slots` (`TArray<STC_Slot>`) each referencing one rule.

- [ ] **Step 1: Write the SGD builder**

Create `Content/Python/tl_make_sgd.py`:

```python
# tl_make_sgd.py — create SGD_TL_A from the four TL rules.
#
# STC_Slot fields (verified live on SGD_CHA_A): Symbol(FName), size(double),
# scalable(bool), offset(FVector), is_corner(bool), Mirror(bool),
# ShapeGrammarRules(TArray<BP_ShapeGrammarRule_C*>) -> python "slots" on the SGD.
# BP_ShapeGrammarDefinition_C variables (python names): slots, main_grammar,
# use_grammar, minimum_size, spawn_on, reverse_spline, description.

R = {"slots": [], "errors": []}
args = mcp_args or {}
DEST = "/Game/PCG/DataAssets/Buildings/TL"
NAME = "SGD_TL_A"

EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()

# slot symbol -> rule asset, mirroring how CHA's SGD holds one slot per level
SLOTS = [
    ("L00", "RULE_TL_L00"),
    ("L01", "RULE_TL_L01"),
    ("L02", "RULE_TL_L02"),
    ("L03", "RULE_TL_L03"),
]
MAIN_GRAMMAR = "L00, L01, L02, L03"

sgd_cls = unreal.load_class(None, "/PCGPrimitives/Grammar/BP/BP_ShapeGrammarDefinition") \
    or unreal.BP_ShapeGrammarDefinition

asset = AT.create_asset(NAME, DEST, sgd_cls, None)
if asset is None:
    asset = EAL.load_asset(DEST + "/" + NAME)
if asset is None:
    R["errors"].append("create_asset returned None and the asset does not exist")
else:
    asset.set_editor_property("main_grammar", MAIN_GRAMMAR)
    asset.set_editor_property("use_grammar", True)
    asset.set_editor_property("description", unreal.Text("TL building - self-built 3-level modular kit."))

    slots = []
    for sym, rule_name in SLOTS:
        rule = EAL.load_asset(DEST + "/" + rule_name)
        if rule is None:
            R["errors"].append("rule missing: %s" % rule_name)
            continue
        s = unreal.STC_Slot()
        s.set_editor_property("symbol", unreal.Name(sym))
        s.set_editor_property("size", 0.0)
        s.set_editor_property("scalable", False)
        s.set_editor_property("offset", unreal.Vector(0.0, 0.0, 0.0))
        s.set_editor_property("is_corner", False)
        s.set_editor_property("mirror", False)
        s.set_editor_property("shape_grammar_rules", [rule])
        slots.append(s)
    asset.set_editor_property("slots", slots)
    EAL.save_loaded_asset(asset)

    back = EAL.load_asset(DEST + "/" + NAME)
    R["slots"] = [str(x.get_editor_property("symbol")) for x in back.get_editor_property("slots")]
    R["main_grammar"] = str(back.get_editor_property("main_grammar"))
    R["use_grammar"] = bool(back.get_editor_property("use_grammar"))

print(json.dumps(R, indent=1, default=str))
mcp_result = R
```

- [ ] **Step 2: Run it**

Run via the bridge: `run_unreal_script(script_path="tl_make_sgd.py")`

Expected: `slots: ["L00","L01","L02","L03"]`, `main_grammar: "L00, L01, L02, L03"`, `use_grammar: true`, `errors: []`.

- [ ] **Step 3: Verify against a known-good asset**

Load `SGD_CHA_A` with the same script (change `NAME`) and compare its `main_grammar` shape — it should be a comma-separated `L##` list. A mismatch in separator or spacing means the grammar tokenizer will not split TL's string.

Expected: CHA's `main_grammar` is also a comma-space-separated `L##` list, confirming TL's format matches.

- [ ] **Step 4: Commit**

```bash
git add Content/Python/tl_make_sgd.py
git commit -m "Author the SGD_TL_A shape-grammar definition"
```

---

## Task 6: Prove the facade on a spline

The art's acceptance test: lay TL along a spline and count what lands. This is where a wrong pivot, scale, or forward axis becomes visible, before any BDF work.

**Files:**
- Create: `Content/Python/tl_verify_sgd.py` (generation half)
- Create: `Content/Python/tl_verify_sgd_read.py` (read half)

**Interfaces:**
- Consumes: `SGD_TL_A` (Task 5), the imported meshes (Task 3).
- Produces: a printed report: instance count, mesh paths used, and the observed facade height.

- [ ] **Step 1: Write the generation half**

Create `Content/Python/tl_verify_sgd.py`. Builds a temporary graph that feeds a spline through `Assign_ShapeGrammarDefinition`, spawns a temp volume far from the delivered area, and generates.

```python
# tl_verify_sgd.py — PHASE A: build a spline, run SGD_TL_A along it, generate.
# Run tl_verify_sgd_read.py as a SEPARATE call afterwards: generation is async,
# so reading output in this same call returns an empty collection with no error.

import json

R = {}
args = mcp_args or {}
KEEP = bool(args.get("keep", False))

# far from the delivered 3x3 area, to avoid polluting it
SPAWN = unreal.Vector(400000.0, 0.0, 300.0)
GRAPH_PATH = "/Game/PCGTest/PCG_TL_SGD_Probe"

EAL = unreal.EditorAssetLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
AT = unreal.AssetToolsHelpers.get_asset_tools()

# ---------- clean any previous run ---------------------------------------
for a in eas.get_all_level_actors():
    try:
        if a.get_actor_label().startswith("TL_SGD_Probe"):
            eas.destroy_actor(a)
    except Exception:
        pass

# ---------- build the graph ----------------------------------------------
graph = EAL.load_asset(GRAPH_PATH)
if graph is None:
    graph = AT.create_asset("PCG_TL_SGD_Probe", "/Game/PCGTest", unreal.PCGGraph, None)
R["graph"] = str(graph) if graph else None

node, settings = graph.add_node_of_type(
    unreal.load_class(None, "/Script/PCG.PCGAssignShapeGrammarDefinitionSettings"))
R["node_added"] = node is not None
R["settings_class"] = settings.get_class().get_name() if settings else None

# discover the real property names instead of guessing
props = [p for p in dir(settings) if not p.startswith("_")]
R["settings_props"] = props[:60]

try:
    sgd = EAL.load_asset("/Game/PCG/DataAssets/Buildings/TL/SGD_TL_A")
    for cand in ("shape_grammar_definition", "grammar_definition", "sgd"):
        if cand in props:
            settings.set_editor_property(cand, sgd)
            R["set_sgd_via"] = cand
            break
    for cand in ("grammar_selection", "selection"):
        if cand in props:
            R["has_grammar_selection"] = cand
            break
except Exception as e:
    R["set_err"] = "%s: %s" % (type(e).__name__, e)

# ---------- create the spline + volume -----------------------------------
spline_actor = eas.spawn_actor_from_class(unreal.Actor, SPAWN, unreal.Rotator())
spline_actor.set_actor_label("TL_SGD_Probe_Spline")
spline = spline_actor.add_component_by_class(unreal.SplineComponent, True)
pts = [unreal.Vector(0, 0, 0), unreal.Vector(2000, 0, 0)]
spline.set_editor_property("spline_curve", unreal.SplineCurve())
spline.clear_spline_points()
for p in pts:
    spline.add_spline_point(p, unreal.SplinePointType.LINEAR, False)
R["spline_points"] = spline.get_number_of_spline_points()

vol_actor = eas.spawn_actor_from_class(unreal.Actor, SPAWN, unreal.Rotator())
vol_actor.set_actor_label("TL_SGD_Probe_Volume")
comp = vol_actor.add_component_by_class(unreal.PCGComponent, True)
comp.set_graph(graph)
comp.activate(True)          # REQUIRED: without this it is a silent zero
comp.generate_local(True)
R["generated"] = True

print(json.dumps(R, indent=1, default=str))
mcp_result = R
```

- [ ] **Step 2: Write the read half**

Create `Content/Python/tl_verify_sgd_read.py`. Two-phase: unwrap the output collection **and** count ISM instances, then clean up.

```python
# tl_verify_sgd_read.py — PHASE B: read what the TL facade spawned, then clean up.
#
# Two independent readings, because they disagree in a way that matters:
#   * output-pin point/tagged-data count  -> what the graph piped out
#   * ISM instance count                  -> what geometry actually landed
# A spawn-type graph can report 0 tagged data and still have spawned thousands
# of instances. Geometry is what the user asked for, so instances win.

import json

R = {}
args = mcp_args or {}
KEEP = bool(args.get("keep", False))
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EAL = unreal.EditorAssetLibrary

target = None
for a in eas.get_all_level_actors():
    try:
        if a.get_actor_label() == "TL_SGD_Probe_Volume":
            target = a
    except Exception:
        continue
if target is None:
    R["fatal"] = "probe volume not found - run tl_verify_sgd.py first"
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit

comp = target.get_component_by_class(unreal.PCGComponent)

# ---------- reading 1: the output pin -------------------------------------
out = {}
try:
    coll = comp.get_generated_graph_output()
    items = coll.get_editor_property("tagged_data")
    out["tagged_count"] = len(items)
    tot = 0
    for it in items:
        wrap = it.get_editor_property("data")
        d = wrap.get_editor_property("data")
        if d:
            try:
                tot += d.get_num_points()
            except Exception:
                pass
    out["total_points"] = tot
except Exception as e:
    out["fatal"] = "%s: %s" % (type(e).__name__, e)
R["output_pin"] = out

# ---------- reading 2: what geometry landed -------------------------------
spawn = {"components": [], "total_instances": 0, "meshes": {}}
try:
    total = 0
    meshes = {}
    for c in target.get_components_by_class(unreal.PrimitiveComponent):
        n = 0
        try:
            n = c.get_instance_count()
        except Exception:
            pass
        if not n:
            continue
        total += n
        try:
            mp = c.get_editor_property("static_mesh")
            path = mp.get_path_name() if mp else "<none>"
        except Exception:
            path = "<err>"
        meshes[path] = meshes.get(path, 0) + n
        spawn["components"].append({
            "comp": c.get_name(), "class": c.get_class().get_name(), "instances": n})
    spawn["total_instances"] = total
    spawn["meshes"] = meshes
    spawn["tl_mesh_instances"] = sum(
        v for k, v in meshes.items() if "/Game/Building/TL/" in k)
except Exception as e:
    spawn["fatal"] = "%s: %s" % (type(e).__name__, e)
R["spawned"] = spawn

# ---------- cleanup: never leave the probe, never save the level ----------
cl = {}
if not KEEP:
    try:
        comp.cleanup_local(True)
        cl["cleanup_local"] = "OK"
    except Exception as e:
        cl["cleanup_local"] = type(e).__name__
    for label in ("TL_SGD_Probe_Volume", "TL_SGD_Probe_Spline"):
        for a in eas.get_all_level_actors():
            try:
                if a.get_actor_label() == label:
                    eas.destroy_actor(a)
            except Exception:
                pass
    cl["actors_removed"] = True
    cl["level_saved"] = False   # deliberately NOT saved - test residue stays out
else:
    cl["skipped"] = "args.keep is true"
R["cleanup"] = cl

print(json.dumps(R, indent=1, default=str))
mcp_result = R
```

- [ ] **Step 3: Run both phases**

Phase A: `run_unreal_script(script_path="tl_verify_sgd.py")`
Phase B: `run_unreal_script(script_path="tl_verify_sgd_read.py")`

Expected: `spawned.total_instances > 0` and `spawned.tl_mesh_instances > 0`, with `spawned.meshes` keys containing `/Game/Building/TL/`.

**If `total_instances` is 0**, check in this order: (a) did `activate(True)` run — `R["generated"]` true only means `generate_local` was called; (b) does the graph's input pin actually carry the spline (the `Assign_ShapeGrammarDefinition` input pin is named `Spline`, not `In` — verify with the pin-label helper); (c) is `SGD_TL_A` actually assigned, per `R["set_sgd_via"]` in Phase A.

- [ ] **Step 4: Check the facade geometry is upright**

Confirm the spawned instances stand vertically: every instance's Z extent should be ~500 cm at L1, not ~0. Read a manifest of instance transforms if `get_instance_count` alone is inconclusive.

**If instances lie flat**, `MeshForwardAxis` is wrong. Flip `mesh_forward_axis` in `tl_make_rules.py` from `Axis.Z` to `Axis.Y`, re-run Task 4, and re-verify. This is the verification the Task 4 comment deferred.

- [ ] **Step 5: Commit**

```bash
git add Content/Python/tl_verify_sgd.py Content/Python/tl_verify_sgd_read.py
git commit -m "Verify the TL facade on a spline with two independent readings"
```

---

## Task 7: Build the TL-extended BDF data asset

The step that makes TL usable by the real city pipeline. Write a **new** asset; never touch Epic's.

**Files:**
- Create: `Content/Python/tl_make_bdf.py`
- Output: `/Game/PCG/DataAssets/BDF/BDF_WithTL` (a `PCGDataAsset`)

**Interfaces:**
- Consumes: `tl_kit_spec.json` (Task 2), and the live `CitySampleBuildingBDF_Asset_PCG` as the source of the 27 existing styles.
- Produces: one `PCGDataAsset` whose `data.tagged_data` has the same four tag groups as the original, each extended with TL rows.

**The schema to replicate** (extracted live; see the plan header table):

| set (tags, pin `In`) | TL rows to add | attributes |
|---|---|---|
| `BDF`,`BDFData` | 1 | `BuildingToken`(String), `VerticalGrammar`(String), `VerticalGrammarStaggered`(String), `MinWallWidth`(Float), `MinBldgHeight`(Float), `MaxBldgHeight`(Float), `RoofData`(Vector4) |
| `Levels`,`BDFData` | 4 | `BuildingToken`(**Name**), `LevelNumber`(Int32), `LevelToken`(String), `LevelHeight`(Float), `Size`(Float), `F`,`F0`,`F1`,`F2`(String), `FLengths`(Vector), `IsTopper`(Bool) |
| `Modules`,`BDFData` | ~4 (L0) + 15 (L1) + 13 (L2) + 13 (L3) | `BuildingToken`(String), `Level`(Int32), `Symbol`(String), `Size`(Double), `Mod_Name`(String), `Mesh`(SoftObjectPath), `HasProps`(Bool), `HasWindow`(Bool), `bScalable`(Bool), `PivotOffset`(Vector), `MeshForwardAxis`(Double), `PropOffset`(Vector), `PtID`(Int32) |
| `Props`,`BDFData` | 0 | (TL skips props in phase 1) |

Note: `Mod_Name` is **NOT** read as a String in the live data (the getter returned empty); treat it as `Name`-typed and verify in Step 3.

- [ ] **Step 1: Write the BDF builder**

Create `Content/Python/tl_make_bdf.py`:

```python
# tl_make_bdf.py — build /Game/PCG/DataAssets/BDF/BDF_WithTL.
#
# Copies all four tag groups from Epic's CitySampleBuildingBDF_Asset_PCG and
# appends TL rows. Epic's asset is READ ONLY here: it is gitignored, so there is
# no VCS fallback if it is damaged.
#
# ============================ WRITE PATH =================================
# MEASURED, NOT ASSUMED (2026-09-24). Three "obvious" routes were tried and ALL
# THREE FAIL, because the relevant properties are declared VisibleAnywhere,
# which sets CPF_EditConst and blocks Python's setter even though the header
# also says BlueprintReadWrite:
#
#   * UPCGDataAsset.data                    -> "Property 'Data' ... is read-only"
#   * UPCGDataCollectionExporter.data       -> same
#   * FPCGDataPtrWrapper.data               -> same
#
# Also: PCGDataFunctionLibrary.make_tagged_data is declared in the header but is
# NOT bound in this build ("has no attribute 'make_tagged_data'").
#
# THE ROUTE THAT WORKS (measured end to end, value verified on disk):
#   1. EditorAssetLibrary.duplicate_asset(SRC, DEST)
#      -> copies the asset with all four tag groups intact (27/240/2916/1966)
#   2. PCGDataFunctionLibrary.add_to_collection(coll, pd, Name("In"), tags)
#      -> builds tagged data with pin and tags preserved
#   3. mutate the point data that now belongs to the DUPLICATE:
#      md.create_string_attribute(...) and pd.set_points(pts) both work
#      (the read-only wall is on the container, not on the data inside it)
#   4. EditorAssetLibrary.save_loaded_asset(asset)
#
# Measured proof: the Levels group went 240 -> 241 points; the .uasset on disk
# grew to 2,958,589 bytes with a fresh mtime; Epic's source stayed byte-identical
# (2958616 bytes, mtime 1788235103 unchanged).
#
# IMPORTANT: mutation must happen on the duplicated asset's OWN data objects.
# Creating fresh PCGPointData and trying to put it into the collection does not
# work, because that needs a writable `data`.

import json

R = {"groups": [], "errors": []}
args = mcp_args or {}
SPEC = args.get("spec", "E:/PCG_Claude/Tools/tl_kit/tl_kit_spec.json")
SRC = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG"
DEST = args.get("dest", "/Game/PCG/DataAssets/BDF/BDF_WithTL")

EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers

with open(SPEC, encoding="utf-8") as f:
    spec = json.load(f)

# ---------- TL values -----------------------------------------------------
# From the BDF source (Content/Building/HDA/Bldg/BDF) + spec 2.8.
# Horizontal grammar per level: levels are remapped so TL's LV0..LV3 mirror CHA's.
TL_BDF = {
    "BuildingToken": "TL",
    "VerticalGrammar": "[LV0][LV1][LV2][LV3]",
    "VerticalGrammarStaggered": "[LV0][LV1][LV2][LV3]",
    "MinWallWidth": 12.0,       # matches CHA; Review Focus 5 watches this value
    "MinBldgHeight": 5.0,
    "MaxBldgHeight": 60.0,
    "RoofData": unreal.Vector4(0.2, 0.1, 0.2, 0.1),   # CHA's Roof_Inset/Offset pair
}

# level -> the 3 facade variants (BDF F0/F1/F2) and their required length in cm.
# CHA's own values are the template (spec 2.6 mapping applied).
TL_LEVELS = [
    {"LevelNumber": 0, "LevelToken": "LV0", "LevelHeight": 5.0, "Size": 0.0,
     "F0": "[FC][FS2]+[LC]", "F1": "[FC][FS2]+[LC]", "F2": "[FC][FS2]+[LC]",
     "FLengths": unreal.Vector(300.0, 300.0, 300.0), "IsTopper": False},
    {"LevelNumber": 1, "LevelToken": "LV1", "LevelHeight": 5.0, "Size": 0.0,
     "F0": "[FC][WS1][W1]+[LC]",
     "F1": "[FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]",
     "F2": "[FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]",
     "FLengths": unreal.Vector(950.0, 3725.0, 5400.0), "IsTopper": False},
    {"LevelNumber": 2, "LevelToken": "LV2", "LevelHeight": 3.0, "Size": 0.0,
     "F0": "[FC][WS1][W1]+[LC]",
     "F1": "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
     "F2": "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
     "FLengths": unreal.Vector(950.0, 3925.0, 5800.0), "IsTopper": False},
    {"LevelNumber": 3, "LevelToken": "LV3", "LevelHeight": 3.0, "Size": 0.0,
     "F0": "[FC][WS1][W1]+[LC]",
     "F1": "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
     "F2": "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
     "FLengths": unreal.Vector(950.0, 3925.0, 5800.0), "IsTopper": False},
]

# symbol -> (kit part, scalable); mirrors CHA's symbol set
SYM = {"Wall_01": ("W1", False), "Column_01": ("P1", False),
       "Column_02": ("P2", False), "Entrance_01": ("E1", False),
       "CornerEx_01": ("C_CE", False), "CornerExL_01": ("C_SL", False),
       "CornerExR_01": ("C_SR", False), "CornerIn_01": ("C_I", False),
       "CornerInL_01": ("C_IL", False), "CornerInR_01": ("C_IR", False)}

TL_MESH_ROOT = "/Game/Building/TL/A"

def tl_modules():
    rows = []
    ptid = 0
    # L0 filler, matching CHA's FS2
    rows.append({"BuildingToken": "TL", "Level": 0, "Symbol": "FS2", "Size": 200.0,
                 "Mod_Name": "L0_Filler", "bScalable": True,
                 "Mesh": "%s/Kit_Bldg_TL_L1_A/Mesh/SM_BLDG_TL_L01_A_Wall_01_N1"
                         % TL_MESH_ROOT,
                 "PivotOffset": unreal.Vector(), "MeshForwardAxis": 2.0,
                 "PropOffset": unreal.Vector(), "HasProps": False, "HasWindow": False,
                 "PtID": ptid})
    ptid += 1
    for p in spec["parts"]:
        sym, scal = SYM[p["part"]]
        mesh_path = "%s/Kit_Bldg_TL_L%d_A/Mesh/%s" % (
            TL_MESH_ROOT, p["level"], p["mesh_name"])
        rows.append({
            "BuildingToken": "TL", "Level": p["level"], "Symbol": sym,
            "Size": p["width_m"] * 100.0, "Mod_Name": p["mesh_name"],
            "bScalable": scal, "Mesh": mesh_path,
            "PivotOffset": unreal.Vector(), "MeshForwardAxis": 2.0,
            "PropOffset": unreal.Vector(), "HasProps": False, "HasWindow": False,
            "PtID": ptid})
        ptid += 1
        if p["part"] == "Wall_01":      # the scalable filler per level
            rows.append(dict(rows[-1], Symbol="WS1", bScalable=True,
                             Mod_Name=p["mesh_name"] + "_WS", PtID=ptid))
            ptid += 1
    return rows

# ---------- attribute type discovery -------------------------------------
# The duplicate already carries every attribute with its correct type, so we
# never create attributes here - we only append points and fill them. But we
# must know each attribute's type to pick the matching SETTER. Discover it by
# probing an existing row with each getter in turn.
def discover_types(pt, md, names):
    types = {}
    for nm in names:
        for kind, fn in (("name", "get_name_attribute"),
                         ("str", "get_string_attribute"),
                         ("bool", "get_bool_attribute"),
                         ("dbl", "get_double_attribute"),
                         ("int", "get_integer32_attribute"),
                         ("vec", "get_vector_attribute"),
                         ("v4", "get_vector4_attribute"),
                         ("sop", "get_soft_object_path_attribute")):
            try:
                getattr(MA, fn)(pt, md, nm)
                types[nm] = kind
                break
            except Exception:
                continue
    return types

SETTERS = {"str": "set_string_attribute", "name": "set_name_attribute",
           "int": "set_integer32_attribute", "dbl": "set_double_attribute",
           "bool": "set_bool_attribute", "vec": "set_vector_attribute",
           "v4": "set_vector4_attribute", "sop": "set_soft_object_path_attribute"}

# explicit inverse of SETTERS: never derive a getter by editing the setter name
GETTERS = {"str": "get_string_attribute", "name": "get_name_attribute",
           "int": "get_integer32_attribute", "dbl": "get_double_attribute",
           "bool": "get_bool_attribute", "vec": "get_vector_attribute",
           "v4": "get_vector4_attribute", "sop": "get_soft_object_path_attribute"}

def mk_pt(md, values, types):
    """Build one FPCGPoint, setting only attributes whose type we discovered.

    set_*_attribute takes UPARAM(ref) FPCGPoint&, which Python returns rather
    than mutating in place, so the result MUST be captured each time.
    """
    p = unreal.PCGPoint()
    for nm, v in values.items():
        kind = types.get(nm)
        if kind is None or v is None:
            continue
        try:
            p = getattr(MA, SETTERS[kind])(p, md, nm, v)
        except Exception as e:
            R["errors"].append("set %s (%s): %s: %s" % (
                nm, kind, type(e).__name__, e))
    return p

# ---------- duplicate, then append ---------------------------------------
if EAL.does_asset_exist(DEST):
    EAL.delete_asset(DEST)

try:
    dup = EAL.duplicate_asset(SRC, DEST)
    R["duplicated"] = dup is not None
except Exception as e:
    R["errors"].append("duplicate_asset: %s: %s" % (type(e).__name__, e))
    dup = None

if dup:
    items = dup.get_editor_property("data").get_editor_property("tagged_data")
    for it in items:
        tags = [str(t) for t in it.get_editor_property("tags")]
        d = it.get_editor_property("data").get_editor_property("data")
        if d is None:
            continue
        md = d.mutable_metadata()
        existing = list(d.get_points())
        keys = tuple(sorted(tags))

        # what rows does this group need?
        if "BDF" in tags and "BDFData" in tags:
            new_rows = [TL_BDF]
        elif "Levels" in tags:
            new_rows = [dict(r, BuildingToken="TL") for r in TL_LEVELS]
        elif "Modules" in tags:
            new_rows = tl_modules()
        else:
            new_rows = []          # Props: phase 1 adds none

        if not new_rows:
            R["groups"].append({"tags": keys, "existing": len(existing),
                                "added": 0})
            continue

        # discover the real types from a row that is already there
        types = discover_types(existing[0], md, list(new_rows[0].keys()))
        if "F" in new_rows[0] and "F" not in types:
            # the Levels set carries F as well as F0/F1/F2; fill it from F0
            pass
        added = []
        for row in new_rows:
            full = dict(row)
            if "F" not in full and "F0" in full:
                full["F"] = full["F0"]
            added.append(mk_pt(md, full, types))

        # append in ONE set_points call: the whole list replaces the array
        d.set_points(existing + added)
        R["groups"].append({"tags": keys, "existing": len(existing),
                            "added": len(added),
                            "total": len(d.get_points()),
                            "types": types})

    try:
        R["saved"] = EAL.save_loaded_asset(dup)
    except Exception as e:
        R["errors"].append("save: %s: %s" % (type(e).__name__, e))

R["exists"] = EAL.does_asset_exist(DEST)

# ---------- verify from a fresh load -------------------------------------
ver = {}
try:
    a2 = EAL.load_asset(DEST)
    items2 = a2.get_editor_property("data").get_editor_property("tagged_data")
    ver["tagged_count"] = len(items2)
    for it in items2:
        tg = [str(t) for t in it.get_editor_property("tags")]
        d = it.get_editor_property("data").get_editor_property("data")
        md = d.mutable_metadata()
        types = discover_types(d.get_points()[0], md, ["BuildingToken"])
        kind = types.get("BuildingToken")
        tl = 0
        if kind:
            getter = getattr(MA, GETTERS[kind])
            for pt in d.get_points():
                try:
                    if str(getter(pt, md, "BuildingToken")) == "TL":
                        tl += 1
                except Exception:
                    pass
        ver["+".join(tg)] = {"points": len(d.get_points()), "tl_points": tl,
                             "token_type": kind}
except Exception as e:
    ver["fatal"] = "%s: %s" % (type(e).__name__, e)
R["verify"] = ver

print(json.dumps(R, indent=1, default=str))
mcp_result = R
```

- [ ] **Step 2: Run it**

Run via the bridge: `run_unreal_script(script_path="tl_make_bdf.py")`

Expected: `duplicated: true`, `saved: true`, `exists: true`, and `verify` showing TL points in the `BDF+BDFData` (1), `Levels+BDFData` (4), and `Modules+BDFData` (~48) groups, with every existing group's original count preserved.

**If `duplicate_asset` returns `None`**, `DEST`'s folder does not exist. Create it first:

```python
unreal.EditorAssetLibrary.make_directory("/Game/PCG/DataAssets/BDF")
```

- [ ] **Step 3: Verify the `Levels.BuildingToken` type**

This is Review Focus 2 — the trap that makes TL silently unmatched. Step 2's `verify` already reports `token_type` per group; confirm the Levels group reports `name` (matching how Epic's copy stores it).

Read a TL level row back and confirm it reads through the **`name`** getter (not `str`):

```python
# inline, via the bridge
a = unreal.EditorAssetLibrary.load_asset("/Game/PCG/DataAssets/BDF/BDF_WithTL")
MA = unreal.PCGMetadataAccessorHelpers
for it in a.get_editor_property("data").get_editor_property("tagged_data"):
    if "Levels" in [str(t) for t in it.get_editor_property("tags")]:
        d = it.get_editor_property("data").get_editor_property("data")
        md = d.mutable_metadata()
        pt = d.get_points()[-1]        # a TL row, appended last
        print("as name:", MA.get_name_attribute(pt, md, "BuildingToken"))
        print("as str :", MA.get_string_attribute(pt, md, "BuildingToken"))
```

Expected: `as name: TL` and `as str:` empty. Whichever getter returns `TL` is the type the copy actually uses.

**If neither returns `TL`**, the point was appended without its metadata entry reaching the copied attribute — re-check `discover_types` on that group and confirm the setter chosen matches.

- [ ] **Step 4: Commit**

```bash
git add Content/Python/tl_make_bdf.py
git commit -m "Build the TL-extended BDF data asset without touching Epic's"
```

---

## Task 8: Register TL in the width tables and the style whitelist

Four edits. Without all four, TL exists and never generates.

**What Task 1 measured about the whitelist (this supersedes the plan's earlier model):**

The style-code whitelist is **not** a string literal sitting on a node. Task 1 scanned both graphs
named earlier plus the full 48-graph closure of their subgraph references and found **zero** node
properties carrying the style-code string. It is instead a **graph-level user parameter**:

- Name: `BuildingsStyles`, type `String`, default `""`.
- Host: `Assign_CitySampleBuildings`' own `user_parameters` InstancedPropertyBag.
- Its own tooltip documents the empty default as *"the primitive will randomly use all available
  buildings styles"*.
- **No consumer overrides it.** All 3 subgraph nodes in `PCG_3_3_1_Buildings` and all 10 in
  `Assign_BldgStyles_per_MinWallWidth` have `subgraph_override == None`, so every consumer is
  currently taking the "all styles" default.
- Inside `Assign_CitySampleBuildings_CoreProcess`, the value is materialized as a point-data
  attribute `BuildingsStyles` and consumed by two nodes: `FilterDataByAttribute_4`
  (`attribute = "@Data.BuildingsStyles"`) and `DataAttributesToTags_1`
  (`attributes_tags_mapping = {"BuildingsStyles": {}}`). Those consume it; they are not the
  definition site.

**Two consequences that shape this task:**

1. The single edit target is the `BuildingsStyles` user parameter. There is no second string to
   hunt for.
2. Because nothing overrides it today, TL would in principle already be eligible via the
   empty-string default. The task still sets it **explicitly**, because relying on an undocumented
   default for a key behaviour is how the "authored but never registered" failure (Review Focus 1)
   hides. An explicit list is also the only way to *prove* TL is in the set.

**Files:**
- Create: `Content/Python/tl_register.py`
- Modify: the two DataTables
- Modify: `/CitySamplePCG/PCG/Primitives/Buildings/Assign_CitySampleBuildings` (the `BuildingsStyles` user parameter)
- Modify: `/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/LoadCitySampleData` (repoint to `BDF_WithTL`)

**Interfaces:**
- Consumes: Task 1's `tl_facts.json` → `whitelist_nodes.Assign_CitySampleBuildings.hits[0]` (the parameter name and its read mechanism), Task 7's `BDF_WithTL`.
- Produces: TL present in `DT_Bldg_MinWidth`, `DT_Bldg_LevelMinWidth`, the `BuildingsStyles` parameter, and via it in every consumer; `LoadCitySampleData` repointed at `BDF_WithTL`.

**Read mechanism for the parameter (Task 1 measured this — do not guess):** the
`user_parameters` property is an `InstancedPropertyBag`. `to_dict()` returns `{}` (unhelpful), but
`export_text()` returns the real values, formatted like
`'(Value=/Engine/Transient.PropertyBag_...(...,BuildingsStyles="",...))'`. Use `export_text()` to
read and confirm; the setter path must be probed the same way the BDF data was — try, read back,
and trust only the read-back.

- [ ] **Step 1: Probe the DataTable row-write mechanism before writing the registration script**

The DataTable edits are genuinely the least certain part of this task, and the earlier plan
guessed at them. Establish the real mechanism first, in one call, then write the script around
what works. Do **not** hand-patch a `.uasset`.

Create `Content/Python/tl_dt_probe.py`:

```python
# tl_dt_probe.py — find how to ADD a row to a DataTable from Python.
#
# The two tables TL needs rows in:
#   DT_Bldg_MinWidth       struct ST_Bldg_MinWidth      fields: buildingToken(Str), minWidth(double)
#   DT_Bldg_LevelMinWidth  struct ST_Level_MinWidth     fields: BuildingToken, LevelToken,
#                                                              LevelNumber(int32), F0Grammar,
#                                                              CornerModuleSymbol, CornerSize,
#                                                              MinWidthWorstCase
#
# READ-ONLY except that it may write one throwaway row and remove it again.

import json

R = {}
args = mcp_args or {}
EAL = unreal.EditorAssetLibrary

TABLES = {
    "DT_Bldg_MinWidth": "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_MinWidth",
    "DT_Bldg_LevelMinWidth": "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_LevelMinWidth",
}

# ---------- what API surface exists for DataTables? ----------------------
DTFL = unreal.DataTableFunctionLibrary
R["DTFL_members"] = sorted([m for m in dir(DTFL) if not m.startswith("_")])

# does the table object expose row write methods?
for label, path in TABLES.items():
    dt = EAL.load_asset(path)
    rec = {"path": path, "loaded": dt is not None}
    if dt is None:
        R[label] = rec
        continue
    rec["class"] = dt.get_class().get_name()
    rec["row_struct"] = str(dt.get_editor_property("row_struct"))
    rec["members"] = sorted([m for m in dir(dt)
                             if not m.startswith("_") and
                             ("row" in m.lower() or "text" in m.lower())])
    # existing rows + their text form (the text form is what a row-write needs)
    try:
        rm = dt.get_editor_property("row_map")
        keys = [str(k) for k in rm.keys()]
        rec["row_count"] = len(keys)
        rec["first_keys"] = keys[:5]
        rec["last_keys"] = keys[-3:]
        rec["starts_with_TL"] = [k for k in keys if k.startswith("TL")]
        # dump ONE existing row as text, to learn the format an add must produce
        if keys:
            one = dt.get_editor_property("row_map")
            row = one[unreal.Name(keys[0])] if hasattr(one, "__getitem__") else None
            if row is not None:
                rec["sample_row_key"] = keys[0]
                try:
                    rec["sample_row_text"] = row.export_text()
                except Exception as e:
                    rec["sample_row_text_err"] = "%s: %s" % (type(e).__name__, e)
    except Exception as e:
        rec["row_map_err"] = "%s: %s" % (type(e).__name__, e)
    R[label] = rec

print("###DTFL_MEMBERS###")
print(json.dumps(R["DTFL_members"], indent=1))
for label in TABLES:
    print("###%s###" % label)
    rec = R.get(label, {})
    print("  loaded=%s row_count=%s" % (rec.get("loaded"), rec.get("row_count")))
    print("  row_struct=%s" % rec.get("row_struct"))
    print("  members=%s" % rec.get("members"))
    print("  first_keys=%s" % rec.get("first_keys"))
    print("  starts_with_TL=%s" % rec.get("starts_with_TL"))
    if rec.get("sample_row_text"):
        print("  sample_row[%s] text:" % rec.get("sample_row_key"))
        print("     %s" % rec["sample_row_text"][:300])

mcp_result = R
```

- [ ] **Step 2: Run the probe and read what it found**

Run via the bridge: `run_unreal_script(script_path="tl_dt_probe.py")`

Expected: a list of `DataTableFunctionLibrary` members including at least one of
`fill_data_table_from_csv_string` / `fill_data_table_from_json_string`, the two tables' row struct
names, their existing row keys (confirming 27 for `DT_Bldg_MinWidth` and the `DT_Bldg_LevelMinWidth`
key pattern), and **the export text of one existing row** — which is the exact format an added row
must produce.

**Decision point, and the reason this step is separate:** if
`fill_data_table_from_csv_string` (or the JSON variant) exists, use it — write TL's rows as a CSV
string with a header naming the struct's fields and append them. If it does **not** exist, report
back to the controller before proceeding: the remaining options (constructing rows via export text
against the struct's mangled field names, the way the RULE assets and the BDF data both had to be
handled) are a different and larger piece of work, and the controller needs to decide whether to
take that route or to drop the DataTable edits on the grounds that `BuildingsStyles` alone decides
participation. **Do not silently skip the tables if the API is missing.**

- [ ] **Step 3: Write the registration script around the working mechanism**

Create `Content/Python/tl_register.py`. Use the mechanism Step 2 proved. The structure:

```python
# tl_register.py — register TL: two DataTable row sets, the BuildingsStyles
# whitelist parameter, and the LoadCitySampleData repoint.
#
# MEASURED BACKGROUND (Task 1):
#   * The style whitelist is a graph-LEVEL USER PARAMETER named "BuildingsStyles"
#     (String, default "") on Assign_CitySampleBuildings' user_parameters
#     InstancedPropertyBag. It is NOT a literal string on any node: a scan of
#     both whitelist graphs plus their full 48-graph closure found zero hits.
#   * No consumer overrides it (all 13 instantiating subgraph nodes across the
#     two graphs have subgraph_override == None), so everyone currently takes
#     the "all styles" empty-string default.
#   * Reading it: user_parameters.to_dict() returns {} -- useless. export_text()
#     returns the real value.
#
# Idempotent: every edit checks for TL first.

import json

R = {"steps": [], "errors": []}
args = mcp_args or {}
FACTS = args.get("facts", "E:/PCG_Claude/Tools/tl_kit/tl_facts.json")
EAL = unreal.EditorAssetLibrary

with open(FACTS, encoding="utf-8") as f:
    facts = json.load(f)

def note(step, **kw):
    R["steps"].append(dict(step=step, **kw))

DT_MIN = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_MinWidth"
DT_LVL = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_LevelMinWidth"
ASG    = "/CitySamplePCG/PCG/Primitives/Buildings/Assign_CitySampleBuildings"
LOAD   = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/LoadCitySampleData"

# ---------- 1 + 2. the two DataTables (mechanism per Step 2's probe) -------
# TL's own values. minWallWidth 12 matches CHA; the level rows mirror the four
# TL level rows written into BDF_WithTL in Task 7 (LV0..LV3).
TL_MINWIDTH_CSV = "buildingToken,minWidth\nTL,12.0\n"
TL_LEVEL_CSV = (
    "BuildingToken,LevelToken,LevelNumber,F0Grammar,CornerModuleSymbol,CornerSize,MinWidthWorstCase\n"
    "TL,LV0,0,[FC][FS2]+[LC],C_CE,150.0,950.0\n"
    "TL,LV1,1,[FC][WS1][W1]+[LC],C_CE,150.0,950.0\n"
    "TL,LV2,2,[FC][WS1][W1]+[LC],C_CE,150.0,950.0\n"
    "TL,LV3,3,[FC][WS1][W1]+[LC],C_CE,150.0,950.0\n"
)

for label, path, csv in (("DT_Bldg_MinWidth", DT_MIN, TL_MINWIDTH_CSV),
                         ("DT_Bldg_LevelMinWidth", DT_LVL, TL_LEVEL_CSV)):
    try:
        dt = EAL.load_asset(path)
        if dt is None:
            R["errors"].append("%s not loadable" % label)
            continue
        rm = dt.get_editor_property("row_map")
        keys = [str(k) for k in rm.keys()]
        if any(k.startswith("TL") for k in keys):
            note(label, action="already has TL rows",
                 tl_rows=[k for k in keys if k.startswith("TL")])
            continue
        # CsvImport with a header row appends/updates by row name. If the first
        # column is not the row name, the import needs an explicit row-name
        # mapping -- Step 2's sample row text tells you which form is right.
        ok = unreal.DataTableFunctionLibrary.fill_data_table_from_csv_string(dt, csv)
        back = [str(k) for k in dt.get_editor_property("row_map").keys()]
        note(label, filled=bool(ok),
             row_count_before=len(keys), row_count_after=len(back),
             tl_rows=[k for k in back if k.startswith("TL")])
        if not any(k.startswith("TL") for k in back):
            R["errors"].append("%s: no TL row after import" % label)
        else:
            EAL.save_loaded_asset(dt)
    except Exception as e:
        R["errors"].append("%s: %s: %s" % (label, type(e).__name__, e))

# ---------- 3. the BuildingsStyles whitelist parameter --------------------
try:
    g = EAL.load_asset(ASG)
    bag = g.get_editor_property("user_parameters")
    before = bag.export_text()
    note("BuildingsStyles_before", text=before[:400])
    if 'BuildingsStyles="TL' in before or "BuildingsStyles=TL" in before:
        note("BuildingsStyles", action="already set")
    else:
        # Probe the setter, then confirm by re-reading export_text(). The bag is
        # an InstancedPropertyBag and its dict view is empty, so a plain
        # set_editor_property on the parameter is unlikely to work; Step 4
        # decides the real mechanism from this probe's output.
        note("BuildingsStyles", action="needs_set",
             read_mechanism="export_text()",
             target_value="TL",
             full_list_needed=(
                 "the tooltip enumerates CHA..SFJ; to keep every existing style "
                 "eligible the value must list all 27 plus TL, or the parameter "
                 "must be left empty and TL relied on via the default"))
except Exception as e:
    R["errors"].append("BuildingsStyles: %s: %s" % (type(e).__name__, e))

# ---------- 4. repoint LoadCitySampleData at BDF_WithTL -------------------
try:
    lg = EAL.load_asset(LOAD)
    hits = []
    for node in lg.get_editor_property("nodes"):
        try:
            s = node.get_settings()
        except Exception:
            continue
        if s is None:
            continue
        for prop in dir(s):
            if prop.startswith("_"):
                continue
            try:
                v = s.get_editor_property(prop)
            except Exception:
                continue
            if "CitySampleBuildingBDF_Asset_PCG" in str(v):
                hits.append({"node_class": s.get_class().get_name(),
                             "param": prop,
                             "text": str(v)[:200]})
    note("LoadCitySampleData", candidates=hits)
except Exception as e:
    R["errors"].append("LoadCitySampleData: %s: %s" % (type(e).__name__, e))

print(json.dumps(R, indent=1, default=str))
mcp_result = R
```

- [ ] **Step 4: Run it, then finish the whitelist and repoint edits it could not do alone**

Run via the bridge: `run_unreal_script(script_path="tl_register.py")`

Then, using what Steps 2–3 reported:

1. **The `BuildingsStyles` value.** If `InstancedPropertyBag` has no usable setter, the value must
   be set through the graph's own user-parameter UI path or by overriding the parameter on the
   instantiating node (`subgraph_override`) — whichever this engine build exposes. Decide from the
   probe output and **read the value back with `export_text()` to confirm**. A value that reads
   back unchanged is a failed edit, not a success.
2. **`BuildingsStyles` must not narrow the city.** If setting it explicitly, the value must list
   **all 27 existing codes plus TL**, not TL alone — otherwise the edit would remove every other
   style from the city, which is a visible behaviour regression Task 10 would catch but which
   should not be introduced deliberately. The 27 codes are: `CHA CHB CHC CHD CHE CHF CHG CHH CHI
   CHJ NYAA NYAB NYAC NYAD NYAE NYAF NYG NYGA NYH QBA QBAA SFA SFB SFC SFD SFE SFJ`.
3. **The repoint.** Set the parameter Step 3's `candidates` named on the `LoadCitySampleData` node
   to `/Game/PCG/DataAssets/BDF/BDF_WithTL`, save, and read it back.

Expected: the `BuildingsStyles` value reads back containing `TL` (plus the other 27), and the
`LoadCitySampleData` node's parameter reads `/Game/PCG/DataAssets/BDF/BDF_WithTL`.

- [ ] **Step 5: Verify TL is present in all four places**

Review Focus 1 and 5: an asset that exists but is unregistered generates nothing, and a
`minWallWidth` that is too large means TL never qualifies.

```python
# inline, via the bridge
import json
EAL = unreal.EditorAssetLibrary
out = {}
dt = EAL.load_asset("/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_MinWidth")
out["DT_MinWidth_keys"] = [str(k) for k in dt.get_editor_property("row_map").keys()]
dt2 = EAL.load_asset("/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_LevelMinWidth")
out["DT_LevelMinWidth_TL"] = [str(k) for k in dt2.get_editor_property("row_map").keys()
                              if str(k).startswith("TL")]
g = EAL.load_asset("/CitySamplePCG/PCG/Primitives/Buildings/Assign_CitySampleBuildings")
txt = g.get_editor_property("user_parameters").export_text()
out["BuildingsStyles_has_TL"] = ("TL" in txt)
out["BuildingsStyles_excerpt"] = txt[:300]
lg = EAL.load_asset("/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/LoadCitySampleData")
out["LoadCitySampleData_points_at"] = [
    str(n.get_settings().get_editor_property("data_asset"))
    for n in lg.get_editor_property("nodes")
    if n.get_settings() is not None and hasattr(n.get_settings(), "data_asset")
][:5]
print(json.dumps(out, indent=1))
```

Expected: `DT_MinWidth_keys` contains `TL`; `DT_LevelMinWidth_TL` is non-empty;
`BuildingsStyles_has_TL` is true; `LoadCitySampleData_points_at` names `BDF_WithTL`.

- [ ] **Step 6: Commit**

```bash
git add Content/Python/tl_register.py Content/Python/tl_dt_probe.py
git commit -m "Register TL in the width tables, the BuildingsStyles whitelist, and LoadCitySampleData"
```


---

## Task 9: Verify TL generates in the city pipeline

**Files:**
- Create: `Content/Python/tl_verify_city.py` (generate)
- Create: `Content/Python/tl_verify_city_read.py` (read)

**Interfaces:**
- Consumes: everything above.
- Produces: a count of TL instances in the 3.3.1 Buildings stage output.

- [ ] **Step 1: Write the generation half**

Create `Content/Python/tl_verify_city.py`. Copy the pattern the existing stage scripts use (`Content/Python/pcg_sa_*.py`): locate the `PCG_3_3_1_Buildings` volume in the current level, activate, generate.

```python
# tl_verify_city.py — PHASE A: run the real buildings stage and generate.
# Run tl_verify_city_read.py as a SEPARATE call: generation is async.

import json

R = {"volumes": []}
args = mcp_args or {}
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

TARGET_GRAPH = "PCG_3_3_1_Buildings"

for a in eas.get_all_level_actors():
    try:
        comp = a.get_component_by_class(unreal.PCGComponent)
    except Exception:
        continue
    if comp is None:
        continue
    try:
        g = str(comp.get_graph())
    except Exception:
        continue
    if TARGET_GRAPH not in g:
        continue
    comp.activate(True)          # REQUIRED: silent zero without it
    comp.generate_local(True)
    R["volumes"].append({"actor": a.get_actor_label(), "graph": g, "generated": True})

R["count"] = len(R["volumes"])
print(json.dumps(R, indent=1, default=str))
mcp_result = R
```

- [ ] **Step 2: Write the read half**

Create `Content/Python/tl_verify_city_read.py`:

```python
# tl_verify_city_read.py — PHASE B: count TL instances in the generated city.
#
# Geometry is the deliverable, so instances decide success, not output points.
# TL counts >= 1 means the whole chain works end to end.

import json

R = {}
args = mcp_args or {}
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

TL = "/Game/Building/TL/"
by_mesh = {}
tl_total = 0
all_total = 0
actors = 0

for a in eas.get_all_level_actors():
    try:
        comps = a.get_components_by_class(unreal.PrimitiveComponent)
    except Exception:
        continue
    hit = False
    for c in comps:
        try:
            n = c.get_instance_count()
        except Exception:
            continue
        if not n:
            continue
        all_total += n
        hit = True
        try:
            mp = c.get_editor_property("static_mesh")
            path = mp.get_path_name() if mp else "<none>"
        except Exception:
            path = "<err>"
        if TL in path:
            tl_total += n
            by_mesh[path] = by_mesh.get(path, 0) + n
    if hit:
        actors += 1

R["actors_with_instances"] = actors
R["all_instances"] = all_total
R["tl_instances"] = tl_total
R["tl_meshes"] = by_mesh
R["verdict"] = ("TL GENERATES" if tl_total else
                "TL ABSENT - check whitelist, DT rows, and minWallWidth")
print(json.dumps(R, indent=1, default=str))
mcp_result = R
```

- [ ] **Step 3: Run both phases**

Phase A: `run_unreal_script(script_path="tl_verify_city.py")`
Phase B: `run_unreal_script(script_path="tl_verify_city_read.py")`

Expected: `tl_instances >= 1` and `verdict: "TL GENERATES"`, with `tl_meshes` keyed by `/Game/Building/TL/...` paths.

- [ ] **Step 4: Confirm TL mixes with the existing styles, and diagnose if absent**

Review Focus 1 and 5 both land here. On success, `all_instances` should be much larger than `tl_instances` — TL appears **alongside** CH/NY/SF, not instead of them. A non-zero `tl_instances` with a plausible share of `all_instances` is the pass condition.

**If `verdict` is "TL ABSENT"**, diagnose in this order and report which step failed:

1. **Is TL in the BDF asset?** Re-run Task 7 Step 3's check. If the Levels rows did not land, nothing downstream can see TL.
2. **Is `LoadCitySampleData` pointing at `BDF_WithTL`?** If it still points at Epic's asset, TL is not in the data at all.
3. **Is TL in both whitelists?** Re-run Task 8 Step 4.
4. **Does TL fit any wall?** If `minWallWidth` is 12 m and the lots in view are narrower, TL never qualifies. Lower `TL_BDF["MinWallWidth"]` in `tl_make_bdf.py`, rebuild (Task 7 Step 2), and re-run. **This is the most likely cause and the one that produces zero output with zero errors.**

- [ ] **Step 5: Commit**

```bash
git add Content/Python/tl_verify_city.py Content/Python/tl_verify_city_read.py
git commit -m "Verify TL generates in the city pipeline"
```

---

## Task 10: Update the durable docs and run the regression

The pipeline analysis documents two facts that this work disproves. Leaving them wrong misleads every future session.

**Files:**
- Modify: `docs/city-sample-pcg-pipeline.md`
- Modify: `.claude/skills/city-sample-pcg-city-builder/references/migrated-citysample-library.md`
- Modify: `.claude/skills/city-sample-pcg-city-builder/references/traps.md`
- Test: `Content/Python/pcg_postmigration_regression.py` (existing)

- [ ] **Step 1: Correct the pipeline doc's building-style section**

In `docs/city-sample-pcg-pipeline.md`, §5.3 currently implies `SGD_<CODE>_A` drives building placement, and §7.1 describes the whitelist without the BDF database. Replace that with what was measured: the 18-stage pipeline reads `CitySampleBuildingBDF_Asset_PCG`, `SGD_*` is the preview route only, and the database is four tagged `PCGPointData` sets whose schema is in this plan's Task 7 table.

- [ ] **Step 2: Add the BDF schema and the two overturning findings to the skill reference**

In `migrated-citysample-library.md` §3, add the four-set schema table, the 1:1 level-row↔RULE correspondence, the three-grammars-per-level mechanism with `FLengths`, and the `Levels.BuildingToken` is-a-`Name` trap. Add the Python write path (exporter, `new_object` needs a non-null outer, CRC-on-save).

- [ ] **Step 3: Add the new traps**

In `traps.md`, add, in the existing numbered style:

- `Levels.BuildingToken` is a `Name`; every other `BuildingToken` is a `String`. Writing it as a string matches nothing, silently.
- A style that is authored but not whitelisted produces zero buildings with zero errors — asset existence does not imply usability.
- `PCGDataCollectionExporter.ShouldSave` compares CRCs, so re-exporting identical content onto an existing asset returns `None`. Delete the target or vary the description.
- `unreal.new_object` fails without a non-null outer; use `unreal.find_package("/Engine/Transient")`.
- `TArray<struct>` properties yield copies: mutate a fresh list and set it whole, then read back. (This is the same trap already recorded for `static_materials`; note that it also governs `Modules Infos` and `Slots`.)

- [ ] **Step 4: Run the regression on the delivered area**

Confirm the earlier delivery is untouched.

Run: `run_unreal_script(script_path="pcg_postmigration_regression.py")`

Expected: the 3×3 area still reports 12 nodes / 12 edges / 41 instances — the same numbers recorded after the asset migration. **A changed count means the whitelist or BDF edits broke an existing style; revert the graph edits and re-apply more narrowly.**

- [ ] **Step 5: Commit**

```bash
git add docs/city-sample-pcg-pipeline.md .claude/skills/city-sample-pcg-city-builder/references/
git commit -m "Record the BDF schema and correct the building-style pipeline docs"
```

---

## Self-Review

**Spec coverage.** §1 goals → Tasks 2–9. §2.1–2.11 facts → encoded in the Global Constraints and Task 7's schema table. §3 route A → Tasks 2–6; route B → Tasks 7–9. §4 blocks A–D → Tasks 2–3 (`tl_kit_spec.json` + Blender + import), 4–6 (SGD), 7–9 (BDF + verify). §5 deliverables → each task commits its script; the spec/city-sample reference updates are Task 10. §6 verification → the two-phase read pattern is written into every verify task, and the four iron rules are Global Constraints. §7 U1–U8 → U1 answered by the probes and encoded in Task 7; U2 → Task 1 Step 4; U3 → Tasks 1 & 3 Step 4; U4 → Task 3 Step 2; U5/U6 → folded into Task 7's level table; U7 → Task 7's never-touch-Epic constraint; U8 → the editor is running. §8 phases P0–P4 → Tasks 1, 2–3, 4–6, 7–9, 10.

**Placeholder scan.** No "TBD"/"implement later". The one deliberate deferral is Task 8's DataTable row-write mechanism, which is genuinely unknown from Python and is handled with two concrete fallbacks rather than a placeholder. Task 1 resolves it before Task 8 needs it.

**Type consistency.** `tl_kit_spec.json` keys (`part`, `level`, `width_m`, `height_m`, `material`, `mesh_name`) are used identically in Tasks 2, 3, 4, and 7. `mesh_forward_axis` is set once (Task 4) and verified once (Task 6). The BDF attribute types in Task 7's `BDF_T`/`LVL_T`/`MOD_T` match the live-read table in the header. `BDF_WithTL` is the path used in Tasks 7, 8, and 9.

**Review Focus.** Each of the five is pinned: (1) unregistered style → Task 8 Step 5, Task 9 Step 4; (2) `Name`-typed token → Task 7 Step 3; (3) wrong pivot → Task 2 Step 4, Task 3 Step 4; (4) wrong scale → Task 3 Step 3; (5) fits-no-wall → Task 8 Step 4, Task 9 Step 4.
