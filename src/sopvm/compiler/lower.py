"""AST -> IR lowering pass (Milestone 3).

Converts a validated ``SopDocument`` (from M2) into a ``CompiledProgram``
(IR) that the runtime (M6) can execute. This pass is a direct 1:1
mapping — no optimization, no policy resolution, no analysis.

``capabilities_paged`` is set equal to ``capabilities_declared`` as a
placeholder. M5 replaces it with the real policy-resolved subset.
"""

from __future__ import annotations

from sopvm.ir.model import CompiledProgram, IrLoop, IrNode
from sopvm.parser.ast import SopDocument

from .errors import LoweringError


def lower(doc: SopDocument) -> CompiledProgram:
    """Lower a validated ``SopDocument`` AST to a ``CompiledProgram`` IR.

    Args:
        doc: A fully validated AST from the M2 parser.

    Returns:
        A ``CompiledProgram`` with one ``IrNode`` per step.

    Raises:
        LoweringError: If the AST has an unexpected shape (defensive
            assertion — should not occur after M2 validation).
    """
    if not doc.steps:
        raise LoweringError("cannot lower an empty document (no steps)")

    entry = doc.steps[0].id
    nodes: dict[str, IrNode] = {}

    for step in doc.steps:
        if step.id in nodes:
            raise LoweringError(f"duplicate step id: {step.id!r}")

        caps = [c.raw for c in step.requires]
        edges = {}
        if step.edges:
            on_ok, on_err = step.edges
            if on_ok is not None:
                edges["on_success"] = on_ok
            if on_err is not None:
                edges["on_failure"] = on_err

        loop = None
        if step.loop is not None:
            loop = IrLoop(max_iterations=step.loop.max_iterations)

        nodes[step.id] = IrNode(
            capabilities_declared=caps,
            capabilities_paged=list(caps),  # M5 placeholder
            edges=edges,
            terminal=step.terminal,
            condition=step.condition,
            loop=loop,
            on_limit=step.on_limit,
        )

    return CompiledProgram(
        ir_version="0.1",
        entry=entry,
        nodes=nodes,
    )
