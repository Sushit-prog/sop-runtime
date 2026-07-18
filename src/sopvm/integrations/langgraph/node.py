"""LangGraph adapter node (Milestone 9).

Exposes SOPVM as a single callable node for LangGraph's StateGraph.
This module is the ONLY place in the codebase allowed to import
langgraph — enforced by an AST-based import boundary test.

Per INTERFACES.md §10:

    def as_langgraph_node(compiled: CompiledProgram, providers: list[ToolProvider]) -> Callable
"""

from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from sopvm.capability.token import parse_capability
from sopvm.ir.model import CompiledProgram
from sopvm.plugins.base import ToolProvider, ToolResult
from sopvm.plugins.registry import ProviderRegistry
from sopvm.runtime.executor import Executor, RunResult
from sopvm.runtime.state import StepState


class _SopvmHandler:
    """Step handler that routes tool calls through the provider registry."""

    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def execute(self, node, request_tool: Callable) -> StepState:
        """Default handler: succeeds if no tool calls are needed.

        For real usage, replace this handler or extend with LLM-based
        semantic execution (future milestone).
        """
        return StepState.DONE


def as_langgraph_node(
    compiled: CompiledProgram,
    providers: list[ToolProvider] | None = None,
    state_mapper: Callable[[RunResult, dict], dict] | None = None,
) -> Callable[[dict], dict]:
    """Wrap a compiled SOP as a LangGraph StateGraph node.

    Args:
        compiled: The compiled SOP program to execute.
        providers: Optional list of tool providers for capability routing.
        state_mapper: Optional callback to map ``RunResult`` into the
            calling graph's state shape. Defaults to a minimal mapper
            that sets ``sopvm_result`` and ``sopvm_path`` keys.

    Returns:
        A callable matching LangGraph's node signature (state in, state out).
    """
    # Build provider registry
    registry = ProviderRegistry()
    if providers:
        for p in providers:
            registry.register(p)

    # Build default state mapper
    if state_mapper is None:
        def _default_mapper(result: RunResult, state: dict) -> dict:
            return {
                **state,
                "sopvm_result": result.final_state.value,
                "sopvm_path": list(result.path),
                "sopvm_violation": result.violation,
            }
        state_mapper = _default_mapper

    def node_fn(state: dict) -> dict:
        handler = _SopvmHandler(registry)
        executor = Executor(
            program=compiled,
            handler=handler,
            registry=registry if providers else None,
        )
        result = executor.run()
        return state_mapper(result, state)

    return node_fn
