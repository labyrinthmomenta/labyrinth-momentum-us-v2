"""Controlled incremental Yahoo history fetcher for US ingestion."""

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import exchange_calendars as xcals

from src.calculation.engine import DataQualityError, PriceBar
from src.data.incremental_merge import merge_incremental_bars
from src.data.providers.controlled_fetch import FetchPolicy
from src.data.providers.controlled_yahoo import (
    make_controlled_yahoo_history_fetcher,
)
from src.data.providers.request_pacer import RequestPacer
from src.data.providers.sessions import validate_recent_sessions
from src.data.providers.yahoo_history import fetch_history_bars
from src.data.storage.market_data import load_bars


def make_incremental_history_fetcher(
    db_path: str | Path,
    *,
    as_of: date,
    full_start: date,
    overlap_sessions: int = 30,
    pacer: RequestPacer | None = None,
    policy: FetchPolicy | None = None,
    provider: Callable[..., list[PriceBar]] = fetch_history_bars,
) -> Callable[[str], list[PriceBar]]:
    """Create a bounded, paced and read-only incremental fetcher.

    The returned fetcher reads existing SQLite history but never writes.
    The ingestion runner remains responsible for atomic persistence.

    as_of must refer to a completed US trading session.
    """
    if not isinstance(as_of, date):
        raise ValueError("as_of must be a date")

    if not isinstance(full_start, date):
        raise ValueError("full_start must be a date")

    if full_start > as_of:
        raise ValueError("full_start must not be after as_of")

    if (
        isinstance(overlap_sessions, bool)
        or not isinstance(overlap_sessions, int)
        or not 1 <= overlap_sessions <= 90
    ):
        raise ValueError(
            "overlap_sessions must be an integer from 1 to 90"
        )

    calendar = xcals.get_calendar("XNYS")

    if not calendar.is_session(as_of):
        raise DataQualityError(
            f"{as_of} is not an XNYS trading session"
        )

    db_path = Path(db_path)

    if not db_path.is_file():
        raise FileNotFoundError(db_path)

    if pacer is None:
        pacer = RequestPacer()

    if policy is None:
        policy = FetchPolicy()

    end = as_of + timedelta(days=1)

    def fetch(symbol: str) -> list[PriceBar]:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("A non-empty symbol is required")

        symbol = symbol.strip().upper()

        stored = load_bars(db_path, symbol)

        if stored:
            # Never silently treat partial existing history as new.
            if len(stored) < 253:
                raise DataQualityError(
                    f"{symbol}: stored history has fewer "
                    "than 253 sessions"
                )

            stored_last = stored[-1].date

            # Validate the existing baseline before contacting Yahoo.
            validate_recent_sessions(
                stored,
                as_of=stored_last,
                required_sessions=253,
            )

            if stored_last >= as_of:
                raise DataQualityError(
                    f"{symbol}: no newer completed session "
                    f"after {stored_last}"
                )

            request_start = stored[-overlap_sessions].date

        else:
            request_start = full_start

        # Share the same pacer and retry policy across all symbols.
        controlled_fetcher = (
            make_controlled_yahoo_history_fetcher(
                start=request_start,
                end=end,
                pacer=pacer,
                policy=policy,
                provider=provider,
            )
        )

        fresh = controlled_fetcher(symbol)

        if not stored:
            return fresh

        return merge_incremental_bars(
            stored,
            fresh,
            as_of=as_of,
            overlap_sessions=overlap_sessions,
        )

    return fetch
