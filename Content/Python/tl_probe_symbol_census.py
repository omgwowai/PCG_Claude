# tl_probe_symbol_census.py -- READ-ONLY. Every distinct Modules.Symbol across all
# styles in BDF_WithTL with how many styles use it, and every Levels F0/F1/F2
# token that is not a plain module symbol. Looks for any angle-specific corner
# symbol (anything beyond C_E / C_I / C_CE and their half pieces).
import json
import re

MA = unreal.PCGMetadataAccessorHelpers


def main():
    a = unreal.EditorAssetLibrary.load_asset("/Game/PCG/DataAssets/BDF/BDF_WithTL")
    syms, grammar_tokens = {}, {}
    for it in a.get_editor_property("data").get_editor_property("tagged_data"):
        tags = [str(t) for t in it.get_editor_property("tags")]
        d = it.get_editor_property("data").get_editor_property("data")
        md = d.mutable_metadata()
        if "Modules" in tags:
            for pt in d.get_points():
                s = MA.get_string_attribute(pt, md, "Symbol")
                st = MA.get_string_attribute(pt, md, "BuildingToken")
                syms.setdefault(s, set()).add(st)
        elif "Levels" in tags:
            for pt in d.get_points():
                st = str(MA.get_name_attribute(pt, md, "BuildingToken"))
                for f in ("F0", "F1", "F2"):
                    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", MA.get_string_attribute(pt, md, f)):
                        grammar_tokens.setdefault(tok, set()).add(st)
    corner = {k: sorted(v) for k, v in syms.items() if k.startswith(("C", "B_"))}
    return {"n_symbols": len(syms),
            "corner_like_symbols": {k: len(v) for k, v in sorted(corner.items())},
            "grammar_tokens_not_modules": sorted(set(grammar_tokens) - set(syms))}


mcp_result = json.loads(json.dumps(main(), default=str))
