"""Test configuration — clears parser schema cache before each test."""

import pytest


@pytest.fixture(autouse=True)
def _clear_schema_cache():
    """Clear the parser's cached schema so tests see the current file."""
    import sopvm.parser.parse as parse_mod
    parse_mod._schema = None
    yield
    parse_mod._schema = None
