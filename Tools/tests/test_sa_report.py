import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import build_pcg_stage_report as R


def test_two_shot_manifest_renders_two_figures_with_kind_captions(tmp_path):
    png = _tiny_png(tmp_path)
    man = {"title": "t", "subtitle": "s", "level": "/Game/X",
           "stages": [{"n": 1, "graph": "PCG_A", "label": "地形",
                       "shots": [{"kind": "debug", "path": png},
                                 {"kind": "geometry", "path": png}],
                       "metrics": {"instances": 0, "debug_instances": 9,
                                   "status": "empty"},
                       "notes": "n"}],
           "footer": "f"}
    doc = R.build_html(man, max_edge=64, quality=50)
    assert doc.count("<figure") == 2
    assert "debug" in doc and "geometry" in doc
    assert doc.count("data:image/jpeg;base64,") == 2


def test_legacy_single_shot_manifest_still_renders_one_figure(tmp_path):
    png = _tiny_png(tmp_path)
    man = {"title": "t", "subtitle": "s", "level": "/Game/X",
           "stages": [{"n": 1, "graph": "PCG_A", "label": "地形",
                       "shot": png,
                       "metrics": {"instances": 1, "debug_instances": 2,
                                   "status": "ok"},
                       "notes": "n"}],
           "footer": "f"}
    doc = R.build_html(man, max_edge=64, quality=50)
    assert doc.count("<figure") == 1


def test_a_missing_shot_renders_the_placeholder_not_a_broken_img(tmp_path):
    man = {"title": "t", "subtitle": "s", "level": "/Game/X",
           "stages": [{"n": 1, "graph": "PCG_A", "label": "地形",
                       "shots": [{"kind": "debug", "img_missing": "/nope.png"},
                                 {"kind": "geometry", "img_missing": "/nope2.png"}],
                       "metrics": {"instances": 0, "debug_instances": 0,
                                   "status": "missing"},
                       "notes": ""}],
           "footer": "f"}
    doc = R.build_html(man, max_edge=64, quality=50)
    assert doc.count("<figure") == 0
    # The brief counted the bare substring "noimg", but PAGE's own stylesheet has a
    # `.noimg{...}` rule, so that substring always occurs once more than the number
    # of placeholders. Counting the placeholder elements states the intent.
    assert doc.count('<div class="noimg">') == 2


def _tiny_png(tmp_path):
    from PIL import Image
    p = tmp_path / "shot.png"
    Image.new("RGB", (120, 80), (10, 20, 30)).save(p)
    return str(p)
