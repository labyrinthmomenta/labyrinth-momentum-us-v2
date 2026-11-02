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


def test_yahoo_rate_limit_stops_batch_after_first_symbol(tmp_path):
    """A real yfinance exception type must stop the remaining batch."""
    from yfinance.exceptions import YFRateLimitError

    from src.data.providers.yahoo import fetch_price_bars

    db_path = tmp_path / "rate_limit.db"
    initialize_test_database(db_path)

    calls = []

    def rate_limited_downloader(symbol, **kwargs):
        calls.append(symbol)
        raise YFRateLimitError()

    def fetcher(symbol):
        return fetch_price_bars(
            symbol,
            start=date(2025, 10, 1),
            end=date(2026, 10, 15),
            downloader=rate_limited_downloader,
        )

    breaker = BatchCircuitBreaker(
        max_consecutive_provider_errors=3
    )

    result = ingest_batch(
        db_path,
        ["AAA", "BBB", "CCC", "DDD", "EEE"],
        as_of=AS_OF,
        fetcher=fetcher,
        circuit_breaker=breaker,
    )

    assert calls == ["AAA"]
    assert breaker.is_open

    assert result.requested == 5
    assert result.counts == {
        "SUCCESS": 0,
        "SKIPPED": 0,
        "FAILED": 1,
    }

    assert result.error_categories == {
        "RATE_LIMIT_ERROR": 1,
    }

    assert result.stopped_early is True
    assert result.unprocessed_symbols == (
        "BBB", "CCC", "DDD", "EEE"
    )

    first = get_download_status(db_path, "AAA")
    assert first is not None
    assert first.status == "FAILED"
    assert first.error_category == "RATE_LIMIT_ERROR"

    for symbol in ("BBB", "CCC", "DDD", "EEE"):
        assert get_download_status(db_path, symbol) is None


def test_controlled_history_rate_limit_stops_batch(tmp_path):
    """Controlled Ticker.history rate-limit must halt remaining symbols."""
    from datetime import date

    from yfinance.exceptions import YFRateLimitError

    from src.data.providers.controlled_fetch import FetchPolicy
    from src.data.providers.controlled_yahoo import (
        make_controlled_yahoo_history_fetcher,
    )
    from src.data.providers.request_pacer import RequestPacer
    from src.data.providers.yahoo_history import fetch_history_bars

    db_path = tmp_path / "controlled_history_limit.db"
    initialize_test_database(db_path)

    calls = []

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, **kwargs):
            calls.append(self.symbol)
            raise YFRateLimitError()

    def provider(symbol, *, start, end):
        return fetch_history_bars(
            symbol,
            start=start,
            end=end,
            ticker_factory=FakeTicker,
        )

    # No real waiting or network calls during this test.
    pacer = RequestPacer(min_interval_seconds=0)

    fetcher = make_controlled_yahoo_history_fetcher(
        start=date(2025, 10, 1),
        end=date(2026, 10, 15),
        provider=provider,
        pacer=pacer,
        policy=FetchPolicy(
            max_attempts=3,
            retry_delay_seconds=0,
        ),
    )

    breaker = BatchCircuitBreaker()

    result = ingest_batch(
        db_path,
        ["AAA", "BBB", "CCC"],
        as_of=AS_OF,
        fetcher=fetcher,
        circuit_breaker=breaker,
    )

    assert calls == ["AAA"]
    assert breaker.is_open
    assert result.counts["FAILED"] == 1
    assert result.error_categories == {"RATE_LIMIT_ERROR": 1}
    assert result.stopped_early is True
    assert result.unprocessed_symbols == ("BBB", "CCC")

    first = get_download_status(db_path, "AAA")
    assert first is not None
    assert first.status == "FAILED"
    assert first.error_category == "RATE_LIMIT_ERROR"

    assert get_download_status(db_path, "BBB") is None
    assert get_download_status(db_path, "CCC") is None
