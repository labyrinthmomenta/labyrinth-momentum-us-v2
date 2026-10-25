"""Bounded retry wrapper for US market-data providers."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar
import time

from src.data.providers.request_pacer import RequestPacer


T = TypeVar("T")


@dataclass(frozen=True)
class FetchPolicy:
    max_attempts: int = 3
    retry_delay_seconds: float = 2.0

    def __post_init__(self):
        if not 1 <= self.max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        if not 0 <= self.retry_delay_seconds <= 60:
            raise ValueError(
                "retry_delay_seconds must be between 0 and 60"
            )


def fetch_with_retry(
    operation: Callable[[], T],
    *,
    policy: FetchPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    pacer: RequestPacer | None = None,
) -> T:
    """Retry transient connection failures with bounded attempts."""
    if policy is None:
        policy = FetchPolicy()

    for attempt in range(1, policy.max_attempts + 1):
        try:
            if pacer is not None:
                pacer.wait_for_slot()
            return operation()
        except (TimeoutError, ConnectionError):
            if attempt == policy.max_attempts:
                raise
            if policy.retry_delay_seconds > 0:
                sleep(policy.retry_delay_seconds)

    raise AssertionError("Unreachable retry state")
