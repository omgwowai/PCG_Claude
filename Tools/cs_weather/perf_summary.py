# perf_summary.py -- add one measurement to Saved/Reports/cs_cloud_motion/perf.json (spec §8, the report's cost table):
# the cloud passes of ProfileGPU runs (parsed by Tools/cs_sky/parse_profilegpu.py) and, with --director, the director's
# tick statistics from director.json. Compare only numbers taken in the same session and conditions.
#   C:\Python314\python.exe -P -E Tools/cs_weather/perf_summary.py --label 静态 --gpu <parsed.json> [--director]
#   C:\Python314\python.exe -P -E Tools/cs_weather/perf_summary.py --label 过渡中 --captures [--director]
#       --captures: the steady-state captures of Content/Python/cs_profile_gpu.py (gpu_captures.json), stored as their
#       median (Task 8 ruling: single frames vary +-4 ms)
import argparse
import json
import os
import statistics
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = os.path.join(ROOT, "Saved", "Reports", "cs_cloud_motion")
PERF = os.path.join(BASE, "perf.json")
STATUS = os.path.join(BASE, "director.json")
CAPTURES = os.path.join(BASE, "gpu_captures.json")
PARSER = os.path.join(ROOT, "Tools", "cs_sky", "parse_profilegpu.py")


def cloud_rows(rows):
    """The outermost ProfileGPU rows whose name mentions clouds (nested ones are inside their parent's inclusive time)."""
    out, depth = [], None
    for r in rows:
        if depth is not None and r["indent"] > depth:
            continue
        depth = None
        if "cloud" in r["name"].lower():
            out.append(r)
            depth = r["indent"]
    return out


def cloud_ms(rows):
    return round(sum(r["incl_ms"] for r in cloud_rows(rows)), 3)


def median_entry(caps):
    """caps: [{"frame_ms", "rows"}] -> the median cloud and frame time, and every capture's cloud time."""
    clouds = [cloud_ms(c["rows"]) for c in caps]
    return {"n": len(caps), "cloud_ms": round(statistics.median(clouds), 3),
            "frame_ms": round(statistics.median(c["frame_ms"] for c in caps), 3), "captures_cloud_ms": clouds}


def parse_capture(log, from_line, i):
    out = os.path.join(BASE, "_capture_%d.json" % i)
    subprocess.run([sys.executable, "-P", "-E", "-W", "ignore", PARSER, "--log", log, "--from-line", str(from_line),
                    "--out", out], check=True, capture_output=True)
    return json.load(open(out, encoding="utf-8"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--gpu")
    ap.add_argument("--captures", action="store_true")
    ap.add_argument("--director", action="store_true")
    a = ap.parse_args()
    if a.captures:
        st = json.load(open(CAPTURES, encoding="utf-8"))
        if st.get("state") != "done":
            print("captures not done:", st.get("state"))
            return 1
        entry = median_entry([parse_capture(st["log"], c["from_line"], i) for i, c in enumerate(st["caps"])])
    else:
        gpu = json.load(open(a.gpu, encoding="utf-8"))
        entry = {"n": 1, "cloud_ms": cloud_ms(gpu["rows"]), "frame_ms": gpu.get("frame_ms"),
                 "rows": [{"name": r["name"], "incl_ms": r["incl_ms"]} for r in cloud_rows(gpu["rows"])]}
    entry["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if a.director:
        entry["tick_ms"] = json.load(open(STATUS, encoding="utf-8")).get("tick_ms")
    perf = json.load(open(PERF, encoding="utf-8")) if os.path.exists(PERF) else {}
    perf[a.label] = entry
    os.makedirs(BASE, exist_ok=True)
    json.dump(perf, open(PERF, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(a.label, {k: entry[k] for k in ("n", "frame_ms", "cloud_ms")}, entry.get("tick_ms"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
