"""AST node definitions for the YAML SOP grammar (Milestone 2).

Shapes are defined canonically in INTERFACES.md §2. This module does
not redefine them — it implements the exact field names and types
specified there.

All node types are immutable (frozen=True). The AST is a build
artifact of parsing a specific source file; nothing downstream should
ever mutate it in place.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityRequest:
    """A single capability string as written in the SOP source.

    Full structured parsing of the parameter payload is M4's job.
    M2 only stores the raw string and checks the surface grammar
    (namespace:action(params)).
    """

    raw: str


@dataclass(frozen=True)
class StepNode:
    """A single step in the SOP graph.

    Attributes:
        id: Stable step identifier (matches ``^[a-zA-Z_][a-zA-Z0-9_]*$``).
        description: Human-readable description of the step.
        requires: Capability requests declared by this step.
        edges: ``(on_success, on_failure)`` — each is a target step id
            or ``None``. Both may be ``None`` only when ``terminal`` is True.
        terminal: Whether this step is a terminal (end) step.
    """

    id: str
    description: str | None
    requires: tuple[CapabilityRequest, ...]
    edges: tuple[str | None, str | None]  # (on_success, on_failure)
    terminal: bool


@dataclass(frozen=True)
class SopDocument:
    """The root AST node: one parsed SOP document.

    Attributes:
        version: SOP version string (from ``sop_version``).
        policy_ref: Path to the policy file (from ``policy``).
        steps: Ordered sequence of steps. Always non-empty for a
            successfully parsed document.
    """

    version: str
    policy_ref: str
    steps: tuple[StepNode, ...]
