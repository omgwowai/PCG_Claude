# cs_autosave_off.py -- turn editor autosave off in memory (UEditorLoadingSavingSettings.bAutoSaveEnable, trap 85)
import unreal
_cdo = unreal.get_default_object(unreal.load_class(None, "/Script/UnrealEd.EditorLoadingSavingSettings"))
_cdo.set_editor_property("bAutoSaveEnable", False, unreal.PropertyAccessChangeNotifyMode.NEVER)
mcp_result = {"bAutoSaveEnable": bool(_cdo.get_editor_property("bAutoSaveEnable"))}
del _cdo
