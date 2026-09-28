# tl_probe_cleanup2.py — force GC then delete the two remaining probe assets.
#
# delete_asset returned False because the objects are still referenced in memory.
# Collect garbage first, then retry. Epic's source asset is confirmed pristine.

import json
import os

R = {}
args = mcp_args or {}
EAL = unreal.EditorAssetLibrary

# ---------- drop references, then collect --------------------------------
for gcfn in ("collect_garbage", "CollectGarbage"):
    fn = getattr(unreal.SystemLibrary, gcfn, None)
    if fn is None:
        continue
    try:
        fn()
        R["gc"] = gcfn
        break
    except Exception as e:
        R["gc_err"] = "%s: %s" % (type(e).__name__, e)

# ---------- retry the deletes --------------------------------------------
results = {}
for p in ("/Game/PCGTest/BDF_DupProbe", "/Game/PCGTest/BDF_PersistProbe"):
    rec = {}
    try:
        rec["existed"] = EAL.does_asset_exist(p)
        rec["deleted"] = EAL.delete_asset(p)
        rec["gone"] = not EAL.does_asset_exist(p)
    except Exception as e:
        rec["err"] = "%s: %s" % (type(e).__name__, e)
    results[p] = rec
R["delete_results"] = results

# ---------- filesystem state --------------------------------------------
d = "E:/PCG_Claude/Content/PCGTest"
try:
    R["remaining"] = sorted(os.listdir(d)) if os.path.isdir(d) else None
except Exception as e:
    R["fs_err"] = "%s: %s" % (type(e).__name__, e)

print(json.dumps(R, indent=1, default=str))
mcp_result = R
