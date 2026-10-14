#!/usr/bin/env python
"""Generate a first-draft stage file from an official graph's IR.

The draft is mechanical: one statement per node in dependency order, all in step 0. A curator
then splits it into the Feishu doc's steps (plan Tasks 9-17); test_stages_l1.py keeps it exact.

    python Tools/pypcg/codegen.py --stage 5            # writes s05_*.py unless it exists
    python Tools/pypcg/codegen.py --stage all --force
"""
import argparse
import json
import keyword
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "Content", "Python"))

from pypcg import compare, ir as pir, stages  # noqa: E402

_SEL = re.compile(r"^PCGBegin\((.*)\)PCGEnd$", re.S)
RESERVED = {"title", "set", "settings", "loop", "defaults", "src", "roles", "tag", "path", "pins",
            "comment", "bubble_visible", "bubble_pinned", "title_color", "name", "use", "alias", "cls"}
_TAKEN = {"g", "sel", "P", "D", "NodeRef", "Graph", "SIZES", "knob", "build"}


def snake(text):
    s = re.sub(r"[^0-9A-Za-z]+", "_", text or "").strip("_").lower()
    if not s:
        s = "node"
    if s[0].isdigit():
        s = "n_" + s
    if keyword.iskeyword(s) or s in _TAKEN:
        s += "_"
    return s


def unique(base, used):
    name, k = base, 2
    while name in used:
        name = "%s_%d" % (base, k)
        k += 1
    used.add(name)
    return name


def lit(v, names):
    if isinstance(v, str):
        m = _SEL.match(v)
        return "sel(%r)" % m.group(1) if m else repr(v)
    if v is None or isinstance(v, (bool, int, float)):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(lit(x, names) for x in v) + "]"
    if isinstance(v, dict):
        if set(v) == {"node_ref"}:
            return "NodeRef(%s)" % names[v["node_ref"]]
        return "{" + ", ".join("%r: %s" % (k, lit(x, names)) for k, x in v.items()) + "}"
    raise TypeError(repr(v))


def port(src, pin, names):
    base = "g.input" if src == pir.IN_NODE else names[src]
    if pin == "Out" and src != pir.IN_NODE:
        return base
    if pin.isidentifier() and not keyword.iskeyword(pin) and pin not in ("name", "use"):
        return "%s.%s" % (base, pin)
    return "%s[%r]" % (base, pin)


def ports(edges, names):
    val = [port(s, p, names) for s, p in edges]
    return val[0] if len(val) == 1 else "[" + ", ".join(val) + "]"


def pin_args(inputs, names, skip=()):
    kwargs, pins = [], []
    for label, edges in inputs:
        if label in skip:
            continue
        expr = ports(edges, names)
        if label.isidentifier() and not keyword.iskeyword(label) and label not in RESERVED:
            kwargs.append("%s=%s" % (label, expr))
        else:
            pins.append("%r: %s" % (label, expr))
    if pins:
        kwargs.append("pins={" + ", ".join(pins) + "}")
    return kwargs


def common(f, names):
    out = []
    if f["comment"]:
        out.append("comment=%r" % f["comment"])
        if not f["bubble_visible"]:
            out.append("bubble_visible=False")
    elif f["bubble_visible"]:
        out.append("bubble_visible=True")
    if f["bubble_pinned"]:
        out.append("bubble_pinned=True")
    if f["title_color"] is not None:
        out.append("title_color=%s" % lit(list(f["title_color"]), names))
    return out


def order(view, ir_nodes):
    todo = [n["name"] for n in ir_nodes if n["name"] not in pir.IO_NODES]
    deps = {n: set() for n in todo}
    for n in todo:
        for _, edges in view[n]["inputs"]:
            deps[n].update(s for s, _ in edges if s in deps)
        deps[n].update(r for r in compare.refs(view[n]["fields"]["settings"]) if r in deps)
    done, out = set(), []
    while len(out) < len(todo):
        ready = next((n for n in todo if n not in done and deps[n] <= done), None)
        if ready is None:
            raise ValueError("cycle among %s" % sorted(set(todo) - done))
        out.append(ready)
        done.add(ready)
    return out


