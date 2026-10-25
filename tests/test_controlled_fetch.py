"""Offline tests for bounded provider retries."""

import pytest

from src.calculation.engine import DataQualityError
from src.data.providers.controlled_fetch import (
    FetchPolicy,
    fetch_with_retry,
)


def test_success_on_first_attempt():
    calls = []

    def operation():
        calls.append(1)
        return "OK"

    result = fetch_with_retry(
        operation,
        sleep=lambda seconds: pytest.fail("Unexpected sleep"),
    )

    assert result == "OK"
    assert len(calls) == 1


def test_timeout_then_success():
    calls = []
    delays = []

    def operation():
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("Temporary timeout")
        return "RECOVERED"

    result = fetch_with_retry(
        operation,
        policy=FetchPolicy(
            max_attempts=3,
            retry_delay_seconds=2.0,
        ),
        sleep=delays.append,
    )

    assert result == "RECOVERED"
    assert len(calls) == 3
    assert delays == [2.0, 2.0]


def test_connection_error_stops_at_limit():
    calls = []
    delays = []

    def operation():
        calls.append(1)
        raise ConnectionError("Offline")

    with pytest.raises(ConnectionError, match="Offline"):
        fetch_with_retry(
            operation,
            policy=FetchPolicy(
                max_attempts=3,
                retry_delay_seconds=1.5,
            ),
            sleep=delays.append,
        )

    assert len(calls) == 3
    assert delays == [1.5, 1.5]


def test_data_quality_error_is_not_retried():
    calls = []

    def operation():
        calls.append(1)
        raise DataQualityError("Invalid OHLC")

    with pytest.raises(DataQualityError, match="Invalid OHLC"):
        fetch_with_retry(
            operation,
            sleep=lambda seconds: pytest.fail("Unexpected sleep"),
        )

    assert len(calls) == 1


def test_unknown_exception_is_not_retried():
    calls = []

    def operation():
        calls.append(1)
        raise RuntimeError("Unexpected failure")

    with pytest.raises(RuntimeError, match="Unexpected failure"):
        fetch_with_retry(
            operation,
            sleep=lambda seconds: pytest.fail("Unexpected sleep"),
        )

    assert len(calls) == 1


def test_invalid_policy_rejected():
    with pytest.raises(ValueError, match="max_attempts"):
        FetchPolicy(max_attempts=4)

    with pytest.raises(ValueError, match="max_attempts"):
        FetchPolicy(max_attempts=0)

    with pytest.raises(ValueError, match="retry_delay_seconds"):
        FetchPolicy(retry_delay_seconds=-1)


def test_shared_pacer_limits_first_requests_and_retries():
    from src.data.providers.request_pacer import RequestPacer

    class FakeClock:
        def __init__(self):
            self.now = 0.0
            self.delays = []

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.delays.append(seconds)
            self.now += seconds

    clock = FakeClock()

    pacer = RequestPacer(
        min_interval_seconds=3.0,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )

    attempts = []
    failures = {"AAPL": 1}

    def operation(symbol):
        attempts.append((symbol, clock.now))
        if failures.get(symbol, 0):
            failures[symbol] -= 1
            raise TimeoutError("Temporary failure")
        return symbol

    policy = FetchPolicy(
        max_attempts=2,
        retry_delay_seconds=0,
    )

    first = fetch_with_retry(
        lambda: operation("AAPL"),
        policy=policy,
        pacer=pacer,
        sleep=clock.sleep,
    )

    second = fetch_with_retry(
        lambda: operation("MSFT"),
        policy=policy,
        pacer=pacer,
        sleep=clock.sleep,
    )

    assert first == "AAPL"
    assert second == "MSFT"

    assert attempts == [
        ("AAPL", 0.0),
        ("AAPL", 3.0),
        ("MSFT", 6.0),
    ]

    assert clock.delays == [3.0, 3.0]
