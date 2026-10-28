# pyworld_deselect.py -- clears the editor's actor selection (the yellow outline in screenshots).
import unreal

unreal.get_editor_subsystem(unreal.EditorActorSubsystem).select_nothing()
print("ok")
