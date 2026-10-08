# tl_probe_rule_modules.py -- READ-ONLY. Full module entries of a RULE asset
# (symbol, mesh, size, scalable, pivot) plus the non-module rule fields, and a
# listing of building material instances usable for the TL kit.
import json
import re

args = mcp_args or {}
RULES = args.get("rules", ["/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L01",
                           "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L13"])
MODULES = "ModulesInfos_38_0EA66FD04214AE8D9F6B83A1B57AC47B"


def split_top(inner):
    out, depth, start = [], 0, None
    for i, c in enumerate(inner):
        if c == "(":
            if depth == 0:
                start = i
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                out.append(inner[start:i + 1])
    return out


def field(entry, prefix):
    m = re.search(prefix + r'_\d+_[0-9A-F]{32}=("([^"]*)"|\(([^)]*)\)|([^,)]*))', entry)
    if not m:
        return None
    return m.group(2) or m.group(3) or m.group(4)


def main():
    R = {}
    EAL = unreal.EditorAssetLibrary
    for p in RULES:
        rule = EAL.load_asset(p)
        txt = rule.get_editor_property("rule").export_text()
        i = txt.find(MODULES + "=(")
        depth, j = 0, i + len(MODULES) + 1
        while j < len(txt):
            if txt[j] == "(":
                depth += 1
            elif txt[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        inner = txt[i + len(MODULES) + 2:j]
        mods = []
        for e in split_top(inner):
            mesh = field(e, "Mesh") or ""
            mods.append({"sym": field(e, "Symbol"), "size": field(e, "Size"),
                         "scal": field(e, "Scalable"), "pivot": field(e, "PivotOffset"),
                         "axis": field(e, "MeshForwardAxis"),
                         "mesh": mesh.split("/")[-1].split(".")[0].strip("'")})
        rest = txt[:i] + txt[j + 1:]
        R[p.split("/")[-1]] = {"modules": mods, "other_fields": rest[:1500]}
    mats = {}
    for root in ("/Game/Building/Material", "/Game/Building/CH/A/Material", "/Game/Building/Library"):
        if EAL.does_directory_exist(root):
            names = [a.split(".")[0].split("/")[-1] for a in EAL.list_assets(root, recursive=True, include_folder=False)]
            mats[root] = sorted(n for n in names if n.startswith(("MI_", "M_")))[:120]
    R["materials"] = mats
    return R


R = main()
mcp_result = json.loads(json.dumps(R, default=str))
