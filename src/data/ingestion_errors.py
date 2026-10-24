"""Classification of US data-ingestion failures."""

import sqlite3
from dataclasses import dataclass

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
