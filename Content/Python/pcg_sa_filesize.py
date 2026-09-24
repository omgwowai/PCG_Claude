# Content/Python/pcg_sa_filesize.py — which external actor file is which actor, and how big.
#
# WHY: shedding 2,449,359 debug cubes did not shrink the saved level at all — 507 MB against
# 506 MB — so the cubes were not the bulk of the bytes. The single largest file is 288.4 MB, well
# over GitHub's 100 MB per-file limit, so the level cannot be committed as-is and I need to know
# exactly which actor owns those bytes before choosing between committing it and gitignoring it.
#
# HOW: an external-actor level stores each actor in its own package, and
# `Actor.get_path_name()` exposes that package path, so the file on disk can be stat'd per actor.
# Reporting instance counts alongside the file size also shows whether a file's bulk is instanced
# geometry or something else (mesh terrain, data assets).
#
# Read-only. No UObject is stored at module level.

import gc
import json
import os

TARGET = "/Game/PCGArea/L_SmallArea18"


def main():
    import unreal

    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    out = {}

    cur = str(les.get_current_level())
    if TARGET.split("/")[-1] not in cur:
        return {"abort": "not on %s (current: %s)" % (TARGET, cur)}

    proj = unreal.Paths.project_dir()
    rows = []
    for a in eas.get_all_level_actors():
        cn = a.get_class().get_name()
        try:
            path = str(a.get_path_name())
        except Exception:
            path = ""
        # external actor packages look like /Game/<Lvl>/__ExternalActors__/<Lvl>/<X>/<YY>/<GUID>
        file_bytes = None
        if "__ExternalActors__" in path:
            rel = path.split("/Game/", 1)[-1] if "/Game/" in path else path
            rel = rel.split(":", 1)[0]            # drop the :PersistentLevel.<Actor> suffix
            cand = os.path.join(proj, "Content", *rel.split("/")) + ".uasset"
            if os.path.exists(cand):
                file_bytes = os.path.getsize(cand)
        n_inst = 0
        n_comp = 0
        for c in a.get_components_by_class(unreal.PrimitiveComponent):
            if c.get_class().get_name() == "BrushComponent":
                continue
            try:
                n = c.get_instance_count()
            except Exception:
                continue
            if n:
                n_inst += n
                n_comp += 1
        rows.append({"label": str(a.get_actor_label()), "class": cn,
                     "mb": round(file_bytes / 1048576.0, 1) if file_bytes else None,
                     "instances": n_inst, "components": n_comp,
                     "external": "__ExternalActors__" in path})
    rows.sort(key=lambda r: -(r["mb"] or 0))
    out["actors"] = rows[:24]
    out["over_90mb"] = [r for r in rows if (r["mb"] or 0) > 90]
    out["over_100mb"] = [r for r in rows if (r["mb"] or 0) > 100]
    out["total_actors"] = len(rows)
    out["external_count"] = sum(1 for r in rows if r["external"])
    out["total_mb"] = round(sum(r["mb"] or 0 for r in rows), 1)
    return out


if __name__ == "__main__":
    try:
        E = {"ok": True, "data": main()}
    except Exception as exc:
        E = {"ok": False, "error": "%s: %s" % (type(exc).__name__, str(exc)[:300])}
    if E.get("ok"):
        d = E["data"]
        if d.get("abort"):
            line = "ABORT %s" % d["abort"]
        else:
            tops = ", ".join("%s %sMB inst=%s" % (r["label"], r["mb"], r["instances"])
                             for r in d["actors"][:6])
            line = ("actors=%s external=%s totalMB=%s | over_90MB=%s over_100MB=%s | top: %s"
                    % (d["total_actors"], d["external_count"], d["total_mb"],
                       len(d["over_90mb"]), len(d["over_100mb"]), tops))
    else:
        line = "ERROR " + E.get("error", "")
    print(line)
    mcp_result = {"ok": E.get("ok"), "line": line}
    del E
    gc.collect()
