"""Offline batch circuit-breaker integration tests."""

from datetime import date
import sqlite3

from src.data.batch_circuit_breaker import BatchCircuitBreaker
from src.data.batch_ingestion import ingest_batch
from src.data.storage.download_status import get_download_status


AS_OF = date(2026, 10, 14)


def initialize_test_database(db_path):
    """Create the minimal existing SQLite ingestion schema."""
    with sqlite3.connect(db_path) as conn:
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



def test_batch_stops_after_three_provider_errors(tmp_path):
    db_path = tmp_path / "circuit_test.db"
    initialize_test_database(db_path)
    calls = []

    def failing_fetcher(symbol):
        calls.append(symbol)
        raise ConnectionError("Simulated provider outage")

    result = ingest_batch(
        db_path,
        ["AAA", "BBB", "CCC", "DDD", "EEE"],
        as_of=AS_OF,
        fetcher=failing_fetcher,
        circuit_breaker=BatchCircuitBreaker(
            max_consecutive_provider_errors=3
        ),
    )

    assert calls == ["AAA", "BBB", "CCC"]
    assert result.requested == 5
    assert result.counts == {
        "SUCCESS": 0,
        "SKIPPED": 0,
        "FAILED": 3,
    }
    assert result.error_categories == {"PROVIDER_ERROR": 3}
    assert result.stopped_early is True
    assert result.unprocessed_symbols == ("DDD", "EEE")

    for symbol in ("AAA", "BBB", "CCC"):
        status = get_download_status(db_path, symbol)
        assert status is not None
        assert status.status == "FAILED"
        assert status.error_category == "PROVIDER_ERROR"

    for symbol in ("DDD", "EEE"):
        assert get_download_status(db_path, symbol) is None


def test_batch_without_breaker_preserves_existing_behavior(tmp_path):
    db_path = tmp_path / "no_breaker.db"
    initialize_test_database(db_path)
    calls = []

    def failing_fetcher(symbol):
        calls.append(symbol)
        raise ConnectionError("Simulated provider outage")

    result = ingest_batch(
        db_path,
        ["AAA", "BBB", "CCC", "DDD", "EEE"],
        as_of=AS_OF,
        fetcher=failing_fetcher,
    )

    assert calls == ["AAA", "BBB", "CCC", "DDD", "EEE"]
    assert result.counts["FAILED"] == 5
    assert result.stopped_early is False
    assert result.unprocessed_symbols == ()


def test_already_open_circuit_does_not_touch_database(tmp_path):
    db_path = tmp_path / "already_open.db"
    initialize_test_database(db_path)

    breaker = BatchCircuitBreaker(
        max_consecutive_provider_errors=1
    )
    from src.data.ingestion_runner import IngestionResult

    breaker.record(
        IngestionResult(
            symbol="PREVIOUS",
            status="FAILED",
            eligibility=None,
            rows=0,
            reason="Provider outage",
            error_category="PROVIDER_ERROR",
            retryable=True,
        )
    )

    assert breaker.is_open

    calls = []

    def forbidden_fetcher(symbol):
        calls.append(symbol)
        raise AssertionError("Open circuit must not fetch")

    result = ingest_batch(
        db_path,
        ["AAA", "BBB"],
        as_of=AS_OF,
        fetcher=forbidden_fetcher,
        circuit_breaker=breaker,
    )

    assert calls == []
    assert result.results == ()
    assert result.requested == 2
    assert result.stopped_early is True
    assert result.unprocessed_symbols == ("AAA", "BBB")

    for symbol in ("AAA", "BBB"):
        assert get_download_status(db_path, symbol) is None


def test_fresh_breaker_allows_new_batch_attempt(tmp_path):
    db_path = tmp_path / "fresh_breaker.db"
    initialize_test_database(db_path)

    calls = []

    def failing_fetcher(symbol):
        calls.append(symbol)
        raise ConnectionError("Provider still unavailable")

    result = ingest_batch(
        db_path,
        ["AAA", "BBB"],
        as_of=AS_OF,
        fetcher=failing_fetcher,
        circuit_breaker=BatchCircuitBreaker(
            max_consecutive_provider_errors=3
        ),
    )

    assert calls == ["AAA", "BBB"]
    assert result.counts["FAILED"] == 2
    assert result.stopped_early is False
    assert result.unprocessed_symbols == ()
