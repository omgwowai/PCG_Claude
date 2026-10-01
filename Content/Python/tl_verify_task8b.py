# tl_verify_task8b.py — correct the original-intact check for the level table.
#
# DT_Bldg_LevelMinWidth names its rows "<CODE>_LV<n>", not bare "<CODE>", so a
# check for the bare token reports every original as missing. Check by PREFIX.

import json

R = {}
args = mcp_args or {}
EAL = unreal.EditorAssetLibrary

CODES = ["CHA", "CHB", "CHC", "CHD", "CHE", "CHF", "CHG", "CHH", "CHI", "CHJ",
         "NYAA", "NYAB", "NYAC", "NYAD", "NYAE", "NYAF", "NYG", "NYGA", "NYH",
         "QBA", "QBAA", "SFA", "SFB", "SFC", "SFD", "SFE", "SFJ"]

DT_LVL = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_LevelMinWidth"
dt = EAL.load_asset(DT_LVL)
rows = [str(x) for x in dt.get_row_names()]
R["row_count"] = len(rows)

# which codes appear as a row-name prefix?
present = set()
for c in CODES:
    if any(r == c or r.startswith(c + "_") for r in rows):
        present.add(c)
R["codes_present_count"] = len(present)
R["missing_codes"] = sorted(set(CODES) - present)
R["all_originals_present"] = (len(present) == len(CODES))

# level-row counts per code, to confirm nothing was truncated
per_code = {}
for r in rows:
    for c in sorted(CODES, key=len, reverse=True):
        if r == c or r.startswith(c + "_"):
            per_code[c] = per_code.get(c, 0) + 1
            break
R["per_code_row_counts"] = dict(sorted(per_code.items()))
R["TL_row_count"] = per_code.get("TL")

# spot-check the L00 row-name convention against TL's own rows
R["TL_rows"] = sorted([r for r in rows if r.startswith("TL")])
R["sample_other_rows"] = sorted([r for r in rows if r.startswith("CHA")])[:6]
R["sample_sfa_rows"] = sorted([r for r in rows if r.startswith("SFA")])[:6]

# and confirm the min-width table's originals too (bare-code names there)
dt2 = EAL.load_asset("/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_MinWidth")
rows2 = [str(x) for x in dt2.get_row_names()]
R["minwidth_row_count"] = len(rows2)
R["minwidth_missing"] = sorted([c for c in CODES if c not in rows2])

print(json.dumps(json.loads(json.dumps(R, default=str)), indent=1)[:4000])
mcp_result = json.loads(json.dumps(R, default=str))
