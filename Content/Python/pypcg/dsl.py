"""The Python form of one PCG graph (docs/pypcg-guide.md).

A stage file describes nodes and edges with these calls; Graph.to_ir(profile) returns the
IR shape UPyPCGToolsLibrary.ExportGraphIR writes, so the comparator checks a stage file
against the official graph offline. No unreal import.
"""
import json
import os
import sys
from contextlib import contextmanager

from . import ir as _ir

SIZES = ("Small", "Medium", "Large")
_HERE = os.path.dirname(os.path.abspath(__file__))
_LIBRARY = {}


EXTRA_CLASSES = {
    _ir.PYTHON_NODE: {"inputs": [], "outputs": []},             # pins are per node (dynamic_pins)
    _ir.SELF_NODE: {"inputs": [], "outputs": ["Out"]},
}


def library():
    """library.json: the real pins and parameters of every subgraph and node class (Task 4), plus
    EXTRA_CLASSES."""
    if not _LIBRARY:
        with open(os.path.join(_HERE, "library.json"), encoding="utf-8") as fh:
            _LIBRARY.update(json.load(fh))
    for cls, pins in EXTRA_CLASSES.items():
        _LIBRARY.setdefault("classes", {}).setdefault(cls, pins)
    return _LIBRARY


def sel(text):
    """An attribute/property selector as UE writes it, e.g. sel("$Position.Z")."""
    return "PCGBegin(%s)PCGEnd" % text


class Role:
    """Upstream actors named by role; the profile turns each name into a soft object path."""

    def __init__(self, *names):
        self.names = list(names)


class Knob:
    """A value a profile may replace (the town's park size); the default is the official value."""

    def __init__(self, name, default):
        self.name = name
        self.default = default


def knob(name, default):
    return Knob(name, default)


class NodeRef:
    """A settings value that points at another node of the same graph."""

    def __init__(self, node):
        self.node = node


class P:
    """One graph user parameter."""

    def __init__(self, name, type, value, container="None", type_object="", category="", tooltip="",
                 advanced=False, meta=None):
        # Ruling T7a: `meta` is the descriptor metadata, kept verbatim (key spelling included);
        # `tooltip` and `advanced` are what the parameter panel shows, set through the hierarchy.
        self.name = name
        self.ir = {"name": name, "type": type, "value": value, "container": container,
                   "type_object": type_object, "category": category, "tooltip": tooltip,
                   "advanced": bool(advanced), "meta": dict(meta or {})}


class D:
    """An inline default on input pin number `index` (0-based) of a metadata node."""

    def __init__(self, index, type=None, value=None, activated=True):
        self.ir = {"index": index, "type": type, "value": value, "activated": activated}


class Port:
    __slots__ = ("node", "pin")

    def __init__(self, node, pin):
        self.node = node
        self.pin = pin


class Node:
    def __init__(self, graph, rec):
        object.__setattr__(self, "_g", graph)
        object.__setattr__(self, "_rec", rec)

    @property
    def name(self):
        return self._rec["name"]

    def __getitem__(self, pin):
        self._g._check_out(self._rec, pin)
        return Port(self, pin)

    def __getattr__(self, pin):
        if pin.startswith("_"):
            raise AttributeError(pin)
        return self[pin]


class Declaration(Node):
    def use(self, title=None, **kw):
        return self._g._usage(self, title, kw)


