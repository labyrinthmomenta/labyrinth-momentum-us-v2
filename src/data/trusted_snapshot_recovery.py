"""Fail-closed trusted recovery for US SQLite pilot snapshots.

The caller must obtain the trusted snapshot ID, SHA-256,
required symbols, and minimum session from an independent
approved source. Snapshot metadata is never self-authorizing.
"""

from collections.abc import Sequence
from contextlib import closing
from datetime import date
import hashlib
import hmac
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from urllib.parse import quote

from src.data.sqlite_snapshot import (
    restore_sqlite_snapshot,
    verify_sqlite_snapshot,
)


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
ID_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}"
)
SYMBOL_PATTERN = re.compile(
    r"[A-Z][A-Z0-9.-]{0,14}"
)

MAX_PILOT_SYMBOLS = 25


def _validate_trusted_inputs(
    *,
    trusted_id: str,
    trusted_sha256: str,
    required_symbols: Sequence[str],
    min_last_session: date,
) -> tuple[str, ...]:
    """Validate independent recovery requirements."""
    if (
        not isinstance(trusted_id, str)
        or ID_PATTERN.fullmatch(trusted_id) is None
    ):
        raise ValueError("Invalid trusted snapshot ID")

    if (
        not isinstance(trusted_sha256, str)
        or SHA256_PATTERN.fullmatch(
            trusted_sha256
        ) is None
    ):
        raise ValueError(
            "Invalid trusted SHA-256; expected "
            "64 lowercase hexadecimal characters"
        )

    if type(min_last_session) is not date:
        raise ValueError(
            "min_last_session must be a date"
        )

    if (
        isinstance(required_symbols, (str, bytes))
        or not isinstance(required_symbols, Sequence)
        or not 1 <= len(required_symbols) <= MAX_PILOT_SYMBOLS
    ):
        raise ValueError(
            "required_symbols must contain "
            "1 to 25 symbols"
        )

    result = []
    seen = set()

    for symbol in required_symbols:
        if (
            not isinstance(symbol, str)
            or SYMBOL_PATTERN.fullmatch(symbol) is None
        ):
            raise ValueError(
                f"Invalid required symbol: {symbol!r}"
            )

        if symbol in seen:
            raise ValueError(
                f"Duplicate required symbol: {symbol}"
            )

        seen.add(symbol)
        result.append(symbol)

    return tuple(result)


