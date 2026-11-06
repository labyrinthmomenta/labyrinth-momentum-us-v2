"""Resolve the latest US session eligible for daily ingestion."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import exchange_calendars as xcals


NEW_YORK = ZoneInfo("America/New_York")


def resolve_ingestion_session(
    *,
    at: datetime | None = None,
    settlement_delay_minutes: int = 60,
) -> date:
    """Return the latest XNYS session past its close buffer.

    Uses actual exchange closing times, including early closes
    and daylight-saving transitions. The buffer is not a
    guarantee that the data provider has published final data.
    """
    if at is None:
        at = datetime.now(timezone.utc)

    if (
        not isinstance(at, datetime)
        or at.tzinfo is None
        or at.utcoffset() is None
    ):
        raise ValueError(
            "at must be a timezone-aware datetime"
        )

    if (
        isinstance(settlement_delay_minutes, bool)
        or not isinstance(settlement_delay_minutes, int)
        or not 0 <= settlement_delay_minutes <= 240
    ):
        raise ValueError(
            "settlement_delay_minutes must be "
            "an integer between 0 and 240"
        )

    calendar = xcals.get_calendar("XNYS")

    new_york_date = at.astimezone(NEW_YORK).date()

    session = calendar.date_to_session(
        new_york_date,
        direction="previous",
    )

    closing_time = calendar.session_close(
        session
    ).to_pydatetime()

    eligible_time = closing_time + timedelta(
        minutes=settlement_delay_minutes
    )

    current_utc = at.astimezone(timezone.utc)

    if current_utc < eligible_time:
        session = calendar.previous_session(session)

    return session.date()
