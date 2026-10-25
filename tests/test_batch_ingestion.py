"""Offline unit tests for bounded US batch ingestion."""

from datetime import date

import pytest

from src.data import batch_ingestion
from src.data.ingestion_runner import IngestionResult


AS_OF = date(2026, 10, 14)


def test_deduplicates_symbols_and_preserves_order(monkeypatch, tmp_path):
    calls = []

    def fake_ingest(db_path, symbol, *, as_of, fetcher, force):
        calls.append(symbol)
        return IngestionResult(
            symbol, "SUCCESS", "PASS", 261, "Stored"
        )

    monkeypatch.setattr(
        batch_ingestion, "ingest_symbol", fake_ingest
    )

    result = batch_ingestion.ingest_batch(
        tmp_path / "unused.db",
        ["aapl", "MSFT", "AAPL", " nvda "],
        as_of=AS_OF,
        fetcher=lambda symbol: [],
    )

    assert calls == ["AAPL", "MSFT", "NVDA"]
    assert result.requested == 3
    assert result.counts == {
        "SUCCESS": 3,
        "SKIPPED": 0,
        "FAILED": 0,
    }


def test_counts_statuses_and_errors(monkeypatch, tmp_path):
    outcomes = {
        "A": IngestionResult(
            "A", "SUCCESS", "PASS", 261, "Stored"
        ),
        "B": IngestionResult(
            "B", "SKIPPED", None, 0, "Already stored"
        ),
        "C": IngestionResult(
            "C", "FAILED", None, 0, "Timeout",
            error_category="PROVIDER_ERROR",
            retryable=True,
        ),
        "D": IngestionResult(
            "D", "FAILED", None, 0, "Missing sessions",
            error_category="DATA_QUALITY_ERROR",
        ),
    }

    monkeypatch.setattr(
        batch_ingestion,
        "ingest_symbol",
        lambda db_path, symbol, **kwargs: outcomes[symbol],
    )

    result = batch_ingestion.ingest_batch(
        tmp_path / "unused.db",
        ["A", "B", "C", "D"],
        as_of=AS_OF,
        fetcher=lambda symbol: [],
    )

    assert result.counts == {
        "SUCCESS": 1,
        "SKIPPED": 1,
        "FAILED": 2,
    }
    assert result.error_categories == {
        "PROVIDER_ERROR": 1,
        "DATA_QUALITY_ERROR": 1,
    }


def test_rejects_batch_over_limit(tmp_path):
    symbols = [f"T{i}" for i in range(26)]

    with pytest.raises(ValueError, match="limit"):
        batch_ingestion.ingest_batch(
            tmp_path / "unused.db",
            symbols,
            as_of=AS_OF,
            fetcher=lambda symbol: [],
        )


def test_rejects_empty_symbol(tmp_path):
    with pytest.raises(ValueError, match="Empty symbol"):
        batch_ingestion.ingest_batch(
            tmp_path / "unused.db",
            ["AAPL", " "],
            as_of=AS_OF,
            fetcher=lambda symbol: [],
        )


def test_rejects_invalid_max_symbols(tmp_path):
    with pytest.raises(ValueError, match="max_symbols"):
        batch_ingestion.ingest_batch(
            tmp_path / "unused.db",
            [],
            as_of=AS_OF,
            fetcher=lambda symbol: [],
            max_symbols=26,
        )


def test_forwards_force_and_as_of(monkeypatch, tmp_path):
    received = []

    def fake_ingest(db_path, symbol, *, as_of, fetcher, force):
        received.append((symbol, as_of, force))
        return IngestionResult(
            symbol, "SKIPPED", None, 0, "Previously stored"
        )

    monkeypatch.setattr(
        batch_ingestion, "ingest_symbol", fake_ingest
    )

    batch_ingestion.ingest_batch(
        tmp_path / "unused.db",
        ["AAPL"],
        as_of=AS_OF,
        fetcher=lambda symbol: [],
        force=True,
    )

    assert received == [("AAPL", AS_OF, True)]


def test_batch_sqlite_resume_after_provider_failure(
    tmp_path, monkeypatch
):
    """Failed symbol retries while successful symbols are skipped."""
    import sqlite3

    from src.data.storage.download_status import get_download_status
    from src.data.storage.market_data import load_bars

    # Reuse the existing runner-test setup and its synthetic bars.
    from tests.test_ingestion_runner import make_bars

    db = tmp_path / "batch.db"

    with sqlite3.connect(db) as conn:
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

    bars = make_bars()
    calls = []
    failures = {"MSFT": 1}

    def fetcher(symbol):
        calls.append(symbol)
        if failures.get(symbol, 0):
            failures[symbol] -= 1
            raise TimeoutError("Simulated temporary provider outage")
        return bars

    first = batch_ingestion.ingest_batch(
        db,
        ["AAPL", "MSFT", "NVDA"],
        as_of=AS_OF,
        fetcher=fetcher,
    )

    assert first.counts == {
        "SUCCESS": 2,
        "SKIPPED": 0,
        "FAILED": 1,
    }
    assert first.error_categories == {"PROVIDER_ERROR": 1}

    assert get_download_status(db, "MSFT").error_category == (
        "PROVIDER_ERROR"
    )
    assert load_bars(db, "MSFT") == []

    second = batch_ingestion.ingest_batch(
        db,
        ["AAPL", "MSFT", "NVDA"],
        as_of=AS_OF,
        fetcher=fetcher,
    )

    assert second.counts == {
        "SUCCESS": 1,
        "SKIPPED": 2,
        "FAILED": 0,
    }
    assert second.error_categories == {}
    assert calls == ["AAPL", "MSFT", "NVDA", "MSFT"]

    for symbol in ("AAPL", "MSFT", "NVDA"):
        assert get_download_status(db, symbol).status == "SUCCESS"
        assert len(load_bars(db, symbol)) >= 253

    assert get_download_status(db, "MSFT").error_category is None


