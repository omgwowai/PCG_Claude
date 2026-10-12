# tl_graph_kit.py -- helpers for authoring a PCG graph from Python.
# Every edge is verified (traps.md 14: add_edge fails silently and returns a
# truthy node). Selectors are written as "PCGBegin(<text>)PCGEnd" through the
# struct's import_text (Task 1 spike: q1_import_text round-tripped exactly).
# Nodes that exist in Epic's BDF_BuildingFromSpline are copied with
# add_node_copy, which carries the private inline pin defaults Python cannot
# set (Task 1 spike q3: DefaultValues is a protected UPROPERTY with no setter).
import re

import unreal

EPIC_BLDG = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/BDF_BuildingFromSpline"
# Task 7 measured these directly on PCGMetadataStringOpSettings with
# Operation=Replace: the brief's guess of InA/InB/InC was wrong. The real data
# pins are In/Search/Replace (plus a SearchCase param pin and the usual
# execution/override/selector pins).
STRING3_PINS = ("In", "Search", "Replace")

# PCGMetadataTypesConstantStruct's typed value field for each PCGMetadataTypes
# member GraphKit.const (and, as of fix round 1, every Txt(...) constant)
# supports. Measured at runtime (Task 7): the struct's fields are snake_case
# (bool_value, double_value, int32_value, string_value, vector_value, ...)
# and its "type" field is a PCGMetadataTypes enum whose members are the
# upper-snake form of these names (DOUBLE, INTEGER32, BOOLEAN, STRING,
# VECTOR, NAME, ...), i.e. typ.upper() names the enum member.
CONST_FIELD = {
    "Double": "double_value",
    "Integer32": "int32_value",
    "Boolean": "bool_value",
    "String": "string_value",
    "Vector": "vector_value",
    "Name": "name_value",
}
CONST_PY = {
    "Double": float,
    "Integer32": int,
    "Boolean": bool,
    "String": str,
    "Name": str,
}

# Matches the "(Type=Kind,XValue=raw)" text every Txt(...) constant in this
# project is built from (the filter thresholds in tl_make_spline_graph.py's
# K.filt(..., value=(kind, txt)) calls, and every AddAttribute/CreateAttributeSet
# constant). Vector is excluded here on purpose: it is never written through
# this generic single-scalar path (its "raw" half would itself contain nested
# parens), only through GraphKit.const("Vector", ...) directly.
_TYPED_TEXT_RE = re.compile(r'^\(Type=(\w+),\w+Value=(.*)\)$')
# Matches the "(X=..,Y=..,Z=..)" text a Vector const's value may be given as.
_VECTOR_RE = re.compile(r'^\(?X=([^,]+),Y=([^,]+),Z=([^,)]+)\)?$')


def cls(name):
    c = unreal.load_class(None, "/Script/PCG." + name)
    if c is None:
        raise RuntimeError("no PCG class " + name)
    return c


class Sel(str):
    """An attribute/property selector value, e.g. Sel("$BoundsMax.X")."""


class Txt(str):
    """A struct value written with import_text, e.g. Txt('(Type=Double,DoubleValue=2)').
    Routed through GraphKit._set_typed_text -> _build_const_struct, which
    verifies the write with get_editor_property (fix round 1, I3): every
    filter threshold and AddAttribute/CreateAttributeSet constant built this
    way now raises instead of silently writing a wrong value."""


def pin_labels(node, which):
    return [str(p.get_editor_property("properties").get_editor_property("label"))
            for p in node.get_editor_property(which)]


def _parse_typed_value(kind, raw):
    """Parse one bare scalar out of a '(Type=Kind,XValue=raw)' text fragment's
    raw half, for every Kind this project's filters/constants use (Double,
    Integer32, Boolean, String, Name). Independent of whatever the struct
    itself reports back -- this is the "expected" value _build_const_struct
    checks the readback against."""
    if kind in ("String", "Name"):
        if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
            return raw[1:-1]
        return raw
    if kind == "Boolean":
        return raw.strip() == "True"
    if kind == "Integer32":
        return int(raw)
    if kind == "Double":
        return float(raw)
    raise RuntimeError("Txt kind %r is not a supported scalar const type" % kind)


