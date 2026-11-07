"""Fail-closed operational readiness policy for US pilot ingestion."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import exchange_calendars as xcals


MARKET = "US"
TIMEZONE_NAME = "America/New_York"
NEW_YORK = ZoneInfo(TIMEZONE_NAME)

MAX_PILOT_SYMBOLS = 25
MIN_CLOSE_DELAY_MINUTES = 120
EARLIEST_LOCAL_TIME = time(18, 0)

SYMBOL_PATTERN = re.compile(r"[A-Z][A-Z0-9.-]{0,14}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class DailyPreflightResult:
    """Operational decision, with no ingestion side effects."""

    decision: str
    as_of: date | None
    symbols: tuple[str, ...]
    reason: str


def _unique_json_keys(pairs):
    """Reject ambiguous JSON objects with repeated keys."""
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(
                f"Duplicate JSON key: {key}"
            )
        result[key] = value

    return result


def _load_json_object(path: Path) -> dict:
    """Load a JSON object, rejecting ambiguous or malformed data."""
    if not path.is_file():
        raise FileNotFoundError(path)

    data = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_json_keys,
    )

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object: {path}"
        )

    return data


def _validate_bootstrap_config(path: Path) -> None:
    """Refuse any configuration enabling US production."""
    config = _load_json_object(path)

    if (
        config.get("market") != MARKET
        or config.get("timezone") != TIMEZONE_NAME
        or config.get("status") != "BOOTSTRAP_ONLY"
        or config.get("publication_enabled") is not False
        or config.get("vcp_production_enabled") is not False
    ):
        raise ValueError(
            "US operational safety configuration rejected"
        )


def _validate_pilot_manifest(
    path: Path,
    expected_sha256: str,
) -> tuple[str, ...]:
    """Verify independently pinned bytes and strict pilot schema."""
    if (
        not isinstance(expected_sha256, str)
        or SHA256_PATTERN.fullmatch(expected_sha256) is None
    ):
        raise ValueError(
            "Expected manifest SHA-256 must be "
            "64 lowercase hexadecimal characters"
        )

    if not path.is_file():
        raise FileNotFoundError(path)

    raw_bytes = path.read_bytes()
    actual_sha256 = hashlib.sha256(
        raw_bytes
    ).hexdigest()

    if not hmac.compare_digest(
        actual_sha256,
        expected_sha256,
    ):
        raise ValueError(
            "Pilot manifest SHA-256 mismatch"
        )

    # Parse exactly the bytes checked above, not a
    # second read of a potentially changed file.
    manifest = json.loads(
        raw_bytes.decode("utf-8"),
        object_pairs_hook=_unique_json_keys,
    )

    if not isinstance(manifest, dict):
        raise ValueError(
            "Pilot manifest must be a JSON object"
        )

    required_keys = {
        "market",
        "mode",
        "production_approved",
        "symbols",
    }

    if set(manifest) != required_keys:
        raise ValueError(
            "Unexpected pilot manifest schema"
        )

    if (
        manifest["market"] != MARKET
        or manifest["mode"] != "PILOT_ONLY"
        or manifest["production_approved"] is not False
    ):
        raise ValueError(
            "Pilot-only authorization rejected"
        )

    raw_symbols = manifest["symbols"]

    if (
        not isinstance(raw_symbols, list)
        or not 1 <= len(raw_symbols) <= MAX_PILOT_SYMBOLS
    ):
        raise ValueError(
            "Pilot manifest must contain 1 to 25 symbols"
        )

    symbols = []
    seen = set()

    for symbol in raw_symbols:
        if (
            not isinstance(symbol, str)
            or SYMBOL_PATTERN.fullmatch(symbol) is None
        ):
            raise ValueError(
                f"Invalid pilot ticker: {symbol!r}"
            )

        if symbol in seen:
            raise ValueError(
                f"Duplicate pilot ticker: {symbol}"
            )

        seen.add(symbol)
        symbols.append(symbol)

    return tuple(symbols)


def evaluate_daily_preflight(
    *,
    config_path: str | Path,
    manifest_path: str | Path,
    expected_manifest_sha256: str,
    at: datetime | None = None,
) -> DailyPreflightResult:
    """Evaluate whether a bounded US pilot may start today.

    No network calls, SQLite writes, or ingestion are performed.

    A READY decision requires:
    - Bootstrap-only configuration
    - An independently pinned and valid pilot manifest
    - A current NYSE trading session
    - Local New York time at or after 18:00
    - At least 120 minutes after actual exchange close

    Provider data publication is NOT guaranteed by READY.
    """
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

    # Fail closed before evaluating skip conditions.
    # Unsafe configuration must never be reported
    # as a harmless early/holiday skip.
    _validate_bootstrap_config(Path(config_path))

    symbols = _validate_pilot_manifest(
        Path(manifest_path),
        expected_manifest_sha256,
    )

    local_at = at.astimezone(NEW_YORK)
    local_date = local_at.date()

    calendar = xcals.get_calendar("XNYS")

    if not calendar.is_session(local_date):
        return DailyPreflightResult(
            decision="SKIP_NO_SESSION",
            as_of=None,
            symbols=symbols,
            reason=(
                f"{local_date.isoformat()} is not "
                "an XNYS trading session"
            ),
        )

    session = calendar.date_to_session(
        local_date,
        direction="none",
    )

    close_utc = calendar.session_close(
        session
    ).to_pydatetime()

    eligible_after_close = (
        close_utc
        + timedelta(minutes=MIN_CLOSE_DELAY_MINUTES)
    )

    local_window_open = datetime.combine(
        local_date,
        EARLIEST_LOCAL_TIME,
        tzinfo=NEW_YORK,
    )

    current_utc = at.astimezone(timezone.utc)

    if (
        local_at < local_window_open
        or current_utc < eligible_after_close
    ):
        return DailyPreflightResult(
            decision="SKIP_EARLY",
            as_of=None,
            symbols=symbols,
            reason=(
                "Waiting for 18:00 New York time "
                "and at least 120 minutes after "
                "the actual XNYS close"
            ),
        )

    return DailyPreflightResult(
        decision="READY",
        as_of=session.date(),
        symbols=symbols,
        reason=(
            "Bootstrap configuration, pinned pilot "
            "manifest, exchange session, and "
            "close-delay checks passed"
        ),
    )