def _is_usage(n):
    decl = n["fields"]["settings"].get("Declaration")
    return (isinstance(decl, dict) and set(decl) == {"node_ref"}
            and n["inputs"] == [("In", [(decl["node_ref"], "InvisiblePin")])])


def statement(name, n, names, roles_by_path, view):
    f = n["fields"]
    cls, title = f["class"], f["title"]
    settings, overrides = dict(f["settings"]), dict(f["overrides"])
    head, args, skip, notes = [], [], set(), []
    if settings.get("bEnabled") is False:
        notes.append("# 不生效：节点已禁用")
    if f["subgraph"]:
        alias = pir.alias_of(f["subgraph"])
        wired = {label for label, _ in n["inputs"]}
        for k in sorted(set(overrides) & wired):
            notes.append("# 不生效：set.%s 被同名 pin 的输入顶掉" % k)
        if alias == "Get_ActorData" and "ActorTag" in overrides and cls == "PCGSubgraphSettings":
            method, head = "actor_by_tag", [repr(overrides.pop("ActorTag"))]
        elif alias == "Get_ActorDataByRef" and "ActorReferences" in overrides and cls == "PCGSubgraphSettings":
            roles = [roles_by_path[p] for p in overrides.pop("ActorReferences")]
            method, head = "ref", [repr(roles[0]) if len(roles) == 1 else repr(roles)]
        else:
            method, head = ("loop" if cls == "PCGLoopSettings" else "sub"), [repr(alias)]
        if title:
            head.append(repr(title))
        if overrides:
            args.append("set=%s" % lit(overrides, names))
        if settings:
            args.append("settings=%s" % lit(settings, names))
        call = "g.%s(" % method
    elif cls == "PCGUserParameterGetSettings":
        head = [repr(f["getter_param"])] + ([repr(title)] if title else [])
        if settings:
            args.append("set=%s" % lit(settings, names))
        call = "g.param("
    elif cls == "PCGGenericUserParameterGetSettings" and "PropertyPath" in settings:
        head = [repr(settings.pop("PropertyPath"))] + ([repr(title)] if title else [])
        if settings:
            args.append("set=%s" % lit(settings, names))
        call = "g.param_path("
    elif cls == "PCGNamedRerouteDeclarationSettings":
        # Ruling P2: every declaration becomes g.declare(), titled or not, so its usages can
        # always be written as <decl>.use().
        head = [repr(title)]
        src = dict(n["inputs"]).get("In")
        if src:
            head.append(ports(src, names))
            skip.add("In")
        if settings:
            args.append("set=%s" % lit(settings, names))
        call = "g.declare("
    elif cls == "PCGNamedRerouteUsageSettings" and _is_usage(n):
        decl = settings.pop("Declaration")["node_ref"]
        skip.add("In")
        if title != view[decl]["fields"]["title"]:
            head = [repr(title)]
        if settings:
            args.append("set=%s" % lit(settings, names))
        call = "%s.use(" % names[decl]
    elif cls == "PCGRerouteSettings" and [label for label, _ in n["inputs"]] == ["In"]:
        head = [ports(dict(n["inputs"])["In"], names)] + ([repr(title)] if title else [])
        skip.add("In")
        if settings:
            args.append("set=%s" % lit(settings, names))
        call = "g.reroute("
    else:
        head = [repr(cls)] + ([repr(title)] if title else [])
        if settings:
            args.append("set=%s" % lit(settings, names))
        if f["pin_defaults"]:
            ds = []
            for d in f["pin_defaults"]:
                parts = [str(d["index"])]
                if d["type"] is not None or d["value"] is not None:
                    parts += [repr(d["type"]), lit(d["value"], names)]
                if not d["activated"]:
                    parts.append("activated=False")
                ds.append("D(%s)" % ", ".join(parts))
            args.append("defaults=[%s]" % ", ".join(ds))
        call = "g.node("
    args += common(f, names) + pin_args(n["inputs"], names, skip)
    lines = ["        " + x for x in notes]
    lines.append("        %s = %s%s)" % (names[name], call, ", ".join(head + args)))
    return lines


