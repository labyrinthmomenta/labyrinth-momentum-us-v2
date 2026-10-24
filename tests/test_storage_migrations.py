"""Offline tests for SQLite schema migrations."""

import sqlite3

import pytest

from src.data.storage.migrations import (
    ensure_error_category_column,
)


@pytest.fixture
def legacy_db(tmp_path):
    db = tmp_path / "legacy.db"

    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE download_status (
                symbol TEXT PRIMARY KEY,
                last_attempt_utc TEXT,
                last_success_utc TEXT,
                last_session TEXT,
                status TEXT NOT NULL,
                error_message TEXT
            )
        """)

        conn.execute("""
            INSERT INTO download_status (
                symbol, status, error_message
            )
            VALUES ('FCBM', 'FAILED', 'Missing sessions')
        """)

    return db


def columns(db):
    with sqlite3.connect(db) as conn:
        return [
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(download_status)"
            )
        ]


def test_adds_error_category(legacy_db):
    added = ensure_error_category_column(legacy_db)

    assert added is True
    assert "error_category" in columns(legacy_db)


def test_second_run_is_idempotent(legacy_db):
    assert ensure_error_category_column(legacy_db) is True
    assert ensure_error_category_column(legacy_db) is False

    assert columns(legacy_db).count("error_category") == 1


def test_preserves_existing_records(legacy_db):
    ensure_error_category_column(legacy_db)

    with sqlite3.connect(legacy_db) as conn:
        row = conn.execute("""
            SELECT symbol, status, error_message, error_category
            FROM download_status
            WHERE symbol = 'FCBM'
        """).fetchone()

    assert row == (
        "FCBM",
        "FAILED",
        "Missing sessions",
        None,
    )


def test_missing_database_rejected(tmp_path):
    db = tmp_path / "missing.db"

    with pytest.raises(FileNotFoundError):
        ensure_error_category_column(db)

    assert not db.exists()


def test_missing_table_rejected(tmp_path):
    db = tmp_path / "empty.db"

    with sqlite3.connect(db):
        pass

    with pytest.raises(RuntimeError, match="does not exist"):
        ensure_error_category_column(db)

    assert "error_category" not in columns(db)
