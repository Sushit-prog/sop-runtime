# SOPVM

A compiler and capability-gated runtime for Standard Operating
Procedures (SOPs) executed by LLM agents — implementing the ideas in
*Compile, Then Page: Executable SOP Programs and a Capability-Gated
Runtime for Procedural LLM Agents* (Yu et al., 2026) as production
infrastructure.

SOPVM is a runtime layer, not another agent framework. It's designed
to sit underneath your existing agent stack (LangGraph, a raw
tool-calling loop, whatever) and answer one question reliably: *did
this run actually follow the procedure, and can I prove it?*

See [`docs/architecture.md`](docs/architecture.md) for the full
system design and milestone roadmap. This README documents what's
actually implemented **right now**.

## Status: Milestone 1

Only the following is implemented and tested:

- A parser for the minimal, **linear** SOP grammar (no branches,
  loops, tool calls, or capability declarations yet — those land in
  later milestones).
- `sopvm compile --check <file>` — validates a SOP source file and
  reports every problem it finds in one pass, with line numbers and
  "did you mean" suggestions where possible.

Everything else described in the architecture doc (IR, runtime,
capability model, drivers, observability) is **not implemented yet**.
Running `sopvm compile` without `--check`, or trying to execute a
SOP, will fail with an explicit "not implemented in this milestone"
message rather than doing something misleading.

## Install

```bash
git clone <this-repo>
cd sopvm
pip install -e ".[dev]"
```

Requires Python 3.10+. No GPU, no local model, no network access
required for anything in this milestone — the compiler is 100%
deterministic.

## Try it

```bash
sopvm compile --check examples/hello-sop/hello.md
```

```
✓ examples/hello-sop/hello.md: valid SOP
  id=hello-sop version=1 owner=platform-team
  title='Hello SOP'
  steps=3
```

Now break it on purpose:

```bash
echo -e '# No frontmatter\n1. Step.' > /tmp/bad.md
sopvm compile --check /tmp/bad.md
```

```
✗ /tmp/bad.md: 1 error(s)
  line 1: a SOP file must start with a YAML frontmatter block delimited by '---' lines
```

## Writing a SOP (Milestone 1 grammar)

```markdown
---
id: onboard-new-hire
version: 1
owner: people-ops
---
# Onboard a New Hire

1. Create the accounts.
2. Send the welcome email.
3. Schedule the first-week check-in,
   which may span multiple lines.
```

Rules enforced by the parser:

- The document must start with a `---`-delimited YAML frontmatter
  block declaring `id` (string), `version` (integer), and `owner`
  (string).
- The body must have a `# Title` heading before any steps.
- Steps must be numbered `1.`, `2.`, `3.`, ... sequentially, with no
  gaps and no duplicates. `1)` or unnumbered bullets are not
  recognized as steps.
- A step's text may continue onto following lines until a blank line
  or the next numbered step.

## Python API

```python
from sopvm.api import compile_check
from sopvm.compiler.errors import SOPParseErrors

try:
    procedure = compile_check("my-sop.md")
    print(procedure.id, len(procedure.steps))
except SOPParseErrors as exc:
    for error in exc.errors:
        print(error)
```

## Running tests

```bash
pytest --cov=sopvm --cov=cli --cov-report=term-missing
```

## Roadmap

See [`docs/architecture.md`](docs/architecture.md) section 10 for all
15 milestones. Next up (Milestone 2): IR lowering and `.sopc`
executable codegen for this same linear subset.
