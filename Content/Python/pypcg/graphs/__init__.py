"""One slim-graph description per stage (spec 2.3): pypcg/graphs/sNN_*.py defines build() -> SlimGraph."""
import importlib
import os

from pypcg import stages

_HERE = os.path.dirname(os.path.abspath(__file__))


def exists(n):
    return os.path.exists(os.path.join(_HERE, stages.entry(n)[2] + ".py"))


def graph(n):
    return importlib.import_module("pypcg.graphs." + stages.entry(n)[2]).build()
