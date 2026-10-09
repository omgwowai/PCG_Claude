# tl_probe_tl_props.py -- READ-ONLY. TL's Props rows as stored in BDF_WithTL,
# and the HasProps flag on TL's module rows.
import json

MA = unreal.PCGMetadataAccessorHelpers


def main():
    a = unreal.EditorAssetLibrary.load_asset("/Game/PCG/DataAssets/BDF/BDF_WithTL")
    out = {"props": [], "modules_with_props": []}
    for it in a.get_editor_property("data").get_editor_property("tagged_data"):
        tags = [str(t) for t in it.get_editor_property("tags")]
        d = it.get_editor_property("data").get_editor_property("data")
        md = d.mutable_metadata()
        for pt in d.get_points():
            if MA.get_string_attribute(pt, md, "BuildingToken") != "TL":
                continue
            if "Props" in tags:
                out["props"].append({
                    "mod": MA.get_string_attribute(pt, md, "ModuleName")[17:],
                    "group": MA.get_string_attribute(pt, md, "PropGroup"),
                    "type": MA.get_string_attribute(pt, md, "Type"),
                    "mesh": MA.get_soft_object_path_attribute(pt, md, "Mesh").export_text().rsplit(".", 1)[-1],
                    "win": MA.get_bool_attribute(pt, md, "WindowHelper"),
                    "parent": MA.get_integer64_attribute(pt, md, "ParentIndex"),
                    "actor": MA.get_integer64_attribute(pt, md, "ActorIndex"),
                    "loc": [round(v, 1) for v in pt.transform.translation.to_tuple()],
                    "bmin": [round(v, 1) for v in pt.get_editor_property("bounds_min").to_tuple()],
                    "bmax": [round(v, 1) for v in pt.get_editor_property("bounds_max").to_tuple()]})
            elif "Modules" in tags and MA.get_bool_attribute(pt, md, "HasProps"):
                out["modules_with_props"].append(MA.get_string_attribute(pt, md, "Mod_Name"))
    return out


mcp_result = json.loads(json.dumps(main(), default=str))
