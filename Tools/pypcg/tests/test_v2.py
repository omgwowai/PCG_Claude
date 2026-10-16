import pytest

from pypcg import geo, v2

TH = dict(v2.DEFAULTS)


def item(tags, kind="polygon", area=0.0, length=0.0, points=0, bbox=((0, 0), (100, 100))):
    return {"tags": list(tags), "class": "", "kind": kind, "area_m2": area, "length_m": length, "points": points,
            "bbox": [list(bbox[0]), list(bbox[1])]}


def rec(items, total=0, per_mesh=None, generated=True):
    return {"generated": generated, "items": items, "instances": {"total": total, "per_mesh": per_mesh or {}, "components": {}}}


def districts(scale=1.0, n=6):
    return rec([item(["SmallDistricts", "Type:Polygon2D"], area=100.0 * scale) for _ in range(n)])


def test_describe_and_summarize():
    poly = geo.Polygon([(0, 0), (10000, 0), (10000, 10000), (0, 10000)])
    d = v2.describe(poly, ["Lots", "Type:Polygon2D"], "PCGPolygon2DData")
    assert d["kind"] == "polygon" and d["area_m2"] == pytest.approx(10000.0)
    s = v2.summarize([d, d])
    assert set(s) == {"Lots"} and s["Lots"]["n"] == 2 and s["Lots"]["area_m2"] == pytest.approx(20000.0)
    line = v2.describe(geo.Spline([(0, 0, 0), (100, 0, 0)]), ["Roads"])
    assert line["kind"] == "spline" and line["length_m"] == pytest.approx(1.0)


def test_identical_runs_pass():
    v = v2.verdict(districts(), [districts()] * 5, False, TH)
    assert v["pass"] and not v["failures"]


def test_missing_tag_fails_and_bookkeeping_tags_are_ignored():
    run = rec([item(["Type:Polygon2D"], area=100.0)])
    v = v2.verdict(districts(), [run], False, TH)
    assert not v["pass"] and any("SmallDistricts" in f for f in v["failures"])


def test_median_decides():
    runs = [districts(1.0), districts(1.05), districts(0.95), districts(2.0), districts(0.1)]
    assert v2.verdict(districts(), runs, False, TH)["pass"]
    assert not v2.verdict(districts(), [districts(1.3)] * 5, False, TH)["pass"]


def test_few_items_skip_count_and_area_but_not_points():
    off = rec([item(["Big"], area=100.0, points=1000)])
    assert v2.verdict(off, [rec([item(["Big"], area=300.0, points=1000)])], False, TH)["pass"]
    assert not v2.verdict(off, [rec([item(["Big"], area=100.0, points=100)])], False, TH)["pass"]


def test_bbox_outside_the_official_one_fails():
    far = rec([item(["SmallDistricts"], area=100.0, bbox=((0, 0), (500000, 100)))] * 6)
    v = v2.verdict(districts(), [far], False, TH)
    assert not v["pass"] and any("outside" in f for f in v["failures"])


def test_kind_change_fails():
    off = rec([item(["Roads"], kind="spline", length=10.0)] * 6)
    run = rec([item(["Roads"], kind="points", points=10)] * 6)
    assert not v2.verdict(off, [run], False, TH)["pass"]


def test_instances_and_mesh_shares():
    off = rec([], total=1000, per_mesh={"/A": 500, "/B": 500})
    assert v2.verdict(off, [rec([], total=1100, per_mesh={"/A": 560, "/B": 540})], False, TH)["pass"]
    assert not v2.verdict(off, [rec([], total=1000, per_mesh={"/A": 800, "/B": 200})], False, TH)["pass"]


def test_deterministic_stages_use_the_tight_tolerance():
    assert not v2.verdict(districts(), [districts(1.05)], True, TH)["pass"]
    assert v2.verdict(districts(), [districts(1.005)], True, TH)["pass"]


def test_downstream_failures():
    ok = rec([item(["X"])], total=10)
    assert v2.downstream({7: (ok, ok)}) == []
    assert v2.downstream({7: (ok, rec([item(["X"])], total=0))}) == ["stage 7: no instances (official 10)"]
    assert v2.downstream({7: (ok, rec([], total=10, generated=False))})[0].startswith("stage 7: not generated")


def test_thresholds_merge_stage_overrides(tmp_path, monkeypatch):
    path = tmp_path / "t.json"
    path.write_text('{"default": {"area": 0.1}, "stages": {"6": {"area": 0.2}}}')
    monkeypatch.setattr(v2, "THRESHOLDS", str(path))
    assert v2.thresholds(6)["area"] == 0.2 and v2.thresholds(7)["area"] == 0.1 and v2.thresholds(7)["count"] == 0.25


def test_same_compares_rounded_summaries():
    assert v2.same(districts(), districts()) and not v2.same(districts(), districts(1.01))


def test_contract_tags_ignore_bookkeeping_tags():
    off = rec([item(["SmallDistricts", "X", "City"], area=100.0) for _ in range(6)])
    run = rec([item(["SmallDistricts"], area=100.0) for _ in range(6)])
    assert v2.verdict(off, [run], False, TH, tags={"SmallDistricts"})["pass"]
    assert not v2.verdict(off, [run], False, TH)["pass"]        # tags=None still sees X and City
    s = v2.summarize(off["items"], tags={"SmallDistricts"})
    assert set(s) == {"SmallDistricts"} and s["SmallDistricts"]["n"] == 6
    assert v2.summarize(off["items"], tags={"Nothing"}) == {}


def test_empty_contract_tags_group_everything_as_all():
    off = rec([item(["SomeTag"], area=100.0) for _ in range(6)], total=10)
    run = rec([item(["AnotherTag"], area=100.0) for _ in range(6)], total=10)
    assert set(v2.summarize(off["items"], tags=set())) == {"(all)"}
    assert v2.verdict(off, [run], False, TH, tags=set())["pass"]
    assert not v2.verdict(off, [rec([item(["AnotherTag"], area=300.0) for _ in range(6)], total=10)],
                          False, TH, tags=set())["pass"]
    assert v2.same(off, run, set())
