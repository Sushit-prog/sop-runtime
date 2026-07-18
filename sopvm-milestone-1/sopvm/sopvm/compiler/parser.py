"""Parser for the minimal (linear) SOP grammar — Milestone 1.

Grammar (informal, Milestone 1 subset only):

    <document>   ::= "---\\n" <frontmatter> "---\\n" <body>
    <frontmatter> ::= YAML mapping with required keys: id, version, owner
    <body>        ::= <blank-lines>? <title> <blank-lines>? <steps>
    <title>       ::= "# " <text>
    <steps>       ::= <step>+
    <step>        ::= "<N>. " <text> <continuation-line>*

Steps must be numbered sequentially starting at 1. Branches, loops,
tool calls (`CALL ...`), and capability declarations (`REQUIRES ...`)
are not part of this grammar yet — see docs/architecture.md sections
3-6 for where they land in later milestones.

This is a hand-written, line-oriented parser rather than a
parser-generator (ANTLR/Lark) output. The grammar above is small and
stable enough that a generated parser would add a heavyweight
dependency for little benefit, and a hand-written parser gives much
better, more specific error messages — which matters here because
SOP authors are typically process owners, not engineers, and the
error message is effectively the product.

The parser deliberately collects as many independent diagnostics as
it safely can in a single pass (see `SOPParseErrors`) rather than
stopping at the first problem, with two exceptions: a completely
missing or unterminated frontmatter block. Both make it impossible to
even locate where the document body starts, so those two cases raise
immediately with a single error.
"""

from __future__ import annotations

import difflib
import re

import yaml

from .ast import Procedure, Step
from .errors import SOPParseError, SOPParseErrors

_STEP_RE = re.compile(r"^(\d+)\.\s+(.*)$")
_REQUIRED_FRONTMATTER_FIELDS = ("id", "version", "owner")


