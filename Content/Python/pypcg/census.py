"""Editor only: what a stage volume produced, as plain records for pypcg.v2 (spec 3, V2)."""
import json

import unreal

from pypcg import stages, v2
from pypcg.ue import convert

DEBUG_MESH = "/PCG/DebugObjects/"


def actor_by_label(label):
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        try:
            if str(a.get_actor_label()) == label:
                return a
        except Exception:
            continue
    return None


def volume(n):
    a = actor_by_label(stages.LABEL(n))
    if a is None:
        raise RuntimeError("no actor labelled %s in this level" % stages.LABEL(n))
    return a


def component(n):
    return volume(n).get_component_by_class(unreal.PCGComponent)


def outputs(pc):
    items = []
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        d = td.get_editor_property("data").get_editor_property("data")            # traps.md 46
        tags = [str(t) for t in td.get_editor_property("tags")]
        try:
            value = convert.from_pcg(d)
        except TypeError:
            value = None
        items.append(v2.describe(value, tags, d.get_class().get_name()))
    return items


def instances(actor):
    per_mesh, components = {}, {}
    for c in actor.get_components_by_class(unreal.PrimitiveComponent):
        cls = c.get_class().get_name()
        if cls == "BrushComponent":
            continue
        components[cls] = components.get(cls, 0) + 1
        if isinstance(c, unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            path = sm.get_path_name() if sm else ""
            if path.startswith(DEBUG_MESH):
                continue
            per_mesh[path] = per_mesh.get(path, 0) + int(c.get_instance_count())
    return {"total": sum(per_mesh.values()), "per_mesh": per_mesh, "components": components}


def record(n):
    a = volume(n)
    pc = a.get_component_by_class(unreal.PCGComponent)
    g = pc.get_graph()
    return {"stage": n, "graph": g.get_path_name() if g else None, "generated": bool(pc.get_editor_property("generated")),
            "items": outputs(pc), "instances": instances(a)}


def overrides(pc):
    inst = pc.get_editor_property("graph_instance")
    return json.loads(unreal.PyPCGToolsLibrary.export_instance_overrides(inst)) if inst else {}


def apply_overrides(pc, values):
    """Set each value on the component's graph instance; names the graph does not have are skipped
    and reported (a slim graph drops debug, partition and merged seed parameters: ruling N5)."""
    inst = pc.get_editor_property("graph_instance")
    done, skipped = [], {}
    for k, v in values.items():
        err = unreal.PyPCGToolsLibrary.set_instance_parameter(inst, k, json.dumps({"v": v}))
        if err:
            skipped[k] = err
        else:
            done.append(k)
    return {"set": done, "skipped": skipped}
