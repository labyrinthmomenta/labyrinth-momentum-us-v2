"""Offline tests for provider request pacing."""

import pytest

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

    def advance(self, seconds):
        self.now += seconds


def test_first_request_has_no_delay():
    clock = FakeClock()
    pacer = RequestPacer(
        min_interval_seconds=3.0,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )

    pacer.wait_for_slot()

    assert clock.delays == []


def test_consecutive_requests_are_spaced():
    clock = FakeClock()
    pacer = RequestPacer(
        min_interval_seconds=3.0,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )

    pacer.wait_for_slot()
    pacer.wait_for_slot()
    pacer.wait_for_slot()

    assert clock.delays == [3.0, 3.0]
    assert clock.now == 6.0


def test_partial_elapsed_time_reduces_delay():
    clock = FakeClock()
    pacer = RequestPacer(
        min_interval_seconds=3.0,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )

    pacer.wait_for_slot()
    clock.advance(1.25)
    pacer.wait_for_slot()

    assert clock.delays == [1.75]
    assert clock.now == 3.0


def test_no_delay_after_sufficient_elapsed_time():
    clock = FakeClock()
    pacer = RequestPacer(
        min_interval_seconds=3.0,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )

    pacer.wait_for_slot()
    clock.advance(5.0)
    pacer.wait_for_slot()

    assert clock.delays == []


def test_zero_interval_allows_immediate_requests():
    clock = FakeClock()
    pacer = RequestPacer(
        min_interval_seconds=0,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )

    pacer.wait_for_slot()
    pacer.wait_for_slot()

    assert clock.delays == []


def test_invalid_interval_rejected():
    with pytest.raises(ValueError, match="min_interval_seconds"):
        RequestPacer(min_interval_seconds=-1)

    with pytest.raises(ValueError, match="min_interval_seconds"):
        RequestPacer(min_interval_seconds=61)
