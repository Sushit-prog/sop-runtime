# Contributing to SOPVM

## Development Setup

```bash
# Clone the repo
git clone https://github.com/your-org/sopvm.git
cd sopvm

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run the full test suite
make ci
# or equivalently:
pytest tests/ -v
```

## Project Structure

```
src/sopvm/
├── parser/          # M2: YAML parser + AST
├── ir/              # M3: IR data model
├── compiler/        # M3+M5: lowering + paging
├── capability/      # M4: token parser + policy loader
├── checker/         # M4: static capability checker
├── runtime/         # M6-M8: executor, gate, violations
├── plugins/         # M8: tool providers + registry + sandbox
├── integrations/    # M9: LangGraph adapter (ONLY place langgraph is imported)
├── telemetry/       # M10: events + sinks
├── cli/             # M11: click CLI
tests/
├── unit/            # Compiler + capability + scheduler unit tests
├── integration/     # Runtime + pipeline integration tests
├── adversarial/     # M12: security test corpus (CI-gated)
├── golden/          # AST/IR JSON snapshot tests
├── property/        # Hypothesis property-based tests
```

## Running Tests

```bash
# Full suite
pytest tests/ -v

# Just adversarial tests (CI-gated)
pytest tests/adversarial/ -v

# With coverage
pytest tests/ --cov=src/sopvm --cov-report=term-missing

# Property-based tests only
pytest tests/property/ -v
```

## Test Taxonomy

| Category | Purpose | When to add |
|---|---|---|
| `unit/` | Isolated component tests | Any new function/class |
| `integration/` | End-to-end pipeline tests | New milestone or cross-component feature |
| `adversarial/` | Security boundary tests | New escalation technique or enforcement layer |
| `golden/` | Snapshot regression tests | Any change to AST/IR output format |
| `property/` | Hypothesis fuzz tests | Any invariant that holds for all valid inputs |

## Proposing INTERFACES.md Changes

INTERFACES.md is the single source of truth for cross-milestone schemas. Changes require:

1. **Read the Change Control section** at the bottom of INTERFACES.md
2. **Version bump** to the affected schema
3. **Explicit call-out** in the milestone prompt listing which section changed and why
4. **Update all consuming modules** — a schema change in §2 (AST) must propagate to §3 (capability), §4 (IR), etc.

Do NOT silently redefine a schema. If you need a new field, add it (MINOR bump). If you need to remove or rename a field, that's a breaking change (MAJOR bump).

## Code Style

- Python 3.10+ only
- No comments unless the WHY is non-obvious
- Frozen dataclasses for all data structures
- No runtime state mutations in the compiler/checker path
