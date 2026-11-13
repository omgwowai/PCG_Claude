# Run inside qrenderdoc:  CS_RDC=<capture> CS_OUT=<dir> qrenderdoc.exe --python Tools/cs_sky/rdc_tree.py
# Replays a capture and writes <CS_OUT>/tree.json:
#   actions   flat list of every action / marker: eid, name, depth, parent path, flags, children count,
#             outputs / depth target, dispatch size, GPU duration (us) when the counter is available
#   textures  every texture: id, name, size, depth, mips, array size, format, type
#   buffers   every buffer: id, name, length
import json
import os
import time
import traceback

import renderdoc as rd

OUT = os.environ.get("CS_OUT", ".")
os.makedirs(OUT, exist_ok=True)
log = open(os.path.join(OUT, "tree_log.txt"), "w", encoding="utf-8")


def say(*a):
    log.write(" ".join(str(x) for x in a) + "\n")
    log.flush()


def rid(r):
    return int(r)


def main():
    t0 = time.time()
    cap = rd.OpenCaptureFile()
    st = cap.OpenFile(os.environ["CS_RDC"], "", None)
    say("open file", st)
    if not cap.LocalReplaySupport():
        say("no local replay support")
    status, ctrl = cap.OpenCapture(rd.ReplayOptions(), None)
    say("open capture", status, "%.1fs" % (time.time() - t0))
    if status != rd.ResultCode.Succeeded:
        return {"error": "OpenCapture failed: %s" % status}
    sd = ctrl.GetStructuredFile()
    names = {}
    for r in ctrl.GetResources():
        names[rid(r.resourceId)] = r.name
    textures = []
    for t in ctrl.GetTextures():
        textures.append({"id": rid(t.resourceId), "name": names.get(rid(t.resourceId), ""), "w": t.width, "h": t.height,
                         "d": t.depth, "mips": t.mips, "arr": t.arraysize, "fmt": t.format.Name(),
                         "type": str(t.type), "dim": t.dimension, "ms": t.msSamp})
    buffers = [{"id": rid(b.resourceId), "name": names.get(rid(b.resourceId), ""), "len": b.length}
               for b in ctrl.GetBuffers()]
    say("resources", len(textures), "textures", len(buffers), "buffers")

    durations = {}
    try:
        counters = ctrl.EnumerateCounters()
        if rd.GPUCounter.EventGPUDuration in counters:
            t1 = time.time()
            for r in ctrl.FetchCounters([rd.GPUCounter.EventGPUDuration]):
                durations[r.eventId] = r.value.d * 1e6
            say("durations", len(durations), "%.1fs" % (time.time() - t1))
    except Exception:
        say("counter error", traceback.format_exc())

    actions = []

    def walk(a, depth, path):
        name = a.GetName(sd)
        flags = str(a.flags)
        entry = {"eid": a.eventId, "aid": a.actionId, "name": name, "depth": depth, "path": path,
                 "flags": flags, "kids": len(a.children)}
        outs = [rid(o) for o in a.outputs if rid(o) != 0]
        if outs:
            entry["outputs"] = outs
        if rid(a.depthOut) != 0:
            entry["depth_out"] = rid(a.depthOut)
        if a.flags & rd.ActionFlags.Dispatch:
            entry["dispatch"] = [a.dispatchDimension[0], a.dispatchDimension[1], a.dispatchDimension[2]]
        if a.flags & (rd.ActionFlags.Drawcall):
            entry["indices"] = a.numIndices
            entry["instances"] = a.numInstances
        if a.eventId in durations:
            entry["us"] = round(durations[a.eventId], 3)
        actions.append(entry)
        sub = path + [name] if a.children else path
        for c in a.children:
            walk(c, depth + 1, sub)

    for a in ctrl.GetRootActions():
        walk(a, 0, [])
    say("actions", len(actions), "%.1fs total" % (time.time() - t0))
    res = {"capture": os.environ["CS_RDC"], "api": str(ctrl.GetAPIProperties().pipelineType),
           "actions": actions, "textures": textures, "buffers": buffers}
    ctrl.Shutdown()
    cap.Shutdown()
    return res


try:
    result = main()
except Exception:
    result = {"error": traceback.format_exc()}
    say(result["error"])
with open(os.path.join(OUT, "tree.json"), "w", encoding="utf-8") as f:
    json.dump(result, f)
log.close()
os._exit(0)
