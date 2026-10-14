"""PyPCG -- the 18 City Sample stage graphs written as Python (docs/pypcg-guide.md).

ir, compare, dsl and town_checks import nothing from unreal, so pytest runs them on any
interpreter. build, extract and census run inside the editor.
"""
from .dsl import D, Graph, NodeRef, P, Role, SIZES, knob, sel  # noqa: F401
