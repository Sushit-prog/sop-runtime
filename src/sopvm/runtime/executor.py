"""Runtime executor loop (Milestone 6 + 7).

Drives a ``CompiledProgram`` through a fixed state machine, calling a
``StepHandler`` at each step. M7 adds the capability gate: before any
tool call is invoked, it runs through ``CapabilityGate.enforce()``. If
denied, the step transitions to DENIED immediately — no retry, no
recovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from sopvm.capability.token import CapabilityToken
from sopvm.ir.model import CompiledProgram, IrNode

from .events import Event, noop_event
from .gate import CapabilityGate
from .state import StepState
from .violations import Violation


@runtime_checkable
class StepHandler(Protocol):
    """Protocol for step execution.

    The ``request_tool`` callback checks the capability gate. Returns
    True if the tool call is allowed, False if denied. If denied, the
    executor transitions the step to DENIED immediately.

    Handlers MUST call ``request_tool`` before any tool invocation.
    """

    def execute(
        self,
        node: IrNode,
        request_tool: Callable[[CapabilityToken], bool],
    ) -> StepState: ...


@dataclass(frozen=True)
class RunResult:
    """Result of a complete run.

    Attributes:
        final_state: The terminal state reached (DONE, FAILED, or DENIED).
        path: Ordered list of step ids that were executed.
        violation: If the run was denied, the Violation record; else None.
    """

    final_state: StepState
    path: tuple[str, ...]
    violation: Violation | None = None


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
        on_event: Callable[[Event], None] = noop_event,
        max_steps: int = 10000,
    ) -> None:
        self._program = program
        self._handler = handler
        self._on_event = on_event
        self._max_steps = max_steps
        self._gate = CapabilityGate()
        self._current_violation: Violation | None = None

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

            # Build the gate-wrapped request_tool callback
            def make_request_tool(sid: str, n: IrNode) -> Callable[[CapabilityToken], bool]:
                def request_tool(cap: CapabilityToken) -> bool:
                    violation = self._gate.enforce(sid, cap, n)
                    if violation is not None:
                        self._current_violation = violation
                        self._on_event(Event(
                            event_type="capability_denied",
                            step_id=sid,
                            extra={
                                "requested": cap.raw,
                                "reason": violation.reason,
                            },
                        ))
                        return False
                    return True
                return request_tool

            request_tool = make_request_tool(current_id, node)

            # Execute the step
            result = self._handler.execute(node, request_tool)

            # If a tool call was denied during execution, override result
            if self._current_violation is not None:
                result = StepState.DENIED

            # Emit end event
            self._on_event(Event(
                event_type="step_completed",
                step_id=current_id,
                extra={"state": result.value},
            ))

            # DENIED always terminates immediately — no retry, no recovery
            if result == StepState.DENIED:
                return RunResult(
                    final_state=StepState.DENIED,
                    path=tuple(path),
                    violation=self._current_violation,
                )

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
