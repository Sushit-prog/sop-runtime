# Adversarial Security Test Suite (Milestone 12)

This corpus documents every adversarial test case, the escalation
technique it represents, and which enforcement layer catches it.

**Disclosure:** This corpus is self-designed, not an external benchmark.
It is not a substitute for professional penetration testing or formal
verification. The techniques are drawn from common privilege-escalation
patterns in capability-based systems and adapted to SOPVM's specific
attack surface.

## Test Matrix

| File | Test Case | Escalation Technique | Enforcement Layer |
|---|---|---|---|
| `test_escalation.py` | `test_amount_exceeds_ceiling` | Request `max_amount=250` vs policy ceiling `max_amount<=100` | Static checker (M4) |
| `test_escalation.py` | `test_unmentioned_namespace` | Call capability in namespace (`fs`) not mentioned in policy at all | Static checker (M4) |
| `test_escalation.py` | `test_malformed_param_name_space_in_key` | Param name with space (`max_ amount`) to bypass naive string equality | Static checker (M4) |
| `test_escalation.py` | `test_malformed_param_name_unicode_homoglyph` | Cyrillic `а` (U+0430) in param name to bypass string equality | Static checker (M4) |
| `test_escalation.py` | `test_action_name_homoglyph` | Cyrillic `ё` (U+0451) in action name — grammar rejects it | Static checker (M4) |
| `test_escalation.py` | `test_negative_amount_passes_numeric_check` | `-100 <= 100` is numerically true — documents limitation | Static checker (M4) |
| `test_gate.py` | `test_out_of_scope_different_namespace` | Cross-namespace call (`db:read` paged, `fs:write` requested) | Runtime gate (M7) |
| `test_gate.py` | `test_out_of_scope_same_namespace_different_action` | Same namespace, wrong action (`db:read` paged, `db:write` requested) | Runtime gate (M7) |
| `test_gate.py` | `test_near_miss_param_value_exceeds_ceiling` | Paged `max_amount<=100`, request `max_amount=250` | Runtime gate (M7) |
| `test_gate.py` | `test_near_miss_param_name_differs` | Paged `max_amount`, request `max_amount_v2` | Runtime gate (M7) |
| `test_gate.py` | `test_within_scope_not_denied` | Correct call within scope — must NOT be denied (false-positive check) | Runtime gate (M7) |
| `test_gate.py` | `test_multiple_caps_one_denied` | Two capabilities: first allowed, second denied | Runtime gate (M7) |
| `test_gate.py` | `test_denied_event_emitted` | Denied call triggers `capability_denied` telemetry event | Runtime gate (M7) + telemetry (M10) |
| `test_provider_integrity.py` | `test_sandbox_catches_lying_provider_without_gate` | Provider declares `db:read` but invokes `fs:write` | Provider sandbox (M8) |
| `test_provider_integrity.py` | `test_sandbox_catches_lying_provider_even_if_gate_bypassed` | Gate bypassed, sandbox still catches lying provider | Provider sandbox (M8) |
| `test_provider_integrity.py` | `test_gate_blocks_lying_provider_at_executor_level` | Gate blocks lying provider at executor level | Runtime gate (M7) |
| `test_provider_integrity.py` | `test_provider_within_scope_not_sandbox_denied` | Honest provider invoking its own declared capability | Provider sandbox (M8) |
| `test_ir_tampering.py` | `test_tampered_paged_capabilities_rejected` | Hand-edit IR JSON to add unauthorized paged capability | IR validation (M12) |
| `test_ir_tampering.py` | `test_tampered_paged_subset_accepted` | Hand-edit IR JSON to narrow paged capabilities (valid) | IR validation (M12) |
| `test_ir_tampering.py` | `test_no_policy_skips_validation` | No policy provided — validation skipped (backwards compat) | N/A (documented) |
| `test_grammar_exploits.py` | `test_semicolon_in_param` | `db:read(orders; DROP TABLE users)` — injection attempt | Capability grammar (M4) |
| `test_grammar_exploits.py` | `test_quotes_in_param` | `db:read("orders" OR "1"="1")` — SQL injection style | Capability grammar (M4) |
| `test_grammar_exploits.py` | `test_unicode_in_namespace` | Unicode chars in namespace to bypass ASCII-only regex | Capability grammar (M4) |
| `test_grammar_exploits.py` | `test_extremely_long_param` | 10KB param string to test parser robustness | Capability grammar (M4) |
| `test_grammar_exploits.py` | `test_nested_parens_in_param` | `db:read(a(b)c)` — nested parentheses | Capability grammar (M4) |

## Known Limitations (Documented, Not Patched)

### Provider Collusion (Out of Scope for v0.1)

Two providers, each individually within declared scope, whose COMBINED
effect a single-provider check wouldn't catch. Example: Provider A
declares `db:read(orders)` and Provider B declares `db:write(orders)`.
Each is within scope individually, but a step that calls both could
exfiltrate data (read via A, write via B).

**Why not patched:** This requires cross-step capability tracking and
information-flow analysis, which is a research-level problem. The M7
gate checks per-step, not per-run. Documenting this as a known
limitation is the honest choice for v0.1.

### Policy Tampering After Compile Time (Out of Scope for v0.1)

If you compile against policy A, then swap in policy B before running
`check`, the check passes against B (which may be more permissive).

**Why not patched:** The IR currently doesn't embed a policy hash.
Fixing this requires pinning the policy version/hash into the IR at
compile time and rejecting mismatches at check/run time. This is a
valuable hardening but is a new feature, not a gap to paper over.

## Running the Adversarial Suite

```bash
pytest tests/adversarial/ -v
```

This runs all adversarial tests. In CI, this suite is gated on every
PR — any unblocked escalation technique fails the build.
