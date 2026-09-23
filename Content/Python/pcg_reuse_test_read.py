# pcg_reuse_test_read.py — phase B of the City Sample REUSE test.
#
# Separate call from phase A by necessity: generation is asynchronous, so
# reading get_generated_graph_output() in the same call returns empty and
# raises nothing (the silent-zero trap).
#
# What counts as proof of reuse: real INSTANCES whose meshes are City Sample
# art — i.e. instanced-mesh components whose static_mesh resolves to
# /Game/{Building,Prop,Road,...}. A point count alone only proves the graph
# evaluated; instance counts plus mesh identity prove the migrated ART is
# actually being consumed.
#
# Cleans up after itself: generates nothing, but destroys the test volume so no
# test residue is left in the level.

import json

R = {}
def S(x):
    return str(x)

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

vol = None
for a in eas.get_all_level_actors():
    try:
        if a.get_class().get_name() == "PCGVolume" and "ReuseTest" in S(a.get_actor_label()):
            vol = a
            break
    except Exception:
        continue

if vol is None:
    R["fatal"] = "no PCGVolume_ReuseTest found — run pcg_reuse_test_setup.py first"
    print(json.dumps(R, indent=1, default=str))
    mcp_result = json.loads(json.dumps(R, default=str))
    raise SystemExit("test volume missing")

R["label"] = S(vol.get_actor_label())
R["origin"] = S(vol.get_actor_location())
R["graph"] = S(vol.pcg_component.get_graph())

# ---- 1. point counts from the generated output ----
G = {"rows": []}
try:
    coll = vol.pcg_component.get_generated_graph_output()
    items = coll.get_editor_property("tagged_data")
    G["tagged_count"] = len(items)
    total = 0
    for it in items:
        d = {"pin": S(it.get_editor_property("pin"))}
        try:
            data = it.get_editor_property("data").get_editor_property("data")
            d["class"] = data.get_class().get_name()
            try:
                d["num_points"] = data.get_num_points()
                total += d["num_points"]
            except Exception:
                d["num_points"] = "n/a"
        except Exception as e:
            d["err"] = S(e)[:80]
        G["rows"].append(d)
    G["total_points"] = total
except Exception as e:
    G["err"] = "%s: %s" % (type(e).__name__, S(e)[:150])
R["generated_output"] = G

# ---- 2. spawned geometry, and WHOSE art it is ----
S_ = {}
meshes = {}
total_inst = 0
ism_count = 0
city_art_instances = 0
try:
    for c in vol.get_components_by_class(unreal.PrimitiveComponent):
        cn = c.get_class().get_name()
        entry = {"class": cn, "component": S(c.get_name())}
        try:
            entry["instance_count"] = c.get_instance_count()
        except Exception:
            entry["instance_count"] = None
        mesh_name = None
        try:
            m = c.get_editor_property("static_mesh")
            if m:
                mesh_name = S(m.get_name())
                try:
                    mesh_name = S(m.get_path_name())
                except Exception:
                    pass
        except Exception:
            pass
        entry["mesh"] = mesh_name
        if entry["instance_count"]:
            ism_count += 1
            total_inst += entry["instance_count"]
            if mesh_name and "/Game/" in mesh_name:
                city_art_instances += entry["instance_count"]
                meshes[mesh_name] = meshes.get(mesh_name, 0) + entry["instance_count"]
        S_.setdefault(cn, []).append(entry)
except Exception as e:
    S_["err"] = "%s: %s" % (type(e).__name__, S(e)[:150])
R["spawned"] = S_
R["ism_component_count"] = ism_count
R["total_instances"] = total_inst
R["instances_using_Game_art"] = city_art_instances
R["distinct_Game_meshes"] = dict(sorted(meshes.items(), key=lambda kv: -kv[1])[:15])

# ---- 3. also count child actors (some spawners create actors, not ISMs) ----
A = {}
try:
    kids = {}
    for a in eas.get_all_level_actors():
        if a is vol:
            continue
        try:
            loc = a.get_actor_location()
        except Exception:
            continue
        if abs(loc.x - 20000.0) < 9000 and abs(loc.y) < 9000:
            cn = a.get_class().get_name()
            kids[cn] = kids.get(cn, 0) + 1
    A["actors_near_test_origin"] = kids
except Exception as e:
    A["err"] = S(e)[:120]
R["nearby_actors"] = A

verdict = (total_inst > 0 or sum(A.get("actors_near_test_origin", {}).values()) > 0)
R["REUSE_GENERATED_SOMETHING"] = bool(verdict)
R["REUSE_USED_CITY_ART"] = bool(city_art_instances > 0)

# ---- 4. clean up the test volume ----
C = {}
try:
    vol.pcg_component.cleanup_local(True)
    C["cleanup_local"] = "called"
except Exception as e:
    C["cleanup_local"] = "ERR %s" % type(e).__name__
try:
    eas.destroy_actor(vol)
    C["destroyed"] = True
except Exception as e:
    C["destroyed"] = "ERR %s" % type(e).__name__
remaining = 0
for a in eas.get_all_level_actors():
    try:
        if "ReuseTest" in S(a.get_actor_label()):
            remaining += 1
    except Exception:
        continue
C["test_volumes_remaining"] = remaining
R["cleanup"] = C

print("reuse read: tagged=%s points=%s ism=%d instances=%d city_art=%d gen=%s used=%s" % (
    G.get("tagged_count"), G.get("total_points"), ism_count, total_inst,
    city_art_instances, R["REUSE_GENERATED_SOMETHING"], R["REUSE_USED_CITY_ART"]))
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
