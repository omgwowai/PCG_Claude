"""The 18 node-by-node drafts of the official graphs (2026-10-14, commit fe380a1), kept as reference
for the Python ports. Each module's build() returns a pypcg.dsl.Graph equal to the official graph."""
import importlib

from pypcg import stages


def graph(n):
    return importlib.import_module("reference_drafts." + stages.entry(n)[2]).build()
