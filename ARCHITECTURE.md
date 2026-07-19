# ARCHITECTURE.md

SOPVM's architecture is built on one core principle: **the compiler never talks to a model, and the runtime never talks to raw SOP prose.** Everything the LLM sees at execution time came out of the compiler as a validated artifact.

## Parser (`sopvm.parser`)

**Milestone:** M2

Parses strict YAML SOP files into a typed AST. Validates against a JSON Schema (`schemas/sop.schema.json`) and performs semantic checks (edge target resolution, reachability, capability grammar).

**Design rationale:** YAML was chosen over Markdown (which M1 used) because it's unambiguous to parse and doesn't require a hand-written grammar. The JSON Schema provides machine-readable validation; the semantic checks catch logic errors that the schema can't express.

**What the parser does NOT do:** It doesn't know about policies, capabilities, or execution semantics. It only validates structure.

See [INTERFACES.md §1](INTERFACES.md#1-sop-source-format-owned-by-m2) for the exact YAML format.

## AST (`sopvm.parser.ast`)

**Milestone:** M2

Frozen dataclasses representing the parsed SOP: `SopDocument`, `StepNode`, `CapabilityRequest`. Immutable — the AST is a build artifact, not a mutable state object.

See [INTERFACES.md §2](INTERFACES.md#2-ast-owned-by-m2) for the exact shape.

## Compiler (`sopvm.compiler`)

**Milestones:** M3 (lowering), M5 (paging)

Two passes:
1. **Lower** (`lower.py`): Converts AST → IR (`CompiledProgram`). Direct 1:1 mapping, no optimization.
2. **Page** (`page.py`): Computes `capabilities_paged` by intersecting declared capabilities against the policy via `satisfies()`. This is where the policy ceiling is applied.

**Design rationale:** Separating lowering from paging makes each pass independently testable and keeps the IR clean. The IR is the *only* artifact the runtime reads — it never sees the AST or source YAML.

**Why compilation is deterministic:** No LLM calls, no randomness, no side effects. Same input → same output, always. This is what makes the compiler testable without an API key.

See [INTERFACES.md §4](INTERFACES.md#4-ir--program-graph-owned-by-m3-capability-annotated-by-m5) for the IR shape.

## Capability Model (`sopvm.capability`, `sopvm.checker`)

**Milestone:** M4

Two layers:
1. **Capability tokens** (`capability/token.py`): Parse `namespace:action(params)` strings into structured tokens. Comparator params (`<=`, `>=`) express ceilings in policy entries.
2. **Static checker** (`checker/check.py`): Validates that every declared capability in the IR satisfies at least one policy entry. This is compile-time enforcement.

**Design rationale:** Capabilities are unforgeable references, not strings the model can produce. The LLM never sees or manipulates a capability token directly — it only requests an action, and the gate decides whether the currently-held capability covers that action.

See [INTERFACES.md §3](INTERFACES.md#3-capability-token-schema-owned-by-m4) for the token schema and policy format.

## Runtime (`sopvm.runtime`)

**Milestones:** M6 (executor), M7 (gate), M8 (providers)

The runtime is a stack machine with an explicit program counter:
1. **Executor** (`executor.py`): Drives the state machine. Fixed transition table, not ad hoc branching.
2. **Capability gate** (`gate.py`): Intercepts every tool-call request. Checks against `capabilities_paged` for the current step. DENIED is a terminal fact — no retry, no recovery.
3. **Provider registry + sandbox** (`plugins/`): Routes approved calls to registered providers. The sandbox catches providers lying about their own scope (defense in depth).

**Design rationale:** The LLM is *never* trusted to control the program counter. It proposes ("I believe the precondition for branch B holds"), the engine decides. Every state transition is auditable via the telemetry system.

**IR version check:** The executor rejects IR files with unsupported versions before execution begins, preventing confusing mid-execution failures.

## Telemetry (`sopvm.telemetry`)

**Milestone:** M10

Every state transition and gate decision is emitted to a `TelemetrySink`. The `JsonlSink` produces append-only JSONL traces. Telemetry failures are silently degraded — a broken sink never crashes the run it's observing.

See [INTERFACES.md §7](INTERFACES.md#7-event--telemetry-schema-owned-by-m10) for the event schema.

## CLI (`sopvm.cli`)

**Milestone:** M11

Four subcommands: `compile`, `check`, `run`, `trace`. The `check` command is designed for pre-commit hooks (exit 1 on violations). No subcommand ever prints a raw Python traceback for expected failures.

## Integration Points

- **LangGraph** (`sopvm.integrations.langgraph`): Wraps a compiled SOP as a StateGraph node. This is the ONLY module allowed to import langgraph (enforced by AST-based import boundary test).
- **Pre-commit** (`.pre-commit-hooks.yaml`): `sopvm-check` hook for CI/CD pipelines.
