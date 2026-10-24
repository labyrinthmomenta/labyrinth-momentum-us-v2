"""Offline tests for ingestion error classification."""

import sqlite3

from src.calculation.engine import DataQualityError
from src.data.ingestion_errors import classify_ingestion_error


def test_missing_sessions_are_data_quality_error():
    exc = DataQualityError(
        "Missing 171 required sessions; first missing: 2025-10-13"
    )
    result = classify_ingestion_error(exc)

    assert result.category == "DATA_QUALITY_ERROR"
    assert result.retryable is False


def test_invalid_ohlc_is_data_quality_error():
    result = classify_ingestion_error(
        DataQualityError("Invalid OHLC")
    )
    assert result.category == "DATA_QUALITY_ERROR"


def test_timeout_is_retryable_provider_error():
    result = classify_ingestion_error(
        TimeoutError("Provider timeout")
    )
    assert result.category == "PROVIDER_ERROR"
    assert result.retryable is True


def test_connection_error_is_retryable():
    result = classify_ingestion_error(
        ConnectionError("Connection lost")
    )
    assert result.category == "PROVIDER_ERROR"
    assert result.retryable is True


def test_storage_error_is_not_immediately_retryable():
    result = classify_ingestion_error(
        sqlite3.OperationalError("Database is locked")
    )
    assert result.category == "STORAGE_ERROR"
    assert result.retryable is False


def test_unknown_error_is_not_misclassified():
    result = classify_ingestion_error(
        RuntimeError("Unexpected error")
    )
    assert result.category == "UNKNOWN_ERROR"
    assert result.retryable is False
