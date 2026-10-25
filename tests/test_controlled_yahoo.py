"""Offline integration tests for the controlled Yahoo adapter."""

from datetime import date

import pytest

from src.calculation.engine import DataQualityError
from src.data.providers.controlled_fetch import FetchPolicy
from src.data.providers.controlled_yahoo import (
    make_controlled_yahoo_fetcher,
)
from src.data.providers.request_pacer import RequestPacer


START = date(2025, 10, 1)
END = date(2026, 10, 15)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.delays = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.delays.append(seconds)
        self.now += seconds


def make_pacer(clock):
    return RequestPacer(
        min_interval_seconds=3.0,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )


def test_symbols_share_the_same_pacer():
    clock = FakeClock()
    calls = []

    def provider(symbol, *, start, end):
        calls.append((symbol, clock.now))
        assert start == START
        assert end == END
        return []

    fetch = make_controlled_yahoo_fetcher(
        start=START,
        end=END,
        pacer=make_pacer(clock),
        provider=provider,
    )

    assert fetch("AAPL") == []
    assert fetch("MSFT") == []
    assert fetch("NVDA") == []

    assert calls == [
        ("AAPL", 0.0),
        ("MSFT", 3.0),
        ("NVDA", 6.0),
    ]
    assert clock.delays == [3.0, 3.0]


def test_timeout_is_retried_with_shared_pacer():
    clock = FakeClock()
    calls = []

    def provider(symbol, *, start, end):
        calls.append((symbol, clock.now))
        if len(calls) == 1:
            raise TimeoutError("Temporary timeout")
        return []

    fetch = make_controlled_yahoo_fetcher(
        start=START,
        end=END,
        pacer=make_pacer(clock),
        policy=FetchPolicy(
            max_attempts=3,
            retry_delay_seconds=0,
        ),
        provider=provider,
    )

    assert fetch("AAPL") == []
    assert calls == [
        ("AAPL", 0.0),
        ("AAPL", 3.0),
    ]


def test_data_quality_error_is_not_retried():
    clock = FakeClock()
    calls = []

    def provider(symbol, *, start, end):
        calls.append(symbol)
        raise DataQualityError("Invalid OHLCV")

    fetch = make_controlled_yahoo_fetcher(
        start=START,
        end=END,
        pacer=make_pacer(clock),
        provider=provider,
    )

    with pytest.raises(DataQualityError, match="Invalid OHLCV"):
        fetch("AAPL")

    assert calls == ["AAPL"]
    assert clock.delays == []
