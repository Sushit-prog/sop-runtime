"""Unit tests for capability token parsing."""

import pytest

from sopvm.capability.token import (
    CapabilityGrammarError,
    CapabilityToken,
    parse_capability,
)


class TestParseCapability:
    def test_simple_no_params(self):
        t = parse_capability("notify:email")
        assert t.namespace == "notify"
        assert t.action == "email"
        assert t.params == {}
        assert t.raw == "notify:email"

    def test_single_param(self):
        t = parse_capability("db:read(orders)")
        assert t.namespace == "db"
        assert t.action == "read"
        assert t.params == {"orders": True}

    def test_multiple_params(self):
        t = parse_capability("payments:refund(max_amount=100.00)")
        assert t.params == {"max_amount": 100.0}

    def test_comparator_param(self):
        t = parse_capability("payments:refund(max_amount<=100.00)")
        assert t.params == {"max_amount": {"op": "<=", "value": 100.0}}

    def test_string_param_value(self):
        t = parse_capability("notify:slack(channel=support-escalations)")
        assert t.params == {"channel": "support-escalations"}

    def test_multiple_mixed_params(self):
        t = parse_capability("net:http(domain=example.com, timeout=30)")
        assert t.params["domain"] == "example.com"
        assert t.params["timeout"] == 30.0

    def test_all_comparators(self):
        for op, expected_op in [("<=", "<="), (">=", ">="), ("<", "<"), (">", ">"), ("==", "==")]:
            t = parse_capability(f"db:read(limit{op}10)")
            assert t.params == {"limit": {"op": expected_op, "value": 10.0}}


class TestMalformedCapability:
    @pytest.mark.parametrize("bad_str", [
        ":read(x)",          # missing namespace
        "db:",               # missing action
        "dbread(x)",         # missing colon
        "",                  # empty
        "db:read(x",         # unclosed paren
        "db:read)x(",        # wrong paren order
    ])
    def test_malformed_raises(self, bad_str):
        with pytest.raises(CapabilityGrammarError):
            parse_capability(bad_str)

    def test_error_carries_raw(self):
        with pytest.raises(CapabilityGrammarError) as exc_info:
            parse_capability(":bad")
        assert exc_info.value.raw == ":bad"


class TestPolicyEntries:
    """Policy-style entries with comparators should parse correctly."""

    def test_ceiling_entry(self):
        t = parse_capability("payments:refund(max_amount<=100.00)")
        assert t.namespace == "payments"
        assert t.action == "refund"
        assert t.params["max_amount"] == {"op": "<=", "value": 100.0}

    def test_ceiling_ge(self):
        t = parse_capability("db:read(min_version>=2)")
        assert t.params["min_version"] == {"op": ">=", "value": 2.0}
