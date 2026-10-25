"""Offline tests for the batch provider-error circuit breaker."""

import pytest

from src.data.batch_circuit_breaker import BatchCircuitBreaker
from src.data.ingestion_runner import IngestionResult


def result(status, category=None):
    return IngestionResult(
        symbol="AAPL",
        status=status,
        eligibility=None,
        rows=0,
        reason="Test outcome",
        error_category=category,
        retryable=(category == "PROVIDER_ERROR"),
    )


def test_three_consecutive_provider_errors_open_circuit():
    breaker = BatchCircuitBreaker()

    failure = result("FAILED", "PROVIDER_ERROR")

    breaker.record(failure)
    assert breaker.consecutive_provider_errors == 1
    assert not breaker.is_open

    breaker.record(failure)
    assert breaker.consecutive_provider_errors == 2
    assert not breaker.is_open

    breaker.record(failure)
    assert breaker.consecutive_provider_errors == 3
    assert breaker.is_open


def test_data_quality_failure_resets_provider_streak():
    breaker = BatchCircuitBreaker()

    breaker.record(result("FAILED", "PROVIDER_ERROR"))
    breaker.record(result("FAILED", "PROVIDER_ERROR"))
    breaker.record(result("FAILED", "DATA_QUALITY_ERROR"))

    assert breaker.consecutive_provider_errors == 0
    assert not breaker.is_open

    breaker.record(result("FAILED", "PROVIDER_ERROR"))
    assert breaker.consecutive_provider_errors == 1
    assert not breaker.is_open


def test_success_resets_provider_streak():
    breaker = BatchCircuitBreaker()

    breaker.record(result("FAILED", "PROVIDER_ERROR"))
    breaker.record(result("SUCCESS"))

    assert breaker.consecutive_provider_errors == 0
    assert not breaker.is_open


def test_circuit_stays_open_after_threshold():
    breaker = BatchCircuitBreaker()

    failure = result("FAILED", "PROVIDER_ERROR")

    for _ in range(3):
        breaker.record(failure)

    assert breaker.is_open

    breaker.record(result("SUCCESS"))

    assert breaker.is_open
    assert breaker.consecutive_provider_errors == 3


def test_custom_threshold():
    breaker = BatchCircuitBreaker(
        max_consecutive_provider_errors=2
    )

    failure = result("FAILED", "PROVIDER_ERROR")

    breaker.record(failure)
    assert not breaker.is_open

    breaker.record(failure)
    assert breaker.is_open


def test_invalid_threshold_rejected():
    with pytest.raises(
        ValueError,
        match="max_consecutive_provider_errors",
    ):
        BatchCircuitBreaker(max_consecutive_provider_errors=0)

    with pytest.raises(
        ValueError,
        match="max_consecutive_provider_errors",
    ):
        BatchCircuitBreaker(max_consecutive_provider_errors=11)



def test_skipped_preserves_provider_error_streak():
    breaker = BatchCircuitBreaker()

    breaker.record(result("FAILED", "PROVIDER_ERROR"))
    breaker.record(result("SKIPPED"))

    assert breaker.consecutive_provider_errors == 1
    assert not breaker.is_open

    breaker.record(result("FAILED", "PROVIDER_ERROR"))
    breaker.record(result("SKIPPED"))
    breaker.record(result("FAILED", "PROVIDER_ERROR"))

    assert breaker.consecutive_provider_errors == 3
    assert breaker.is_open
