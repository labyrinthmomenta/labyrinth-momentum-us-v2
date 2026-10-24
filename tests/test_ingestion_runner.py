"""Offline tests for resumable US ingestion."""

from datetime import date
import sqlite3

import exchange_calendars as xcals
import pytest

from src.calculation.engine import PriceBar
from src.data.ingestion_runner import ingest_symbol
from src.data.storage.download_status import get_download_status
from src.data.storage.market_data import load_bars


AS_OF = date(2026, 10, 14)


@pytest.fixture
def database(tmp_path):
    db = tmp_path / "runner.db"

    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE daily_bars (
                symbol TEXT NOT NULL,
                session_date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                PRIMARY KEY (symbol, session_date)
            );

            CREATE TABLE download_status (
                symbol TEXT PRIMARY KEY,
                last_attempt_utc TEXT,
                last_success_utc TEXT,
                last_session TEXT,
                status TEXT NOT NULL,
                error_message TEXT
            );
        """)

    return db


def make_bars(close=20.0, volume=200_000.0):
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_window(
        AS_OF.isoformat(), -253
    )

    return [
        PriceBar(
            date=session.date(),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=volume,
        )
        for session in sessions
    ]


def test_successful_ingestion(database):
    bars = make_bars()

    result = ingest_symbol(
        database, "AAPL",
        as_of=AS_OF,
        fetcher=lambda symbol: bars,
    )

    assert result.status == "SUCCESS"
    assert result.eligibility == "PASS"
    assert result.rows == 253
    assert load_bars(database, "AAPL") == bars
    assert get_download_status(database, "AAPL").status == "SUCCESS"


def test_filter_fail_still_stores_valid_bars(database):
    bars = make_bars(close=2.0)

    result = ingest_symbol(
        database, "IBIO",
        as_of=AS_OF,
        fetcher=lambda symbol: bars,
    )

    assert result.status == "SUCCESS"
    assert result.eligibility == "FILTER_FAIL"
    assert len(load_bars(database, "IBIO")) == 253


def test_incomplete_history_fails_without_bars(database):
    bars = make_bars()[:80]

    result = ingest_symbol(
        database, "FCBM",
        as_of=AS_OF,
        fetcher=lambda symbol: bars,
    )

    assert result.status == "FAILED"
    assert load_bars(database, "FCBM") == []
    assert get_download_status(database, "FCBM").status == "FAILED"


def test_fetch_failure_is_recorded(database):
    def broken_fetcher(symbol):
        raise RuntimeError("Simulated Yahoo outage")

    result = ingest_symbol(
        database, "AAPL",
        as_of=AS_OF,
        fetcher=broken_fetcher,
    )

    assert result.status == "FAILED"
    assert "Simulated Yahoo outage" in result.reason
    assert load_bars(database, "AAPL") == []
    assert get_download_status(database, "AAPL").status == "FAILED"


def test_success_is_skipped_on_rerun(database):
    calls = []

    def fetcher(symbol):
        calls.append(symbol)
        return make_bars()

    first = ingest_symbol(
        database, "AAPL",
        as_of=AS_OF,
        fetcher=fetcher,
    )
    second = ingest_symbol(
        database, "AAPL",
        as_of=AS_OF,
        fetcher=fetcher,
    )

    assert first.status == "SUCCESS"
    assert second.status == "SKIPPED"
    assert calls == ["AAPL"]


def test_force_reprocesses_success(database):
    calls = []

    def fetcher(symbol):
        calls.append(symbol)
        return make_bars()

    ingest_symbol(
        database, "AAPL",
        as_of=AS_OF,
        fetcher=fetcher,
    )

    second = ingest_symbol(
        database, "AAPL",
        as_of=AS_OF,
        fetcher=fetcher,
        force=True,
    )

    assert second.status == "SUCCESS"
    assert calls == ["AAPL", "AAPL"]


def test_failed_refresh_preserves_previous_success(database):
    bars = make_bars()

    first = ingest_symbol(
        database,
        "AAPL",
        as_of=AS_OF,
        fetcher=lambda symbol: bars,
    )
    assert first.status == "SUCCESS"

    previous = get_download_status(database, "AAPL")
    original_bars = load_bars(database, "AAPL")

    def broken_fetcher(symbol):
        raise RuntimeError("Temporary Yahoo outage")

    second = ingest_symbol(
        database,
        "AAPL",
        as_of=AS_OF,
        fetcher=broken_fetcher,
        force=True,
    )

    current = get_download_status(database, "AAPL")

    assert second.status == "FAILED"
    assert load_bars(database, "AAPL") == original_bars
    assert current.status == "FAILED"
    assert current.last_session == previous.last_session
    assert current.last_success_utc == previous.last_success_utc


def test_failed_refresh_can_be_retried(database):
    bars = make_bars()
    attempts = []

    def sometimes_fails(symbol):
        attempts.append(symbol)
        if len(attempts) == 1:
            raise RuntimeError("Temporary error")
        return bars

    first = ingest_symbol(
        database,
        "AAPL",
        as_of=AS_OF,
        fetcher=sometimes_fails,
    )

    second = ingest_symbol(
        database,
        "AAPL",
        as_of=AS_OF,
        fetcher=sometimes_fails,
    )

    assert first.status == "FAILED"
    assert second.status == "SUCCESS"
    assert attempts == ["AAPL", "AAPL"]
    assert load_bars(database, "AAPL") == bars


def test_corrupted_success_is_not_skipped(database):
    bars = make_bars()
    calls = []

    def fetcher(symbol):
        calls.append(symbol)
        return bars

    first = ingest_symbol(
        database,
        "AAPL",
        as_of=AS_OF,
        fetcher=fetcher,
    )
    assert first.status == "SUCCESS"

    with sqlite3.connect(database) as conn:
        conn.execute(
            """
            DELETE FROM daily_bars
            WHERE symbol = ? AND session_date = ?
            """,
            ("AAPL", bars[100].date.isoformat()),
        )

    second = ingest_symbol(
        database,
        "AAPL",
        as_of=AS_OF,
        fetcher=fetcher,
    )

    assert second.status == "SUCCESS"
    assert calls == ["AAPL", "AAPL"]
    assert load_bars(database, "AAPL") == bars
