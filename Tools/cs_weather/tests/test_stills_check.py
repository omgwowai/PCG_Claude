import numpy as np
from PIL import Image

import stills_check as SC


def _img(path, a):
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGB").save(path)


def test_block_metric_ignores_pixel_noise_and_sees_a_shift(tmp_path):
    rng = np.random.default_rng(1)
    base = np.repeat(np.linspace(40.0, 200.0, 512)[None, :], 256, axis=0)
    _img(tmp_path / "ref.png", base)
    _img(tmp_path / "noisy.png", base + rng.normal(0.0, 6.0, base.shape))       # render noise
    shifted = base.copy()
    shifted[:, 128:256] += 40.0                                                     # a cloud that moved / changed
    _img(tmp_path / "moved.png", shifted)
    quiet = SC.block_p999(str(tmp_path / "ref.png"), str(tmp_path / "noisy.png"))
    moved = SC.block_p999(str(tmp_path / "ref.png"), str(tmp_path / "moved.png"))
    assert quiet < 2.0 and moved > 30.0


def test_verdict_rules():
    assert SC.verdict(3.0, 25.0, 10.0) == (True, True)
    assert SC.verdict(12.0, 25.0, 10.0) == (False, True)       # age 0 drifted from the static look
    assert SC.verdict(3.0, 6.0, 10.0) == (True, False)         # age 1200 barely moved
