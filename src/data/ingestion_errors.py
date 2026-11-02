"""Classification of US data-ingestion failures."""

import sqlite3
from dataclasses import dataclass

from yfinance.exceptions import (
    YFPricesMissingError,
    YFRateLimitError,
    YFTickerMissingError,
    YFTzMissingError,
)

from src.calculation.engine import DataQualityError


@dataclass(frozen=True)
class IngestionError:
    category: str
    retryable: bool
    reason: str


def classify_ingestion_error(
    exc: Exception,
) -> IngestionError:
    """Classify known errors without guessing unknown causes."""
    message = str(exc)

    if isinstance(exc, YFRateLimitError):
        return IngestionError(
            "RATE_LIMIT_ERROR",
            False,
            message,
        )

    if isinstance(
        exc,
        (YFPricesMissingError, YFTickerMissingError, YFTzMissingError),
    ):
        return IngestionError(
            "YAHOO_DATA_UNAVAILABLE",
            False,
            message,
        )

    if isinstance(exc, DataQualityError):
        return IngestionError(
            "DATA_QUALITY_ERROR",
            False,
            message,
        )

    if isinstance(exc, sqlite3.Error):
        return IngestionError(
            "STORAGE_ERROR",
            False,
            message,
        )

    if isinstance(exc, (ConnectionError, TimeoutError)):
        return IngestionError(
            "PROVIDER_ERROR",
            True,
            message,
        )

    return IngestionError(
        "UNKNOWN_ERROR",
        False,
        message,
    )
