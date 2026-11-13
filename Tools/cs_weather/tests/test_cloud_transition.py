import itertools
import math

import pytest

import cs_cloud_code as CC
import cs_cloud_motion as M
import cs_wx_resolve as R

EMPTY = {"components": {}}
PAIRS = [("art_towers", "art_storm"), ("art_mackerel", "art_cloudsea"), ("art_streets", "art_afterglow"),
         ("art_rays", "art_moonlit"), ("art_lenticular", "art_shelf")]


def res(name):
    return R.resolve(name, EMPTY)


def ppv_defaults():
    special = {"auto_exposure_method": "AEM_HISTOGRAM", "white_temp": 6500.0, "vignette_intensity": 0.4,
               "local_exposure_highlight_contrast_scale": 1.0}
    return {k: special.get(k, [1.0, 1.0, 1.0, 1.0] if k.startswith("color_") else 0.0) for k in R.managed_ppv()}


PPV = ppv_defaults()


def run(a, b, light="full", dur=1800.0, n=400, t0=100.0):
    st = M.new_state(res(a), 0.0)
    M.start_transition(st, res(b), t0, dur, light)
    return st, [M.frame(st, t0 + dur * i / n, PPV) for i in range(n + 1)]


def test_start_frame_is_the_current_cloud():
    st = M.new_state(res("art_towers"), 0.0)
    plain = M.frame(st, 100.0, PPV)
    M.start_transition(st, res("art_storm"), 100.0, 1800.0, "full")
    first = M.frame(st, 100.0, PPV)
    for n in CC.SLOT_NAMES:
        assert first["mid"][n] == pytest.approx(plain["mid"][n]), n
    assert first["mid"]["B_SlotOn"] == 0.0


def test_end_frame_is_the_designed_target():
    _st, frames = run("art_towers", "art_storm")
    last = frames[-1]
    target = M.new_slot(res("art_storm"), 0.0)
    want = M.slot_params(target, 0.0)
    for n in CC.SLOT_NAMES:
        if n != "SlotOn":
            assert last["mid"]["B_" + n] == pytest.approx(want[n], abs=1e-9), n
    assert last["mid"]["SlotOn"] == 0.0 and last["mid"]["B_SlotOn"] == 1.0
    static = M.look_static(res("art_storm"), target["clouds_light"])
    assert last["look"]["sun"] == pytest.approx(static["sun"])
    assert last["look"]["ppv"]["auto_exposure_min_brightness"] == pytest.approx(
        static["ppv"]["auto_exposure_min_brightness"])


def test_finish_moves_b_into_a_without_a_jump():
    st, frames = run("art_streets", "art_afterglow")
    before = frames[-1]
    M.finish_transition(st)
    after = M.frame(st, 100.0 + 1800.0, PPV)
    for n in CC.SLOT_NAMES:
        if n != "SlotOn":
            assert after["mid"][n] == pytest.approx(before["mid"]["B_" + n], abs=1e-9), n
    assert after["mid"]["B_SlotOn"] == 0.0 and st["look"]["name"] == "art_afterglow"


def _max_step(values):
    return max(abs(y - x) for x, y in zip(values, values[1:]))


def _storm(cloud):
    return cloud["CellStrength"] > 0.0 and cloud["LensAmt"] <= 0.0      # the lenticular uses CellStrength as a mask


@pytest.mark.parametrize("pair", PAIRS)
def test_parameters_are_continuous(pair):
    _s, coarse = run(*pair, n=400)
    _s, fine = run(*pair, n=1600)
    for key in coarse[0]["mid"]:
        base_key = key[2:] if key.startswith("B_") else key
        if base_key == "SlotOn" or base_key in M.WRAPPED:
            continue        # SlotOn switches by design (on an empty slot); wrapped time inputs: Task 5's tests
        c = _max_step([f["mid"][key] for f in coarse])
        f = _max_step([f["mid"][key] for f in fine])
        if c > 1e-9:
            assert f < c / 3.0 + 1e-9, (pair, key, c, f)       # a jump would not shrink with a finer step


def _flat_look(fr):
    out = {"sun_el": fr["look"]["sun"][0], "sun_az": fr["look"]["sun"][1]}
    for k, v in fr["look"]["ppv"].items():
        if isinstance(v, float):
            out["ppv." + k] = v
        elif isinstance(v, list):
            out.update({"ppv.%s.%d" % (k, i): float(x) for i, x in enumerate(v)})
    for s, vals in fr["look"]["components"].items():
        for k, v in vals.items():
            if isinstance(v, float):
                out["%s.%s" % (s, k)] = v
    return out


