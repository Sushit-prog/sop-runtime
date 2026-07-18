# VERSIONING_POLICY.md

SOPVM follows Semantic Versioning 2.0.0.

## Version Format

`MAJOR.MINOR.PATCH`

- **MAJOR**: Breaking changes to the public API (compile, check, Runtime)
- **MINOR**: New functionality that is backwards-compatible
- **PATCH**: Backwards-compatible bug fixes

## Public API Surface

Per INTERFACES.md §8, the public API is:

```python
sopvm.compile(sop_path: str, policy_path: str) -> CompiledProgram
sopvm.check(compiled: CompiledProgram) -> CheckResult
sopvm.Runtime(compiled: CompiledProgram, providers: list[ToolProvider])
    .run() -> RunResult
```

Anything not in this list is internal and may change without a version bump.

## What Requires a Version Bump

| Change | Bump |
|---|---|
| Breaking change to compile/check/Runtime signatures | MAJOR |
| New optional parameter added to public API | MINOR |
| Bug fix that doesn't change public API shape | PATCH |
| New IR version supported | MINOR |
| IR version dropped (no longer supported) | MAJOR |
| Internal module refactor (no public API change) | None |

## IR Versioning

IR files carry an `ir_version` field. The runtime rejects unsupported
versions with `UnsupportedIrVersionError` before execution begins.

Adding support for a new IR version: MINOR bump.
Dropping support for an old IR version: MAJOR bump.

## Enforcement

A CI script (`scripts/check_api_compat.py`) compares the current public
surface against the last tagged release. Breaking changes without a
MAJOR bump fail the build.
