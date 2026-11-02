"""Offline tests for yfinance rate-limit handling."""

from datetime import date

import pytest
from yfinance.exceptions import YFRateLimitError

from src.data.ingestion_errors import classify_ingestion_error
from src.data.providers.yahoo import fetch_price_bars
from src.data.providers.controlled_fetch import (
    FetchPolicy,
    fetch_with_retry,
)


START = date(2025, 10, 1)
END = date(2026, 10, 15)


def test_yahoo_preserves_rate_limit_exception():
    def rate_limited_download(*args, **kwargs):
        raise YFRateLimitError()

    with pytest.raises(YFRateLimitError):
        fetch_price_bars(
            "AAPL",
            start=START,
            end=END,
            downloader=rate_limited_download,
        )


def test_rate_limit_is_classified_separately():
    classified = classify_ingestion_error(YFRateLimitError())

    assert classified.category == "RATE_LIMIT_ERROR"
    assert classified.retryable is False


def test_rate_limit_is_not_retried():
    calls = []

    def operation():
        calls.append(1)
        raise YFRateLimitError()

    with pytest.raises(YFRateLimitError):
        fetch_with_retry(
            operation,
            policy=FetchPolicy(max_attempts=3),
            sleep=lambda seconds: pytest.fail("Unexpected retry"),
        )

    assert len(calls) == 1
