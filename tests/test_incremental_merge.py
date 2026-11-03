"""Offline regression tests for safe incremental OHLCV merging."""

from dataclasses import replace
from datetime import date

import exchange_calendars as xcals
import pytest

from src.calculation.engine import DataQualityError, PriceBar
from src.data.incremental_merge import merge_incremental_bars


AS_OF = date(2026, 11, 2)
OVERLAP = 30


def sample_histories():
    """Generate 253 prior sessions and one new completed session."""
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_window(
        AS_OF.isoformat(),
        -254,
    )

    complete = []

    for index, session in enumerate(sessions):
        close = 100.0 + index * 0.1

        complete.append(
            PriceBar(
                date=session.date(),
                open=close,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=200_000.0,
            )
        )

    assert len(complete) == 254
    assert complete[-1].date == AS_OF

    stored = complete[:-1]
    fresh = complete[-(OVERLAP + 1):]

    return stored, fresh, complete


def test_valid_incremental_merge_adds_one_session():
    stored, fresh, expected = sample_histories()
    original = list(stored)

    merged = merge_incremental_bars(
        stored,
        fresh,
        as_of=AS_OF,
        overlap_sessions=OVERLAP,
    )

    assert merged == expected
    assert len(merged) == 254
    assert len({bar.date for bar in merged}) == 254
    assert stored == original


def test_changed_overlap_is_rejected():
    stored, fresh, _ = sample_histories()

    fresh[5] = replace(
        fresh[5],
        close=fresh[5].close + 0.5,
    )

    with pytest.raises(DataQualityError):
        merge_incremental_bars(
            stored,
            fresh,
            as_of=AS_OF,
            overlap_sessions=OVERLAP,
        )


def test_missing_session_in_new_window_is_rejected():
    stored, fresh, _ = sample_histories()

    del fresh[10]

    with pytest.raises(DataQualityError):
        merge_incremental_bars(
            stored,
            fresh,
            as_of=AS_OF,
            overlap_sessions=OVERLAP,
        )


def test_insufficient_overlap_is_rejected():
    stored, fresh, _ = sample_histories()

    too_short = fresh[-10:]

    with pytest.raises(DataQualityError):
        merge_incremental_bars(
            stored,
            too_short,
            as_of=AS_OF,
            overlap_sessions=OVERLAP,
        )


def test_missing_latest_session_is_rejected():
    stored, fresh, _ = sample_histories()

    without_latest = fresh[:-1]

    with pytest.raises(DataQualityError):
        merge_incremental_bars(
            stored,
            without_latest,
            as_of=AS_OF,
            overlap_sessions=OVERLAP,
        )
