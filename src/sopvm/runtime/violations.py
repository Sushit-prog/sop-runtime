"""Capability violation records (Milestone 7).

Returned by the capability gate when a tool call is denied. Carries
enough context for M10's telemetry to report it as a policy event,
distinct from execution errors.
"""

from __future__ import annotations

from dataclasses import dataclass

from sopvm.capability.token import CapabilityToken


@dataclass(frozen=True)
class Violation:
    """A denied capability request at runtime.

    Attributes:
        step_id: The step that attempted the denied call.
        requested: The capability token that was requested.
        paged: The capabilities that were paged (grantable) for this step.
        reason: Human-readable explanation of why it was denied.
    """

    step_id: str
    requested: CapabilityToken
    paged: list[CapabilityToken]
    reason: str
