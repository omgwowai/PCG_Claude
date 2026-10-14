"""Structural comparison of two graph IRs (spec section 3.5). No unreal import.

Nodes are paired by a bijection found with colour refinement plus individualisation, never by
object name, so a Python-built graph compares equal to the official one when every class,
title, comment, non-default setting, subgraph override, pin default, getter binding and
input edge (in per-pin order) matches.
"""
from . import ir as _ir

NODE_FIELDS = ("class", "title", "title_color", "comment", "bubble_visible", "bubble_pinned",
               "settings", "subgraph", "overrides", "pin_defaults", "getter_param")
_DEFAULTS = {"title": "", "title_color": None, "comment": "", "bubble_visible": False,
             "bubble_pinned": False, "settings": {}, "subgraph": "", "overrides": {},
             "pin_defaults": [], "getter_param": ""}
PARAM_FIELDS = ("name", "type", "container", "type_object", "value", "category", "tooltip", "meta")
IGNORED_META = ("Category", "ToolTip")      # carried by the hierarchy instead (ruling R5)
_WHITE = (1.0, 1.0, 1.0, 1.0)
_MISSING = object()                         # sentinel: key absent, distinct from an explicit None
_INDIVIDUALISED = [0]                       # bumped each time match() breaks a symmetric tie


def canon(v):
    """Hashable, type-aware form: True != 1, but 100000 == 100000.0."""
    if isinstance(v, bool):
        return ("b", v)
    if isinstance(v, (int, float)):
        return ("n", float(v))
    if isinstance(v, str):
        return ("s", v)
    if v is None:
        return ("z",)
    if isinstance(v, (list, tuple)):
        return ("l",) + tuple(canon(x) for x in v)
    if isinstance(v, dict):
        return ("d",) + tuple(sorted((str(k), canon(x)) for k, x in v.items()))
    raise TypeError("not JSON: %r" % (v,))


def _canon_or_missing(v):
    """canon(v), but _MISSING compares distinct from any real value, including None."""
    return ("missing",) if v is _MISSING else canon(v)


def _render(v):
    """Display form for a diff record's "a"/"b": _MISSING reads as the literal string below."""
    return "<missing>" if v is _MISSING else v


def refs(value, out=None):
    """Node names referenced by {"node_ref": name} anywhere inside value."""
    out = [] if out is None else out
    if isinstance(value, dict):
        if set(value) == {"node_ref"}:
            out.append(value["node_ref"])
        else:
            for v in value.values():
                refs(v, out)
    elif isinstance(value, list):
        for v in value:
            refs(v, out)
    return out


def _blank_refs(value):
    if isinstance(value, dict):
        if set(value) == {"node_ref"}:
            return {"node_ref": "?"}
        return {k: _blank_refs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_blank_refs(v) for v in value]
    return value


