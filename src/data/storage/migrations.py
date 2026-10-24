"""Idempotent SQLite schema migrations for US market data."""

from pathlib import Path
import sqlite3


def ensure_error_category_column(
    db_path: str | Path,
) -> bool:
    """Add error_category to download_status if absent.

    Returns True when the column was added,
    False when it already existed.
    """
    db_path = Path(db_path)

    if not db_path.is_file():
        raise FileNotFoundError(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")

        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(download_status)"
            )
        }

        if not columns:
            raise RuntimeError(
                "download_status table does not exist"
            )

        if "error_category" in columns:
            return False

        conn.execute(
            "ALTER TABLE download_status "
            "ADD COLUMN error_category TEXT"
        )

        return True
