# tl_graph_kit.py -- helpers for authoring a PCG graph from Python.
# Every edge is verified (traps.md 14: add_edge fails silently and returns a
# truthy node). Selectors are written as "PCGBegin(<text>)PCGEnd" through the
# struct's import_text (Task 1 spike: q1_import_text round-tripped exactly).
# Nodes that exist in Epic's BDF_BuildingFromSpline are copied with
# add_node_copy, which carries the private inline pin defaults Python cannot
# set (Task 1 spike q3: DefaultValues is a protected UPROPERTY with no setter).
import unreal

EPIC_BLDG = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/BDF_BuildingFromSpline"
# Task 7 measured these directly on PCGMetadataStringOpSettings with
# Operation=Replace: the brief's guess of InA/InB/InC was wrong. The real data
# pins are In/Search/Replace (plus a SearchCase param pin and the usual
# execution/override/selector pins).
STRING3_PINS = ("In", "Search", "Replace")

# PCGMetadataTypesConstantStruct's typed value field for each PCGMetadataTypes
# member GraphKit.const supports. Measured at runtime (Task 7): the struct's
# fields are snake_case (bool_value, double_value, int32_value, string_value,
# vector_value, ...) and its "type" field is a PCGMetadataTypes enum whose
# members are the upper-snake form of these names (DOUBLE, INTEGER32,
# BOOLEAN, STRING, VECTOR, ...), i.e. typ.upper() names the enum member.
CONST_FIELD = {
    "Double": "double_value",
    "Integer32": "int32_value",
    "Boolean": "bool_value",
    "String": "string_value",
    "Vector": "vector_value",
}
CONST_PY = {
    "Double": float,
    "Integer32": int,
    "Boolean": bool,
    "String": str,
}


def cls(name):
    c = unreal.load_class(None, "/Script/PCG." + name)
    if c is None:
        raise RuntimeError("no PCG class " + name)
    return c


class Sel(str):
    """An attribute/property selector value, e.g. Sel("$BoundsMax.X")."""


class Txt(str):
    """A struct value written with import_text, e.g. Txt('(Type=Double,DoubleValue=2)')."""


def pin_labels(node, which):
    return [str(p.get_editor_property("properties").get_editor_property("label"))
            for p in node.get_editor_property(which)]


class GraphKit:
    def __init__(self, graph):
        self.g = graph
        self._copied = {}

    # ---- properties
    def _set_selector(self, st, prop, text):
        s = st.get_editor_property(prop)
        s.import_text("PCGBegin(%s)PCGEnd" % text)
        st.set_editor_property(prop, s)
        got = st.get_editor_property(prop).export_text()
        if text not in got:
            raise RuntimeError("selector %s on %s did not take %r (got %s)"
                               % (prop, st.get_class().get_name(), text, got))

    def set(self, st, prop, value):
        if isinstance(value, Sel):
            self._set_selector(st, prop, str(value))
        elif isinstance(value, Txt):
            v = st.get_editor_property(prop)
            v.import_text(str(value))
            st.set_editor_property(prop, v)
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
        """A one-entry attribute set. typ: Double, Integer32, Boolean, String, Vector.

        Builds the PCGCreateAttributeSetSettings node's AttributeTypes struct
        (a PCGMetadataTypesConstantStruct) by setting its typed fields
        directly -- Task 1's spike only proved the Double case through
        export_text, and Task 7 found that a one-entry String set does not
        read back cleanly through export_text() (it ends at "Z=" because the
        struct's export_text is very long and StringValue sits after several
        nested sub-structs). So this verifies the write with
        get_editor_property on the readback struct, not export_text.
        """
        n = self.node("PCGCreateAttributeSetSettings", output_target=Sel(name))
        st = n.get_settings()
        t = st.get_editor_property("attribute_types")
        member = getattr(unreal.PCGMetadataTypes, typ.upper())
        t.set_editor_property("type", member)
        field = CONST_FIELD[typ]
        if typ == "Vector":
            text = str(value)
            vv = t.get_editor_property("vector_value")
            vv.import_text(text if text.startswith("(") else "(%s)" % text)
            t.set_editor_property("vector_value", vv)
            want = vv.to_tuple()
        else:
            want = CONST_PY[typ](value)
            t.set_editor_property(field, want)
        st.set_editor_property("attribute_types", t)

        back = st.get_editor_property("attribute_types")
        got_type = back.get_editor_property("type")
        if got_type != member:
            raise RuntimeError("const %s=%r: type did not take (got %s)" % (name, value, got_type))
        if typ == "Vector":
            got = back.get_editor_property("vector_value").to_tuple()
        else:
            got = back.get_editor_property(field)
        if got != want:
            raise RuntimeError("const %s=%r: field %s did not take (wanted %r, got %r)"
                               % (name, value, field, want, got))
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
