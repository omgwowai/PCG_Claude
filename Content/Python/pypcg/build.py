"""Editor only: write a stage IR into a PCG graph asset and check it (spec 3.7, L2)."""
import json

import unreal

from . import compare, extract, ir as _ir

L = unreal.PyPCGToolsLibrary
AUTO_DX, AUTO_DY = 420, 160
LAST_CDO_RESETS = []              # "node.key" reset by the last build() call (strings only; traps.md 25)


def _ok(result, what):
    if result:
        raise RuntimeError("%s: %s" % (what, result))


def _v(value):
    return json.dumps({"v": value})


def _labels(node, which):
    return [str(p.get_editor_property("properties").get_editor_property("label"))
            for p in node.get_editor_property(which)]


def _pin(node, which, label):
    for p in node.get_editor_property(which):
        if str(p.get_editor_property("properties").get_editor_property("label")) == label:
            return p
    return None


WRITABLE = "/Game/PyPCG/"          # the only tree build() may clear and rewrite (final review M1)


def check_target(path):
    """Refuse any graph path outside /Game/PyPCG/. The C++ write guard (PyPCGToolsLibrary IsProtected)
    does not see these Python-API writes, and _write CLEARS the asset before writing it."""
    if not str(path).startswith(WRITABLE):
        raise RuntimeError("refusing to write %s: pypcg.build writes only under %s" % (path, WRITABLE))


def asset(path):
    check_target(path)
    EAL = unreal.EditorAssetLibrary
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)
    pkg, name = path.rsplit("/", 1)
    g = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, pkg, unreal.PCGGraph, unreal.PCGGraphFactory())
    if g is None:
        raise RuntimeError("create_asset returned None for %s (traps.md 15)" % path)
    return g


def _clear(g):
    # remove_node one at a time: remove_nodes (plural) takes no arguments in Python (traps.md 45).
    for n in list(g.get_editor_property("nodes")):
        g.remove_node(n)
    for e in list(g.get_all_edges()):
        # PCGEdge's "output" end is the downstream node (traps.md 23).
        g.remove_edge(e.get_input_node(), e.get_input_pin_label(), e.get_output_node(), e.get_output_pin_label())
    if g.get_all_edges():
        raise RuntimeError("could not clear the edges between the input and output nodes")


def _resolve_refs(value, made):
    if isinstance(value, dict):
        if set(value) == {"node_ref"}:
            return made[value["node_ref"]].get_settings().get_path_name()
        return {k: _resolve_refs(v, made) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_refs(v, made) for v in value]
    return value


def _reset_to_class_defaults(g, ir, made):
    """The IR lists only settings that differ from the class default object, so an absent key
    means "the CDO's value". A freshly added node does not always hold it: some constructors set
    other values on new objects only (PCGExtractAttributeSettings turns
    bForceOutputAttributeToBeInElementsDomain off, while the CDO and every node saved before that
    deprecation keep it on). Copy the CDO's value into every key a node holds off-default that its
    IR does not list. Seed is excluded: an absent Seed means the fresh seed, written by build().
    Returns "node.key" strings for the report (strings only, traps.md 25)."""
    names = {made[k].get_name(): k for k in made}
    by_name = {n["name"]: n for n in ir["nodes"]}
    done = []
    for exported in json.loads(L.export_graph_ir(g))["nodes"]:
        name = names.get(exported["name"])
        # The input/output nodes come with the graph, not from add_node_of_type, and their settings
        # (e.g. the protected bHasAddedDefaultPin) are written from the IR or left as the new graph
        # made them; a slim IR lists none of them (compare.slim_normalize).
        if name is None or name in _ir.IO_NODES:
            continue
        n = by_name[name]
        stale = sorted(set(exported.get("settings") or {}) - set(n.get("settings") or {}) - {"Seed"})
        if not stale:
            continue
        st = made[name].get_settings()
        cdo = unreal.get_default_object(st.get_class())
        for key in stale:
            try:
                st.set_editor_property(key, cdo.get_editor_property(key))
            except Exception as ex:
                raise RuntimeError("%s: cannot reset %s.%s to its class default: %s"
                                   % (n.get("src") or name, n["class"], key, ex))
            done.append("%s.%s" % (n.get("title") or n["class"], key))
    return done


