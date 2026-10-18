"""Offline tests for US price and dollar-liquidity filters."""

from datetime import date

import exchange_calendars as xcals
import pytest

from src.calculation.engine import PriceBar
from src.data.eligibility import check_eligibility


AS_OF = date(2026, 10, 14)


def make_bars(close=10.0, volume=200_000.0):
    cal = xcals.get_calendar("XNYS")
    sessions = cal.sessions_window(AS_OF.isoformat(), -90)

    return [
        PriceBar(
            date=session.date(),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=volume,
        )
        for session in sessions
    ]


def test_both_thresholds_pass():
    result = check_eligibility(make_bars(), as_of=AS_OF)
    assert result.status == "PASS"
    assert result.last_close == 10.0
    assert result.adv90_usd == 2_000_000.0


def test_price_exactly_five_fails():
    result = check_eligibility(
        make_bars(close=5.0, volume=300_000),
        as_of=AS_OF,
    )
    assert result.status == "FILTER_FAIL"


def test_price_below_five_fails():
    result = check_eligibility(
        make_bars(close=4.99, volume=300_000),
        as_of=AS_OF,
    )
    assert result.status == "FILTER_FAIL"


def test_adv_exactly_one_million_fails():
    result = check_eligibility(
        make_bars(close=10, volume=100_000),
        as_of=AS_OF,
    )
    assert result.adv90_usd == 1_000_000
    assert result.status == "FILTER_FAIL"


def test_adv_below_one_million_fails():
    result = check_eligibility(
        make_bars(close=10, volume=99_999),
        as_of=AS_OF,
    )
    assert result.status == "FILTER_FAIL"


def test_missing_middle_session_is_incomplete():
    bars = make_bars()
    bars.pop(40)

    result = check_eligibility(bars, as_of=AS_OF)
    assert result.status == "DATA_INCOMPLETE"


def test_missing_last_session_is_incomplete():
    bars = make_bars()
    bars.pop()

    result = check_eligibility(bars, as_of=AS_OF)
    assert result.status == "DATA_INCOMPLETE"


def test_nan_price_is_incomplete():
    bars = make_bars()
    bars[30] = PriceBar(
        date=bars[30].date,
        open=10,
        high=10,
        low=10,
        close=float("nan"),
        volume=200_000,
    )

    result = check_eligibility(bars, as_of=AS_OF)
    assert result.status == "DATA_INCOMPLETE"


def test_infinite_volume_is_incomplete():
    bars = make_bars()
    bars[30] = PriceBar(
        date=bars[30].date,
        open=10,
        high=10,
        low=10,
        close=10,
        volume=float("inf"),
    )

    result = check_eligibility(bars, as_of=AS_OF)
    assert result.status == "DATA_INCOMPLETE"


def test_zero_volume_is_valid_but_fails_liquidity():
    result = check_eligibility(
        make_bars(close=10, volume=0),
        as_of=AS_OF,
    )

    assert result.status == "FILTER_FAIL"
    assert result.adv90_usd == 0


def test_empty_history_is_incomplete():
    result = check_eligibility([], as_of=AS_OF)
    assert result.status == "DATA_INCOMPLETE"
