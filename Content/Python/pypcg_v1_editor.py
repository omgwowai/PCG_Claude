import gc
import importlib
import json
import os
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())

# pypcg_v1_editor.py -- V1 checks with the editor's real booleans, on the runs V2 recorded (spec 3, V1).
# Args: {"stage": n}                                   -> stage mode (below)
#       {"assign": {"stage": n}}                       -> assign mode (Task 12; + the oracle, Task 15)
#       {"assign": {"stage": n, "step": "gen"}}        -> generate the assign oracle (Task 15)
#       {"published": {"stage": n}}                    -> published mode (Task 11): the LIVE volume's
#                                                         output against the stage's own parameters
# The two are told apart by the presence of the "assign" key, whose value must be a DICT carrying
# "stage"; `{"stage": n, "assign": true}` is not a form this file accepts.
# Stage mode: for every Saved/Reports/v2/sNN/slim_<seed>.run.json:
#   - replay: when the inputs were recordable, run the stage again with the same params and seed and
#     require identical outputs (determinism);
#   - pypcg.checks.sNN.check(inputs or None, params, outputs, ops, official) when that module exists;
#     official is the volume's current output when it holds its official graph (after V2's restore);
#     a checks module that defines check_record(rec, ops, official) gets the whole record instead
#     (stage 10: a partial replay of what the record can rebuild, then the invariants).
# Assign mode (Task 12): every Assign_Assets call the official graph holds is rebuilt in Python from
# its OWN recorded settings, with one target point, and the Python expansion is reported -- the phase
# `{"assign": {"stage": n}}` of the plan. See `assign_phase` for what it does and does not compare.

ASSIGN_SUBGRAPH = "/PCGPrimitives/Primitives/Assign/Assign_Assets"

# The Assign_Assets pin names mapped onto the keys `pypcg.geo.assets.expand` reads. The dictionary is
# the seam between the graph and the helper, and it is the reason this table is explicit: without it
# every parameter recorded from the graph would arrive at `expand` under a name it does not read and
# be silently replaced by its default. Task 12's review found exactly that.
#
# Three pins are deliberately mapped to None, which `assign_calls` reads as "collected but not
# honoured by `expand`":
#   MatchScaleToInputBounds  the ratio is reported as `$Scale` either way; whether the primitive
#                            also writes it into the input points' `$Scale` is unmeasured
#   UseIndexattribute / IndexAttribute
#                            the index-attribute pick (`Branch_1_Index`) is not implemented; `choose`
#                            always draws
# The four graph-override pins are not parameters of the computation at all and are not listed.
ASSIGN_PARAM_KEYS = {
    "PositionOffset": "position_offset",
    "RotationOffset": "rotation_offset",
    "ScaleOffset": "scale_offset",
    "ExtentsScale": "extents_scale",
    "UniformScale": "uniform_scale",
    "UseMeshBounds": "use_mesh_bounds",
    "UseMeshAttribute": "use_mesh_attribute",
    "MeshAttribute": "mesh_attribute",
    "RandomPositionRange": "random_position_range",
    "RandomRotationRange": "random_rotation_range",
    "RandomScaleRange": "random_scale_range",
    "MatchScaleToInputBounds": None,
    "UseIndexattribute": None,
    "IndexAttribute": None,
}
# The three `TransformPoints_2` pins, whose values only mean anything together with an `rng`.
ASSIGN_RANDOM_PINS = ("RandomPositionRange", "RandomRotationRange", "RandomScaleRange")


