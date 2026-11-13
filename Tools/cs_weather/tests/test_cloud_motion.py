import math

import pytest

import cs_cloud_code as CC
import cs_cloud_motion as M
import cs_wx_resolve as R

EMPTY = {"components": {}}


def res(name):
    return R.resolve(name, EMPTY)


def slot(name, t=0.0):
    return M.new_slot(res(name), t)


def test_time_params_are_neutral_at_age_zero():
    for name in ("base", "art_towers", "art_afterglow", "art_storm", "cirrus"):
        s = slot(name)
        for k, v in M.time_params(s["base"], s["motion"], 0.0).items():
            if k not in ("EvoAmt", "EvoScaleKm"):
                assert v == 0.0, (name, k)


def test_slot_params_at_age_zero_are_the_preset():
    for name in ("art_mackerel", "art_storm", "art_shelf", "art_lenticular", "art_cloudsea", "storm"):
        s = slot(name, 500.0)
        p = M.slot_params(s, 500.0)
        for k, v in s["base"].items():
            assert p[k] == pytest.approx(v, abs=1e-12), (name, k)
        assert p["SlotOn"] == 1.0


def test_advection_follows_the_compass_heading():
    s = slot("base")
    s["motion"].update({"wind_ms": 10.0, "wind_deg": 90.0})
    tp = M.time_params(s["base"], s["motion"], 1000.0)
    assert tp["AdvX"] == pytest.approx(0.0, abs=1e-9)
    assert tp["AdvY"] == pytest.approx(10.0)


def test_detail_offsets_follow_the_air():
    s = slot("base")                                   # StretchX 1, StretchAngle 0
    s["motion"].update({"wind_ms": 12.0, "wind_deg": 30.0, "detail_speed": 1.0, "boil_detail_ms": 0.0})
    tp = M.time_params(s["base"], s["motion"], 777.0)
    ds = s["base"]["DetailScaleKm"]
    assert tp["DetailOffU"] == pytest.approx(M.frac(-tp["AdvX"] / ds))
    assert tp["DetailOffV"] == pytest.approx(M.frac(-tp["AdvY"] / ds))
    assert tp["Detail2OffU"] == pytest.approx(M.frac(2.71 * (-tp["AdvX"] / ds)))


def test_detail_offsets_in_the_stretched_frame():
    s = slot("art_afterglow")                          # StretchX 5, StretchAngle 255
    s["motion"].update({"wind_ms": 40.0, "wind_deg": 255.0, "detail_speed": 1.0, "boil_detail_ms": 0.0})
    tp = M.time_params(s["base"], s["motion"], 100.0)
    along = 40.0e-3 * 100.0 / s["base"]["StretchX"]
    assert tp["DetailOffU"] == pytest.approx(M.frac(-along / s["base"]["DetailScaleKm"]))
    assert min(tp["DetailOffV"], 1.0 - tp["DetailOffV"]) == pytest.approx(0.0, abs=1e-9)


def test_wrapped_values_stay_in_unit_interval_for_long_runs():
    s = slot("art_afterglow")
    for tau in (0.0, 1.0, 3.6e3, 3.6e6, 1.0e7, -1.0e5):
        tp = M.time_params(s["base"], s["motion"], tau)
        for k in M.WRAPPED:
            assert 0.0 <= tp[k] < 1.0 and math.isfinite(tp[k]), (k, tau)


def test_rising_boil_moves_the_pattern_up():
    s = slot("art_towers")
    s["motion"]["boil_billow_ms"] = 3.0
    got = M.time_params(s["base"], s["motion"], 10.0)["BoilBillow"]
    assert got == pytest.approx(M.frac(-3.0e-3 * 10.0 / (s["base"]["BillowScaleKm"] * 8.0)))


def test_osc_mod_is_neutral_at_zero_and_bounded():
    s = slot("art_storm")
    s["motion"]["mods"] = [{"param": "OvershootKm", "osc": [0.4, 8.0, 1.0]}]
    base = s["base"]["OvershootKm"]
    vals = [M.slot_params(s, s["tau0"] + tau)["OvershootKm"] for tau in range(0, 2000, 7)]
    assert vals[0] == pytest.approx(base)
    assert max(abs(v - base) for v in vals) <= 0.8 + 1e-9


def test_approach_mod_is_bounded_ahead_and_linear_before_zero():
    s = slot("art_shelf")
    s["motion"]["mods"] = [{"params": ["FrontX", "FrontY"], "approach": [2.5, 12.0, 100.0]}]
    x0, y0 = s["base"]["FrontX"], s["base"]["FrontY"]
    hx, hy = M.heading(100.0)

    def along(tau):
        p = M.slot_params(s, s["tau0"] + tau)
        return (p["FrontX"] - x0) * hx + (p["FrontY"] - y0) * hy

    assert along(1.0e6) == pytest.approx(2.5, rel=1e-6)
    assert along(-1800.0) == pytest.approx(-12.0e-3 * 1800.0)
    assert along(0.0) == pytest.approx(0.0, abs=1e-12)


def test_motion_defaults_by_layer_height():
    assert M.motion_for(None, res("cirrus")["cloud"])["wind_ms"] == 30.0
    assert M.motion_for(None, res("clear_noon")["cloud"])["wind_ms"] == 6.0
    storm = M.motion_for(None, res("storm")["cloud"])
    assert storm["form_window"] == [0.0, 1.0] and storm["mods"] == []


def test_unknown_motion_key_is_an_error():
    with pytest.raises(KeyError):
        M.motion_for({"wnd_ms": [3.0, "typo"]}, res("base")["cloud"])


def test_plain_frame_writes_every_slot_parameter_and_turns_b_off():
    st = M.new_state(res("art_towers"), 0.0)
    fr = M.frame(st, 120.0, {})
    for n in CC.SLOT_NAMES + M.GLOBAL_PARAMS:
        assert n in fr["mid"], n
    assert fr["mid"]["B_SlotOn"] == 0.0 and fr["mid"]["SlotOn"] == 1.0
    assert fr["vc"]["layer_height"] == 6.0
    assert fr["look"]["dome"] is False and fr["look"]["sun"] == [38.0, 195.0]


def test_adv_budget_long_run():
    s = slot("art_mackerel")
    assert M.adv_km(s, s["tau0"] + 3600.0) == pytest.approx(s["motion"]["wind_ms"] * 3.6)
