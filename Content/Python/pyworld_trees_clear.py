# pyworld_trees_clear.py -- DELETES the earlier single-mesh experiments under /Game/PyPCG/World/Trees (root files only)
# and the catalog actors.
import json

import unreal

EAL = unreal.EditorAssetLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for a in eas.get_all_level_actors():
    if str(a.get_actor_label()).startswith("PyWorldCatalog_"):
        eas.destroy_actor(a)
gone = []
for p in EAL.list_assets("/Game/PyPCG/World/Trees", recursive=False):
    EAL.delete_asset(p.split(".")[0])
    gone.append(p)
print(json.dumps(gone))
