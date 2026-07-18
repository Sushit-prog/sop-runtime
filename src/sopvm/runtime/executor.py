"""Runtime executor loop (Milestone 6 + 7 + 8).

Drives a ``CompiledProgram`` through a fixed state machine, calling a
``StepHandler`` at each step. M7 adds the capability gate. M8 adds
provider routing: approved calls go through ``ProviderRegistry.lookup()``
→ ``wrap_provider()`` → ``invoke()``, applying both SOP-level scope
(M7 gate) and provider-integrity (M8 sandbox) checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from sopvm.capability.token import CapabilityToken
from sopvm.ir.model import CompiledProgram, IrNode
from sopvm.plugins.base import ToolResult
from sopvm.plugins.registry import ProviderRegistry
from sopvm.plugins.sandbox import wrap_provider

from .events import Event, noop_event
from .gate import CapabilityGate
from .state import StepState
from .violations import Violation


@runtime_checkable
class StepHandler(Protocol):
    """Protocol for step execution.

    The ``request_tool`` callback:
    1. Checks the capability gate (M7)
    2. Looks up the provider in the registry (M8)
    3. Wraps the provider with sandbox integrity checks (M8)
    4. Invokes the provider
    5. Returns a ``ToolResult``

    If the gate denies, ``request_tool`` returns a failed ``ToolResult``
    and the executor transitions the step to DENIED.
    """

    def execute(
        self,
        node: IrNode,
        request_tool: Callable[[CapabilityToken, dict], ToolResult],
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
        registry: Optional provider registry for tool routing (M8).
        max_steps: Safety limit to prevent infinite loops. Defaults to
            10000; raised to a large value if needed.
    """

    def __init__(
        self,
        program: CompiledProgram,
        handler: StepHandler,
        on_event: Callable[[Event], None] = noop_event,
        registry: ProviderRegistry | None = None,
        max_steps: int = 10000,
    ) -> None:
        self._program = program
        self._handler = handler
        self._on_event = on_event
        self._registry = registry
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

            # Build the gate+registry-wrapped request_tool callback
            def make_request_tool(sid: str, n: IrNode) -> Callable[[CapabilityToken, dict], ToolResult]:
                def request_tool(cap: CapabilityToken, args: dict) -> ToolResult:
                    # M7 gate check
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
                        return ToolResult(
                            success=False,
                            error=f"capability denied: {violation.reason}",
                        )

                    # M8 provider routing
                    if self._registry is not None:
                        provider = self._registry.lookup(cap)
                        if provider is None:
                            return ToolResult(
                                success=False,
                                error=f"no provider registered for {cap.raw!r}",
                            )
                        sandboxed = wrap_provider(provider)
                        try:
                            return sandboxed.invoke(cap, args)
                        except Exception as e:
                            return ToolResult(success=False, error=str(e))

                    # No registry — return a stub success
                    return ToolResult(success=True)

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
