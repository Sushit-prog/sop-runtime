"""Adversarial security-boundary tests.

Each test case represents a specific escalation technique an attacker
(or a confused SOP author) might use to exceed a policy ceiling.
"""

import pytest

from sopvm.capability.policy import Policy
from sopvm.capability.token import parse_capability
from sopvm.checker.check import check
from sopvm.ir.model import CompiledProgram, IrNode


def _program(nodes: dict[str, list[str]]) -> CompiledProgram:
    """Build a minimal CompiledProgram from {step_id: [cap_strings]}."""
    ir_nodes = {}
    for sid, caps in nodes.items():
        ir_nodes[sid] = IrNode(
            capabilities_declared=caps,
            capabilities_paged=list(caps),
            edges={},
            terminal=True,
        )
    first = next(iter(nodes))
    return CompiledProgram(ir_version="0.1", entry=first, nodes=ir_nodes)


def _policy(*cap_strs: str) -> Policy:
    return Policy(
        policy_version="0.1",
        allowed_capabilities=tuple(parse_capability(c) for c in cap_strs),
    )


# --- Escalation technique: amount exceeding the policy ceiling ---------------
# SOP requests max_amount=250.00 but policy caps at max_amount<=100.00.
# A naive string-equality check would compare "max_amount=250.00" against
# "max_amount<=100.00" and might pass if it doesn't parse the comparator.
def test_amount_exceeds_ceiling():
    prog = _program({"issue_refund": ["payments:refund(max_amount=250.00)"]})
    policy = _policy("payments:refund(max_amount<=100.00)")
    result = check(prog, policy)
    assert result.passed is False
    assert result.violations[0].step_id == "issue_refund"
    assert "250" in result.violations[0].requested
    assert "exceeds" in result.violations[0].reason


# --- Escalation technique: namespace not in policy at all -------------------
# A capability in a namespace (fs) that the policy never mentions.
# A policy that only checks "does some entry share the same action name"
# would incorrectly pass this.
def test_unmentioned_namespace():
    prog = _program({"exfil": ["fs:write(/etc/shadow)"]})
    policy = _policy("db:read(orders)", "notify:email")
    result = check(prog, policy)
    assert result.passed is False
    assert "not mentioned" in result.violations[0].reason


# --- Escalation technique: subtly malformed param name ----------------------
# "max_ amount" (space in key) vs "max_amount" — a naive string-equality
# check on the param name would treat these as different keys and might
# skip the ceiling comparison entirely.
def test_malformed_param_name_space_in_key():
    prog = _program({"x": ["payments:refund(max_ amount=250.00)"]})
    policy = _policy("payments:refund(max_amount<=100.00)")
    result = check(prog, policy)
    assert result.passed is False
    assert len(result.violations) == 1


# --- Escalation technique: unicode homoglyph in param name -----------------
# "mаx_amount" (Cyrillic 'а' U+0430) vs "max_amount" (Latin 'a' U+0061).
# A byte-level equality check would see these as different keys.
def test_malformed_param_name_unicode_homoglyph():
    # Cyrillic 'а' (U+0430) instead of Latin 'a' (U+0061)
    prog = _program({"x": ["payments:refund(m\u0430x_amount=250.00)"]})
    policy = _policy("payments:refund(max_amount<=100.00)")
    result = check(prog, policy)
    # The homoglyph param is treated as a bare resource name, so the
    # real param "max_amount" is absent from the request — the ceiling
    # check catches this as "exceeds policy ceiling".
    assert result.passed is False
    assert "exceeds" in result.violations[0].reason


# --- Escalation technique: action name homoglyph ---------------------------
# "refund" vs "refunԁ" (with a Cyrillic 'd' U+0451 or similar).
# The policy allows "payments:refund(...)" but the SOP requests
# "payments:refunԁ(...)" — a visually identical but semantically different
# action that bypasses string-equality on the action field.
def test_action_name_homoglyph():
    # Cyrillic 'ё' (U+0451) looks like Latin 'd' — rejected by grammar
    prog = _program({"x": ["payments:refun\u0451(max_amount=50)"]})
    policy = _policy("payments:refund(max_amount<=100.00)")
    result = check(prog, policy)
    # The non-ASCII character causes a grammar error, which check()
    # converts to a violation rather than crashing.
    assert result.passed is False
    assert "malformed" in result.violations[0].reason


# --- Escalation technique: negative amount bypassing <= ---------------------
# A value of -100 satisfies max_amount<=100 numerically, but might be
# semantically invalid (negative refund). This test documents that the
# checker enforces the numerical constraint as specified — it does NOT
# add semantic validation beyond the comparator.
def test_negative_amount_passes_numeric_check():
    prog = _program({"x": ["payments:refund(max_amount=-100.00)"]})
    policy = _policy("payments:refund(max_amount<=100.00)")
    result = check(prog, policy)
    # -100 <= 100 is numerically true — checker passes it.
    # Semantic validation of negative amounts is out of scope for M4.
    assert result.passed is True
