# pypcg_s01_terrain_probe.py -- stage 1 (Task 24): the terrain-state sampler. Read-only with respect to shipped
# content: a probe graph under /Game/PyPCG/Probe/ on a SPAWNED probe actor (never saved; the stage-1 volume is not
# touched) reads the mesh terrain twice -- Final (what every later stage stands on) and Intermediate at sub-priority
# 2 (= stage 1's write alone, the query stage 7 makes) -- and extracts the Intermediate one's points.
#   {"build": true, "nonce": n}                       -> build PCG_T24Terrain + generate on the probe actor
#   {"read": true, "out": "E:/PCG_Claude/Saved/t24/terrain_x.json", "grid": 41}
#                                                     -> Final heights on a 41 x 41 grid + every Intermediate
#                                                        vertex, and the output objects' path names
#   {"compare": ["a.json", "b.json"]}                 -> the diff of two reads
#   {"remove": true}
# `nonce` moves the query's z extent by n cm, so a rebuild is a new query (the cache cannot hand back an earlier
# one); after a build, wait until the read's output objects are NEW before trusting its numbers (traps.md 77).
# The comparison this stage's evidence rests on: read once under the official terrain and once under the slim one,
# then `compare` -- equal on every vertex and every grid height means the slim write changed nothing.
import json
import os
import sys

import unreal

for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]

LABEL = "T24_TerrainProbe"
PATH = "/Game/PyPCG/Probe/PCG_T24Terrain"


def _node(name, cls, settings=None, inputs=None, extra=None):
    x = {"name": name, "class": cls, "title": "", "settings": dict(settings or {}, Seed=1), "comment": "",
         "bubble_visible": False, "bubble_pinned": False, "inputs": inputs or [], "pin_defaults": [],
         "getter_param": "", "pos": None}
    x.update(extra or {})
    return x


def _actor(spawn_at=None):
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        try:
            if str(a.get_actor_label()) == LABEL:
                return a
        except Exception:
            continue
    if spawn_at is None:
        return None
    a = eas.spawn_actor_from_class(unreal.PCGVolume, spawn_at, unreal.Rotator())
    a.set_actor_label(LABEL)
    return a


def build(args):
    from pypcg import build as B, census, ir as _ir
    off = _ir.load("E:/PCG_Claude/Tools/pypcg/official_ir/PCG_1_1_Terrain.json")
    by = {x["name"]: x for x in off["nodes"]}

    def get(name, query, sub):
        g = json.loads(json.dumps(by["GetMeshTerrain_0"]))
        g["name"] = name
        g["pos"] = None
        # `nonce` moves the query's z extent by that many cm: a new settings CRC, so the PCG cache cannot hand back
        # an earlier query's result (a same-settings rebuild returned the old terrain, 2026-10-20)
        g["overrides"] = {"MeshPartitionBoundSize": {"X": 300000, "Y": 300000, "Z": 300000 + int(args.get("nonce", 0))},
                          "MeshPartitionQueryType": query, "ModifierSubPriority": sub}
        return g
    ext = json.loads(json.dumps(by["ExtractMeshTerrainPoints_0"]))
    ext["pos"] = None
    ext["inputs"] = [{"label": "PrimaryInput", "edges": [["GetInter2", "Out"]]}]
    nodes = [_node("DefaultInputNode", "PCGGraphInputOutputSettings"), get("GetFinal", "Final", 0),
             get("GetInter2", "Intermediate", 2), ext]
    outs = []
    for tag, src in (("T24Final", "GetFinal"), ("T24Inter2", "GetInter2"), ("T24Inter2Points", "ExtractMeshTerrainPoints_0")):
        nodes.append(_node("Tag_" + tag, "PCGAddTagSettings", {"TagsToAdd": tag}, [{"label": "In", "edges": [[src, "Out"]]}]))
        outs.append(["Tag_" + tag, "Out"])
    nodes.append(_node("DefaultOutputNode", "PCGGraphInputOutputSettings", inputs=[{"label": "Out", "edges": outs}]))
    ir = {"schema": off["schema"], "graph": "PCG_T24Terrain", "graph_props": {}, "params": [], "comment_boxes": [],
          "nodes": nodes, "sites": []}
    diffs = B.build_slim(ir, PATH, save=True)
    if diffs:
        return {"abort": [str(d) for d in diffs[:5]]}
    t = census.volume(1).get_actor_transform()
    a = _actor(t.translation)
    a.set_actor_location(t.translation, False, False)
    a.set_actor_scale3d(unreal.Vector(1.0, 1.0, 1.0))
    pc = a.get_component_by_class(unreal.PCGComponent)
    pc.set_editor_property("regenerate_in_editor", False)
    pc.set_graph(unreal.EditorAssetLibrary.load_asset(PATH))
    pc.activate(True)
    pc.generate_local(True)
    return {"graph": PATH, "at": [t.translation.x, t.translation.y, t.translation.z]}


