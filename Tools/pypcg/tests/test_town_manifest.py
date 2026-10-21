import town_manifest


def census():
    return {"_level": "/Game/PyPCG/L_PyTown", "stages": [
        {"stage": 1, "graph": "PCG_1_1_Terrain", "title": "地形底座", "instances": 0, "status": "unmeasured",
         "notes": ["terrain heights not measurable; see the screenshot"], "params": {"CityFlatness": 0.6},
         "shot": "pt_stage_01_PCG_1_1_Terrain_p1.png"},
        {"stage": 11, "graph": "PCG_3_3_1_Buildings", "title": "建筑", "instances": 1234, "status": "ok",
         "notes": [], "params": {"ComplexBuildingShapes": True}, "shot": "pt_stage_11_PCG_3_3_1_Buildings_p1.png"}]}


def test_manifest_shapes_stages_for_the_report(tmp_path):
    (tmp_path / "pt_stage_11_PCG_3_3_1_Buildings_p1.png").write_bytes(b"x")
    m = town_manifest.build(census(), str(tmp_path))
    assert m["level"] == "/Game/PyPCG/L_PyTown" and len(m["stages"]) == 2
    s1, s11 = m["stages"]
    assert s1["metrics"]["status"] == "empty" and "terrain" in s1["notes"] and "CityFlatness" in s1["notes"]
    assert s11["metrics"] == {"instances": 1234, "debug_instances": 0, "status": "ok"}
    assert s11["shots"][0]["kind"] == "geometry" and s11["shots"][0]["path"].endswith("_p1.png")
    assert s1["shots"][0].get("img_missing")


def test_a_reshot_name_resolves_to_its_promoted_canonical_file(tmp_path):
    # The pass file records the claimed name of a re-shoot (`_p1_r2.png`); promote_variants() renames it
    # onto the canonical `_p1.png`, so that is the file on disk.
    (tmp_path / "pt_stage_11_PCG_3_3_1_Buildings_p1.png").write_bytes(b"x")
    c = census()
    c["stages"][1]["shot"] = "pt_stage_11_PCG_3_3_1_Buildings_p1_r2.png"
    s11 = town_manifest.build(c, str(tmp_path))["stages"][1]
    assert not s11["shots"][0].get("img_missing") and s11["shots"][0]["path"].endswith("Buildings_p1.png")


def test_pass_two_variation_and_determinism_reach_the_notes(tmp_path):
    c = census()
    c["stages"][1].update(deterministic=False, instances_pass2=1240,
                          variation={"label": "native run-to-run variation", "pass1": 1234, "pass2": 1240,
                                     "net": 6, "per_mesh_abs": 8, "differing_meshes": {"/Game/A": [10, 16]}})
    c["stages"][0].update(deterministic=True, instances_pass2=0)
    s1, s11 = town_manifest.build(c, str(tmp_path))["stages"]
    assert "1234" in s11["notes"] and "1240" in s11["notes"] and "native run-to-run variation" in s11["notes"]
    assert "A 10→16" in s11["notes"]
    assert "第二遍" in s1["notes"]
