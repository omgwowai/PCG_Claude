# pcg_sa_diag.py — read-only. Work out whether stage 1 finished generating, is still
# generating, or failed. The probe returned `generated: false` with zero instances and
# zero debug components one call after `gen` returned fired=true.
#
# It does NOT sleep. Sleeping here would block the game thread, and PCG's generation
# needs game-thread ticks to finish, so a sleep would suppress the very thing being
# measured. Elapsed time is taken from the editor's own clock instead, and the caller
# simply probes across separate calls.
#
# No UObject is stored at module level.

import gc
import json

TARGET = "/Game/PCGArea/L_SmallArea18"


def main():
    import unreal

    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    out = {}

    cur = str(les.get_current_level())
    if TARGET.split("/")[-1] not in cur:
        return {"abort": "not on %s (current: %s)" % (TARGET, cur)}

    volumes = [a for a in eas.get_all_level_actors()
               if a.get_class().get_name() == "PCGVolume"]
    out["volume_count"] = len(volumes)

    # per-volume generated flag and instanced component tally
    gen_true = []
    comp_summary = {}
    for v in volumes:
        label = str(v.get_actor_label())
        try:
            gen = bool(v.pcg_component.get_editor_property("generated"))
        except Exception as ex:
            gen = "ERR " + str(ex)[:60]
        if gen is True:
            gen_true.append(label)
        n_comp = 0
        n_inst = 0
        for c in v.get_components_by_class(unreal.PrimitiveComponent):
            if c.get_class().get_name() == "BrushComponent":
                continue
            try:
                n = c.get_instance_count()
            except Exception:
                continue
            if n:
                n_comp += 1
                n_inst += n
        comp_summary[label] = {"comps": n_comp, "instances": n_inst, "generated": gen}
    out["generated_true"] = sorted(gen_true)
    out["generated_true_count"] = len(gen_true)

    # stage 1 detail
    t1 = comp_summary.get("PCG_1_1_Terrain")
    out["stage1"] = t1

    # do the debug flags persist on stage 1's graph? If they do, generation was
    # submitted with them; if they are gone, something cleared them.
    for v in volumes:
        if str(v.get_actor_label()) != "PCG_1_1_Terrain":
            continue
        try:
            g = v.pcg_component.get_graph()
            flagged = []
            for nd in g.get_editor_property("nodes"):
                st = nd.get_settings()
                if st is not None and st.get_editor_property("debug"):
                    flagged.append(st.get_class().get_name())
            out["stage1_flagged_now"] = flagged
            out["stage1_node_count"] = len(g.get_editor_property("nodes"))
            out["stage1_graph"] = str(g.get_path_name())
        except Exception as ex:
            out["stage1_flag_err"] = str(ex)[:120]
        try:
            pc = v.pcg_component
            out["stage1_component"] = {
                "activated": bool(pc.get_editor_property("activated")),
                "generated": bool(pc.get_editor_property("generated")),
                "seed": int(pc.get_editor_property("seed")),
            }
            try:
                coll = pc.get_generated_graph_output()
                tagged = coll.get_editor_property("tagged_data")
                out["stage1_output_tagged"] = len(tagged)
            except Exception as ex:
                out["stage1_output_err"] = str(ex)[:100]
        except Exception as ex:
            out["stage1_pc_err"] = str(ex)[:120]

    # terrain actors, since stage 1 writes MeshTerrain
    terr = []
    for a in eas.get_all_level_actors():
        cn = a.get_class().get_name()
        if "MeshPartition" in cn or "MeshTerrain" in cn:
            e = {"label": str(a.get_actor_label()), "class": cn}
            try:
                e["comps"] = len(a.get_components_by_class(unreal.PrimitiveComponent))
            except Exception:
                pass
            terr.append(e)
    out["terrain_actors"] = terr

    # the sink for stage 1's own output: a quick count of PCG debug objects anywhere
    dbg_total = 0
    for a in eas.get_all_level_actors():
        for c in a.get_components_by_class(unreal.PrimitiveComponent):
            try:
                sm = c.get_editor_property("static_mesh")
                if sm and str(sm.get_path_name()).startswith("/PCG/DebugObjects/"):
                    try:
                        dbg_total += c.get_instance_count() or 0
                    except Exception:
                        pass
            except Exception:
                continue
    out["debug_cubes_level_wide"] = dbg_total
    return out


try:
    RESULT = {"ok": True, "data": main()}
except Exception as exc:
    RESULT = {"ok": False, "error": "%s: %s" % (type(exc).__name__, str(exc)[:300])}

try:
    mcp_result = json.loads(json.dumps(RESULT, default=str))
except Exception as se:
    mcp_result = {"ok": False, "serialization_failed": str(se)[:200]}

print(json.dumps(mcp_result, ensure_ascii=False, default=str))
del RESULT
gc.collect()
