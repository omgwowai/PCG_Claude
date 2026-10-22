"""The level guards of the editor drivers (final review I2, M14): pure parts only."""
from pypcg import level as L
from pypcg import stages

LABELS = stages.names()
TEMPLATE = {label: stages.OFFICIAL_DIR + label for label in LABELS}


def town_graphs():
    return {label: "/Game/PyPCG/Town/%s.%s" % (label, label) for label in LABELS}


def template_graphs():
    return {label: "/CitySamplePCG/Levels/PCG/%s.%s" % (label, label) for label in LABELS}


def test_map_package_is_the_full_package_path():
    assert L.map_package("/Game/PyPCG/L_PyTown.L_PyTown:PersistentLevel") == L.TOWN
    assert L.map_package("/CitySamplePCG/Levels/L_CitySamplePCG_Demo.L_CitySamplePCG_Demo:PersistentLevel") == L.DEMO
    assert L.map_package("") == "" and L.map_package(None) == ""


def test_refusal_compares_full_paths_not_short_names():
    assert L.refusal(L.TOWN, L.TOWN, "x") is None
    r = L.refusal("/Game/Elsewhere/L_PyTown", L.TOWN, "pypcg_town.py")    # same short name, other package
    assert "abort" in r and L.TOWN in r["abort"] and "/Game/Elsewhere/L_PyTown" in r["abort"]
    assert "none" in L.refusal("", L.DEMO, "x")["abort"]


def test_graphs_outside():
    assert L.graphs_outside({"a": "/Game/PyPCG/Town/A.A", "b": None, "c": "/Game/PyPCG/Probe/C.C"},
                            L.TOWN_GRAPHS) == ["b", "c"]


def test_save_after_assign_needs_every_stage_graph_under_town():
    assert L.save_problems(town_graphs(), LABELS) == []
    g = town_graphs()
    g[LABELS[9]] = "/Game/PyPCG/Probe/PCG_T17Tap.PCG_T17Tap"
    p = L.save_problems(g, LABELS)
    assert len(p) == 1 and "PCG_T17Tap" in p[0]
    # Without a template, the template's own graphs are not acceptable either (finish runs after assign).
    assert L.save_problems(template_graphs(), LABELS)


def test_save_before_assign_accepts_the_template_graphs_only_all_together():
    assert L.save_problems(template_graphs(), LABELS, TEMPLATE) == []
    assert L.save_problems(town_graphs(), LABELS, TEMPLATE) == []
    mixed = template_graphs()
    mixed[LABELS[0]] = "/Game/PyPCG/Town/%s.%s" % (LABELS[0], LABELS[0])
    assert L.save_problems(mixed, LABELS, TEMPLATE)
    probe = template_graphs()
    probe[LABELS[12]] = "/Game/PyPCG/Probe/PCG_T18Tap.PCG_T18Tap"
    p = L.save_problems(probe, LABELS, TEMPLATE)
    assert len(p) == 1 and "PCG_T18Tap" in p[0]


def test_save_refuses_stray_and_missing_volumes():
    g = dict(town_graphs(), PyPCG_Probe="/Game/PyPCG/Probe/PCG_PyProbe.PCG_PyProbe")
    assert any("PyPCG_Probe" in x for x in L.save_problems(g, LABELS))
    g = town_graphs()
    del g[LABELS[3]]
    assert any("missing" in x for x in L.save_problems(g, LABELS))


def test_no_unreal_import_at_module_level():
    import inspect
    src = inspect.getsource(L)
    assert "\nimport unreal" not in src
