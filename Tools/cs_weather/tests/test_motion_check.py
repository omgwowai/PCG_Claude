import numpy as np
from PIL import Image

import motion_check as MC


def _frames(tmp_path, n=40, jump_at=25):
    paths = []
    for k in range(n):
        img = np.repeat(np.linspace(0.0, 1.0, 256)[None, :] * 200.0 + k * 0.5, 160, axis=0)   # a slow drift
        if k >= jump_at:
            img = img + 30.0
        p = tmp_path / ("f_%05d.png" % k)
        Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGB").save(p)
        paths.append(str(p))
    return paths


def test_a_jump_is_found(tmp_path):
    d = MC.diffs(_frames(tmp_path))
    assert len(d) == 40 and d[0] == 0.0
    assert MC.jumps(d, 1, len(d), 3.0) == [25]


def test_a_smooth_clip_has_no_jump(tmp_path):
    d = MC.diffs(_frames(tmp_path, jump_at=999))
    assert MC.jumps(d, 1, len(d), 3.0) == []


def test_the_range_limits_the_search(tmp_path):
    d = MC.diffs(_frames(tmp_path))
    assert MC.jumps(d, 1, 20, 3.0) == []


def test_sustained_motion_is_not_a_jump():
    """A bright, fast first part and a dark, slow second part (streets -> afterglow): the clip median is low, but frames
    whose change rises and falls with their neighbours are motion, not a jump (Task 11)."""
    d = [0.0] + [2.0] * 30 + [2.0 + 0.6 * i for i in range(10)] + [8.0 - 0.6 * i for i in range(10)] + [2.0] * 100 + [0.7] * 300
    assert MC.jumps(d, 1, len(d), 3.0) == []


def test_a_spike_during_fast_motion_is_a_jump():
    """The water pop of mackerel -> cloudsea (frame 53): 10.1 against neighbours of 4.5-4.8."""
    d = [0.0] + [2.6] * 200 + [4.5] * 20 + [10.1] + [4.8] * 20 + [2.6] * 200
    assert MC.jumps(d, 1, len(d), 3.0) == [221]


def _recorded(name):
    import json
    import os
    return json.load(open(os.path.join(os.path.dirname(__file__), "data", name), encoding="utf-8"))["d"]


def test_recorded_streets_motion_is_not_a_jump():
    """streets -> afterglow (Task 11): fast motion in the bright first part (frames 31-39, 55-62 exceed 3 x the clip
    median, which the dark dusk half pulls down) rises and falls with its neighbours: no jump."""
    assert MC.jumps(_recorded("streets_afterglow_d.json"), 30, 451, 3.0) == []


def test_recorded_finish_step_is_a_jump():
    """mackerel -> cloudsea (Task 11): the cloud component snapped from the union back to the cloud sea's own at the
    last transition frame (450): 7.8 against 0.5."""
    assert MC.jumps(_recorded("mackerel_cloudsea_d.json"), 30, 451, 3.0) == [450]


def test_recorded_water_pop_is_a_jump():
    """The water pop of the first mackerel -> cloudsea recording (frames 40-69, the pop at 53: 10.1 against 4.5-4.8)."""
    pop = [4.26, 4.29, 4.29, 4.27, 4.33, 4.33, 4.35, 4.42, 4.46, 4.48, 4.48, 4.46, 4.48, 10.14, 7.07, 6.38, 6.08, 5.76,
           5.6, 5.46, 5.39, 5.25, 5.16, 5.11, 5.06, 5.05, 5.02, 5.06, 4.96, 4.91]
    d = [0.0] + [2.6] * 100 + pop + [2.6] * 100
    assert MC.jumps(d, 1, len(d), 3.0) == [100 + 13 + 1]
