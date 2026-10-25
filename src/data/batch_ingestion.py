"""Controlled batch ingestion for the US bootstrap universe."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.calculation.engine import PriceBar
from src.data.ingestion_runner import IngestionResult, ingest_symbol


@dataclass(frozen=True)
class BatchResult:
    results: tuple[IngestionResult, ...]
    requested: int

    @property
    def counts(self) -> dict[str, int]:
        counts = {
            "SUCCESS": 0,
            "SKIPPED": 0,
            "FAILED": 0,
        }
        for result in self.results:
            counts[result.status] += 1
        return counts

    @property
    def eligibility_counts(self) -> dict[str, int]:
        counts = {
            "PASS": 0,
            "FILTER_FAIL": 0,
            "DATA_INCOMPLETE": 0,
        }
        for result in self.results:
            if result.eligibility in counts:
                counts[result.eligibility] += 1
        return counts

    @property
    def error_categories(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for result in self.results:
            if result.status == "FAILED":
                category = result.error_category or "UNCLASSIFIED"
                counts[category] = counts.get(category, 0) + 1
        return counts


def ingest_batch(
    db_path: str | Path,
    symbols: Sequence[str],
    *,
    as_of: date,
    fetcher: Callable[[str], Sequence[PriceBar]],
    max_symbols: int = 25,
    force: bool = False,
) -> BatchResult:
    """Ingest a bounded batch with deterministic input ordering."""
    if not 1 <= max_symbols <= 25:
        raise ValueError("max_symbols must be between 1 and 25")

    normalized = tuple(dict.fromkeys(
        symbol.strip().upper() for symbol in symbols
    ))

    if any(not symbol for symbol in normalized):
        raise ValueError("Empty symbol in batch")

    if len(normalized) > max_symbols:
        raise ValueError(
            f"Batch contains {len(normalized)} symbols; "
            f"limit is {max_symbols}"
        )

    results = tuple(
        ingest_symbol(
            db_path,
            symbol,
            as_of=as_of,
            fetcher=fetcher,
            force=force,
        )
        for symbol in normalized
    )

    return BatchResult(
        results=results,
        requested=len(normalized),
    )
