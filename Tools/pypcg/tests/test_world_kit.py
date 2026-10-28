from pypcg.world import kit as K


def test_every_level_module_has_a_mesh_and_a_width():
    for fam, f in K.FAMILIES.items():
        assert f["palette"] in K.TINTS, fam
        for code, lv in f["levels"].items():
            assert lv["h"] > 0.0 and lv["mods"], (fam, code)
            for sym, m in lv["mods"].items():
                assert m["mesh"].startswith("/Game/") and "." in m["mesh"].rsplit("/", 1)[1], (fam, code, sym)
                assert m["w"] > 0.0 and m["kit"], (fam, code, sym)


def test_bays_line_up_across_the_levels_of_a_family():
    """The windows of a facade sit above each other: every level of the family's bay group has the same symbols
    with the same widths (the BDF's modules of a style share the grid)."""
    for fam, f in K.FAMILIES.items():
        widths = None
        for code, lv in f["levels"].items():
            if lv.get("band"):
                continue
            w = {s: f["bays"][s] for s in f["bays"]}
            for s in f["bays"]:
                assert s in lv["mods"] and abs(lv["mods"][s]["w"] - w[s]) < 1e-9, (fam, code, s)
            widths = widths or w
            assert w == widths


def test_corners_fit_in_the_end_zone():
    for fam, f in K.FAMILIES.items():
        for code, lv in f["levels"].items():
            c = lv["corner"]
            assert c["cx"] > 0.0 and c["cy"] > 0.0, (fam, code)
            assert c["cx"] <= f["end"] + 2.0 and c["cy"] <= f["end"] + 2.0, (fam, code)


def test_family_02_uses_fifty_centimetre_corners_and_four_and_five_metre_bays():
    f = K.FAMILIES["F02"]
    assert f["end"] == 50.0 and f["bays"] == {"S": 400.0, "L": 500.0, "P": 50.0}


def test_material_for_a_module():
    g = K.FAMILIES["F02"]["levels"]["G"]["mods"]["S"]
    assert K.material(g, "Base") == ""                                      # its own material
    assert K.material(g, "Ochre") == "/Game/PyPCG/World/Town/MI_1st_Floor_Kit_02_Ochre.MI_1st_Floor_Kit_02_Ochre"
    fix = K.FAMILIES["F01"]["levels"]["G"]["mods"]["P"]                     # lost its material on import
    assert K.material(fix, "Base").endswith("Modular_Building_Ground_Floor_Window_Kit_00_inst")


def test_every_tinted_material_is_listed_for_the_material_script():
    need = {path for path, _parent, _color in K.materials_needed()}
    for fam, f in K.FAMILIES.items():
        for lv in f["levels"].values():
            for m in list(lv["mods"].values()) + [lv["corner"]]:
                if m.get("mesh"):
                    for tint in K.TINTS[f["palette"]]:
                        mat = K.material(m, tint if not lv.get("band") else "Base")
                        assert mat == "" or mat in need or mat == K.inst(m["kit"]), (fam, m["kit"], tint)
    for tint in K.TINTS["Roof"]:
        assert K.tinted(K.ROOF["kit"], tint) in need
    assert len(need) == len(K.materials_needed())
