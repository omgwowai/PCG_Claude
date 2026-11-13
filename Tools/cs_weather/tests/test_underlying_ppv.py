import pytest

import cs_cloud_motion as M

STRUCT = {"local_exposure_highlight_contrast_scale": 1.0, "local_exposure_shadow_contrast_scale": 1.0,
          "white_temp": 6500.0, "vignette_intensity": 0.4, "color_contrast": [1.0, 1.0, 1.0, 1.0]}
CVARS = {"r.DefaultFeature.LocalExposure.HighlightContrastScale": 0.8,
         "r.DefaultFeature.LocalExposure.ShadowContrastScale": 0.8, "r.LocalExposure": 1}


def test_local_exposure_starts_from_the_project_defaults():
    """SceneView.cpp 2081-2089: the view starts the local-exposure contrast scales from their r.DefaultFeature console
    variables (0.8 in this project), not from the struct default 1.0 (Task 11: the frame-450 step)."""
    u = M.underlying_ppv(STRUCT, CVARS, [])
    assert u["local_exposure_highlight_contrast_scale"] == pytest.approx(0.8)
    assert u["local_exposure_shadow_contrast_scale"] == pytest.approx(0.8)
    assert u["white_temp"] == 6500.0 and u["vignette_intensity"] == 0.4


def test_local_exposure_off_means_one():
    u = M.underlying_ppv(STRUCT, dict(CVARS, **{"r.LocalExposure": 0}), [])
    assert u["local_exposure_highlight_contrast_scale"] == 1.0


def test_level_volumes_blend_in_by_priority():
    vols = [{"priority": 5, "blend_weight": 1.0, "overrides": {"white_temp": 5000.0}},
            {"priority": 0, "blend_weight": 1.0, "overrides": {"white_temp": 7000.0, "vignette_intensity": 0.2}},
            {"priority": 1, "blend_weight": 0.5, "overrides": {"color_contrast": [1.2, 1.2, 1.2, 1.0]}}]
    u = M.underlying_ppv(STRUCT, CVARS, vols)
    assert u["white_temp"] == 5000.0                       # the highest priority applies last
    assert u["vignette_intensity"] == pytest.approx(0.2)
    assert u["color_contrast"] == pytest.approx([1.1, 1.1, 1.1, 1.0])
    assert "auto_exposure_bias" not in u                    # only the managed keys the caller passed


def test_transition_ends_on_the_underlying_value():
    """mackerel (local exposure highlight 0.75) -> cloud sea (not set): the last transition frame must carry the value the
    view has once our override is off -- the project default 0.8, not 1.0."""
    import cs_wx_resolve as R
    ppv = M.underlying_ppv(dict(STRUCT, auto_exposure_min_brightness=-10.0, auto_exposure_max_brightness=20.0,
                                auto_exposure_bias=1.0, auto_exposure_method="AEM_HISTOGRAM",
                                color_saturation=[1.0, 1.0, 1.0, 1.0], white_tint=0.0), CVARS, [])
    st = M.new_state(R.resolve("art_mackerel", {"components": {}}), 0.0)
    M.start_transition(st, R.resolve("art_cloudsea", {"components": {}}), 0.0, 1800.0, "full")
    last = M.frame(st, 1799.999, ppv)
    assert last["look"]["ppv"]["local_exposure_highlight_contrast_scale"] == pytest.approx(0.8, abs=1e-3)
