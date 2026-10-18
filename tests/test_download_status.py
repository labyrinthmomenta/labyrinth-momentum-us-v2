"""Offline tests for resumable download status storage."""

from datetime import date
import sqlite3

import pytest

from src.data.storage.download_status import (
    get_download_status,
    update_download_status,
)


@pytest.fixture
def database(tmp_path):
    db = tmp_path / "status.db"

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

    return db


def test_unknown_symbol_returns_none(database):
    assert get_download_status(database, "AAPL") is None


def test_symbol_normalization(database):
    update_download_status(database, " aapl ", "IN_PROGRESS")

    result = get_download_status(database, "AAPL")
    assert result.symbol == "AAPL"


def test_in_progress_status(database):
    update_download_status(database, "AAPL", "IN_PROGRESS")

    result = get_download_status(database, "AAPL")
    assert result.status == "IN_PROGRESS"
    assert result.last_attempt_utc is not None
    assert result.last_success_utc is None


def test_success_status(database):
    update_download_status(
        database,
        "AAPL",
        "SUCCESS",
        last_session=date(2026, 10, 14),
    )

    result = get_download_status(database, "AAPL")
    assert result.status == "SUCCESS"
    assert result.last_session == "2026-10-14"
    assert result.last_success_utc is not None


def test_failure_preserves_last_success(database):
    update_download_status(
        database,
        "AAPL",
        "SUCCESS",
        last_session=date(2026, 10, 14),
    )

    previous = get_download_status(database, "AAPL")

    update_download_status(
        database,
        "AAPL",
        "FAILED",
        error_message="Yahoo unavailable",
    )

    current = get_download_status(database, "AAPL")

    assert current.status == "FAILED"
    assert current.last_session == previous.last_session
    assert current.last_success_utc == previous.last_success_utc
    assert current.error_message == "Yahoo unavailable"


def test_in_progress_preserves_last_success(database):
    update_download_status(
        database,
        "AAPL",
        "SUCCESS",
        last_session=date(2026, 10, 14),
    )

    previous = get_download_status(database, "AAPL")

    update_download_status(database, "AAPL", "IN_PROGRESS")

    current = get_download_status(database, "AAPL")
    assert current.status == "IN_PROGRESS"
    assert current.last_success_utc == previous.last_success_utc
    assert current.last_session == previous.last_session


def test_invalid_status_rejected(database):
    with pytest.raises(ValueError, match="Invalid download status"):
        update_download_status(database, "AAPL", "UNKNOWN")


def test_empty_symbol_rejected(database):
    with pytest.raises(ValueError, match="Symbol cannot be empty"):
        update_download_status(database, "   ", "IN_PROGRESS")


def test_success_requires_session(database):
    with pytest.raises(ValueError, match="requires last_session"):
        update_download_status(database, "AAPL", "SUCCESS")


def test_failure_cannot_change_last_session(database):
    with pytest.raises(ValueError, match="Only SUCCESS"):
        update_download_status(
            database,
            "AAPL",
            "FAILED",
            last_session=date(2026, 10, 14),
        )


def test_success_rejects_error_message(database):
    with pytest.raises(ValueError, match="cannot have error_message"):
        update_download_status(
            database,
            "AAPL",
            "SUCCESS",
            last_session=date(2026, 10, 14),
            error_message="Unexpected error",
        )
