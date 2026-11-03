"""Safe incremental merging of US daily OHLCV histories."""

from collections.abc import Sequence
from datetime import date
import math

import exchange_calendars as xcals

from src.calculation.engine import DataQualityError, PriceBar
from src.data.providers.sessions import validate_recent_sessions


def _validate_sequence(
    bars: Sequence[PriceBar],
    *,
    name: str,
    calendar,
) -> None:
    """Reject malformed, unordered or non-session OHLCV bars."""
    previous = None

    for bar in bars:
        if previous is not None and bar.date <= previous:
            raise DataQualityError(
                f"{name}: dates must be strictly increasing"
            )

        if not calendar.is_session(bar.date):
            raise DataQualityError(
                f"{name}: invalid trading session {bar.date}"
            )

        prices = (bar.open, bar.high, bar.low, bar.close)

        if not all(
            math.isfinite(value) and value > 0
            for value in prices
        ):
            raise DataQualityError(
                f"{name}: invalid price on {bar.date}"
            )

        if (
            bar.high < bar.low
            or bar.high < max(bar.open, bar.close)
            or bar.low > min(bar.open, bar.close)
        ):
            raise DataQualityError(
                f"{name}: inconsistent OHLC on {bar.date}"
            )

        if (
            bar.volume is None
            or not math.isfinite(bar.volume)
            or bar.volume < 0
        ):
            raise DataQualityError(
                f"{name}: invalid volume on {bar.date}"
            )

        previous = bar.date


def merge_incremental_bars(
    stored: Sequence[PriceBar],
    fresh: Sequence[PriceBar],
    *,
    as_of: date,
    overlap_sessions: int = 30,
) -> list[PriceBar]:
    """Merge validated historical bars with a recent Yahoo window.

    Rules:
    - Stored history must contain at least 253 complete sessions.
    - A new completed session must exist.
    - The last overlap_sessions stored bars must be present in fresh.
    - Every shared session must have identical OHLCV values.
    - Every new trading session up to as_of must be present.
    - Result must retain complete historical coverage.

    This function performs no network calls or database writes.
    """
    if not isinstance(as_of, date):
        raise ValueError("as_of must be a date")

    if (
        isinstance(overlap_sessions, bool)
        or not isinstance(overlap_sessions, int)
        or not 1 <= overlap_sessions <= 90
    ):
        raise ValueError(
            "overlap_sessions must be an integer from 1 to 90"
        )

    stored = list(stored)
    fresh = list(fresh)

    if not stored:
        raise DataQualityError("Stored history is empty")

    if not fresh:
        raise DataQualityError("Fresh history is empty")

    calendar = xcals.get_calendar("XNYS")

    if not calendar.is_session(as_of):
        raise DataQualityError(
            f"{as_of} is not a completed XNYS session"
        )

    _validate_sequence(
        stored,
        name="Stored history",
        calendar=calendar,
    )

    _validate_sequence(
        fresh,
        name="Fresh history",
        calendar=calendar,
    )

    stored_last = stored[-1].date

    if stored_last >= as_of:
        raise DataQualityError(
            "Incremental merge requires a newer session"
        )

    if fresh[-1].date != as_of:
        raise DataQualityError(
            f"Fresh history must end at {as_of}"
        )

    if len(stored) < 253:
        raise DataQualityError(
            "Stored history has fewer than 253 sessions"
        )

    if len(stored) < overlap_sessions:
        raise DataQualityError(
            "Stored history is shorter than overlap window"
        )

    # Verify existing history before using it as the baseline.
    validate_recent_sessions(
        stored,
        as_of=stored_last,
        required_sessions=253,
    )

    stored_by_date = {
        bar.date: bar for bar in stored
    }

    fresh_by_date = {
        bar.date: bar for bar in fresh
    }

    # All required overlap dates must be present.
    overlap_dates = [
        bar.date for bar in stored[-overlap_sessions:]
    ]

    missing_overlap = [
        session
        for session in overlap_dates
        if session not in fresh_by_date
    ]

    if missing_overlap:
        raise DataQualityError(
            "Missing required overlap session: "
            f"{missing_overlap[0]}"
        )

    # Compare every shared date, not merely the minimum overlap.
    for session, incoming in fresh_by_date.items():
        existing = stored_by_date.get(session)

        if existing is not None and incoming != existing:
            raise DataQualityError(
                "OHLCV overlap mismatch on "
                f"{session}; full-history review required"
            )

    # Check every session between stored history and as_of.
    expected_new = [
        session.date()
        for session in calendar.sessions_in_range(
            stored_last.isoformat(),
            as_of.isoformat(),
        )
        if session.date() > stored_last
    ]

    missing_new = [
        session
        for session in expected_new
        if session not in fresh_by_date
    ]

    if missing_new:
        raise DataQualityError(
            "Missing new trading session: "
            f"{missing_new[0]}"
        )

    new_bars = [
        fresh_by_date[session]
        for session in expected_new
    ]

    merged = stored + new_bars

    # Final calendar and OHLCV validation.
    validate_recent_sessions(
        merged,
        as_of=as_of,
        required_sessions=253,
    )

    return merged