def generate(official_ir, roles_by_path, fresh_seeds, stage_title=""):
    view = compare.view(official_ir, fresh_seeds)
    seq = order(view, official_ir["nodes"])
    used, names = set(), {}
    for name in seq:
        f = view[name]["fields"]
        base = f["title"] or (pir.alias_of(f["subgraph"]) if f["subgraph"] else f["class"].replace("PCG", "").replace("Settings", ""))
        names[name] = unique(snake(base), used)
    graph_name = official_ir["graph"].rsplit("/", 1)[-1].split(".")[0]
    n_nodes = len(official_ir["nodes"])
    n_edges = sum(len(p["edges"]) for x in official_ir["nodes"] for p in x["inputs"])
    params = []
    for p in official_ir.get("params", []):
        extra = []
        for key, default in (("container", "None"), ("type_object", ""), ("category", "")):
            if p.get(key, default) != default:
                extra.append("%s=%r" % (key, p[key]))
        tip = compare.tooltip_of(p)
        if tip:
            extra.append("tooltip=%r" % tip)
        meta = {k: v for k, v in (p.get("meta") or {}).items() if k not in compare.IGNORED_META}
        if meta:
            extra.append("meta=%r" % meta)
        params.append("P(%s)" % ", ".join([repr(p["name"]), repr(p["type"]), lit(p["value"], names)] + extra))
    io = {x: view[x]["fields"]["settings"] for x in pir.IO_NODES}
    head = ["    g = Graph(%r," % graph_name,
            "              params=[%s]," % (",\n                      ".join(params)),
            "              graph_props=%s%s)" % (lit(official_ir.get("graph_props") or {}, names),
                                                 "".join(", %s=%s" % (k, lit(io[n], names)) for k, n in
                                                         (("input_settings", pir.IN_NODE), ("output_settings", pir.OUT_NODE)) if io[n]))]
    body = ['    with g.step(0, "未整理"):']
    for name in seq:
        body += statement(name, view[name], names, roles_by_path, view)
    out_edges = dict(view[pir.OUT_NODE]["inputs"]).get("Out", [])
    tail = []
    if out_edges:
        tail = ["    g.out(%s)" % ", ".join(port(s, p, names) for s, p in out_edges)]
    doc = ['"""%s —— %s（CODEGEN DRAFT：尚未按飞书文档分步整理）' % (graph_name, stage_title),
           "",
           "官方 %d 节点 / %d 边。由 Tools/pypcg/codegen.py 生成；整理规则见 docs/pypcg-guide.md。" % (n_nodes, n_edges),
           '"""',
           "from pypcg import D, Graph, NodeRef, P, sel  # noqa: F401",
           "",
           "",
           "def build():"]
    return "\n".join(doc + head + body + tail + ["    return g", ""])


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    from pypcg.profiles import official
    lib = json.load(open(os.path.join(REPO, "Content", "Python", "pypcg", "library.json"), encoding="utf-8"))
    roles_by_path = {p: r for r, p in official.ROLES.items()}
    wanted = [s[0] for s in stages.STAGES] if a.stage == "all" else [int(a.stage)]
    for n in wanted:
        _, graph_name, module, title = stages.entry(n)
        out = os.path.join(REPO, "Content", "Python", "pypcg", "stages", module + ".py")
        if os.path.exists(out) and not a.force:
            print("skip (exists)", out)
            continue
        snap = pir.load(os.path.join(REPO, "Tools", "pypcg", "official_ir", graph_name + ".json"))
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(generate(snap, roles_by_path, lib["fresh_seeds"], title))
        print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
