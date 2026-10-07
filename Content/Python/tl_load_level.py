# tl_load_level.py -- load a level by path (default: the CitySample PCG demo).
# Never saves anything. Run on its own call; generation and reads go in later calls.
import json

args = mcp_args or {}
LEVEL = args.get("level", "/CitySamplePCG/Levels/L_CitySamplePCG_Demo")
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

R = {"requested": LEVEL}
R["loaded"] = les.load_level(LEVEL)
w = unreal.EditorLevelLibrary.get_editor_world()
R["world"] = w.get_path_name() if w else None
mcp_result = json.loads(json.dumps(R, default=str))
