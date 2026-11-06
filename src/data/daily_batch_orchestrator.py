"""Bounded daily US market-data batch orchestration."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.calculation.engine import PriceBar
from src.data.batch_circuit_breaker import BatchCircuitBreaker
from src.data.batch_ingestion import BatchResult, ingest_batch
from src.data.ingestion_runner import IngestionResult


@dataclass(frozen=True)
class DailyBatchResult:
    """Aggregate result of one bounded daily ingestion run."""

    batch_results: tuple[BatchResult, ...]
    requested: int
    stopped_early: bool = False
    unprocessed_symbols: tuple[str, ...] = ()

    @property
    def results(self) -> tuple[IngestionResult, ...]:
        """All attempted symbol results in execution order."""
        return tuple(
            item
            for batch in self.batch_results
            for item in batch.results
        )

    @property
    def counts(self) -> dict[str, int]:
        counts = {
            "SUCCESS": 0,
            "SKIPPED": 0,
            "FAILED": 0,
        }

        for batch in self.batch_results:
            for status, count in batch.counts.items():
                counts[status] += count

        return counts

    @property
    def eligibility_counts(self) -> dict[str, int]:
        counts = {
            "PASS": 0,
            "FILTER_FAIL": 0,
            "DATA_INCOMPLETE": 0,
        }

        for batch in self.batch_results:
            for status, count in batch.eligibility_counts.items():
                counts[status] += count

        return counts

    @property
    def error_categories(self) -> dict[str, int]:
        counts: dict[str, int] = {}

        for batch in self.batch_results:
            for category, count in batch.error_categories.items():
                counts[category] = (
                    counts.get(category, 0) + count
                )

        return counts


def run_daily_batches(
    db_path: str | Path,
    symbols: Sequence[str],
    *,
    as_of: date,
    fetcher: Callable[[str], Sequence[PriceBar]],
    batch_size: int = 25,
    force: bool = False,
    circuit_breaker: BatchCircuitBreaker | None = None,
) -> DailyBatchResult:
    """Execute sequential batches with a shared circuit breaker.

    The orchestrator does not fetch or persist data directly.
    Existing ingestion logic handles per-symbol status,
    validation, atomic storage, and same-session skipping.

    Stops before launching additional batches if the circuit
    breaker opens.
    """
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 25
    ):
        raise ValueError(
            "batch_size must be an integer from 1 to 25"
        )

    normalized: list[str] = []
    seen: set[str] = set()

    for raw_symbol in symbols:
        if not isinstance(raw_symbol, str):
            raise ValueError("Symbols must be strings")

        symbol = raw_symbol.strip().upper()

        if not symbol:
            raise ValueError("Empty symbol in daily universe")

        if symbol not in seen:
            seen.add(symbol)
            normalized.append(symbol)

    requested = len(normalized)

    if not normalized:
        return DailyBatchResult(
            batch_results=(),
            requested=0,
        )

    breaker = (
        circuit_breaker
        if circuit_breaker is not None
        else BatchCircuitBreaker()
    )

    # Never launch work when the circuit is already open.
    if breaker.is_open:
        return DailyBatchResult(
            batch_results=(),
            requested=requested,
            stopped_early=True,
            unprocessed_symbols=tuple(normalized),
        )

    completed_batches: list[BatchResult] = []
    unprocessed: tuple[str, ...] = ()

    for offset in range(0, requested, batch_size):
        # One shared breaker persists across all batches.
        if breaker.is_open:
            unprocessed = tuple(normalized[offset:])
            break

        batch_symbols = tuple(
            normalized[offset:offset + batch_size]
        )

        batch = ingest_batch(
            db_path,
            batch_symbols,
            as_of=as_of,
            fetcher=fetcher,
            max_symbols=batch_size,
            force=force,
            circuit_breaker=breaker,
        )

        completed_batches.append(batch)

        # Preserve all symbols remaining inside this batch
        # and in every subsequent, unstarted batch.
        if batch.stopped_early or breaker.is_open:
            unprocessed = (
                tuple(batch.unprocessed_symbols)
                + tuple(normalized[
                    offset + len(batch_symbols):
                ])
            )
            break

    return DailyBatchResult(
        batch_results=tuple(completed_batches),
        requested=requested,
        stopped_early=bool(unprocessed),
        unprocessed_symbols=unprocessed,
    )
