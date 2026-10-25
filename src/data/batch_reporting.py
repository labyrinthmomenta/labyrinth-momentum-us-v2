"""Read-only eligibility reporting for completed US batches."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.calculation.engine import DataQualityError
from src.data.eligibility import check_eligibility
from src.data.providers.sessions import validate_recent_sessions
from src.data.storage.market_data import load_bars


@dataclass(frozen=True)
class EligibilityReport:
    counts: dict[str, int]
    by_symbol: dict[str, str]


def report_stored_eligibility(
    db_path: str | Path,
    symbols: Sequence[str],
    *,
    as_of: date,
) -> EligibilityReport:
    """Recalculate eligibility from persisted OHLCV without writes."""
    normalized = tuple(dict.fromkeys(
        symbol.strip().upper() for symbol in symbols
    ))

    if any(not symbol for symbol in normalized):
        raise ValueError("Empty symbol in report")

    counts = {
        "PASS": 0,
        "FILTER_FAIL": 0,
        "DATA_INCOMPLETE": 0,
    }
    by_symbol: dict[str, str] = {}

    for symbol in normalized:
        bars = load_bars(db_path, symbol)

        try:
            validate_recent_sessions(
                bars,
                as_of=as_of,
                required_sessions=253,
            )
            eligibility = check_eligibility(
                bars,
                as_of=as_of,
            )
            status = eligibility.status
        except (DataQualityError, ValueError):
            status = "DATA_INCOMPLETE"

        counts[status] += 1
        by_symbol[symbol] = status

    return EligibilityReport(
        counts=counts,
        by_symbol=by_symbol,
    )
