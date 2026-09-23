---
name: driving-unreal-via-mcp
description: Use when the user asks to do anything inside the running Unreal Engine editor — spawn or modify actors, manipulate the level or world, import or create assets, edit materials, batch-edit, query scene state — that runs through the run_unreal_script MCP tool. Unreal-specific.
---

# Driving Unreal via MCP

## Overview

The `run_unreal_script` MCP tool runs a `.py` file from `Content/Python/` inside
Unreal's embedded interpreter (args arrive as the global `mcp_args`; set
`mcp_result` to return JSON data). The `unreal` Python API has thousands of
classes — writing scripts from memory gives wrong signatures and stale calls.

**Core discipline: introspect → verify → write the real script.** Discover the
true API at runtime; do not guess.

## Preflight

- The editor must be running with the `UnrealMcpBridge` plugin. If the tool
  returns `"Unreal editor not connected on 127.0.0.1:8777"`, STOP and ask the
  user to launch it. Do not retry blindly.
- Scripts must live under `Content/Python/` (the scripts root). Paths escaping
  it are rejected.

## Main-line workflow

```dot
digraph driving_unreal {
    "UE task" [shape=box];
    "Editor connected?" [shape=diamond];
    "Stop: ask user to launch editor" [shape=box];
    "API already introspected this\nsession or verified in references?" [shape=diamond];
    "Find entry point (api-map.md)" [shape=box];
    "Introspect: write _explore.py,\nrun it, READ real signatures" [shape=box];
    "Write real script\n(descriptive name, obey gotchas.md)" [shape=box];
    "Run + verify stdout / mcp_result" [shape=box];
    "Matches intent?" [shape=diamond];
    "Done" [shape=doublecircle];

    "UE task" -> "Editor connected?";
    "Editor connected?" -> "Stop: ask user to launch editor" [label="no"];
    "Editor connected?" -> "API already introspected this\nsession or verified in references?" [label="yes"];
    "API already introspected this\nsession or verified in references?" -> "Write real script\n(descriptive name, obey gotchas.md)" [label="yes"];
    "API already introspected this\nsession or verified in references?" -> "Find entry point (api-map.md)" [label="no"];
    "Find entry point (api-map.md)" -> "Introspect: write _explore.py,\nrun it, READ real signatures";
    "Introspect: write _explore.py,\nrun it, READ real signatures" -> "Write real script\n(descriptive name, obey gotchas.md)";
    "Write real script\n(descriptive name, obey gotchas.md)" -> "Run + verify stdout / mcp_result";
    "Run + verify stdout / mcp_result" -> "Matches intent?";
    "Matches intent?" -> "Done" [label="yes"];
    "Matches intent?" -> "Introspect: write _explore.py,\nrun it, READ real signatures" [label="no, re-introspect failing API"];
}
```

1. **Preflight** — confirm the editor is connected (above).
2. **Find the entry point** — use `references/api-map.md` to pick the class/subsystem to introspect.
3. **Introspect** — take a template from `references/introspection.md`, write a READ-ONLY exploration script to `Content/Python/_explore.py`, run it via `run_unreal_script`, and READ the real signatures from stdout. Do not guess parameters.
4. **Write the real script** — based on the introspected API, obeying `references/gotchas.md`. Save it with a descriptive name (e.g. `tint_cubes_red.py`) so it is reusable/auditable. `print` progress; return data via `mcp_result`.
5. **Run + verify** — run it, read stdout/`mcp_result`, confirm intent. On error, re-introspect the failing API (back to step 3).

**Skip-introspection exception:** if this session already introspected the API in
question, or the call is one already verified in `references/gotchas.md`, write the
real script directly — don't force an exploration round-trip on simple tasks.

## Red flags — STOP

| Thought | Reality |
|---|---|
| "I know this `unreal` method, I'll write the full script from memory." | The API is huge and version-specific. Introspect first — wrong signatures waste a full run. |
| "I'll skip introspection and just run it; I'll fix errors if they come." | One introspection round-trip is cheaper than guess-fail-guess. Introspect. |
| "I'll assume the method name / argument order." | Read the real signature with `help()`. Assumptions are the #1 failure. |
| "The script worked, I'm done." | Did you SAVE edited assets AND the level if you changed actors? Is `mcp_result` JSON-serializable? Check `gotchas.md`. |
| "Connection error — let me retry the same call." | Editor isn't connected. Stop and ask the user to launch it. |

## References

- `references/introspection.md` — exploration script templates (the toolkit for step 3).
- `references/api-map.md` — which class/subsystem to introspect for a given task.
- `references/gotchas.md` — game thread, transactions, asset saving, serialization, paths.
