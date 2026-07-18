# SOPVM — Architecture Design Document

**A runtime for compiling and safely executing Standard Operating Procedures with LLM agents**

Based on: *Compile, Then Page: Executable SOP Programs and a Capability-Gated Runtime for Procedural LLM Agents* (Yu, Yin, Yu, Yang, Li — HKPU / HKU / Zhejiang Normal University, arXiv:2607.11346)

---

## 0. Paper Analysis (Before Any Design Decisions)

I pulled the actual abstract before designing anything, because the title alone is easy to over-interpret in a direction the paper doesn't support — and one of those over-interpretations (below) matters a lot for scope.

**What the paper actually reports:**

- Enterprise agents need to follow long-horizon, conditional, safety-critical SOPs. Official SOP prose is often *unreliable as a control surface* — models don't consistently follow it.
- The authors **compile** SOP text into **executable pseudo-code** and run it on a **program-guided (PG) stack machine**. The stack machine **pages the active frame** — i.e., at any point in execution, the model is shown the *current* frame of the program (like a CPU/OS showing a working set), not the entire program at once, while an LLM performs the actual semantic work (deciding what a step "means" and whether a condition holds).
- A three-arm study (raw prose vs. compiled-but-unpaged vs. compiled-and-paged) across six models shows: **compiling to pseudo-code never significantly hurts, and helps by up to 16 points** over prose in the cases where prose underperforms.
- The **paging/runtime-guidance benefit is capability-gated** — but "capability" here means **model capability**, not a security capability token. Two strong models benefit clearly from active-frame paging (58:19 and 75:31 discordant-pair wins); **weak models are actively harmed by it**. An ablation that keeps the full program visible but adds a cursor recovers most of the strong-model gain, meaning the win is mostly about *state discipline* (the model reliably tracking "where am I"), not about hiding information.
- Their practical recommendation: **compile the SOP first (always safe), and only turn on active-frame paging after you've verified the model has the discipline to benefit from it** — otherwise you're removing context from a model that needed it.

**The naming trap to flag explicitly:** the paper's "capability-gated" refers to *gating an execution-mode feature (paging) on empirically measured model capability*. It is **not** a description of an object-capability / least-privilege security system for tool access (OAuth scopes, ACLs, etc.). Your task brief asks for a full production capability *security* model (GitHub, Slack, filesystem, email tool grants) — that's a legitimate and valuable thing to build, but it is **an engineering extension on top of the paper**, not something the paper itself studied. I'm designing both, and labeling which is which throughout, because conflating them would misrepresent the paper if you ever have to defend this design to someone who's read it (e.g., in an interview).

**Why current agent frameworks are insufficient (the gap this project fills):**

Frameworks like LangGraph, CrewAI, AutoGen, and even LiteLLM-adjacent orchestrators solve *how agents call tools and pass messages*. None of them solve *how do you guarantee a long, conditional, safety-critical procedure is followed the same way every time, in a way you can audit and gate by model quality*. Today, "following an SOP" mostly means "put it in the system prompt and hope." That's the gap. SOPVM is not a competitor to LangGraph — it's infrastructure that could sit *underneath* LangGraph, LlamaIndex agents, or a raw tool-calling loop, the same way LLVM sits underneath Clang/Rust/Swift rather than competing with any single language.

**What to implement faithfully vs. adapt vs. deliberately skip:**

| Category | Idea | Decision |
|---|---|---|
| Faithful | SOP → compiled pseudo-code IR, never-raw-prose-at-runtime | Implement. This is the core validated claim. |
| Faithful | Stack machine with an explicit "active frame" and cursor | Implement. This is the paging mechanism itself. |
| Faithful | Gate the paging *mode* on a measured model-capability/discipline check, not on vibes | Implement as a first-class runtime setting (`paging_mode: auto | always | never`) backed by a small built-in eval harness, not a hardcoded model allowlist. |
| Faithful | Full-program-visible-with-cursor as an intermediate mode | Implement as a third execution mode (`cursor-only`), since the paper shows it captures most of the benefit and is strictly safer to ship as a default than full paging. |
| Adapted for production | "Capability" as security/tool-permission gating | Build as a *separate*, clearly-named subsystem (object-capability model for tool access), not conflated with paging mode. This is standard infra practice (least privilege for tool-calling agents) and is what makes this look like real infra rather than a paper replica. |
| Adapted for production | SOPBench-style evaluation | Don't reimplement their benchmark exactly (it's a research artifact, not infra). Instead, ship a small, extensible "capability probe" harness: a handful of representative SOP programs + a scoring rubric you can point at any model/config to decide `auto` paging mode. This is inspired by SOPBench's *purpose*, not a port of it. |
| Intentionally not implemented | Multi-model comparative benchmarking infrastructure (six-model, three-arm statistical study tooling) | Out of scope. That's a research artifact for producing a paper's numbers, not something a runtime needs at v1. Document it as a "Phase 2 research mode" possibility, don't build it. |
| Intentionally not implemented | Novel model training / fine-tuning for discipline | Out of scope — SOPVM is a runtime, not a model-improvement project. If a model lacks discipline, SOPVM's answer is "downgrade to cursor-only or unpaged mode," not "let's fine-tune it." |
| Intentionally not implemented | General-purpose planning/goal-decomposition (turning a vague goal into an SOP) | Out of scope for v1. SOPVM consumes already-authored SOPs (this is explicit in your brief too — "already-defined procedures"). Auto-SOP-generation is a different, much fuzzier research problem and would dilute the infra story.

