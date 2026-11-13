# Run inside qrenderdoc:  CS_RDC=<capture> CS_OUT=<dir> CS_FROM=<first eid of the frame to analyse>
#                         qrenderdoc.exe --python Tools/cs_sky/rdc_export.py
# For every target pass (marker name, first match at or after CS_FROM) this script finds the leaf dispatch / draw
# actions inside the marker, sets the replay to each of them and records the pipeline's written resources
# (compute UAVs, render targets) and read resources (SRVs). It then dumps the raw texel data of the written textures
# (and of a few named inputs) to <CS_OUT>/tex/<tag>.bin with a JSON sidecar, so the images can be decoded offline.
# Writes <CS_OUT>/passes.json (per pass: eid range, leaf actions, shader entry, resources, GPU time) and timings.
import json
import os
import re
import time
import traceback

import renderdoc as rd

OUT = os.environ.get("CS_OUT", ".")
FROM = int(os.environ.get("CS_FROM", "0"))
ONLY = [t for t in os.environ.get("CS_ONLY", "").split(",") if t]   # optional: export only these tags
TEX_DIR = os.path.join(OUT, "tex")
os.makedirs(TEX_DIR, exist_ok=True)
log = open(os.path.join(OUT, "export_log.txt"), "w", encoding="utf-8")

# tag, marker name (exact, or prefix when it ends with '*'), occurrence index after FROM, what to dump
TARGETS = [
    ("cloud_skyao", "CloudSkyAO", 0, "writes"),
    ("cloud_shadow", "CloudShadow", 0, "writes"),
    ("atmo_transmittance", "TransmittanceLut", 0, "writes"),
    ("atmo_multiscattering", "MultiScatteringLut", 0, "writes"),
    ("atmo_distantskylight", "DistantSkyLightLut", 0, "writes"),
    ("atmo_rt_skyview", "RealTimeCaptureSkyViewLut", 0, "writes"),
    ("atmo_rt_camera360", "RealTimeCaptureCamera360VolumeLut", 0, "writes"),
    ("atmo_skyview", "SkyViewLut", 0, "writes"),
    ("atmo_cameravolume", "CameraVolumeLut", 0, "writes"),
    ("cap_cloud_face0", "Capture Volumetric Cloud Face=0", 0, "writes"),
    ("cap_face0", "Capture Face=0", 0, "writes"),
    ("cap_face5", "ApplyLowerHemisphereColor", 5, "writes"),
    ("cap_convolve", "Convolve", 0, "writes"),
    ("cap_irradiance", "ComputeSkyEnvMapDiffuseIrradianceCS", 0, "writes"),
    ("fog_init", "InitializeVolumeAttributes", 0, "writes"),
    ("fog_scatter", "LightScattering *", 0, "writes"),
    ("fog_integrate", "FinalIntegration", 0, "writes"),
    ("cloud_view", "CloudView (CS) <view>", 0, "writes"),       # <view> / <output>: sizes read from the capture
    ("cloud_hqap", "HighQualityAerialPerspectiveOnCloud", 0, "writes"),
    ("cloud_fog", "ExponentialHeightFog on Clouds", 0, "writes"),
    ("shafts", "LightShafts (Occlusion)", 0, "writes"),
    ("sky_draw", "SkyAtmosphere", 0, "writes"),
    ("fog_draw", "ExponentialHeightFog", 0, "writes"),
    ("cloud_compose", "VolumetricComposeCloudOverScene", 0, "writes"),
    ("sun_light", "RenderLight Light::StandardDeferred(Single): DirectionalLight", 0, "writes"),
    ("tsr", "TemporalSuperResolution(sg.AntiAliasingQuality=3)*", 0, "writes"),
    ("tonemap", "Tonemap <output>*", 0, "writes"),
]
# The cloud shadow map's spatial filter (CloudDataSpatialFilter after CloudShadow) only runs while
# r.VolumetricCloud.ShadowMap.SpatialFiltering > 0; the look of cs_clear_sky.py turns it off.
MAX_BYTES = 600 * 1024 * 1024


def say(*a):
    log.write(" ".join(str(x) for x in a) + "\n")
    log.flush()


def rid(r):
    return int(r)


def match(name, pattern):
    if pattern.endswith("*"):
        return name.startswith(pattern[:-1])
    return name == pattern


def flatten(root):
    out = []

    def walk(a, parent):
        out.append((a, parent))
        for c in a.children:
            walk(c, a)
    for a in root:
        walk(a, None)
    return out


def leaves(a):
    res = []

    def walk(x):
        if not x.children:
            if x.flags & (rd.ActionFlags.Dispatch | rd.ActionFlags.Drawcall | rd.ActionFlags.Clear |
                          rd.ActionFlags.Copy | rd.ActionFlags.Resolve | rd.ActionFlags.MeshDispatch):
                res.append(x)
        for c in x.children:
            walk(c)
    walk(a)
    return res


