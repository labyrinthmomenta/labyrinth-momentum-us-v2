"""Independently pinned, immutable US pilot checkpoints."""

from collections.abc import Sequence
from contextlib import closing
from datetime import date
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from urllib.parse import quote

from src.data.sqlite_snapshot import verify_sqlite_snapshot
from src.data.trusted_snapshot_recovery import (
    verify_trusted_snapshot,
)


SHA_PATTERN = re.compile(r"[0-9a-f]{64}")
SYMBOL_PATTERN = re.compile(r"[A-Z][A-Z0-9.-]{0,14}")

REQUIRED_FIELDS = {
    "schema_version",
    "market",
    "mode",
    "production_approved",
    "as_of",
    "pilot_manifest_sha256",
    "required_symbols",
    "previous_checkpoint_sha256",
    "snapshot_id",
    "snapshot_sha256",
}


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024), b""
        ):
            digest.update(chunk)
    return digest.hexdigest()


def _check_sha(value, label):
    if (
        not isinstance(value, str)
        or SHA_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(f"Invalid {label}")
    return value


def _check_date(value, label):
    if type(value) is not date:
        raise ValueError(f"{label} must be a date")
    return value


def _check_symbols(symbols):
    if (
        isinstance(symbols, (str, bytes))
        or not isinstance(symbols, Sequence)
        or not 1 <= len(symbols) <= 25
    ):
        raise ValueError(
            "Required symbols must contain 1 to 25 entries"
        )

    result = []
    for symbol in symbols:
        if (
            not isinstance(symbol, str)
            or SYMBOL_PATTERN.fullmatch(symbol) is None
            or symbol in result
        ):
            raise ValueError(
                f"Invalid or duplicate symbol: {symbol!r}"
            )
        result.append(symbol)

    return tuple(result)


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate checkpoint key: {key}")
        result[key] = value
    return result


def _verify_snapshot_state(
    snapshot_dir,
    snapshot_id,
    snapshot_sha256,
    symbols,
    as_of,
):
    snapshot = Path(snapshot_dir)

    verify_trusted_snapshot(
        snapshot_dir=snapshot,
        trusted_id=snapshot_id,
        trusted_sha256=snapshot_sha256,
        required_symbols=symbols,
        min_last_session=as_of,
    )

    db = snapshot / "market_data.db"
    uri = (
        "file:"
        + quote(str(db.resolve()), safe="/")
        + "?mode=ro"
    )

    with closing(sqlite3.connect(uri, uri=True)) as conn:
        statuses = conn.execute(
            """
            SELECT symbol, status, last_session
            FROM download_status
            """
        ).fetchall()

        histories = conn.execute(
            """
            SELECT symbol, MAX(session_date)
            FROM daily_bars
            GROUP BY symbol
            """
        ).fetchall()

    expected = set(symbols)
    actual_status = {row[0] for row in statuses}
    actual_history = {row[0] for row in histories}

    if (
        len(statuses) != len(symbols)
        or actual_status != expected
        or actual_history != expected
    ):
        raise ValueError(
            "Snapshot symbol coverage mismatch"
        )

    target_date = as_of.isoformat()

    for symbol, status, last_session in statuses:
        if status != "SUCCESS" or last_session != target_date:
            raise ValueError(
                f"Incomplete checkpoint status: {symbol}"
            )

    for symbol, last_bar in histories:
        if last_bar != target_date:
            raise ValueError(
                f"Checkpoint history date mismatch: {symbol}"
            )

    if not hmac.compare_digest(
        _sha256_file(db),
        snapshot_sha256,
    ):
        raise ValueError(
            "Snapshot changed during verification"
        )


def write_snapshot_checkpoint(
    *,
    snapshot_dir,
    checkpoint_path,
    as_of,
    pilot_manifest_sha256,
    required_symbols,
    previous_checkpoint_sha256=None,
):
    """Create a checkpoint without replacing any existing file."""
    _check_date(as_of, "as_of")
    _check_sha(
        pilot_manifest_sha256,
        "pilot manifest SHA-256",
    )
    symbols = _check_symbols(required_symbols)

    if previous_checkpoint_sha256 is not None:
        _check_sha(
            previous_checkpoint_sha256,
            "previous checkpoint SHA-256",
        )

    target = Path(checkpoint_path)

    if target.exists() or target.is_symlink():
        raise FileExistsError(target)

    manifest = verify_sqlite_snapshot(snapshot_dir)

    _verify_snapshot_state(
        snapshot_dir,
        manifest["snapshot_id"],
        manifest["sha256"],
        symbols,
        as_of,
    )

    checkpoint = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "as_of": as_of.isoformat(),
        "pilot_manifest_sha256": pilot_manifest_sha256,
        "required_symbols": list(symbols),
        "previous_checkpoint_sha256": (
            previous_checkpoint_sha256
        ),
        "snapshot_id": manifest["snapshot_id"],
        "snapshot_sha256": manifest["sha256"],
    }

    content = (
        json.dumps(
            checkpoint, indent=2, sort_keys=True
        ) + "\n"
    ).encode("utf-8")

    target.parent.mkdir(parents=True, exist_ok=True)

    fd, name = tempfile.mkstemp(
        prefix=f".{target.name}.staging-",
        dir=target.parent,
    )
    staged = Path(name)

    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

        os.link(staged, target)
    finally:
        staged.unlink(missing_ok=True)

    return target


