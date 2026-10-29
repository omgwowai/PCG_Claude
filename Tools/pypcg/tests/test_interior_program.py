"""PyInterior rule tables: programs, room types, access, styles (spec 2026-10-28 §4.2, §4.3, §4.5, §4.9)."""
import pytest

from pypcg.interior import program as P


@pytest.mark.parametrize("area, name", [(20, "Studio"), (33.9, "Studio"), (34, "OneBed"), (57.9, "OneBed"), (58, "TwoBed"),
                                        (88, "ThreeBed"), (129.9, "ThreeBed"), (130, "FourBed"), (400, "FourBed")])
def test_band_edges(area, name):
    assert P.choose(area).name == name


def test_programs_upgrade_with_area():
    order = [p.name for p in P.PROGRAMS]
    last = -1
    for a in range(20, 300, 3):
        k = order.index(P.choose(a).name)
        assert k >= last
        last = k


def test_fallback_chain_shrinks_and_ends_in_studio():
    for prog in P.PROGRAMS:
        chain = list(P.fallbacks(prog))
        assert chain[0] == prog
        assert chain[-1].name == "Studio"
        sizes = [len(p.public) + len(p.private) for p in chain]
        assert all(b <= a for a, b in zip(sizes, sizes[1:]))
        assert len(set(chain)) == len(chain)
        # required rooms of a program survive until the program itself is downgraded
        for p in chain:
            if p.name == prog.name:
                kept = {s.type for s in p.public + p.private}
                assert {s.type for s in prog.public + prog.private if not s.optional} <= kept


def test_every_room_type_has_rules():
    used = {s.type for p in P.PROGRAMS for s in p.public + p.private} | {"Corridor"}
    assert used <= set(P.ROOMS)
    assert used <= set(P.ACCESS)
    for t in used:
        r = P.ROOMS[t]
        assert r.zone in ("public", "private", "service", "circulation")
        assert 0 < r.min_short <= r.min_long
        assert r.floor in P.FLOORS
        for parent in P.ACCESS[t]:
            assert parent in P.ROOMS
    for t in P.ENTRY:
        assert P.ACCESS[t] == ()


def test_every_style_has_every_palette():
    keys = set(P.STYLES["Scandi"])
    for name, s in P.STYLES.items():
        assert set(s) == keys, name
        for wall_key in ("living", "bedroom", "wet", "neutral"):
            assert s["walls"][wall_key], (name, wall_key)
            for c in s["walls"][wall_key]:
                assert c in P.COLORS
        for k in ("fabric", "accent"):
            for c in s[k]:
                assert c in P.COLORS
        for k in ("facade", "trim", "door", "wood", "wood_dark"):
            assert s[k] in P.COLORS
        for floor in P.FLOORS:
            assert s["floors"][floor] in P.FLOOR_MATERIALS


def test_targets_split_a_zone_by_weight():
    prog = P.choose(100)
    t = P.targets(prog.private, 5000 * 100.0)
    assert sum(t) == pytest.approx(5000 * 100.0)
    w = [s.weight for s in prog.private]
    assert t[0] / t[1] == pytest.approx(w[0] / w[1])
