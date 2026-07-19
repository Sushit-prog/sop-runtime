"""SQLite-backed ToolProvider — reference implementation.

A genuine (non-mocked) tool integration demonstrating how a real
provider plugs into SOPVM's ToolProvider protocol. Uses Python's
built-in sqlite3 module — no external dependencies.

This is a REFERENCE EXAMPLE, not a production provider. It lives
under examples/ and is not part of src/sopvm/.

Security: uses parameterized queries (?) for ALL user-controlled values.
Never string-formats args into SQL. This matters specifically for this
project: a capability-gated runtime with a SQL injection vulnerability
in its own reference provider would undercut the whole security story.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sopvm.capability.token import CapabilityToken
from sopvm.plugins.base import ToolResult


class SqliteProvider:
    """Real SQLite database provider.

    Handles ``db:read(<table>)`` and ``db:write(<table>)`` capabilities
    by executing actual SQL against a SQLite database file.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str | Path = "examples/providers/demo.db") -> None:
        self._db_path = Path(db_path)

    def declared_capabilities(self) -> list[str]:
        """Declare read/write capabilities for the orders table."""
        return [
            "db:read(orders)",
            "db:write(orders)",
        ]

    def invoke(self, capability: CapabilityToken, args: dict) -> ToolResult:
        """Execute a real SQL operation against the SQLite database.

        All user-controlled values use parameterized queries (?).
        Table names are validated against the declared capabilities
        whitelist and checked with isidentifier() before use.
        """
        if not self._db_path.exists():
            return ToolResult(
                success=False,
                error=f"database file not found: {self._db_path}",
            )

        resource = self._extract_resource(capability)
        if resource is None:
            return ToolResult(
                success=False,
                error=f"cannot extract table name from capability: {capability.raw}",
            )

        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            try:
                action = capability.action
                if action == "read":
                    return self._do_read(conn, resource, args)
                elif action == "write":
                    return self._do_write(conn, resource, args)
                else:
                    return ToolResult(
                        success=False,
                        error=f"unsupported db action: {action!r}",
                    )
            finally:
                conn.close()
        except sqlite3.Error as e:
            return ToolResult(success=False, error=f"SQLite error: {e}")
        except Exception as e:
            return ToolResult(success=False, error=f"unexpected error: {e}")

    def _extract_resource(self, capability: CapabilityToken) -> str | None:
        """Extract the table name from the capability's bare parameter."""
        for key, value in capability.params.items():
            if value is True:
                return key
        return None

    def _get_allowed_tables(self) -> set[str]:
        """Extract table names from declared capabilities."""
        tables = set()
        for cap_str in self.declared_capabilities():
            if "(" in cap_str and cap_str.endswith(")"):
                table = cap_str.split("(")[1].rstrip(")")
                tables.add(table)
        return tables

    def _validate_table(self, table: str) -> ToolResult | None:
        """Validate table name is safe. Returns None if OK, ToolResult if error."""
        allowed = self._get_allowed_tables()
        if table not in allowed:
            return ToolResult(
                success=False,
                error=f"table {table!r} not in declared capabilities",
            )
        if not table.isidentifier():
            return ToolResult(
                success=False,
                error=f"invalid table name: {table!r}",
            )
        return None

    def _do_read(self, conn: sqlite3.Connection, table: str, args: dict) -> ToolResult:
        """Execute a SELECT query with parameterized table name."""
        err = self._validate_table(table)
        if err is not None:
            return err

        columns = args.get("columns")
        if columns and isinstance(columns, list):
            for col in columns:
                if not isinstance(col, str) or not col.isidentifier():
                    return ToolResult(success=False, error=f"invalid column name: {col!r}")
            col_str = ", ".join(columns)
        else:
            col_str = "*"

        query = f"SELECT {col_str} FROM {table}"
        cursor = conn.execute(query)
        rows = [dict(row) for row in cursor.fetchall()]

        return ToolResult(success=True, data=rows)

    def _do_write(self, conn: sqlite3.Connection, table: str, args: dict) -> ToolResult:
        """Execute an INSERT or UPDATE with parameterized values."""
        err = self._validate_table(table)
        if err is not None:
            return err

        action = args.get("action", "insert")

        if action == "insert":
            row = args.get("row", {})
            if not row:
                return ToolResult(success=False, error="insert requires 'row' argument")

            for col in row:
                if not isinstance(col, str) or not col.isidentifier():
                    return ToolResult(success=False, error=f"invalid column name: {col!r}")

            columns = list(row.keys())
            values = list(row.values())
            placeholders = ", ".join(["?"] * len(columns))
            col_names = ", ".join(columns)

            query = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
            conn.execute(query, values)
            conn.commit()

            return ToolResult(success=True, data={"rows_affected": 1})

        elif action == "update":
            where = args.get("where", {})
            set_vals = args.get("set", {})
            if not set_vals:
                return ToolResult(success=False, error="update requires 'set' argument")
            if not where:
                return ToolResult(success=False, error="update requires 'where' argument")

            for col in list(set_vals.keys()) + list(where.keys()):
                if not isinstance(col, str) or not col.isidentifier():
                    return ToolResult(success=False, error=f"invalid column name: {col!r}")

            set_parts = []
            set_values = []
            for col, val in set_vals.items():
                set_parts.append(f"{col} = ?")
                set_values.append(val)

            where_parts = []
            where_values = []
            for col, val in where.items():
                where_parts.append(f"{col} = ?")
                where_values.append(val)

            query = f"UPDATE {table} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}"
            conn.execute(query, set_values + where_values)
            conn.commit()

            return ToolResult(success=True, data={"rows_affected": conn.total_changes})

        else:
            return ToolResult(success=False, error=f"unsupported write action: {action!r}")
