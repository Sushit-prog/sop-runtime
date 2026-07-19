# SOPVM

[![CI](https://github.com/Sushit-prog/sop-runtime/actions/workflows/adversarial.yml/badge.svg)](https://github.com/Sushit-prog/sop-runtime/actions/workflows/adversarial.yml)
[![PyPI](https://img.shields.io/pypi/v/sopvm)](https://pypi.org/project/sopvm/)
[![Python](https://img.shields.io/pypi/pyversions/sopvm)](https://pypi.org/project/sopvm/)
[![License](https://img.shields.io/pypi/l/sopvm)](https://github.com/Sushit-prog/sop-runtime/blob/main/LICENSE)

**v0.4.0 — 15/15 milestones complete, conditional branching, SQLite provider, 268 tests passing.**

A runtime layer beneath agent frameworks — not another one.

SOPVM compiles Standard Operating Procedures into executable programs and runs them on a capability-gated stack machine. It sits *underneath* LangGraph, CrewAI, or any tool-calling loop — the same way LLVM sits underneath Clang, Rust, and Swift rather than competing with any single language.

## Why Compilation Matters

Most "follow the SOP" approaches today mean "paste the SOP text into a system prompt and hope." The LLM re-plans every step, inconsistently. SOPVM compiles the SOP once into a deterministic, auditable program. The LLM only does the semantic work (interpreting what a step means); the runtime handles state tracking, capability enforcement, and execution flow. This is measurably better — the research paper behind SOPVM shows up to 16-point accuracy gains over raw prose.

## Features

- **Deterministic compilation** — same SOP + policy always produces the same IR. No LLM calls, no randomness, no side effects.
- **Conditional branching** — `condition` field with `on_success`/`on_failure` edges, plus bounded loops with `max_iterations` and `on_limit`.
- **Capability-gated execution** — every tool call is checked against a policy ceiling before invocation. Denied calls are terminal facts, not retryable failures.
- **Static policy checking** — `sopvm check` validates capabilities at compile time, usable as a pre-commit hook (exit 1 on violations).
- **Provider sandbox** — providers that invoke capabilities beyond their declared scope are caught at runtime, independent of the SOP-level gate.
- **Telemetry** — every state transition and gate decision is emitted to an append-only JSONL trace. Broken sinks degrade silently, never crash the run.
- **Adversarial test suite** — 25+ escalation techniques tested in CI: ceiling bypass, namespace escalation, Unicode homoglyphs, IR tampering, provider lying.
- **LangGraph integration** — wrap any compiled SOP as a StateGraph node with one function call.
- **Local LLM handler** — reference StepHandler using llama.cpp for local inference (no paid API, no GPU required).

## Quickstart

### From PyPI

```bash
pip install sopvm
```

Create a minimal SOP (`hello.sop.yaml`):

```yaml
sop_version: "0.1"
name: "hello"
policy: "policy.yaml"

steps:
  - id: greet
    description: "Say hello"
    terminal: true
    requires:
      capabilities: ["db:read(greetings)"]
```

Create a policy (`policy.yaml`):

```yaml
policy_version: "0.1"
allowed_capabilities:
  - "db:read(greetings)"
```

Then compile, check, and run:

```bash
sopvm compile hello.sop.yaml --policy policy.yaml -o hello.ir.json
sopvm check hello.ir.json --policy policy.yaml
sopvm run hello.ir.json
```

### From source

```bash
git clone https://github.com/Sushit-prog/sop-runtime.git
cd sop-runtime
pip install -e ".[dev]"

# Compile the example SOP
sopvm compile examples/sops/refund-request-handling.sop.yaml \
    --policy policies/support-agent.policy.yaml \
    -o compiled.ir.json

# Check for policy violations (pre-commit mode)
sopvm check compiled.ir.json --policy policies/support-agent.policy.yaml
# exit 0 = all capabilities within policy
# exit 1 = violations found

# Execute the compiled SOP
sopvm run compiled.ir.json
```

### Example output

```
$ sopvm compile hello.sop.yaml --policy policy.yaml -o hello.ir.json
Compiled to hello.ir.json

$ sopvm check hello.ir.json --policy policy.yaml
All capabilities within policy.

$ sopvm run hello.ir.json
Final state: DONE
Path: greet
```

## Python API

```python
import sopvm

# Compile a SOP against a policy
compiled = sopvm.compile("sop.yaml", "policy.yaml")

# Check for policy violations
result = sopvm.check(compiled)
if not result.passed:
    for v in result.violations:
        print(f"VIOLATION: {v.step_id} — {v.reason}")

# Execute the compiled SOP
runtime = sopvm.Runtime(compiled)
run_result = runtime.run()
print(f"State: {run_result.final_state.value}")
print(f"Path: {' -> '.join(run_result.path)}")
```

## CLI Reference

| Command | Purpose | Exit codes |
|---|---|---|
| `sopvm compile <sop> --policy <policy> -o <ir>` | Compile SOP YAML to IR JSON | 0 success, 2 error |
| `sopvm check <ir> --policy <policy>` | Validate IR against policy | 0 pass, 1 violation, 2 error |
| `sopvm run <ir>` | Execute compiled SOP | 0 DONE, 1 FAILED/DENIED |
| `sopvm trace <log> <run_id>` | Pretty-print telemetry trace | 0 found, 1 not found |

## Architecture

```
SOP YAML ──► Parser ──► AST ──► Compiler ──► IR ──► Runtime ──► Result
             (M2)       (M2)   (M3+M5)     (M3)  (M6-M8)
                                          ┌──────┴──────┐
                                          │ Gate │Plugins│
                                          │ (M7) │ (M8)  │
                                          └──────┴──────┘
```

| Component | Module | Description |
|---|---|---|
| Parser | `sopvm.parser` | YAML parsing, JSON Schema validation, semantic checks |
| AST | `sopvm.parser.ast` | Frozen dataclasses: `SopDocument`, `StepNode`, `CapabilityRequest` |
| Compiler | `sopvm.compiler` | AST→IR lowering + policy-based capability paging |
| IR | `sopvm.ir` | `CompiledProgram`, `IrNode` — the only artifact the runtime reads |
| Capability Model | `sopvm.capability` | Token parser, policy loader, ceiling enforcement |
| Static Checker | `sopvm.checker` | Compile-time policy validation |
| Runtime | `sopvm.runtime` | Executor, capability gate, state machine |
| Plugins | `sopvm.plugins` | `ToolProvider` protocol, registry, sandbox wrapper |
| Telemetry | `sopvm.telemetry` | `Event` schema, `JsonlSink`, `InMemorySink` |
| CLI | `sopvm.cli` | `compile`, `check`, `run`, `trace` subcommands |
| LangGraph | `sopvm.integrations.langgraph` | `as_langgraph_node()` adapter |

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design rationale.

## Security

SOPVM's security model is layered:

1. **Compile-time** — the static checker validates every capability against the policy before the IR is emitted.
2. **Runtime re-validation** — the executor re-validates `capabilities_paged` against the policy at load time, catching IR tampering.
3. **Gate enforcement** — every tool call is checked against the current step's paged capabilities. DENIED is terminal.
4. **Provider sandbox** — providers that invoke undeclared capabilities are caught independently of the gate.

The adversarial test suite (`tests/adversarial/`) exercises all four layers with 25+ escalation techniques, run on every PR.

See [examples/adversarial_walkthrough.md](examples/adversarial_walkthrough.md) for a step-by-step walkthrough.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — component design and rationale
- [INTERFACES.md](INTERFACES.md) — canonical contract schemas (M2-M13)
- [VERSIONING_POLICY.md](VERSIONING_POLICY.md) — SemVer rules
- [CHANGELOG.md](CHANGELOG.md) — release history
- [CONTRIBUTING.md](CONTRIBUTING.md) — development setup and code style
- [POSTMORTEM.md](POSTMORTEM.md) — real incidents found and fixed during the build

## Examples

- [`examples/sops/`](examples/sops/) — example SOP YAML files (refund, incident response, order processing with branching)
- [`examples/providers/`](examples/providers/) — reference tool providers: `sqlite_provider.py` (real SQLite), `mock_db.py`
- [`examples/handlers/`](examples/handlers/) — local LLM StepHandler using llama.cpp (reference implementation)
- [`examples/langgraph_integration.py`](examples/langgraph_integration.py) — LangGraph StateGraph wrapper
- [`examples/run_db_demo.py`](examples/run_db_demo.py) — end-to-end demo with real SQLite reads/writes
- [`examples/run_llm_demo.py`](examples/run_llm_demo.py) — end-to-end demo with local LLM
- [`examples/adversarial_walkthrough.md`](examples/adversarial_walkthrough.md) — step-by-step escalation attempt with real CLI output

## Contributing

```bash
git clone https://github.com/Sushit-prog/sop-runtime.git
cd sop-runtime
pip install -e ".[dev]"
pytest tests/ -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development guide, test taxonomy, and how to propose INTERFACES.md changes.

## License

Apache-2.0