def _rename_refs(value, mapping):
    if isinstance(value, dict):
        if set(value) == {"node_ref"}:
            return {"node_ref": mapping.get(value["node_ref"], "?" + value["node_ref"])}
        return {k: _rename_refs(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [_rename_refs(v, mapping) for v in value]
    return value


def tooltip_of(param):
    if "tooltip" in param:
        return param["tooltip"] or ""
    for v in (param.get("hier_meta") or {}).get("Values", []):
        if str(v.get("_structType", "")).endswith("PropertyBagPropertyMetadata_Common"):
            return v.get("Tooltip") or ""
    return ""


def _param(p):
    out = {k: p.get(k, "") for k in ("name", "type", "container", "type_object", "category")}
    out["value"] = p.get("value", _MISSING)
    out["tooltip"] = tooltip_of(p)
    out["meta"] = {k: v for k, v in (p.get("meta") or {}).items() if k not in IGNORED_META}
    return out


def _pin_default(d):
    return {"index": d["index"], "activated": bool(d.get("activated")),
            "type": d.get("type"), "value": d.get("value")}


def view(ir, fresh_seeds):
    """Normalised per-node fields: node_refs by name, fresh seeds dropped, defaults filled."""
    graph = ir.get("graph", "")
    nodes = {}
    for n in ir["nodes"]:
        f = {k: n.get(k, _DEFAULTS.get(k)) for k in NODE_FIELDS}
        if f["title_color"] is not None and tuple(float(c) for c in f["title_color"]) == _WHITE:
            f["title_color"] = None
        settings = _ir.node_refs_to_names(dict(f["settings"] or {}), graph)
        seed = fresh_seeds.get(f["class"])
        if seed is not None and settings.get("Seed") == seed:
            settings.pop("Seed")
        f["settings"] = settings
        f["overrides"] = dict(f["overrides"] or {})
        f["pin_defaults"] = sorted((_pin_default(d) for d in f["pin_defaults"] or []), key=lambda d: d["index"])
        f["subgraph"] = f["subgraph"] or ""
        f["getter_param"] = f["getter_param"] or ""
        inputs = [(p["label"], [tuple(e) for e in p["edges"]]) for p in n.get("inputs", []) if p.get("edges")]
        if n["name"] in nodes:
            raise ValueError("duplicate node name %r" % (n["name"],))
        nodes[n["name"]] = {"fields": f, "inputs": inputs, "pos": n.get("pos"),
                            "where": n.get("src") or n.get("title") or n["name"], "step": n.get("step")}
    return nodes


def match(va, vb):
    """Pair node names of view va with view vb: (mapping a->b, unmatched_a, unmatched_b)."""
    sides = {"a": va, "b": vb}
    color = {}
    outs = {}
    ids = {}

    def intern(key):
        """Small sequential ints for colours: hash() can collide (hash(-1) == hash(-2) in
        CPython), which would silently merge two structurally different nodes into one colour."""
        return ids.setdefault(key, len(ids))

    for s, v in sides.items():
        for name, n in v.items():
            color[(s, name)] = intern(("io", name)) if name in _ir.IO_NODES else intern(canon(_blank_refs(n["fields"])))
            outs[(s, name)] = []
        for name, n in v.items():
            for label, edges in n["inputs"]:
                for i, (src, pin) in enumerate(edges):
                    if (s, src) in outs:
                        outs[(s, src)].append((pin, name, label, i))

    def refine():
        nonlocal color
        while True:
            new = {}
            for (s, name), c in color.items():
                n = sides[s][name]
                ins = sorted(((label, i, color.get((s, src)), pin)
                              for label, edges in n["inputs"] for i, (src, pin) in enumerate(edges)), key=repr)
                o = sorted(((pin, color[(s, d)], label, i) for pin, d, label, i in outs[(s, name)]), key=repr)
                r = sorted(repr(color.get((s, x))) for x in refs(n["fields"]["settings"]))
                new[(s, name)] = intern((c, tuple(ins), tuple(o), tuple(r)))
            stable = len(set(new.values())) == len(set(color.values()))
            color = new
            if stable:
                return

    refine()
    mapping, taken = {}, set()
    for io_name in _ir.IO_NODES:            # the input/output nodes always pair with each other
        if io_name in va and io_name in vb:
            mapping[io_name] = io_name
            taken.add(io_name)
    counter = 0
    while True:
        groups = {}
        for (s, name), c in color.items():
            if (s == "a" and name in mapping) or (s == "b" and name in taken):
                continue
            groups.setdefault(c, {"a": [], "b": []})[s].append(name)
        progressed = False
        ambiguous = None
        for g in groups.values():
            if len(g["a"]) == 1 and len(g["b"]) == 1:
                mapping[g["a"][0]] = g["b"][0]
                taken.add(g["b"][0])
                progressed = True
            elif g["a"] and g["b"] and (ambiguous is None or len(g["a"]) < len(ambiguous["a"])):
                ambiguous = g
        if progressed:
            continue
        if ambiguous is None:
            break
        counter += 1
        _INDIVIDUALISED[0] += 1
        a0, b0 = sorted(ambiguous["a"])[0], sorted(ambiguous["b"])[0]
        color[("a", a0)] = color[("b", b0)] = intern(("individualised", counter))
        refine()
    # Weak pass: nodes that differ in some field still pair when class, subgraph and title agree
    # (then class + subgraph), so a changed value reports as one field diff, not missing + extra.
    for key in (lambda f: (f["class"], f["subgraph"], f["title"]), lambda f: (f["class"], f["subgraph"])):
        ga, gb = {}, {}
        for name in sorted(va):
            if name not in mapping:
                ga.setdefault(key(va[name]["fields"]), []).append(name)
        for name in sorted(vb):
            if name not in taken:
                gb.setdefault(key(vb[name]["fields"]), []).append(name)
        for k, names in ga.items():
            for x, y in zip(names, gb.get(k, [])):
                mapping[x] = y
                taken.add(y)
    return mapping, sorted(set(va) - set(mapping)), sorted(set(vb) - taken)


def _members(box, nodes):
    x, y = box.get("NodePosX", 0), box.get("NodePosY", 0)
    w, h = box.get("NodeWidth", 0), box.get("NodeHeight", 0)
    return {name for name, n in nodes.items()
            if n["pos"] and x <= n["pos"][0] <= x + w and y <= n["pos"][1] <= y + h}


def diff(a, b, fresh_seeds, check_layout=False):
    """Differences of candidate `a` against reference `b`; [] means structurally equal."""
    va, vb = view(a, fresh_seeds), view(b, fresh_seeds)
    out = []

    def add(kind, where, field, av, bv):
        out.append({"kind": kind, "where": where, "field": field, "a": av, "b": bv})

    ga, gb = a.get("graph_props") or {}, b.get("graph_props") or {}
    for k in sorted(set(ga) | set(gb)):
        av = ga[k] if k in ga else _MISSING
        bv = gb[k] if k in gb else _MISSING
        if _canon_or_missing(av) != _canon_or_missing(bv):
            add("graph", "graph", "graph_props." + k, _render(av), _render(bv))
    pa, pb = [_param(p) for p in a.get("params", [])], [_param(p) for p in b.get("params", [])]
    if [p["name"] for p in pa] != [p["name"] for p in pb]:
        add("graph", "graph", "params", [p["name"] for p in pa], [p["name"] for p in pb])
    else:
        for x, y in zip(pa, pb):
            for k in PARAM_FIELDS:
                if _canon_or_missing(x[k]) != _canon_or_missing(y[k]):
                    add("graph", "graph", "params.%s.%s" % (x["name"], k), _render(x[k]), _render(y[k]))

    mapping, ua, ub = match(va, vb)
    for name in ua:
        add("extra_node", va[name]["where"], "", va[name]["fields"]["class"], None)
    for name in ub:
        add("missing_node", vb[name]["where"], "", None, vb[name]["fields"]["class"])
    for x, y in sorted(mapping.items()):
        fa, fb = va[x]["fields"], vb[y]["fields"]
        for k in NODE_FIELDS:
            if k in ("settings", "overrides"):
                for key in sorted(set(fa[k]) | set(fb[k])):
                    a_has, b_has = key in fa[k], key in fb[k]
                    av = _rename_refs(fa[k].get(key), mapping) if a_has else _MISSING
                    bv = fb[k].get(key) if b_has else _MISSING
                    if _canon_or_missing(av) != _canon_or_missing(bv):
                        add("node", va[x]["where"], "%s.%s" % (k, key), _render(av), _render(bv))
            elif canon(fa[k]) != canon(fb[k]):
                add("node", va[x]["where"], k, fa[k], fb[k])
        ia = {label: [(mapping.get(s, "?" + s), p) for s, p in edges] for label, edges in va[x]["inputs"]}
        ib = dict(vb[y]["inputs"])
        for label in sorted(set(ia) | set(ib)):
            if ia.get(label) != ib.get(label):
                add("edge", va[x]["where"], "inputs." + label, ia.get(label), ib.get(label))
        if check_layout and canon(va[x]["pos"]) != canon(vb[y]["pos"]):
            add("layout", va[x]["where"], "pos", va[x]["pos"], vb[y]["pos"])

    if check_layout:
        ba, bb = a.get("comment_boxes") or [], b.get("comment_boxes") or []
        if len(ba) != len(bb):
            add("layout", "graph", "comment_boxes", len(ba), len(bb))
        for i, (x, y) in enumerate(zip(ba, bb)):
            for k in sorted(set(x) | set(y)):
                if k != "GUID" and canon(x.get(k)) != canon(y.get(k)):
                    add("layout", "graph", "comment_boxes[%d].%s" % (i, k), x.get(k), y.get(k))
            ma = {mapping.get(n, "?" + n) for n in _members(x, va)}
            mb = _members(y, vb)
            if ma != mb:
                add("layout", "graph", "comment_boxes[%d].members" % i, sorted(ma), sorted(mb))
    return out


def undeclared_changes(ir_x, ir_y):
    """Paths that differ between two IRs of the same stage file (same node names) and are not
    covered by a role/knob site recorded in ir_x["sites"]. Used for the town build (spec 3.6)."""
    sites = [s["where"] for s in ir_x.get("sites", [])]
    changes = []
    for na, nb in zip(ir_x["nodes"], ir_y["nodes"]):
        if na["name"] != nb["name"] or na.get("class") != nb.get("class"):
            changes.append("%s.class" % na["name"])
            continue
        for field in ("settings", "overrides"):
            xa, xb = na.get(field) or {}, nb.get(field) or {}
            for k in sorted(set(xa) | set(xb)):
                if canon(xa.get(k)) != canon(xb.get(k)):
                    changes.append("%s.%s.%s" % (na["name"], field, k))
        for field in ("title", "comment", "pin_defaults", "getter_param", "subgraph", "inputs"):
            if canon(na.get(field)) != canon(nb.get(field)):
                changes.append("%s.%s" % (na["name"], field))
    if len(ir_x["nodes"]) != len(ir_y["nodes"]):
        changes.append("nodes.count")
    for p, q in zip(ir_x.get("params", []), ir_y.get("params", [])):
        if canon(p) != canon(q):
            changes.append("params.%s" % p.get("name"))

    def covered(c):
        return any(c == s or c.startswith(s + ".") or c.startswith(s + "[") or s.startswith(c + ".")
                   or s.startswith(c + "[") for s in sites)
    return [c for c in changes if not covered(c)]


def format_diffs(diffs, limit=40):
    lines = []
    for d in diffs[:limit]:
        lines.append("  %-12s %s  %s: candidate %r, reference %r"
                     % (d["kind"], d["where"], d["field"], d["a"], d["b"]))
    if len(diffs) > limit:
        lines.append("  ... %d more" % (len(diffs) - limit))
    return "\n".join(lines)
