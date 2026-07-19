"""Capability annotation / paging plan pass (Milestone 5).

Replaces M3's placeholder logic (``capabilities_paged = capabilities_declared``)
with the real policy-resolved subset. For every ``IrNode``, each capability
in ``capabilities_declared`` is tested against the policy via ``satisfies()``.
Only capabilities that satisfy at least one policy entry are included in
``capabilities_paged``; the rest are silently omitted.

This pass does NOT raise on denied capabilities — that's the static
checker's job (M4/M11). A step with zero ``capabilities_paged`` is a
valid, representable state; it just means that step can do nothing until
the checker/runtime flags it elsewhere.
"""

from __future__ import annotations

from sopvm.capability.policy import Policy
from sopvm.capability.token import parse_capability
from sopvm.checker.check import satisfies
from sopvm.ir.model import CompiledProgram, IrNode


def apply_paging(program: CompiledProgram, policy: Policy) -> CompiledProgram:
    """Compute the policy-resolved ``capabilities_paged`` for every node.

    Returns a new ``CompiledProgram`` — the input is never mutated.

    For each capability in ``capabilities_declared``, if it satisfies
    some entry in ``policy.allowed_capabilities``, it is included in
    the new node's ``capabilities_paged``. Otherwise it is omitted
    (silently narrowed — no error raised).
    """
    new_nodes: dict[str, IrNode] = {}

    for step_id, node in program.nodes.items():
        paged: list[str] = []
        for cap_str in node.capabilities_declared:
            token = parse_capability(cap_str)
            if any(satisfies(token, allowed) for allowed in policy.allowed_capabilities):
                paged.append(cap_str)

        new_nodes[step_id] = IrNode(
            capabilities_declared=list(node.capabilities_declared),
            capabilities_paged=paged,
            edges=dict(node.edges),
            terminal=node.terminal,
            condition=node.condition,
            loop=node.loop,
            on_limit=node.on_limit,
        )

    return CompiledProgram(
        ir_version=program.ir_version,
        entry=program.entry,
        nodes=new_nodes,
    )
