# tl_probe_cleanup.py — remove every probe asset this session created.
#
# Probe assets created during P0 (all under /Game/PCGTest):
#   TL_ProbeRT, TL_ProbeRT2, TL_ProbeRT3, BDF_DupProbe, BDF_PersistProbe
# Also the probe graph if one got made: PCG_TL_SGD_Probe.
#
# delete_asset can fail while an object holds the asset in memory; report the
# result and the filesystem state either way.

import json
import os

R = {}
args = mcp_args or {}
EAL = unreal.EditorAssetLibrary

TARGETS = [
    "/Game/PCGTest/TL_ProbeRT",
    "/Game/PCGTest/TL_ProbeRT2",
    "/Game/PCGTest/TL_ProbeRT3",
    "/Game/PCGTest/BDF_DupProbe",
    "/Game/PCGTest/BDF_PersistProbe",
    "/Game/PCGTest/BDF_ProbeWrite",
    "/Game/PCGTest/PCG_TL_SGD_Probe",
]

results = {}
for p in TARGETS:
    rec = {}
    try:
        rec["existed"] = EAL.does_asset_exist(p)
    except Exception as e:
        rec["existed"] = "%s" % type(e).__name__
    try:
        rec["deleted"] = EAL.delete_asset(p)
    except Exception as e:
        rec["deleted"] = "%s: %s" % (type(e).__name__, e)
    try:
        rec["gone"] = not EAL.does_asset_exist(p)
    except Exception as e:
        rec["gone"] = "?"
    results[p] = rec
R["delete_results"] = results

# filesystem check: anything left behind under Content/PCGTest?
try:
    d = "E:/PCG_Claude/Content/PCGTest"
    R["pcgtest_exists"] = os.path.isdir(d)
    if os.path.isdir(d):
        R["pcgtest_files"] = sorted(os.listdir(d))
except Exception as e:
    R["fs_err"] = "%s: %s" % (type(e).__name__, e)

# confirm Epic's BDF asset is still pristine
SRC = ("E:/PCG_Claude/Plugins/CitySamplePCG/Content/PCG/Primitives/Buildings/"
       "Subgraphs/CitySampleBuildingBDF_Asset_PCG.uasset")
try:
    if os.path.isfile(SRC):
        st = os.stat(SRC)
        R["source_size"] = st.st_size
        R["source_mtime"] = st.st_mtime
        R["source_pristine"] = (st.st_size == 2958616)
except Exception as e:
    R["source_err"] = type(e).__name__

print(json.dumps(R, indent=1, default=str))
mcp_result = R
