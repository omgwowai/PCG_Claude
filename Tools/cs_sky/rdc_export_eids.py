# Run inside qrenderdoc: CS_RDC=<capture> CS_OUT=<dir> CS_JOBS='[[tag, eid, resource_id_or_0], ...]'
# For each job: replay to eid, record the pipeline's read / written resources and shader entry, and dump the given
# texture (or every written texture when the id is 0) into <CS_OUT>/tex like rdc_export.py. Results: <CS_OUT>/eids.json
import json
import os
import traceback

import renderdoc as rd

OUT = os.environ["CS_OUT"]
TEX = os.path.join(OUT, "tex")
os.makedirs(TEX, exist_ok=True)
jobs = json.loads(os.environ["CS_JOBS"])
res = {"jobs": []}


def rid(r):
    return int(r)


def dump(ctrl, t, tag, eid):
    meta = {"tag": tag, "eid": eid, "id": rid(t.resourceId), "w": t.width, "h": t.height, "d": t.depth,
            "arr": t.arraysize, "mips": t.mips, "fmt": t.format.Name(), "type": str(t.type), "files": []}
    for s in (range(t.arraysize) if t.arraysize > 1 else [0]):
        data = ctrl.GetTextureData(t.resourceId, rd.Subresource(0, s, 0))
        fn = "%s_s%d.bin" % (tag, s)
        open(os.path.join(TEX, fn), "wb").write(bytes(data))
        meta["files"].append({"slice": s, "file": fn, "bytes": len(data)})
    json.dump(meta, open(os.path.join(TEX, tag + ".json"), "w"), indent=1)


try:
    cap = rd.OpenCaptureFile()
    cap.OpenFile(os.environ["CS_RDC"], "", None)
    st, ctrl = cap.OpenCapture(rd.ReplayOptions(), None)
    names = {rid(r.resourceId): r.name for r in ctrl.GetResources()}
    texs = {rid(t.resourceId): t for t in ctrl.GetTextures()}
    for tag, eid, want in jobs:
        ctrl.SetFrameEvent(eid, True)
        pipe = ctrl.GetPipelineState()
        reads, writes = [], []
        for stg in (rd.ShaderStage.Vertex, rd.ShaderStage.Pixel, rd.ShaderStage.Compute):
            try:
                reads += [rid(d.descriptor.resource) for d in pipe.GetReadOnlyResources(stg)]
                writes += [rid(d.descriptor.resource) for d in pipe.GetReadWriteResources(stg)]
            except Exception:
                pass
        try:
            writes += [rid(d.resource) for d in pipe.GetOutputTargets()]
        except Exception:
            pass
        entry = None
        for stg in (rd.ShaderStage.Pixel, rd.ShaderStage.Compute):
            try:
                r = pipe.GetShaderReflection(stg)
                if r is not None:
                    entry = r.entryPoint
            except Exception:
                pass
        job = {"tag": tag, "eid": eid, "entry": entry,
               "reads": sorted(set(names.get(x, str(x)) for x in reads if x)),
               "writes": sorted(set(names.get(x, str(x)) for x in writes if x)), "dumped": []}
        targets = [want] if want else [x for x in dict.fromkeys(writes) if x in texs]
        for x in targets:
            if x in texs:
                dump(ctrl, texs[x], "%s__%d" % (tag, x), eid)
                job["dumped"].append("%s__%d" % (tag, x))
        res["jobs"].append(job)
    ctrl.Shutdown()
    cap.Shutdown()
except Exception:
    res["error"] = traceback.format_exc()
json.dump(res, open(os.path.join(OUT, "eids.json"), "w"), indent=1)
os._exit(0)
