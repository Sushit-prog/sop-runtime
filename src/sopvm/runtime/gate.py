"""Capability gate (Milestone 7).

Intercepts tool-call requests and checks them against the current step's
``capabilities_paged``. This is the core enforcement mechanism: a tool
call can only proceed if its requested capability satisfies at least one
paged entry.

``DENIED`` is a terminal fact about a run, not a transient failure.
No retry logic. No silent swallowing.
"""

from __future__ import annotations

from sopvm.capability.token import CapabilityToken
from sopvm.checker.check import satisfies
from sopvm.ir.model import IrNode

from .violations import Violation


class CapabilityGate:
    """Checks tool-call requests against the current step's paged capabilities."""

    def check_call(
        self,
        step_id: str,
        requested: CapabilityToken,
        node: IrNode,
    ) -> bool:
        """Return True only if the requested capability is paged for this step.

        A capability is paged if it satisfies (via M4's ``satisfies()``)
        at least one entry in ``node.capabilities_paged``.
        """
        for paged_str in node.capabilities_paged:
            paged_token = CapabilityToken(
                namespace="", action="", params={}, raw=paged_str,
            )
            # Parse the paged string to get a proper token for satisfies()
            from sopvm.capability.token import parse_capability
            paged_token = parse_capability(paged_str)
            if satisfies(requested, paged_token):
                return True
        return False

    def enforce(
        self,
        step_id: str,
        requested: CapabilityToken,
        node: IrNode,
    ) -> Violation | None:
        """Check and enforce: returns a Violation if denied, None if allowed.

        This is the method the executor calls. If it returns a Violation,
        the step transitions to DENIED immediately — no retry, no recovery.
        """
        if self.check_call(step_id, requested, node):
            return None

        paged_tokens = [
            parse_capability(s) for s in node.capabilities_paged
        ]
        return Violation(
            step_id=step_id,
            requested=requested,
            paged=paged_tokens,
            reason=(
                f"capability {requested.raw!r} not satisfied by any "
                f"paged capability for step {step_id!r}"
            ),
        )


# Module-level import to avoid circular imports at module level
from sopvm.capability.token import parse_capability  # noqa: E402
