# tl_probe_hasprops_symbols.py -- READ-ONLY. Which module symbols carry
# HasProps=True in BDF_WithTL, per style (CHA plus a few siblings and TL), and
# whether a mesh with both a C_CE and a C_E row flags both or only one.
import json

MA = unreal.PCGMetadataAccessorHelpers
STYLES = ("CHA", "CHB", "CHJ", "NYA", "TL")


def main():
    a = unreal.EditorAssetLibrary.load_asset("/Game/PCG/DataAssets/BDF/BDF_WithTL")
    out = {s: {} for s in STYLES}
    by_mesh = {s: {} for s in STYLES}
    for it in a.get_editor_property("data").get_editor_property("tagged_data"):
        if "Modules" not in [str(t) for t in it.get_editor_property("tags")]:
            continue
        d = it.get_editor_property("data").get_editor_property("data")
        md = d.mutable_metadata()
        for pt in d.get_points():
            s = MA.get_string_attribute(pt, md, "BuildingToken")
            if s not in out:
                continue
            sym = MA.get_string_attribute(pt, md, "Symbol")
            hp = MA.get_bool_attribute(pt, md, "HasProps")
            k = out[s].setdefault(sym, [0, 0])
            k[0 if hp else 1] += 1
            mesh = MA.get_string_attribute(pt, md, "Mod_Name")
            by_mesh[s].setdefault(mesh, []).append("%s:%s" % (sym, "P" if hp else "-"))
    corner_meshes = {s: {m: v for m, v in ms.items() if any(x.startswith("C_E:") for x in v)
                         and any(x.startswith("C_CE:") for x in v)}
                     for s, ms in by_mesh.items()}
    return {"symbol_hasprops_[true,false]": out,
            "meshes_with_C_CE_and_C_E": {s: dict(list(v.items())[:6]) for s, v in corner_meshes.items()}}


mcp_result = json.loads(json.dumps(main(), default=str))
