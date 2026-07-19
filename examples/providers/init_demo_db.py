"""Initialize the demo SQLite database with seed data.

Creates examples/providers/demo.db with an orders table and sample rows.
Run once before running the db demo:

    python examples/providers/init_demo_db.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "demo.db"


def init_db(db_path: Path = DB_PATH) -> None:
    """Create the orders table and insert seed data."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
            )
        """)

        # Insert seed rows only if the table is empty
        count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO orders (customer, amount, status) VALUES (?, ?, ?)",
                [
                    ("Alice", 50.00, "pending"),
                    ("Bob", 150.00, "pending"),
                    ("Carol", 75.00, "shipped"),
                ],
            )
            conn.commit()
            print(f"Initialized {db_path} with 3 seed orders.")
        else:
            print(f"{db_path} already has {count} orders, skipping seed data.")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
