# POSTMORTEM.md

Real problems found and fixed during the SOPVM build. Written for a technical reader evaluating engineering judgment — not a project summary.

---

## Incident 1: M1 Drift and Recovery

### Problem

The first implementation of M1 (Parser + AST for a minimal SOP subset) deviated from the project's own canonical spec on three dimensions:

1. **Input format**: M1 parsed Markdown with YAML frontmatter. The canonical spec (later formalized in INTERFACES.md §1) defined a strict YAML format. The M1 parser was a hand-written recursive-descent parser for a bespoke Markdown grammar — a significant implementation effort that was thrown away.

2. **AST shape**: M1 defined `Procedure(id, version, owner, title, steps, source_path)` and `Step(index, text, source_line)`. The canonical spec (INTERFACES.md §2) defined `SopDocument(version, policy_ref, steps)` and `StepNode(id, description, requires, edges, terminal)`. The field names, types, and structure were entirely different.

3. **Directory layout**: M1 used `sopvm/sopvm/compiler/` (repo root wrapping package root). The canonical layout uses `src/sopvm/parser/` with `pyproject.toml`'s `[tool.hatch.build.targets.wheel] packages = ["src/sopvm"]`.

4. **Scope creep**: M1 shipped a working CLI (`sopvm compile --check`), an API module (`sopvm.api.compile_check()`), a full test suite, CI configuration, and documentation — all built against the divergent spec. None of this conformed to the canonical shapes that M2+ needed.

### How it was found

A milestone-by-milestone drift check against the Deliverables list, rather than trusting a self-reported summary. The check compared: (a) what M1 actually implemented (by reading the source files), (b) what the canonical spec required (INTERFACES.md §1-§2), and (c) what M2-M13 needed to consume (the AST and parser interface). The divergence was obvious on every axis.

### Root cause

M1 was implemented before INTERFACES.md existed as a formal contract. The spec was derived from the architecture document, which described the *intent* (Markdown grammar, recursive-descent parser) but not the *exact shapes*. M1 implemented what the architecture doc described. Later milestones formalized the contract, and M1 didn't conform to it.

### Fix

Salvaged only what conformed: the M1 test patterns and the project structure conventions. Discarded the M1 parser, AST, CLI, and API module. Rebuilt M2 against INTERFACES.md §1-§2 exactly:

- New YAML parser with JSON Schema validation (`src/sopvm/parser/parse.py`)
- New AST matching the canonical shapes (`src/sopvm/parser/ast.py`)
- New directory layout (`src/sopvm/parser/`, not `sopvm/sopvm/compiler/`)
- New JSON Schema (`schemas/sop.schema.json`)

The M1 zip archive was preserved at `sopvm-milestone-1/` as a reference but is not imported or used by any subsequent code.

### What it proves