@pytest.mark.parametrize("pair", PAIRS)
def test_look_is_continuous(pair):
    _s, coarse = run(*pair, n=400)
    _s, fine = run(*pair, n=1600)
    keys = set(_flat_look(coarse[0])) & set(_flat_look(coarse[-1]))
    for key in sorted(keys):
        c = _max_step([_flat_look(f)[key] for f in coarse])
        f = _max_step([_flat_look(f)[key] for f in fine])
        if c > 1e-9:
            assert f < c / 3.0 + 1e-9, (pair, key, c, f)


def test_dome_enters_and_leaves():
    _s, frames = run("art_rays", "art_moonlit")
    domes = [f["look"]["dome"] for f in frames]
    assert domes[0] is False and domes[-1] is True
    first = domes.index(True)
    assert all(domes[first:])
    stars = [f["look"]["stars"]["StarIntensity"] for f in frames[first:]]
    assert stars[0] < 0.05 and stars[-1] == pytest.approx(2.0)
    assert all(b >= a - 1e-12 for a, b in zip(stars, stars[1:]))
    _s, back = run("art_moonlit", "art_towers")
    leaving = [f["look"]["dome"] for f in back]
    assert leaving[0] is True and leaving[-1] is False
    assert back[-1]["look"]["stars"] is None


@pytest.mark.parametrize("pair", [("art_towers", "art_storm"), ("art_storm", "art_lenticular"),
                                  ("art_rays", "art_shelf"), ("base", "art_mackerel")])
def test_incoming_slot_is_empty_when_it_switches_on(pair):
    _s, frames = run(*pair, n=1600)
    m = next(f for f in frames if f["mid"]["B_SlotOn"] == 1.0)["mid"]
    cloud = res(pair[1])["cloud"]
    assert m["B_CoverageBias"] <= -m["B_CoverageScale"] - 0.05 + 1e-3
    for k in ("B_FrontAmt", "B_RainDensity", "B_MammaAmt") + (("B_CellStrength",) if _storm(cloud) else ()):
        assert m[k] == pytest.approx(0.0, abs=1e-3), (pair, k)
    if cloud["LensAmt"] > 0.0:
        assert m["B_LensCut"] == pytest.approx(1.0, abs=1e-3)


@pytest.mark.parametrize("pair", [("art_storm", "art_towers"), ("art_lenticular", "art_rays"),
                                  ("art_shelf", "art_streets"), ("art_mackerel", "base")])
def test_outgoing_slot_is_empty_when_it_switches_off(pair):
    _s, frames = run(*pair, n=1600)
    m = [f for f in frames if f["mid"]["SlotOn"] == 1.0][-1]["mid"]
    cloud = res(pair[0])["cloud"]
    assert m["CoverageBias"] <= -m["CoverageScale"] - 0.05 + 1e-3
    for k in ("FrontAmt", "RainDensity", "MammaAmt") + (("CellStrength",) if _storm(cloud) else ()):
        assert m[k] == pytest.approx(0.0, abs=1e-3), (pair, k)
    if cloud["LensAmt"] > 0.0:
        assert m["LensCut"] == pytest.approx(1.0, abs=1e-3)


def test_union_layer_and_sample_cap():
    _s, frames = run("art_cloudsea", "art_afterglow")
    vc = frames[200]["vc"]
    assert vc["layer_bottom_altitude"] == 0.0 and vc["layer_height"] == pytest.approx(10.0)
    assert vc["view_sample_count_scale"] == pytest.approx(M.SAMPLE_SCALE_MAX)
    assert vc["tracing_max_distance"] == 120.0


def test_sun_takes_the_short_way():
    _s, frames = run("art_towers", "art_storm")             # azimuth 195 -> 85
    az = [f["look"]["sun"][1] for f in frames]
    assert min(az) >= 85.0 - 1e-9 and max(az) <= 195.0 + 1e-9


def test_clouds_mode_keeps_the_light():
    st, frames = run("art_lenticular", "art_shelf", light="clouds")
    lens = M.look_static(res("art_lenticular"))
    for f in (frames[0], frames[200], frames[-1]):
        assert f["look"]["sun"] == pytest.approx(lens["sun"])
        assert f["look"]["ppv"] == lens["ppv"]
    M.finish_transition(st)
    assert st["look"]["name"] == "art_lenticular" and st["slots"]["A"]["preset"] == "art_shelf"


