# Run inside qrenderdoc:  qrenderdoc.exe --python Tools/cs_sky/rdc_markers.py
# Reads a capture's structured data WITHOUT replaying it (no GPU work) and writes the marker strings it finds.
# Paths come from the environment: CS_RDC (capture), CS_OUT (json output).
import json
import os
import traceback

import renderdoc as rd

out = os.environ.get("CS_OUT", "rdc_markers.json")
res = {}
try:
    cap = rd.OpenCaptureFile()
    status = cap.OpenFile(os.environ["CS_RDC"], "", None)
    res["open"] = str(status)
    sd = cap.GetStructuredData()
    names = {}
    markers = []
    for ch in sd.chunks:
        n = ch.name
        names[n] = names.get(n, 0) + 1
        if "BeginEvent" in n or "SetMarker" in n or "Marker" in n:
            txt = None
            for i in range(ch.NumChildren()):
                c = ch.GetChild(i)
                if c.name in ("MarkerText", "Marker", "Name", "pData"):
                    try:
                        txt = c.AsString()
                    except Exception:
                        txt = None
                    if txt:
                        break
            if txt and len(markers) < 200000:
                markers.append(txt)
    res["chunk_kinds"] = sorted(names.items(), key=lambda kv: -kv[1])[:60]
    res["marker_count"] = len(markers)
    keys = ("Sky", "Atmosphere", "Cloud", "Volumetric", "Fog", "LightShaft", "Capture", "Lut", "LUT",
            "Reconstruct", "Compose", "Shadow", "Tonemap", "PostProcess", "TSR", "Lumen")
    res["interesting"] = [m for m in markers if any(k in m for k in keys)][:600]
    cap.Shutdown()
except Exception:
    res["error"] = traceback.format_exc()
with open(out, "w", encoding="utf-8") as f:
    json.dump(res, f, indent=1)
os._exit(0)
