"""Durable JSON audit reports for US daily ingestion runs."""

from collections.abc import Sequence
from datetime import date, datetime, timezone
from pathlib import Path
import json
import os
import tempfile

from src.data.daily_batch_orchestrator import DailyBatchResult


SCHEMA_VERSION = 1


def _validate_result(result: DailyBatchResult) -> None:
    """Reject inconsistent daily run accounting."""
    if not isinstance(result, DailyBatchResult):
        raise ValueError("Expected DailyBatchResult")

    if result.requested < 0:
        raise ValueError("Requested count cannot be negative")

    attempted = len(result.results)
    unprocessed = len(result.unprocessed_symbols)

    if attempted + unprocessed != result.requested:
        raise ValueError(
            "Daily result accounting mismatch: "
            "attempted + unprocessed != requested"
        )

    if result.stopped_early != bool(unprocessed):
        raise ValueError(
            "Stopped-early flag does not match "
            "unprocessed symbols"
        )

    if result.stopped_early and not result.unprocessed_symbols:
        raise ValueError(
            "Interrupted run must identify remaining symbols"
        )

    seen = set()

    for item in result.results:
        if item.status not in {
            "SUCCESS", "SKIPPED", "FAILED"
        }:
            raise ValueError(
                f"Invalid ingestion status: {item.status}"
            )

        if item.symbol in seen:
            raise ValueError(
                f"Duplicate attempted symbol: {item.symbol}"
            )

        seen.add(item.symbol)

    for symbol in result.unprocessed_symbols:
        if symbol in seen:
            raise ValueError(
                f"Symbol both attempted and unprocessed: {symbol}"
            )

        seen.add(symbol)

    if len(seen) != result.requested:
        raise ValueError(
            "Daily symbol accounting is inconsistent"
        )

    # Check individual batch accounting as well.
    for batch in result.batch_results:
        if (
            len(batch.results)
            + len(batch.unprocessed_symbols)
            != batch.requested
        ):
            raise ValueError(
                "Individual batch accounting mismatch"
            )


def _serialize_result(result: DailyBatchResult) -> list[dict]:
    """Convert ingestion outcomes into JSON-safe records."""
    return [
        {
            "symbol": item.symbol,
            "status": item.status,
            "eligibility": item.eligibility,
            "rows": item.rows,
            "reason": item.reason,
            "error_category": item.error_category,
            "retryable": item.retryable,
        }
        for item in result.results
    ]


def write_daily_run_report(
    result: DailyBatchResult,
    *,
    as_of: date,
    report_path: str | Path,
    generated_at: datetime | None = None,
) -> Path:
    """Atomically create a daily audit report without overwrite.

    The report uses a temporary file in the destination
    directory and installs it using an exclusive hard link.

    Existing reports are never replaced.
    No market-data database writes or network calls occur.
    """
    if (
        not isinstance(as_of, date)
        or isinstance(as_of, datetime)
    ):
        raise ValueError("as_of must be a date")

    if generated_at is None:
        generated_at = datetime.now(timezone.utc)

    if (
        not isinstance(generated_at, datetime)
        or generated_at.tzinfo is None
        or generated_at.utcoffset() is None
    ):
        raise ValueError(
            "generated_at must be timezone-aware"
        )

    _validate_result(result)

    path = Path(report_path)

    if not path.name:
        raise ValueError("Invalid report path")

    counts = result.counts

    if result.stopped_early:
        run_status = "INTERRUPTED"
    elif counts["FAILED"] > 0:
        run_status = "COMPLETED_WITH_ERRORS"
    else:
        run_status = "COMPLETED"

    report = {
        "schema_version": SCHEMA_VERSION,
        "market": "US",
        "as_of": as_of.isoformat(),
        "generated_at_utc": generated_at.astimezone(
            timezone.utc
        ).isoformat(),
        "run_status": run_status,
        "summary": {
            "requested": result.requested,
            "attempted": len(result.results),
            "unprocessed": len(
                result.unprocessed_symbols
            ),
            "batch_count": len(result.batch_results),
            "counts": counts,
            "eligibility_counts_new_successes": (
                result.eligibility_counts
            ),
            "error_categories": result.error_categories,
        },
        "unprocessed_symbols": list(
            result.unprocessed_symbols
        ),
        "results": _serialize_result(result),
    }

    content = (
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Create a private temporary file in the same directory.
    # The final path is installed atomically without replacing
    # an existing report, including under concurrent writers.
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

        # os.link fails with FileExistsError if the final
        # report path already exists. Unlike os.replace,
        # it never silently overwrites the destination.
        os.link(temporary_name, path)

    finally:
        # Remove only the temporary name. A successful link
        # leaves the completed report at its final path.
        Path(temporary_name).unlink(
            missing_ok=True
        )

    return path


def write_aborted_run_report(
    *,
    as_of: date,
    report_path: str | Path,
    symbols: Sequence[str],
    error: Exception,
    phase: str,
    generated_at: datetime | None = None,
) -> Path:
    """Atomically record a failed run with unknown progress.

    This function deliberately does not infer the number of
    successful, failed, or unprocessed symbols from an exception.

    Existing reports are never overwritten.
    """
    if (
        not isinstance(as_of, date)
        or isinstance(as_of, datetime)
    ):
        raise ValueError("as_of must be a date")

    if generated_at is None:
        generated_at = datetime.now(timezone.utc)

    if (
        not isinstance(generated_at, datetime)
        or generated_at.tzinfo is None
        or generated_at.utcoffset() is None
    ):
        raise ValueError(
            "generated_at must be timezone-aware"
        )

    if not isinstance(error, Exception):
        raise ValueError("error must be an Exception")

    if not isinstance(phase, str) or not phase.strip():
        raise ValueError("phase must be a non-empty string")

    if isinstance(symbols, (str, bytes)):
        raise ValueError("symbols must be a sequence")

    normalized = []
    seen = set()

    for raw in symbols:
        if not isinstance(raw, str):
            raise ValueError("Symbols must be strings")

        symbol = raw.strip().upper()

        if not symbol or symbol in seen:
            raise ValueError(
                "Blank or duplicate symbol in aborted run"
            )

        seen.add(symbol)
        normalized.append(symbol)

    if not normalized:
        raise ValueError(
            "Aborted run must identify requested symbols"
        )

    path = Path(report_path)

    if not path.name:
        raise ValueError("Invalid report path")

    report = {
        "schema_version": SCHEMA_VERSION,
        "market": "US",
        "as_of": as_of.isoformat(),
        "generated_at_utc": generated_at.astimezone(
            timezone.utc
        ).isoformat(),
        "run_status": "ABORTED",
        "phase": phase,
        "requested_symbols": normalized,
        "summary": {
            "requested": len(normalized),
            "attempted": None,
            "unprocessed": None,
            "counts": None,
            "eligibility_counts_new_successes": None,
            "error_categories": None,
        },
        "results": None,
        "unprocessed_symbols": None,
        "error": {
            "type": type(error).__name__,
            "message": str(error),
        },
    }

    content = (
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    )

    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

        # Exclusive creation: an existing report wins.
        # Never use os.replace for audit reports.
        os.link(temporary_name, path)

    finally:
        Path(temporary_name).unlink(
            missing_ok=True
        )

    return path
