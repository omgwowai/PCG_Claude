# pcg_asset_rescan.py - can the RUNNING editor register the copied content
# without a restart?
#
# Why this matters: the editor process (PID 40444) hosts the only MCP tool this
# session has. Restarting it to pick up new plugins risks losing that tool, so
# first find out how much can be picked up live. Plugin mount points genuinely
# need a restart, but /Game content is on a mount that already exists, so an
# asset-registry rescan may be enough for the art.
#
# Reports before/after counts so the effect is measured, not assumed.

import json

R = {}
def S(x):
    return str(x)

EAL = unreal.EditorAssetLibrary

# ---- before ----
def count(path):
    try:
        return len(EAL.list_assets(path, recursive=True, include_folder=False))
    except Exception as e:
        return "ERR %s" % type(e).__name__

BEFORE = {}
for p in ("/Game", "/Game/Building", "/Game/Prop", "/Game/Crowd",
          "/Game/Megascans", "/Game/Material", "/Game/Road", "/CitySamplePCG"):
    BEFORE[p] = count(p)
R["before"] = BEFORE

# ---- can these specific assets load? (disk-present but maybe unregistered) ----
LOAD_BEFORE = {}
for p in ("/Game/Building/Library/Building_Shapes/BLDG_Volume_C",
          "/Game/Building/CH/A/Kit_Bldg_CHA_L10_A/Mesh/SM_BLDG_CHA_L10_A_Wall_01_N1",
          "/Game/Prop/Kit_roof_exhaust_RR/Mesh/SM_roof_pipe_a_N1"):
    try:
        a = EAL.load_asset(p)
        LOAD_BEFORE[p] = a.get_class().get_name() if a else None
    except Exception as e:
        LOAD_BEFORE[p] = "ERR %s" % type(e).__name__
R["load_before"] = LOAD_BEFORE

# ---- attempt a rescan ----
S1 = {}
try:
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    S1["class"] = ar.get_class().get_name()
    S1["scan_methods"] = [m for m in dir(ar) if "scan" in m.lower() or "search" in m.lower()]
    try:
        ar.scan_paths_synchronous(["/Game"], True, True)
        S1["scan_paths_synchronous"] = "called"
    except Exception as e:
        S1["scan_paths_synchronous"] = "ERR %s: %s" % (type(e).__name__, S(e)[:150])
    try:
        ar.scan_modified_assets(True)
        S1["scan_modified_assets"] = "called"
    except Exception as e:
        S1["scan_modified_assets"] = "ERR %s" % type(e).__name__
except Exception as e:
    S1["err"] = "%s: %s" % (type(e).__name__, S(e)[:150])
R["rescan"] = S1

# ---- after ----
AFTER = {}
for p in ("/Game", "/Game/Building", "/Game/Prop", "/Game/Crowd",
          "/Game/Megascans", "/Game/Material", "/Game/Road", "/CitySamplePCG"):
    AFTER[p] = count(p)
R["after"] = AFTER

LOAD_AFTER = {}
for p in ("/Game/Building/Library/Building_Shapes/BLDG_Volume_C",
          "/Game/Building/CH/A/Kit_Bldg_CHA_L10_A/Mesh/SM_BLDG_CHA_L10_A_Wall_01_N1",
          "/Game/Prop/Kit_roof_exhaust_RR/Mesh/SM_roof_pipe_a_N1"):
    try:
        a = EAL.load_asset(p)
        LOAD_AFTER[p] = a.get_class().get_name() if a else None
    except Exception as e:
        LOAD_AFTER[p] = "ERR %s" % type(e).__name__
R["load_after"] = LOAD_AFTER

R["delta"] = {}
for k in BEFORE:
    try:
        R["delta"][k] = AFTER[k] - BEFORE[k]
    except Exception:
        R["delta"][k] = "n/a"

print("rescan: before=%s after=%s" % (json.dumps(BEFORE), json.dumps(AFTER)))
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
