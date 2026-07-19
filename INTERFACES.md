# SOPVM — INTERFACES.md (canonical contract doc)

Status: DRAFT skeleton. Every later milestone prompt must conform to this or explicitly call out a proposed change here first. This file is the single source of truth for cross-milestone shapes — no milestone may silently redefine a schema it doesn't own.

Ownership: each section names the milestone that *defines* it. Other milestones may *consume* it but not *redefine* it.

---

## 1. SOP Source Format (owned by M2)

Strict YAML, validated against a JSON Schema (`schemas/sop.schema.json`). No free-form prose fields feed the compiler — only structured fields do.

```yaml
sop_version: "0.1"
name: "refund-request-handling"
policy: "policies/support-agent.policy.yaml"   # top-level capability ceiling (see §3)

steps:
  - id: verify_identity
    description: "Confirm requester identity via order lookup"
    requires:
      capabilities: ["db:read(orders)"]
    on_success: check_eligibility
    on_failure: escalate_human

  - id: check_eligibility
    description: "Check refund policy eligibility"
    requires:
      capabilities: ["db:read(orders)", "db:read(policy_rules)"]
    on_success: issue_refund
    on_failure: escalate_human

  - id: issue_refund
    description: "Issue refund via payment provider"
    requires:
      capabilities: ["payments:refund(max_amount=100.00)"]
    on_success: notify_user
    on_failure: escalate_human

  - id: check_order_value
    description: "Check if order value exceeds $100"
    requires:
      capabilities: ["db:read(orders)"]
    condition: "Is the order value greater than $100?"
    on_success: high_value_approval
    on_failure: auto_approve

  - id: retry_api_check
    description: "Check if API is responding"
    requires:
      capabilities: ["net:http(health_check)"]
    condition: "Is the API responding with status 200?"
    on_success: api_ok
    on_failure: retry_api_check
    loop:
      max_iterations: 3
    on_limit: api_failed

  - id: notify_user
    terminal: true
    requires:
      capabilities: ["notify:email"]

  - id: escalate_human
    terminal: true
    requires:
      capabilities: ["notify:slack(channel=support-escalations)"]
```

Rules M2 must enforce at parse time:
- every `on_success`/`on_failure` target must resolve to a declared step id
- every non-terminal step must declare at least one outgoing edge
- `capabilities` entries must match the capability grammar in §3
- unreferenced steps (unreachable from the declared entry point) are a parse error, not a warning

---

## 2. AST (owned by M2)

Internal only — not a public contract, but shape is fixed here so M3 doesn't guess:

```
SopDocument
├── version: str
├── policy_ref: str
└── steps: list[StepNode]
     StepNode
     ├── id: str
     ├── description: str
     ├── requires: CapabilityRequest[]
     ├── edges: {on_success: str|None, on_failure: str|None}
     ├── terminal: bool
     ├── condition: str|None          # natural language condition to evaluate
     ├── loop: LoopConfig|None        # bounded loop configuration
     │    └── max_iterations: int
     └── on_limit: str|None           # edge to follow when loop limit hit
```

---

## 3. Capability Token Schema (owned by M4)

Auditable outside Python — `schemas/capability.schema.json`.

Grammar: `namespace:action(param=value, ...)` — parameterized, not a flat string enum (see MILESTONES.md risk #2).

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CapabilityToken",
  "type": "object",
  "required": ["namespace", "action", "params"],
  "properties": {
    "namespace": { "type": "string", "examples": ["fs", "net", "db", "payments", "notify"] },
    "action":    { "type": "string", "examples": ["read", "write", "http", "refund"] },
    "params":    { "type": "object", "additionalProperties": true },
    "raw":       { "type": "string", "description": "original string form, e.g. payments:refund(max_amount=100.00)" }
  }
}
```

Policy file (top-level ceiling a SOP may never exceed):

```yaml
# policies/support-agent.policy.yaml
policy_version: "0.1"
allowed_capabilities:
  - "db:read(orders)"
  - "db:read(policy_rules)"
  - "payments:refund(max_amount<=100.00)"
  - "notify:email"
  - "notify:slack(channel=support-escalations)"
