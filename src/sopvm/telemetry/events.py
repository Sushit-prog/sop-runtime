"""Telemetry event schema (Milestone 10).

Per INTERFACES.md §7:

    {
      "event": "capability_denied",
      "step_id": "issue_refund",
      "requested": "payments:refund(max_amount=250.00)",
      "paged": ["payments:refund(max_amount<=100.00)"],
      "timestamp": "2026-07-18T12:00:00Z",
      "run_id": "..."
    }

Event types (fixed enum, extend via versioning policy only):
    step_started, step_completed, step_failed, capability_granted,
    capability_denied, run_started, run_completed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, unique


@unique
class EventType(Enum):
    """Fixed set of event types. Extend via versioning policy only."""

    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    CAPABILITY_GRANTED = "capability_granted"
    CAPABILITY_DENIED = "capability_denied"
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"


@dataclass(frozen=True)
class Event:
    """A telemetry event emitted during execution.

    Attributes:
        event: Event type name (must be a valid ``EventType`` value).
        step_id: The step this event relates to (empty for run-level events).
        timestamp: ISO8601 UTC timestamp.
        run_id: Unique run identifier (uuid4).
        extra: Arbitrary additional context (e.g. requested/paged for
            capability_denied events).
    """

    event: str
    step_id: str
    timestamp: str
    run_id: str
    extra: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        valid = {e.value for e in EventType}
        if self.event not in valid:
            raise ValueError(
                f"unknown event type {self.event!r}; "
                f"valid types: {', '.join(sorted(valid))}"
            )


def new_event(
    event_type: EventType | str,
    step_id: str = "",
    run_id: str = "",
    extra: dict[str, object] | None = None,
) -> Event:
    """Create an Event with automatic timestamp.

    Args:
        event_type: The event type (EventType enum or string value).
        step_id: The step this event relates to.
        run_id: The run identifier.
        extra: Additional context.
    """
    if isinstance(event_type, EventType):
        event_type = event_type.value
    return Event(
        event=event_type,
        step_id=step_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        run_id=run_id,
        extra=extra or {},
    )
