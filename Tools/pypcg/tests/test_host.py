import sys

from pypcg import host


def test_fresh_drops_cached_pypcg_modules():
    saved = {k: v for k, v in sys.modules.items() if k == "pypcg" or k.startswith("pypcg.")}
    sys.modules["pypcg.stages.s99_cached"] = object()
    try:
        host._fresh()
        assert not [k for k in sys.modules if k == "pypcg" or k.startswith("pypcg.")]
    finally:
        sys.modules.update(saved)
        sys.modules.pop("pypcg.stages.s99_cached", None)


def test_inline_script_text_matches_what_the_dsl_writes():
    assert host.inline_script("s06_districts") == 'from pypcg import host\nhost.run("s06_districts", globals())\n'
