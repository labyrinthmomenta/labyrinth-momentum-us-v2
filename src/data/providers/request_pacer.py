"""Minimum spacing between market-data provider requests."""

from collections.abc import Callable
from dataclasses import dataclass, field
import time


@dataclass
class RequestPacer:
    min_interval_seconds: float = 3.0
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _last_request_start: float | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def __post_init__(self):
        if not 0 <= self.min_interval_seconds <= 60:
            raise ValueError(
                "min_interval_seconds must be between 0 and 60"
            )

    def wait_for_slot(self) -> None:
        """Wait until the next request may start."""
        now = self.clock()

        if self._last_request_start is not None:
            elapsed = now - self._last_request_start
            remaining = self.min_interval_seconds - elapsed

            if remaining > 0:
                self.sleep(remaining)

        self._last_request_start = self.clock()
