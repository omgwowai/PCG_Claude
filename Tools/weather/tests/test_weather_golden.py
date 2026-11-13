import json
import os

import gen_golden as G


def _read(name):
    with open(os.path.join(G.GOLDEN_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


def test_golden_files_are_up_to_date():
    for name, build in (("calendar_cases.json", G.calendar_cases), ("astronomy_cases.json", G.astronomy_cases),
                        ("sky_cases.json", G.sky_cases)):
        assert _read(name) == json.loads(json.dumps(build())), \
            "stale %s: run C:/Python314/python.exe Tools/weather/gen_golden.py" % name


def test_golden_covers_the_edges():
    cal = _read("calendar_cases.json")
    days = [c["game_seconds"] / 86400.0 for c in cal["evaluate"]]
    assert max(days) >= 2000.0 and any(6.0 <= d < 7.0 for d in days)
    assert any(c["day"] == 99 and c["hour"] == 25.0 for c in cal["seconds_for"])
    assert len(_read("astronomy_cases.json")["sun"]) == 160 and len(_read("sky_cases.json")["rig"]) == 40
