import perf_summary as PS


def _rows(shadow, main, faces):
    rows = [{"name": "Scene", "indent": 4, "excl_ms": 0.1, "incl_ms": 40.0},
            {"name": "VolumetricCloudShadow", "indent": 6, "excl_ms": 0.0, "incl_ms": shadow},
            {"name": "CloudShadow", "indent": 8, "excl_ms": 0.0, "incl_ms": shadow - 0.4},
            {"name": "VolumetricCloud", "indent": 6, "excl_ms": 0.0, "incl_ms": main},
            {"name": "CaptureConvolveSkyEnvMap", "indent": 6, "excl_ms": 0.0, "incl_ms": sum(faces) + 0.2}]
    rows += [{"name": "Capture Volumetric Cloud Face=%d" % i, "indent": 8, "excl_ms": 0.0, "incl_ms": f}
             for i, f in enumerate(faces)]
    return rows


def test_cloud_ms_counts_outermost_rows_once():
    assert PS.cloud_ms(_rows(14.0, 4.0, [0.5, 0.3])) == 14.0 + 4.0 + 0.5 + 0.3


def test_median_of_captures():
    caps = [{"frame_ms": f, "rows": _rows(s, 4.0, [1.0])} for f, s in ((35.0, 14.0), (36.0, 20.0), (34.0, 15.0))]
    m = PS.median_entry(caps)
    assert m["cloud_ms"] == 20.0 and m["frame_ms"] == 35.0 and m["n"] == 3
    assert m["captures_cloud_ms"] == [19.0, 25.0, 20.0]
