"""tl_make_rules.py -- create RULE_TL_L00..L03 from the kit spec.

ACCESS PATH (measured directly in Task 4, confirmed against RULE_CHA_L00 and
RULE_CHA_L01 -- see task-4-report.md for the raw export_text() dumps):

  A `BP_ShapeGrammarRule_C` asset has exactly one top-level editor property,
  `rule` (an `STC_Rule` struct wrapper, Python type `StructBase`). That struct
  wrapper -- NOT the asset object itself -- exposes `export_text()` /
  `import_text()`. Calling `export_text()` on the asset object fails (UObject
  has no such method in this build); calling it on the *struct* returned by
  `asset.get_editor_property("rule")` works and returns the canonical
  `(FieldName_GUID=value,...)` text form.

  The struct's fields are never reachable through get_editor_property() on any
  dir()-listed name (dir() only lists generic struct methods), so every field
  has to be located/replaced by regex against its mangled name:

    grammar_10_4003928D40C6099DCA57829F48235D57          -- FString, the facade grammar
    ModulesInfos_38_0EA66FD04214AE8D9F6B83A1B57AC47B      -- TArray<STC_Module>

  Both mangled names were confirmed identical across RULE_CHA_L00 and
  RULE_CHA_L01 (class-level struct layout, not per-instance), matching the
  prediction in tl_facts.json's rule_grammars.read_mechanism.

  Per-module (STC_Module) fields observed in the array elements:
    Mesh_69_ABC2F260431A21DAF912F49032642918            -- soft ref to StaticMesh (omitted if no mesh)
    Symbol_6_F9FB29564DEA8BEF1EA1DD8AA30C03E3            -- FString symbol, e.g. "W1"
    Scalable_68_5F7BC934476923AF3C7BBCB6F7239ECF         -- bool, only present (=True) on scalable fillers
    Size_67_AA4253B1485ED7A89506FCA171AC20BA             -- float, cm
    PivotOffset_28_063B0B4741DD9478C20E8E83A4DFF20A      -- FVector
    MeshForwardAxis_35_62B04DFB4A4BA73267F123A1D53AC25F  -- enum, written as the literal token Y
    DebugColor_83_34BC0D8C4720597367B304B35AAFEE3F       -- FColor, cosmetic only

  FINDING that contradicts tl_facts.json / tl_kit_spec.json: both files
  describe MeshForwardAxis as "2.0 (EAxis::Z)" from the BDF numeric encoding.
  But every module in the real, working RULE_CHA_L00 and RULE_CHA_L01 assets
  writes this field as the literal token `Y`, never `Z`. Since EAxis::Type's
  ordinal 2 is actually `Y` (None=0, X=1, Y=2, Z=3), "2.0" *does* mean Y, and
  the facts/spec's own parenthetical "(EAxis::Z)" is simply mislabeled. This
  script follows the measured, working ground truth (`Y`) rather than the
  mislabeled annotation.

  PivotOffset: per the plan's explicit instruction, TL starts at (0,0,0) for
  every module -- not CHA's per-module non-zero magnitude -- and Task 6 is
  where a wrong value would be caught.

Because export_text() only serializes fields that differ from the class
default, the set of fields present varies asset-to-asset (RULE_CHA_L00 has
~15 top-level fields incl. positiononslot/RandPosRange/etc.; RULE_CHA_L01 has
only 5). Rather than fabricate a full struct from scratch, each TL rule is
created by *duplicating* an existing CHA rule of the same shape (a scaffold
that already carries a `grammar` and a `ModulesInfos` field to substitute),
then doing targeted, balanced-paren-aware text surgery on just those two
fields. Every other field (Overrideprofilegrammar, upvector,
SplineMeshangleThreshold, ...) is left exactly as the scaffold had it.

RULE_TL_L00 is a special case: the TL kit has no level-0 (foundation) meshes
at all (tl_kit_spec.json's parts start at level 1), and GRAMMARS[0] is
byte-identical to RULE_CHA_L00's own grammar. So for L00 this script only
writes the grammar field (a same-value round-trip, kept for provenance) and
leaves ModulesInfos exactly as duplicated from RULE_CHA_L00 -- i.e. it still
references CHA's borrowed NY foundation mesh, honestly, rather than
inventing TL-specific foundation content that does not exist. (Ruled
acceptable in review: Task 3 only built levels 1-3, and GRAMMARS[0] is a pure
filler row, so a borrowed foundation mesh at L00 is an acceptable placeholder
for a level the kit deliberately does not author.)

VERIFICATION: after each rule is saved, this script forces a genuine reload
from disk (unreal.EditorLoadingAndSavingUtils.reload_packages on the asset's
package, ASSUME_POSITIVE so it never blocks on a dialog under the headless
MCP bridge) and re-reads the grammar/module count from that freshly-reloaded
object -- not from the in-memory object that was just mutated. A prior run of
this script only re-fetched the mutated in-memory object, which proves
import_text()/set_editor_property() round-tripped but cannot catch a
save_loaded_asset() failure or a load-time deserialization difference; that
gap is why the disk-reload step exists. Any mismatch after reload raises.

An unmapped `part` name in the kit spec (no PART_TO_SYMBOL entry) also raises
rather than being silently skipped, so a kit that gains a new part type fails
loudly instead of quietly losing a module.
"""

