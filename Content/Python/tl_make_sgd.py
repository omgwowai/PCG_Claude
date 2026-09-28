"""tl_make_sgd.py -- create SGD_TL_A binding RULE_TL_L00..L03 into a 4-level
shape-grammar definition, by duplicating SGD_CHA_A and rebinding.

ACCESS PATHS (measured directly in this task's Step 1 probe, against the
real SGD_CHA_A -- see task-5-report.md for the raw dumps):

  A `BP_ShapeGrammarDefinition_C` asset's TOP-LEVEL properties -- "Main
  Grammar" (str), "Use Grammar" (bool), "Description" (str), "Slots"
  (TArray<STC_Slot>) -- are all reachable directly via get_editor_property()/
  set_editor_property(), using their literal DISPLAY names: Title Case,
  WITH THE SPACE (e.g. "Main Grammar", not "main_grammar" or "MainGrammar").
  No mangled GUID suffix and no export_text()/import_text() round-trip is
  needed at this level at all.

  *** This CONTRADICTS the brief's Step 1 framing ***, which stated flatly
  that "the SGD class itself exposes no main_grammar-style property at all"
  and that dir() shows "nothing grammar-shaped". Both of those statements
  are true only for snake_case/PascalCase spellings without a space --
  dir() indeed lists no such attribute (dir() only ever shows generic
  UDataAsset/editor-property plumbing, since Python's dir() does not
  enumerate UPROPERTY reflection data), but get_editor_property("Main
  Grammar") (title case, with the literal space) succeeds immediately and
  returns "L00, L01, L02, L03, L04, L05, L06*, L07, L08, L09*, L10, L20" --
  a plain FString, no export_text() needed. Task 1's finding that "the SGD
  class exposes no main_grammar-style property at all" is corrected here:
  it does, just not under a name dir() will surface or that a snake_case
  guess would hit, and it needs no text-surgery workaround.

  The mangled-struct-field problem DOES apply, but only ONE level down --
  inside the STC_Slot struct that fills the Slots array, exactly as the
  brief predicted for that one field:

    ShapeGrammarRules_42_0CB868434643776AF184F78028144928
        -- TArray<BP_ShapeGrammarRule_C> (soft ref, one element per slot in
           every SGD_CHA_A slot observed). Confirmed identical mangled name
           across all 12 SGD_CHA_A slots (class-level struct layout).

  *** This ALSO goes further than the brief's fallback plan (export_text()/
  import_text() text surgery, the same technique tl_make_rules.py used for
  STC_Rule) ***: get_editor_property()/set_editor_property() work DIRECTLY
  on the slot struct using that exact mangled name string as the property
  name -- e.g. slot.get_editor_property("ShapeGrammarRules_42_...") returns
  a live unreal.Array of the bound RULE object(s), and
  slot.set_editor_property("ShapeGrammarRules_42_...", [new_rule_obj])
  rebinds it, both confirmed by direct probe on scratch/copied structs
  before this script touched anything real. So NO text surgery
  (export_text()/import_text()) is used anywhere in this script; every
  field is read and written through get_editor_property()/
  set_editor_property() using the names above. export_text() is used only
  for the human-readable dumps in this script's report output, never as
  part of the write path.

  Other STC_Slot fields also work under their clean snake_case names:
  "symbol" (str), "size" (float, cm -- confirmed to equal the level's
  height: SGD_CHA_A's L01/L02/L03 slots read 500.0/300.0/300.0, which are
  exactly TL's own kit heights of 5.0m/3.0m/3.0m x100 from
  tl_kit_spec.json), "mirror" (bool), "scalable" (bool) -- EXCEPT
  "iscorner", which -- like the rule-binding field -- IS mangled-only
  (iscorner_37_537B72C44F41655DFBC568871556A218; get/set_editor_property
  ("iscorner", ...) raises "Failed to find property"). This script never
  needs to touch iscorner/offset/mirror/scalable/size directly: because it
  builds SGD_TL_A by DUPLICATING SGD_CHA_A (the same scaffolding approach
  tl_make_rules.py used for the RULE assets) and then truncating to 4 slots
  and rebinding only the rule reference, every other per-slot field
  (symbol, size, offset, mirror, scalable, iscorner) is inherited byte-for-
  byte from CHA's own L00-L03 slots -- which is exactly right, since TL's
  own L01-L03 kit heights are numerically identical to CHA's (confirmed
  above) and L00 is TL's known borrowed-placeholder level (no TL-specific
  foundation content exists; RULE_TL_L00 itself borrows CHA's L00 module
  set, per tl_make_rules.py's own documented ruling).

VERIFICATION: after saving, this script forces a genuine reload from disk
(unreal.EditorLoadingAndSavingUtils.reload_packages, ASSUME_POSITIVE, gated
on the reload's own success flag -- exactly tl_make_rules.py's pattern) and
re-reads Main Grammar / Use Grammar / Slots / each slot's rule binding from
that freshly-reloaded object, not the in-memory object just mutated. It also
re-reads SGD_CHA_A's own fields in the same run, for a same-script,
same-mechanism comparison (Step 3 of the brief).
"""