def verify_snapshot_checkpoint(
    *,
    checkpoint_path,
    snapshot_dir,
    trusted_checkpoint_sha256,
    expected_pilot_manifest_sha256,
    required_symbols,
    min_as_of,
    expected_previous_checkpoint_sha256,
):
    """Check externally pinned checkpoint and referenced snapshot."""
    _check_sha(
        trusted_checkpoint_sha256,
        "trusted checkpoint SHA-256",
    )
    _check_sha(
        expected_pilot_manifest_sha256,
        "pilot manifest SHA-256",
    )
    _check_date(min_as_of, "min_as_of")
    symbols = _check_symbols(required_symbols)

    if expected_previous_checkpoint_sha256 is not None:
        _check_sha(
            expected_previous_checkpoint_sha256,
            "previous checkpoint SHA-256",
        )

    path = Path(checkpoint_path)

    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(path)

    raw = path.read_bytes()

    if len(raw) > 32768:
        raise ValueError("Checkpoint too large")

    actual_sha = hashlib.sha256(raw).hexdigest()

    if not hmac.compare_digest(
        actual_sha, trusted_checkpoint_sha256
    ):
        raise ValueError(
            "Independent checkpoint SHA-256 mismatch"
        )

    checkpoint = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_keys,
    )

    if (
        not isinstance(checkpoint, dict)
        or set(checkpoint) != REQUIRED_FIELDS
    ):
        raise ValueError("Invalid checkpoint schema")

    if (
        type(checkpoint["schema_version"]) is not int
        or checkpoint["schema_version"] != 1
        or checkpoint["market"] != "US"
        or checkpoint["mode"] != "PILOT_ONLY"
        or checkpoint["production_approved"] is not False
    ):
        raise ValueError("Checkpoint safety gate rejected")

    raw_date = checkpoint["as_of"]

    if not isinstance(raw_date, str):
        raise ValueError("Invalid checkpoint date")

    try:
        as_of = date.fromisoformat(raw_date)
    except ValueError as exc:
        raise ValueError(
            "Invalid checkpoint date"
        ) from exc

    if (
        as_of.isoformat() != raw_date
        or as_of < min_as_of
    ):
        raise ValueError(
            "Checkpoint is stale or has an invalid date"
        )

    if checkpoint["required_symbols"] != list(symbols):
        raise ValueError(
            "Checkpoint required symbols mismatch"
        )

    if (
        checkpoint["pilot_manifest_sha256"]
        != expected_pilot_manifest_sha256
    ):
        raise ValueError(
            "Pilot manifest SHA-256 mismatch"
        )

    previous = checkpoint["previous_checkpoint_sha256"]

    if previous is not None:
        _check_sha(
            previous,
            "checkpoint predecessor SHA-256",
        )

    if previous != expected_previous_checkpoint_sha256:
        raise ValueError(
            "Checkpoint predecessor mismatch"
        )

    snapshot_sha = _check_sha(
        checkpoint["snapshot_sha256"],
        "snapshot SHA-256",
    )

    _verify_snapshot_state(
        snapshot_dir,
        checkpoint["snapshot_id"],
        snapshot_sha,
        symbols,
        as_of,
    )

    if not hmac.compare_digest(
        _sha256_file(path),
        trusted_checkpoint_sha256,
    ):
        raise ValueError(
            "Checkpoint changed during verification"
        )

    return checkpoint