def descriptor_resource(d):
    for attr in ("descriptor", "resource"):
        if hasattr(d, attr):
            v = getattr(d, attr)
            if attr == "descriptor":
                return descriptor_resource(v)
            return v
    return None


def pipeline_resources(ctrl, action):
    """(written, read) resource ids at this action."""
    pipe = ctrl.GetPipelineState()
    written, read = [], []
    is_compute = bool(action.flags & rd.ActionFlags.Dispatch)
    stages = [rd.ShaderStage.Compute] if is_compute else [rd.ShaderStage.Vertex, rd.ShaderStage.Pixel]
    for st in stages:
        try:
            for d in pipe.GetReadWriteResources(st):
                r = descriptor_resource(d)
                if r is not None and rid(r) != 0:
                    written.append(rid(r))
        except Exception as e:
            say("rw err", e)
        try:
            for d in pipe.GetReadOnlyResources(st):
                r = descriptor_resource(d)
                if r is not None and rid(r) != 0:
                    read.append(rid(r))
        except Exception as e:
            say("ro err", e)
    if not is_compute:
        try:
            for d in pipe.GetOutputTargets():
                r = descriptor_resource(d)
                if r is not None and rid(r) != 0:
                    written.append(rid(r))
        except Exception as e:
            say("ot err", e)
    entry = None
    try:
        refl = pipe.GetShaderReflection(stages[-1])
        if refl is not None:
            entry = refl.entryPoint
    except Exception:
        pass
    return list(dict.fromkeys(written)), list(dict.fromkeys(read)), entry


