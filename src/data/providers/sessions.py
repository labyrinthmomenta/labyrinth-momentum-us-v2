"""Validate US daily bars against an exchange trading calendar."""

from datetime import date
import math
from collections.abc import Sequence

import exchange_calendars as xcals

from src.calculation.engine import DataQualityError, PriceBar


def validate_recent_sessions(
    bars: Sequence[PriceBar],
    *,
    as_of: date,
    required_sessions: int = 90,
    exchange: str = "XNYS",
) -> list[PriceBar]:
    """Return the exact expected completed sessions or raise an error.

    as_of must already be a completed trading session.
    This function does not decide whether today's market is closed.
    """
    if required_sessions < 1:
        raise ValueError("required_sessions must be positive")

    calendar = xcals.get_calendar(exchange)

    if not calendar.is_session(as_of):
        raise DataQualityError(
            f"{as_of} is not an {exchange} trading session"
        )

    expected = calendar.sessions_window(
        as_of,
        -required_sessions,
    )

    by_date = {}

    for bar in bars:
        if bar.date in by_date:
            raise DataQualityError(
                f"Duplicate session: {bar.date}"
            )
        by_date[bar.date] = bar

    missing = [
        session.date()
        for session in expected
        if session.date() not in by_date
    ]

    if missing:
        raise DataQualityError(
            f"Missing {len(missing)} required sessions; "
            f"first missing: {missing[0]}"
        )

    validated = [by_date[session.date()] for session in expected]

    for bar in validated:
        prices = (bar.open, bar.high, bar.low, bar.close)

        if not all(math.isfinite(p) and p > 0 for p in prices):
            raise DataQualityError(
                f"Invalid price on {bar.date}"
            )

        if (
            bar.high < bar.low
            or bar.high < max(bar.open, bar.close)
            or bar.low > min(bar.open, bar.close)
        ):
            raise DataQualityError(
                f"Inconsistent OHLC on {bar.date}"
            )

        if (
            bar.volume is None
            or not math.isfinite(bar.volume)
            or bar.volume < 0
        ):
            raise DataQualityError(
                f"Invalid volume on {bar.date}"
            )

    return validated
