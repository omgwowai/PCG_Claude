import gc
import json
import os
import shutil
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
_TOOLS = os.path.join(_REPO, "Tools", "pypcg")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

# pypcg_compare_stage.py -- V2 in the demo level (spec 3). ONE generation per call; read it in the next.
# NEVER save the level: every change here is in memory and `restore` undoes the graph swaps.
#   prepare                                 record graphs/overrides/regen flags; turn regen-in-editor off
#   gen {"stage", "variant", "seed"?}       variant "official" | "slim"; slim swaps in /Game/PyPCG/Slim/<graph>
#   read {"stage", "as", "into"?}           census -> Saved/Reports/v2/s<into>/<as>.json (+ the run record
#                                           when <as> starts with "slim_"); into defaults to stage
#   verdict {"stage"}                       pypcg.v2 over the files of that stage -> verdict.json + docs/pypcg/v2/sNN.md
#   fingerprint {"save" | "compare": name}  which volumes' outputs changed between two calls
#   restore                                 official graphs, overrides and regen flags back on every volume
OUT = os.path.join(_REPO, "Saved", "Reports", "v2")
STATE = os.path.join(OUT, "_state.json")
DEMO_OVERRIDES = os.path.join(_REPO, "Tools", "pypcg", "data", "demo_overrides.json")


def _load(path, default=None):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True)


def _stage_dir(n):
    return os.path.join(OUT, "s%02d" % n)


def phase_prepare(args):
    from pypcg import census, stages
    state = _load(STATE, {})
    for n, label, *_ in stages.STAGES:
        pc = census.component(n)
        if label not in state:                                     # first prepare: the shipped state
            g = pc.get_graph()
            state[label] = {"graph": g.get_path_name() if g else None, "overrides": census.overrides(pc),
                            "regen": bool(pc.get_editor_property("regenerate_in_editor")),
                            "seed": int(pc.get_editor_property("seed"))}
        pc.set_editor_property("regenerate_in_editor", False)      # every regeneration is explicit (trap 33)
    _save(STATE, state)
    if not os.path.exists(DEMO_OVERRIDES) or args.get("refresh"):
        _save(DEMO_OVERRIDES, {label: s["overrides"] for label, s in state.items()})
    return {"volumes": len(state), "regen_off": True, "demo_overrides": DEMO_OVERRIDES}


def phase_gen(args):
    from pypcg import census, stage_api, stages
    n, variant = int(args["stage"]), args["variant"]
    state = _load(STATE)
    if state is None:
        return {"abort": "run prepare first"}
    label = stages.LABEL(n)
    pc = census.component(n)
    applied = {}
    if variant == "slim":
        pc.set_graph(unreal.EditorAssetLibrary.load_asset("/Game/PyPCG/Slim/" + label))
        values = dict(state[label]["overrides"])
        values[stage_api.SEED] = int(args.get("seed", stage_api.SEED_DEFAULT))
        applied = census.apply_overrides(pc, values)               # after set_graph (trap 44)
        os.environ[stage_api.RECORD_ENV] = "1"
    else:
        pc.set_graph(unreal.EditorAssetLibrary.load_asset(state[label]["graph"].split(".")[0]))
        applied = census.apply_overrides(pc, state[label]["overrides"])
        pc.set_editor_property("seed", int(state[label]["seed"]))   # set_graph leaves the component seed alone
        os.environ.pop(stage_api.RECORD_ENV, None)                 # official runs must not record
    pc.activate(True)
    pc.generate_local(True)
    return {"stage": n, "variant": variant, "graph": pc.get_graph().get_path_name(), "overrides": applied}


def phase_read(args):
    from pypcg import census, stage_api
    n, name = int(args["stage"]), args["as"]
    into = int(args.get("into", n))
    rec = census.record(n)
    _save(os.path.join(_stage_dir(into), name + ".json"), rec)
    run = os.path.join(stage_api.RUNS_DIR, "s%02d.json" % n)
    if name.startswith("slim_") and os.path.exists(run):
        shutil.copyfile(run, os.path.join(_stage_dir(into), name + ".run.json"))
    tags = {}
    for it in rec["items"]:
        for t in it["tags"]:
            if ":" not in t:
                tags[t] = tags.get(t, 0) + 1
    return {"stage": n, "as": name, "into": into, "generated": rec["generated"], "graph": rec["graph"], "tags": tags,
            "instances": rec["instances"]["total"]}


