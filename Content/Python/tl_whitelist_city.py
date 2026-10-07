# tl_whitelist_city.py -- add TL to the city buildings stage's style whitelist.
#
# PCG_3_3_1_Buildings calls Assign_CitySampleBuildings three times (Small,
# Medium, Large districts). Each call overrides the subgraph's BuildingsStyles
# parameter on its subgraph_instance with an explicit style list, so the
# subgraph's own default (set by tl_register.py) is never used. TL goes into
# the Medium list: the 19-code general list that CHA, whose level heights TL
# follows, belongs to.
#
# The graph lives in the gitignored plugin content. A file copy is taken under
# Saved/ before the first save; E:/CitySample 5.8 holds a byte-identical copy.
#
# Args: {"apply": true} to write; default is a dry run.

import json
import os
import shutil

GRAPH = "/CitySamplePCG/Levels/PCG/PCG_3_3_1_Buildings"
DISK = "E:/PCG_Claude/Plugins/CitySamplePCG/Content/Levels/PCG/PCG_3_3_1_Buildings.uasset"
BACKUP = "E:/PCG_Claude/Saved/TL_backups/PCG_3_3_1_Buildings.uasset"
TARGET_NODES = ("Assign City Sample Buildings - Medium",)
PARAM = "BuildingsStyles"
CODE = "TL"


def node_title(n):
    try:
        t = n.get_editor_property("node_title")
        if t and str(t) != "None":
            return str(t)
    except Exception:
        pass
    return n.get_name()


def assign_nodes(g):
    out = {}
    for n in g.get_editor_property("nodes"):
        s = n.get_settings()
        if s is None or "Subgraph" not in s.get_class().get_name():
            continue
        inst = s.get_editor_property("subgraph_instance")
        if inst is None:
            continue
        sg = inst.get_editor_property("graph")
        if sg is None or not sg.get_path_name().endswith("Assign_CitySampleBuildings"):
            continue
        out[node_title(n)] = inst
    return out


def read_lists(g):
    H = unreal.PCGGraphParametersHelpers
    return {t: H.get_string_parameter(i, PARAM) for t, i in assign_nodes(g).items()}


def main(apply):
    R = {"apply": apply, "errors": []}
    EAL = unreal.EditorAssetLibrary
    H = unreal.PCGGraphParametersHelpers
    g = EAL.load_asset(GRAPH)
    if g is None:
        R["errors"].append("graph not loadable")
        return R
    R["before"] = read_lists(g)
    nodes = assign_nodes(g)
    missing = [t for t in TARGET_NODES if t not in nodes]
    if missing:
        R["errors"].append("target nodes not found: %s" % missing)
        return R

    plan = {}
    for t in TARGET_NODES:
        current = H.get_string_parameter(nodes[t], PARAM)
        if current == "":
            # An empty override means "all styles". Appending TL here would
            # produce "TL", which narrows the call to TL alone instead of
            # widening it -- refuse rather than silently breaking the call.
            R["errors"].append(
                "%s: %s is empty (means 'all styles'); appending TL would "
                "narrow the call to TL alone -- refusing, fix by hand"
                % (t, PARAM))
            continue
        codes = [c for c in current.split(",") if c]
        if CODE not in codes:
            plan[t] = ",".join(codes + [CODE])
    R["plan"] = plan
    if R["errors"]:
        return R
    if not apply or not plan:
        R["note"] = "dry run" if not apply else "already contains TL"
        return R

    if not os.path.exists(BACKUP):
        os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
        shutil.copy2(DISK, BACKUP)
    R["backup"] = {"path": BACKUP, "bytes": os.path.getsize(BACKUP),
                   "src_bytes_before": os.path.getsize(DISK)}

    g.modify()
    for t, value in plan.items():
        nodes[t].modify()
        H.set_string_parameter(nodes[t], PARAM, value)
    R["saved"] = EAL.save_asset(GRAPH, only_if_is_dirty=False)
    R["disk_bytes_after"] = os.path.getsize(DISK)
    R["after"] = read_lists(g)
    R["overridden_after"] = {t: H.is_overridden(nodes[t], PARAM) for t in TARGET_NODES}
    for t in TARGET_NODES:
        if CODE not in R["after"][t].split(","):
            R["errors"].append("%s does not contain TL after the write" % t)
    return R


R = main(bool((mcp_args or {}).get("apply")))
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
