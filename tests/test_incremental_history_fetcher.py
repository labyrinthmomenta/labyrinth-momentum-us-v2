"""Offline contract tests for controlled incremental Yahoo fetching."""

import sqlite3
from dataclasses import replace
from datetime import date, timedelta

import exchange_calendars as xcals
import pytest
from yfinance.exceptions import YFRateLimitError

from src.calculation.engine import DataQualityError, PriceBar
from src.data.providers.controlled_fetch import FetchPolicy
from src.data.providers.request_pacer import RequestPacer
from src.data.incremental_history_fetcher import (
    make_incremental_history_fetcher,
)
from src.data.storage.market_data import load_bars, save_bars


AS_OF = date(2026, 11, 2)
FULL_START = date(2025, 7, 1)
END = AS_OF + timedelta(days=1)


def histories():
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_window(
        AS_OF.isoformat(), -254
    )

    complete = []

    for index, session in enumerate(sessions):
        close = 100.0 + index * 0.1
        complete.append(
            PriceBar(
                date=session.date(),
                open=close,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=200_000.0,
            )
        )

    assert len(complete) == 254
    return complete[:-1], complete[-31:], complete


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "incremental.db"

    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE daily_bars (
                symbol TEXT NOT NULL,
                session_date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                PRIMARY KEY (symbol, session_date)
            )
        """)

    return path


def factory(database, provider, **kwargs):
    return make_incremental_history_fetcher(
        database,
        as_of=AS_OF,
        full_start=FULL_START,
        overlap_sessions=30,
        pacer=RequestPacer(min_interval_seconds=0),
        policy=FetchPolicy(
            max_attempts=2,
            retry_delay_seconds=0,
        ),
        provider=provider,
        **kwargs,
    )


def test_new_symbol_requests_full_history(database):
    _, _, complete = histories()
    calls = []

    def provider(symbol, *, start, end):
        calls.append((symbol, start, end))
        return complete

    fetcher = factory(database, provider)
    result = fetcher("AAPL")

    assert result == complete
    assert calls == [("AAPL", FULL_START, END)]
    assert load_bars(database, "AAPL") == []


def test_existing_symbol_requests_only_overlap(database):
    stored, fresh, complete = histories()
    save_bars(database, "AAPL", stored)

    calls = []

    def provider(symbol, *, start, end):
        calls.append((symbol, start, end))
        return fresh

    fetcher = factory(database, provider)
    merged = fetcher("AAPL")

    assert merged == complete
    assert calls == [
        ("AAPL", stored[-30].date, END)
    ]

    # Fetcher returns data but does not write it.
    assert load_bars(database, "AAPL") == stored


def test_changed_overlap_is_rejected_without_write(database):
    stored, fresh, _ = histories()
    save_bars(database, "AAPL", stored)

    changed = list(fresh)
    changed[5] = replace(
        changed[5],
        close=changed[5].close + 0.5,
    )

    def provider(symbol, *, start, end):
        return changed

    fetcher = factory(database, provider)

    with pytest.raises(DataQualityError):
        fetcher("AAPL")

    assert load_bars(database, "AAPL") == stored


def test_incomplete_stored_history_does_not_fetch(database):
    stored, _, _ = histories()
    save_bars(database, "AAPL", stored[:100])

    calls = []

    def provider(symbol, *, start, end):
        calls.append(symbol)
        raise AssertionError("Provider must not be called")

    fetcher = factory(database, provider)

    with pytest.raises(DataQualityError):
        fetcher("AAPL")

    assert calls == []


def test_rate_limit_is_not_retried(database):
    stored, _, _ = histories()
    save_bars(database, "AAPL", stored)

    calls = []

    def provider(symbol, *, start, end):
        calls.append(symbol)
        raise YFRateLimitError()

    fetcher = factory(database, provider)

    with pytest.raises(YFRateLimitError):
        fetcher("AAPL")

    assert calls == ["AAPL"]
    assert load_bars(database, "AAPL") == stored


def test_timeout_retries_then_merges(database):
    stored, fresh, complete = histories()
    save_bars(database, "AAPL", stored)

    calls = []

    def provider(symbol, *, start, end):
        calls.append(symbol)
        if len(calls) == 1:
            raise TimeoutError("Simulated timeout")
        return fresh

    fetcher = factory(database, provider)
    result = fetcher("AAPL")

    assert calls == ["AAPL", "AAPL"]
    assert result == complete
    assert load_bars(database, "AAPL") == stored