def test_refusals():
    st = M.new_state(res("art_towers"), 0.0)
    names = R.names()
    assert M.check_target(st, "art_nope", names, 1800.0, "full")
    assert M.check_target(st, "art_towers", names, 1800.0, "full")
    assert M.check_target(st, "art_storm", names, 5.0, "full")
    assert M.check_target(st, "art_storm", names, 1800.0, "dim")
    assert M.check_target(st, "art_storm", names, 1800.0, "full") is None
    assert M.check_seek(st) is None
    M.start_transition(st, res("art_storm"), 0.0, 1800.0, "full")
    assert M.check_target(st, "art_rays", names, 1800.0, "full")
    assert M.check_seek(st)
    with pytest.raises(ValueError):
        M.start_transition(st, res("art_rays"), 10.0, 1800.0, "full")


def test_progress_depends_on_simulated_time_only():
    st = M.new_state(res("art_towers"), 0.0)
    M.start_transition(st, res("art_storm"), 50.0, 1000.0, "full")
    assert M.progress(st, 550.0) == pytest.approx(0.5)
    assert M.progress(st, 0.0) == 0.0 and M.progress(st, 5000.0) == 1.0


def test_every_pair_is_finite():
    cache = {n: res(n) for n in R.names()}
    for a, b in itertools.permutations(R.names(), 2):
        st = M.new_state(cache[a], 0.0)
        M.start_transition(st, cache[b], 0.0, 1800.0, "full")
        for i in range(51):
            fr = M.frame(st, 1800.0 * i / 50.0, PPV)
            for k, v in fr["mid"].items():
                assert math.isfinite(v), (a, b, i, k)
            vc = fr["vc"]
            top = vc["layer_bottom_altitude"] + vc["layer_height"]
            for on, r in ((fr["mid"]["SlotOn"], cache[a]), (fr["mid"]["B_SlotOn"], cache[b])):
                if on > 0.0:                      # the layer contains every slot that is on (Task 11 vc ramps)
                    v2 = r["components"]["VolumetricCloudComponent"]
                    assert vc["layer_bottom_altitude"] <= v2["layer_bottom_altitude"] + 1e-9, (a, b, i)
                    assert top >= v2["layer_bottom_altitude"] + v2["layer_height"] - 1e-9, (a, b, i)
            assert vc["view_sample_count_scale"] <= M.SAMPLE_SCALE_MAX + 1e-9


