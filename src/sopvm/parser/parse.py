"""YAML SOP parser (Milestone 2).

Parses a YAML SOP file into a typed AST, validating against the JSON
Schema (INTERFACES.md §1) and performing semantic checks (edge target
resolution, reachability, capability grammar).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft7Validator, ValidationError

from .ast import CapabilityRequest, SopDocument, StepNode
from .errors import ParseError, SchemaValidationError, SemanticError

_CAPABILITY_RE = re.compile(
    r"^[a-zA-Z_][a-zA-Z0-9_]*:[a-zA-Z_][a-zA-Z0-9_]*(?:\(.*\))?$"
)

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "sop.schema.json"
_schema: dict | None = None


def _load_schema() -> dict:
    global _schema
    if _schema is None:
        _schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return _schema


def parse(path: str | Path) -> SopDocument:
    """Parse a YAML SOP file into a ``SopDocument`` AST.

    Args:
        path: Filesystem path to the YAML SOP file.

    Returns:
        A validated ``SopDocument``.

    Raises:
        SchemaValidationError: If the YAML fails JSON Schema validation.
        SemanticError: If a semantic rule is violated (unresolved edge
            targets, non-terminal without edges, unreachable steps,
            malformed capability strings).
    """
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(raw, dict):
        raise SchemaValidationError(
            f"expected a YAML mapping, got {type(raw).__name__}",
            path=[],
        )

    # --- JSON Schema validation -------------------------------------------
    schema = _load_schema()
    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(raw))
    if errors:
        err = errors[0]  # report the first schema violation
        schema_path = list(err.absolute_path)
        raise SchemaValidationError(
            f"schema validation failed: {err.message}",
            path=schema_path,
            cause=err.message,
        )

    # --- Build AST --------------------------------------------------------
    doc = SopDocument(
        version=raw["sop_version"],
        policy_ref=raw["policy"],
        steps=tuple(_build_step(s) for s in raw["steps"]),
    )

    # --- Semantic checks --------------------------------------------------
    _check_edges(doc)
    _check_reachability(doc)
    _check_capability_grammar(doc)

    return doc


def _build_step(raw: dict) -> StepNode:
    caps = tuple(CapabilityRequest(raw=c) for c in raw["requires"]["capabilities"])
    return StepNode(
        id=raw["id"],
        description=raw.get("description"),
        requires=caps,
        edges=(raw.get("on_success"), raw.get("on_failure")),
        terminal=raw.get("terminal", False),
    )


def _check_edges(doc: SopDocument) -> None:
    ids = {s.id for s in doc.steps}
    for step in doc.steps:
        if step.terminal:
            continue
        on_ok, on_err = step.edges
        if on_ok is None and on_err is None:
            raise SemanticError(
                f"non-terminal step '{step.id}' has no outgoing edges",
                step_id=step.id,
            )
        for target in (on_ok, on_err):
            if target is not None and target not in ids:
                raise SemanticError(
                    f"step '{step.id}' references unknown target '{target}'",
                    step_id=step.id,
                )


def _check_reachability(doc: SopDocument) -> None:
    if not doc.steps:
        return
    ids = {s.id for s in doc.steps}
    edges: dict[str, set[str]] = {s.id: set() for s in doc.steps}
    for s in doc.steps:
        for t in s.edges:
            if t is not None:
                edges[s.id].add(t)

    entry = doc.steps[0].id
    visited: set[str] = set()
    queue = [entry]
    while queue:
        current = queue.pop()
        if current in visited:
            continue
        visited.add(current)
        queue.extend(edges.get(current, set()) - visited)

    unreachable = ids - visited
    if unreachable:
        raise SemanticError(
            f"unreachable steps: {', '.join(sorted(unreachable))}",
        )


def _check_capability_grammar(doc: SopDocument) -> None:
    for step in doc.steps:
        for cap in step.requires:
            if not _CAPABILITY_RE.match(cap.raw):
                raise SemanticError(
                    f"malformed capability string '{cap.raw}' in step '{step.id}'",
                    step_id=step.id,
                )
