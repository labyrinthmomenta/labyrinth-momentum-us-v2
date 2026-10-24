"""Persistent download status for resumable US data ingestion."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
import sqlite3


VALID_STATUSES = {"IN_PROGRESS", "SUCCESS", "FAILED"}


@dataclass(frozen=True)
class DownloadStatus:
    symbol: str
    status: str
    last_attempt_utc: str | None
    last_success_utc: str | None
    last_session: str | None
    error_message: str | None
    error_category: str | None = None


def update_download_status(
    db_path: str | Path,
    symbol: str,
    status: str,
    *,
    last_session: date | None = None,
    error_message: str | None = None,
    error_category: str | None = None,
) -> None:
    """Update symbol status while preserving prior successful metadata."""
    symbol = symbol.strip().upper()

    if not symbol:
        raise ValueError("Symbol cannot be empty")

    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid download status: {status}")

    if status == "SUCCESS" and last_session is None:
        raise ValueError("SUCCESS requires last_session")

    if status != "SUCCESS" and last_session is not None:
        raise ValueError("Only SUCCESS may set last_session")

    if status == "SUCCESS" and error_message is not None:
        raise ValueError("SUCCESS cannot have error_message")

    if status != "FAILED" and error_category is not None:
        raise ValueError(
            "error_category is only allowed for FAILED status"
        )

    from src.data.storage.migrations import (
        ensure_error_category_column,
    )

    ensure_error_category_column(db_path)

    now = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO download_status (
                symbol,
                last_attempt_utc,
                last_success_utc,
                last_session,
                status,
                error_message,
                error_category
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                last_attempt_utc = excluded.last_attempt_utc,
                last_success_utc = CASE
                    WHEN excluded.status = 'SUCCESS'
                    THEN excluded.last_success_utc
                    ELSE download_status.last_success_utc
                END,
                last_session = CASE
                    WHEN excluded.status = 'SUCCESS'
                    THEN excluded.last_session
                    ELSE download_status.last_session
                END,
                status = excluded.status,
                error_message = excluded.error_message,
                error_category = excluded.error_category
            """,
            (
                symbol,
                now,
                now if status == "SUCCESS" else None,
                last_session.isoformat() if last_session else None,
                status,
                error_message,
                error_category,
            ),
        )


def get_download_status(
    db_path: str | Path,
    symbol: str,
) -> DownloadStatus | None:
    """Read the latest status for one symbol."""
    from src.data.storage.migrations import (
        ensure_error_category_column,
    )

    ensure_error_category_column(db_path)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                symbol,
                status,
                last_attempt_utc,
                last_success_utc,
                last_session,
                error_message,
                error_category
            FROM download_status
            WHERE symbol = ?
            """,
            (symbol.strip().upper(),),
        ).fetchone()

    return DownloadStatus(*row) if row else None
