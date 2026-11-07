"""A6c.23 Phase II: portable offline recovery contracts."""

from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from src.data.sqlite_snapshot import create_sqlite_snapshot
from src.data.snapshot_checkpoint import (
    write_snapshot_checkpoint,
)
from src.data.portable_recovery_bundle import (
    create_portable_recovery_bundle,
    restore_portable_recovery_bundle,
)


AS_OF = date(2026, 11, 2)
SYMBOLS = ("GOOGL", "NIO")
PILOT_SHA256 = "1" * 64

EXPECTED_MEMBERS = {
    "anchor.json",
    "checkpoint.json",
    "snapshot/manifest.json",
    "snapshot/market_data.db",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def case(tmp_path):
    source = tmp_path / "pilot.db"

    with sqlite3.connect(source) as conn:
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
            "INSERT INTO daily_bars VALUES (?, ?, ?, ?)",
            [
                ("GOOGL", "2026-10-30", 100.0, 1000000),
                ("GOOGL", "2026-11-02", 101.0, 1100000),
                ("NIO", "2026-11-02", 5.5, 2000000),
            ],
        )

        conn.executemany(
            "INSERT INTO download_status VALUES (?, ?, ?)",
            [
                ("GOOGL", "SUCCESS", "2026-11-02"),
                ("NIO", "SUCCESS", "2026-11-02"),
            ],
        )

        conn.commit()

    snapshot = create_sqlite_snapshot(
        source_db=source,
        snapshot_root=tmp_path / "snapshots",
        snapshot_id="us_pilot_2026-11-02_3_v1",
    )

    checkpoint = (
        tmp_path / "us_pilot_2026-11-02_checkpoint_v1.json"
    )

    write_snapshot_checkpoint(
        snapshot_dir=snapshot,
        checkpoint_path=checkpoint,
        as_of=AS_OF,
        pilot_manifest_sha256=PILOT_SHA256,
        required_symbols=SYMBOLS,
        previous_checkpoint_sha256=None,
    )

    snapshot_db = snapshot / "market_data.db"

    anchor_data = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "approval_status": "OFFLINE_CANDIDATE",
        "production_approved": False,
        "checkpoint_file": checkpoint.name,
        "checkpoint_sha256": digest(
            checkpoint.read_bytes()
        ),
        "snapshot_id": snapshot.name,
        "snapshot_sha256": digest(
            snapshot_db.read_bytes()
        ),
        "pilot_manifest_sha256": PILOT_SHA256,
        "as_of": AS_OF.isoformat(),
        "previous_checkpoint_sha256": None,
    }

    anchor = tmp_path / "anchor.json"

    anchor.write_text(
        json.dumps(anchor_data, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "anchor_path": anchor,
        "checkpoint_path": checkpoint,
        "snapshot_dir": snapshot,
        "bundle_path": tmp_path / "recovery.zip",
        "trusted_anchor_sha256": digest(
            anchor.read_bytes()
        ),
        "expected_pilot_manifest_sha256": PILOT_SHA256,
        "required_symbols": SYMBOLS,
        "min_as_of": AS_OF,
        "restore_root": tmp_path / "restored",
    }


def create(case, **overrides):
    args = {
        key: case[key]
        for key in (
            "anchor_path",
            "checkpoint_path",
            "snapshot_dir",
            "bundle_path",
            "trusted_anchor_sha256",
            "expected_pilot_manifest_sha256",
            "required_symbols",
            "min_as_of",
        )
    }
    args.update(overrides)

    return create_portable_recovery_bundle(**args)


def restore(case, **overrides):
    args = {
        key: case[key]
        for key in (
            "bundle_path",
            "trusted_anchor_sha256",
            "expected_pilot_manifest_sha256",
            "required_symbols",
            "min_as_of",
            "restore_root",
        )
    }
    args.update(overrides)

    return restore_portable_recovery_bundle(**args)


def rewrite_member(bundle, target_member, replacement):
    with zipfile.ZipFile(bundle, "r") as archive:
        members = [
            (name, archive.read(name))
            for name in archive.namelist()
        ]

    with zipfile.ZipFile(
        bundle,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for name, contents in members:
            archive.writestr(
                name,
                replacement if name == target_member
                else contents,
            )


def test_portable_bundle_restores_verified_sqlite(case):
    bundle = create(case)

    assert bundle == case["bundle_path"]
    assert bundle.is_file()

    with zipfile.ZipFile(bundle) as archive:
        assert set(archive.namelist()) == EXPECTED_MEMBERS

    result = restore(case)

    assert result == case["restore_root"]

    restored_db = (
        result
        / "snapshot"
        / case["snapshot_dir"].name
        / "market_data.db"
    )

    assert restored_db.is_file()
    assert restored_db.read_bytes() == (
        case["snapshot_dir"] / "market_data.db"
    ).read_bytes()

    with sqlite3.connect(
        f"file:{restored_db.resolve()}?mode=ro",
        uri=True,
    ) as conn:
        assert conn.execute(
            "PRAGMA integrity_check"
        ).fetchone() == ("ok",)

        assert conn.execute(
            "SELECT COUNT(*) FROM daily_bars"
        ).fetchone()[0] == 3


def test_existing_bundle_cannot_be_overwritten(case):
    bundle = create(case)
    before = bundle.read_bytes()

    with pytest.raises(FileExistsError):
        create(case)

    assert bundle.read_bytes() == before


def test_existing_restore_root_cannot_be_overwritten(case):
    create(case)

    root = case["restore_root"]
    root.mkdir()
    protected = root / "keep.txt"
    protected.write_text("DO NOT REPLACE")

    with pytest.raises(FileExistsError):
        restore(case)

    assert protected.read_text() == "DO NOT REPLACE"


def test_wrong_external_anchor_pin_is_rejected(case):
    with pytest.raises(ValueError):
        create(
            case,
            trusted_anchor_sha256="0" * 64,
        )

    assert not case["bundle_path"].exists()


def test_modified_archived_sqlite_is_rejected(case):
    bundle = create(case)

    with zipfile.ZipFile(bundle) as archive:
        original = archive.read(
            "snapshot/market_data.db"
        )

    rewrite_member(
        bundle,
        "snapshot/market_data.db",
        original + b"UNAUTHORIZED CHANGE",
    )

    with pytest.raises(ValueError):
        restore(case)

    assert not case["restore_root"].exists()


def test_zip_path_traversal_is_rejected(case):
    bundle = create(case)

    with zipfile.ZipFile(bundle, "a") as archive:
        archive.writestr(
            "../outside.txt",
            b"UNAUTHORIZED",
        )

    with pytest.raises(ValueError):
        restore(case)

    assert not case["restore_root"].exists()
    assert not (
        case["restore_root"].parent / "outside.txt"
    ).exists()


def test_rehashed_production_anchor_still_rejected(case):
    bundle = create(case)

    with zipfile.ZipFile(bundle) as archive:
        anchor = json.loads(
            archive.read("anchor.json")
        )

    anchor["production_approved"] = True

    altered_bytes = (
        json.dumps(anchor, indent=2) + "\n"
    ).encode("utf-8")

    rewrite_member(
        bundle,
        "anchor.json",
        altered_bytes,
    )

    with pytest.raises(ValueError):
        restore(
            case,
            trusted_anchor_sha256=digest(
                altered_bytes
            ),
        )

    assert not case["restore_root"].exists()


def test_stale_bundle_is_rejected(case):
    create(case)

    with pytest.raises(ValueError):
        restore(
            case,
            min_as_of=date(2026, 11, 3),
        )

    assert not case["restore_root"].exists()


# === STEP 240 — COMPLETION MARKER ===


def verify_completed(case):
    from src.data.portable_recovery_bundle import (
        verify_committed_recovery,
    )

    return verify_committed_recovery(
        restore_root=case["restore_root"],
        bundle_path=case["bundle_path"],
        trusted_anchor_sha256=(
            case["trusted_anchor_sha256"]
        ),
        expected_pilot_manifest_sha256=(
            case["expected_pilot_manifest_sha256"]
        ),
        required_symbols=case["required_symbols"],
        min_as_of=case["min_as_of"],
    )


def test_valid_recovery_has_completion_marker(case):
    create(case)
    root = restore(case)

    marker = root / "recovery.complete.json"

    assert marker.is_file()
    assert not marker.is_symlink()

    content = json.loads(
        marker.read_text(encoding="utf-8")
    )

    assert content["schema_version"] == 1
    assert content["status"] == "VERIFIED_OFFLINE"
    assert content["market"] == "US"
    assert content["mode"] == "PILOT_ONLY"
    assert content["approval_status"] == "OFFLINE_CANDIDATE"
    assert content["production_approved"] is False

    assert content["bundle_sha256"] == digest(
        case["bundle_path"].read_bytes()
    )
    assert content["trusted_anchor_sha256"] == (
        case["trusted_anchor_sha256"]
    )

    verified = verify_completed(case)
    assert verified == content


def test_missing_completion_marker_rejected(case):
    create(case)
    root = restore(case)

    (root / "recovery.complete.json").unlink()

    with pytest.raises(ValueError):
        verify_completed(case)


def test_changed_completion_digest_rejected(case):
    create(case)
    root = restore(case)

    marker = root / "recovery.complete.json"
    content = json.loads(marker.read_text())

    content["bundle_sha256"] = "0" * 64

    marker.write_text(
        json.dumps(content),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        verify_completed(case)


def test_production_claim_in_marker_rejected(case):
    create(case)
    root = restore(case)

    marker = root / "recovery.complete.json"
    content = json.loads(marker.read_text())

    content["production_approved"] = True

    marker.write_text(
        json.dumps(content),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        verify_completed(case)


def test_modified_restored_database_rejected(case):
    create(case)
    root = restore(case)

    db = (
        root
        / "snapshot"
        / case["snapshot_dir"].name
        / "market_data.db"
    )

    with db.open("ab") as stream:
        stream.write(b"UNAUTHORIZED CHANGE")

    with pytest.raises(ValueError):
        verify_completed(case)


def test_bundle_change_after_restore_rejected(case):
    create(case)
    restore(case)

    # Change only the ZIP metadata, leaving its members intact.
    # A completed recovery must remain bound to the same ZIP.
    with zipfile.ZipFile(
        case["bundle_path"],
        "a",
    ) as archive:
        archive.comment = b"CHANGED AFTER RESTORE"

    with pytest.raises(ValueError):
        verify_completed(case)


def test_symlinked_completion_marker_rejected(case):
    create(case)
    root = restore(case)

    marker = root / "recovery.complete.json"
    marker.unlink()

    marker.symlink_to(root / "anchor.json")

    with pytest.raises(ValueError):
        verify_completed(case)


def test_incomplete_restore_directory_rejected(case):
    create(case)

    root = case["restore_root"]
    root.mkdir()

    (root / "anchor.json").write_bytes(
        case["anchor_path"].read_bytes()
    )

    assert not (
        root / "recovery.complete.json"
    ).exists()

    with pytest.raises(ValueError):
        verify_completed(case)


# === STEP 243 — PUBLICATION SAFETY ===


def test_reader_rejects_before_marker_publication(
    case, monkeypatch
):
    """Uncommitted files must never be accepted by readers."""
    from src.data import portable_recovery_bundle as recovery

    create(case)

    original_writer = recovery._write_completion_marker
    observations = []

    def inspect_before_commit(marker_path, marker_data):
        root = case["restore_root"]

        assert root.is_dir()
        assert (root / "anchor.json").is_file()
        assert (root / "checkpoint.json").is_file()

        snapshot = (
            root
            / "snapshot"
            / case["snapshot_dir"].name
        )
        assert (snapshot / "manifest.json").is_file()
        assert (snapshot / "market_data.db").is_file()

        assert not marker_path.exists()

        with pytest.raises(
            ValueError,
            match="Missing or unsafe recovery completion marker",
        ):
            verify_completed(case)

        observations.append("READER_REJECTED")

        original_writer(marker_path, marker_data)

    monkeypatch.setattr(
        recovery,
        "_write_completion_marker",
        inspect_before_commit,
    )

    root = restore(case)

    assert observations == ["READER_REJECTED"]
    assert (
        verify_completed(case)["status"]
        == "VERIFIED_OFFLINE"
    )


def test_marker_publication_failure_cleans_partial_restore(
    case, monkeypatch
):
    """A failed final marker write must not leave a target."""
    from src.data import portable_recovery_bundle as recovery

    create(case)

    bundle_before = digest(
        case["bundle_path"].read_bytes()
    )

    def simulated_disk_failure(marker_path, marker_data):
        raise OSError(
            "simulated completion marker disk failure"
        )

    monkeypatch.setattr(
        recovery,
        "_write_completion_marker",
        simulated_disk_failure,
    )

    with pytest.raises(
        OSError,
        match="simulated completion marker disk failure",
    ):
        restore(case)

    assert not case["restore_root"].exists()

    assert digest(
        case["bundle_path"].read_bytes()
    ) == bundle_before

    assert not any(
        p.name.startswith(".portable-recovery-staging-")
        for p in case["restore_root"].parent.iterdir()
    )


def test_final_reverification_failure_rolls_back(
    case, monkeypatch
):
    """Even a failure after marker creation must roll back."""
    from src.data import portable_recovery_bundle as recovery

    create(case)

    observations = []

    def simulated_reverification_failure(**kwargs):
        root = kwargs["restore_root"]

        assert (
            root / "recovery.complete.json"
        ).is_file()

        observations.append("MARKER_WAS_PRESENT")

        raise ValueError(
            "simulated final verification failed"
        )

    monkeypatch.setattr(
        recovery,
        "verify_committed_recovery",
        simulated_reverification_failure,
    )

    with pytest.raises(
        ValueError,
        match="simulated final verification failed",
    ):
        restore(case)

    assert observations == ["MARKER_WAS_PRESENT"]
    assert not case["restore_root"].exists()


def test_concurrent_restore_cannot_claim_same_target(
    case, monkeypatch
):
    """A second publisher cannot replace an in-progress one."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from src.data import portable_recovery_bundle as recovery

    create(case)

    ready = Event()
    release = Event()

    original_writer = recovery._write_completion_marker

    def delayed_marker_writer(marker_path, marker_data):
        ready.set()

        if not release.wait(timeout=15):
            raise TimeoutError(
                "Test synchronization timed out"
            )

        original_writer(marker_path, marker_data)

    monkeypatch.setattr(
        recovery,
        "_write_completion_marker",
        delayed_marker_writer,
    )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(restore, case)

        try:
            assert ready.wait(timeout=15), (
                "Publisher did not reach marker boundary"
            )

            assert case["restore_root"].is_dir()

            with pytest.raises(FileExistsError):
                restore(case)

            with pytest.raises(
                ValueError,
                match="Missing or unsafe recovery completion marker",
            ):
                verify_completed(case)

        finally:
            release.set()

        root = future.result(timeout=20)

    assert root == case["restore_root"]
    assert (
        verify_completed(case)["status"]
        == "VERIFIED_OFFLINE"
    )


def test_unexpected_file_invalidates_completed_recovery(case):
    """A marked recovery is not valid after unapproved changes."""
    create(case)
    root = restore(case)

    assert (
        verify_completed(case)["status"]
        == "VERIFIED_OFFLINE"
    )

    unexpected = root / "unapproved.tmp"
    unexpected.write_text(
        "NOT PART OF THE RECOVERY BUNDLE",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Unexpected recovery root contents",
    ):
        verify_completed(case)
