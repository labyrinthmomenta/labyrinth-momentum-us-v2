"""Offline classification tests for Yahoo unavailable-data errors."""

import pytest

from yfinance.exceptions import (
    YFPricesMissingError,
    YFTickerMissingError,
    YFTzMissingError,
)

from src.data.ingestion_errors import classify_ingestion_error
from src.data.batch_circuit_breaker import BatchCircuitBreaker


@pytest.mark.parametrize(
    "exc",
    [
        YFPricesMissingError("TEST", "Missing daily prices"),
        YFTickerMissingError("TEST", "Ticker unavailable"),
        YFTzMissingError("TEST"),
    ],
)
def test_yahoo_data_unavailable_is_not_retryable(exc):
    classified = classify_ingestion_error(exc)

    assert classified.category == "YAHOO_DATA_UNAVAILABLE"
    assert classified.retryable is False


def test_yahoo_data_unavailable_does_not_open_circuit():
    from types import SimpleNamespace

    breaker = BatchCircuitBreaker(
        max_consecutive_provider_errors=3
    )

    for _ in range(4):
        breaker.record(
            SimpleNamespace(
                status="FAILED",
                error_category="YAHOO_DATA_UNAVAILABLE",
            )
        )

    assert breaker.is_open is False
    assert breaker.consecutive_provider_errors == 0
