"""A6c.30: independent authority-side evidence reverification.

Tests use real SQLite snapshots and checkpoints in tmp_path.
No tests grant authorization, update a head, or publish.
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
from src.data.trusted_head_authority import (
    prepare_trusted_head_advancement_request,
)
from src.data.authority_evidence_reverification import (
    reverify_authority_evidence,
)


SYMBOLS = ("GOOGL", "NIO")
PILOT_SHA = "1" * 64

CURRENT_DAY = date(2026, 11, 2)
CANDIDATE_DAY = date(2026, 11, 3)


def sha256(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def canonical_bytes(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ) + "\n"
    ).encode("utf-8")


def write_json(path, value):
    path.write_bytes(canonical_bytes(value))
    return sha256(path)


def source_database(path, as_of):
    session = as_of.isoformat()

    bars = [
        ("GOOGL", "2026-11-02", 101.0, 1000000.0),
        ("NIO", "2026-11-02", 5.5, 2000000.0),
    ]

    if as_of == CANDIDATE_DAY:
        bars.extend([
            ("GOOGL", "2026-11-03", 102.0, 1100000.0),
            ("NIO", "2026-11-03", 5.7, 2200000.0),
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
            "INSERT INTO daily_bars VALUES (?, ?, ?, ?)",
            bars,
        )

        db.executemany(
            "INSERT INTO download_status VALUES (?, ?, ?)",
            [
                ("GOOGL", "SUCCESS", session),
                ("NIO", "SUCCESS", session),
            ],
        )

        db.commit()


@pytest.fixture
def case(tmp_path):
    current_db = tmp_path / "current.db"
    candidate_db = tmp_path / "candidate.db"

    source_database(current_db, CURRENT_DAY)
    source_database(candidate_db, CANDIDATE_DAY)

    current_snapshot = create_sqlite_snapshot(
        source_db=current_db,
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

    head_sha = sha256(current_checkpoint)

    candidate_snapshot = create_sqlite_snapshot(
        source_db=candidate_db,
        snapshot_root=tmp_path / "snapshots",
        snapshot_id="us_pilot_2026-11-03_4_v1",
    )

    candidate_checkpoint = write_snapshot_checkpoint(
        snapshot_dir=candidate_snapshot,
        checkpoint_path=tmp_path / "candidate.json",
        as_of=CANDIDATE_DAY,
        pilot_manifest_sha256=PILOT_SHA,
        required_symbols=SYMBOLS,
        previous_checkpoint_sha256=head_sha,
    )

    candidate_sha = sha256(candidate_checkpoint)

    proposal = assess_verified_snapshot_advance(
        current_checkpoint_path=current_checkpoint,
        current_snapshot_dir=current_snapshot,
        candidate_checkpoint_path=candidate_checkpoint,
        candidate_snapshot_dir=candidate_snapshot,
        trusted_current_head_sha256=head_sha,
        expected_candidate_sha256=candidate_sha,
        expected_pilot_manifest_sha256=PILOT_SHA,
        required_symbols=SYMBOLS,
        min_candidate_as_of=CANDIDATE_DAY,
    )

    authority_state = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "generation": 0,
        "head_checkpoint_sha256": head_sha,
        "head_as_of": CURRENT_DAY.isoformat(),
        "pilot_manifest_sha256": PILOT_SHA,
        "previous_authority_state_sha256": None,
    }

    authority_path = tmp_path / "authority.json"
    authority_sha = write_json(
        authority_path,
        authority_state,
    )

    request = prepare_trusted_head_advancement_request(
        authority_state_path=authority_path,
        trusted_authority_state_sha256=authority_sha,
        verified_snapshot_proposal=proposal,
        expected_current_head_sha256=head_sha,
        expected_pilot_manifest_sha256=PILOT_SHA,
    )

    return {
        "authority_path": authority_path,
        "authority_sha": authority_sha,
        "current_checkpoint": current_checkpoint,
        "current_snapshot": current_snapshot,
        "candidate_checkpoint": candidate_checkpoint,
        "candidate_snapshot": candidate_snapshot,
        "head_sha": head_sha,
        "candidate_sha": candidate_sha,
        "proposal": proposal,
        "request": request,
    }


def reverify(case, **overrides):
    arguments = {
        "authority_state_path": case["authority_path"],
        "trusted_authority_state_sha256": (
            case["authority_sha"]
        ),
        "authorization_request": case["request"],
        "current_checkpoint_path": (
            case["current_checkpoint"]
        ),
        "current_snapshot_dir": case["current_snapshot"],
        "candidate_checkpoint_path": (
            case["candidate_checkpoint"]
        ),
        "candidate_snapshot_dir": case["candidate_snapshot"],
        "trusted_current_head_sha256": case["head_sha"],
        "expected_candidate_sha256": case["candidate_sha"],
        "expected_pilot_manifest_sha256": PILOT_SHA,
        "required_symbols": SYMBOLS,
        "min_candidate_as_of": CANDIDATE_DAY,
    }

    arguments.update(overrides)

    return reverify_authority_evidence(**arguments)


def make_request(case, proposal):
    return prepare_trusted_head_advancement_request(
        authority_state_path=case["authority_path"],
        trusted_authority_state_sha256=(
            case["authority_sha"]
        ),
        verified_snapshot_proposal=proposal,
        expected_current_head_sha256=case["head_sha"],
        expected_pilot_manifest_sha256=PILOT_SHA,
    )


def test_real_evidence_request_is_reverified(case):
    paths = [
        case["authority_path"],
        case["current_checkpoint"],
        case["candidate_checkpoint"],
        case["current_snapshot"] / "market_data.db",
        case["candidate_snapshot"] / "market_data.db",
    ]

    before = {
        str(path): sha256(path)
        for path in paths
    }

    result = reverify(case)

    assert result["status"] == (
        "EVIDENCE_REVERIFIED_AUTHORIZATION_REQUIRED"
    )
    assert result["production_approved"] is False

    assert result[
        "previous_authority_state_sha256"
    ] == case["authority_sha"]

    assert result[
        "current_head_checkpoint_sha256"
    ] == case["head_sha"]

    assert result[
        "candidate_head_checkpoint_sha256"
    ] == case["candidate_sha"]

    assert result["current_generation"] == 0
    assert result["requested_generation"] == 1

    assert result["candidate_as_of"] == "2026-11-03"

    assert result["candidate_snapshot_sha256"] == (
        verify_sqlite_snapshot(
            case["candidate_snapshot"]
        )["sha256"]
    )

    assert "signature" not in result
    assert "authority_approved" not in result
    assert "authorized" not in result

    assert reverify(case) == result

    assert {
        str(path): sha256(path)
        for path in paths
    } == before


def test_structurally_valid_forgery_is_rejected(case):
    forged = {
        **case["proposal"],
        "candidate_snapshot_sha256": "0" * 64,
    }

    forged_request = make_request(case, forged)

    assert forged_request["status"] == (
        "AUTHORIZATION_REQUIRED"
    )

    with pytest.raises(ValueError):
        reverify(
            case,
            authorization_request=forged_request,
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("status", "AUTHORIZED"),
        ("requested_generation", True),
        ("candidate_snapshot_sha256", "0" * 64),
        ("unexpected_authority_approval", True),
    ],
)
def test_modified_or_extended_request_is_rejected(
    case, field, replacement
):
    modified = {
        **case["request"],
        field: replacement,
    }

    with pytest.raises(ValueError):
        reverify(
            case,
            authorization_request=modified,
        )


def test_wrong_authority_state_pin_rejected(case):
    with pytest.raises(ValueError):
        reverify(
            case,
            trusted_authority_state_sha256="0" * 64,
        )


def test_wrong_current_head_pin_rejected(case):
    with pytest.raises(ValueError):
        reverify(
            case,
            trusted_current_head_sha256="0" * 64,
        )


def test_wrong_candidate_checkpoint_pin_rejected(case):
    with pytest.raises(ValueError):
        reverify(
            case,
            expected_candidate_sha256="0" * 64,
        )


def test_modified_candidate_sqlite_rejected(case):
    db_path = (
        case["candidate_snapshot"]
        / "market_data.db"
    )

    with db_path.open("ab") as stream:
        stream.write(b"UNAUTHORIZED_MODIFICATION")

    with pytest.raises(ValueError):
        reverify(case)


def test_resealed_incomplete_sqlite_state_rejected(case):
    """Reject a newly rehashed candidate with invalid status.

    Even a freshly generated, internally consistent
    request is not evidence of valid SQLite history.
    """

    snapshot = case["candidate_snapshot"]
    db_path = snapshot / "market_data.db"

    with sqlite3.connect(db_path) as db:
        updated = db.execute(
            """
            UPDATE download_status
            SET last_session = '2026-11-02'
            WHERE symbol = 'NIO'
            """
        )
        assert updated.rowcount == 1
        db.commit()

    database_sha = sha256(db_path)

    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    manifest["sha256"] = database_sha
    manifest["database_bytes"] = db_path.stat().st_size

    write_json(manifest_path, manifest)

    assert (
        verify_sqlite_snapshot(snapshot)["sha256"]
        == database_sha
    )

    checkpoint_path = case["candidate_checkpoint"]
    checkpoint = json.loads(
        checkpoint_path.read_text(encoding="utf-8")
    )

    checkpoint["snapshot_sha256"] = database_sha
    candidate_sha = write_json(
        checkpoint_path,
        checkpoint,
    )

    # Metadata advancement passes after resealing.
    metadata = assess_checkpoint_advance(
        current_checkpoint_path=case["current_checkpoint"],
        candidate_checkpoint_path=checkpoint_path,
        trusted_current_head_sha256=case["head_sha"],
        expected_candidate_sha256=candidate_sha,
        expected_pilot_manifest_sha256=PILOT_SHA,
        required_symbols=SYMBOLS,
        min_candidate_as_of=CANDIDATE_DAY,
    )

    assert metadata["status"] == (
        "VALIDATED_PROPOSAL_ONLY"
    )

    claimed_proposal = {
        **case["proposal"],
        "candidate_checkpoint_sha256": candidate_sha,
        "candidate_snapshot_sha256": database_sha,
    }

    refreshed_request = make_request(
        case,
        claimed_proposal,
    )

    assert refreshed_request["status"] == (
        "AUTHORIZATION_REQUIRED"
    )

    with pytest.raises(
        ValueError,
        match="Incomplete checkpoint status",
    ):
        reverify(
            case,
            authorization_request=refreshed_request,
            expected_candidate_sha256=candidate_sha,
        )


def test_wrong_candidate_snapshot_directory_rejected(case):
    with pytest.raises(ValueError):
        reverify(
            case,
            candidate_snapshot_dir=case["current_snapshot"],
        )


def test_symlinked_candidate_snapshot_rejected(
    case, tmp_path
):
    link = tmp_path / "candidate_link"

    link.symlink_to(
        case["candidate_snapshot"],
        target_is_directory=True,
    )

    with pytest.raises(ValueError):
        reverify(
            case,
            candidate_snapshot_dir=link,
        )


def test_candidate_below_minimum_date_rejected(case):
    with pytest.raises(ValueError):
        reverify(
            case,
            min_candidate_as_of=date(2026, 11, 4),
        )


def test_wrong_current_checkpoint_predecessor_rejected(case):
    with pytest.raises(ValueError):
        reverify(
            case,
            expected_current_predecessor_sha256="0" * 64,
        )
