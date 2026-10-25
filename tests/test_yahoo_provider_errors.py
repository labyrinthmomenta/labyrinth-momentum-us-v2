"""Offline regression tests for Yahoo provider failures."""

from datetime import date

import pytest

from src.data.providers.yahoo import fetch_price_bars


START = date(2025, 10, 1)
END = date(2026, 10, 15)


def test_yahoo_timeout_preserves_provider_error():
    def timed_out_download(*args, **kwargs):
        raise TimeoutError("Simulated Yahoo timeout")

    with pytest.raises(TimeoutError, match="Simulated Yahoo timeout"):
        fetch_price_bars(
            "AAPL",
            start=START,
            end=END,
            downloader=timed_out_download,
        )


def test_yahoo_connection_error_preserves_provider_error():
    def disconnected_download(*args, **kwargs):
        raise ConnectionError("Simulated connection failure")

    with pytest.raises(
        ConnectionError,
        match="Simulated connection failure",
    ):
        fetch_price_bars(
            "AAPL",
            start=START,
            end=END,
            downloader=disconnected_download,
        )