---

## 1. Problem Statement

**Target users**

- Platform/infra teams inside companies deploying LLM agents for customer support, finance ops, compliance workflows, IT helpdesk, or DevOps runbooks — anywhere a human SOP already exists and the company is nervous about an LLM "improvising" through it.
- Agent framework maintainers/integrators who want a safety/compliance execution layer they can bolt underneath an existing LangGraph or custom tool-calling loop instead of building one themselves.
- ML platform engineers who need auditability (what steps ran, what was skipped, what tool calls were gated and why) for an internal or external compliance review.

**Existing solutions and their shortcomings**

- **Prompt-only SOPs** (SOP text pasted into a system prompt): cheapest, most common, and — per the paper — measurably unreliable, with no structural guarantee the model tracks state, checks preconditions, or refuses out-of-policy branches.
- **General agent orchestrators (LangGraph, CrewAI, AutoGen)**: give you graphs/state machines for *agent-to-agent or agent-to-tool* control flow, but the "procedure" itself is still usually prose or ad hoc Python — there's no compiler, no IR, no static analysis pass over the procedure, and no first-class notion of "this model hasn't earned the right to run in reduced-context mode yet."
- **RPA (robotic process automation) tools** (UiPath, Power Automate): deterministic and auditable, but not built for the "an LLM has to interpret a judgment-call step" problem — they assume every step is scriptable, which is exactly the case SOPs-with-LLM-judgment don't satisfy.
- **Guardrail/validation libraries** (Guardrails AI, NeMo Guardrails, LMQL-style constrained decoding): operate on *output shape*, not on *procedure state*. They can validate that a single response is well-formed; they have no concept of "step 14 of 40, branch B, capability X currently held."

**Engineering tradeoffs SOPVM has to make explicit**

- Paging reduces context and (per the paper) can hurt weak models — so the runtime must default to the *safe* mode and require an explicit, measured opt-in to more aggressive paging, not the reverse.
- Full static analysis of an SOP (proving all branches terminate, all capabilities requested are grantable, etc.) is valuable but can't block v1 — ship a conservative subset (unreachable-branch detection, undeclared-capability detection, cycle/infinite-loop detection) and grow it.
- CPU-only development means the runtime itself must never assume local GPU inference; all "smartness" (semantic step execution) is delegated to an external LLM API call, and the runtime's own logic (parsing, scheduling, capability checks) has to be cheap enough to unit-test in CI on a laptop in seconds, not minutes.

---

## 2. High-Level Architecture

