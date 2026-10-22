import json
import os

from pypcg import compare, ir, stages

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LIB = json.load(open(os.path.join(REPO, "Content", "Python", "pypcg", "library.json"), encoding="utf-8"))


def snap(name):
    return ir.load(os.path.join(REPO, "Tools", "pypcg", "official_ir", name + ".json"))


def test_all_18_snapshots_exist_and_total_matches_the_census():
    graphs = [snap(n) for n in stages.names()]
    assert sum(len(g["nodes"]) for g in graphs) == 1509
    assert sum(len(p["edges"]) for g in graphs for n in g["nodes"] for p in n["inputs"]) == 1780


def test_each_snapshot_equals_itself():
    for n in stages.names():
        g = snap(n)
        assert compare.diff(g, g, LIB["fresh_seeds"], check_layout=True) == [], n


def test_every_subgraph_in_the_snapshots_is_in_the_library():
    for n in stages.names():
        for node in snap(n)["nodes"]:
            if node.get("subgraph"):
                assert ir.alias_of(node["subgraph"]) in LIB["subgraphs"], (n, node["name"])


def test_every_settings_node_carries_a_seed():
    # Ruling T3a: extraction fills in Seed (from the class default object) whenever the exporter
    # omitted it, so every settings node -- IO nodes included, since DefaultInputNode and
    # DefaultOutputNode are PCGGraphInputOutputSettings nodes too -- carries an explicit Seed.
    for n in stages.names():
        for node in snap(n)["nodes"]:
            assert "Seed" in (node.get("settings") or {}), (n, node["name"], node.get("class"))