def assign_calls(ir):
    """Every Assign_Assets node of a graph IR, with its settings and its `Assets` override.

    The overrides come from the IR the exporter writes (a subgraph node's `overrides` is its instance
    override bag), so nothing here has to reach into the property bag by hand.

    `params` is keyed the way `pypcg.geo.assets.expand` reads its `params` dict (see
    `ASSIGN_PARAM_KEYS`), and `unhonoured` lists the pins the graph sets that `expand` does not read,
    so a caller can see the gap rather than silently lose it. `random` is True when this call has a
    non-zero random range: a caller that does not supply an `rng` then cannot reproduce the
    primitive's draw.

    `seed` is the node's OWN `Seed` pin (instance override first, then the settings' value). It is
    recorded for a reader and is deliberately NOT fed to `expand`: the primitive spends that seed on
    `TransformPoints_2`'s draws and on the asset pick, while `expand` takes only `params["rng"]`, and
    this phase supplies no rng. A caller that wants to reproduce a random call must construct an
    `rng` and pass the call's `seed` to it; nothing today does, which is what `random_calls`
    reports."""
    out = []
    for node in ir.get("nodes", []):
        sub = node.get("subgraph") or ""
        if ASSIGN_SUBGRAPH not in sub:
            continue
        ov = dict(node.get("overrides") or {})
        params, unhonoured = {}, []
        for pin, key in ASSIGN_PARAM_KEYS.items():
            if pin not in ov:
                continue
            if key is None:
                unhonoured.append(pin)
            else:
                params[key] = ov[pin]
        random = any(_non_zero(ov.get(p)) for p in ASSIGN_RANDOM_PINS)
        out.append({"node": node["name"], "title": node.get("title", ""),
                    "assets": list(ov.get("Assets") or []),
                    "params": params, "unhonoured": unhonoured, "random": random,
                    "seed": (ov.get("Seed", (node.get("settings") or {}).get("Seed")))})
    return out


def _non_zero(v):
    """A Vector/Rotator override that is not all-zero, as a truth test for `assign_calls`' `random`."""
    if v is None:
        return False
    if isinstance(v, dict):
        return any(abs(float(x)) > 0.0 for x in v.values())
    if isinstance(v, (int, float)):
        return abs(float(v)) > 0.0
    return any(abs(float(x)) > 0.0 for x in v)


def assign_probe_result(call, target, table):
    """The Python half of one Assign_Assets call: expand ONE target point with the call's own
    parameters and report the result beside the primitive's.

    This is a shape report, not an equality: nothing here is compared with the primitive. The exact
    comparison is the oracle (`_assign_oracle_compare`), which taps the primitive's own input and
    output on a live volume."""
    from pypcg import geo
    points = geo.Points()
    points.add(target["loc"], rot=target["rot"], scale=target["scale"], seed=target["seed"],
               bounds_min=target["bounds_min"], bounds_max=target["bounds_max"])
    params = dict(call["params"])
    params.setdefault("mesh_attribute", "Mesh")
    ours = geo.assets.expand(points, table, [0], params)
    return {"n": len(ours),
            "loc": [list(l) for l in ours.loc[:4]],
            "rot": [[round(x, 4) for x in r] for r in ours.rot[:4]],
            "scale": [list(s) for s in ours.scale[:4]],
            "seed": list(ours.seed[:4]),
            "asset": [str(a) for a in ours.attrs.get("Asset", [])[:4]]}


def _assign_failures(n, calls, tabled, fixtures):
    """Expand every Assign_Assets call of stage `n` with ONE fixture target and report what came back.

    `fixtures` is the list of recorded run records. `_assign_target` uses the first run's first output
    point when one exists (a real point of this stage) and a fixed box otherwise, so this runs whether
    or not the stage has recorded runs; the caller reports how many it had. A call fails when it
    records no `Assets`, when one of its assets does not load, or when the expansion yields no points.

    Each `checked` row also carries `unhonoured` (pins the graph sets that `expand` does not read) and
    `random` (the call has a non-zero random range, so its real output cannot be reproduced without
    the primitive's own random stream). Those are reported, not failed: they are gaps in the helper's
    coverage, not wrong behaviour."""
    failures, checked = [], []
    target = _assign_target(fixtures)
    for call in calls:
        if not call["assets"]:
            failures.append("Assign_Assets %s: no Assets override recorded" % call["node"])
            continue
        missing = [p for p in call["assets"] if tabled[p]["note"]]
        if missing:
            failures.append("Assign_Assets %s: %s could not be loaded" % (call["node"], missing))
            continue
        table = [tabled[p] for p in call["assets"]]
        ours = assign_probe_result(call, target, table)
        if ours["n"] == 0:
            failures.append("Assign_Assets %s: expanding %d assets gave no points"
                            % (call["node"], len(call["assets"])))
            continue
        checked.append({"node": call["node"], "assets": len(call["assets"]), "points": ours["n"],
                        "asset0": (ours["asset"] or [None])[0],
                        "loc0": ours["loc"][0] if ours["loc"] else None,
                        "unhonoured": list(call.get("unhonoured") or []),
                        "random": bool(call.get("random"))})
    return failures, checked


