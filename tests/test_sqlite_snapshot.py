"""A6c.22: offline SQLite snapshot and restore contracts."""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from src.data.daily_run_lock import (
    DailyRunAlreadyActiveError,
    hold_daily_ingestion_lock,
)

from src.data.sqlite_snapshot import (
    create_sqlite_snapshot,
    verify_sqlite_snapshot,
    restore_sqlite_snapshot,
)


SNAPSHOT_ID = "us_pilot_2026-11-02_v1"


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "pilot.db"

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")

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

    return path


def rows(db):
    with sqlite3.connect(
        f"file:{Path(db).resolve()}?mode=ro",
        uri=True,
    ) as conn:
        bars = conn.execute(
            """
            SELECT symbol, session_date, close, volume
            FROM daily_bars
            ORDER BY symbol, session_date
            """
        ).fetchall()

        statuses = conn.execute(
            """
            SELECT symbol, status, last_session
            FROM download_status
            ORDER BY symbol
            """
        ).fetchall()

        integrity = conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

    return bars, statuses, integrity


def create(database, tmp_path):
    return create_sqlite_snapshot(
        source_db=database,
        snapshot_root=tmp_path / "snapshots",
        snapshot_id=SNAPSHOT_ID,
    )


def test_snapshot_preserves_complete_sqlite_state(
    database, tmp_path
):
    snapshot = create(database, tmp_path)

    assert snapshot.is_dir()

    db_copy = snapshot / "market_data.db"
    manifest_file = snapshot / "manifest.json"

    assert db_copy.is_file()
    assert manifest_file.is_file()

    manifest = json.loads(
        manifest_file.read_text(encoding="utf-8")
    )

    assert manifest["schema_version"] == 1
    assert manifest["market"] == "US"
    assert manifest["snapshot_id"] == SNAPSHOT_ID
    assert manifest["database_file"] == "market_data.db"

    actual_digest = hashlib.sha256(
        db_copy.read_bytes()
    ).hexdigest()

    assert manifest["sha256"] == actual_digest
    assert manifest["database_bytes"] == db_copy.stat().st_size

    assert manifest["tables"]["daily_bars"] == 3
    assert manifest["tables"]["download_status"] == 2

    assert rows(db_copy) == rows(database)

    # Reading a standalone snapshot must not create
    # WAL, shared-memory, or journal sidecar files.
    assert not any(
        Path(str(db_copy) + suffix).exists()
        for suffix in ("-wal", "-shm", "-journal")
    )

    with sqlite3.connect(
        f"file:{db_copy.resolve()}?mode=ro",
        uri=True,
    ) as conn:
        assert conn.execute(
            "PRAGMA journal_mode"
        ).fetchone() == ("delete",)

    verified = verify_sqlite_snapshot(snapshot)
    assert verified["sha256"] == actual_digest


def test_existing_snapshot_cannot_be_overwritten(
    database, tmp_path
):
    snapshot = create(database, tmp_path)
    before = (snapshot / "market_data.db").read_bytes()

    with pytest.raises(FileExistsError):
        create(database, tmp_path)

    assert (
        snapshot / "market_data.db"
    ).read_bytes() == before


def test_active_ingestion_lock_blocks_snapshot(
    database, tmp_path
):
    with hold_daily_ingestion_lock(database):
        with pytest.raises(DailyRunAlreadyActiveError):
            create(database, tmp_path)

    assert not (
        tmp_path / "snapshots" / SNAPSHOT_ID
    ).exists()


def test_modified_snapshot_database_is_rejected(
    database, tmp_path
):
    snapshot = create(database, tmp_path)
    db_copy = snapshot / "market_data.db"

    with db_copy.open("ab") as stream:
        stream.write(b"UNAUTHORIZED_CHANGE")

    with pytest.raises(ValueError):
        verify_sqlite_snapshot(snapshot)


def test_modified_snapshot_manifest_is_rejected(
    database, tmp_path
):
    snapshot = create(database, tmp_path)
    manifest_path = snapshot / "manifest.json"

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    manifest["sha256"] = "0" * 64

    manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        verify_sqlite_snapshot(snapshot)


def test_restore_recovers_exact_logical_records(
    database, tmp_path
):
    snapshot = create(database, tmp_path)
    restored = tmp_path / "recovered.db"

    result = restore_sqlite_snapshot(
        snapshot_dir=snapshot,
        target_db=restored,
    )

    assert result == restored
    assert restored.is_file()
    assert rows(restored) == rows(database)
    assert rows(restored)[2] == "ok"


def test_restore_refuses_existing_database(
    database, tmp_path
):
    snapshot = create(database, tmp_path)
    target = tmp_path / "protected.db"

    target.write_bytes(b"PROTECTED")
    before = target.read_bytes()

    with pytest.raises(FileExistsError):
        restore_sqlite_snapshot(
            snapshot_dir=snapshot,
            target_db=target,
        )

    assert target.read_bytes() == before


def test_invalid_snapshot_id_cannot_escape_root(
    database, tmp_path
):
    root = tmp_path / "snapshots"

    with pytest.raises(ValueError):
        create_sqlite_snapshot(
            source_db=database,
            snapshot_root=root,
            snapshot_id="../escape",
        )

    assert not (tmp_path / "escape").exists()


def test_invalid_source_database_fails_closed(
    tmp_path,
):
    source = tmp_path / "invalid.db"
    source.write_bytes(b"THIS IS NOT SQLITE")

    root = tmp_path / "snapshots"

    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        create_sqlite_snapshot(
            source_db=source,
            snapshot_root=root,
            snapshot_id=SNAPSHOT_ID,
        )

    assert not (root / SNAPSHOT_ID).exists()
