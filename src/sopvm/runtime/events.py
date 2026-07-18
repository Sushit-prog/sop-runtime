"""Runtime event hooks (Milestone 6).

Minimal Event dataclass and on_event callback type — just enough of a
hook that M10 (telemetry) can extend without refactoring this module's
call sites. The full event schema from INTERFACES.md §7 is M10's job.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Event:
    """A runtime event emitted during execution.

    Attributes:
        event_type: Event name (e.g. ``step_started``, ``step_completed``).
        step_id: The step this event relates to.
        extra: Arbitrary additional context. Kept as a plain dict so M10
            can extend without changing this dataclass's signature.
    """

    event_type: str
    step_id: str
    extra: dict[str, object] = field(default_factory=dict)


def noop_event(event: Event) -> None:
    """Default no-op event handler."""
