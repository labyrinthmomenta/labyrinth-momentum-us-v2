"""Resumable single-symbol US market-data ingestion."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.calculation.engine import DataQualityError, PriceBar, compute_snapshot
from src.data.eligibility import check_eligibility
from src.data.providers.sessions import validate_recent_sessions
from src.data.storage.market_data import load_bars
from src.data.storage.atomic_ingestion import persist_complete_history
from src.data.storage.download_status import (
    get_download_status,
    update_download_status,
)


@dataclass(frozen=True)
class IngestionResult:
    symbol: str
    status: str
    eligibility: str | None
    rows: int
    reason: str


def ingest_symbol(
    db_path: str | Path,
    symbol: str,
    *,
    as_of: date,
    fetcher: Callable[[str], Sequence[PriceBar]],
    force: bool = False,
) -> IngestionResult:
    """Ingest one symbol; allow restart after incomplete attempts."""
    symbol = symbol.strip().upper()

    if not symbol:
        raise ValueError("Symbol cannot be empty")

    previous = get_download_status(db_path, symbol)

    if (
        not force
        and previous is not None
        and previous.status == "SUCCESS"
        and previous.last_session == as_of.isoformat()
    ):
        try:
            stored = load_bars(db_path, symbol)
            validate_recent_sessions(
                stored,
                as_of=as_of,
                required_sessions=253,
            )
        except (DataQualityError, ValueError):
            pass
        else:
            return IngestionResult(
                symbol, "SKIPPED", None, 0,
                "Previously ingested history validated",
            )

    update_download_status(db_path, symbol, "IN_PROGRESS")

    try:
        bars = list(fetcher(symbol))

        validate_recent_sessions(
            bars,
            as_of=as_of,
            required_sessions=253,
        )

        eligibility = check_eligibility(
            bars,
            as_of=as_of,
        )

        if eligibility.status == "DATA_INCOMPLETE":
            raise ValueError("Eligibility data incomplete")

        if eligibility.status == "PASS":
            compute_snapshot(bars, as_of=as_of)

        written = persist_complete_history(
            db_path,
            symbol,
            bars,
            as_of=as_of,
        )

        return IngestionResult(
            symbol,
            "SUCCESS",
            eligibility.status,
            written,
            "Validated and stored",
        )

    except Exception as exc:
        update_download_status(
            db_path,
            symbol,
            "FAILED",
            error_message=f"{type(exc).__name__}: {exc}"[:500],
        )

        return IngestionResult(
            symbol,
            "FAILED",
            None,
            0,
            f"{type(exc).__name__}: {exc}",
        )
