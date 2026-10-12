# tl_probe_rule_export.py -- READ-ONLY. For each given shape-grammar RULE_* /
# SGD_* asset: the rule struct's export_text (grammar, ModulesInfos with every
# module's symbol / mesh / size / scalable / offsets), written to
# Saved/graph_dumps/rules_<name>.txt. Returns sizes plus the grammar strings.
# Args: {"assets": ["<asset path>", ...]}
import json
import os
import re

args = mcp_args or {}
OUT = os.path.join(unreal.Paths.project_saved_dir(), "graph_dumps")


def main():
    res = []
    for p in args.get("assets", []):
        a = unreal.EditorAssetLibrary.load_asset(p)
        if a is None:
            res.append({"asset": p, "error": "not loadable"})
            continue
        texts = {}
        for prop in ("rule", "Slots", "Main Grammar", "Use Grammar", "Description"):
            try:
                v = a.get_editor_property(prop)
            except Exception:
                continue
            if hasattr(v, "export_text"):
                texts[prop] = v.export_text()
            elif isinstance(v, (list, tuple)):
                texts[prop] = "[" + ",\n".join(x.export_text() if hasattr(x, "export_text") else str(x) for x in v) + "]"
            else:
                texts[prop] = str(v)
        name = p.rsplit("/", 1)[-1]
        path = os.path.join(OUT, "rules_%s.txt" % name)
        with open(path, "w", encoding="utf-8") as f:
            for k, v in texts.items():
                f.write("### %s\n%s\n\n" % (k, v))
        grammar = re.findall(r'grammar_\w+="([^"]*)"', "\n".join(texts.values()))
        res.append({"asset": p, "class": a.get_class().get_name(), "file": path,
                    "props": list(texts), "grammar": grammar[:6],
                    "main_grammar": texts.get("Main Grammar")})
    return res


mcp_result = json.loads(json.dumps(main(), default=str))