def dump_texture(ctrl, tex, tag, eid):
    t = tex
    bpp_guess = t.format.ElementSize() if hasattr(t.format, "ElementSize") else 0
    meta = {"tag": tag, "eid": eid, "id": rid(t.resourceId), "w": t.width, "h": t.height, "d": t.depth,
            "arr": t.arraysize, "mips": t.mips, "fmt": t.format.Name(), "type": str(t.type),
            "compByteWidth": t.format.compByteWidth, "compCount": t.format.compCount,
            "compType": str(t.format.compType), "fmtType": str(t.format.type), "files": []}
    slices = range(t.arraysize) if t.arraysize > 1 else [0]
    for s in slices:
        sub = rd.Subresource(0, s, 0)
        data = ctrl.GetTextureData(t.resourceId, sub)
        if len(data) > MAX_BYTES:
            say("skip big", tag, len(data))
            continue
        fn = "%s_s%d.bin" % (tag, s)
        with open(os.path.join(TEX_DIR, fn), "wb") as f:
            f.write(bytes(data))
        meta["files"].append({"slice": s, "file": fn, "bytes": len(data)})
    with open(os.path.join(TEX_DIR, tag + ".json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    return meta


def main():
    t0 = time.time()
    cap = rd.OpenCaptureFile()
    cap.OpenFile(os.environ["CS_RDC"], "", None)
    status, ctrl = cap.OpenCapture(rd.ReplayOptions(), None)
    say("open", status, "%.1fs" % (time.time() - t0))
    sd = ctrl.GetStructuredFile()
    names = {rid(r.resourceId): r.name for r in ctrl.GetResources()}
    texs = {rid(t.resourceId): t for t in ctrl.GetTextures()}
    flat = flatten(ctrl.GetRootActions())
    say("flat", len(flat))

    # sizes of the analysed render: the main view's CloudView (internal view rect) and Tonemap (output) markers are the
    # largest of their kind before the first Slate pass (the sky-light capture traces 128x128 cube faces first)
    first_end = min([a.eventId for a, p in flat if a.eventId > FROM and
                     a.GetName(sd).startswith("RenderGraphExecute - Slate")] or [1 << 40])

    def biggest(prefix):
        best = None
        for a, p in flat:
            if FROM <= a.eventId < first_end:
                mm = re.match(re.escape(prefix) + r"(\d+)x(\d+)", a.GetName(sd))
                if mm and (best is None or int(mm.group(1)) * int(mm.group(2)) > best[0] * best[1]):
                    best = (int(mm.group(1)), int(mm.group(2)))
        return best
    view, output = biggest("CloudView (CS) "), biggest("Tonemap ")
    say("view", view, "output", output, "first_end", first_end)
    sizes = {"<view>": "%dx%d" % view, "<output>": "%dx%d" % output}

    durations = {}
    passes = []
    for tag, pattern, occ, what in TARGETS:
        if ONLY and tag not in ONLY:
            continue
        for k, v in sizes.items():
            pattern = pattern.replace(k, v)
        try:
            hits = [a for a, p in flat if a.eventId >= FROM and match(a.GetName(sd), pattern)]
            if len(hits) <= occ:
                say("no hit", tag, pattern)
                passes.append({"tag": tag, "marker": pattern, "missing": True})
                continue
            m = hits[occ]
            lv = leaves(m) or [m]
            info = {"tag": tag, "marker": m.GetName(sd), "eid": m.eventId,
                    "eid_end": lv[-1].eventId, "leaves": []}
            total_us = 0.0
            written_all = []
            for leaf in (lv[:11] + lv[-1:] if len(lv) > 12 else lv):   # keep the pass's last draw
                ctrl.SetFrameEvent(leaf.eventId, True)
                w, r, entry = pipeline_resources(ctrl, leaf)
                us = durations.get(leaf.eventId)
                if us:
                    total_us += us
                li = {"eid": leaf.eventId, "name": leaf.GetName(sd), "entry": entry,
                      "dispatch": list(leaf.dispatchDimension) if leaf.flags & rd.ActionFlags.Dispatch else None,
                      "written": [{"id": x, "name": names.get(x, ""),
                                   "tex": [texs[x].width, texs[x].height, texs[x].depth, texs[x].arraysize,
                                           texs[x].format.Name()] if x in texs else None} for x in w],
                      "read": [{"id": x, "name": names.get(x, "")} for x in r][:40], "us": us}
                info["leaves"].append(li)
                for x in w:
                    if x in texs and x not in [y[0] for y in written_all]:
                        written_all.append((x, leaf.eventId))
            info["us_total"] = round(total_us, 2) if total_us else None
            # dump the textures each written resource holds after the last leaf that wrote it
            dumped = []
            for x, _ in written_all[:6]:
                last = max(l["eid"] for l in info["leaves"] if any(wr["id"] == x for wr in l["written"]))
                ctrl.SetFrameEvent(last, True)
                t = texs[x]
                if t.width * t.height * max(1, t.depth) > 4096 * 4096 * 2 and t.depth > 1:
                    say("skip huge volume", tag, x)
                    continue
                sub_tag = "%s__%d" % (tag, x)
                meta = dump_texture(ctrl, t, sub_tag, last)
                meta["name"] = names.get(x, "")
                dumped.append({"tag": sub_tag, "name": names.get(x, ""), "eid": last,
                               "size": [t.width, t.height, t.depth, t.arraysize], "fmt": t.format.Name()})
            info["dumped"] = dumped
            # for full-screen passes also keep the state just BEFORE the pass (scene colour before/after). The scene
            # colour is the render target of the pass's last draw (the sun's pass first writes ShadowMaskTexture).
            last_rt = [w for w in info["leaves"][-1]["written"] if w["tex"]] if info["leaves"] else []
            if tag in ("sky_draw", "fog_draw", "cloud_compose", "sun_light") and last_rt:
                x = last_rt[0]["id"]
                ctrl.SetFrameEvent(m.eventId - 1, True)
                t = texs[x]
                meta = dump_texture(ctrl, t, "%s__%d_before" % (tag, x), m.eventId - 1)
                info["dumped_before"] = {"tag": "%s__%d_before" % (tag, x), "eid": m.eventId - 1,
                                         "after": "%s__%d" % (tag, x), "id": x}
            passes.append(info)
            say("ok", tag, m.eventId, len(lv), [d["tag"] for d in dumped], "%.1fs" % (time.time() - t0))
        except Exception:
            say("fail", tag, traceback.format_exc())
            passes.append({"tag": tag, "marker": pattern, "error": traceback.format_exc()[-600:]})
    try:
        res = ctrl.FetchCounters([rd.GPUCounter.EventGPUDuration])
        say("counter results", len(res))
        for r in res:
            durations[r.eventId] = r.value.d * 1e6
    except Exception:
        say("counter error", traceback.format_exc())
    for p in passes:
        tot = 0.0
        for l in p.get("leaves", []):
            l["us"] = durations.get(l["eid"])
            tot += l["us"] or 0.0
        p["us_total"] = round(tot, 2) if tot else None
    with open(os.path.join(OUT, "passes.json"), "w", encoding="utf-8") as f:
        json.dump({"from": FROM, "first_end": first_end, "view": list(view), "output": list(output),
                   "passes": passes, "durations_count": len(durations),
                   "durations": {str(k): v for k, v in durations.items() if k >= FROM}}, f, indent=1)
    ctrl.Shutdown()
    cap.Shutdown()
    say("done %.1fs" % (time.time() - t0))


try:
    main()
except Exception:
    say(traceback.format_exc())
log.close()
os._exit(0)
