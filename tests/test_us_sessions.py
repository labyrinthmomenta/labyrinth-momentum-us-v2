from datetime import date

import exchange_calendars as xcals
import pytest

from src.calculation.engine import DataQualityError, PriceBar
from src.data.providers.sessions import validate_recent_sessions


def make_bars(dates):
    return [
        PriceBar(
            date=d,
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1000,
        )
        for d in dates
    ]


def test_complete_90_sessions():
    cal = xcals.get_calendar("XNYS")
    sessions = cal.sessions_window("2026-10-14", -90)
    bars = make_bars([s.date() for s in sessions])

    result = validate_recent_sessions(
        bars,
        as_of=date(2026, 10, 14),
        required_sessions=90,
    )

    assert len(result) == 90
    assert result[0].date == date(2026, 6, 8)
    assert result[-1].date == date(2026, 10, 14)


def test_missing_session_is_rejected():
    cal = xcals.get_calendar("XNYS")
    sessions = cal.sessions_window("2026-10-14", -90)
    dates = [s.date() for s in sessions]
    bars = make_bars(dates[:-1])

    with pytest.raises(DataQualityError, match="Missing"):
        validate_recent_sessions(
            bars,
            as_of=date(2026, 10, 14),
            required_sessions=90,
        )


def test_non_trading_as_of_is_rejected():
    with pytest.raises(DataQualityError):
        validate_recent_sessions(
            make_bars([]),
            as_of=date(2026, 10, 17),
        )


def test_duplicate_session_is_rejected():
    cal = xcals.get_calendar("XNYS")
    sessions = cal.sessions_window("2026-10-14", -90)
    bars = make_bars([s.date() for s in sessions])
    bars.append(bars[-1])

    with pytest.raises(DataQualityError, match="Duplicate"):
        validate_recent_sessions(
            bars,
            as_of=date(2026, 10, 14),
            required_sessions=90,
        )


def test_rejects_nan_close_on_required_session():
    cal = xcals.get_calendar("XNYS")
    sessions = cal.sessions_window("2026-10-14", -90)
    bars = make_bars([s.date() for s in sessions])

    bars[-1] = PriceBar(
        date=bars[-1].date,
        open=100,
        high=101,
        low=99,
        close=float("nan"),
        volume=1000,
    )

    with pytest.raises(DataQualityError, match="Invalid price"):
        validate_recent_sessions(
            bars,
            as_of=date(2026, 10, 14),
            required_sessions=90,
        )


def test_rejects_missing_volume():
    cal = xcals.get_calendar("XNYS")
    sessions = cal.sessions_window("2026-10-14", -90)
    bars = make_bars([s.date() for s in sessions])

    bars[-1] = PriceBar(
        date=bars[-1].date,
        open=100,
        high=101,
        low=99,
        close=100,
        volume=None,
    )

    with pytest.raises(DataQualityError, match="Invalid volume"):
        validate_recent_sessions(
            bars,
            as_of=date(2026, 10, 14),
            required_sessions=90,
        )


def test_complete_253_sessions():
    cal = xcals.get_calendar("XNYS")
    sessions = cal.sessions_window("2026-10-14", -253)
    bars = make_bars([s.date() for s in sessions])

    result = validate_recent_sessions(
        bars,
        as_of=date(2026, 10, 14),
        required_sessions=253,
    )

    assert len(result) == 253
    assert result[-1].date == date(2026, 10, 14)
