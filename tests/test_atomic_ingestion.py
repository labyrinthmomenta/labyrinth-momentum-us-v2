"""Offline atomic-ingestion and rollback tests."""

from datetime import date
import sqlite3

import pytest

from src.calculation.engine import DataQualityError, PriceBar
from src.data.storage.atomic_ingestion import (
    persist_validated_history,
)
from src.data.storage.market_data import load_bars


AS_OF = date(2026, 10, 14)


@pytest.fixture
def database(tmp_path):
    db = tmp_path / "atomic.db"

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


def bar(day, close=100.0):
    return PriceBar(
        date=day,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000.0,
    )


def status_row(database, symbol="AAPL"):
    with sqlite3.connect(database) as conn:
        return conn.execute(
            """
            SELECT status, last_session
            FROM download_status
            WHERE symbol = ?
            """,
            (symbol,),
        ).fetchone()


def test_atomic_success(database):
    bars = [
        bar(date(2026, 10, 13)),
        bar(AS_OF),
    ]

    written = persist_validated_history(
        database, "AAPL", bars, as_of=AS_OF
    )

    assert written == 2
    assert load_bars(database, "AAPL") == bars
    assert status_row(database) == ("SUCCESS", "2026-10-14")


def test_atomic_rollback_when_status_insert_fails(database):
    original = [bar(AS_OF, close=100)]

    persist_validated_history(
        database, "AAPL", original, as_of=AS_OF
    )

    with sqlite3.connect(database) as conn:
        conn.execute("""
            CREATE TRIGGER prevent_status_update
            BEFORE UPDATE ON download_status
            BEGIN
                SELECT RAISE(ABORT, 'status write blocked');
            END;
        """)

    replacement = [bar(AS_OF, close=50)]

    with pytest.raises(sqlite3.IntegrityError, match="status write blocked"):
        persist_validated_history(
            database,
            "AAPL",
            replacement,
            as_of=AS_OF,
        )

    assert load_bars(database, "AAPL") == original
    assert status_row(database) == ("SUCCESS", "2026-10-14")


def test_atomic_rejects_missing_existing_session(database):
    original = [
        bar(date(2026, 10, 13)),
        bar(AS_OF),
    ]

    persist_validated_history(
        database, "AAPL", original, as_of=AS_OF
    )

    with pytest.raises(DataQualityError, match="remove"):
        persist_validated_history(
            database,
            "AAPL",
            [bar(AS_OF)],
            as_of=AS_OF,
        )

    assert load_bars(database, "AAPL") == original
    assert status_row(database) == ("SUCCESS", "2026-10-14")


def test_atomic_rejects_wrong_end_date(database):
    with pytest.raises(DataQualityError, match="end at as_of"):
        persist_validated_history(
            database,
            "AAPL",
            [bar(date(2026, 10, 13))],
            as_of=AS_OF,
        )

    assert load_bars(database, "AAPL") == []
    assert status_row(database) is None


def test_atomic_rejects_invalid_bar(database):
    invalid = PriceBar(
        date=AS_OF,
        open=100,
        high=101,
        low=99,
        close=float("nan"),
        volume=1000,
    )

    with pytest.raises(DataQualityError, match="Invalid price"):
        persist_validated_history(
            database,
            "AAPL",
            [invalid],
            as_of=AS_OF,
        )

    assert load_bars(database, "AAPL") == []
    assert status_row(database) is None


def test_atomic_preserves_other_symbol(database):
    nvda = [bar(AS_OF, close=200)]
    aapl = [bar(AS_OF, close=100)]

    persist_validated_history(
        database, "NVDA", nvda, as_of=AS_OF
    )
    persist_validated_history(
        database, "AAPL", aapl, as_of=AS_OF
    )

    persist_validated_history(
        database,
        "AAPL",
        [bar(AS_OF, close=110)],
        as_of=AS_OF,
    )

    assert load_bars(database, "NVDA") == nvda
    assert status_row(database, "NVDA") == (
        "SUCCESS", "2026-10-14"
    )


def make_complete_us_bars(
    as_of=AS_OF,
    required_sessions=253,
):
    import exchange_calendars as xcals

    cal = xcals.get_calendar("XNYS")
    sessions = cal.sessions_window(
        as_of.isoformat(),
        -required_sessions,
    )

    return [
        bar(session.date(), close=100)
        for session in sessions
    ]


def test_complete_history_persists_successfully(database):
    from src.data.storage.atomic_ingestion import (
        persist_complete_history,
    )

    bars = make_complete_us_bars()

    written = persist_complete_history(
        database,
        "AAPL",
        bars,
        as_of=AS_OF,
    )

    assert written == 253
    assert load_bars(database, "AAPL") == bars
    assert status_row(database) == ("SUCCESS", "2026-10-14")


def test_complete_history_rejects_missing_session(database):
    from src.data.storage.atomic_ingestion import (
        persist_complete_history,
    )

    bars = make_complete_us_bars()
    bars.pop(100)

    with pytest.raises(Exception):
        persist_complete_history(
            database,
            "AAPL",
            bars,
            as_of=AS_OF,
        )

    assert load_bars(database, "AAPL") == []
    assert status_row(database) is None


def test_complete_history_rejects_short_requirement(database):
    from src.data.storage.atomic_ingestion import (
        persist_complete_history,
    )

    bars = make_complete_us_bars()

    with pytest.raises(ValueError, match="at least 253"):
        persist_complete_history(
            database,
            "AAPL",
            bars,
            as_of=AS_OF,
            required_sessions=90,
        )

    assert load_bars(database, "AAPL") == []
    assert status_row(database) is None


def test_complete_history_preserves_older_history(database):
    from src.data.storage.atomic_ingestion import (
        persist_complete_history,
    )

    older = bar(date(2025, 10, 10))
    initial = [older] + make_complete_us_bars()

    persist_complete_history(
        database,
        "AAPL",
        initial,
        as_of=AS_OF,
    )

    replacement = make_complete_us_bars()

    with pytest.raises(DataQualityError, match="remove"):
        persist_complete_history(
            database,
            "AAPL",
            replacement,
            as_of=AS_OF,
        )

    assert load_bars(database, "AAPL") == initial
    assert status_row(database) == ("SUCCESS", "2026-10-14")