def test_batch_reports_eligibility_separately():
    result = batch_ingestion.BatchResult(
        results=(
            IngestionResult(
                "AAPL", "SUCCESS", "PASS", 261, "Stored"
            ),
            IngestionResult(
                "IBIO", "SUCCESS", "FILTER_FAIL", 261, "Stored"
            ),
            IngestionResult(
                "MSFT", "SKIPPED", None, 0, "Previously stored"
            ),
            IngestionResult(
                "FCBM", "FAILED", None, 0, "Missing sessions",
                error_category="DATA_QUALITY_ERROR",
            ),
        ),
        requested=4,
    )

    assert result.counts == {
        "SUCCESS": 2,
        "SKIPPED": 1,
        "FAILED": 1,
    }

    assert result.eligibility_counts == {
        "PASS": 1,
        "FILTER_FAIL": 1,
        "DATA_INCOMPLETE": 0,
    }

    assert result.error_categories == {
        "DATA_QUALITY_ERROR": 1,
    }


def test_batch_resume_preserves_stored_eligibility(tmp_path):
    """Eligibility remains reportable after successful symbols are skipped."""
    import sqlite3

    from tests.test_ingestion_runner import make_bars
    from src.data.batch_reporting import report_stored_eligibility

    db = tmp_path / "resume_reporting.db"

    with sqlite3.connect(db) as conn:
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

    def fetcher(symbol):
        if symbol == "FCBM":
            raise TimeoutError("Simulated provider timeout")
        if symbol == "IBIO":
            return make_bars(close=2.0)
        return make_bars()

    symbols = ["AAPL", "IBIO", "FCBM"]

    first = batch_ingestion.ingest_batch(
        db,
        symbols,
        as_of=AS_OF,
        fetcher=fetcher,
    )

    assert first.counts == {
        "SUCCESS": 2,
        "SKIPPED": 0,
        "FAILED": 1,
    }

    second = batch_ingestion.ingest_batch(
        db,
        symbols,
        as_of=AS_OF,
        fetcher=fetcher,
    )

    assert second.counts == {
        "SUCCESS": 0,
        "SKIPPED": 2,
        "FAILED": 1,
    }

    report = report_stored_eligibility(
        db,
        symbols,
        as_of=AS_OF,
    )

    assert report.counts == {
        "PASS": 1,
        "FILTER_FAIL": 1,
        "DATA_INCOMPLETE": 1,
    }

    assert report.by_symbol == {
        "AAPL": "PASS",
        "IBIO": "FILTER_FAIL",
        "FCBM": "DATA_INCOMPLETE",
    }


def test_empty_batch_is_valid_noop(monkeypatch, tmp_path):
    def forbidden_ingest(*args, **kwargs):
        raise AssertionError("Empty batch must not ingest")

    monkeypatch.setattr(
        batch_ingestion,
        "ingest_symbol",
        forbidden_ingest,
    )

    result = batch_ingestion.ingest_batch(
        tmp_path / "unused.db",
        [],
        as_of=AS_OF,
        fetcher=lambda symbol: [],
    )

    assert result.requested == 0
    assert result.results == ()
    assert result.counts == {
        "SUCCESS": 0,
        "SKIPPED": 0,
        "FAILED": 0,
    }


def test_exactly_25_unique_symbols_are_accepted(
    monkeypatch, tmp_path
):
    calls = []

    def fake_ingest(db_path, symbol, *, as_of, fetcher, force):
        calls.append(symbol)
        return IngestionResult(
            symbol, "SKIPPED", None, 0, "Already stored"
        )

    monkeypatch.setattr(
        batch_ingestion, "ingest_symbol", fake_ingest
    )

    symbols = [f"T{i}" for i in range(25)]

    result = batch_ingestion.ingest_batch(
        tmp_path / "unused.db",
        symbols,
        as_of=AS_OF,
        fetcher=lambda symbol: [],
    )

    assert result.requested == 25
    assert len(calls) == 25
    assert result.counts["SKIPPED"] == 25


def test_duplicate_symbols_do_not_exceed_limit(
    monkeypatch, tmp_path
):
    calls = []

    def fake_ingest(db_path, symbol, *, as_of, fetcher, force):
        calls.append(symbol)
        return IngestionResult(
            symbol, "SKIPPED", None, 0, "Already stored"
        )

    monkeypatch.setattr(
        batch_ingestion, "ingest_symbol", fake_ingest
    )

    result = batch_ingestion.ingest_batch(
        tmp_path / "unused.db",
        ["aapl"] * 30,
        as_of=AS_OF,
        fetcher=lambda symbol: [],
    )

    assert result.requested == 1
    assert calls == ["AAPL"]
