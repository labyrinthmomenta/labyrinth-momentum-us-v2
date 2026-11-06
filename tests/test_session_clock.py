"""Regression tests for the US daily ingestion session clock."""

from datetime import date, datetime

import pytest

from src.data.session_clock import resolve_ingestion_session


@pytest.mark.parametrize(
    "instant, expected",
    [
        # Normal session: 16:00 New York close,
        # plus the default 60-minute safety buffer.
        ("2026-11-04T20:59:00+00:00", "2026-11-03"),
        ("2026-11-04T21:00:00+00:00", "2026-11-03"),
        ("2026-11-04T21:59:59+00:00", "2026-11-03"),
        ("2026-11-04T22:00:00+00:00", "2026-11-04"),

        # Istanbul clock: New York is still trading.
        ("2026-11-04T22:53:00+03:00", "2026-11-03"),

        # Weekend and next Monday before market close.
        ("2026-11-07T16:00:00+00:00", "2026-11-06"),
        ("2026-11-09T14:00:00+00:00", "2026-11-06"),

        # Thanksgiving: Thursday closed.
        ("2026-11-26T19:00:00+00:00", "2026-11-25"),

        # Day after Thanksgiving: early close at
        # 13:00 New York / 18:00 UTC.
        ("2026-11-27T17:59:00+00:00", "2026-11-25"),
        ("2026-11-27T18:59:59+00:00", "2026-11-25"),
        ("2026-11-27T19:00:00+00:00", "2026-11-27"),

        # US daylight-saving transition:
        # March 6 closes at 21:00 UTC,
        # March 9 closes at 20:00 UTC.
        ("2026-03-06T21:59:59+00:00", "2026-03-05"),
        ("2026-03-06T22:00:00+00:00", "2026-03-06"),
        ("2026-03-09T20:59:59+00:00", "2026-03-06"),
        ("2026-03-09T21:00:00+00:00", "2026-03-09"),
    ],
)
def test_session_resolution(instant, expected):
    result = resolve_ingestion_session(
        at=datetime.fromisoformat(instant)
    )

    assert result == date.fromisoformat(expected)


def test_rejects_naive_datetime():
    with pytest.raises(ValueError):
        resolve_ingestion_session(
            at=datetime(2026, 11, 4, 22, 0)
        )


@pytest.mark.parametrize(
    "delay",
    [-1, 241, True, 1.5],
)
def test_rejects_invalid_delay(delay):
    with pytest.raises(ValueError):
        resolve_ingestion_session(
            at=datetime.fromisoformat(
                "2026-11-04T22:00:00+00:00"
            ),
            settlement_delay_minutes=delay,
        )


def test_zero_delay_allows_immediate_close():
    result = resolve_ingestion_session(
        at=datetime.fromisoformat(
            "2026-11-04T21:00:00+00:00"
        ),
        settlement_delay_minutes=0,
    )

    assert result == date(2026, 11, 4)