def read(args):
    from pypcg.ue import convert
    a = _actor()
    if a is None:
        return {"abort": "no probe actor"}
    pc = a.get_component_by_class(unreal.PCGComponent)
    got = {}
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        tags = [str(t) for t in td.get_editor_property("tags")]
        d = td.get_editor_property("data").get_editor_property("data")
        for t in tags:
            if t.startswith("T24"):
                got[t] = d
    out = {"kinds": {k: v.get_class().get_name() for k, v in got.items()},
           "objects": {k: v.get_path_name() for k, v in got.items()}}
    g = int(args.get("grid", 41))
    half = float(args.get("half", 140000.0))
    loc = a.get_actor_location()
    if "T24Final" in got:
        terr = convert.from_pcg(got["T24Final"])
        rows = []
        for i in range(g):
            for j in range(g):
                x = loc.x - half + 2 * half * i / (g - 1)
                y = loc.y - half + 2 * half * j / (g - 1)
                rows.append([x, y, terr.height(x, y)])
        out["final_grid"] = rows
    if "T24Inter2Points" in got:
        pts = convert.points_of(got["T24Inter2Points"])
        out["inter2_points"] = [list(p) for p in pts.loc]
    path = args["out"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    hs = [r[2] for r in out.get("final_grid", []) if r[2] is not None]
    return {"written": path, "kinds": out["kinds"], "objects": out["objects"], "final_grid": len(out.get("final_grid", [])),
            "final_misses": sum(1 for r in out.get("final_grid", []) if r[2] is None),
            "final_z_range": [min(hs), max(hs)] if hs else None,
            "inter2_points": len(out.get("inter2_points", []))}


def compare(args):
    a, b = (json.load(open(p, encoding="utf-8")) for p in args["compare"])
    res = {}
    ga, gb = a.get("final_grid", []), b.get("final_grid", [])
    if ga and len(ga) == len(gb):
        d = [abs((x[2] or 0) - (y[2] or 0)) for x, y in zip(ga, gb)]
        res["final_grid"] = {"n": len(d), "max_abs_cm": max(d), "differ": sum(1 for v in d if v != 0.0)}
    pa, pb = a.get("inter2_points", []), b.get("inter2_points", [])
    if pa and len(pa) == len(pb):
        d = [max(abs(p[k] - q[k]) for k in range(3)) for p, q in zip(pa, pb)]
        res["inter2_points"] = {"n": len(d), "max_abs_cm": max(d), "differ": sum(1 for v in d if v != 0.0)}
    else:
        res["inter2_points"] = {"n_a": len(pa), "n_b": len(pb)}
    return res


def remove(args):
    a = _actor()
    return {"removed": bool(a) and unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(a)}


def main(args):
    from pypcg import level
    # Final review I2: the probe actor is spawned into the current level; the demo is the level the s01.md
    # terrain evidence was read on, and nowhere else may receive the actor.
    refused = level.require(level.DEMO, "pypcg_s01_terrain_probe.py")
    if refused:
        return refused
    if args.get("read"):
        return read(args)
    if args.get("compare"):
        return compare(args)
    if args.get("remove"):
        return remove(args)
    return build(args)


mcp_result = json.loads(json.dumps(main(mcp_args or {}), default=str))