def _assign_target(fixtures):
    """The one target point the comparison uses: the first output point of the first recorded run
    (a real point of this stage), or a fixed 1000 x 1000 x 100 cm box at the origin when there is no
    run to read. The box is the fixture the editor measurements of task-12-report.md used."""
    for rec in fixtures:
        for pin, items in sorted(rec.get("outputs", {}).items()):
            for value, _tags in items[:1]:
                if value.get("kind") != "points" or value.get("truncated") or not value.get("n"):
                    continue
                return {"loc": tuple(value["loc"][0]), "rot": tuple(value["rot"][0]),
                        "scale": tuple(value["scale"][0]), "seed": int(value["seed"][0]),
                        "bounds_min": tuple(value["bounds_min"][0]),
                        "bounds_max": tuple(value["bounds_max"][0]),
                        "from": "%s/%s" % (rec.get("stage"), pin)}
    return {"loc": (0.0, 0.0, 0.0), "rot": (0.0, 0.0, 0.0), "scale": (1.0, 1.0, 1.0), "seed": 42,
            "bounds_min": (-1000.0, -500.0, 0.0), "bounds_max": (1000.0, 500.0, 100.0),
            "from": "the fixed box (no recorded run)"}


def assign_phase(n, step=None, only=None, overrides=None, label=None):
    """`{"assign": {"stage": n}}`: rebuild every Assign_Assets call of stage `n` in Python from its OWN
    recorded settings, with one target point, and check the Python expansion's shape against the
    graph's own parameters.

    This runs WITHOUT the demo level's volumes: it reads the official graph's IR (the calls and their
    overrides), loads the real assets through `pypcg.ue.assets.load`, and expands the fixture target.

    The exact comparison with the primitive is two more calls (Task 15):
      `{"assign": {"stage": n, "step": "gen"}}`  builds the ORACLE graph -- the official nodes upstream
          of every Assign_Assets call, the call itself, and a tap on its input and its output -- puts it
          on stage n's own volume (so the scene reads, the component seed and every node seed are the
          official ones) and generates. Restore the volume with V2's `gen {variant: official}` or
          `restore` (the result says `restore_required`). Two options (Task 15 fix round 1):
          `"calls": [node, ...]` keeps only those Assign_Assets calls (and what they read), and
          `"set": {node: {pin: value}}` edits a call's overrides in the oracle graph -- e.g. zeroes a
          random range so a setting that only appears on random calls can be measured exactly.
      `{"assign": {"stage": n, "label": name}}` (after that generation) also reads both taps and runs
          `pypcg.geo.assets.expand_items` on the tapped input with the call's own settings and the
          primitive's own picks (the tapped output's last item names each target's kit), and compares
          the result with the tapped output item for item: point counts, location, rotation
          (quaternion), scale, `Asset`, bounds and seed, reporting how many are bit for bit equal and
          the largest difference of each. The settings compared are the ORACLE graph's own (so a `set`
          edit is honoured). A call with a non-zero random range is marked `random` and compared only
          on item sizes, item order and `Asset`: this phase has no `TransformPoints_2` stream. `oracle`
          is absent when the volume does not hold the oracle. With `label`, the oracle result is
          written to `Saved/Reports/v2/sNN/assign_oracle_<label>.json`."""
    from pypcg import extract, geo, stages
    from pypcg.ue import assets as uassets
    if step == "gen":
        return _assign_oracle_gen(n, only, overrides)
    graph = unreal.EditorAssetLibrary.load_asset(stages.official_path(n))
    if graph is None:
        return {"stage": n, "abort": "cannot load %s" % stages.official_path(n)}
    calls = assign_calls(extract.export(graph))
    if not calls:
        return {"stage": n, "calls": 0, "note": "this stage calls no Assign_Assets"}
    paths = [p for c in calls for p in c["assets"]]
    tabled = {e["path"]: e for e in uassets.load(sorted(set(paths)))}
    d = os.path.join(_REPO, "Saved", "Reports", "v2", "s%02d" % n)
    fixtures = []
    if os.path.isdir(d):
        for f in sorted(x for x in os.listdir(d) if x.endswith(".run.json")):
            try:
                fixtures.append(json.load(open(os.path.join(d, f), encoding="utf-8")))
            except ValueError:
                continue
    failures, checked = _assign_failures(n, calls, tabled, fixtures)
    # `random_calls` counts the calls whose real output cannot be reproduced here: a non-zero random
    # range draws from `TransformPoints_2`'s own seeded stream, and this phase supplies no `rng`. A
    # clean `failures` list is therefore not a claim that those calls agree with the primitive.
    random_calls = [c["node"] for c in checked if c.get("random")]
    unhonoured = sorted({p for c in checked for p in (c.get("unhonoured") or [])})
    out = {"stage": n, "calls": len(calls), "runs": len(fixtures),
           "target": {k: list(v) if isinstance(v, tuple) else v for k, v in _assign_target(fixtures).items()},
           "expanded": checked, "random_calls": random_calls,
           "random": bool(random_calls), "unhonoured_pins": unhonoured,
           "failures": failures[:20]}
    oracle = _assign_oracle_compare(n, calls, uassets)
    if oracle is not None:
        out["oracle"] = oracle
        if label:
            # The evidence on disk (Task 15 fix round 2): the full oracle result, read in THIS call,
            # after the generation the previous call started.
            path = os.path.join(_REPO, "Saved", "Reports", "v2", "s%02d" % n, "assign_oracle_%s.json" % label)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(dict(oracle, stage=n, label=label), fh, indent=1, default=str)
            oracle["written"] = path
        out["failures"] = (failures + oracle.get("failures", []))[:20]
    return out


