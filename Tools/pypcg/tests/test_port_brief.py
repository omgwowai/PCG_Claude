import port_brief


def test_districts_contract():
    ir = port_brief.load(6)
    cls = port_brief.classify(ir)
    assert {n for n, c in cls.items() if c == "input"} == {"Subgraph_0", "Subgraph_1"}
    assert not [n for n, c in cls.items() if c == "gen"]              # its 4 meshes are debug-only
    assert {"Branch_0", "Branch_SmallDebug", "Subgraph_9"} <= {n for n, c in cls.items() if c == "drop"}
    tags = {t for _, _, ts in port_brief.output_tags(ir) for t in ts}
    assert tags == {"ArteryRoads", "CollectorRoads", "localRoads", "UndividableDistricts", "SmallDistricts",
                    "MediumDistricts", "LargeDistricts"}
    readers = port_brief.consumers(6)
    assert (7, "FilterByTag 'ArteryRoads'") in readers and (9, "Filter_Tags 'SmallDistricts'") in readers


def test_roads_keep_generation_and_drop_the_partition_branch():
    cls = port_brief.classify(port_brief.load(7))
    kept = {n for n, c in cls.items() if c == "gen"}
    assert {"Subgraph_26", "Subgraph_7", "Subgraph_46", "Subgraph_37"} <= kept     # Spawn Road, Crosswalks, 2 terrain writes
    assert cls["Subgraph_4"] == "drop" and cls["Loop_0"] == "drop"                 # GridPartition, LoopSpawnActorPerData


def test_totals_over_the_18_graphs():
    import collections
    from pypcg import stages
    total = collections.Counter()
    for n, *_ in stages.STAGES:
        total.update(port_brief.classify(port_brief.load(n)).values())
    assert (total["gen"], total["input"], total["drop"]) == (109, 69, 175)
