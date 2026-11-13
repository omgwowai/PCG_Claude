# cs_weather_shots.py -- queue several high-res screenshots (see cs_wx_lib.start_shot_queue).
# Args: {"shots": [{"name": "x", "camera": "CS_SkyCam", "res": [w, h]}, ...], "settle": 20}  or  {"status": true}
import importlib

import cs_wx_lib as lib

importlib.reload(lib)
_args = globals().get("mcp_args") or {}
mcp_result = lib.shot_status() if _args.get("status") else lib.start_shot_queue(_args["shots"], _args.get("settle", 20))