ORACLE_GRAPH = "/Game/PyPCG/Probe/PCG_AssignOracle_s%02d"
ORACLE_IN, ORACLE_OUT = "AssignIn_", "AssignOut_"


def _upstream(nodes, name):
    """Every node `name` depends on (its inputs, transitively), `name` included."""
    by = {x["name"]: x for x in nodes}
    seen, todo = set(), [name]
    while todo:
        k = todo.pop()
        if k in seen or k not in by:
            continue
        seen.add(k)
        for p in by[k].get("inputs", []):
            todo += [e[0] for e in p["edges"]]
    return seen


def _io_node(name, seed, label):
    pin = {"Label": label, "PinStatus": "Normal", "Tooltip": "", "Usage": "Normal",
           "bAllowMultipleConnections": True, "bAllowMultipleData": True, "bInvisiblePin": False,
           "AllowedTypes": {"CustomSubtype": -1,
                            "Ids": [{"Struct": "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfo'"}]}}
    return {"name": name, "class": "PCGGraphInputOutputSettings", "title": "",
            "settings": {"Seed": seed, "Pins": [pin], "bHasAddedDefaultPin": True}, "comment": "",
            "bubble_visible": False, "bubble_pinned": False, "inputs": [], "pin_defaults": [],
            "getter_param": "", "pos": None}


def _tag_node(name):
    return {"name": name, "class": "PCGAddTagSettings", "title": "", "settings": {"Seed": 0, "TagsToAdd": name},
            "comment": "", "bubble_visible": False, "bubble_pinned": False, "inputs": [], "pin_defaults": [],
            "getter_param": "", "pos": None}


