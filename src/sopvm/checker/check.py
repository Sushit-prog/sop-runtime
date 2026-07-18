"""Static capability checker (Milestone 4).

Deterministic, side-effect-free: checks a compiled IR against a policy
without any I/O beyond loading the input files. This is the project's
headline claim — pure static analysis, usable as a pre-commit hook.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sopvm.capability.policy import Policy
from sopvm.capability.token import CapabilityToken, parse_capability
from sopvm.ir.model import CompiledProgram


@dataclass(frozen=True)
class Violation:
    """A single capability policy violation.

    Attributes:
        step_id: The step that requested the violating capability.
        requested: The raw capability string that was requested.
        reason: Human-readable explanation of why it was denied.
    """

    step_id: str
    requested: str
    reason: str


@dataclass(frozen=True)
class CheckResult:
    """Result of a static capability check.

    Attributes:
        passed: True if no violations were found.
        violations: List of violations (empty if passed).
    """

    passed: bool
    violations: tuple[Violation, ...] = field(default_factory=tuple)


def satisfies(requested: CapabilityToken, allowed: CapabilityToken) -> bool:
    """Check if a requested capability satisfies a policy ceiling.

    Rules:
    - namespace and action must match exactly.
    - For each param in ``allowed`` that has a comparator (``<=``, ``>=``,
      ``<``, ``>``, ``==``), the corresponding param in ``requested`` must
      satisfy it numerically.
    - Params in ``allowed`` without comparators must match exactly.
    - Params in ``requested`` not mentioned in ``allowed`` are unconstrained
      (allowed is a ceiling, not an exact-match contract).

    Design note: this means a request can carry extra params beyond what
    the policy mentions, and still pass. This is intentional — the policy
    is a ceiling on constrained dimensions, not a whitelist of all params.
    This choice is flagged for discussion in the PR description.
    """
    if requested.namespace != allowed.namespace:
        return False
    if requested.action != allowed.action:
        return False

    for key, allowed_val in allowed.params.items():
        requested_val = requested.params.get(key)
        if requested_val is None:
            # Param in allowed but not in requested — violation.
            return False

        if isinstance(allowed_val, dict):
            # Comparator param in policy ceiling.
            op = allowed_val["op"]
            ceiling = allowed_val["value"]
            if not _compare(requested_val, op, ceiling):
                return False
        elif allowed_val is True:
            # Bare param in allowed — requested must also have bare param.
            if requested_val is not True:
                return False
        else:
            # Named param — exact match.
            if requested_val != allowed_val:
                return False

    return True


def _compare(
    requested: str | float,
    op: str,
    ceiling: str | float,
) -> bool:
    """Evaluate a single comparator constraint."""
    req = _to_float(requested)
    ceil = _to_float(ceiling)
    if req is None or ceil is None:
        # Non-numeric values: only == and != are meaningful.
        if op == "==":
            return requested == ceiling
        return False

    if op == "<=":
        return req <= ceil
    elif op == ">=":
        return req >= ceil
    elif op == "<":
        return req < ceil
    elif op == ">":
        return req > ceil
    elif op == "==":
        return req == ceil
    return False


def _to_float(v: str | float) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def check(program: CompiledProgram, policy: Policy) -> CheckResult:
    """Static check: does every declared capability satisfy the policy?

    For every ``IrNode``, for every capability in ``capabilities_declared``,
    check it against every entry in ``policy.allowed_capabilities``. If
    none satisfy, record a violation.

    Malformed capability strings are caught and reported as violations
    rather than raising exceptions — the checker must not crash on bad input.

    This function is fully deterministic and side-effect-free.
    """
    from sopvm.capability.token import CapabilityGrammarError

    violations: list[Violation] = []

    for step_id, node in program.nodes.items():
        for cap_str in node.capabilities_declared:
            try:
                token = parse_capability(cap_str)
            except CapabilityGrammarError:
                violations.append(Violation(
                    step_id=step_id,
                    requested=cap_str,
                    reason=f"malformed capability string {cap_str!r}",
                ))
                continue

            if not any(satisfies(token, allowed) for allowed in policy.allowed_capabilities):
                # Find the ceiling for the reason message.
                matching = [
                    a for a in policy.allowed_capabilities
                    if a.namespace == token.namespace and a.action == token.action
                ]
                if matching:
                    ceiling_str = matching[0].raw
                    reason = f"exceeds policy ceiling {ceiling_str}"
                else:
                    reason = f"capability {cap_str!r} not mentioned in policy"

                violations.append(Violation(
                    step_id=step_id,
                    requested=cap_str,
                    reason=reason,
                ))

    return CheckResult(
        passed=len(violations) == 0,
        violations=tuple(violations),
    )
