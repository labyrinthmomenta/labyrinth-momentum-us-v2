"""Circuit breaker for consecutive provider failures."""

from dataclasses import dataclass

from src.data.ingestion_runner import IngestionResult


@dataclass
class BatchCircuitBreaker:
    max_consecutive_provider_errors: int = 3
    consecutive_provider_errors: int = 0
    is_open: bool = False

    def __post_init__(self):
        if not 1 <= self.max_consecutive_provider_errors <= 10:
            raise ValueError(
                "max_consecutive_provider_errors must be between 1 and 10"
            )

    def record(self, result: IngestionResult) -> None:
        """Observe an ingestion outcome and update circuit state."""
        if self.is_open:
            return

        if result.status == "SKIPPED":
            return

        if (
            result.status == "FAILED"
            and result.error_category == "PROVIDER_ERROR"
        ):
            self.consecutive_provider_errors += 1
        else:
            self.consecutive_provider_errors = 0

        if (
            self.consecutive_provider_errors
            >= self.max_consecutive_provider_errors
        ):
            self.is_open = True
