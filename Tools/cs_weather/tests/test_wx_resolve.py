import cs_weather_presets as P
import cs_wx_resolve as R

EMPTY = {"components": {}}


def test_every_preset_resolves_and_the_cloud_layer_follows():
    assert len(R.names()) == 22
    for name in R.names():
        r = R.resolve(name, EMPTY)
        assert r["name"] == name
        vc = r["components"]["VolumetricCloudComponent"]
        assert r["cloud"]["LayerKm"] == vc["layer_height"]
        assert r["cloud"]["BottomKm"] == vc["layer_bottom_altitude"]


def test_base_is_the_ten_oclock_look():
    r = R.resolve("base", EMPTY)
    assert r["sun"] == P.BASE_SUN
    for section, props in P.BASE.items():
        if section == "PPV":
            continue
        for k, v in props.items():
            assert r["components"][section][k] == v, (section, k)
    assert r["ppv"] == P.BASE["PPV"]
    assert r["mi"] == "MI_CS_CumulusCloud_Clear"
    assert r["cloud"]["BottomKm"] == 1.4 and r["cloud"]["LayerKm"] == 4.0
    assert r["night_sky"] is None and r["motion"] is None


def test_art_storm_values():
    r = R.resolve("art_storm", EMPTY)
    assert r["components"]["VolumetricCloudComponent"]["layer_height"] == 13.0
    assert r["cloud"]["BottomKm"] == 0.0 and r["cloud"]["LayerKm"] == 13.0
    assert r["cloud"]["CellX"] == -10.8
    assert r["ppv"]["vignette_intensity"] == 0.55
    assert r["ppv"]["color_saturation"] == P.CAMERA_LOOK["color_saturation"][0]
    assert r["components"]["SkyAtmosphereComponent"]["other_absorption_scale"] == 0.001919


def test_night_preset_has_its_dome():
    r = R.resolve("art_moonlit", EMPTY)
    assert r["night_sky"] == {"StarIntensity": 2.0, "StarSharp": 4.0}
    assert r["components"]["DirectionalLightComponent"]["intensity"] == 0.25


def test_precedence_override_preset_base_snapshot():
    snap = {"components": {"SkyAtmosphereComponent": {"mie_absorption": [0.1, 0.2, 0.3, 1.0]}}}
    assert R.resolve("base", snap)["components"]["SkyAtmosphereComponent"]["mie_absorption"] == [0.1, 0.2, 0.3, 1.0]
    over = R.resolve("art_towers", snap, {"set": {"SkyAtmosphereComponent.mie_scattering_scale": 0.5}})
    assert over["components"]["SkyAtmosphereComponent"]["mie_scattering_scale"] == 0.5
    assert R.resolve("art_towers", snap)["components"]["SkyAtmosphereComponent"]["mie_scattering_scale"] == 0.02


def test_cloud_override_and_layer():
    r = R.resolve("art_towers", EMPTY, {"cloud": {"CoverageScale": 0.1}})
    assert r["cloud"]["CoverageScale"] == 0.1
    assert r["cloud"]["LayerKm"] == 6.0 and r["cloud"]["BottomKm"] == 1.2


def test_managed_props_without_any_source_are_left_out():
    assert "mie_absorption" in R.managed()["SkyAtmosphereComponent"]
    assert "mie_absorption" not in R.resolve("base", EMPTY)["components"]["SkyAtmosphereComponent"]
