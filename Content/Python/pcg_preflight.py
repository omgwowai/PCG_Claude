# pcg_preflight.py — PCG capability probe for PCG_Claude
#
# READ-ONLY. Creates nothing, modifies nothing, saves nothing.
# Safe to run any time; the first thing to run in a PCG session.
#
# Purpose: the API surface this project can reach must be discovered, not assumed.
# This reports what actually exists so later scripts are written against reality.
#
# Run via the MCP bridge:
#   run_unreal_script(script_path="pcg_preflight.py")
#
# Findings come back under `return:` (from mcp_result) and `stdout:` (from print).

import json

report = {}


def _members(obj):
    """Public member names of a class or module, sorted."""
    try:
        return sorted(m for m in dir(obj) if not m.startswith("_"))
    except Exception as e:  # pragma: no cover - defensive
        return ["<error: %s>" % e]


# --- 1. Is the PCG plugin actually loaded? -----------------------------------
# If PCG was just enabled in the .uproject, the editor must be restarted first.
report["pcg_loaded"] = hasattr(unreal, "PCGGraph") or hasattr(unreal, "PCGComponent")
if not report["pcg_loaded"]:
    report["verdict"] = (
        "PCG is NOT loaded. Either PCG/PCGPrimitives are not enabled in "
        "PCG_Claude.uproject, or the editor has not been restarted since enabling them. "
        "Everything below this line is meaningless until that is fixed."
    )
    print(report["verdict"])
else:
    report["verdict"] = "PCG is loaded; probe results below are meaningful."

# --- 2. Every script-visible name containing PCG ------------------------------
pcg_names = sorted(n for n in dir(unreal) if "PCG" in n)
report["pcg_name_count"] = len(pcg_names)
report["pcg_names"] = pcg_names

# --- 3. The graph mutation surface -------------------------------------------
# These are the calls that matter for authoring. Report exactly what exists so
# nobody writes a call that cannot bind.
graph_api = {}
if hasattr(unreal, "PCGGraph"):
    graph_api = _members(unreal.PCGGraph)
report["PCGGraph_members"] = graph_api

# Specifically check the authoring entry points by name.
for fn in ("add_node_of_type", "add_node_instance", "add_node_copy",
           "add_edge", "remove_edge", "remove_node",
           "get_input_node", "get_output_node", "get_all_edges"):
    report["has_graph_" + fn] = fn in graph_api

# --- 4. Node settings classes = the node palette ------------------------------
# add_node_of_type needs a UPCGSettings subclass. If none are script-visible,
# programmatic authoring is not viable and the approach must change.
settings = sorted(n for n in pcg_names if n.endswith("Settings"))
report["settings_class_count"] = len(settings)
report["settings_classes"] = settings

# --- 5. Component: generation and result inspection ---------------------------
if hasattr(unreal, "PCGComponent"):
    comp = _members(unreal.PCGComponent)
    report["PCGComponent_members"] = comp
    for fn in ("generate_local", "cleanup_local", "generate", "cleanup",
               "set_graph", "get_generated_graph_output"):
        report["has_component_" + fn] = fn in comp
else:
    report["PCGComponent_members"] = ["<unreal.PCGComponent not found>"]

# --- 6. Result-reading types --------------------------------------------------
# Without the PCGToolset's GetNodeDataView (not available in this project),
# verifying output means reading these. Report what is reachable.
for cls in ("PCGData", "PCGPointData", "PCGPoint", "PCGDataCollection",
            "PCGVolume", "PCGGraphInstance", "PCGGraphInterface"):
    report["has_" + cls] = hasattr(unreal, cls)

# --- 7. Is the primitives library mounted? ------------------------------------
# PCGPrimitives is content-only; its subgraphs live at /PCGPrimitives/.
dirs = {
    "/PCGPrimitives/Primitives": "primitives library (the node vocabulary)",
    "/PCGPrimitives/Examples": "example graphs",
    "/PCGPrimitives/Instants": "instant graphs",
    "/PCGPrimitives/Grammar": "shape grammar assets",
    "/Game": "project content (should already exist)",
}
mounted = {}
for d, label in dirs.items():
    try:
        mounted[d] = {"exists": bool(unreal.EditorAssetLibrary.does_directory_exist(d)),
                      "what": label}
    except Exception as e:
        mounted[d] = {"exists": None, "what": label, "error": str(e)}
report["mounts"] = mounted

# --- 8. Does this project already have PCG content of its own? ----------------
try:
    own = unreal.EditorAssetLibrary.list_assets("/Game", recursive=True, include_folder=False)
    own_pcg = [a for a in own if "PCG" in a]
    report["project_own_pcg_assets_count"] = len(own_pcg)
    report["project_own_pcg_assets_sample"] = own_pcg[:20]
except Exception as e:
    report["project_own_pcg_assets_count"] = None
    report["project_own_pcg_assets_error"] = str(e)

# --- 9. Human-readable verdict -------------------------------------------------
lines = []
lines.append("PCG loaded: %s" % report["pcg_loaded"])
lines.append("script-visible PCG names: %d" % report["pcg_name_count"])
lines.append("settings (node) classes: %d" % report["settings_class_count"])
lines.append("PCGGraph.add_node_of_type present: %s" % report.get("has_graph_add_node_of_type"))
lines.append("PCGGraph.add_edge present: %s" % report.get("has_graph_add_edge"))
lines.append("PCGComponent.generate_local present: %s" % report.get("has_component_generate_local"))
lines.append("PCGComponent.get_generated_graph_output present: %s"
             % report.get("has_component_get_generated_graph_output"))
for d, info in mounted.items():
    lines.append("mount %-32s exists=%s  (%s)" % (d, info.get("exists"), info.get("what")))
lines.append("project's own PCG assets: %s" % report["project_own_pcg_assets_count"])
print("\n".join(lines))

mcp_result = report
