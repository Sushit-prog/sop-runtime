"""Telemetry sinks (Milestone 10).

TelemetrySink protocol and implementations. A sink receives Events and
stores/forwards them. Failures in a sink must never crash the run it's
observing — degraded logging, not exceptions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from .events import Event


@runtime_checkable
class TelemetrySink(Protocol):
    """Protocol for telemetry event sinks."""

    def emit(self, event: Event) -> None:
        """Emit a telemetry event. Must not raise."""
        ...


class JsonlSink:
    """Append-only JSONL file sink — one JSON object per line."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: Event) -> None:
        """Append the event as a JSON line. Never raises."""
        try:
            record = {
                "event": event.event,
                "step_id": event.step_id,
                "timestamp": event.timestamp,
                "run_id": event.run_id,
                **event.extra,
            }
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, sort_keys=True) + "\n")
        except Exception:
            # Telemetry failure must not crash the run
            pass


class InMemorySink:
    """In-memory sink for testing — stores events in a list."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        """Store the event in memory."""
        self.events.append(event)
