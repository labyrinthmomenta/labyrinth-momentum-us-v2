"""A6c.23: immutable and independently trusted checkpoints."""

from datetime import date
import hashlib
import json
import sqlite3

import pytest

from src.data.sqlite_snapshot import create_sqlite_snapshot
from src.data.snapshot_checkpoint import (
    write_snapshot_checkpoint,
    verify_snapshot_checkpoint,
)


AS_OF = date(2026, 11, 2)
SYMBOLS = ("GOOGL", "NIO")
PILOT_SHA256 = "1" * 64


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def bundle(tmp_path):
    db = tmp_path / "source.db"

    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE daily_bars (
                symbol TEXT NOT NULL,
                session_date TEXT NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                PRIMARY KEY(symbol, session_date)
            );

            CREATE TABLE download_status (
                symbol TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                last_session TEXT
            );
        """)

        conn.executemany(
            """
            INSERT INTO daily_bars
            VALUES (?, ?, ?, ?)
            """,
            [
                ("GOOGL", "2026-11-02", 101.0, 1000000),
                ("NIO", "2026-11-02", 5.5, 2000000),
            ],
        )

        conn.executemany(
            """
            INSERT INTO download_status
            VALUES (?, ?, ?)
            """,
            [
                ("GOOGL", "SUCCESS", "2026-11-02"),
                ("NIO", "SUCCESS", "2026-11-02"),
            ],
        )

        conn.commit()

    snapshot = create_sqlite_snapshot(
        source_db=db,
        snapshot_root=tmp_path / "snapshots",
        snapshot_id="us_pilot_2026-11-02_v1",
    )

    return {
        "snapshot_dir": snapshot,
        "checkpoint_path": tmp_path / "checkpoint.json",
    }


def write(bundle, **overrides):
    args = {
        **bundle,
        "as_of": AS_OF,
        "pilot_manifest_sha256": PILOT_SHA256,
        "required_symbols": SYMBOLS,
        "previous_checkpoint_sha256": None,
    }
    args.update(overrides)
    return write_snapshot_checkpoint(**args)


def verify(bundle, checkpoint, **overrides):
    args = {
        "checkpoint_path": checkpoint,
        "snapshot_dir": bundle["snapshot_dir"],
        "trusted_checkpoint_sha256": sha256(checkpoint),
        "expected_pilot_manifest_sha256": PILOT_SHA256,
        "required_symbols": SYMBOLS,
        "min_as_of": AS_OF,
        "expected_previous_checkpoint_sha256": None,
    }
    args.update(overrides)
    return verify_snapshot_checkpoint(**args)


def test_valid_independently_pinned_checkpoint(bundle):
    checkpoint = write(bundle)
    result = verify(bundle, checkpoint)

    assert result["schema_version"] == 1
    assert result["market"] == "US"
    assert result["mode"] == "PILOT_ONLY"
    assert result["production_approved"] is False
    assert result["as_of"] == "2026-11-02"
    assert result["pilot_manifest_sha256"] == PILOT_SHA256
    assert result["previous_checkpoint_sha256"] is None
    assert result["snapshot_id"] == (
        "us_pilot_2026-11-02_v1"
    )
    assert len(result["snapshot_sha256"]) == 64


def test_checkpoint_cannot_be_overwritten(bundle):
    checkpoint = write(bundle)
    original = checkpoint.read_bytes()

    with pytest.raises(FileExistsError):
        write(bundle)

    assert checkpoint.read_bytes() == original


def test_modified_checkpoint_fails_external_pin(bundle):
    checkpoint = write(bundle)
    trusted_head = sha256(checkpoint)

    content = json.loads(checkpoint.read_text())
    content["as_of"] = "2026-11-03"
    checkpoint.write_text(json.dumps(content))

    with pytest.raises(ValueError):
        verify(
            bundle,
            checkpoint,
            trusted_checkpoint_sha256=trusted_head,
        )


def test_wrong_external_head_is_rejected(bundle):
    checkpoint = write(bundle)

    with pytest.raises(ValueError):
        verify(
            bundle,
            checkpoint,
            trusted_checkpoint_sha256="0" * 64,
        )


def test_checkpoint_cannot_authorize_wrong_snapshot(bundle):
    checkpoint = write(bundle)
    content = json.loads(checkpoint.read_text())
    content["snapshot_sha256"] = "2" * 64
    checkpoint.write_text(json.dumps(content))

    # Even if a caller accepts the edited checkpoint hash,
    # its snapshot reference must still be verified.
    with pytest.raises(ValueError):
        verify(bundle, checkpoint)


def test_older_checkpoint_is_rejected(bundle):
    checkpoint = write(bundle)

    with pytest.raises(ValueError):
        verify(
            bundle,
            checkpoint,
            min_as_of=date(2026, 11, 3),
        )


def test_previous_checkpoint_link_is_verified(bundle):
    previous_head = "b" * 64

    checkpoint = write(
        bundle,
        previous_checkpoint_sha256=previous_head,
    )

    result = verify(
        bundle,
        checkpoint,
        expected_previous_checkpoint_sha256=previous_head,
    )

    assert result["previous_checkpoint_sha256"] == previous_head

    with pytest.raises(ValueError):
        verify(
            bundle,
            checkpoint,
            expected_previous_checkpoint_sha256="c" * 64,
        )


def test_missing_required_symbol_is_rejected(bundle):
    checkpoint = write(bundle)

    with pytest.raises(ValueError):
        verify(
            bundle,
            checkpoint,
            required_symbols=("GOOGL", "NIO", "AMZN"),
        )


def test_production_mode_is_rejected_even_if_rehashed(bundle):
    checkpoint = write(bundle)

    content = json.loads(checkpoint.read_text())
    content["mode"] = "PRODUCTION"
    checkpoint.write_text(json.dumps(content))

    with pytest.raises(ValueError):
        verify(bundle, checkpoint)
