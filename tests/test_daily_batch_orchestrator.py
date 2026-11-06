"""Offline contracts for bounded daily US ingestion orchestration."""

from datetime import date

import pytest

from src.data import daily_batch_orchestrator as orchestrator
from src.data.batch_circuit_breaker import BatchCircuitBreaker
from src.data.batch_ingestion import BatchResult
from src.data.ingestion_runner import IngestionResult


AS_OF = date(2026, 11, 2)


def skipped(symbol):
    return IngestionResult(
        symbol=symbol,
        status="SKIPPED",
        eligibility=None,
        rows=0,
        reason="Previously completed",
    )


def fake_fetcher(symbol):
    raise AssertionError(
        f"No actual provider call expected: {symbol}"
    )


def test_53_symbols_are_split_into_25_25_3(monkeypatch):
    calls = []
    breakers = []

    def fake_batch(db_path, symbols, **kwargs):
        calls.append(tuple(symbols))
        breakers.append(kwargs["circuit_breaker"])

        assert kwargs["as_of"] == AS_OF
        assert kwargs["max_symbols"] == 25
        assert kwargs["force"] is False

        return BatchResult(
            results=tuple(skipped(s) for s in symbols),
            requested=len(symbols),
        )

    monkeypatch.setattr(
        orchestrator, "ingest_batch", fake_batch
    )

    symbols = [f"SYM{i:03d}" for i in range(53)]

    result = orchestrator.run_daily_batches(
        "unused.db",
        symbols,
        as_of=AS_OF,
        fetcher=fake_fetcher,
    )

    assert list(map(len, calls)) == [25, 25, 3]
    assert [s for group in calls for s in group] == symbols

    # One circuit breaker is shared across every batch.
    assert len({id(b) for b in breakers}) == 1

    assert result.requested == 53
    assert result.counts == {
        "SUCCESS": 0,
        "SKIPPED": 53,
        "FAILED": 0,
    }
    assert result.unprocessed_symbols == ()
    assert not result.stopped_early


def test_symbols_normalized_and_deduplicated(monkeypatch):
    calls = []

    def fake_batch(db_path, symbols, **kwargs):
        calls.append(tuple(symbols))
        return BatchResult(
            results=tuple(skipped(s) for s in symbols),
            requested=len(symbols),
        )

    monkeypatch.setattr(
        orchestrator, "ingest_batch", fake_batch
    )

    result = orchestrator.run_daily_batches(
        "unused.db",
        [" aapl ", "MSFT", "aapl", " nvda "],
        as_of=AS_OF,
        fetcher=fake_fetcher,
        batch_size=2,
    )

    assert calls == [
        ("AAPL", "MSFT"),
        ("NVDA",),
    ]
    assert result.requested == 3


def test_rate_limit_stops_all_remaining_batches(monkeypatch):
    symbols = [f"SYM{i:03d}" for i in range(30)]
    calls = []

    def fake_batch(db_path, batch, **kwargs):
        calls.append(tuple(batch))

        failure = IngestionResult(
            symbol=batch[0],
            status="FAILED",
            eligibility=None,
            rows=0,
            reason="Yahoo rate limited",
            error_category="RATE_LIMIT_ERROR",
            retryable=False,
        )

        kwargs["circuit_breaker"].record(failure)

        return BatchResult(
            results=(failure,),
            requested=len(batch),
            stopped_early=True,
            unprocessed_symbols=tuple(batch[1:]),
        )

    monkeypatch.setattr(
        orchestrator, "ingest_batch", fake_batch
    )

    result = orchestrator.run_daily_batches(
        "unused.db",
        symbols,
        as_of=AS_OF,
        fetcher=fake_fetcher,
    )

    # Do not launch batch 2 after batch 1 opens circuit.
    assert len(calls) == 1
    assert len(calls[0]) == 25

    assert result.counts["FAILED"] == 1
    assert result.stopped_early
    assert result.unprocessed_symbols == tuple(symbols[1:])
    assert len(result.unprocessed_symbols) == 29


@pytest.mark.parametrize(
    "size",
    [0, 26, True, 1.5],
)
def test_invalid_batch_size_rejected(size):
    with pytest.raises(ValueError):
        orchestrator.run_daily_batches(
            "unused.db",
            ["AAPL"],
            as_of=AS_OF,
            fetcher=fake_fetcher,
            batch_size=size,
        )


def test_blank_symbol_rejected():
    with pytest.raises(ValueError):
        orchestrator.run_daily_batches(
            "unused.db",
            ["AAPL", "  ", "MSFT"],
            as_of=AS_OF,
            fetcher=fake_fetcher,
        )


def test_empty_universe_performs_no_work(monkeypatch):
    def forbidden_batch(*args, **kwargs):
        raise AssertionError("Batch must not run")

    monkeypatch.setattr(
        orchestrator, "ingest_batch", forbidden_batch
    )

    result = orchestrator.run_daily_batches(
        "unused.db",
        [],
        as_of=AS_OF,
        fetcher=fake_fetcher,
    )

    assert result.requested == 0
    assert result.batch_results == ()
    assert result.unprocessed_symbols == ()
    assert not result.stopped_early


def test_already_open_circuit_performs_no_work(monkeypatch):
    def forbidden_batch(*args, **kwargs):
        raise AssertionError("Batch must not run")

    monkeypatch.setattr(
        orchestrator, "ingest_batch", forbidden_batch
    )

    breaker = BatchCircuitBreaker()

    breaker.record(
        IngestionResult(
            symbol="AAPL",
            status="FAILED",
            eligibility=None,
            rows=0,
            reason="Rate limit",
            error_category="RATE_LIMIT_ERROR",
            retryable=False,
        )
    )

    assert breaker.is_open

    result = orchestrator.run_daily_batches(
        "unused.db",
        ["AAPL", "MSFT"],
        as_of=AS_OF,
        fetcher=fake_fetcher,
        circuit_breaker=breaker,
    )

    assert result.requested == 2
    assert result.stopped_early
    assert result.unprocessed_symbols == ("AAPL", "MSFT")