import json
import re

R = {"rules": [], "errors": [], "mesh_check": {}}
args = mcp_args or {}
SPEC = args.get("spec", "E:/PCG_Claude/Tools/tl_kit/tl_kit_spec.json")
DEST = "/Game/PCG/DataAssets/Buildings/TL"

EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()

with open(SPEC, encoding="utf-8") as f:
    spec = json.load(f)

# ---------------------------------------------------------------- mangled names
GRAMMAR_FIELD = "grammar_10_4003928D40C6099DCA57829F48235D57"
MODULES_FIELD = "ModulesInfos_38_0EA66FD04214AE8D9F6B83A1B57AC47B"

# ---------------------------------------------------------------- grammar strings
# From the brief's GRAMMARS dict, taken verbatim.
GRAMMARS = {
    0: "[FC][FS2]+[LC]",
    1: "[FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]",
    2: "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
    3: "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][WS1][W1]+[LC]",
}

# ---------------------------------------------------------------- scaffolds to duplicate
CHA_BASE = "/CitySamplePCG/PCG/DataAssets/Buildings/CHA"
SCAFFOLD_CANDIDATES = {
    0: CHA_BASE + "/RULE_CHA_L00",
    1: CHA_BASE + "/RULE_CHA_L01",
    2: CHA_BASE + "/RULE_CHA_L02",
    3: CHA_BASE + "/RULE_CHA_L03",
}
SCAFFOLD_FALLBACK = {3: CHA_BASE + "/RULE_CHA_L02"}


# ---------------------------------------------------------------- text-surgery helpers
def find_field_span(text, mangled_name):
    """Return (value_start, value_end) for a field's value text, handling a
    quoted-string value, a parenthesized (possibly nested) value, or a bare
    token/number value. None if the field is not present."""
    key = mangled_name + "="
    idx = text.find(key)
    if idx == -1:
        return None
    vstart = idx + len(key)
    if vstart >= len(text):
        return None
    ch = text[vstart]
    if ch == '"':
        end = text.find('"', vstart + 1)
        if end == -1:
            return None
        return (vstart, end + 1)
    if ch == '(':
        depth = 0
        i = vstart
        n = len(text)
        while i < n:
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
                if depth == 0:
                    return (vstart, i + 1)
            i += 1
        return None
    # bare token/number: runs until a top-level comma or closing paren
    i = vstart
    n = len(text)
    while i < n and text[i] not in ',)':
        i += 1
    return (vstart, i)


def extract_field_value(text, mangled_name):
    span = find_field_span(text, mangled_name)
    if span is None:
        return None
    v = text[span[0]:span[1]]
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return v[1:-1]
    return v


def replace_field(text, mangled_name, new_value_text):
    span = find_field_span(text, mangled_name)
    if span is None:
        raise RuntimeError("field not found: %s" % mangled_name)
    return text[:span[0]] + new_value_text + text[span[1]:]


def count_top_level_entries(array_inner_text):
    """Count direct-child (...) groups in the (already-unwrapped) inner text
    of an array field's value."""
    depth = 0
    count = 0
    for c in array_inner_text:
        if c == '(':
            if depth == 0:
                count += 1
            depth += 1
        elif c == ')':
            depth -= 1
    return count