def _layout(g, ir, made, layout_from, fresh_seeds):
    """Positions and comment boxes come from the official graph through the node bijection
    (ruling R2); nodes without an official partner are placed right of their first input."""
    pos = {}
    boxes = []
    if layout_from:
        mapping, official_ir = layout_from
        off_nodes = {n["name"]: n for n in official_ir["nodes"]}
        for name, off in mapping.items():
            if off in off_nodes and off_nodes[off].get("pos"):
                pos[name] = list(off_nodes[off]["pos"])
        inverse = {v: k for k, v in mapping.items()}
        off_view = compare.view(official_ir, fresh_seeds)
        for box in official_ir.get("comment_boxes", []):
            members = compare._members(box, off_view)
            if all(m in inverse for m in members):
                boxes.append(box)
    stacked = {}
    for n in ir["nodes"]:
        if n["name"] in pos:
            continue
        src = next((e[0] for p in n.get("inputs", []) for e in p["edges"] if e[0] in pos), None)
        x, y = (pos[src][0] + AUTO_DX, pos[src][1]) if src else (0, 0)
        k = stacked.get((x, y), 0)
        stacked[(x, y)] = k + 1
        pos[n["name"]] = [x, y + k * AUTO_DY]
    for name, (x, y) in pos.items():
        made[name].set_node_position(int(x), int(y))
    _ok(L.set_graph_comment_boxes(g, json.dumps({"boxes": boxes})), "comment boxes")
    return len(boxes)


CLASS_PATHS = {_ir.PYTHON_NODE: "/Script/PCGPythonInteropEditor.PCGPythonDataProcessorSettings"}
SLIM_DX, SLIM_DY = 480, 200


def _class(name):
    return unreal.load_class(None, CLASS_PATHS.get(name, "/Script/PCG." + name))


def _write(ir, path, fresh_seeds):
    """Clear the asset at path and write ir into it: parameters, nodes, settings, overrides, pin
    defaults, getter bindings, dynamic pins, titles, comments and edges. Returns (graph, nodes by IR name).

    A build that reports diffs is not saved, but the asset stays cleared and rewritten IN MEMORY (dirty);
    a later save-all would persist it. No reload-from-disk is done here: reload_packages on a graph that
    stage volumes reference was never measured in this project, and the editor cannot be tested offline."""
    check_target(path)
    g = asset(path)
    unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(g)
    _clear(g)
    params = []
    for p in ir.get("params", []):
        # Ruling T7a: meta goes through verbatim; the panel's tooltip/advanced are their own fields.
        q = dict(p)
        q["meta"] = dict(p.get("meta") or {})
        q["tooltip"] = compare.tooltip_of(p)
        q["advanced"] = compare.advanced_of(p)
        q.pop("hier_meta", None)
        params.append(q)
    _ok(L.set_graph_user_parameters(g, json.dumps({"params": params})), "user parameters")
    if ir.get("graph_props"):
        _ok(L.set_properties_json(g, json.dumps(ir["graph_props"])), "graph_props")

    made = {_ir.IN_NODE: g.get_input_node(), _ir.OUT_NODE: g.get_output_node()}
    for n in ir["nodes"]:
        if n["name"] in made:
            continue
        cls = _class(n["class"])
        if cls is None:
            raise RuntimeError("%s: no node class %s (is its plugin enabled?)" % (n.get("src") or n["name"], n["class"]))
        node, st = g.add_node_of_type(cls)
        if n.get("subgraph"):
            sg = unreal.EditorAssetLibrary.load_asset(n["subgraph"].split(".")[0])
            if sg is None:
                raise RuntimeError("%s: missing subgraph %s" % (n.get("src") or n["name"], n["subgraph"]))
            st.set_subgraph(sg)
        made[n["name"]] = node

    resets = _reset_to_class_defaults(g, ir, made)
    LAST_CDO_RESETS[:] = resets

    for n in ir["nodes"]:
        where = n.get("src") or n.get("title") or n["name"]
        node = made[n["name"]]
        st = node.get_settings()
        settings = _resolve_refs(n.get("settings") or {}, made)
        if n["name"] in _ir.IO_NODES and "Seed" not in settings and n["class"] in fresh_seeds:
            settings["Seed"] = fresh_seeds[n["class"]]
        dyn_in, dyn_out = settings.pop("InputDynamicPins", None), settings.pop("OutputDynamicPins", None)
        if settings:
            _ok(L.set_properties_json(st, json.dumps(settings)), "%s settings" % where)
        if dyn_in is not None or dyn_out is not None:
            _ok(L.set_dynamic_pin_labels(st, list(dyn_in or []), list(dyn_out or [])), "%s dynamic pins" % where)
        if n.get("subgraph"):
            inst = st.get_editor_property("subgraph_instance")
            for k, v in (n.get("overrides") or {}).items():
                _ok(L.set_instance_parameter(inst, k, _v(v)), "%s override %s" % (where, k))
        for d in n.get("pin_defaults") or []:
            has_value = d.get("type") is not None
            _ok(L.set_pin_default_value(st, int(d["index"]), d.get("type") or "", _v(d.get("value")),
                                        has_value, bool(d.get("activated"))), "%s pin default %s" % (where, d["index"]))
        if n.get("getter_param"):
            _ok(L.bind_user_parameter_getter(st, n["getter_param"]), "%s getter" % where)
        if n.get("title"):
            node.set_editor_property("node_title", n["title"])
        if n.get("title_color"):
            node.set_editor_property("node_title_color", unreal.LinearColor(*n["title_color"]))
        if n.get("comment") or n.get("bubble_visible") or n.get("bubble_pinned"):
            _ok(L.set_node_comment(node, n.get("comment") or "", bool(n.get("bubble_visible")),
                                   bool(n.get("bubble_pinned"))), "%s comment" % where)

    for n in ir["nodes"]:
        dst = made[n["name"]]
        for p in n.get("inputs", []):
            for src_name, src_pin in p["edges"]:
                pin = _pin(dst, "input_pins", p["label"])
                before = len(pin.get_editor_property("edges")) if pin else -1
                g.add_edge(made[src_name], src_pin, dst, p["label"])
                pin = _pin(dst, "input_pins", p["label"])
                if pin is None or len(pin.get_editor_property("edges")) != before + 1:
                    raise RuntimeError("edge %s.%s -> %s.%s not created (traps.md 14); source outputs %s, target inputs %s"
                                       % (src_name, src_pin, n.get("src") or n["name"], p["label"],
                                          _labels(made[src_name], "output_pins"), _labels(dst, "input_pins")))
    return g, made