import json

R = {"steps": {}, "errors": []}
EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()

CHA_SGD_PATH = "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/SGD_CHA_A"
DEST_DIR = "/Game/PCG/DataAssets/Buildings/TL"
DEST_NAME = "SGD_TL_A"
DEST_PATH = DEST_DIR + "/" + DEST_NAME
RULE_MANGLED = "ShapeGrammarRules_42_0CB868434643776AF184F78028144928"
TL_RULES = {
    0: "/Game/PCG/DataAssets/Buildings/TL/RULE_TL_L00",
    1: "/Game/PCG/DataAssets/Buildings/TL/RULE_TL_L01",
    2: "/Game/PCG/DataAssets/Buildings/TL/RULE_TL_L02",
    3: "/Game/PCG/DataAssets/Buildings/TL/RULE_TL_L03",
}
TARGET_MAIN_GRAMMAR = "L00, L01, L02, L03"
TARGET_DESCRIPTION = "TL building - 4 levels, medium facade variant."


def read_sgd_fields(sgd_obj, label):
    """Read the fields this script cares about off a loaded SGD object,
    using the clean-but-spaced top-level names and the mangled per-slot
    rule-binding name. Returns a plain, JSON-safe dict."""
    out = {"label": label}
    out["main_grammar"] = sgd_obj.get_editor_property("Main Grammar")
    out["use_grammar"] = sgd_obj.get_editor_property("Use Grammar")
    out["description"] = sgd_obj.get_editor_property("Description")
    slots = sgd_obj.get_editor_property("Slots")
    out["slot_count"] = len(slots)
    slot_info = []
    for s in slots:
        sym = str(s.get_editor_property("symbol"))
        bound = s.get_editor_property(RULE_MANGLED)
        bound_paths = [b.get_path_name() for b in bound]
        slot_info.append({
            "symbol": sym,
            "size": s.get_editor_property("size"),
            "bound_rule_paths": bound_paths,
        })
    out["slots"] = slot_info
    return out


# ---------------------------------------------------------------- Step 1 (recap)
# Probe already run interactively (tl_probe_sgd*.py, deleted after folding
# findings into this docstring and this report). Re-derive the same facts
# here so this script's own output is self-contained evidence, and so Step 3
# (compare against the known-good asset) runs from the same mechanism.
try:
    cha_sgd = EAL.load_asset(CHA_SGD_PATH)
    if cha_sgd is None:
        raise RuntimeError("could not load %s" % CHA_SGD_PATH)
    cha_read = read_sgd_fields(cha_sgd, "SGD_CHA_A (reference, untouched)")
    cha_slot0 = cha_sgd.get_editor_property("Slots")[0]
    cha_read["slot0_export_text"] = cha_slot0.export_text()
    R["steps"]["step1_probe_recap"] = cha_read
except Exception as e:
    R["errors"].append("step1_probe_recap: %s: %s" % (type(e).__name__, e))
    cha_sgd = None

