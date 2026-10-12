# tl_probe_export_t3d.py -- READ-ONLY. Export one asset to T3D text under
# Saved/graph_dumps/<name>.t3d with the generic object exporter, so private
# UPROPERTYs that Python cannot read (e.g. the inline pin default values of PCG
# metadata nodes) can be inspected. Returns the file path and size only.
# Args: {"asset": "<asset path>"}
import json
import os

args = mcp_args or {}


def main():
    path = args["asset"]
    obj = unreal.EditorAssetLibrary.load_asset(path)
    out = os.path.join(unreal.Paths.project_saved_dir(), "graph_dumps", path.rsplit("/", 1)[-1] + ".t3d")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    task = unreal.AssetExportTask()
    task.set_editor_property("object", obj)
    task.set_editor_property("filename", out)
    task.set_editor_property("automated", True)
    task.set_editor_property("prompt", False)
    task.set_editor_property("replace_identical", True)
    task.set_editor_property("exporter", None)
    ok = unreal.Exporter.run_asset_export_task(task)
    errs = [str(e) for e in task.get_editor_property("errors")] if hasattr(task, "errors") else []
    return {"ok": ok, "file": out, "exists": os.path.exists(out),
            "size": os.path.getsize(out) if os.path.exists(out) else 0, "errors": errs}


mcp_result = json.loads(json.dumps(main(), default=str))