# ---------------------------------------------------------------- module-array building
PART_TO_SYMBOL = {
    "Wall_01": "W1", "Column_01": "P1", "Column_02": "P2",
    "Entrance_01": "E1", "CornerEx_01": "C_CE", "CornerExL_01": "C_SL",
    "CornerExR_01": "C_SR", "CornerIn_01": "C_I", "CornerInL_01": "C_IL",
    "CornerInR_01": "C_IR",
}

# cosmetic only -- matched to CHA's own per-symbol debug colors where the
# symbol exists there, invented for the one TL-only symbol (P2)
SYMBOL_COLOR = {
    "W1": (0, 255, 255), "WS1": (0, 255, 255),
    "P1": (241, 0, 255), "P2": (200, 150, 255),
    "E1": (0, 0, 255),
    "C_CE": (255, 255, 0), "C_SL": (255, 255, 0), "C_SR": (255, 255, 0),
    "C_I": (255, 255, 0), "C_IL": (255, 255, 0), "C_IR": (255, 255, 0),
}


def mesh_asset_path(level, mesh_name):
    return "/Game/Building/TL/A/Kit_Bldg_TL_L%d_A/Mesh/%s" % (level, mesh_name)


def build_module_entry(symbol, mesh_path, size_cm, scalable):
    b, g, r = SYMBOL_COLOR.get(symbol, (128, 128, 128))
    fields = []
    fields.append('Mesh_69_ABC2F260431A21DAF912F49032642918="/Script/Engine.StaticMesh\'%s.%s\'"'
                  % (mesh_path, mesh_path.rsplit("/", 1)[-1]))
    fields.append('Symbol_6_F9FB29564DEA8BEF1EA1DD8AA30C03E3="%s"' % symbol)
    if scalable:
        fields.append('Scalable_68_5F7BC934476923AF3C7BBCB6F7239ECF=True')
    fields.append('Size_67_AA4253B1485ED7A89506FCA171AC20BA=%.6f' % size_cm)
    fields.append('PivotOffset_28_063B0B4741DD9478C20E8E83A4DFF20A=(X=0.000000,Y=0.000000,Z=0.000000)')
    fields.append('MeshForwardAxis_35_62B04DFB4A4BA73267F123A1D53AC25F=Y')
    fields.append('DebugColor_83_34BC0D8C4720597367B304B35AAFEE3F=(B=%d,G=%d,R=%d,A=255)' % (b, g, r))
    return "(" + ",".join(fields) + ")"


def build_modules_array_text(level):
    parts = [p for p in spec["parts"] if p["level"] == level]
    entries = []
    missing = []
    unmapped = []
    wall_part = None
    for p in parts:
        sym = PART_TO_SYMBOL.get(p["part"])
        if sym is None:
            # Fail loudly rather than silently dropping a module: a kit that
            # gains a new part type must not quietly lose a module here.
            unmapped.append(p["part"])
            continue
        path = mesh_asset_path(level, p["mesh_name"])
        if not EAL.does_asset_exist(path):
            missing.append(path)
        entries.append(build_module_entry(sym, path, p["width_m"] * 100.0, False))
        if p["part"] == "Wall_01":
            wall_part = p
    if unmapped:
        raise RuntimeError("unmapped part name(s) with no PART_TO_SYMBOL entry: %s" % sorted(set(unmapped)))
    if wall_part is not None:
        path = mesh_asset_path(level, wall_part["mesh_name"])
        entries.append(build_module_entry("WS1", path, wall_part["width_m"] * 100.0, True))
    return "(" + ",".join(entries) + ")", missing, len(entries)


