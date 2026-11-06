"""Safety-gated daily ingestion runner for the US pilot."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path

from src.calculation.engine import PriceBar
from src.data.daily_batch_orchestrator import (
    DailyBatchResult,
    run_daily_batches,
)
from src.data.daily_run_report import (
    write_daily_run_report,
    write_aborted_run_report,
)
from src.data.incremental_history_fetcher import (
    make_incremental_history_fetcher,
)
from src.data.session_clock import resolve_ingestion_session
from src.data.daily_run_lock import hold_daily_ingestion_lock


MAX_PILOT_SYMBOLS = 25


@dataclass(frozen=True)
class DailyIngestionOutcome:
    """Result and audit location for a daily pilot run."""

    as_of: date
    report_path: Path
    result: DailyBatchResult


def _validate_bootstrap_config(config_path: Path) -> None:
    """Fail closed unless US production publication is disabled."""
    if not config_path.is_file():
        raise FileNotFoundError(config_path)

    config = json.loads(
        config_path.read_text(encoding="utf-8")
    )

    if not isinstance(config, dict):
        raise ValueError("US configuration must be an object")

    if (
        config.get("market") != "US"
        or config.get("status") != "BOOTSTRAP_ONLY"
        or config.get("publication_enabled") is not False
        or config.get("vcp_production_enabled") is not False
    ):
        raise ValueError(
            "US bootstrap safety gate rejected configuration"
        )


def _normalize_pilot_symbols(
    symbols: Sequence[str],
) -> tuple[str, ...]:
    """Normalize and bound the explicitly supplied pilot universe."""
    if isinstance(symbols, (str, bytes)):
        raise ValueError("symbols must be a sequence")

    normalized = []
    seen = set()

    for raw in symbols:
        if not isinstance(raw, str):
            raise ValueError("Symbols must be strings")

        symbol = raw.strip().upper()

        if not symbol:
            raise ValueError("Blank symbol in pilot universe")

        if symbol not in seen:
            seen.add(symbol)
            normalized.append(symbol)

    if not normalized:
        raise ValueError("Pilot universe cannot be empty")

    if len(normalized) > MAX_PILOT_SYMBOLS:
        raise ValueError(
            "Pilot universe cannot exceed 25 unique symbols"
        )

    return tuple(normalized)


def run_daily_ingestion(
    *,
    db_path: str | Path,
    config_path: str | Path,
    report_path: str | Path,
    symbols: Sequence[str],
    full_start: date,
    provider: Callable[..., list[PriceBar]] | None = None,
    at: datetime | None = None,
    batch_size: int = 25,
    overlap_sessions: int = 30,
    settlement_delay_minutes: int = 60,
) -> DailyIngestionOutcome:
    """Run one explicitly authorized, bounded US pilot ingestion.

    All validation is performed before constructing the fetcher.

    The caller must explicitly supply a provider.
    This function does not automatically select live Yahoo.

    The existing ingestion layer performs atomic SQLite writes.
    The audit writer creates a separate, non-overwriting JSON file.
    """
    db_path = Path(db_path)
    config_path = Path(config_path)
    report_path = Path(report_path)

    # Validate safety constraints before any ingestion work.
    _validate_bootstrap_config(config_path)

    if not db_path.is_file():
        raise FileNotFoundError(db_path)

    # Protect ingestion and audit publication together.
    with hold_daily_ingestion_lock(db_path):
        if report_path.exists() or report_path.is_symlink():
            raise FileExistsError(
                f"Audit report already exists: {report_path}"
            )

        if provider is None or not callable(provider):
            raise ValueError(
                "An explicit callable provider is required"
            )

        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or not 1 <= batch_size <= 25
        ):
            raise ValueError(
                "batch_size must be an integer from 1 to 25"
            )

        if (
            not isinstance(full_start, date)
            or isinstance(full_start, datetime)
        ):
            raise ValueError("full_start must be a date")

        if at is None:
            at = datetime.now(timezone.utc)

        if (
            not isinstance(at, datetime)
            or at.tzinfo is None
            or at.utcoffset() is None
        ):
            raise ValueError(
                "at must be a timezone-aware datetime"
            )

        normalized = _normalize_pilot_symbols(symbols)

        # 1. Resolve the latest eligible US trading session.
        as_of = resolve_ingestion_session(
            at=at,
            settlement_delay_minutes=settlement_delay_minutes,
        )

        if full_start > as_of:
            raise ValueError(
                "full_start cannot be after the target session"
            )

        # 2-4. Run fetcher, batches, and audit under
        # the exclusive database lock.
        phase = "FETCHER_INITIALIZATION"

        try:
            fetcher = make_incremental_history_fetcher(
                db_path,
                as_of=as_of,
                full_start=full_start,
                overlap_sessions=overlap_sessions,
                provider=provider,
            )

            phase = "BATCH_EXECUTION"

            result = run_daily_batches(
                db_path,
                normalized,
                as_of=as_of,
                fetcher=fetcher,
                batch_size=batch_size,
                force=False,
            )

            phase = "AUDIT_WRITE"

            output_path = write_daily_run_report(
                result,
                as_of=as_of,
                report_path=report_path,
            )

        except Exception as exc:
            # An exception may occur after partial SQLite
            # writes. Completion counts are therefore unknown.
            #
            # Only attempt an ABORTED report if a completed
            # report has not already appeared at this path.
            if (
                not report_path.exists()
                and not report_path.is_symlink()
            ):
                try:
                    write_aborted_run_report(
                        as_of=as_of,
                        report_path=report_path,
                        symbols=normalized,
                        error=exc,
                        phase=phase,
                    )
                except Exception as audit_error:
                    # Never mask the original ingestion error
                    # if audit persistence also fails.
                    exc.add_note(
                        "ABORTED report could not be written: "
                        f"{type(audit_error).__name__}: "
                        f"{audit_error}"
                    )

            raise

        return DailyIngestionOutcome(
            as_of=as_of,
            report_path=output_path,
            result=result,
        )
