"""Offline tests for the single-symbol Yahoo history adapter."""

from datetime import date

import pandas as pd
import pytest
from yfinance.exceptions import YFRateLimitError

from src.calculation.engine import DataQualityError
from src.data.providers.yahoo_history import fetch_history_bars


START = date(2026, 10, 13)
END = date(2026, 10, 15)


def sample_frame():
    return pd.DataFrame(
        {
            "Open": [100.0, 102.0],
            "High": [103.0, 105.0],
            "Low": [99.0, 101.0],
            "Close": [102.0, 104.0],
            "Volume": [1000, 1200],
        },
        index=pd.to_datetime(["2026-10-13", "2026-10-14"]),
    )


def test_successful_history_conversion():
    class FakeTicker:
        def history(self, **kwargs):
            return sample_frame()

    bars = fetch_history_bars(
        "AAPL",
        start=START,
        end=END,
        ticker_factory=lambda symbol: FakeTicker(),
    )

    assert len(bars) == 2
    assert bars[-1].close == 104.0
    assert bars[-1].volume == 1200.0


def test_history_parameters_are_preserved():
    calls = []

    class FakeTicker:
        def history(self, **kwargs):
            calls.append(kwargs)
            return sample_frame()

    fetch_history_bars(
        " aapl ",
        start=START,
        end=END,
        ticker_factory=lambda symbol: FakeTicker(),
    )

    assert calls[0]["start"] == START.isoformat()
    assert calls[0]["end"] == END.isoformat()
    assert calls[0]["interval"] == "1d"
    assert calls[0]["auto_adjust"] is False
    assert calls[0]["actions"] is True
    assert calls[0]["raise_errors"] is True


def test_rate_limit_exception_is_preserved():
    class FakeTicker:
        def history(self, **kwargs):
            raise YFRateLimitError()

    with pytest.raises(YFRateLimitError):
        fetch_history_bars(
            "AAPL",
            start=START,
            end=END,
            ticker_factory=lambda symbol: FakeTicker(),
        )


def test_empty_history_is_data_quality_error():
    class FakeTicker:
        def history(self, **kwargs):
            return pd.DataFrame()

    with pytest.raises(DataQualityError, match="empty"):
        fetch_history_bars(
            "AAPL",
            start=START,
            end=END,
            ticker_factory=lambda symbol: FakeTicker(),
        )


def test_invalid_date_range_is_rejected():
    with pytest.raises(ValueError, match="start must be earlier"):
        fetch_history_bars(
            "AAPL",
            start=END,
            end=START,
            ticker_factory=lambda symbol: None,
        )


def test_connection_error_is_preserved():
    class FakeTicker:
        def history(self, **kwargs):
            raise ConnectionError("Simulated network failure")

    with pytest.raises(ConnectionError, match="Simulated"):
        fetch_history_bars(
            "AAPL",
            start=START,
            end=END,
            ticker_factory=lambda symbol: FakeTicker(),
        )
