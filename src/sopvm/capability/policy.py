"""Policy loader — parses YAML policy files per INTERFACES.md §3.

Policy format:

```yaml
policy_version: "0.1"
allowed_capabilities:
  - "db:read(orders)"
  - "payments:refund(max_amount<=100.00)"
  - "notify:email"
```

Each entry in ``allowed_capabilities`` is a capability string parsed
into a ``CapabilityToken``. Comparator params (``<=``, ``>=``, etc.)
express ceilings that the static checker evaluates against SOP requests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .token import CapabilityToken, CapabilityGrammarError, parse_capability


class PolicyError(Exception):
    """Raised when a policy file is invalid or missing required fields."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class Policy:
    """A parsed capability policy.

    Attributes:
        policy_version: Policy schema version.
        allowed_capabilities: List of ceiling capability tokens.
    """

    policy_version: str
    allowed_capabilities: tuple[CapabilityToken, ...] = field(default_factory=tuple)


def load_policy(path: str | Path) -> Policy:
    """Load and parse a YAML policy file.

    Args:
        path: Filesystem path to the policy YAML file.

    Returns:
        A validated ``Policy``.

    Raises:
        PolicyError: If the file is missing required fields or contains
            malformed capability strings.
    """
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(raw, dict):
        raise PolicyError(
            f"policy file must be a YAML mapping, got {type(raw).__name__}"
        )

    if "policy_version" not in raw:
        raise PolicyError("policy file missing required field: policy_version")

    if "allowed_capabilities" not in raw:
        raise PolicyError("policy file missing required field: allowed_capabilities")

    caps_raw = raw["allowed_capabilities"]
    if not isinstance(caps_raw, list) or len(caps_raw) == 0:
        raise PolicyError("allowed_capabilities must be a non-empty list")

    tokens: list[CapabilityToken] = []
    for entry in caps_raw:
        if not isinstance(entry, str):
            raise PolicyError(
                f"allowed_capabilities entries must be strings, got: {type(entry).__name__}"
            )
        try:
            tokens.append(parse_capability(entry))
        except CapabilityGrammarError as e:
            raise PolicyError(f"malformed capability in policy: {e}") from e

    return Policy(
        policy_version=raw["policy_version"],
        allowed_capabilities=tuple(tokens),
    )