class Graph:
    def __init__(self, name, params=(), graph_props=None, description=None,
                 input_settings=None, output_settings=None):
        self.name = name
        self._params = list(params)
        self._props = dict(graph_props or {})
        if description is not None:
            self._props["Description"] = description
        self._nodes = []
        self._step = None
        self.input = Node(self, self._io(_ir.IN_NODE, input_settings))
        self.output = Node(self, self._io(_ir.OUT_NODE, output_settings))

    def _io(self, name, settings):
        rec = {"name": name, "class": "PCGGraphInputOutputSettings", "title": "",
               "settings": dict(settings or {}), "inputs": [], "src": "", "step": None}
        self._nodes.append(rec)
        return rec

    @contextmanager
    def step(self, number, title):
        old = self._step
        self._step = "%d %s" % (number, title)
        try:
            yield
        finally:
            self._step = old

    @staticmethod
    def _caller():
        frame = sys._getframe(1)
        while frame is not None and os.path.dirname(os.path.abspath(frame.f_code.co_filename)) == _HERE:
            frame = frame.f_back
        if frame is None:
            return ""
        return "%s:%d" % (os.path.basename(frame.f_code.co_filename), frame.f_lineno)

    # ---- library checks
    def _subgraph(self, alias):
        subs = library()["subgraphs"]
        if alias not in subs:
            near = sorted(a for a in subs if a.lower()[:6] == alias.lower()[:6])
            raise KeyError("%s: unknown subgraph %r; similar: %s" % (self._caller(), alias, near))
        return subs[alias]

    def _pins(self, rec, which):
        if "dynamic_pins" in rec:
            return rec["dynamic_pins"][which]
        lib = library()
        if which == "outputs" and "getter_param" in rec:
            # M1: a getter node's only valid output pin is its own bound parameter, not the
            # union of every getter pin in the library.
            return [rec["getter_param"]]
        if rec["name"] == _ir.IN_NODE:
            return lib["io"]["input_node_" + which]
        if rec["name"] == _ir.OUT_NODE:
            return lib["io"]["output_node_" + which]
        if "subgraph" in rec:
            return lib["subgraphs"][_ir.alias_of(rec["subgraph"])][which]
        return lib["classes"][rec["class"]][which]

    def _check_in(self, rec, label):
        allowed = self._pins(rec, "inputs")
        if label not in allowed:
            raise KeyError("%s: %s has no input pin %r; inputs: %s"
                           % (self._caller(), rec["title"] or rec["class"], label, allowed))

    def _check_out(self, rec, pin):
        allowed = self._pins(rec, "outputs")
        # M1: getter_param names match case-insensitively (ruling T4e), so the output pin -- which
        # is the getter's bound parameter name -- must too.
        match = pin.lower() in [a.lower() for a in allowed] if "getter_param" in rec else pin in allowed
        if not match:
            raise KeyError("%s: %s has no output pin %r; outputs: %s"
                           % (self._caller(), rec["title"] or rec["class"], pin, allowed))

    # ---- nodes
    def _add(self, cls, title, settings, kw, subgraph=None, overrides=None, defaults=None, getter=None,
             node_type=Node, dynamic=None):
        comment = kw.pop("comment", None) or ""
        rec = {"name": "n%d" % len(self._nodes), "class": cls, "title": title or "",
               "settings": dict(settings or {}), "comment": comment,
               "bubble_visible": kw.pop("bubble_visible", bool(comment)),
               "bubble_pinned": kw.pop("bubble_pinned", False),
               "inputs": [], "src": self._caller(), "step": self._step}
        color = kw.pop("title_color", None)
        if color is not None:
            rec["title_color"] = list(color)
        if subgraph is not None:
            rec["subgraph"] = subgraph
            rec["overrides"] = dict(overrides or {})
        if defaults:
            rec["pin_defaults"] = [dict(d.ir) for d in defaults]
        if getter is not None:
            rec["getter_param"] = getter
        pins = dict(kw.pop("pins", None) or {})
        pins.update(kw)
        if dynamic is not None:
            rec["dynamic_pins"] = {"inputs": list(dynamic[0]), "outputs": list(dynamic[1])}
        self._nodes.append(rec)
        for label, src in pins.items():
            self._connect(rec, label, src)
        return node_type(self, rec)

    def sub(self, alias, title="", set=None, settings=None, loop=False, **kw):
        entry = self._subgraph(alias)
        for key in (set or {}):
            if key not in entry["params"]:
                raise KeyError("%s: %s has no parameter %r; parameters: %s"
                               % (self._caller(), alias, key, sorted(entry["params"])))
        return self._add("PCGLoopSettings" if loop else "PCGSubgraphSettings", title, settings, kw,
                         subgraph=entry["path"], overrides=set)

    def loop(self, alias, title="", **kw):
        return self.sub(alias, title, loop=True, **kw)

    def node(self, cls, title="", set=None, defaults=None, **kw):
        if cls not in library()["classes"]:
            raise KeyError("%s: unknown node class %r" % (self._caller(), cls))
        return self._add(cls, title, set, kw, defaults=defaults)

    def param(self, name, title="", set=None, **kw):
        # Ruling T4e: accept a name that matches a declared parameter case-insensitively, but
        # keep the caller's own spelling in getter_param. Three official getters (in LeftOverLots
        # and CentralPark_Visuals) store "UseMegaPlantsTrees" where the declared parameter is
        # "UseMegaplantsTrees" -- a case-only difference. Separately, 16 getters have
        # getter_bound false (their stored GUIDs are stale); the comparator does not look at
        # getter_bound.
        declared = [p.name.lower() for p in self._params]
        if name.lower() not in declared:
            raise KeyError("%s: graph %s has no parameter %r; parameters: %s"
                           % (self._caller(), self.name, name, [p.name for p in self._params]))
        return self._add("PCGUserParameterGetSettings", title, set, kw, getter=name)

    def param_path(self, path, title="", set=None, **kw):
        settings = {"PropertyPath": path}
        settings.update(set or {})
        return self._add("PCGGenericUserParameterGetSettings", title, settings, kw)

    def actor_by_tag(self, tag, title="", set=None, **kw):
        overrides = {"ActorTag": tag}
        overrides.update(set or {})
        return self.sub("Get_ActorData", title, set=overrides, **kw)

    def ref(self, roles, title="", set=None, **kw):
        roles = [roles] if isinstance(roles, str) else list(roles)
        overrides = {"ActorReferences": Role(*roles)}
        overrides.update(set or {})
        return self.sub("Get_ActorDataByRef", title, set=overrides, **kw)

    def python(self, module_name, inputs, outputs, title=""):
        """A Python Data Processor running pypcg.stages.<module_name> through the host (ruling N4)."""
        from .host import inline_script
        settings = {"InlineScript": inline_script(module_name), "bMuteEditorToast": True,
                    "InputDynamicPins": list(inputs), "OutputDynamicPins": list(outputs)}
        return self._add(_ir.PYTHON_NODE, title, settings, {}, dynamic=(inputs, outputs))

    def actor_points(self, tag, title="", **kw):
        """Get Actor Data: one point per level actor carrying `tag` -- its transform, bounds and an `ActorReference`
        attribute (Mode GetSinglePoint). The whole selector struct is written, as the exporter reads it back (trap 90)."""
        settings = {"Mode": "GetSinglePoint",
                    "ActorSelector": {"ActorFilter": "AllWorldActors", "bMustOverlapSelf": False,
                                      "bIncludeChildren": False, "IncludeIsolatedActors": "Ignore",
                                      "bDisableFilter": False, "ActorSelection": "ByTag", "ActorSelectionTag": tag,
                                      "ActorSelectionClass": "None", "ActorReferenceSelector": "PCGBegin(@Last)PCGEnd",
                                      "bSelectMultiple": True, "bIgnoreSelfAndChildren": False}}
        return self._add(_ir.SELF_NODE, title, settings, kw)

    def self_point(self, title="Get Self (Volume Transform)", **kw):
        """The volume's own transform as one point (what Create_Spline_Shape reads when not at the origin)."""
        return self._add(_ir.SELF_NODE, title, {"Mode": "GetSinglePoint"}, kw)

    def reroute(self, src, title="", set=None, **kw):
        kw["In"] = src
        return self._add("PCGRerouteSettings", title, set, kw)

    def declare(self, title, src=None, set=None, **kw):
        if src is not None:
            kw["In"] = src
        return self._add("PCGNamedRerouteDeclarationSettings", title, set, kw, node_type=Declaration)

    def _usage(self, decl, title, kw):
        settings = {"Declaration": NodeRef(decl)}
        settings.update(kw.pop("set", None) or {})
        kw["In"] = Port(decl, "InvisiblePin")
        return self._add("PCGNamedRerouteUsageSettings", decl._rec["title"] if title is None else title,
                         settings, kw)

    # ---- edges
    def connect(self, src, node, pin):
        self._connect(node._rec, pin, src)

    def out(self, *srcs):
        for src in srcs:
            self._connect(self.output._rec, "Out", src)

    def _connect(self, rec, label, src):
        self._check_in(rec, label)
        sources = src if isinstance(src, (list, tuple)) else [src]
        entry = next((p for p in rec["inputs"] if p["label"] == label), None)
        if entry is None:
            entry = {"label": label, "edges": []}
            rec["inputs"].append(entry)
        for s in sources:
            port = s if isinstance(s, Port) else Port(s, "Out")
            if not isinstance(port.node, Node):
                raise TypeError("%s: %r is not a node or port" % (self._caller(), s))
            self._check_out(port.node._rec, port.pin)
            entry["edges"].append([port.node.name, port.pin])

    # ---- IR
    def to_ir(self, profile=None):
        roles = getattr(profile, "ROLES", {})
        knobs = getattr(profile, "KNOBS", {})
        sites = []

        def resolve(value, where):
            if isinstance(value, Role):
                missing = [r for r in value.names if r not in roles]
                if missing:
                    raise KeyError("%s: profile has no role %s" % (where, missing))
                sites.append({"where": where, "kind": "role", "roles": list(value.names)})
                return [roles[r] for r in value.names]
            if isinstance(value, Knob):
                sites.append({"where": where, "kind": "knob", "knob": value.name})
                return knobs.get(value.name, value.default)
            if isinstance(value, NodeRef):
                return {"node_ref": value.node.name}
            if isinstance(value, dict):
                return {k: resolve(v, "%s.%s" % (where, k)) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [resolve(v, "%s[%d]" % (where, i)) for i, v in enumerate(value)]
            return value

        nodes = []
        for rec in self._nodes:
            out = dict(rec)
            for field in ("settings", "overrides", "pin_defaults"):
                if field in rec:
                    out[field] = resolve(rec[field], "%s.%s" % (rec["name"], field))
            out["inputs"] = [{"label": p["label"], "edges": [list(e) for e in p["edges"]]} for p in rec["inputs"]]
            nodes.append(out)
        return {"schema": _ir.SCHEMA, "graph": self.name,
                "graph_props": resolve(self._props, "graph_props"),
                "params": [resolve(p.ir, "params.%s" % p.name) for p in self._params],
                "comment_boxes": [], "nodes": nodes, "sites": sites}


_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
_OFFICIAL = {}


def _official_ir(stage):
    from . import stages
    if stage not in _OFFICIAL:
        path = os.path.join(_REPO, "Tools", "pypcg", "official_ir", stages.name(stage) + ".json")
        _OFFICIAL[stage] = _ir.load(path)
    return _OFFICIAL[stage]


def _role_by_path():
    from .profiles import official
    return {p: r for r, p in official.ROLES.items()}


def roles_of(paths):
    paths = paths if isinstance(paths, list) else [paths]
    table = _role_by_path()
    unknown = [p for p in paths if p not in table]
    if unknown:
        raise KeyError("actor references without a role: %s" % unknown)
    return [table[p] for p in paths]


def official_node(stage, name):
    for n in _official_ir(stage)["nodes"]:
        if n["name"] == name:
            return n
    near = sorted(n["name"] for n in _official_ir(stage)["nodes"] if n["name"][:5] == name[:5])
    raise KeyError("official stage %s has no node %r; similar: %s" % (stage, name, near))


def official_param(stage, name):
    from . import compare
    for p in _official_ir(stage)["params"]:
        if p["name"] == name:
            return P(p["name"], p["type"], p["value"], p.get("container", "None"), p.get("type_object", ""),
                     p.get("category", ""), compare.tooltip_of(p), compare.advanced_of(p), p.get("meta"))
    raise KeyError("official stage %s has no parameter %r" % (stage, name))


class SlimGraph(Graph):
    """A stage's slim graph (spec 2.1). One user parameter per stage parameter (Seed first), each
    with one getter into its Python node's Params pin; the Python node(s); and whatever scene reads
    (keep, actor_by_tag, ref, self_point) and engine generation nodes (keep) the description adds.
    extra_params are official parameters only kept nodes read; more_modules add Python nodes for
    stage parts that sit after an engine generation node."""

    def __init__(self, stage_module, extra_params=(), more_modules=(), name=None):
        from . import stage_api, stages
        self.stage = stage_module
        specs = {}
        for m in (stage_module,) + tuple(more_modules):
            for spec in stage_api.param_specs(m):
                if spec[0] in specs and specs[spec[0]][1] != spec[1]:
                    raise TypeError("parameter %s is %s in one module and %s in another" % (spec[0], specs[spec[0]][1], spec[1]))
                specs.setdefault(spec[0], spec)
        params = [P(n, t, v, type_object=to, category=cat, tooltip=tip) for n, t, v, tip, to, cat in specs.values()]
        super().__init__(name or stages.name(stage_module.STAGE), params=params + list(extra_params),
                         description=stage_module.DOC.strip())
        self._getters = {}
        self.pynodes = {}
        for m in (stage_module,) + tuple(more_modules):
            name = m.__name__.rsplit(".", 1)[-1]
            node = self.python(name, [stage_api.PARAMS_PIN] + list(m.INPUTS), list(m.OUTPUTS), title="Python: " + name)
            for spec in stage_api.param_specs(m):
                self.connect(self.p(spec[0]), node, stage_api.PARAMS_PIN)
            self.pynodes[name] = node
        self.py = self.pynodes[stage_module.__name__.rsplit(".", 1)[-1]]

    def to_ir(self, profile=None):
        # An unwired dynamic pin is required by execution (UPCGPythonDataProcessorSettings::
        # IsInputPinRequiredByExecution) and makes the graph compiler cull the node, silently.
        for name, node in self.pynodes.items():
            wired = {p["label"] for p in node._rec["inputs"] if p["edges"]}
            missing = [pin for pin in node._rec["dynamic_pins"]["inputs"] if pin not in wired]
            if missing:
                raise ValueError("%s: Python node %s has unwired input pins %s; wire every stage input "
                                 "(an unwired dynamic pin culls the node)" % (self.name, name, missing))
        return super().to_ir(profile)
    def p(self, name):
        """The output of this parameter's getter (one getter per parameter, shared: spec E6)."""
        if name not in self._getters:
            self._getters[name] = self.param(name, name)
        return self._getters[name][name]

    def keep(self, official_name, title=None, **pins):
        """Copy official node `official_name` of this stage: class, subgraph, overrides, settings
        without Seed, pin defaults and title. Actor references become roles, so a profile can point
        them at another level."""
        off = official_node(self.stage.STAGE, official_name)
        from . import compare
        combined = {"settings": off.get("settings") or {}, "overrides": off.get("overrides") or {},
                    "pin_defaults": off.get("pin_defaults") or []}
        mapped = _ir.node_refs_to_names(combined, _official_ir(self.stage.STAGE)["graph"])
        if mapped != combined:
            raise ValueError("%s: official node %s references other nodes of its graph (%s); a slim graph "
                             "cannot keep it -- describe that part in Python instead"
                             % (self.name, official_name, compare.refs(mapped)))
        overrides = dict(off.get("overrides") or {})
        if "ActorReferences" in overrides:
            overrides["ActorReferences"] = Role(*roles_of(overrides["ActorReferences"]))
        settings = {k: v for k, v in (off.get("settings") or {}).items() if k != "Seed"}
        defaults = [D(d["index"], d.get("type"), d.get("value"), d.get("activated", True))
                    for d in off.get("pin_defaults") or []]
        title = off.get("title", "") if title is None else title
        if off.get("subgraph"):
            return self._add(off["class"], title, settings, pins, subgraph=off["subgraph"], overrides=overrides,
                             defaults=defaults)
        return self._add(off["class"], title, settings, pins, defaults=defaults)
