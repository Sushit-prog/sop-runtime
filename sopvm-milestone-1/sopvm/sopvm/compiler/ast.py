"""AST node definitions for the minimal (linear) SOP subset.

Milestone 1 supports procedures made of an ordered, non-branching list
of steps declared after a YAML frontmatter block and a title heading.
Branches, loops, tool calls, and capability declarations are added in
later milestones (see docs/architecture.md, sections 3-5) and are
intentionally absent from this module — adding them here early would
let the runtime start depending on AST shapes the analyzer hasn't been
built to check yet.

Both node types are immutable (`frozen=True`). The AST is a build
artifact of parsing a specific source file; nothing downstream should
ever mutate it in place, since the same `Procedure` object is expected
to be safely shared between the CLI, the (future) IR lowering pass,
and any caller that compiled a SOP once and wants to inspect it
multiple times.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Step:
    """A single leaf step in a linear SOP.

    Step *execution* semantics (i.e. what it means for an LLM to
    "perform" this step) belong to the runtime (milestone 3+), not the
    AST. The AST only records what was written and where, so the
    compiler stays fully deterministic and requires no model access.

    Attributes:
        index: The 1-indexed step number as declared in the source
            (e.g. ``3`` for a line starting with ``3.``). Steps are
            required to be declared sequentially starting at 1 — see
            `sopvm.compiler.parser` for the validation that enforces
            this before a `Step` is ever constructed.
        text: The step body, whitespace-trimmed. May span multiple
            source lines (continuation lines with no leading step
            number are folded into the previous step's text).
        source_line: The 1-indexed line number in the original source
            file where this step's numbering token (e.g. ``3.``)
            appears. Used to produce line-accurate diagnostics in
            later compiler phases and runtime error messages.
    """

    index: int
    text: str
    source_line: int


@dataclass(frozen=True)
class Procedure:
    """The root AST node: one compiled SOP document.

    Attributes:
        id: The SOP's stable identifier, from the frontmatter ``id``
            field. Used later (milestone 5+) as the unit capability
            declarations and policies are scoped to.
        version: The SOP's author-declared version number, from the
            frontmatter ``version`` field.
        owner: A free-text owner/team identifier, from the
            frontmatter ``owner`` field.
        title: The procedure's human-readable title, taken from the
            first ``# `` heading in the document body.
        steps: The ordered, 1-indexed sequence of `Step` nodes. Always
            non-empty for a successfully parsed `Procedure` — the
            parser rejects SOPs with zero steps.
        source_path: The path the document was parsed from, if any.
            ``None`` when parsing from an in-memory string (e.g. in
            tests). Purely informational; never used for control flow.
    """

    id: str
    version: int
    owner: str
    title: str
    steps: tuple[Step, ...] = field(default_factory=tuple)
    source_path: str | None = None
