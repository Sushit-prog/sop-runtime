"""Capability token data model and parser.

Grammar: ``namespace:action(param=value, ...)``

Policy entries may use comparator params (``max_amount<=100.00``) to
express ceilings. SOP-declared requests use concrete values only
(``max_amount=100.00``). The parser accepts both forms; the semantic
distinction is enforced by the checker, not the parser.

Param forms:
- ``ns:action(key<=value)`` — comparator (policy ceiling)
- ``ns:action(key=value)`` — named assignment
- ``ns:action(resource)`` — bare resource identifier
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Matches: namespace:action  or  namespace:action(params)
_CAP_RE = re.compile(
    r"^(?P<ns>[a-zA-Z_][a-zA-Z0-9_]*)"
    r":(?P<action>[a-zA-Z_][a-zA-Z0-9_]*)"
    r"(?:\((?P<params>.*)\))?$"
)

# Comparator: key<=value, key>=value, key<value, key>value, key==value
_PARAM_COMPARATOR_RE = re.compile(
    r"^\s*(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)"
    r"\s*(?P<op><=|>=|<|>|==)"
    r"\s*(?P<value>.+?)\s*$"
)

# Assignment: key=value
_PARAM_ASSIGN_RE = re.compile(
    r"^\s*(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)"
    r"\s*=\s*"
    r"(?P<value>.+?)\s*$"
)

# Bare resource identifier: just a word (e.g. "orders", "/tmp/out")
_PARAM_BARE_RE = re.compile(
    r"^\s*(?P<key>.+?)\s*$"
)


class CapabilityGrammarError(Exception):
    """Raised when a capability string is malformed."""

    def __init__(self, message: str, raw: str | None = None) -> None:
        self.raw = raw
        super().__init__(message)


@dataclass(frozen=True)
class CapabilityToken:
    """A parsed capability token.

    Attributes:
        namespace: The capability namespace (e.g. ``db``, ``payments``).
        action: The action within the namespace (e.g. ``read``, ``refund``).
        params: Parsed parameters. Values may be:
            - ``True`` for bare resource identifiers (e.g. ``db:read(orders)``)
            - ``str`` or ``float`` for assignment params (e.g. ``channel=slack``)
            - ``{"op": str, "value": float|str}`` for comparator params
        raw: The original unparsed string.
    """

    namespace: str
    action: str
    params: dict[str, str | float | bool | dict[str, str | float]]
    raw: str


def parse_capability(s: str) -> CapabilityToken:
    """Parse a capability string into a ``CapabilityToken``.

    Accepts both concrete requests (``ns:action(k=v)``) and ceiling
    expressions with comparators (``ns:action(k<=v)``).

    Args:
        s: The capability string to parse.

    Returns:
        A ``CapabilityToken``.

    Raises:
        CapabilityGrammarError: If the string doesn't match the grammar.
    """
    m = _CAP_RE.match(s)
    if not m:
        raise CapabilityGrammarError(
            f"malformed capability string: {s!r}", raw=s
        )

    ns = m.group("ns")
    action = m.group("action")
    params_str = m.group("params")

    params: dict[str, str | float | bool | dict[str, str | float]] = {}
    if params_str and params_str.strip():
        for param_part in _split_params(params_str):
            # Try comparator first: key<=value
            pm = _PARAM_COMPARATOR_RE.match(param_part)
            if pm:
                params[pm.group("key")] = {
                    "op": pm.group("op"),
                    "value": _coerce_value(pm.group("value")),
                }
                continue

            # Try assignment: key=value
            pm = _PARAM_ASSIGN_RE.match(param_part)
            if pm:
                params[pm.group("key")] = _coerce_value(pm.group("value"))
                continue

            # Bare resource identifier
            key = param_part.strip()
            if key:
                params[key] = True
            else:
                raise CapabilityGrammarError(
                    f"empty parameter in capability {s!r}",
                    raw=s,
                )

    return CapabilityToken(namespace=ns, action=action, params=params, raw=s)


def _split_params(params_str: str) -> list[str]:
    """Split a parameter string on commas, respecting parentheses."""
    parts = []
    depth = 0
    current: list[str] = []
    for ch in params_str:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def _coerce_value(raw: str) -> str | float:
    """Try to parse a value as a float, otherwise keep as string."""
    try:
        return float(raw)
    except ValueError:
        return raw