def _parse_vector_value(value):
    """Independently parse the (x, y, z) a Vector const SHOULD hold, from an
    unreal.Vector, an (x, y, z) tuple/list, or '(X=..,Y=..,Z=..)' text.
    Deliberately does not go through the struct being verified -- fix round
    1, I2: the old code compared vv.to_tuple() (read from the very struct
    import_text() had just written) against itself, which cannot catch a
    wrong value. This parses the caller's original intent on its own."""
    if isinstance(value, unreal.Vector):
        return (float(value.x), float(value.y), float(value.z))
    if isinstance(value, (tuple, list)) and len(value) == 3:
        return (float(value[0]), float(value[1]), float(value[2]))
    if isinstance(value, str):
        m = _VECTOR_RE.match(value.strip())
        if not m:
            raise RuntimeError("Vector value %r not parseable as (X=..,Y=..,Z=..)" % (value,))
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)))
    raise RuntimeError("Vector value must be unreal.Vector, (x,y,z), or 'X=..,Y=..,Z=..' text, got %r"
                       % (value,))


class GraphKit:
    def __init__(self, graph):
        self.g = graph

    # ---- properties
    def _set_selector(self, st, prop, text):
        s = st.get_editor_property(prop)
        s.import_text("PCGBegin(%s)PCGEnd" % text)
        st.set_editor_property(prop, s)
        got = st.get_editor_property(prop).export_text()
        # Fix round 1, I3 (second half): exact match of the whole wrapped
        # selector text, not a substring check -- a substring check would
        # pass for e.g. text="C" against a selector that actually holds
        # "ABC", or against unrelated wrapper noise.
        expected = "PCGBegin(%s)PCGEnd" % text
        if got != expected:
            raise RuntimeError("selector %s on %s did not take %r (got %s)"
                               % (prop, st.get_class().get_name(), text, got))

    def _build_const_struct(self, st, prop, typ, value):
        """Set `prop` (a PCGMetadataTypesConstantStruct-valued property, e.g.
        AttributeTypes) on settings object st to the given typed constant,
        and verify the write by reading `prop` straight back with
        get_editor_property -- never export_text() (Task 7: a one-entry
        String set's export_text() looks truncated at a glance, though the
        full untruncated text does in fact contain the right value; reading
        the struct's own typed field back is unambiguous either way).
        Raises on any mismatch, so a silently-wrong constant or filter
        threshold fails loudly (fix round 1, I3) instead of writing
        unchecked -- this now backs every Txt(...) value as well as
        GraphKit.const.

        typ: Double, Integer32, Boolean, String, Name, Vector. For Vector,
        `value` may be an unreal.Vector, an (x, y, z) tuple, or
        "(X=..,Y=..,Z=..)" text; see _parse_vector_value for why the
        expected value is parsed independently (fix round 1, I2).
        """
        t = st.get_editor_property(prop)
        member = getattr(unreal.PCGMetadataTypes, typ.upper())
        t.set_editor_property("type", member)
        if typ == "Vector":
            want = _parse_vector_value(value)
            text = value if isinstance(value, str) else "(X=%r,Y=%r,Z=%r)" % want
            vv = t.get_editor_property("vector_value")
            vv.import_text(text if text.startswith("(") else "(%s)" % text)
            t.set_editor_property("vector_value", vv)
            field = "vector_value"
        else:
            field = CONST_FIELD[typ]
            want = CONST_PY[typ](value)
            t.set_editor_property(field, want)
        st.set_editor_property(prop, t)

        back = st.get_editor_property(prop)
        got_type = back.get_editor_property("type")
        if got_type != member:
            raise RuntimeError("%s.%s=%r: type did not take (got %s)"
                               % (st.get_class().get_name(), prop, value, got_type))
        if typ == "Vector":
            got = back.get_editor_property("vector_value").to_tuple()
            ok = all(abs(a - b) < 1e-6 for a, b in zip(got, want))
        else:
            got = back.get_editor_property(field)
            ok = got == want
        if not ok:
            raise RuntimeError("%s.%s=%r: field %s did not take (wanted %r, got %r)"
                               % (st.get_class().get_name(), prop, value, field, want, got))

    def _set_typed_text(self, st, prop, text):
        """Route a Txt(...) value through _build_const_struct (fix round 1,
        I3): every filter threshold (the 625/200 cm short cuts, the 90 deg
        acute cut, LevelNumber == 0, BuildingToken == "TL") and every
        AddAttribute constant (ShortScale = 1, the FloorGrammar strings) goes
        through this, so a silently-wrong threshold raises instead of being
        written unchecked and discovered only downstream in generated data."""
        m = _TYPED_TEXT_RE.match(text)
        if not m:
            raise RuntimeError("Txt %r did not match '(Type=Kind,XValue=raw)'" % (text,))
        kind, raw = m.group(1), m.group(2)
        if kind == "Vector":
            raise RuntimeError("Txt(Vector...) is not supported (nested parens); "
                               "use GraphKit.const('Vector', ...) directly")
        value = _parse_typed_value(kind, raw)
        self._build_const_struct(st, prop, kind, value)

    def set(self, st, prop, value):
        if isinstance(value, Sel):
            self._set_selector(st, prop, str(value))
        elif isinstance(value, Txt):
            self._set_typed_text(st, prop, str(value))
        elif isinstance(value, list) and value and isinstance(value[0], Sel):
            arr = []
            for text in value:
                s = unreal.PCGAttributePropertyInputSelector()
                s.import_text("PCGBegin(%s)PCGEnd" % text)
                arr.append(s)
            st.set_editor_property(prop, arr)
        else:
            st.set_editor_property(prop, value)

    # ---- nodes
    def node(self, cls_name, **props):
        n, st = self.g.add_node_of_type(cls(cls_name))
        for k, v in props.items():
            self.set(st, k, v)
        return n

    def sub(self, graph_path, loop=False, **params):
        n, st = self.g.add_node_of_type(cls("PCGLoopSettings" if loop else "PCGSubgraphSettings"))
        st.set_subgraph(unreal.EditorAssetLibrary.load_asset(graph_path))
        inst = st.get_editor_property("subgraph_instance")
        H = unreal.PCGGraphParametersHelpers
        for k, v in params.items():
            if isinstance(v, bool):
                H.set_bool_parameter(inst, k, v)
            elif isinstance(v, float):
                H.set_double_parameter(inst, k, v)
            else:
                H.set_string_parameter(inst, k, v)
        return n

    def loop(self, graph_path, **params):
        return self.sub(graph_path, loop=True, **params)

    def copy(self, node_name, graph_path=EPIC_BLDG, **props):
        """Copy one node's settings out of another graph (that graph is only read)."""
        src = unreal.EditorAssetLibrary.load_asset(graph_path)
        for n in src.get_editor_property("nodes"):
            if n.get_name() == node_name:
                new, st = self.g.add_node_copy(n.get_settings())
                for k, v in props.items():
                    self.set(st, k, v)
                return new
        raise RuntimeError("%s has no node %s" % (graph_path, node_name))

    def const(self, typ, value, name):
        """A one-entry attribute set. typ: Double, Integer32, Boolean, String,
        Name, Vector. Builds the node then verifies the write through
        _build_const_struct (see its docstring for the Vector tautology fix,
        round 1 I2, and the general readback-not-export_text rationale)."""
        n = self.node("PCGCreateAttributeSetSettings", output_target=Sel(name))
        st = n.get_settings()
        self._build_const_struct(st, "attribute_types", typ, value)
        return (n, "Out")

    # ---- edges
    def edge(self, src, dst, dst_pin):
        """src is a (node, out_pin) port."""
        before = len(self.g.get_all_edges())
        self.g.add_edge(src[0], src[1], dst, dst_pin)
        if len(self.g.get_all_edges()) <= before:
            raise RuntimeError("edge %s.%s -> %s.%s not created; out pins %s, in pins %s"
                               % (src[0].get_name(), src[1], dst.get_name(), dst_pin,
                                  pin_labels(src[0], "output_pins"), pin_labels(dst, "input_pins")))

    # ---- shorthands
    def maths(self, src, op, a, b, out):
        """out = a <op> b on src's data. a is an attribute selector; b is a number
        (wired as a constant) or a Sel (same data)."""
        kw = dict(operation=getattr(unreal.PCGMetadataMathsOperation, op),
                  input_source1=Sel(a), output_target=Sel(out))
        if isinstance(b, Sel):
            kw["input_source2"] = b
            n = self.node("PCGMetadataMathsSettings", **kw)
            self.edge(src, n, "InA")
            self.edge(src, n, "InB")
        elif b is None:
            n = self.node("PCGMetadataMathsSettings", **kw)
            self.edge(src, n, "In")
        else:
            n = self.node("PCGMetadataMathsSettings", **kw)
            self.edge(src, n, "InA")
            self.edge(self.const("Double", b, "C"), n, "InB")
        return (n, "Out")

    def filt(self, src, attr, op, value=None, against=None):
        """Point filter: attr <op> constant value, or attr <op> another attribute."""
        kw = dict(target_attribute=Sel(attr),
                  operator=getattr(unreal.PCGAttributeFilterOperator, op))
        if against is not None:
            kw.update(use_constant_threshold=False, threshold_attribute=Sel(against))
        else:
            kind, txt = value
            kw.update(use_constant_threshold=True, attribute_types=Txt("(Type=%s,%s)" % (kind, txt)))
        n = self.node("PCGAttributeFilteringSettings", **kw)
        self.edge(src, n, "In")
        return (n, "InsideFilter"), (n, "OutsideFilter")

    def merge(self, *ports):
        n = self.node("PCGMergeSettings")
        for p in ports:
            self.edge(p, n, "In")
        return (n, "Out")
