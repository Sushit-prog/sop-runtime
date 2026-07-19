# SOPVM

[![CI](https://github.com/Sushit-prog/sop-runtime/actions/workflows/adversarial.yml/badge.svg)](https://github.com/Sushit-prog/sop-runtime/actions/workflows/adversarial.yml)
[![PyPI](https://img.shields.io/pypi/v/sopvm)](https://pypi.org/project/sopvm/)
[![Python](https://img.shields.io/pypi/pyversions/sopvm)](https://pypi.org/project/sopvm/)
[![License](https://img.shields.io/pypi/l/sopvm)](https://github.com/Sushit-prog/sop-runtime/blob/main/LICENSE)

**v0.2.0 — published on PyPI, 15/15 milestones complete, 229 tests passing.**

**A runtime layer beneath agent frameworks — not another one.**

SOPVM compiles Standard Operating Procedures into executable programs and runs them on a capability-gated stack machine. It sits *underneath* LangGraph, CrewAI, or any tool-calling loop — the same way LLVM sits underneath Clang, Rust, and Swift rather than competing with any single language.

## Why Compilation Matters

Most "follow the SOP" approaches today mean "paste the SOP text into a system prompt and hope." The LLM re-plans every step, inconsistently. SOPVM compiles the SOP once into a deterministic, auditable program. The LLM only does the semantic work (interpreting what a step means); the runtime handles state tracking, capability enforcement, and execution flow. This is measurably better — the research paper behind SOPVM shows up to 16-point accuracy gains over raw prose.

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

## Architecture

```
SOP YAML ──► Parser ──► AST ──► Compiler ──► IR ──► Runtime ──► Result
             (M2)       (M2)   (M3+M5)     (M3)  (M6-M8)
                                          ┌──────┴──────┐
                                          │ Gate │Plugins│
                                          │ (M7) │ (M8)  │
                                          └──────┴──────┘
```

| Box | Module | Milestone |
|---|---|---|
| Parser | `sopvm.parser` | M2 |
| AST | `sopvm.parser.ast` | M2 |
| Compiler (lower+page) | `sopvm.compiler` | M3, M5 |
| IR | `sopvm.ir` | M3 |
| Runtime (gate+providers) | `sopvm.runtime` | M6-M8 |
| Static Checker | `sopvm.checker` | M4 |
| Telemetry | `sopvm.telemetry` | M10 |
| CLI | `sopvm.cli` | M11 |
| LangGraph Adapter | `sopvm.integrations.langgraph` | M9 |

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design rationale.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — component design and rationale
- [INTERFACES.md](INTERFACES.md) — canonical contract schemas (M2-M13)
- [VERSIONING_POLICY.md](VERSIONING_POLICY.md) — SemVer rules
- [CHANGELOG.md](CHANGELOG.md) — release history
- [CONTRIBUTING.md](CONTRIBUTING.md) — development setup

## Examples

- `examples/sops/` — example SOP YAML files
- `examples/providers/` — reference tool provider implementations
- `examples/langgraph_integration.py` — LangGraph StateGraph wrapper
- `examples/adversarial_walkthrough.md` — step-by-step escalation attempt
