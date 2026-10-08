# tl_import_kit.py -- superseded by tl_kit_rebuild_meshes.py.
#
# Legacy FBX reimport over an existing mesh appends new material slots instead
# of reusing ones with matching names, and deleting a mesh first force-nulls
# the references BDF_WithTL, RULE_TL_* and generated level output hold to it.
# tl_kit_rebuild_meshes.py imports into a scratch folder and copies the LOD0
# geometry onto the existing asset, which keeps every path and reference.
raise RuntimeError("tl_import_kit.py is superseded: run tl_kit_rebuild_meshes.py")