```
                         ┌─────────────────────────────┐
                         │   SOP Source (Markdown/YAML) │
                         │  human-authored procedure    │
                         └───────────────┬───────────────┘
                                         │
                                ┌────────▼────────┐
                                │      Parser      │  (grammar: sections,
                                │                   │   steps, conditions,
                                └────────┬────────┘   capability decls)
                                         │
                                ┌────────▼────────┐
                                │       AST        │
                                └────────┬────────┘
                                         │
                                ┌────────▼────────┐
                                │  IR Lowering      │  (stack-machine
                                │  (SOP-IR)         │   friendly ops)
                                └────────┬────────┘
                                         │
                       ┌─────────────────┼─────────────────┐
                       │                 │                 │
              ┌────────▼───────┐ ┌───────▼────────┐ ┌──────▼───────┐
              │ Static Analyzer │ │ Capability      │ │  Optimizer    │
              │ (unreachable    │ │ Allocator       │ │ (dead-branch  │
              │  branches, undecl. │ (binds declared  │  pruning,     │
              │  capabilities, │ │  capabilities to │ │  frame        │
              │  cycles)        │ │  policy scopes)  │ │  coalescing)  │
              └────────┬───────┘ └───────┬────────┘ └──────┬───────┘
                       └─────────────────┼─────────────────┘
                                         │
                                ┌────────▼────────┐
                                │ Executable        │  (SOP-bytecode:
                                │ Program (.sopc)    │   versioned,
                                └────────┬────────┘   content-hashed)
                                         │
════════════════════════════════════════▼══════════════════════════════════
                                    RUNTIME
                                         │
                                ┌────────▼────────┐
                                │    Scheduler      │  (turn loop, retry/
                                │                    │   timeout policy)
                                └────────┬────────┘
                                         │
                      ┌──────────────────┼──────────────────┐
                      │                  │                  │
             ┌────────▼───────┐ ┌────────▼────────┐ ┌───────▼────────┐
             │ Capability      │ │ Execution Engine  │ │ Paging Manager  │
             │ Manager         │ │ (stack machine:    │ │ (active-frame,  │
             │ (grants, checks,│ │  push/pop frames,  │ │  cursor-only,   │
             │  expiry, audit) │ │  LLM semantic call, │ │  full-visible   │
             └────────┬───────┘ │  branch/loop ops)   │ │  modes)         │
                      │          └────────┬────────┘ └───────┬────────┘
                      │                   │                   │
                      └───────────────────┼───────────────────┘
                                          │
                                 ┌────────▼────────┐
                                 │  Tool Drivers      │  (plugin ABI:
                                 │  (GitHub, Slack,   │   GitHub/Slack/FS/
                                 │   FS, Email, HTTP,  │   Email/HTTP/DB)
                                 │   DB)               │
                                 └────────┬────────┘
                                          │
                                 ┌────────▼────────┐
                                 │ Observability      │  (OTel traces,
                                 │ Layer               │   Prometheus
                                 └────────┬────────┘   metrics, structured
                                          │             logs, replay)
                                 ┌────────▼────────┐
                                 │  Audit Log         │  (append-only,
                                 │  (SQLite/Postgres)  │   hash-chained)
                                 └─────────────────┘
```

Design principle behind this shape: **the compiler never talks to a model, and the runtime never talks to raw SOP prose.** Everything the LLM sees at execution time came out of the compiler as a validated artifact. That boundary is what makes the system testable — the compiler is 100% deterministic and unit-testable without any API key; the runtime is the only layer that needs a live model, and even there, the *scheduling and capability logic* around the model call is deterministic and independently testable.

---

## 3. Compiler Design

**Parser**

- Input format: a constrained Markdown dialect plus YAML frontmatter for metadata (SOP id, version, declared capabilities, owner). Constrained Markdown, not a bespoke DSL, because SOPs are already written by non-engineers in Markdown/Confluence/Notion today — the adoption cost of "learn our DSL" kills infra tools. The parser recognizes a small set of structural markers (numbered steps, `IF/ELSE` blocks as a fenced sub-grammar, `REQUIRES capability: <name>` annotations, `CALL <tool>.<action>` lines) inside otherwise-normal Markdown.
- Grammar is a recursive-descent parser (hand-written, not a parser-generator dependency) — SOP grammar is small and stable enough that a generated parser (ANTLR/Lark) adds a heavyweight dependency for little benefit, and a hand-written parser gives much better error messages, which matters because your users are process owners, not engineers.
- Parser errors are the first UX surface non-engineers will see — every error carries a line number, the offending text, and a "did you mean" suggestion where feasible (e.g., unmatched `IF` without `ENDIF`).

**AST**

- Node types: `Procedure`, `Step` (leaf, delegated to LLM semantic execution), `Conditional` (branch), `Loop` (bounded — unbounded loops are a compile error unless an explicit max-iterations is declared), `ToolCall` (structured, not a leaf `Step`, because it needs capability binding), `CapabilityDeclaration`, `Precondition`/`Postcondition` assertions.
- AST is intentionally *not* Turing-complete. No arbitrary recursion, no dynamic step generation. This is a deliberate constraint (like a regular vs. context-free language tradeoff) — it's what makes static analysis (reachability, capability-safety, termination) tractable at all. Document this constraint prominently; it's a selling point ("we can prove things about your SOP because we don't let you write arbitrary code in it"), not a limitation to apologize for.

**IR (SOP-IR)**

