"""Unit tests for the SQLite provider.

Tests use tmp_path fixtures (real temp SQLite databases, not the demo.db)
to prove the provider works with actual SQL, including SQL injection
neutralization.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sopvm.capability.token import parse_capability
from examples.providers.sqlite_provider import SqliteProvider


@pytest.fixture
def db_with_orders(tmp_path: Path) -> Path:
    """Create a temp SQLite database with an orders table and seed data."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        )
    """)
    conn.executemany(
        "INSERT INTO orders (customer, amount, status) VALUES (?, ?, ?)",
        [
            ("Alice", 50.00, "pending"),
            ("Bob", 150.00, "pending"),
        ],
    )
    conn.commit()
    conn.close()
    return db


class TestReadOperations:
    def test_read_all_rows(self, db_with_orders: Path):
        """Read all rows from the orders table."""
        provider = SqliteProvider(db_with_orders)
        cap = parse_capability("db:read(orders)")
        result = provider.invoke(cap, {})

        assert result.success is True
        assert len(result.data) == 2
        assert result.data[0]["customer"] == "Alice"
        assert result.data[1]["customer"] == "Bob"

    def test_read_specific_columns(self, db_with_orders: Path):
        """Read only specific columns."""
        provider = SqliteProvider(db_with_orders)
        cap = parse_capability("db:read(orders)")
        result = provider.invoke(cap, {"columns": ["customer", "amount"]})

        assert result.success is True
        assert len(result.data) == 2
        assert set(result.data[0].keys()) == {"customer", "amount"}

    def test_read_empty_table(self, tmp_path: Path):
        """Read from an empty table returns empty list."""
        db = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE orders (id INTEGER, customer TEXT)")
        conn.commit()
        conn.close()

        provider = SqliteProvider(db)
        cap = parse_capability("db:read(orders)")
        result = provider.invoke(cap, {})

        assert result.success is True
        assert result.data == []


class TestWriteOperations:
    def test_insert_row(self, db_with_orders: Path):
        """Insert a new row and verify it exists."""
        provider = SqliteProvider(db_with_orders)
        cap = parse_capability("db:write(orders)")
        result = provider.invoke(cap, {
            "action": "insert",
            "row": {"customer": "Dave", "amount": 200.00, "status": "pending"},
        })

        assert result.success is True
        assert result.data["rows_affected"] == 1

        # Verify the row was inserted
        conn = sqlite3.connect(str(db_with_orders))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM orders WHERE customer = 'Dave'").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["amount"] == 200.00

    def test_update_row(self, db_with_orders: Path):
        """Update a row and verify the change."""
        provider = SqliteProvider(db_with_orders)
        cap = parse_capability("db:write(orders)")
        result = provider.invoke(cap, {
            "action": "update",
            "where": {"customer": "Alice"},
            "set": {"status": "shipped"},
        })

        assert result.success is True

        # Verify the update
        conn = sqlite3.connect(str(db_with_orders))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM orders WHERE customer = 'Alice'").fetchone()
        conn.close()
        assert row["status"] == "shipped"


class TestCapabilityRejection:
    def test_unsupported_table_rejected(self, db_with_orders: Path):
        """Requesting a table not in declared capabilities is rejected."""
        provider = SqliteProvider(db_with_orders)
        cap = parse_capability("db:read(users)")  # 'users' not declared
        result = provider.invoke(cap, {})

        assert result.success is False
        assert "not in declared capabilities" in result.error

    def test_unsupported_action_rejected(self, db_with_orders: Path):
        """Requesting an unsupported db action is rejected."""
        provider = SqliteProvider(db_with_orders)
        # Use a capability with an unsupported action (e.g. "delete")
        cap = parse_capability("db:delete(orders)")
        result = provider.invoke(cap, {})

        assert result.success is False
        assert "unsupported" in result.error

    def test_missing_database_rejected(self, tmp_path: Path):
        """Requesting a non-existent database file is rejected."""
        provider = SqliteProvider(tmp_path / "nonexistent.db")
        cap = parse_capability("db:read(orders)")
        result = provider.invoke(cap, {})

        assert result.success is False
        assert "not found" in result.error


class TestSQLInjectionNeutralization:
    def test_injection_via_table_name(self, db_with_orders: Path):
        """SQL injection via table name is neutralized.

        The injection string 'orders; DROP TABLE orders' fails the
        isidentifier() check, so it's rejected before any SQL is built.
        Even if it passed, parameterized queries would prevent harm.
        """
        provider = SqliteProvider(db_with_orders)

        # Attempt injection: table name contains SQL injection payload
        cap = parse_capability("db:read(orders; DROP TABLE orders)")
        result = provider.invoke(cap, {})

        # Should be rejected — the table name fails validation
        assert result.success is False
        assert "not in declared capabilities" in result.error or "invalid" in result.error

        # Verify table still exists and data is intact
        conn = sqlite3.connect(str(db_with_orders))
        rows = conn.execute("SELECT * FROM orders").fetchall()
        conn.close()
        assert len(rows) == 2  # Original seed data survives

    def test_injection_via_column_name(self, db_with_orders: Path):
        """SQL injection via column name is neutralized."""
        provider = SqliteProvider(db_with_orders)
        cap = parse_capability("db:read(orders)")

        # Attempt injection: column name contains SQL injection payload
        result = provider.invoke(cap, {"columns": ["1=1; DROP TABLE orders --"]})

        assert result.success is False
        assert "invalid column name" in result.error

        # Verify table still exists
        conn = sqlite3.connect(str(db_with_orders))
        rows = conn.execute("SELECT * FROM orders").fetchall()
        conn.close()
        assert len(rows) == 2

    def test_injection_via_insert_value(self, db_with_orders: Path):
        """SQL injection via insert value is neutralized by parameterized queries.

        Even though the value contains SQL injection syntax, sqlite3's ?
        placeholders treat it as a literal string value, not executable SQL.
        """
        provider = SqliteProvider(db_with_orders)
        cap = parse_capability("db:write(orders)")

        # Attempt injection: value contains SQL injection payload
        result = provider.invoke(cap, {
            "action": "insert",
            "row": {
                "customer": "'; DROP TABLE orders; --",
                "amount": 0.00,
                "status": "pending",
            },
        })

        # Should succeed — the injection is treated as a literal string
        assert result.success is True

        # Verify: the malicious string is stored as-is, table is intact
        conn = sqlite3.connect(str(db_with_orders))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM orders WHERE customer = ?",
            ("'; DROP TABLE orders; --",),
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["customer"] == "'; DROP TABLE orders; --"

        # Verify table still has all rows (original 2 + the injected 1)
        conn = sqlite3.connect(str(db_with_orders))
        count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        conn.close()
        assert count == 3

    def test_injection_via_where_clause(self, db_with_orders: Path):
        """SQL injection via WHERE clause is neutralized by parameterized queries.

        The tautology ``'1'='1'`` is treated as a literal string value
        by the parameterized query, so no rows match the WHERE clause.
        The original data remains untouched.
        """
        provider = SqliteProvider(db_with_orders)
        cap = parse_capability("db:write(orders)")

        # Attempt injection: WHERE clause contains tautology
        result = provider.invoke(cap, {
            "action": "update",
            "where": {"customer": "Alice' OR '1'='1"},
            "set": {"status": "hacked"},
        })

        # Should succeed — the injection is treated as a literal string
        assert result.success is True

        # Verify: original data is untouched (tautology didn't execute)
        conn = sqlite3.connect(str(db_with_orders))
        conn.row_factory = sqlite3.Row
        alice = conn.execute("SELECT status FROM orders WHERE customer = 'Alice'").fetchone()
        bob = conn.execute("SELECT status FROM orders WHERE customer = 'Bob'").fetchone()
        conn.close()
        assert alice["status"] == "pending"  # Alice untouched — tautology didn't match
        assert bob["status"] == "pending"    # Bob untouched
