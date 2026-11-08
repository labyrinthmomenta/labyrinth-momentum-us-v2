"""A6c.28: verified offline snapshot advancement tests.

A successful assessment verifies both the checkpoint
transition and its actual SQLite snapshots.

No test updates an authorized trusted head, performs
network access, or enables production.
"""

from datetime import date
import hashlib
import json
import sqlite3

import pytest

from src.data.sqlite_snapshot import (
    create_sqlite_snapshot,
    verify_sqlite_snapshot,
)
from src.data.snapshot_checkpoint import (
    write_snapshot_checkpoint,
)
from src.data.trusted_checkpoint_advancement import (
    assess_checkpoint_advance,
)
from src.data.verified_snapshot_advancement import (
    assess_verified_snapshot_advance,
)


SYMBOLS = ("GOOGL", "NIO")
PILOT_SHA = "1" * 64

CURRENT_DAY = date(2026, 11, 2)
CANDIDATE_DAY = date(2026, 11, 3)


def sha256(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def write_json(path, content):
    raw = (
        json.dumps(
            content,
            sort_keys=True,
            indent=2,
        ) + "\n"
    ).encode("utf-8")

    path.write_bytes(raw)

    return hashlib.sha256(raw).hexdigest()


def make_source_database(path, as_of):
    """Create a genuine two-symbol SQLite source."""
    current_day = as_of.isoformat()

    bars = [
        (
            "GOOGL",
            "2026-11-02",
            101.0,
            1000000.0,
        ),
        (
            "NIO",
            "2026-11-02",
            5.5,
            2000000.0,
        ),
    ]

    if as_of == CANDIDATE_DAY:
        bars.extend([
            (
                "GOOGL",
                "2026-11-03",
                102.0,
                1100000.0,
            ),
            (
                "NIO",
                "2026-11-03",
                5.7,
                2200000.0,
            ),
        ])

    with sqlite3.connect(path) as db:
        db.executescript("""
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

        db.executemany(
            """
            INSERT INTO daily_bars
            VALUES (?, ?, ?, ?)
            """,
            bars,
        )

        db.executemany(
            """
            INSERT INTO download_status
            VALUES (?, ?, ?)
            """,
            [
                ("GOOGL", "SUCCESS", current_day),
                ("NIO", "SUCCESS", current_day),
            ],
        )

        db.commit()


@pytest.fixture
def case(tmp_path):
    source_current = tmp_path / "source_current.db"
    source_candidate = tmp_path / "source_candidate.db"

    make_source_database(
        source_current,
        CURRENT_DAY,
    )

    make_source_database(
        source_candidate,
        CANDIDATE_DAY,
    )

    current_snapshot = create_sqlite_snapshot(
        source_db=source_current,
        snapshot_root=tmp_path / "snapshots",
        snapshot_id="us_pilot_2026-11-02_2_v1",
    )

    current_checkpoint = write_snapshot_checkpoint(
        snapshot_dir=current_snapshot,
        checkpoint_path=tmp_path / "current.json",
        as_of=CURRENT_DAY,
        pilot_manifest_sha256=PILOT_SHA,
        required_symbols=SYMBOLS,
        previous_checkpoint_sha256=None,
    )

    current_head = sha256(current_checkpoint)

    candidate_snapshot = create_sqlite_snapshot(
        source_db=source_candidate,
        snapshot_root=tmp_path / "snapshots",
        snapshot_id="us_pilot_2026-11-03_2_v1",
    )

    candidate_checkpoint = write_snapshot_checkpoint(
        snapshot_dir=candidate_snapshot,
        checkpoint_path=tmp_path / "candidate.json",
        as_of=CANDIDATE_DAY,
        pilot_manifest_sha256=PILOT_SHA,
        required_symbols=SYMBOLS,
        previous_checkpoint_sha256=current_head,
    )

    candidate_sha = sha256(candidate_checkpoint)

    assert (
        verify_sqlite_snapshot(current_snapshot)
        ["sha256"]
        != verify_sqlite_snapshot(candidate_snapshot)
        ["sha256"]
    )

    return {
        "current_snapshot": current_snapshot,
        "current_checkpoint": current_checkpoint,
        "current_head": current_head,
        "candidate_snapshot": candidate_snapshot,
        "candidate_checkpoint": candidate_checkpoint,
        "candidate_sha": candidate_sha,
    }


def assess(case, **overrides):
    args = {
        "current_checkpoint_path": (
            case["current_checkpoint"]
        ),
        "current_snapshot_dir": (
            case["current_snapshot"]
        ),
        "candidate_checkpoint_path": (
            case["candidate_checkpoint"]
        ),
        "candidate_snapshot_dir": (
            case["candidate_snapshot"]
        ),
        "trusted_current_head_sha256": (
            case["current_head"]
        ),
        "expected_candidate_sha256": (
            case["candidate_sha"]
        ),
        "expected_pilot_manifest_sha256": PILOT_SHA,
        "required_symbols": SYMBOLS,
        "min_candidate_as_of": CANDIDATE_DAY,
    }

    args.update(overrides)

    return assess_verified_snapshot_advance(**args)


def update_candidate_checkpoint(case, **changes):
    path = case["candidate_checkpoint"]

    content = json.loads(
        path.read_text(encoding="utf-8")
    )

    content.update(changes)

    case["candidate_sha"] = write_json(
        path,
        content,
    )


def test_valid_verified_snapshot_proposal(case):
    result = assess(case)

    assert result["status"] == (
        "VERIFIED_SNAPSHOT_PROPOSAL_ONLY"
    )

    assert result["previous_checkpoint_sha256"] == (
        case["current_head"]
    )

    assert result["candidate_checkpoint_sha256"] == (
        case["candidate_sha"]
    )

    assert result["previous_as_of"] == "2026-11-02"
    assert result["candidate_as_of"] == "2026-11-03"
    assert result["pilot_manifest_sha256"] == PILOT_SHA
    assert result["production_approved"] is False

    candidate_manifest = verify_sqlite_snapshot(
        case["candidate_snapshot"]
    )

    assert result["candidate_snapshot_sha256"] == (
        candidate_manifest["sha256"]
    )


def test_wrong_independent_current_head_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            trusted_current_head_sha256="0" * 64,
        )


def test_wrong_independent_candidate_pin_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            expected_candidate_sha256="0" * 64,
        )


def test_missing_candidate_snapshot_rejected(
    case, tmp_path
):
    with pytest.raises(
        (ValueError, FileNotFoundError)
    ):
        assess(
            case,
            candidate_snapshot_dir=(
                tmp_path / "missing_snapshot"
            ),
        )


def test_wrong_candidate_snapshot_directory_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            candidate_snapshot_dir=(
                case["current_snapshot"]
            ),
        )


def test_modified_candidate_sqlite_rejected(case):
    db = (
        case["candidate_snapshot"]
        / "market_data.db"
    )

    with db.open("ab") as stream:
        stream.write(b"UNAUTHORIZED_CHANGE")

    with pytest.raises(ValueError):
        assess(case)


def test_modified_candidate_manifest_rejected(case):
    manifest_path = (
        case["candidate_snapshot"]
        / "manifest.json"
    )

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    manifest["tables"]["daily_bars"] = 999

    write_json(manifest_path, manifest)

    with pytest.raises(ValueError):
        assess(case)


def test_resealed_incomplete_status_rejected(case):
    """Reject bad data even after manifest/checkpoint rehashing.

    The metadata transition itself must remain valid.
    Failure must come from actual SQLite state validation.
    """

    snapshot_dir = case["candidate_snapshot"]
    db_path = snapshot_dir / "market_data.db"

    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            UPDATE download_status
            SET last_session = '2026-11-02'
            WHERE symbol = 'NIO'
            """
        )
        db.commit()

    new_db_sha = sha256(db_path)

    manifest_path = snapshot_dir / "manifest.json"

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    manifest["sha256"] = new_db_sha
    manifest["database_bytes"] = (
        db_path.stat().st_size
    )

    write_json(manifest_path, manifest)

    # Internal snapshot verification still succeeds.
    assert (
        verify_sqlite_snapshot(snapshot_dir)["sha256"]
        == new_db_sha
    )

    # Update checkpoint with the new snapshot hash
    # and independently pin that candidate in the test.
    update_candidate_checkpoint(
        case,
        snapshot_sha256=new_db_sha,
    )

    # Metadata advancement alone accepts this candidate.
    metadata = assess_checkpoint_advance(
        current_checkpoint_path=(
            case["current_checkpoint"]
        ),
        candidate_checkpoint_path=(
            case["candidate_checkpoint"]
        ),
        trusted_current_head_sha256=(
            case["current_head"]
        ),
        expected_candidate_sha256=(
            case["candidate_sha"]
        ),
        expected_pilot_manifest_sha256=PILOT_SHA,
        required_symbols=SYMBOLS,
        min_candidate_as_of=CANDIDATE_DAY,
    )

    assert metadata["status"] == (
        "VALIDATED_PROPOSAL_ONLY"
    )

    # Full verification must reject the stale NIO status.
    with pytest.raises(
        ValueError,
        match="Incomplete checkpoint status",
    ):
        assess(case)


def test_wrong_predecessor_even_if_rehashed_rejected(case):
    update_candidate_checkpoint(
        case,
        previous_checkpoint_sha256="2" * 64,
    )

    with pytest.raises(ValueError):
        assess(case)


def test_production_claim_even_if_rehashed_rejected(case):
    update_candidate_checkpoint(
        case,
        production_approved=True,
    )

    with pytest.raises(ValueError):
        assess(case)


def test_symlinked_candidate_snapshot_rejected(
    case, tmp_path
):
    link = tmp_path / "candidate_snapshot_link"

    link.symlink_to(
        case["candidate_snapshot"],
        target_is_directory=True,
    )

    with pytest.raises(ValueError):
        assess(
            case,
            candidate_snapshot_dir=link,
        )
