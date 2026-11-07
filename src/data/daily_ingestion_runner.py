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
from src.data.daily_operations_policy import (
    evaluate_daily_preflight,
)


MAX_PILOT_SYMBOLS = 25

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPERATIONS_CONFIG_PATH = (
    PROJECT_ROOT / 'config/us_daily_operations.json'
)
PILOT_MANIFEST_PATH = (
    PROJECT_ROOT / 'config/us_pilot_manifest.json'
)
PINNED_MANIFEST_SHA256 = (
    '0b35135a9e55f9ff974dcab795f9ba52'
    'd8522b8fa50a033bc340d74acccffebd'
)


@dataclass(frozen=True)
class DailyIngestionOutcome:
    """Result and audit location for a daily pilot run."""

    as_of: date | None
    report_path: Path | None
    result: DailyBatchResult | None
    decision: str = 'READY'
    reason: str = ''


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



def _load_pinned_operational_policy() -> tuple[Path, str]:
    """Read and strictly verify the offline pilot operations policy.

    The expected manifest digest is independently pinned in
    this module. Changing the operations JSON cannot approve
    an alternative manifest or enable live execution.
    """
    path = Path(OPERATIONS_CONFIG_PATH)

    if not path.is_file():
        raise FileNotFoundError(path)

    def unique_keys(pairs):
        result = {}

        for key, value in pairs:
            if key in result:
                raise ValueError(
                    f"Duplicate operations key: {key}"
                )
            result[key] = value

        return result

    operations = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_keys,
    )

    if not isinstance(operations, dict):
        raise ValueError(
            "US daily operations configuration must be an object"
        )

    required = {
        "market",
        "mode",
        "manifest_path",
        "expected_manifest_sha256",
        "timezone",
        "not_before_local",
        "minimum_close_delay_minutes",
        "live_provider_enabled",
        "scheduled_execution_enabled",
        "publication_enabled",
    }

    if set(operations) != required:
        raise ValueError(
            "Unexpected US daily operations configuration schema"
        )

    if (
        operations["market"] != "US"
        or operations["mode"] != "PILOT_ONLY"
        or operations["manifest_path"]
        != "config/us_pilot_manifest.json"
        or operations["expected_manifest_sha256"]
        != PINNED_MANIFEST_SHA256
        or operations["timezone"] != "America/New_York"
        or operations["not_before_local"] != "18:00"
        or type(operations["minimum_close_delay_minutes"])
        is not int
        or operations["minimum_close_delay_minutes"] != 120
        or operations["live_provider_enabled"] is not False
        or operations["scheduled_execution_enabled"] is not False
        or operations["publication_enabled"] is not False
    ):
        raise ValueError(
            "US daily operations authorization rejected"
        )

    return PILOT_MANIFEST_PATH, PINNED_MANIFEST_SHA256


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

        # 1. Authorize the requested subset before any
        #    fetcher construction or market-data writes.
        manifest_path, expected_sha256 = (
            _load_pinned_operational_policy()
        )

        preflight = evaluate_daily_preflight(
            config_path=config_path,
            manifest_path=manifest_path,
            expected_manifest_sha256=expected_sha256,
            at=at,
        )

        unauthorized = [
            symbol
            for symbol in normalized
            if symbol not in preflight.symbols
        ]

        if unauthorized:
            raise ValueError(
                "Symbols outside the pinned US pilot manifest: "
                + ", ".join(unauthorized)
            )

        if preflight.decision != "READY":
            if preflight.decision not in {
                "SKIP_EARLY",
                "SKIP_NO_SESSION",
            }:
                raise ValueError(
                    f"Unknown preflight decision: "
                    f"{preflight.decision}"
                )

            return DailyIngestionOutcome(
                as_of=None,
                report_path=None,
                result=None,
                decision=preflight.decision,
                reason=preflight.reason,
            )

        # Keep the existing session clock, but reject a
        # disagreement with the independent operations gate.
        as_of = resolve_ingestion_session(
            at=at,
            settlement_delay_minutes=settlement_delay_minutes,
        )

        if preflight.as_of != as_of:
            raise ValueError(
                "Session Clock disagrees with operations preflight"
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
            decision='READY',
            reason=preflight.reason,
        )
