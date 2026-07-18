"""Runtime executor loop (Milestone 6).

Drives a ``CompiledProgram`` through a fixed state machine, calling a
``StepHandler`` at each step. No tool-calling logic yet — the handler
is a protocol that returns DONE/FAILED only (DENIED comes from M7's
capability gate).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sopvm.ir.model import CompiledProgram, IrNode

from .events import Event, noop_event
from .state import StepState


@runtime_checkable
class StepHandler(Protocol):
    """Protocol for step execution.

    M6 implementations return DONE or FAILED. M7 adds the capability
    gate that can return DENIED.
    """

    def execute(self, node: IrNode) -> StepState: ...


@dataclass(frozen=True)
class RunResult:
    """Result of a complete run.

    Attributes:
        final_state: The terminal state reached (DONE, FAILED, or DENIED).
        path: Ordered list of step ids that were executed.
    """

    final_state: StepState
    path: tuple[str, ...]


class ExecutorError(Exception):
    """Raised on malformed graph or infinite-loop detection."""


class Executor:
    """Drives execution of a ``CompiledProgram``.

    Args:
        program: The compiled IR program to execute.
        handler: Callback that executes a single step.
        on_event: Optional event callback (default: no-op).
        max_steps: Safety limit to prevent infinite loops. Defaults to
            10000; raised to a large value if needed.
    """

    def __init__(
        self,
        program: CompiledProgram,
        handler: StepHandler,
        on_event: callable[[Event], None] = noop_event,
        max_steps: int = 10000,
    ) -> None:
        self._program = program
        self._handler = handler
        self._on_event = on_event
        self._max_steps = max_steps

    def run(self) -> RunResult:
        """Execute the program to completion.

        Returns:
            A ``RunResult`` with the final state and execution path.

        Raises:
            ExecutorError: If the graph is malformed or the step limit
                is exceeded (infinite-loop detection).
        """
        path: list[str] = []
        current_id = self._program.entry
        step_count = 0

        while True:
            if current_id not in self._program.nodes:
                raise ExecutorError(
                    f"step {current_id!r} not found in program"
                )

            node = self._program.nodes[current_id]
            path.append(current_id)
            step_count += 1

            if step_count > self._max_steps:
                raise ExecutorError(
                    f"step limit exceeded ({self._max_steps}) — "
                    f"possible infinite loop"
                )

            # Emit start event
            self._on_event(Event(
                event_type="step_started",
                step_id=current_id,
            ))

            # Execute the step
            result = self._handler.execute(node)

            # Emit end event
            self._on_event(Event(
                event_type="step_completed",
                step_id=current_id,
                extra={"state": result.value},
            ))

            # DENIED always terminates immediately
            if result == StepState.DENIED:
                return RunResult(final_state=StepState.DENIED, path=tuple(path))

            # Determine next step based on handler result + terminal flag
            if node.terminal:
                # Terminal step: handler result determines final state
                return RunResult(final_state=result, path=tuple(path))

            # Non-terminal step: follow edge based on handler result
            edge_key = "on_success" if result == StepState.DONE else "on_failure"
            next_id = node.edges.get(edge_key)
            if next_id is None:
                raise ExecutorError(
                    f"step {current_id!r} is non-terminal but has no "
                    f"{edge_key} edge"
                )
            current_id = next_id
