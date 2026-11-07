"""A6c.22 trusted snapshot recovery security contracts."""

import hashlib
import json
import sqlite3
from datetime import date

import pytest

from src.data.sqlite_snapshot import (
    create_sqlite_snapshot,
    verify_sqlite_snapshot,
)
from src.data.trusted_snapshot_recovery import (
    verify_trusted_snapshot,
    restore_trusted_snapshot,
)


SNAPSHOT_ID = "us_pilot_2026-11-02_v1"
REQUIRED = ("GOOGL", "NIO")
MIN_SESSION = date(2026, 11, 2)


@pytest.fixture
def recovery_case(tmp_path):
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
            (symbol, session_date, close, volume)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("GOOGL", "2026-10-30", 100.0, 1000000),
                ("GOOGL", "2026-11-02", 101.0, 1100000),
                ("NIO", "2026-11-02", 5.5, 2000000),
            ],
        )

        conn.executemany(
            """
            INSERT INTO download_status
            (symbol, status, last_session)
            VALUES (?, ?, ?)
            """,
            [
                ("GOOGL", "SUCCESS", "2026-11-02"),
                ("NIO", "SUCCESS", "2026-11-02"),
            ],
        )

        conn.commit()

    root = tmp_path / "snapshots"

    snapshot = create_sqlite_snapshot(
        source_db=db,
        snapshot_root=root,
        snapshot_id=SNAPSHOT_ID,
    )

    manifest = verify_sqlite_snapshot(snapshot)

    return {
        "snapshot_dir": snapshot,
        "trusted_id": SNAPSHOT_ID,
        "trusted_sha256": manifest["sha256"],
        "required_symbols": REQUIRED,
        "min_last_session": MIN_SESSION,
    }


def verify(case, **overrides):
    arguments = dict(case)
    arguments.update(overrides)
    return verify_trusted_snapshot(**arguments)


def test_independently_pinned_snapshot_is_accepted(
    recovery_case,
):
    manifest = verify(recovery_case)

    assert manifest["snapshot_id"] == SNAPSHOT_ID
    assert manifest["sha256"] == (
        recovery_case["trusted_sha256"]
    )
    assert manifest["tables"]["daily_bars"] == 3


def test_wrong_independent_sha256_is_rejected(
    recovery_case,
):
    # Internal manifest remains valid, but trusted pin differs.
    assert verify_sqlite_snapshot(
        recovery_case["snapshot_dir"]
    )

    with pytest.raises(ValueError):
        verify(
            recovery_case,
            trusted_sha256="0" * 64,
        )


def test_resealed_tampered_snapshot_is_rejected(
    recovery_case,
):
    snapshot = recovery_case["snapshot_dir"]
    db = snapshot / "market_data.db"
    manifest_path = snapshot / "manifest.json"

    # Simulate someone modifying the snapshot AND
    # updating its internal manifest to match.
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            UPDATE daily_bars
            SET close = 999.0
            WHERE symbol = 'GOOGL'
              AND session_date = '2026-11-02'
            """
        )
        conn.commit()

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    manifest["sha256"] = hashlib.sha256(
        db.read_bytes()
    ).hexdigest()

    manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    # Self-reported SHA-256 is now consistent.
    assert verify_sqlite_snapshot(snapshot)

    # The independent trusted SHA-256 must still block it.
    with pytest.raises(ValueError):
        verify(recovery_case)


def test_wrong_snapshot_id_is_rejected(
    recovery_case,
):
    with pytest.raises(ValueError):
        verify(
            recovery_case,
            trusted_id="unapproved_snapshot",
        )


def test_older_snapshot_cannot_be_restored(
    recovery_case,
):
    with pytest.raises(ValueError):
        verify(
            recovery_case,
            min_last_session=date(2026, 11, 3),
        )


def test_missing_expected_symbol_is_rejected(
    recovery_case,
):
    # Still within the authorized 25-symbol limit.
    # Failure must be due to missing stored symbol state.
    with pytest.raises(
        ValueError,
        match="Missing download status: AMZN",
    ):
        verify(
            recovery_case,
            required_symbols=("GOOGL", "NIO", "AMZN"),
        )


def test_non_success_status_is_rejected(
    recovery_case, tmp_path,
):
    # Construct another valid, independently pinned
    # snapshot whose status records are incomplete.
    db = tmp_path / "failed_source.db"

    with sqlite3.connect(
        recovery_case["snapshot_dir"] / "market_data.db"
    ) as source:
        with sqlite3.connect(db) as target:
            source.backup(target)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            UPDATE download_status
            SET status = 'FAILED'
            WHERE symbol = 'NIO'
            """
        )
        conn.commit()

    failed = create_sqlite_snapshot(
        source_db=db,
        snapshot_root=tmp_path / "failed_snapshots",
        snapshot_id="failed_snapshot",
    )

    failed_manifest = verify_sqlite_snapshot(failed)

    with pytest.raises(ValueError):
        verify_trusted_snapshot(
            snapshot_dir=failed,
            trusted_id="failed_snapshot",
            trusted_sha256=failed_manifest["sha256"],
            required_symbols=REQUIRED,
            min_last_session=MIN_SESSION,
        )


def test_restore_is_verified_and_non_overwriting(
    recovery_case, tmp_path,
):
    target = tmp_path / "restored.db"

    result = restore_trusted_snapshot(
        **recovery_case,
        target_db=target,
    )

    assert result == target
    assert target.is_file()

    with sqlite3.connect(target) as conn:
        assert conn.execute(
            "PRAGMA integrity_check"
        ).fetchone() == ("ok",)

        assert conn.execute(
            "SELECT COUNT(*) FROM daily_bars"
        ).fetchone()[0] == 3

    before = hashlib.sha256(
        target.read_bytes()
    ).hexdigest()

    with pytest.raises(FileExistsError):
        restore_trusted_snapshot(
            **recovery_case,
            target_db=target,
        )

    assert hashlib.sha256(
        target.read_bytes()
    ).hexdigest() == before