def _contract_tags(n):
    """The tags stage n owes its readers, read from its official IR snapshot (ruling T7c). A snapshot
    whose output carries no tag at all yields the empty set, which v2 reads as one "(all)" group."""
    for m in [m for m in sys.modules if m == "port_brief"]:
        del sys.modules[m]
    import port_brief
    return {t for _, _, ts in port_brief.output_tags(port_brief.load(n)) for t in ts if not t.startswith("(")}


def phase_verdict(args):
    from pypcg import stages, v2
    n = int(args["stage"])
    d = _stage_dir(n)
    official = _load(os.path.join(d, "official.json"))
    module = stages.spec(n)
    seeds = v2.V2_SEEDS if module.RANDOM else (v2.V2_SEEDS[-1],)
    runs = [_load(os.path.join(d, "slim_%d.json" % s)) for s in seeds]
    if official is None or any(r is None for r in runs):
        return {"abort": "missing official.json or slim_<seed>.json for seeds %s" % (seeds,)}
    tags = _contract_tags(n)
    v = v2.verdict(official, runs, not module.RANDOM, v2.thresholds(n), tags)
    pairs = {}
    for k in stages.DOWNSTREAM.get(n, []):
        o, r = _load(os.path.join(d, "down_%d_official.json" % k)), _load(os.path.join(d, "down_%d_slim.json" % k))
        if o is None or r is None:
            return {"abort": "missing down_%d_official.json or down_%d_slim.json" % (k, k)}
        pairs[k] = (o, r)
    down = v2.downstream(pairs)
    after = _load(os.path.join(d, "official_after.json"))
    notes = []
    if after is not None and not v2.same(official, after, tags):
        down.append("the official graph did not reproduce its own output after restore (determinism)")
    for s in seeds:
        run = _load(os.path.join(d, "slim_%d.run.json" % s), {})
        if run.get("notes"):
            notes.append("seed %d: %s" % (s, "; ".join(run["notes"])))
        if "seconds" in run:
            notes.append("seed %d: Python %.2f s" % (s, run["seconds"]))
    result = {"stage": n, "pass": v["pass"] and not down, "failures": v["failures"], "downstream": down, "rows": v["rows"]}
    _save(os.path.join(d, "verdict.json"), result)
    md = os.path.join(_REPO, "docs", "pypcg", "v2", "s%02d.md" % n)
    os.makedirs(os.path.dirname(md), exist_ok=True)
    with open(md, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(v2.markdown(n, v, down, notes))
    return {"stage": n, "pass": result["pass"], "failures": v["failures"][:20], "downstream": down, "report": md}


def phase_fingerprint(args):
    from pypcg import census, stages
    prints = {}
    for n, label, *_ in stages.STAGES:
        coll = census.component(n).get_generated_graph_output()
        prints[label] = [td.get_editor_property("data").get_editor_property("data").get_path_name()
                         for td in coll.get_editor_property("tagged_data")]
    if "save" in args:
        _save(os.path.join(OUT, "_fp_%s.json" % args["save"]), prints)
        return {"saved": args["save"], "volumes": len(prints)}
    before = _load(os.path.join(OUT, "_fp_%s.json" % args["compare"]), {})
    return {"changed": sorted(k for k in prints if prints[k] != before.get(k))}


def phase_restore(args):
    from pypcg import census, stage_api, stages
    state = _load(STATE)
    if state is None:
        return {"abort": "nothing to restore"}
    out = {}
    for n, label, *_ in stages.STAGES:
        pc = census.component(n)
        s = state[label]
        if pc.get_graph() is None or pc.get_graph().get_path_name() != s["graph"]:
            pc.set_graph(unreal.EditorAssetLibrary.load_asset(s["graph"].split(".")[0]))
        res = census.apply_overrides(pc, s["overrides"])
        pc.set_editor_property("regenerate_in_editor", s["regen"])
        pc.set_editor_property("seed", int(s["seed"]))
        out[label] = {"graph": pc.get_graph().get_path_name(), "skipped": res["skipped"]}
    os.environ.pop(stage_api.RECORD_ENV, None)
    os.remove(STATE)
    return {"restored": len(out), "problems": {k: v for k, v in out.items() if v["skipped"]}}


PHASES = {"prepare": phase_prepare, "gen": phase_gen, "read": phase_read, "verdict": phase_verdict,
          "fingerprint": phase_fingerprint, "restore": phase_restore}


def run(args):
    if "L_CitySamplePCG_Demo" not in str(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).get_current_level()):
        return {"abort": "V2 runs in /CitySamplePCG/Levels/L_CitySamplePCG_Demo"}
    return PHASES[args["phase"]](args)


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