- A flat, stack-machine-oriented instruction set: `PUSH_FRAME`, `POP_FRAME`, `EVAL_STEP <step_id>` (hands control to the LLM with the current frame), `BRANCH <cond_id> <true_target> <false_target>`, `LOOP_HEAD <max_iter>`, `LOOP_TAIL`, `REQUEST_CAP <cap_name> <scope>`, `RELEASE_CAP <cap_name>`, `CALL_TOOL <driver> <action> <arg_refs>`, `ASSERT <condition>`, `HALT <status>`.
- This is deliberately close to a real bytecode (think CPython bytecode or a tiny WASM subset) rather than staying as a tree, because the runtime's paging mechanism needs a linear instruction stream with an addressable cursor — "page N" only makes sense once you have addresses.
- IR is versioned and the compiled artifact is content-hashed (`.sopc` file = IR + metadata + hash), so the runtime can refuse to execute an SOP whose compiled artifact doesn't match its declared source hash — this is your first real supply-chain-style integrity guarantee and it's cheap to add.

**Static Analyzer**

- Reachability analysis: flag branches that can never be taken (dead SOP text — surprisingly common in real-world SOPs that accumulate cruft).
- Capability-safety analysis: every `CALL_TOOL` must be reachable only through a code path that has a preceding `REQUEST_CAP` for a capability whose scope covers that action. This is checked at compile time so you *cannot even build* an executable program that calls Slack without ever having declared it needs Slack access — this is the compile-time half of the capability story (the runtime does the dynamic half).
- Termination analysis: every `LOOP_HEAD` must have a statically-bounded `max_iter` or a provably-decreasing loop variable; otherwise it's a compile error, not a runtime timeout.

**Optimizer**

- Dead-branch elimination (using the reachability results above).
- Frame coalescing: adjacent steps with no branching or capability changes between them can be scheduled as a single "page" to reduce the number of LLM round-trips — this is a legitimate production optimization the paper doesn't need to care about (they're measuring accuracy, not latency/cost) but you should, since round-trips are money.
- This layer is intentionally small at v1 (2-3 passes). Resist the urge to build a general optimization pipeline; an over-built optimizer for a project this size reads as scope creep in a portfolio review, not sophistication.

**Validation**

- Schema validation of the YAML frontmatter (declared capabilities must reference a known plugin+action from the registered driver set, or compilation fails with a clear "unknown capability: slack.post_message — did you mean slack.send_message?" error).
- A `sopvm compile --check` mode that runs the full analyzer/validator without emitting an executable — this is your CI-friendly "lint my SOP" entry point, and it's the single most demo-able CLI command for a portfolio (fast, deterministic, no API key required).

**Executable generation**

- Output is a single `.sopc` file: JSON or MessagePack envelope containing IR instructions, the capability manifest, source hash, compiler version, and a step-to-source-line map (for good runtime error messages that point back at the original SOP text, not raw IR).

---

## 4. Runtime Design

**Execution engine**

- A genuine stack machine: an explicit call/frame stack (not just "call the LLM in a loop"). Each `Step` execution produces a `StepResult` (status, extracted state deltas, tool-call requests) that the engine validates against the IR before advancing the cursor. The LLM is *never* trusted to control the program counter directly — it proposes ("I believe the precondition for branch B holds"), the engine decides whether to actually branch, based on structured output the engine parses and validates, not on the model's free-text claim about what it did.

**Scheduler**

