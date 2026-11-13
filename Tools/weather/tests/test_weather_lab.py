import weather_lab as L


def test_refuses_the_big_levels():
    for big in L.BIG_LEVELS:
        assert "abort" in L.refusal(big)
    assert L.refusal("/Game/Untitled") is None and L.refusal(L.LEVEL) is None
    assert "/Game/PyPCG/L_PyWorld" in L.BIG_LEVELS
