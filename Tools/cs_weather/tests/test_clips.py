import pytest

import cs_cloud_motion as M
import cs_weather_presets as P


def test_clip_list_has_ten_motion_and_five_transition_clips():
    clips = M.clip_list(P)
    kinds = [c["kind"] for c in clips]
    assert kinds.count("preset") == 10 and kinds.count("transition") == 5
    assert len({c["clip"] for c in clips}) == 15


def test_motion_clip_timing():
    c = next(c for c in M.clip_list(P) if c.get("preset") == "art_towers")
    fr = M.clip_frames(c)
    assert c["clip"] == "motion_towers" and c["cams"] == ["CS_ART_Towers"]
    assert fr["n"] == 300 and fr["dt"] == pytest.approx(120.0 / 30.0) and fr["t_start"] is None


def test_transition_clip_timing():
    c = next(c for c in M.clip_list(P) if c["kind"] == "transition")
    fr = M.clip_frames(c)
    assert fr["n"] == 480 and fr["hold_frames"] == 30 and fr["dur"] == 1800.0
    assert fr["t_start"] == pytest.approx(30 * fr["dt"])
    assert fr["t_start"] + fr["dur"] == pytest.approx(450 * fr["dt"])


def test_stills_names_match_the_weather_shots():
    s = next(s for s in M.stills_list(P) if s["preset"] == "art_storm")
    assert s["names"] == ["wx_art_storm_storm_mid0", "wx_art_storm_storm_mid1200"]
    plan = M.clip_frames(s)
    assert plan["times"] == [0.0, 1200.0] and plan["n"] == 2
    assert len(M.stills_list(P)) == 10


def _turn(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def test_camera_at_endpoints_and_target_cameras():
    a, b = P.CAMERAS["CS_ART_Wide"], P.CAMERAS["CS_ART_Sea"]          # a rot camera -> a target camera
    p0, p1 = M.camera_at(a, b, 0.0), M.camera_at(a, b, 1.0)
    assert p0["loc"] == pytest.approx(a["loc"]) and p1["loc"] == pytest.approx(b["loc"])
    assert p0["rot"][:2] == pytest.approx(a["rot"][:2])
    pose_b = M.camera_pose(b)
    assert p1["rot"][0] == pytest.approx(pose_b["rot"][0])
    assert _turn(p1["rot"][1], pose_b["rot"][1]) < 1e-9
    assert p1["fov"] == pytest.approx(b["fov"])
    c = M.camera_at(P.CAMERAS["CS_ART_Towers"], P.CAMERAS["CS_ART_Storm"], 0.7)   # aspect 1.6 -> 2.0
    assert c["aspect"] == 1.6 and c["res"] == [1920, 1200]


def test_camera_pose_of_a_target_camera_looks_at_the_target():
    pose = M.camera_pose(P.CAMERAS["CS_ART_Sea"])                     # NE corner, looking SSW down at the tower
    assert pose["rot"][0] < 0.0
    assert 180.0 < pose["rot"][1] % 360.0 < 270.0


WATER_SWITCH_Z = (-500.0, -400.0)     # camera z band in which the demo's water turns from dull to reflective (Task 11)


def test_transition_cameras_do_not_cross_the_water_switch():
    for c in M.clip_list(P):
        if c["kind"] != "transition":
            continue
        a, b = (P.CAMERAS[x] for x in c["cams"])
        zs = [M.camera_at(a, b, i / 100.0)["loc"][2] for i in range(101)]
        below = all(z <= WATER_SWITCH_Z[0] for z in zs)
        above = all(z >= WATER_SWITCH_Z[1] for z in zs)
        assert below or above, (c["clip"], round(min(zs)), round(max(zs)))


def test_moving_cameras_cross_the_city_above_the_roofs():
    """lenticular -> shelf flew a straight line from 250 m to 21 m through downtown (Task 11: frame 287 is a wall).
    Wherever the camera is away from both end columns it must be at least CLEAR_Z high (the tallest roof is 438 m)."""
    for c in M.clip_list(P):
        if c["kind"] != "transition":
            continue
        a, b = (P.CAMERAS[x] for x in c["cams"])
        pa, pb = M.camera_pose(a), M.camera_pose(b)
        for i in range(201):
            loc = M.camera_at(a, b, i / 200.0)["loc"]
            da = ((loc[0] - pa["loc"][0]) ** 2 + (loc[1] - pa["loc"][1]) ** 2) ** 0.5
            db = ((loc[0] - pb["loc"][0]) ** 2 + (loc[1] - pb["loc"][1]) ** 2) ** 0.5
            if da > 10000.0 and db > 10000.0:            # cm: 100 m from both end columns
                assert loc[2] >= M.CLEAR_Z - 1e-6, (c["clip"], i, [round(x) for x in loc])
