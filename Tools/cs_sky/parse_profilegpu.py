"""Parse the Graphics-pipeline table that `ProfileGPU` prints to the editor log into JSON.

Usage: C:\Python314\python.exe Tools/cs_sky/parse_profilegpu.py --log Saved/Logs/PCG_Claude.log --from-line N
           --out Saved/Reports/cs_weather/profilegpu.json
Each row: name, indent (tree depth in characters), exclusive / inclusive GPU time in ms.
"""
import argparse
import io
import json
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--from-line", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    lines = io.open(a.log, encoding="utf-8", errors="replace").read().splitlines()[a.from_line:]
    start = next(i for i, l in enumerate(lines) if "GPU Profile for Frame" in l and "Graphics pipeline" in l)
    frame_ms = None
    rows = []
    for l in lines[start:]:
        if "LogRHI: Display:" not in l:
            continue
        body = l.split("LogRHI: Display:", 1)[1]
        m = re.search(r"Frame Time\s*:\s*([\d.]+)ms", body)
        if m:
            frame_ms = float(m.group(1))
        if "┗" in body and rows:
            break
        parts = body.split("┃")
        if len(parts) < 4:
            continue
        e = re.search(r"([\d.]+) ms", parts[1])
        i = re.search(r"([\d.]+) ms", parts[2])
        if not (e and i):
            continue
        raw = parts[3].rstrip()
        name = raw.strip(" │├└─┬┌╰╭┊")
        rows.append({"name": name, "indent": len(raw) - len(raw.lstrip(" │├└─┬┌╰╭┊")),
                     "excl_ms": float(e.group(1)), "incl_ms": float(i.group(1))})
    json.dump({"frame_ms": frame_ms, "rows": rows}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("rows", len(rows), "frame", frame_ms)


if __name__ == "__main__":
    main()
