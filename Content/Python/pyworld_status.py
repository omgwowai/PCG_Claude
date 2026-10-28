# pyworld_status.py -- READ-ONLY: the current level, dirty packages, and per PyWorld stage whether its volume holds
# its graph and is generated, plus the instance count of its output (a quick look after an editor restart).
import json
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
from pypcg import level, world as W  # noqa: E402

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
out = {"map": level.current_map(),
       "dirty_maps": [str(p.get_name()) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()],
       "dirty_content": [str(p.get_name()) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()][:12],
       "stages": {}, "probes": []}
for a in eas.get_all_level_actors():
    tags = {str(t) for t in a.tags}
    label = str(a.get_actor_label())
    if label.startswith("PyWorldProbe_"):
        out["probes"].append(label)
    for n, _l, _m, _t in W.STAGES:
        if W.volume_tag(n) in tags:
            pc = a.get_component_by_class(unreal.PCGComponent)
            g = pc.get_graph()
            inst = sum(c.get_instance_count() for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent))
            out["stages"][n] = {"graph": g.get_name() if g else None, "generated": bool(pc.get_editor_property("generated")),
                                "instances": inst}
print(json.dumps(out, indent=1))