- Owns the turn loop: cursor → build a paging-mode-appropriate prompt from the current frame → call the model → validate structured output → advance state → repeat.
- Retry policy: transient tool/model failures get exponential backoff with a bounded retry count (configurable per-step, since a "read a file" step and a "send a payment" step should not share a retry policy); a step exceeding retries transitions the whole run to a `NEEDS_HUMAN` terminal state rather than silently failing.
- Timeout handling: both a per-step wall-clock timeout and a whole-run timeout; both are IR-declared (not just runtime config), so a compiled SOP is self-describing about its own time budget.
- Rollback: SOPVM does **not** attempt automatic multi-step compensation/rollback (that's a distributed-transactions problem, not something to bolt onto v1). Instead, every `CALL_TOOL` with side effects must declare an optional `on_failure` step reference in the SOP itself (author-specified compensating action), and the engine invokes it on failure. This is an honest, scoped answer instead of promising general rollback you can't deliver.
- Graceful failure: every terminal state (`COMPLETED`, `FAILED`, `NEEDS_HUMAN`, `CAPABILITY_DENIED`, `TIMEOUT`) is a first-class, audited status with a human-readable reason string, not an exception that bubbles up and gets swallowed.

**Execution context**

- A serializable `RunContext` object: run id, current frame stack, bound variables, held capabilities + their expiry, paging mode in effect, and full step history. Serializable specifically so that a run can be persisted and *resumed* — this matters for long-horizon SOPs that might span human-in-the-loop approval steps that take hours.

**Paging mechanism (the paper's core contribution, implemented directly)**

- Three modes, selectable per-run and overridable by the capability probe (below):
  - `full` — entire compiled program is in context every turn (safest for weak models per the paper's finding).
  - `cursor` — full program stays visible, but a cursor marker highlights the active frame (the ablation mode the paper shows captures most of the benefit).
  - `paged` — only the active frame (plus a small fixed window of prior-frame summaries) is in context (maximum context reduction, best result on strong/disciplined models, actively harmful on weak ones).
- A small built-in **capability probe harness**: a fixed set of representative SOP programs with known-correct execution traces, run once per (model, paging-mode) combination during setup, scored against expected refusal/branch behavior. The score decides whether `auto` mode is allowed to select `paged` for that model, or falls back to `cursor`/`full`. This operationalizes the paper's "verify discipline before enabling paging" recommendation as an actual runtime feature instead of a manual judgment call — and it's a great blog-post/README artifact ("here's our probe harness output for GPT-4o vs. a 7B open model").

---

## 5. Capability Model

Two capability concepts exist in this system and must stay visibly separate (see §0):

1. **Paging capability tier** — model-capability gating from the paper, described above. Not a security mechanism.
2. **Tool-access capability model** — a real object-capability security system, described here. This is the production security layer.

**Capability schema**

- A capability is `{name, driver, actions: [...], scope: {...constraints...}, granted_to: run_id, issued_at, expires_at, max_uses}`. Scopes are driver-specific structured constraints (e.g., for the filesystem driver, an allowed path prefix; for GitHub, a specific repo + allowed operations like `read_issue`/`comment`, explicitly excluding `merge_pr` unless separately granted).
- Capabilities are **unforgeable references**, not strings the model can produce — the LLM never sees or manipulates a capability token directly; it only requests an *action*, and the Capability Manager decides whether a currently-held capability covers that action. This is the classic object-capability principle (à la Cap'n Proto / seL4 capabilities) applied to LLM tool-calling instead of letting the model "know" a secret and trusting it not to leak it into output.

**Capability lifecycle**

- `Requested` (by `REQUEST_CAP` IR instruction at a specific compiled point) → `Granted` (by policy evaluation, see below) → `Active` (usable until expiry/use-limit) → `Expired`/`Revoked`/`Released`. Every transition is written to the audit log with the triggering IR instruction address.

**Capability inheritance**

- A parent frame's capabilities are visible to child frames pushed within its lexical scope (matches normal stack-scoping semantics), but a child frame **cannot escalate** — it can only request capabilities its enclosing frame's declared manifest allows, checked at compile time by the Capability Allocator and re-checked at runtime by the Capability Manager (defense in depth: don't trust the compiler alone at execution time).

**Capability expiration**

- Time-based (`expires_at`) and use-based (`max_uses`) expiry, whichever comes first. Default expiry is short (single-step scope) unless the SOP explicitly declares a wider `persist_for: <n_steps>` — narrow-by-default, widen-by-declaration, matching least-privilege norms.

**Capability verification**

- Every `CALL_TOOL` IR instruction is intercepted by the Capability Manager *before* it reaches a tool driver. Verification checks: (a) a matching active capability exists, (b) the requested action is within the capability's declared action set, (c) the requested arguments satisfy the capability's scope constraints (e.g., the file path is under the allowed prefix). Any failure produces a `CAPABILITY_DENIED` terminal or step-local failure (configurable), never a silent skip.

**Policy enforcement**

- A separate, pluggable `PolicyEngine` interface decides *whether to grant* a requested capability (the Capability Manager decides *whether a currently-held one applies*, which is different). Default implementation: static YAML policy (per-SOP, per-tenant) — "SOPs owned by team X may request `github.comment` but never `github.merge`." This is intentionally swappable (OPA/Rego integration is a documented extension point, not a v1 dependency) so the project doesn't force a specific policy language on adopters.

**Comparing alternative designs**

| Approach | Why not chosen as primary |
|---|---|
| Ambient authority (model can call any configured tool, checked only by driver-level API keys) | This is the status quo in most agent frameworks today and is exactly the failure mode SOPVM exists to fix — no least privilege, no per-run scoping, no auditable grant/deny trail. |
| RBAC (roles mapped to tool permissions, checked at the driver) | Simpler to implement, but roles are static and coarse — doesn't naturally express "this specific run, this specific step, this specific file path only," which is what an SOP actually needs. Kept as a *simplification* users can configure (a policy can just grant broad static roles), but the underlying primitive is capabilities, not roles, because capabilities are strictly more expressive and RBAC can be built on top of them (not the reverse). |
| Full formal capability calculus (verified via a theorem prover) | Correct in spirit, wildly disproportionate for a portfolio-stage v1. Documented as a "hardening" milestone, not built now. |

---

## 6. Plugin Architecture

**Design goals:** a plugin is the *only* place vendor-specific code lives; the compiler and runtime never import a vendor SDK directly.

**Plugin ABI (per driver):**

- `manifest()` → declares the driver name, version, and its **action catalog**: each action has a name, a JSON-Schema-typed argument spec, a required-capability-scope shape, and an idempotency flag (idempotent actions are safer to retry automatically; non-idempotent ones require explicit `on_failure`/confirmation handling upstream).
- `validate_config(config)` → called at deploy time (e.g., "is this GitHub token present and does it have the scopes this driver's actions need"), independent of any specific run.
- `execute(action, args, capability)` → the only method that actually performs I/O; receives the already-verified capability object (not raw credentials — the driver itself holds vendor credentials internally, scoped at deploy time, and the capability just proves the *SOP run* is authorized to trigger this specific action).
- `dry_run(action, args)` (optional but strongly encouraged) → returns what *would* happen without doing it; this is what powers a `sopvm run --dry-run` mode, which is one of the best trust-building features you can ship (let a compliance reviewer see the exact planned tool calls before any of them execute).

**Reference drivers to ship at v1 (breadth signals real infra, not a toy):**

- Filesystem (path-scoped read/write/list)
- HTTP (allowlisted-domain GET/POST, useful as the generic "call any internal API" escape hatch)
- GitHub (issue/PR read + comment; merge/close explicitly gated behind a stricter default policy)
- Slack (post message to a specific channel/thread)
- Email (send via a configured SMTP/API provider, recipient-domain scoped)
- Database (parameterized read-only queries against a declared connection; write actions are a documented but disabled-by-default capability)

Each driver's action catalog and required-capability-scope shape is generated into the docs site automatically from `manifest()`, so driver docs can never drift from actual driver behavior.

---

## 7. Observability

- **Metrics (Prometheus):** run counts by terminal status, step latency histograms, capability grant/deny counters (labeled by driver+action — this is your best security-relevant dashboard), paging-mode distribution, retry counts, tool-driver error rates.
- **Traces (OpenTelemetry):** one root span per run, one child span per frame/step (with the paging mode and cursor position as span attributes), one child span per tool call (with driver/action, *not* raw arguments, as attributes — avoid leaking sensitive tool-call payloads into trace backends by default, redaction is opt-out per driver at most, not opt-in).
- **Structured logs:** every state transition emitted as a structured (JSON) event with run id, step id, IR address, and terminal/intermediate status — designed to be trivially greppable/queryable, and to double as the input to replay.
- **Execution replay:** because `RunContext` is fully serializable and every LLM call + tool call is logged with its exact input/output, a completed or failed run can be replayed deterministically for tool calls (mocked from the log) while optionally re-invoking the LLM live (to test "would a newer model handle this differently"). This is a genuinely differentiating feature versus most agent frameworks and maps directly to your existing langgraph-replay project's DNA — worth cross-referencing it in the README as "sibling project, applied to SOP execution specifically."
- **Audit log:** append-only, hash-chained (each entry includes the hash of the previous entry) table of every capability grant/deny and every tool call, stored in SQLite for local dev / Postgres for production. Hash-chaining is a small addition that turns "we have logs" into "we have logs a customer's auditor can trust weren't edited after the fact" — cheap, high perceived-value.

---

## 8. Public API

**Python API (primary integration surface):**

- `sopvm.compile(source_path) -> CompiledProgram`
- `sopvm.Runtime(compiled_program, policy_engine, drivers=[...], paging_mode="auto")`
- `runtime.run(inputs: dict) -> RunResult` (sync) and `runtime.run_async(...)` (async, since most agent-framework integrations are async-first)
- `runtime.on(event: str, callback)` — callback hooks for `step_started`, `step_completed`, `capability_denied`, `run_completed`, etc., so this can be embedded inside a LangGraph node or any other framework's loop rather than requiring you to hand over your whole application's control flow.

**CLI:**

- `sopvm compile <file> [--check]`
- `sopvm run <compiled.sopc> --input inputs.json [--dry-run] [--paging-mode auto|full|cursor|paged]`
- `sopvm probe <model-config>` — runs the capability probe harness and prints/stores the recommended paging mode for that model
- `sopvm replay <run_id>`
- `sopvm audit <run_id>` — pretty-prints the hash-chained audit trail for a run

**Middleware:**

- A framework-agnostic ASGI/WSGI-style middleware pattern isn't the right fit here (this isn't a web framework); instead, "middleware" = the `on()` hook system above plus a small `Interceptor` interface (`before_step`, `after_step`, `before_tool_call`) that lets adopters inject cross-cutting logic (custom logging, extra policy checks) without forking the runtime.

**FastAPI endpoints (optional reference server, not required to use the library):**

- `POST /compile`, `POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/audit`, `POST /runs/{id}/resume` (for `NEEDS_HUMAN` states). Shipped as a separate `sopvm-server` package/extra, not baked into the core library, so embedders aren't forced to run a web server just to use the runtime in-process.

**Callbacks:** covered by the `on()` event system above — deliberately one mechanism, not both a callback list and a separate event bus, to avoid two ways to do the same thing.

**Configuration:** a single `sopvm.toml` (or environment variables, 12-factor style) covering driver credentials/config, default policy file path, default paging mode, and observability exporters (OTel endpoint, Prometheus port). Config schema is versioned from day one specifically to **avoid future breaking changes**, per your brief — v1 ships with a `config_version` field and the loader is written to reject unknown-version configs loudly rather than silently misinterpreting them.

---

## 9. Repository Structure

```
sopvm/
├── sopvm/                      # core library (installable package)
│   ├── compiler/
│   │   ├── parser.py           # Markdown+YAML SOP grammar → AST
│   │   ├── ast.py               # AST node definitions
│   │   ├── ir.py                 # SOP-IR instruction set + lowering
│   │   ├── analyzer.py          # reachability, capability-safety, termination checks
│   │   ├── optimizer.py         # dead-branch elim, frame coalescing
│   │   └── codegen.py           # .sopc artifact emission
│   ├── runtime/
│   │   ├── engine.py             # stack machine
│   │   ├── scheduler.py          # turn loop, retry/timeout policy
│   │   ├── paging.py              # full/cursor/paged mode implementations
│   │   ├── context.py             # RunContext (serializable state)
│   │   └── probe.py                # capability probe harness
│   ├── capabilities/
│   │   ├── manager.py              # grant/verify/expire
│   │   ├── policy.py                # PolicyEngine interface + default YAML impl
│   │   └── schema.py                # capability data model
│   ├── drivers/
│   │   ├── base.py                  # plugin ABI
│   │   ├── filesystem.py
│   │   ├── http.py
│   │   ├── github.py
│   │   ├── slack.py
│   │   ├── email.py
│   │   └── database.py
│   ├── observability/
│   │   ├── tracing.py                # OTel setup
│   │   ├── metrics.py                # Prometheus exporters
│   │   ├── audit.py                   # hash-chained audit log
│   │   └── replay.py                  # deterministic replay engine
│   └── api.py                          # public Python API surface (compile/Runtime)
├── sopvm_server/                # optional FastAPI reference server (separate installable extra)
├── cli/                          # `sopvm` CLI entrypoint
├── examples/                    # end-to-end example SOPs (onboarding, incident response, refund policy)
│   └── each with: .md source, compiled .sopc (checked in), expected-run fixtures
├── tests/
│   ├── unit/                     # compiler + capability + scheduler unit tests (no API key needed)
│   ├── integration/              # runtime + mock drivers, using a fake/local LLM stub
│   └── probe_fixtures/            # capability-probe reference SOPs + expected traces
├── docs/
│   ├── architecture.md            # this document, trimmed for public consumption
│   ├── writing_sops.md             # authoring guide for non-engineers
│   ├── driver_guide.md              # how to write a new plugin
│   └── generated/                    # auto-generated driver action catalogs
├── benchmarks/                   # optional GPU-benchable, CPU-skippable perf/paging-mode comparisons
├── .github/workflows/            # CI: lint, unit tests, integration tests, docs build
├── pyproject.toml
├── CONTRIBUTING.md
├── SECURITY.md                    # capability model + responsible disclosure process
└── README.md
```

Every top-level folder maps to a section in this document (compiler/, runtime/, capabilities/, drivers/, observability/) — a reviewer who reads this design doc should be able to open the repo and immediately know where anything lives.

---

## 10. Milestones

Each milestone is scoped so the repo is fully working (installable, CI-green, documented) at every step — no "big bang" integration milestone.

1. **Parser + AST for a minimal SOP subset** (linear steps only, no branches/loops/capabilities). `sopvm compile --check` works end-to-end. CI green with unit tests.
2. **IR + codegen for the same minimal subset.** `.sopc` artifacts are emitted and content-hashed. Add `examples/hello-sop`.
3. **Minimal runtime: execute a linear `.sopc` against a real LLM API in `full` paging mode only.** First end-to-end demo (`sopvm run`), with a single mock-friendly driver (filesystem) for tool calls.
4. **Add branching + bounded loops to parser/AST/IR/runtime.** Static analyzer v1: reachability + termination checks.
5. **Capability schema + Capability Manager + compile-time capability-safety analysis.** No policy engine yet — default-allow, but every grant/check is logged.
6. **Policy engine (YAML-based) + deny-by-default enforcement.** `SECURITY.md` written. This is the milestone where the "capability-gated" security story becomes real and demo-able (`sopvm run --dry-run` showing a denied call).
7. **Plugin ABI formalized + two more drivers (HTTP, GitHub) beyond filesystem.** Driver docs auto-generated from manifests.
8. **Observability: structured logs + audit log (hash-chained) + `sopvm audit` CLI command.**
9. **OpenTelemetry tracing + Prometheus metrics wired through scheduler/engine/capability manager.**
10. **`cursor` and `paged` execution modes implemented; capability probe harness (v1: 3-5 fixture SOPs + scoring) + `sopvm probe` CLI.** This is the milestone that makes the paper's core finding tangible in the repo.
11. **Retry/timeout/rollback (`on_failure`) policy + `NEEDS_HUMAN`/resume support in scheduler and Python API.**
12. **Execution replay engine**, reusing/cross-referencing patterns from your existing langgraph-replay project.
13. **Remaining reference drivers (Slack, Email, Database) + optional `sopvm-server` FastAPI package.**
14. **Optimizer passes (dead-branch elimination, frame coalescing) + benchmark suite (CPU-only default path, optional GPU/local-model bench documented separately).**
15. **Hardening pass: expand static analyzer coverage, expand probe fixtures, write `docs/writing_sops.md`, polish README/examples for public release, tag v1.0.**

---

## 11. Risks

**Technical risks**

- *Structured-output reliability from the LLM* (the engine depends on parsing valid step results/branch decisions). Mitigation: strict JSON-schema-constrained output where the provider supports it, with a validation-and-single-retry-then-fail-closed policy otherwise — never silently guess at malformed output.
- *Static analysis false confidence* — passing the analyzer doesn't prove runtime safety, only the checked properties. Mitigation: document analyzer guarantees precisely (what it does and does not prove) rather than implying more than it delivers.

**Scalability risks**

- *Audit log write amplification* at high run volume (every capability check + tool call is logged). Mitigation: batched/async writes with an explicit durability tradeoff documented, and Postgres (not SQLite) as the documented production target from the start.
- *Probe harness staleness* — a model's measured discipline can drift across provider-side model updates. Mitigation: probe results are versioned and tied to a model+version identifier, with a documented "re-run probe after any model upgrade" operational practice, surfaced as a CLI warning if a probe result is older than a configurable staleness window.

**Security risks**

- *Capability confused-deputy risk* if a driver ever accepts raw args without re-validating scope itself (defense only at the manager layer). Mitigation: driver ABI requires drivers to re-check scope locally too (defense in depth, explicit in `driver_guide.md`).
- *Credential handling in drivers* — vendor tokens must never flow through the LLM context. Mitigation: capability objects passed to `execute()` never contain raw credentials; drivers hold credentials from deploy-time config only.

**Maintainability risks**

- *Grammar creep* — a constrained Markdown grammar with too many one-off authoring conveniences becomes an unmaintainable parser. Mitigation: any new grammar feature requires an accompanying analyzer rule or it's rejected (keeps the "provable SOP" property from eroding).
- *Plugin sprawl without a stable ABI* — six drivers at v1 is a commitment to keep an ABI stable. Mitigation: ABI versioning from milestone 7 onward, with a driver compatibility matrix in docs.

---

## Closing note on positioning

This document deliberately keeps the "paging is model-capability-gated" finding and the "tool access is object-capability-gated" security design as two clearly separate stories, even though your original brief's Section 5 asked for the latter under the paper's title. That separation is itself worth stating explicitly in the README's "Relation to the paper" section — it signals to a technical reader (exactly the audience you're building this repo for) that you read the paper carefully rather than pattern-matching on its title, which is precisely the kind of judgment a hiring committee for an infra role is trying to screen for.