def _assign_oracle_gen(n, only=None, overrides=None):
    """Build `/Game/PyPCG/Probe/PCG_AssignOracle_sNN` from the official IR snapshot and generate it on
    stage n's own volume (one generation; read with `{"assign": {"stage": n}}` in a later call)."""
    from pypcg import build as B, census, ir as _ir, stages
    off = _ir.load(os.path.join(_REPO, "Tools", "pypcg", "official_ir", stages.name(n) + ".json"))
    calls = [x for x in off["nodes"] if ASSIGN_SUBGRAPH in (x.get("subgraph") or "")
             and (not only or x["name"] in only)]
    if not calls:
        return {"stage": n, "abort": "this stage calls no Assign_Assets"}
    keep = set()
    for c in calls:
        keep |= _upstream(off["nodes"], c["name"])
    keep.discard("DefaultInputNode")
    by = {x["name"]: x for x in off["nodes"]}
    nodes = [_io_node("DefaultInputNode", by["DefaultInputNode"]["settings"]["Seed"], "In")]
    for name in sorted(keep):
        x = json.loads(json.dumps(by[name]))
        x["inputs"] = [{"label": p["label"], "edges": [e for e in p["edges"] if e[0] in keep]}
                       for p in x.get("inputs", [])]
        x["inputs"] = [p for p in x["inputs"] if p["edges"]]
        x["pos"] = None
        # A named-reroute usage stores its declaration as an object path inside the OFFICIAL graph;
        # the oracle must point at its own copy (build resolves {"node_ref": name}).
        for field in ("settings", "overrides", "pin_defaults"):
            if field in x:
                x[field] = _ir.node_refs_to_names(x[field], off["graph"])
        if overrides and name in overrides:
            x["overrides"] = dict(x.get("overrides") or {}, **overrides[name])
        nodes.append(x)
    taps = []
    for c in calls:
        src = next((p["edges"] for p in c["inputs"] if p["label"] == "PrimaryInput"), [])
        tin, tout = _tag_node(ORACLE_IN + c["name"]), _tag_node(ORACLE_OUT + c["name"])
        tin["inputs"] = [{"label": "In", "edges": [list(e) for e in src]}]
        tout["inputs"] = [{"label": "In", "edges": [[c["name"], "Out"]]}]
        nodes += [tin, tout]
        taps += [tin["name"], tout["name"]]
    out = _io_node("DefaultOutputNode", by["DefaultOutputNode"]["settings"]["Seed"], "Out")
    out["inputs"] = [{"label": "Out", "edges": [[t, "Out"] for t in taps]}]
    nodes.append(out)
    ir = {"schema": off["schema"], "graph": stages.name(n) + "_AssignOracle", "graph_props": {},
          "params": [p for p in off["params"]], "comment_boxes": [], "nodes": nodes, "sites": []}
    path = ORACLE_GRAPH % n
    diffs = B.build_slim(ir, path, save=True)
    if diffs:
        return {"stage": n, "abort": "oracle graph differs from its description", "diffs": [str(x) for x in diffs[:5]]}
    pc = census.component(n)
    state = json.load(open(os.path.join(_REPO, "Saved", "Reports", "v2", "_state.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(_REPO, "Saved", "Reports", "v2", "_state.json")) else {}
    pc.set_graph(unreal.EditorAssetLibrary.load_asset(path))
    shipped = state.get(stages.name(n), {})
    if shipped.get("overrides"):
        census.apply_overrides(pc, shipped["overrides"])
    if "seed" in shipped:
        pc.set_editor_property("seed", int(shipped["seed"]))
    pc.activate(True)
    pc.generate_local(True)
    return {"stage": n, "oracle": path, "nodes": len(nodes), "calls": [c["name"] for c in calls],
            "seed": int(pc.get_editor_property("seed")), "set": overrides or {}, "restore_required": True,
            "next": "{\"assign\": {\"stage\": %d}} after the generation, then gen official / restore" % n}


def _assign_oracle_compare(n, official_calls, uassets):
    """The tapped primitive against `expand_items`, or None when the volume does not hold the oracle.
    The calls and their settings are read from the oracle graph itself, so a `set` edit is compared."""
    from pypcg import census, extract, geo
    from pypcg.geo import assets as A
    from pypcg.ue import convert
    pc = census.component(n)
    g = pc.get_graph()
    if g is None or g.get_path_name().split(".")[0] != ORACLE_GRAPH % n:
        return None
    exported = extract.export(g)
    calls = assign_calls(exported)
    # The rebuilt graph names its nodes afresh, so a call is found through the tap wired to it: the
    # AddTag whose tag is `AssignOut_<official name>` reads the call's `Out`.
    renamed = {}
    for x in exported.get("nodes", []):
        tag = str((x.get("settings") or {}).get("TagsToAdd", ""))
        if tag.startswith(ORACLE_OUT):
            for p in x.get("inputs", []):
                for e in p["edges"]:
                    renamed[e[0]] = tag[len(ORACLE_OUT):]
    for c in calls:
        c["node"] = renamed.get(c["node"], c["node"])
    tabled = {e["path"]: e for e in uassets.load(sorted({p for c in calls for p in c["assets"]}))}
    taps = {}
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        tags = [str(t) for t in td.get_editor_property("tags")]
        tap = next((t for t in tags if t.startswith(ORACLE_IN) or t.startswith(ORACLE_OUT)), None)
        if tap is None:
            continue
        d = td.get_editor_property("data").get_editor_property("data")
        if isinstance(d, unreal.PCGBasePointData):
            taps.setdefault(tap, []).append(convert.points_of(d))
    rows, failures = [], []
    for call in calls:
        ins, outs = taps.get(ORACLE_IN + call["node"], []), taps.get(ORACLE_OUT + call["node"], [])
        if not ins or not outs:
            failures.append("Assign_Assets %s: the oracle tapped %d input and %d output items"
                            % (call["node"], len(ins), len(outs)))
            continue
        targets = geo.Points()
        for k, t in enumerate(ins):
            # `WriteDataIndex_1` + `AttributeMathsOp_13`: each input data item's seeds += its index,
            # then `MergePoints_0` makes one target set.
            t.seed = [A._i32(int(s) + k) for s in t.seed]
            targets.extend(t)
        table = [tabled[p] for p in call["assets"]]
        picked = outs[-1].attrs.get(A.ASSET_ATTR) or []
        index = {p: i for i, p in enumerate(call["assets"])}
        if len(picked) != len(targets) or any(p not in index for p in picked):
            failures.append("Assign_Assets %s: the output's last item does not name a kit per target "
                            "(%d targets, %d named)" % (call["node"], len(targets), len(picked)))
            continue
        ours = A.expand_items(targets, table, [index[p] for p in picked], dict(call["params"]))
        row = {"node": call["node"], "targets": len(targets), "items": [len(x) for x in outs],
               "python_items": [len(x) for x in ours], "random": bool(call.get("random")),
               "settings": call["params"]}
        if call.get("random"):
            # No TransformPoints_2 stream here: only what the random ranges cannot move is compared.
            same_items = [len(x) for x in ours] == [len(x) for x in outs]
            same_asset = same_items and all(a.attrs[A.ASSET_ATTR] == b.attrs[A.ASSET_ATTR] for a, b in zip(ours, outs))
            row.update(points=sum(len(x) for x in outs), compared="sizes, order, Asset",
                       equal={"items": same_items, "Asset": same_asset})
            if not (same_items and same_asset):
                failures.append("Assign_Assets %s (random): item sizes %s vs Python %s, Asset equal %s"
                                % (call["node"], row["items"], row["python_items"], same_asset))
            rows.append(row)
            continue
        stats = {k: {"exact": 0, "max": 0.0} for k in ("loc", "quat", "scale", "bounds")}
        same = {"Asset": 0, "seed": 0}
        total = 0
        if len(ours) == len(outs) and all(len(a) == len(b) for a, b in zip(ours, outs)):
            for a, b in zip(ours, outs):
                for i in range(len(b)):
                    total += 1
                    for k, x, y in (("loc", a.loc[i], b.loc[i]), ("scale", a.scale[i], b.scale[i]),
                                    ("bounds", tuple(a.bounds_min[i]) + tuple(a.bounds_max[i]),
                                     tuple(b.bounds_min[i]) + tuple(b.bounds_max[i]))):
                        dv = max(abs(p - q) for p, q in zip(x, y))
                        stats[k]["max"] = max(stats[k]["max"], dv)
                        stats[k]["exact"] += tuple(x) == tuple(y)
                    qa, qb = a.quat[i], b.quat[i]
                    dq = min(max(abs(p - q) for p, q in zip(qa, qb)), max(abs(p + q) for p, q in zip(qa, qb)))
                    stats["quat"]["max"] = max(stats["quat"]["max"], dq)
                    stats["quat"]["exact"] += tuple(qa) == tuple(qb)
                    same["Asset"] += a.attrs[A.ASSET_ATTR][i] == b.attrs[A.ASSET_ATTR][i]
                    same["seed"] += int(a.seed[i]) == int(b.seed[i])
            row.update(points=total, fields=stats, equal=same)
            for k in ("Asset", "seed"):
                if same[k] != total:
                    failures.append("Assign_Assets %s: %s differs on %d of %d points"
                                    % (call["node"], k, total - same[k], total))
            for k, tol in (("loc", ORACLE_LOC_TOL_CM), ("quat", ORACLE_QUAT_TOL), ("scale", 0.0), ("bounds", 0.0)):
                if stats[k]["max"] > tol:
                    failures.append("Assign_Assets %s: %s off by up to %.3g (bound %.3g)"
                                    % (call["node"], k, stats[k]["max"], tol))
        else:
            failures.append("Assign_Assets %s: item sizes %s, Python %s"
                            % (call["node"], row["items"], row["python_items"]))
        rows.append(row)
    return {"graph": ORACLE_GRAPH % n, "calls": rows, "failures": failures}


# What `_assign_oracle_compare` calls agreement. The counts, `Asset`, seed, scale and bounds must be
# exact; location and rotation carry the FTransform multiply's vectorised arithmetic, which Python's
# scalar order does not reproduce in the last bits. Measured 2026-10-19 on stage 17's one call (9 873
# points: 9 843 copies + 30 docks): location bit for bit on 9 864, the rest within 7.3e-12 cm; the
# quaternion bit for bit on 9 809, the rest within 4.4e-16; Asset, seed, scale and bounds all exact.
ORACLE_LOC_TOL_CM = 1e-9
ORACLE_QUAT_TOL = 1e-12


def _official_outputs(n):
    from pypcg import census, stages
    from pypcg.ue import convert
    pc = census.component(n)
    g = pc.get_graph()
    if g is None or g.get_path_name().split(".")[0] != stages.official_path(n):
        return None
    out = {}
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        d = td.get_editor_property("data").get_editor_property("data")
        try:
            value = convert.from_pcg(d)
        except TypeError:
            continue
        for t in td.get_editor_property("tags"):
            if ":" not in str(t):
                out.setdefault(str(t), []).append(value)
    return out


HIGHWAY_SPLINES = ("HighwaySpline2", "HighwaySpline3")


def _highway_spline_lengths():
    """The two highway spline actors' own lengths, in cm, read off the scene the graph reads. Empty
    when the stage's level does not carry them."""
    from pypcg.profiles import official
    out = []
    for role in HIGHWAY_SPLINES:
        path = official.ROLES.get(role)
        if not path:
            return []
        obj = unreal.load_object(None, path)
        if obj is None:
            return []
        comps = obj.get_components_by_class(unreal.SplineComponent)
        if not comps:
            return []
        out.append(comps[0].get_spline_length())
    return out


def published_phase(n, as_name, width_name):
    """`{"published": {"stage": n, "as": <param>, "width": <param>}}`: the LIVE volume's published
    output checked against a parameter, on the live volume rather than on a recorded run.

    Needed because stage 8's published polygon comes out of NATIVE nodes, so the recorded run holds
    the Python node's splines and never sees it: `check()`'s polygon half otherwise only runs when a
    volume happens to hold its official graph. This reads the volume's generated output as
    `pypcg.geo` values and calls the stage's own `check()`. `as_name` is the parameter the published
    AREA is measured against through the highway spline lengths (default `Highway_Width`); the
    lengths come from the volume's own inputs where the check can reach them, else from the graph.

    Stage 8 only. Returns the check's failures plus the numbers it was judged on, so the bound is
    visible even when it passes."""
    from pypcg import census, geo, stages
    from pypcg.ue import convert
    module = stages.spec(n)
    try:
        chk = importlib.import_module("pypcg.checks.s%02d" % n)
    except ImportError:
        return {"stage": n, "abort": "no checks module"}
    pc = census.component(n)
    outs = {}
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        d = td.get_editor_property("data").get_editor_property("data")
        try:
            value = convert.from_pcg(d)
        except TypeError:
            continue
        for t in td.get_editor_property("tags"):
            if ":" not in str(t):
                outs.setdefault(str(t), []).append((value, [str(t)]))
    params = {name: spec.default for name, spec in module.PARAMS.items()}
    # the volume's own instance overrides win over the declared defaults
    inst = pc.get_editor_property("graph_instance")
    over = json.loads(unreal.PyPCGToolsLibrary.export_instance_overrides(inst)) if inst else {}
    params.update({k: v for k, v in over.items() if k in params})
    # the highway spline lengths, from the stage's own recorded run when there is one
    ins = None
    run = os.path.join(_REPO, "Saved", "PyPCG", "runs", "s%02d.json" % n)
    if os.path.exists(run):
        with open(run, encoding="utf-8") as fh:
            rec = json.load(fh)
        try:
            ins = {pin: [(geo.from_json(v), frozenset(t)) for v, t in items]
                   for pin, items in rec["inputs"].items()}
        except ValueError:
            ins = None
    # the LIVE volume has no recorded input to read the spline lengths from, but the check's area
    # clause needs them; take them off the highway spline actors the graph reads, which is what the
    # recorded path measures too. Only stages whose published output is a polygon need this.
    lengths = None
    if outs.get("Highway"):
        lengths = _highway_spline_lengths()
    failures = chk.check(ins, params, outs, None)
    if lengths:
        failures += chk._published_area(outs, params.get(width_name, 0.0), ins, lengths)
    polys = [v for v in geo.values(outs.get("Highway", [])) if hasattr(v, "outer")]
    detail = {"stage": n, "volume": census.volume(n).get_actor_label(), "params": params,
              "items": {k: len(v) for k, v in outs.items()}, "inputs_recorded": ins is not None}
    if polys:
        from pypcg.stages import s08_highways
        detail["half_width_cm"] = [round(chk.half_width(p), 1) for p in polys]
        detail["area_m2"] = round(sum(geo.area_m2(p) for p in polys), 2)
        detail["published_width_cm"] = s08_highways.published_width_cm(params.get(width_name, 0.0))
        want_half = 0.5 * params.get(width_name, 0.0) + s08_highways.EXPAND_CM
        detail["want_half_width_cm"] = want_half
        detail["width_tol_cm"] = chk.WIDTH_TOL_CM
        detail["width_error_cm"] = round(max(abs(h - want_half) for h in detail["half_width_cm"]), 1)
        detail["area_tol"] = chk.PUBLISHED_AREA_TOL
        if lengths:
            want_area = s08_highways.published_width_cm(params.get(width_name, 0.0)) * sum(lengths) / 1e4
            detail["spline_length_m"] = round(sum(lengths) / 100.0, 2)
            detail["want_area_m2"] = round(want_area, 2)
            detail["area_error"] = round(100.0 * (detail["area_m2"] - want_area) / want_area, 3)
    detail["failures"] = failures[:20]
    return detail


def run_stage(args):
    from pypcg import geo, stage_api, stages
    from pypcg.ue.ops import Ops
    n = int(args["stage"])
    official = _official_outputs(n)
    d = os.path.join(_REPO, "Saved", "Reports", "v2", "s%02d" % n)
    files = sorted(f for f in os.listdir(d) if f.endswith(".run.json")) if os.path.isdir(d) else []
    if not files:
        return {"abort": "no recorded runs under %s; run V2 first" % d}
    try:
        checks = importlib.import_module("pypcg.checks.s%02d" % n)
    except ImportError:
        checks = None
    module, ops = stages.spec(n), Ops()
    failures, replayed, deterministic = [], 0, True
    for f in files:
        rec = json.load(open(os.path.join(d, f), encoding="utf-8"))
        outputs = {pin: [(geo.from_json(v), tags) for v, tags in items] for pin, items in rec["outputs"].items()
                   if all(not v.get("truncated") for v, _ in items)}
        try:
            inputs = {pin: [(geo.from_json(v), frozenset(tags)) for v, tags in items] for pin, items in rec["inputs"].items()}
        except ValueError:
            inputs = None
        if inputs is not None:
            again, _ = stage_api.execute(module, inputs, rec["params"], ops)
            replayed += 1
            same = {p: [[geo.to_json(v), list(t)] for v, t in items] for p, items in again.items()} == \
                {p: [[v, list(t)] for v, t in items] for p, items in rec["outputs"].items()}
            if not same:
                deterministic = False
                failures.append("%s: replay with the same seed gave different outputs" % f)
        if checks is not None and hasattr(checks, "check_record"):
            # A stage whose record cannot be replayed whole (a surface input, point sets over
            # MAX_RECORDED_POINTS) may check the record itself: a partial replay of what it can rebuild,
            # then its invariants (stage 10 first). It takes the place of `check`.
            failures += ["%s: %s" % (f, x) for x in checks.check_record(rec, ops, official)]
        elif checks is not None:
            failures += ["%s: %s" % (f, x) for x in checks.check(inputs, {k: v for k, v in rec["params"].items()
                                                                         if k != stage_api.SEED}, outputs, ops, official)]
    result = {"stage": n, "runs": len(files), "replayed": replayed, "deterministic": deterministic,
              "official_seen": official is not None, "failures": failures[:40]}
    # Also on disk: a slow stage (9: about 50 s) can outlast the bridge's websocket keepalive, and the
    # call then reports a closed connection although the run completed.
    with open(os.path.join(d, "v1.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    return result


try:
    _args = mcp_args or {}
    if "published" in _args:
        _pub = _args["published"]
        mcp_result = json.loads(json.dumps(published_phase(int(_pub["stage"]), _pub.get("as", "Highway_Width"),
                                                           _pub.get("width", "Highway_Width")), default=str))
    elif "assign" in _args:
        _asg = _args["assign"]
        _d = _asg if isinstance(_asg, dict) else {"stage": _args["stage"]}
        mcp_result = json.loads(json.dumps(assign_phase(int(_d["stage"]), _d.get("step"), _d.get("calls"),
                                                        _d.get("set"), _d.get("label")), default=str))
    else:
        mcp_result = json.loads(json.dumps(run_stage(_args), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