def _read_only_uri(path: Path) -> str:
    return (
        "file:"
        + quote(str(path.resolve()), safe="/")
        + "?mode=ro"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _verify_required_state(
    database: Path,
    symbols: tuple[str, ...],
    min_last_session: date,
) -> None:
    """Validate successful statuses against stored price histories.

    Each required symbol must:
    - Have a SUCCESS download status
    - Have a valid, sufficiently recent last_session
    - Have at least one stored bar
    - Have its latest stored bar equal last_session

    This does not replace the existing 253-session data
    coverage validation performed during ingestion.
    """
    with closing(
        sqlite3.connect(
            _read_only_uri(database),
            uri=True,
        )
    ) as conn:
        for symbol in symbols:
            row = conn.execute(
                """
                SELECT status, last_session
                FROM download_status
                WHERE symbol = ?
                """,
                (symbol,),
            ).fetchone()

            if row is None:
                raise ValueError(
                    f"Missing download status: {symbol}"
                )

            status, last_session = row

            if status != "SUCCESS":
                raise ValueError(
                    f"Symbol has non-success status: "
                    f"{symbol}: {status}"
                )

            if not isinstance(last_session, str):
                raise ValueError(
                    f"Invalid last_session: {symbol}"
                )

            try:
                last_date = date.fromisoformat(
                    last_session
                )
            except ValueError as exc:
                raise ValueError(
                    f"Invalid session date for {symbol}"
                ) from exc

            if last_date.isoformat() != last_session:
                raise ValueError(
                    f"Noncanonical session date: {symbol}"
                )

            if last_date < min_last_session:
                raise ValueError(
                    f"Stale snapshot history: "
                    f"{symbol}: {last_session}"
                )

            latest_bar, count = conn.execute(
                """
                SELECT MAX(session_date), COUNT(*)
                FROM daily_bars
                WHERE symbol = ?
                """,
                (symbol,),
            ).fetchone()

            if count < 1 or latest_bar is None:
                raise ValueError(
                    f"Missing price history: {symbol}"
                )

            if latest_bar != last_session:
                raise ValueError(
                    f"Status/history date mismatch: "
                    f"{symbol}: "
                    f"{last_session} != {latest_bar}"
                )


def verify_trusted_snapshot(
    *,
    snapshot_dir: str | Path,
    trusted_id: str,
    trusted_sha256: str,
    required_symbols: Sequence[str],
    min_last_session: date,
) -> dict:
    """Verify snapshot integrity and independent recovery trust.

    Passing a SHA-256 value is not proof of authorization:
    the CALLER must obtain the expected digest independently,
    rather than reading it from the untrusted snapshot.
    """
    symbols = _validate_trusted_inputs(
        trusted_id=trusted_id,
        trusted_sha256=trusted_sha256,
        required_symbols=required_symbols,
        min_last_session=min_last_session,
    )

    snapshot = Path(snapshot_dir)

    # First verify the snapshot's own integrity and schema.
    manifest = verify_sqlite_snapshot(snapshot)

    # Then verify independent identity and byte-level trust.
    if manifest["snapshot_id"] != trusted_id:
        raise ValueError(
            "Trusted snapshot ID mismatch"
        )

    if not hmac.compare_digest(
        manifest["sha256"],
        trusted_sha256,
    ):
        raise ValueError(
            "Independent trusted SHA-256 mismatch"
        )

    database = snapshot / "market_data.db"

    # Check the bytes again before semantic inspection.
    if not hmac.compare_digest(
        _sha256(database),
        trusted_sha256,
    ):
        raise ValueError(
            "Trusted snapshot database checksum mismatch"
        )

    _verify_required_state(
        database,
        symbols,
        min_last_session,
    )

    # Catch any modification during semantic inspection.
    if not hmac.compare_digest(
        _sha256(database),
        trusted_sha256,
    ):
        raise ValueError(
            "Snapshot changed during verification"
        )

    return manifest


def _check_target_available(target: Path) -> None:
    if target.exists() or target.is_symlink():
        raise FileExistsError(
            f"Restore target already exists: {target}"
        )

    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(target) + suffix)

        if sidecar.exists() or sidecar.is_symlink():
            raise FileExistsError(
                f"Restore target sidecar exists: {sidecar}"
            )


def restore_trusted_snapshot(
    *,
    snapshot_dir: str | Path,
    trusted_id: str,
    trusted_sha256: str,
    required_symbols: Sequence[str],
    min_last_session: date,
    target_db: str | Path,
) -> Path:
    """Verify, stage, and exclusively publish a recovered SQLite DB.

    No existing target database is replaced.

    A restored copy is independently checked against the
    trusted SHA-256 before being exposed at the target path.
    """
    target = Path(target_db)

    _check_target_available(target)

    symbols = _validate_trusted_inputs(
        trusted_id=trusted_id,
        trusted_sha256=trusted_sha256,
        required_symbols=required_symbols,
        min_last_session=min_last_session,
    )

    verify_trusted_snapshot(
        snapshot_dir=snapshot_dir,
        trusted_id=trusted_id,
        trusted_sha256=trusted_sha256,
        required_symbols=symbols,
        min_last_session=min_last_session,
    )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Restore into a private temporary directory on the
    # target filesystem, not directly into the final path.
    with tempfile.TemporaryDirectory(
        prefix=f".{target.name}.trusted-",
        dir=target.parent,
    ) as temporary_dir:
        staged_db = (
            Path(temporary_dir) / "restored.db"
        )

        restore_sqlite_snapshot(
            snapshot_dir=snapshot_dir,
            target_db=staged_db,
        )

        if not hmac.compare_digest(
            _sha256(staged_db),
            trusted_sha256,
        ):
            raise ValueError(
                "Staged restore differs from trusted SHA-256"
            )

        _verify_required_state(
            staged_db,
            symbols,
            min_last_session,
        )

        if not hmac.compare_digest(
            _sha256(staged_db),
            trusted_sha256,
        ):
            raise ValueError(
                "Staged restore changed during validation"
            )

        _check_target_available(target)

        # Atomic exclusive publication on the same filesystem.
        # Fails if another process created the target.
        os.link(staged_db, target)

    return target