# ---------------------------------------------------------------- main
for level in (0, 1, 2, 3):
    name = "RULE_TL_L%02d" % level
    dest_path = DEST + "/" + name
    rec = {"name": name, "dest_path": dest_path}
    try:
        if EAL.does_asset_exist(dest_path):
            asset = EAL.load_asset(dest_path)
            rec["created_via"] = "already_existed"
        else:
            scaffold_path = SCAFFOLD_CANDIDATES[level]
            if not EAL.does_asset_exist(scaffold_path) and level in SCAFFOLD_FALLBACK:
                scaffold_path = SCAFFOLD_FALLBACK[level]
            src = EAL.load_asset(scaffold_path)
            if src is None:
                raise RuntimeError("scaffold not found/loadable: %s" % scaffold_path)
            asset = AT.duplicate_asset(name, DEST, src)
            if asset is None:
                raise RuntimeError("duplicate_asset returned None (scaffold=%s)" % scaffold_path)
            rec["created_via"] = "duplicated_from_" + scaffold_path

        rule = asset.get_editor_property("rule")
        txt = rule.export_text()

        target_grammar = GRAMMARS[level]
        new_txt = replace_field(txt, GRAMMAR_FIELD, '"%s"' % target_grammar)

        if level == 0:
            rec["modules_written"] = False
            rec["modules_note"] = "no TL level-0 kit exists; ModulesInfos left as duplicated from scaffold"
        else:
            modules_text, missing, n_entries = build_modules_array_text(level)
            if missing:
                raise RuntimeError("missing mesh assets: %s" % missing)
            new_txt = replace_field(new_txt, MODULES_FIELD, modules_text)
            rec["modules_written"] = True
            rec["module_count_written"] = n_entries

        rule.import_text(new_txt)
        asset.set_editor_property("rule", rule)

        # in-memory sanity check: fetch a NEW struct proxy from the asset,
        # not the one we just mutated, and export it again. This proves
        # import_text() -> set_editor_property() round-tripped in memory, but
        # it CANNOT catch a save_loaded_asset() failure or a load-time
        # deserialization difference, because it never leaves the process's
        # live object -- see the genuine disk-reload check below for that.
        rule2 = asset.get_editor_property("rule")
        txt2 = rule2.export_text()
        rec["grammar_written"] = target_grammar
        rec["grammar_in_memory"] = extract_field_value(txt2, GRAMMAR_FIELD)

        mspan = find_field_span(txt2, MODULES_FIELD)
        if mspan is not None:
            inner = txt2[mspan[0] + 1:mspan[1] - 1]
            rec["module_count_in_memory"] = count_top_level_entries(inner)
        else:
            rec["module_count_in_memory"] = 0

        saved_ok = EAL.save_loaded_asset(asset)
        rec["saved_ok"] = bool(saved_ok)
        if not saved_ok:
            raise RuntimeError("EAL.save_loaded_asset returned falsy for %s" % dest_path)

        # ---- genuine disk round-trip: force the package to reload from the
        # .uasset that was just written, then re-read the rule struct from
        # that freshly-reloaded object. ASSUME_POSITIVE avoids any editor
        # dialog (this runs headless via the MCP bridge) while still doing a
        # real reload rather than a no-op.
        pkg = asset.get_outermost()
        reloaded, reload_err = unreal.EditorLoadingAndSavingUtils.reload_packages(
            [pkg], unreal.ReloadPackagesInteractionMode.ASSUME_POSITIVE
        )
        rec["disk_reload_attempted"] = bool(reloaded)
        rec["disk_reload_error"] = str(reload_err) if reload_err else ""

        asset_fresh = EAL.load_asset(dest_path)
        if asset_fresh is None:
            raise RuntimeError("post-reload load_asset returned None for %s" % dest_path)
        rule_fresh = asset_fresh.get_editor_property("rule")
        txt_fresh = rule_fresh.export_text()

        rec["grammar_read_back"] = extract_field_value(txt_fresh, GRAMMAR_FIELD)
        rec["grammar_ok"] = (rec["grammar_read_back"] == target_grammar)
        if not rec["grammar_ok"]:
            raise RuntimeError(
                "grammar did not survive disk reload for %s: wrote %r, read back %r"
                % (dest_path, target_grammar, rec["grammar_read_back"])
            )

        mspan_fresh = find_field_span(txt_fresh, MODULES_FIELD)
        if mspan_fresh is not None:
            inner_fresh = txt_fresh[mspan_fresh[0] + 1:mspan_fresh[1] - 1]
            rec["module_count_read_back"] = count_top_level_entries(inner_fresh)
        else:
            rec["module_count_read_back"] = 0

        if rec.get("modules_written") and rec["module_count_read_back"] != rec["module_count_written"]:
            raise RuntimeError(
                "module count did not survive disk reload for %s: wrote %d, read back %d"
                % (dest_path, rec["module_count_written"], rec["module_count_read_back"])
            )

        R["rules"].append(rec)
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
        R["errors"].append(rec)

print(json.dumps(R, indent=1, default=str))
mcp_result = R
