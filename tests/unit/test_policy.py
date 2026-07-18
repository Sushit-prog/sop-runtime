"""Unit tests for policy loading."""

from pathlib import Path

import pytest

from sopvm.capability.policy import Policy, PolicyError, load_policy


def _write_policy(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.policy.yaml"
    p.write_text(content, encoding="utf-8")
    return p


class TestLoadPolicy:
    def test_valid_policy(self, tmp_path):
        p = _write_policy(tmp_path, 'policy_version: "0.1"\nallowed_capabilities:\n  - "db:read(orders)"\n  - "notify:email"')
        policy = load_policy(p)
        assert policy.policy_version == "0.1"
        assert len(policy.allowed_capabilities) == 2
        assert policy.allowed_capabilities[0].namespace == "db"
        assert policy.allowed_capabilities[1].action == "email"

    def test_policy_with_comparator(self, tmp_path):
        p = _write_policy(tmp_path, 'policy_version: "0.1"\nallowed_capabilities:\n  - "payments:refund(max_amount<=100.00)"')
        policy = load_policy(p)
        assert policy.allowed_capabilities[0].params["max_amount"] == {"op": "<=", "value": 100.0}

    def test_missing_policy_version(self, tmp_path):
        p = _write_policy(tmp_path, 'allowed_capabilities:\n  - "db:read(x)"')
        with pytest.raises(PolicyError, match="policy_version"):
            load_policy(p)

    def test_missing_allowed_capabilities(self, tmp_path):
        p = _write_policy(tmp_path, 'policy_version: "0.1"')
        with pytest.raises(PolicyError, match="allowed_capabilities"):
            load_policy(p)

    def test_empty_allowed_capabilities(self, tmp_path):
        p = _write_policy(tmp_path, 'policy_version: "0.1"\nallowed_capabilities: []')
        with pytest.raises(PolicyError, match="non-empty"):
            load_policy(p)

    def test_malformed_capability_in_policy(self, tmp_path):
        p = _write_policy(tmp_path, 'policy_version: "0.1"\nallowed_capabilities:\n  - ":bad"')
        with pytest.raises(PolicyError, match="malformed"):
            load_policy(p)

    def test_non_mapping_yaml(self, tmp_path):
        p = _write_policy(tmp_path, "- just a list")
        with pytest.raises(PolicyError, match="mapping"):
            load_policy(p)

    def test_non_string_entry(self, tmp_path):
        p = _write_policy(tmp_path, 'policy_version: "0.1"\nallowed_capabilities:\n  - 123')
        with pytest.raises(PolicyError, match="strings"):
            load_policy(p)


class TestRealPolicyFile:
    def test_load_support_agent_policy(self):
        policy = load_policy(Path("policies/support-agent.policy.yaml"))
        assert policy.policy_version == "0.1"
        assert len(policy.allowed_capabilities) == 5
        namespaces = {c.namespace for c in policy.allowed_capabilities}
        assert namespaces == {"db", "payments", "notify"}