def parse(text: str, *, source_path: str | None = None) -> Procedure:
    """Parse SOP source text into a `Procedure` AST.

    Args:
        text: The raw SOP document source.
        source_path: Optional path the text was read from, recorded on
            the returned `Procedure` for diagnostics purposes only.

    Returns:
        A fully validated `Procedure`.

    Raises:
        SOPParseErrors: If the document violates the grammar or fails
            semantic validation (missing/invalid frontmatter fields,
            missing title, no steps, non-sequential step numbering).
    """
    lines = text.splitlines()
    errors: list[SOPParseError] = []

    # --- Frontmatter block boundaries -----------------------------------
    if not lines or lines[0].strip() != "---":
        raise SOPParseErrors(
            [
                SOPParseError(
                    "a SOP file must start with a YAML frontmatter block "
                    "delimited by '---' lines",
                    line=1,
                )
            ]
        )

    closing_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            closing_idx = i
            break

    if closing_idx is None:
        raise SOPParseErrors(
            [
                SOPParseError(
                    "unterminated frontmatter block: no closing '---' found",
                    line=1,
                )
            ]
        )

    # --- Frontmatter content ---------------------------------------------
    frontmatter_text = "\n".join(lines[1:closing_idx])
    frontmatter: dict = {}
    try:
        loaded = yaml.safe_load(frontmatter_text)
        if loaded is None:
            errors.append(
                SOPParseError(
                    "frontmatter block is empty; expected id/version/owner fields",
                    line=1,
                )
            )
        elif not isinstance(loaded, dict):
            errors.append(
                SOPParseError(
                    f"frontmatter must be a YAML mapping, got: {type(loaded).__name__}",
                    line=1,
                )
            )
        else:
            frontmatter = loaded
    except yaml.YAMLError as exc:
        errors.append(SOPParseError(f"invalid YAML in frontmatter: {exc}", line=1))

    present_keys = list(frontmatter.keys())
    missing_fields = [k for k in _REQUIRED_FRONTMATTER_FIELDS if k not in frontmatter]
    for key in missing_fields:
        close = difflib.get_close_matches(key, present_keys, n=1, cutoff=0.6)
        errors.append(
            SOPParseError(
                f"missing required frontmatter field: {key!r}",
                line=1,
                suggestion=close[0] if close else None,
            )
        )

    fm_id = frontmatter.get("id")
    if "id" in frontmatter:
        if not isinstance(fm_id, str) or not fm_id.strip():
            errors.append(
                SOPParseError(
                    f"frontmatter field 'id' must be a non-empty string, got: {fm_id!r}",
                    line=1,
                )
            )
            fm_id = None

    fm_owner = frontmatter.get("owner")
    if "owner" in frontmatter:
        if not isinstance(fm_owner, str) or not fm_owner.strip():
            errors.append(
                SOPParseError(
                    f"frontmatter field 'owner' must be a non-empty string, got: {fm_owner!r}",
                    line=1,
                )
            )
            fm_owner = None

    fm_version = frontmatter.get("version")
    if "version" in frontmatter:
        if isinstance(fm_version, bool) or not isinstance(fm_version, int):
            errors.append(
                SOPParseError(
                    f"frontmatter field 'version' must be an integer, got: {fm_version!r}",
                    line=1,
                )
            )
            fm_version = None

    # --- Title -------------------------------------------------------------
    idx = closing_idx + 1
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1

    title: str | None = None
    title_failed = False
    if idx >= len(lines):
        errors.append(
            SOPParseError(
                "missing title heading: expected a line starting with '# ' "
                "after the frontmatter block",
                line=closing_idx + 2,
            )
        )
        title_failed = True
        steps_start_idx = idx
    elif not lines[idx].startswith("# "):
        errors.append(
            SOPParseError(
                f"expected a title heading (a line starting with '# '), "
                f"found: {lines[idx].strip()!r}",
                line=idx + 1,
            )
        )
        title_failed = True
        steps_start_idx = idx  # don't consume; still try to parse steps from here
    else:
        candidate = lines[idx][2:].strip()
        if not candidate:
            errors.append(
                SOPParseError("title heading must not be empty", line=idx + 1)
            )
            title_failed = True
        else:
            title = candidate
        steps_start_idx = idx + 1

    # --- Steps ---------------------------------------------------------------
    steps: list[Step] = []
    current: dict | None = None
    expected_index = 1
    seen_numbers: set[int] = set()

    def flush_current() -> None:
        nonlocal current
        if current is not None:
            step_text = "\n".join(current["lines"]).strip()
            steps.append(
                Step(
                    index=current["index"],
                    text=step_text,
                    source_line=current["source_line"],
                )
            )
            current = None

    i = steps_start_idx
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        match = _STEP_RE.match(line)
        if match:
            flush_current()
            num = int(match.group(1))
            rest = match.group(2).strip()
            if num in seen_numbers:
                errors.append(
                    SOPParseError(f"duplicate step number {num}", line=i + 1)
                )
            else:
                if num != expected_index:
                    errors.append(
                        SOPParseError(
                            "steps must be numbered sequentially starting at "
                            f"1; expected step {expected_index}, found step {num}",
                            line=i + 1,
                        )
                    )
                seen_numbers.add(num)
                expected_index = num + 1
            current = {
                "index": num,
                "lines": [rest] if rest else [],
                "source_line": i + 1,
            }
        elif stripped == "":
            flush_current()
        else:
            if current is not None:
                current["lines"].append(stripped)
            else:
                errors.append(
                    SOPParseError(
                        f"unexpected content outside of a numbered step: {stripped!r}",
                        line=i + 1,
                    )
                )
        i += 1
    flush_current()

    if not title_failed and not steps:
        errors.append(
            SOPParseError(
                "no steps found: a SOP must declare at least one numbered "
                "step (e.g. '1. Do the thing.')",
                line=min(steps_start_idx + 1, len(lines) + 1),
            )
        )

    if errors:
        raise SOPParseErrors(errors)

    return Procedure(
        id=fm_id,  # type: ignore[arg-type]  # guaranteed non-None: no errors means all required fields validated
        version=fm_version,  # type: ignore[arg-type]
        owner=fm_owner,  # type: ignore[arg-type]
        title=title,  # type: ignore[arg-type]
        steps=tuple(steps),
        source_path=source_path,
    )
