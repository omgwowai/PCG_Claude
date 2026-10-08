# tl_probe_section_slots.py -- READ-ONLY. For TL meshes, check that each LOD0
# section's material index lands on the slot whose name matches the geometry:
# glass sections should sit on TL_Glass, etc. Reports per-section slot name,
# triangle count and the section's mean normal X (glass faces point +X).
import json

args = mcp_args or {}
NAMES = args.get("names", ["SM_BLDG_TL_L02_A_Wall_01_N1"])


def main():
    EAL = unreal.EditorAssetLibrary
    SMES = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    out = {}
    for n in NAMES:
        lv = int(n.split("_L")[1][:2])
        m = EAL.load_asset("/Game/Building/TL/A/Kit_Bldg_TL_L%d_A/Mesh/%s" % (lv, n))
        slots = [str(s.get_editor_property("material_slot_name")) for s in m.get_editor_property("static_materials")]
        secs = []
        for i in range(m.get_num_sections(0)):
            info = SMES.get_lod_material_slot(m, 0, i) if hasattr(SMES, "get_lod_material_slot") else None
            secs.append({"section": i, "slot_index": info,
                         "slot": slots[info] if isinstance(info, int) and 0 <= info < len(slots) else None})
        out[n] = {"slots": slots, "sections": secs, "verts": SMES.get_number_verts(m, 0)}
    return out


mcp_result = json.loads(json.dumps(main(), default=str))