```

Static checker (M4) contract: given a compiled IR + a policy file, return a `CheckResult`:

```json
{
  "passed": false,
  "violations": [
    {
      "step_id": "issue_refund",
      "requested": "payments:refund(max_amount=250.00)",
      "reason": "exceeds policy ceiling payments:refund(max_amount<=100.00)"
    }
  ]
}
```

This must be checkable **without running the runtime** — pure static analysis, usable as a pre-commit hook (M11).

---

## 4. IR / Program Graph (owned by M3, capability-annotated by M5)

```json
{
  "ir_version": "0.1",
  "entry": "verify_identity",
  "nodes": {
    "verify_identity": {
      "capabilities_declared": ["db:read(orders)"],
      "capabilities_paged": ["db:read(orders)"],
      "edges": { "on_success": "check_eligibility", "on_failure": "escalate_human" },
      "terminal": false
    },
    "check_order_value": {
      "capabilities_declared": ["db:read(orders)"],
      "capabilities_paged": ["db:read(orders)"],
      "edges": { "on_success": "high_value_approval", "on_failure": "auto_approve" },
      "terminal": false,
      "condition": "Is the order value greater than $100?"
    },
    "retry_api_check": {
      "capabilities_declared": ["net:http(health_check)"],
      "capabilities_paged": ["net:http(health_check)"],
      "edges": { "on_success": "api_ok", "on_failure": "retry_api_check" },
      "terminal": false,
      "condition": "Is the API responding with status 200?",
      "loop": { "max_iterations": 3 },
      "on_limit": "api_failed"
    }
  }
}
```

- `capabilities_declared`: what the source SOP asked for at this step (from AST, unchanged by compiler).
- `capabilities_paged`: what M5's paging-plan pass actually resolves as grantable *at this step* (may be a subset after policy intersection — never a superset of `capabilities_declared`).
- IR is the only artifact the runtime (M6) ever reads. The runtime never sees the AST or source YAML directly.

---

## 5. Runtime State Machine (owned by M6)

States per step: `PENDING → RUNNING → {DONE, FAILED, DENIED}`.

- `DENIED` is a distinct terminal state from `FAILED` — a capability violation is not an execution error, it's a policy event, and M10's telemetry must be able to tell them apart.
- Transition rules are a fixed table, not branching logic scattered through the executor — this table is what M12's adversarial tests assert against.

---

## 6. Tool Provider / Plugin Interface (owned by M8)

```python
class ToolProvider(Protocol):
    def declared_capabilities(self) -> list[str]: ...
    def invoke(self, capability: CapabilityToken, args: dict) -> ToolResult: ...
```

- `invoke` is never called directly by step logic — only by the gate (M7), which checks `capability` against `capabilities_paged` for the current step first.
- A provider that lies about `declared_capabilities()` (requests more at invoke time than it declared) is itself a `DENIED` event, not a crash.

---

## 7. Event / Telemetry Schema (owned by M10)

```json
{
  "event": "capability_denied",
  "step_id": "issue_refund",
  "requested": "payments:refund(max_amount=250.00)",
  "paged": ["payments:refund(max_amount<=100.00)"],
  "timestamp": "2026-07-18T12:00:00Z",
  "run_id": "..."
}
```

Event types (fixed enum, extend via versioning policy only): `step_started`, `step_completed`, `step_failed`, `capability_granted`, `capability_denied`, `run_started`, `run_completed`.

---

## 8. Public API (owned by M13, staged incrementally by M3/M6/M11)

```python
sopvm.compile(sop_path: str, policy_path: str) -> CompiledProgram
sopvm.check(compiled: CompiledProgram) -> CheckResult
sopvm.Runtime(compiled: CompiledProgram, providers: list[ToolProvider])
    .run() -> RunResult
```

Anything not in this list is internal and may change without a version bump.

---

## 9. CLI Contract (owned by M11)

```
sopvm compile <sop.yaml> --policy <policy.yaml> -o <out.ir.json>
sopvm check <out.ir.json> --policy <policy.yaml>        # exit 1 on violation, for pre-commit
sopvm run <out.ir.json> --providers <providers.yaml>
sopvm trace <run_id>                                     # replay telemetry
```

---

## 10. LangGraph Adapter (owned by M9)

Adapter module only — must not leak LangGraph types into M1–M8. Exposes SOPVM as a single callable node:

```python
def as_langgraph_node(compiled: CompiledProgram, providers: list[ToolProvider]) -> Callable
```

---

## Change control

Any edit to a section above after its owning milestone has merged requires:
1. A version bump to the affected schema (see VERSIONING_POLICY.md)
2. An explicit call-out in the milestone prompt that changes it, listing exactly which section of this file is being modified and why