A spec that exists only in prose (architecture docs) is not a contract. A spec that exists only in code (M1's implementation) is not a contract either. The contract needs to be a standalone document with exact shapes — which is what INTERFACES.md became. The lesson: formalize the contract *before* implementing, not after.

---

## Incident 2: IR Tampering Gap (M12)

### Problem

The adversarial security suite in M12 tested whether a hand-edited, tampered compiled IR file would be caught at runtime. The scenario: an attacker takes a compiled IR JSON, hand-edits `capabilities_paged` on one node to include a capability the compiler would never have emitted (e.g., `fs:write(/etc/passwd)` when the policy only allows `db:read(orders)`), then feeds it to the runtime.

The runtime did not catch this. It trusted the `capabilities_paged` values in the IR file as-is. The gate checked tool calls against `capabilities_paged`, but if `capabilities_paged` itself was tampered, the gate enforced the tampered values.

### How it was found

M12's adversarial test `test_tampered_paged_capabilities_rejected` constructed a `CompiledProgram` with a paged capability (`fs:write(/etc/shadow)`) that the policy does not allow, passed it to the `Executor` with a policy, and expected an `ExecutorError`. Before the fix, the test passed — meaning the tampered IR ran without complaint.

### Root cause

The security architecture had a gap between compile-time validation and runtime enforcement:

| Layer | What it validates | Trust model |
|---|---|---|
| M4 static checker | `capabilities_paged` against `Policy` | Compile-time: validates the IR was produced correctly |
| M7 runtime gate | Each tool-call against `node.capabilities_paged` | Runtime: **trusts** `capabilities_paged` from the IR |

The M4 checker runs at compile time and produces a validated IR. But the IR is a serialized artifact — anyone can edit the JSON. The runtime loaded the IR via `CompiledProgram.from_json()`, which is pure deserialization with zero validation. If the IR was tampered between compile time and run time, the runtime had no way to know.

This matters specifically for a capability-gated system because the *entire security model* rests on `capabilities_paged` being trustworthy. If a step's paged capabilities can be widened without detection, an attacker can escalate any capability by editing one JSON field.

### Fix

Added `_validate_paged_capabilities()` to `Executor.run()` (`src/sopvm/runtime/executor.py`). When a `policy` is provided, the executor re-validates every `capabilities_paged` entry against the policy before execution begins:

```python
def _validate_paged_capabilities(self) -> None:
    if self._policy is None:
        return
    from sopvm.capability.token import parse_capability
    from sopvm.checker.check import satisfies
    for step_id, node in self._program.nodes.items():
        for cap_str in node.capabilities_paged:
            token = parse_capability(cap_str)
            if not any(satisfies(token, a) for a in self._policy.allowed_capabilities):
                raise ExecutorError(
                    f"IR tampering detected: step {step_id!r} has "
                    f"paged capability {cap_str!r} that is not "
                    f"satisfied by any entry in the policy"
                )
```

The `Executor` now accepts an optional `policy` parameter. The CLI's `run` command and the `compile_sop()` pipeline pass the policy through. Without a policy (backwards compatibility), validation is skipped.

### What it proves

A compiled artifact is not inherently trustworthy just because a compiler produced it. The compiler validates at build time, but the artifact can be edited between build and run. For security-critical systems, runtime re-validation is defense-in-depth, not redundancy. The principle: trust boundaries should be enforced at the point of use, not just the point of production.

---

## Incident 3: The Langgraph Import Leak (M15)

### Problem

M9 built an import-boundary test (`tests/test_import_boundaries.py`) specifically to guarantee that `langgraph` stays an optional dependency, isolated to `src/sopvm/integrations/langgraph/`. The test used AST parsing to walk every `.py` file under `src/sopvm/` and check for langgraph imports. This test passed for milestones M9 through M12.

In M13 (Public API Stabilization), the `Runtime` class in `src/sopvm/__init__.py` and the `run` command in `src/sopvm/cli/main.py` both added lazy imports of `_SopvmHandler` from the langgraph adapter module:

```python
from sopvm.integrations.langgraph.node import _SopvmHandler
```

This import is inside a function body (lazy), not at the top of the file. The import-boundary test uses `ast.walk()`, which visits all nodes including those inside function bodies — so the lazy import *should* have been caught. But it wasn't.

### How it was found

M15's clean-venv install verification. The build produced `sopvm-0.2.0-py3-none-any.whl`. I installed it in a fresh virtualenv with zero optional dependencies. Running `sopvm.compile()`, `sopvm.check()`, and `sopvm.Runtime().run()` all worked. But `Runtime().run()` raised:

```
ModuleNotFoundError: No module named 'langgraph'
```

The `Runtime` class imported `_SopvmHandler` from the langgraph adapter, which itself imports `from langgraph.graph import StateGraph`. Without langgraph installed, the import chain broke at runtime.

### Root cause

The import-boundary test's detection logic had a gap. It checked:

```python
if node.module and node.module.startswith("langgraph"):
```

This correctly catches `from langgraph.graph import StateGraph` (module starts with `"langgraph"`). But the actual violation was:

```python
from sopvm.integrations.langgraph.node import _SopvmHandler
```

The module name here is `sopvm.integrations.langgraph.node`. It starts with `sopvm`, not `langgraph`. The `startswith` check missed it entirely.

The test was verifying the *wrong invariant*. It checked "does any file import a module whose name starts with `langgraph`?" when it should have checked "does any file import a module whose path contains `langgraph`?" The indirect import through the allowlisted adapter module was invisible to the original check.

### Fix

Changed the detection logic in `_has_langgraph_import()`:

```python
# Before (missed indirect imports):
if node.module and node.module.startswith("langgraph"):

# After (catches any module path containing langgraph):
if node.module and ("langgraph" in node.module.split(".")):
```

This catches both:
- `from langgraph.graph import StateGraph` — direct import
- `from sopvm.integrations.langgraph.node import _SopvmHandler` — indirect through allowlisted module

The fix also fixed the underlying code: both `__init__.py` and `cli/main.py` were updated to use a `_SimpleHandler` class defined inline instead of importing `_SopvmHandler` from the langgraph adapter, removing the hard dependency.

### What it proves

A regression-prevention test can have a real gap in its own detection logic. The test existed, passed, and looked correct — but its detection predicate was narrower than the failure mode it was supposed to prevent. The way to find this is not to trust that the test exists, but to verify the test against the exact failure mode: "if I introduce a langgraph import through *this specific path*, does the test catch it?" The M15 clean-venv verification was the actual safety net, not the test. The lesson: tests are code, and code has bugs — including the tests that are supposed to catch bugs.

---

## Incident 4: The max_iterations Validation Gap

### Problem

When M16 added conditional branching and bounded loops to the SOP grammar, `CompiledProgram.from_json()` accepted `max_iterations` from the IR JSON without validation. The IR JSON Schema validates `max_iterations` as `integer` at parse time, but `from_json()` is pure deserialization — it trusts whatever the JSON contains.

If someone hand-edited the IR and set `max_iterations` to a string (`"abc"`), a float (`3.5`), `None`, zero, or a negative number, the executor would crash with a `TypeError` at runtime:

```python
# executor.py line 286
if count >= node.loop.max_iterations:  # TypeError: '>=' not supported between 'int' and 'str'
```

This is a different failure mode than the IR tampering gap (Incident 2). That gap was about *semantic* correctness — paged capabilities widened beyond policy. This gap is about *structural* correctness — a field that should be a positive integer but isn't.

### How it was found

A code review question: "could a node with a missing or corrupted max_iterations hang the runtime?" The answer was: it wouldn't hang (the `max_steps` safety limit catches infinite loops), but it would crash with a raw `TypeError` instead of a clean error message. The executor's defensive `max_steps` check prevents a true hang, but the failure mode is still ugly.

### Root cause

The IR deserialization path (`CompiledProgram.from_json()`) was written as a direct映射 from JSON keys to dataclass fields, with no type validation beyond what Python's dataclass constructor enforces. The JSON Schema validates at parse time, but the IR is a serialized artifact that can be hand-edited. The `from_json()` method is the second trust boundary — it should validate structural invariants before the executor ever sees the data.

### Fix

Added validation in `CompiledProgram.from_json()` (`src/sopvm/ir/model.py`):

```python
if v.get("loop"):
    max_iter = v["loop"].get("max_iterations")
    if not isinstance(max_iter, int) or max_iter < 1:
        raise ValueError(
            f"invalid max_iterations for step {k!r}: "
            f"expected positive integer, got {max_iter!r}"
        )
    loop = IrLoop(max_iterations=max_iter)
```

This catches all corrupt values (string, float, None, zero, negative) at deserialization time with a clear error message, not a cryptic `TypeError` at execution time.

Added 5 tests in `tests/unit/test_conditional.py::TestCorruptMaxIterations` covering string, float, None, zero, and negative values.

### What it proves

There are two trust boundaries for any serialized artifact: the schema (which validates at write time) and the deserializer (which validates at read time). The IR is written by the compiler and read by the runtime — but it can be edited between those two points by anyone. Validating only at write time (JSON Schema) is not enough. The deserializer is the second line of defense, and it needs to enforce the same invariants. This is the same principle as Incident 2 (IR tampering), applied to a different field.

---

## Incident 5: The Paging Pass Dropped Conditional Fields

### Problem

When Phase 1 added conditional branching and bounded loops to the SOP grammar (`condition`, `loop`, `on_limit` fields), the fields were correctly added to the AST, the lowerer, and the IR model. But the `apply_paging()` pass (M5) silently dropped them. When `compile_sop()` called `lower()` then `apply_paging()`, the resulting `CompiledProgram` had `condition=None` on every node — even though the AST had the fields and the lowerer copied them correctly.

The result: conditional SOPs compiled successfully but the executor saw no conditions. All conditional steps returned DONE (no condition to evaluate), all loops had no max_iterations, and `on_limit` edges were lost. The demo ran through the wrong path and no tool calls happened.

### How it was found

The `run_db_demo.py` demo showed identical before/after database dumps — no `db:write` happened despite the SOP declaring one. Tracing the execution path revealed the condition step was treated as non-conditional (no `condition` field in the IR), so the handler always returned DONE, routing to the wrong branch.

### Root cause

The Phase 1 unit tests (`TestConditionalLowering`) tested `lower()` in isolation — they constructed `SopDocument` objects by hand and called `lower(doc)` directly. This proved the lowerer copies `condition`/`loop`/`on_limit` correctly. But no test exercised the full `compile_sop()` pipeline (`parse → lower → apply_paging`). The `apply_paging()` pass created new `IrNode` objects but only copied four fields:

```python
# page.py — BEFORE fix
new_nodes[step_id] = IrNode(
    capabilities_declared=list(node.capabilities_declared),
    capabilities_paged=paged,
    edges=dict(node.edges),
    terminal=node.terminal,
    # condition, loop, on_limit — MISSING
)
```

The paging pass was written before conditional branching existed. When Phase 1 added new fields to `IrNode`, the paging pass was never updated to copy them. The unit tests for conditionals tested `lower()` but not `apply_paging()` — a classic coverage gap where each component was tested in isolation but not through the pipeline.

### Fix

Added the missing fields to `apply_paging()`:

```python
# page.py — AFTER fix
new_nodes[step_id] = IrNode(
    capabilities_declared=list(node.capabilities_declared),
    capabilities_paged=paged,
    edges=dict(node.edges),
    terminal=node.terminal,
    condition=node.condition,    # added
    loop=node.loop,              # added
    on_limit=node.on_limit,      # added
)
```

Added `TestFullPipeline` in `tests/unit/test_conditional.py` with 3 tests that compile conditional/loop SOPs through the full `compile_sop()` pipeline (parse → lower → page) and assert the fields survive. These tests would have caught the bug before it shipped.

### What it proves

Unit testing each component in isolation is necessary but not sufficient. When a new feature adds fields that flow through multiple pipeline stages, every stage that creates new objects must be updated — and every stage must be tested through the full pipeline, not just in isolation. The `TestConditionalLowering` tests proved `lower()` works; the missing `TestFullPipeline` tests would have proved `apply_paging()` preserves the fields. The lesson: when adding fields that flow through a pipeline, add an end-to-end pipeline test that exercises the full path, not just the individual components.
