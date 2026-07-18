"""Minimal LangGraph integration example (Milestone 9).

Demonstrates wrapping a compiled SOP as a LangGraph StateGraph node.
This is a reference implementation — not production-ready without an
actual LLM-based StepHandler.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from sopvm.compiler.pipeline import compile_sop
from sopvm.integrations.langgraph.node import as_langgraph_node


class SopState(TypedDict, total=False):
    sopvm_result: str
    sopvm_path: list[str]
    sopvm_violation: object


def build_sop_graph(
    sop_path: str,
    policy_path: str,
) -> StateGraph:
    """Build a LangGraph StateGraph with the SOP as a single node."""
    compiled = compile_sop(sop_path, policy_path)
    sop_node = as_langgraph_node(compiled)

    graph = StateGraph(SopState)
    graph.add_node("sop", sop_node)
    graph.add_edge(START, "sop")
    graph.add_edge("sop", END)
    return graph


if __name__ == "__main__":
    # Example usage
    graph = build_sop_graph(
        sop_path="tests/fixtures/refund-request-handling.sop.yaml",
        policy_path="policies/support-agent.policy.yaml",
    )
    compiled_graph = graph.compile()
    result = compiled_graph.invoke({})
    print(f"Result: {result}")
