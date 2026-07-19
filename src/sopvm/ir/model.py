"""IR (Intermediate Representation) data model.

Shapes are defined canonically in INTERFACES.md §4. This module
implements the exact field names and types specified there.

CompiledProgram and IrNode are immutable (frozen=True). The IR is a
build artifact of lowering a specific AST; nothing downstream should
ever mutate it in place.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class IrNode:
    """A single node in the compiled IR program graph.

    Attributes:
        capabilities_declared: Capability strings the source SOP asked
            for at this step (from AST, unchanged by compiler).
        capabilities_paged: What the paging-plan pass resolves as
            grantable at this step. In M3 this is always identical to
            ``capabilities_declared`` — M5 replaces this with the real
            policy-resolved subset.
        edges: Outgoing edges dict with keys ``on_success`` and/or
            ``on_failure``, each mapping to a target step id string.
            Empty dict for terminal steps.
        terminal: Whether this step is a terminal (end) step.
    """

    capabilities_declared: list[str] = field(default_factory=list)
    capabilities_paged: list[str] = field(default_factory=list)
    edges: dict[str, str] = field(default_factory=dict)
    terminal: bool = False


@dataclass(frozen=True)
class CompiledProgram:
    """The root IR node: one compiled SOP program.

    Attributes:
        ir_version: IR schema version.
        entry: The id of the first step (entry point).
        nodes: Mapping from step id to ``IrNode``.
        policy_ref: Path to the policy file used during compilation.
    """

    ir_version: str
    entry: str
    nodes: dict[str, IrNode] = field(default_factory=dict)
    policy_ref: str = ""

    def to_json(self) -> str:
        """Serialize to a JSON string with deterministic key ordering."""
        return json.dumps(self._to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str) -> CompiledProgram:
        """Deserialize from a JSON string."""
        d = json.loads(text)
        nodes = {
            k: IrNode(
                capabilities_declared=v["capabilities_declared"],
                capabilities_paged=v["capabilities_paged"],
                edges=v["edges"],
                terminal=v["terminal"],
            )
            for k, v in d["nodes"].items()
        }
        return cls(
            ir_version=d["ir_version"],
            entry=d["entry"],
            nodes=nodes,
            policy_ref=d.get("policy_ref", ""),
        )

    def _to_dict(self) -> dict:
        return {
            "ir_version": self.ir_version,
            "entry": self.entry,
            "policy_ref": self.policy_ref,
            "nodes": {
                k: {
                    "capabilities_declared": v.capabilities_declared,
                    "capabilities_paged": v.capabilities_paged,
                    "edges": v.edges,
                    "terminal": v.terminal,
                }
                for k, v in self.nodes.items()
            },
        }
