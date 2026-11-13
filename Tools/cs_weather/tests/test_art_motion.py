import cs_cloud_code as CC
import cs_cloud_motion as M
import cs_weather_presets as P
import cs_wx_resolve as R

EMPTY = {"components": {}}


def test_every_art_preset_has_motion_with_reasons():
    for name in P.ART_ORDER:
        mo = P.PRESETS[name].get("motion")
        assert mo, name
        for key, e in mo.items():
            assert key in M.MOTION_KEYS, (name, key)
            if key == "mods":
                assert isinstance(e, list) and e, (name, key)
                for item in e:
                    assert isinstance(item, list) and len(item) == 2 and isinstance(item[0], dict), (name, item)
                    assert item[1].strip(), (name, item)
            else:
                assert isinstance(e, list) and len(e) == 2 and isinstance(e[1], str), (name, key)
        for key in ("wind_ms", "wind_deg", "clip_speed"):
            assert key in mo and mo[key][1].strip(), (name, key)


def test_mods_name_real_parameters():
    for name in P.ART_ORDER:
        for mod, _why in P.PRESETS[name]["motion"].get("mods", []):
            assert "osc" in mod or "approach" in mod, (name, mod)
            names = [mod["param"]] if "param" in mod else mod["params"]
            if "params" in mod:
                assert len(mod["params"]) % 2 == 0
            for n in names:
                assert n in CC.SLOT_NAMES, (name, n)


def test_motion_resolves_for_every_preset():
    for name in R.names():
        r = R.resolve(name, EMPTY)
        m = M.motion_for(r.get("motion"), r["cloud"])
        assert m["wind_ms"] >= 0.0 and m["clip_speed"] > 0.0, name
        assert 0.0 <= m["form_window"][0] < m["form_window"][1] <= 1.0, name
        assert 0.0 <= m["fade_window"][0] < m["fade_window"][1] <= 1.0, name


def test_storm_and_shelf_motion():
    storm = M.motion_for(P.PRESETS["art_storm"]["motion"], R.resolve("art_storm", EMPTY)["cloud"])
    assert storm["form_window"] == [0.0, 1.0]
    assert {m["param"] for m in storm["mods"]} == {"OvershootKm", "AnvilShiftKm"}
    shelf = M.motion_for(P.PRESETS["art_shelf"]["motion"], R.resolve("art_shelf", EMPTY)["cloud"])
    assert shelf["mods"][0]["approach"] == [2.5, 12.0, 100.0] and shelf["evo_amt"] == 0.0


def test_transition_clips_reference_presets_and_cameras():
    assert len(P.TRANSITION_CLIPS) == 5 and len({c["clip"] for c in P.TRANSITION_CLIPS}) == 5
    for c in P.TRANSITION_CLIPS:
        assert c["from"] in P.ART_ORDER and c["to"] in P.ART_ORDER and c["from"] != c["to"]
        assert c["light"] in ("full", "clouds")
        assert len(c["cams"]) == 2 and all(cam in P.CAMERAS for cam in c["cams"])
        assert c["why"].strip()
    assert [c["light"] for c in P.TRANSITION_CLIPS].count("clouds") == 1
