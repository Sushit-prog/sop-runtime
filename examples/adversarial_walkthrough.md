# Adversarial Walkthrough

This document walks through a capability-escalation attempt, step by step,
using **real CLI output** — not fabricated or illustrative.

## Setup

We have a refund-processing SOP that declares `payments:refund(max_amount=100.00)`
as a capability ceiling. An attacker tries to escalate to `max_amount=250.00`.

## Step 1: The SOP

The legitimate SOP requests a refund with a ceiling of $100:

```yaml
# tests/fixtures/refund-request-handling.sop.yaml (excerpt)
- id: issue_refund
  description: "Issue refund via payment provider"
  requires:
    capabilities: ["payments:refund(max_amount=100.00)"]
  on_success: notify_user
  on_failure: escalate_human
```

## Step 2: Compile Against the Policy

```
$ sopvm compile tests/fixtures/refund-request-handling.sop.yaml \
    --policy policies/support-agent.policy.yaml \
    -o examples/compiled-refund.ir.json
Compiled to examples/compiled-refund.ir.json
```

The compiler applies the policy ceiling. In the IR, `capabilities_paged` for
`issue_refund` contains the original request — which satisfies the policy's
`max_amount<=100.00` ceiling.

## Step 3: Check Passes (Legitimate SOP)

```
$ sopvm check examples/compiled-refund.ir.json \
    --policy policies/support-agent.policy.yaml
All capabilities within policy.
```

Exit code 0. The legitimate SOP is within policy.

## Step 4: Attacker Tampers with the IR

The attacker hand-edits the compiled IR to escalate the refund amount:

```json
{
  "ir_version": "0.1",
  "entry": "a",
  "nodes": {
    "a": {
      "capabilities_declared": ["payments:refund(max_amount=250.00)"],
      "capabilities_paged": ["payments:refund(max_amount=250.00)"],
      "edges": {},
      "terminal": true
    }
  }
}
```

## Step 5: Check Catches the Violation

```
$ sopvm check examples/violating.ir.json \
    --policy policies/support-agent.policy.yaml
VIOLATION step=a requested='payments:refund(max_amount=250.00)' reason=exceeds policy ceiling payments:refund(max_amount<=100.00)
```

Exit code 1. The static checker (M4) catches the policy violation at compile
time. The `max_amount=250.00` request exceeds the `max_amount<=100.00` ceiling.

## Step 6: Runtime Gate Catches It Too

Even if someone bypasses `sopvm check` and runs the tampered IR directly:

```python
from sopvm.runtime.executor import Executor, UnsupportedIrVersionError
from sopvm.ir.model import CompiledProgram, IrNode
from sopvm.capability.policy import Policy, load_policy
from sopvm.capability.token import parse_capability

# Load the tampered IR
program = CompiledProgram.from_json(open("examples/violating.ir.json").read())
policy = load_policy("policies/support-agent.policy.yaml")

# The executor re-validates capabilities_paged against the policy
# This catches IR tampering at runtime too
class DenyHandler:
    def execute(self, node, request_tool=None):
        from sopvm.runtime.state import StepState
        if request_tool:
            result = request_tool(parse_capability("payments:refund(max_amount=250.00)"), {})
            if not result.success:
                return StepState.DENIED
        return StepState.DONE

result = Executor(program, DenyHandler(), policy=policy).run()
print(f"Final state: {result.final_state.value}")
# Final state: DENIED
```

The runtime gate (M7) denies the tool call because `max_amount=250.00`
doesn't satisfy the policy ceiling `max_amount<=100.00`.

## Defense-in-Depth Summary

| Layer | What it catches | When |
|---|---|---|
| **Static checker (M4)** | Policy ceiling violations in the IR | Compile time (`sopvm check`) |
| **IR validation (M12)** | Tampered `capabilities_paged` in loaded IR | Runtime (executor startup) |
| **Capability gate (M7)** | Out-of-scope tool calls at execution time | Runtime (per tool call) |
| **Provider sandbox (M8)** | Lying providers invoking undeclared capabilities | Runtime (per invocation) |

Three independent layers. An attacker must bypass all three to escalate
a capability — and each layer catches a different class of attack.
