"""Atomic persistence of validated US daily bars and success status."""

from collections.abc import Sequence
from datetime import date, datetime, timezone
from pathlib import Path
import math
import sqlite3

from src.calculation.engine import DataQualityError, PriceBar


def persist_validated_history(
    db_path: str | Path,
    symbol: str,
    bars: Sequence[PriceBar],
    *,
    as_of: date,
) -> int:
    """Replace complete history and mark success in one transaction.

    The caller must validate the required exchange-calendar coverage
    before calling this function. Existing stored dates cannot be lost.
    """
    symbol = symbol.strip().upper()

    if not symbol:
        raise ValueError("Symbol cannot be empty")
    if not bars:
        raise DataQualityError("Cannot persist empty history")
    if not isinstance(as_of, date):
        raise ValueError("as_of must be a date")

    records = []
    previous = None

    for bar in bars:
        if previous is not None and bar.date <= previous:
            raise DataQualityError("Bars must have strictly increasing dates")
        previous = bar.date

        prices = (bar.open, bar.high, bar.low, bar.close)
        if not all(math.isfinite(v) and v > 0 for v in prices):
            raise DataQualityError(f"Invalid price on {bar.date}")

        if (
            bar.high < bar.low
            or bar.high < max(bar.open, bar.close)
            or bar.low > min(bar.open, bar.close)
        ):
            raise DataQualityError(f"Inconsistent OHLC on {bar.date}")

        if (
            bar.volume is None
            or not math.isfinite(bar.volume)
            or bar.volume < 0
        ):
            raise DataQualityError(f"Invalid volume on {bar.date}")

        records.append((
            symbol,
            bar.date.isoformat(),
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume,
        ))

    if bars[-1].date != as_of:
        raise DataQualityError("History must end at as_of")

    now = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")

        existing = {
            row[0]
            for row in conn.execute(
                "SELECT session_date FROM daily_bars WHERE symbol = ?",
                (symbol,),
            )
        }

        incoming = {record[1] for record in records}
        missing = existing - incoming

        if missing:
            raise DataQualityError(
                f"Replacement would remove {len(missing)} "
                f"existing sessions; first missing: {min(missing)}"
            )

        conn.execute(
            "DELETE FROM daily_bars WHERE symbol = ?",
            (symbol,),
        )

        conn.executemany(
            """
            INSERT INTO daily_bars (
                symbol, session_date, open, high, low, close, volume
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )

        conn.execute(
            """
            INSERT INTO download_status (
                symbol, last_attempt_utc, last_success_utc,
                last_session, status, error_message
            )
            VALUES (?, ?, ?, ?, 'SUCCESS', NULL)
            ON CONFLICT(symbol) DO UPDATE SET
                last_attempt_utc = excluded.last_attempt_utc,
                last_success_utc = excluded.last_success_utc,
                last_session = excluded.last_session,
                status = 'SUCCESS',
                error_message = NULL
            """,
            (symbol, now, now, as_of.isoformat()),
        )

        conn.commit()

    return len(records)


def persist_complete_history(
    db_path: str | Path,
    symbol: str,
    bars: Sequence[PriceBar],
    *,
    as_of: date,
    required_sessions: int = 253,
) -> int:
    """Validate complete US trading sessions before atomic persistence."""
    from src.data.providers.sessions import validate_recent_sessions

    if required_sessions < 253:
        raise ValueError(
            "US momentum ingestion requires at least 253 sessions"
        )

    validate_recent_sessions(
        bars,
        as_of=as_of,
        required_sessions=required_sessions,
    )

    eligible = [bar for bar in bars if bar.date <= as_of]

    return persist_validated_history(
        db_path,
        symbol,
        eligible,
        as_of=as_of,
    )