def build(ir, path, reference_ir, layout_from=None, fresh_seeds=None, check_layout=False, save=True):
    fresh_seeds = fresh_seeds or {}
    g, made = _write(ir, path, fresh_seeds)
    kept_boxes = _layout(g, ir, made, layout_from, fresh_seeds)
    # extract.export, not the raw exporter: the reference IR comes from extract.export, which makes
    # a Seed equal to the class CDO's seed explicit (ruling T3a).
    built = extract.export(g)
    diffs = compare.diff(built, reference_ir, fresh_seeds, check_layout=check_layout)
    if not diffs and save:
        if not unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False):
            raise RuntimeError("save_asset failed for " + path)
    for d in diffs:
        d.setdefault("asset", path)
    if layout_from and kept_boxes != len(layout_from[1].get("comment_boxes", [])):
        diffs.append({"kind": "layout", "where": "graph", "field": "comment_boxes.kept",
                      "a": kept_boxes, "b": len(layout_from[1].get("comment_boxes", []))})
    return diffs


def _slim_layout(g, ir, made):
    """Columns by longest path from the sources; rows in description order."""
    nodes = {n["name"]: n for n in ir["nodes"]}
    depth = {}

    def d(name, stack=()):
        if name not in depth:
            srcs = [e[0] for p in nodes[name].get("inputs", []) for e in p["edges"] if e[0] in nodes and e[0] not in stack]
            depth[name] = 1 + max((d(s, stack + (name,)) for s in srcs), default=-1)
        return depth[name]

    rows = {}
    for n in ir["nodes"]:
        k = d(n["name"])
        i = rows.get(k, 0)
        rows[k] = i + 1
        made[n["name"]].set_node_position(int(k * SLIM_DX), int(i * SLIM_DY))
    _ok(L.set_graph_comment_boxes(g, json.dumps({"boxes": []})), "comment boxes")


def build_slim(ir, path, save=True):
    """Write a slim graph and check it against its own description (spec 3, structural check);
    save only when they agree."""
    g, made = _write(ir, path, {})
    _slim_layout(g, ir, made)
    diffs = compare.slim_diff(extract.export(g), ir)
    if not diffs and save:
        if not unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False):
            raise RuntimeError("save_asset failed for " + path)
    for d in diffs:
        d.setdefault("asset", path)
    return diffs