def _numbers(vc):
    return {k: v for k, v in vc.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


@pytest.mark.parametrize("pair", PAIRS + [("art_rays", "art_storm"), ("cirrus", "art_storm"), ("base", "cirrus")])
def test_cloud_component_is_continuous_at_both_ends(pair):
    """The first transition frame keeps the outgoing cloud component, the last one is the incoming preset's: a component
    that snaps to the union at the start or back at the end is a one-frame jump (Task 11, frame 450 of
    mackerel -> cloudsea: 7.8 vs 0.5)."""
    st = M.new_state(res(pair[0]), 0.0)
    before = _numbers(M.frame(st, 100.0, PPV)["vc"])
    M.start_transition(st, res(pair[1]), 100.0, 1800.0, "full")
    first = _numbers(M.frame(st, 100.0, PPV)["vc"])
    last = _numbers(M.frame(st, 1900.0, PPV)["vc"])
    M.finish_transition(st)
    after = _numbers(M.frame(st, 1900.0, PPV)["vc"])
    for k, v in before.items():
        assert first[k] == pytest.approx(v), (pair, "start", k)
    for k, v in after.items():
        assert last[k] == pytest.approx(v), (pair, "end", k)


@pytest.mark.parametrize("pair", PAIRS)
def test_cloud_component_is_continuous_inside(pair):
    _s, coarse = run(*pair, n=400)
    _s, fine = run(*pair, n=1600)
    for key in _numbers(coarse[0]["vc"]):
        c = _max_step([f["vc"][key] for f in coarse])
        f = _max_step([f["vc"][key] for f in fine])
        if c > 1e-9:
            assert f < c / 3.0 + 1e-9, (pair, key, c, f)


def test_union_sample_scale_keeps_both_slots_steps():
    """Long in-layer paths take SampleCountMax steps over the whole layer: the union keeps the thinner slot's step size
    (towers 6 km inside the storm's 13 km: 4 x 13 / 6)."""
    st = M.new_state(res("art_towers"), 0.0)
    M.start_transition(st, res("art_storm"), 0.0, 1800.0, "full")
    vc = M.frame(st, 900.0, PPV)["vc"]
    assert vc["layer_height"] == pytest.approx(13.0)
    assert vc["view_sample_count_scale"] == pytest.approx(4.0 * 13.0 / 6.0)


def test_a_storm_target_waits_for_the_layer():
    st = M.new_state(res("art_towers"), 0.0)
    M.start_transition(st, res("art_storm"), 0.0, 1800.0, "full")
    for i in range(80):
        fr = M.frame(st, 1800.0 * i / 400.0, PPV)
        if fr["mid"]["B_SlotOn"] > 0.0:
            assert M.ease(fr["p"]) >= M.LAYER_RAMP - 1e-12, i


SNAPSHOT_FILE = "data/original_extra_snapshot.json"   # the demo level's original values, as cs_weather.py records them


def _snapshot():
    import json
    import os
    return json.load(open(os.path.join(os.path.dirname(__file__), SNAPSHOT_FILE), encoding="utf-8"))


def test_lerp_val_blends_plain_list_with_encoded_value():
    """Snapshot values arrive encoded ({"__t": "LinearColor", "v": [...]}), preset values as plain lists (Final review
    Important 1): they must blend element by element, not switch at w = 0.5."""
    plain = [1.0, 0.868, 0.12, 1.0]
    enc = {"__t": "LinearColor", "v": [0.346, 1.0, 0.045, 531.6]}
    for a, b in ((plain, enc), (enc, plain)):
        va = a["v"] if isinstance(a, dict) else a
        vb = b["v"] if isinstance(b, dict) else b
        got = M.lerp_val(a, b, 0.25)
        got_v = got["v"] if isinstance(got, dict) else got
        assert got_v == pytest.approx([x + (y - x) * 0.25 for x, y in zip(va, vb)])
    fog_enc = {"__t": "Fog", "v": {"fog_density": 0.02, "fog_height_falloff": 0.2, "fog_height_offset": 0.0}}
    fog_plain = {"fog_density": 0.0, "fog_height_falloff": 0.006, "fog_height_offset": 0.0}
    got = M.lerp_val(fog_plain, fog_enc, 0.5)
    got_v = got["v"] if "__t" in got else got
    assert got_v["fog_density"] == pytest.approx(0.01) and got_v["fog_height_falloff"] == pytest.approx(0.103)


def _flat(look):
    """Numeric leaves of a look: component values (encoded or plain), the sun, the post-process values, the stars."""
    out = {"sun_el": look["sun"][0], "sun_az": look["sun"][1]}

    def add(prefix, v):
        if isinstance(v, dict) and "__t" in v:
            v = v["v"]
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            out[prefix] = float(v)
        elif isinstance(v, list):
            for i, x in enumerate(v):
                add("%s.%d" % (prefix, i), x)
        elif isinstance(v, dict):
            for k, x in v.items():
                add("%s.%s" % (prefix, k), x)

    for s, vals in look["components"].items():
        for k, v in vals.items():
            add("%s.%s" % (s, k), v)
    for k, v in look["ppv"].items():
        add("ppv." + k, v)
    for k, v in (look["stars"] or {}).items():
        add("stars." + k, v)
    return out


def test_no_full_transition_switches_a_value_at_the_middle():
    """Every ordered preset pair, resolved with the real snapshot: across the middle of the light window (raw progress
    0.4995 -> 0.5005) no numeric value may move by more than 2 % of its whole change (Final review Important 1: 210 of 462
    pairs switched snapshot colours in one frame)."""
    snap = _snapshot()
    cache = {n: R.resolve(n, snap) for n in R.names()}
    bad = []
    for a, b in itertools.permutations(R.names(), 2):
        st = M.new_state(cache[a], 0.0)
        M.start_transition(st, cache[b], 0.0, 1000.0, "full")
        f0, f1 = (_flat(M.frame(st, t, PPV)["look"]) for t in (0.0, 1000.0))
        m0, m1 = (_flat(M.frame(st, t, PPV)["look"]) for t in (499.5, 500.5))
        for k in set(m0) & set(m1) & set(f0) & set(f1):
            whole = abs(f1[k] - f0[k])
            if abs(m1[k] - m0[k]) > 0.02 * whole + 1e-9:
                bad.append((a, b, k, round(m0[k], 4), round(m1[k], 4)))
                break
    assert not bad, "%d pairs jump, e.g. %s" % (len(bad), bad[:3])
