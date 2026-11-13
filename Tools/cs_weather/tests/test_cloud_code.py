import re

import cs_cloud_code as CC


def test_slot_names_are_the_scalars_without_pixel_angle_plus_extras():
    expect = [s[0] for s in CC.SCALARS if s[0] != "PixelAngle"] + [s[0] for s in CC.SLOT_EXTRA]
    assert CC.SLOT_NAMES == expect
    assert len(set(CC.SLOT_NAMES)) == len(CC.SLOT_NAMES) == 104


def test_pins_unique_and_counted():
    pins = CC.pins()
    assert len(pins) == len(set(pins)) == 217
    assert pins[:len(CC.NODE_INPUTS)] == CC.NODE_INPUTS
    for n in CC.SLOT_NAMES:
        assert n in pins and "B_" + n in pins


def test_slot_b_defaults_match_a_except_slot_on():
    d = {n: v for n, v, _g in CC.scalar_pins()}
    assert d["SlotOn"] == 1.0 and d["B_SlotOn"] == 0.0
    for n, v, _g in CC.SLOT_SCALARS:
        if n != "SlotOn":
            assert d["B_" + n] == v, n


def test_v2_defaults_are_neutral():
    d = {n: v for n, v, _g in CC.SLOT_EXTRA}
    for n in ("AdvX", "AdvY", "DetailOffU", "DetailOffV", "DetailOffW", "Detail2OffU", "Detail2OffV", "Detail2OffW",
              "EvoAmt", "EvoPhase", "BoilShape", "BoilBillow", "BoilTurret", "MammaPhase", "MackerelPhase", "LumpPhase",
              "RainFall"):
        assert d[n] == 0.0, n
    assert d["ExtinctionMax"] == 0.12 and d["BottomKm"] == 1.4 and d["SlotOn"] == 1.0


def test_every_slot_parameter_is_read_by_the_body():
    body = CC.slot_body("A")
    for n in CC.SLOT_NAMES:
        if n != "SlotOn":
            assert re.search(r"\b%s\b" % n, body), n


def test_slot_b_body_has_no_bare_slot_parameter():
    body = CC.slot_body("B")
    for n in CC.SLOT_NAMES:
        assert not re.search(r"(?<![A-Za-z0-9_])%s\b" % n, body), n
    for g in ["P", "Cam", "Alt", "SD", "L", "WeatherTex", "ShapeTex", "DetailTex", "PixelAngle"]:
        assert re.search(r"\b%s\b" % g, body), g


def test_generate_combines_both_slots():
    code = CC.generate()
    assert code.count("if (SlotOn > 0.0)") == 1 and code.count("if (B_SlotOn > 0.0)") == 1
    assert code.rstrip().endswith("return sig;")
    for out in ("Cons = consM;", "AO = sig > 0.0", "Alb = sig > 0.0"):
        assert code.count(out) == 1, out
    assert "return outD" not in code and not re.search(r"(?<![A-Za-z0-9_])Alb = lerp", code)
    assert code.count("{") == code.count("}") and code.count("(") == code.count(")")


def test_texture_samples_per_slot():
    assert len(re.findall(r"Texture[23]DSampleLevel", CC.slot_body("A"))) == 16


def test_time_inputs_enter_the_lookups_they_should():
    body = CC.slot_body("A")
    for expr in ("0.61 + MackerelPhase", "0.23 + MammaPhase", "0.29 + LumpPhase", "0.83 + BoilTurret",
                 "0.11 + BoilBillow", "hk * 0.08 + RainFall", "saturate(npl - fi)", "Alt * 1.0e-5 - BottomKm",
                 "pkm - float3(AdvX, AdvY, 0.0)", "oD = outD * ExtinctionMax;", "float3(euv, EvoPhase)",
                 "float3(euv, 0.0)", "dbase * 2.71 + 0.37 + float3(Detail2OffU, Detail2OffV, Detail2OffW)"):
        assert expr in body, expr


def test_conservative_density_reads_no_evolution_fetch():
    """Cons is evaluated at every ray-march sample (UpdateMaterialCloudParam, VolumetricCloudMaterialPixelCommon.ush 65-67),
    so it must not depend on the evolution term's two shape fetches: it uses the evolution-free upper bound covC / topHC /
    rampTC (Task 8 GPU ruling)."""
    body = CC.slot_body("A")
    cons = [line.strip() for line in body.splitlines() if line.strip().startswith("oCons")]
    assert cons == ["oCons = max(saturate(rampTC * rampB * covC * 1.5), consX > 0.0 ? 1.0 : 0.0);"]
    evo = body.index("float ev =")
    assert body.index("float covC = saturate(cov * (1.0 + 2.0 * EvoAmt));") < evo
    after = body[evo:]
    assert not re.search(r"\bcovC\s*\*?=[^;]*\bcov\b", after)      # covC never takes the evolved cov
    assert not re.search(r"\btopHC\s*=[^;]*\btopH\b", after)
    assert not re.search(r"\brampTC\s*=[^;]*\brampT\b", after)


def test_conservative_chain_follows_every_coverage_step():
    body = CC.slot_body("A")
    for expr in ("covC *= rk;", "covC = lerp(covC, cm * saturate(covC * 2.0), MackerelAmt);", "covC = max(covC, cell);",
                 "topHC = lerp(topHC, ctop, cell);",
                 "float topHC = clamp(typeH * lerp(0.45, 1.0, saturate(covC * 1.3)), 0.05, 1.0);"):
        assert expr in body, expr