# ---------------------------------------------------------------- Step 2: build
try:
    if cha_sgd is None:
        raise RuntimeError("cannot build without a loaded SGD_CHA_A scaffold")

    if EAL.does_asset_exist(DEST_PATH):
        asset = EAL.load_asset(DEST_PATH)
        created_via = "already_existed"
    else:
        asset = AT.duplicate_asset(DEST_NAME, DEST_DIR, cha_sgd)
        if asset is None:
            raise RuntimeError("duplicate_asset returned None for %s" % DEST_PATH)
        created_via = "duplicated_from_" + CHA_SGD_PATH
    R["steps"]["created_via"] = created_via

    # Truncate to the first 4 slots (L00-L03), each a deep copy so mutating
    # one does not alias another (STC_Slot is a value-type struct; .copy()
    # matches the pattern already proven safe in the probe).
    src_slots = asset.get_editor_property("Slots")
    if len(src_slots) < 4:
        raise RuntimeError("scaffold has only %d slots, need >=4" % len(src_slots))
    new_slots = [src_slots[i].copy() for i in range(4)]

    # Sanity: confirm the first 4 scaffold slots really are L00..L03 in
    # order before rebinding purely by index.
    got_symbols = [str(s.get_editor_property("symbol")) for s in new_slots]
    expected_symbols = ["L00", "L01", "L02", "L03"]
    if got_symbols != expected_symbols:
        raise RuntimeError(
            "scaffold's first 4 slots are %r, expected %r -- refusing to "
            "rebind by index against an unexpected slot order"
            % (got_symbols, expected_symbols)
        )

    # Rebind each slot's rule reference to the matching RULE_TL_L0n.
    rebind_report = []
    for i in range(4):
        rule_path = TL_RULES[i]
        rule_obj = EAL.load_asset(rule_path)
        if rule_obj is None:
            raise RuntimeError("could not load %s" % rule_path)
        new_slots[i].set_editor_property(RULE_MANGLED, [rule_obj])
        bound_now = new_slots[i].get_editor_property(RULE_MANGLED)
        rebind_report.append({
            "slot_index": i,
            "symbol": got_symbols[i],
            "rebound_to": rule_path,
            "in_memory_readback": [b.get_path_name() for b in bound_now],
        })
    R["steps"]["rebind_in_memory"] = rebind_report

    asset.set_editor_property("Slots", new_slots)
    asset.set_editor_property("Main Grammar", TARGET_MAIN_GRAMMAR)
    asset.set_editor_property("Use Grammar", True)
    asset.set_editor_property("Description", TARGET_DESCRIPTION)

    # In-memory sanity read (NOT evidence the save landed -- see disk-reload
    # gate below, same distinction Task 4's review established).
    R["steps"]["in_memory_after_set"] = read_sgd_fields(asset, "SGD_TL_A (in-memory, just mutated)")

    saved_ok = EAL.save_loaded_asset(asset)
    R["steps"]["saved_ok"] = bool(saved_ok)
    if not saved_ok:
        raise RuntimeError("EAL.save_loaded_asset returned falsy for %s" % DEST_PATH)

    # ---- genuine disk round-trip ----
    pkg = asset.get_outermost()
    reloaded, reload_err = unreal.EditorLoadingAndSavingUtils.reload_packages(
        [pkg], unreal.ReloadPackagesInteractionMode.ASSUME_POSITIVE
    )
    R["steps"]["disk_reload_attempted"] = bool(reloaded)
    R["steps"]["disk_reload_error"] = str(reload_err) if reload_err else ""
    if not reloaded:
        raise RuntimeError(
            "reload_packages reported no reload for %s; refusing to trust a "
            "read that may be the in-memory object" % DEST_PATH
        )

    asset_fresh = EAL.load_asset(DEST_PATH)
    if asset_fresh is None:
        raise RuntimeError("post-reload load_asset returned None for %s" % DEST_PATH)

    fresh_read = read_sgd_fields(asset_fresh, "SGD_TL_A (fresh disk reload)")
    R["steps"]["step2_read_back_from_disk"] = fresh_read

    # ---------------------------------------------------------------- Step 3
    # Compare against SGD_CHA_A's own read, taken earlier in this same run.
    cha_read_again = R["steps"]["step1_probe_recap"]
    verdict = {
        "same_field_names": True,  # both reads used identical property names above
        "separator_match": (
            ", " in fresh_read["main_grammar"]
            and fresh_read["main_grammar"] == TARGET_MAIN_GRAMMAR
        ),
        "cha_separator_sample": cha_read_again["main_grammar"],
        "tl_main_grammar": fresh_read["main_grammar"],
        "tl_use_grammar": fresh_read["use_grammar"],
        "tl_slot_count": fresh_read["slot_count"],
    }

    expected_binding = {
        "L00": "RULE_TL_L00", "L01": "RULE_TL_L01",
        "L02": "RULE_TL_L02", "L03": "RULE_TL_L03",
    }
    binding_check = []
    all_bound_ok = True
    for s in fresh_read["slots"]:
        sym = s["symbol"]
        paths = s["bound_rule_paths"]
        one_binding = (len(paths) == 1)
        bound_name = paths[0].rsplit("/", 1)[-1].split(".")[0] if paths else None
        ok = one_binding and (bound_name == expected_binding.get(sym))
        all_bound_ok = all_bound_ok and ok
        binding_check.append({
            "symbol": sym,
            "one_binding": one_binding,
            "bound_rule": bound_name,
            "expected": expected_binding.get(sym),
            "ok": ok,
        })
    verdict["binding_check"] = binding_check
    verdict["all_bindings_ok"] = all_bound_ok
    verdict["main_grammar_ok"] = (fresh_read["main_grammar"] == TARGET_MAIN_GRAMMAR)
    verdict["slot_count_ok"] = (fresh_read["slot_count"] == 4)
    verdict["overall_ok"] = (
        verdict["all_bindings_ok"] and verdict["main_grammar_ok"]
        and verdict["slot_count_ok"] and fresh_read["use_grammar"] is True
    )
    R["steps"]["step3_verdict"] = verdict

    if not verdict["overall_ok"]:
        raise RuntimeError("SGD_TL_A verification failed: %r" % verdict)

except Exception as e:
    R["errors"].append("build: %s: %s" % (type(e).__name__, e))

print(json.dumps(R, indent=1, default=str))
mcp_result = R
