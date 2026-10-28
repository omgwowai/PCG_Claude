import gc
import json

import unreal

# pyworld_probe_channels.py -- READ ONLY. Channels (material layers), modifier priorities and material of the
# mesh-partition definitions: whether PCG's Write_MeshTerrain can paint the terrain's surface material.


def _get(obj, name):
    try:
        return obj.get_editor_property(name)
    except Exception as ex:
        return "ERR %s" % str(ex)[:120]


def _struct(v, depth=0):
    if depth > 3:
        return str(v)[:200]
    if isinstance(v, (list, tuple, unreal.Array)):
        return [_struct(x, depth + 1) for x in list(v)[:30]]
    if isinstance(v, unreal.StructBase):
        out = {}
        for name in dir(v):
            if name.startswith("_") or callable(getattr(v, name, None)):
                continue
            try:
                out[name] = _struct(v.get_editor_property(name), depth + 1)
            except Exception:
                pass
        return out or str(v)[:300]
    if isinstance(v, unreal.Object):
        return v.get_path_name()
    return str(v)[:300]


def run():
    eal = unreal.EditorAssetLibrary
    out = {}
    for p in ["/PCGPrimitives_MeshPartitionInterop/Assets/MeshPartitionDefinitions/MPD_Basic",
              "/PCGPrimitives_MeshPartitionInterop/Assets/MeshPartitionDefinitions/MPD_Default"]:
        a = eal.load_asset(p)
        rec = {}
        for name in ("material", "modifier_type_priorities", "channel_map", "channel_texel_size",
                     "compiled_section_build_variants", "preview_section_build_variant"):
            rec[name] = _struct(_get(a, name))
        try:
            rec["priorities_fn"] = [str(x) for x in a.get_modifier_type_priorities()]
        except Exception as ex:
            rec["priorities_fn"] = str(ex)[:200]
        out[p] = rec
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if a.get_class().get_name() == "MeshPartition":
            d = a.get_mesh_partition_definition()
            out["level_definition"] = d.get_path_name() if d else None
    return out


mcp_result = json.loads(json.dumps(run(), default=str))
gc.collect()
