# cs_cvar.py -- set / read console variables. Args: {"set": {"name": value, ...}, "get": ["name", ...]}
import unreal

_args = globals().get("mcp_args") or {}
_w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
for _n, _v in (_args.get("set") or {}).items():
    unreal.SystemLibrary.execute_console_command(_w, "%s %s" % (_n, _v))
mcp_result = {n: unreal.SystemLibrary.get_console_variable_float_value(n)
              for n in list((_args.get("set") or {}).keys()) + list(_args.get("get") or [])}
del _w
