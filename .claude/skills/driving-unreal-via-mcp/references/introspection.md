# Introspection templates

Ready-to-run, READ-ONLY exploration scripts. Fill in the bracketed parts, write
to `Content/Python/_explore.py`, run via `run_unreal_script`, and read the real
API from stdout. Each follows the transport convention: `print` findings and put
the key data in `mcp_result`.

## List a class's methods/attributes (with keyword filter)

```python
import unreal
cls = unreal.EditorActorSubsystem            # <- the class to inspect
needle = ""                                  # <- optional substring filter, "" = all
names = [n for n in dir(cls) if needle.lower() in n.lower()]
for n in names:
    print(n)
mcp_result = {"class": cls.__name__, "count": len(names), "members": names}
```

## Read a function/method's real signature + docstring

```python
import unreal, inspect
target = unreal.EditorActorSubsystem.spawn_actor_from_class   # <- the callable
print(getattr(target, "__doc__", "") or "(no docstring)")
try:
    print("signature:", inspect.signature(target))
except (ValueError, TypeError):
    print("signature: <not introspectable; read the docstring above>")
mcp_result = {"doc": getattr(target, "__doc__", "")}
```

`unreal` callables often expose their signature only in the docstring — always
print `__doc__`.

## List all available EditorSubsystems

```python
import unreal
subs = [n for n in dir(unreal) if n.endswith("Subsystem")]
for n in subs:
    print(n)
mcp_result = {"subsystems": subs}
```

Get an instance with `unreal.get_editor_subsystem(unreal.<Name>)`.

## Search class/symbol names by keyword

```python
import unreal
needle = "Material"                          # <- keyword
hits = [n for n in dir(unreal) if needle.lower() in n.lower()]
for n in hits:
    print(n)
mcp_result = {"needle": needle, "hits": hits}
```

## Inspect an enum's values

```python
import unreal
en = unreal.AssetImportTask                  # <- enum or class
print([n for n in dir(en) if not n.startswith("_")])
```

## Notes

- These scripts only read — they never mutate the level or assets.
- If `dir()` output is long, set `needle` to filter rather than dumping everything.
- After reading the real signatures, write the real script (see SKILL.md step 4).
