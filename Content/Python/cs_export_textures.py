# Export a few 2D textures to Saved/Reports/cs_weather/tex/ so their channels can be inspected offline.
# args: {"assets": [...], "ext": "tga"}
import os
import unreal


def _main(args):
    out_dir = os.path.join(unreal.Paths.project_saved_dir(), "Reports", "cs_weather", "tex")
    os.makedirs(out_dir, exist_ok=True)
    res = []
    for path in args.get("assets", []):
        a = unreal.EditorAssetLibrary.load_asset(path)
        if a is None:
            res.append({"path": path, "error": "missing"})
            continue
        fn = os.path.join(out_dir, a.get_name() + "." + args.get("ext", "tga"))
        task = unreal.AssetExportTask()
        task.set_editor_property("object", a)
        task.set_editor_property("filename", fn)
        task.set_editor_property("automated", True)
        task.set_editor_property("prompt", False)
        task.set_editor_property("replace_identical", True)
        ok = unreal.Exporter.run_asset_export_task(task)
        res.append({"path": path, "ok": bool(ok), "file": os.path.abspath(fn),
                    "exists": os.path.exists(fn), "errors": [str(e) for e in task.get_editor_property("errors")]})
    return res


mcp_result = _main(globals().get("mcp_args") or {})
