"""A6c.33: authority-side evidence binding contract.

The subject must independently reverify real SQLite,
authority states, transition review and CAS intent.

Even a successful result cannot approve or execute CAS.
All test files are temporary.
"""

from datetime import date
import hashlib
import json
import sqlite3

import pytest

from src.data.sqlite_snapshot import (
    create_sqlite_snapshot,
)
from src.data.snapshot_checkpoint import (
    write_snapshot_checkpoint,
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
from src.data.protected_authority_transition import (
    assess_protected_authority_transition,
)
from src.data.authority_cas_intent import (
    prepare_authority_cas_intent,
)
from src.data.authority_execution_boundary import (
    assess_authority_execution_boundary,
)


SYMBOLS = ("GOOGL", "NIO")
PILOT_SHA = "1" * 64

CURRENT_DAY = date(2026, 11, 2)
CANDIDATE_DAY = date(2026, 11, 3)

BOUND_STATUS = (
    "EVIDENCE_BOUND_EXTERNAL_CAS_REQUIRED_NOT_EXECUTED"
)


def canonical(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ) + "\n"
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(
        canonical(value)
    ).hexdigest()


def sha256(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def write_json(path, value):
    path.write_bytes(canonical(value))
    return sha256(path)


def make_database(path, day):
    bars = [
        ("GOOGL", "2026-11-02", 101.0, 1000000.0),
        ("NIO", "2026-11-02", 5.5, 2000000.0),
    ]

    if day == CANDIDATE_DAY:
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
                ("GOOGL", "SUCCESS", day.isoformat()),
                ("NIO", "SUCCESS", day.isoformat()),
            ],
        )

        db.commit()


@pytest.fixture
def case(tmp_path):
    current_db = tmp_path / "current.db"
    candidate_db = tmp_path / "candidate.db"

    make_database(current_db, CURRENT_DAY)
    make_database(candidate_db, CANDIDATE_DAY)

    current_snapshot = create_sqlite_snapshot(
        source_db=current_db,
        snapshot_root=tmp_path / "snapshots",
        snapshot_id="us_pilot_2026-11-02_2_v1",
    )

    current_checkpoint = write_snapshot_checkpoint(
        snapshot_dir=current_snapshot,
        checkpoint_path=tmp_path / "current_checkpoint.json",
        as_of=CURRENT_DAY,
        pilot_manifest_sha256=PILOT_SHA,
        required_symbols=SYMBOLS,
        previous_checkpoint_sha256=None,
    )

    current_head = sha256(current_checkpoint)

    candidate_snapshot = create_sqlite_snapshot(
        source_db=candidate_db,
        snapshot_root=tmp_path / "snapshots",
        snapshot_id="us_pilot_2026-11-03_4_v1",
    )

    candidate_checkpoint = write_snapshot_checkpoint(
        snapshot_dir=candidate_snapshot,
        checkpoint_path=tmp_path / "candidate_checkpoint.json",
        as_of=CANDIDATE_DAY,
        pilot_manifest_sha256=PILOT_SHA,
        required_symbols=SYMBOLS,
        previous_checkpoint_sha256=current_head,
    )

    candidate_head = sha256(candidate_checkpoint)

    evidence_args = {
        "current_checkpoint_path": current_checkpoint,
        "current_snapshot_dir": current_snapshot,
        "candidate_checkpoint_path": candidate_checkpoint,
        "candidate_snapshot_dir": candidate_snapshot,
        "trusted_current_head_sha256": current_head,
        "expected_candidate_sha256": candidate_head,
        "expected_pilot_manifest_sha256": PILOT_SHA,
        "required_symbols": SYMBOLS,
        "min_candidate_as_of": CANDIDATE_DAY,
    }

    proposal = assess_verified_snapshot_advance(
        **evidence_args
    )

    authority_0 = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "generation": 0,
        "head_checkpoint_sha256": current_head,
        "head_as_of": CURRENT_DAY.isoformat(),
        "pilot_manifest_sha256": PILOT_SHA,
        "previous_authority_state_sha256": None,
    }

    authority_0_path = tmp_path / "authority_0.json"
    authority_0_sha = write_json(
        authority_0_path,
        authority_0,
    )

    authorization_request = (
        prepare_trusted_head_advancement_request(
            authority_state_path=authority_0_path,
            trusted_authority_state_sha256=authority_0_sha,
            verified_snapshot_proposal=proposal,
            expected_current_head_sha256=current_head,
            expected_pilot_manifest_sha256=PILOT_SHA,
        )
    )

    reverified = reverify_authority_evidence(
        authority_state_path=authority_0_path,
        trusted_authority_state_sha256=authority_0_sha,
        authorization_request=authorization_request,
        **evidence_args,
    )

    authority_1 = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "generation": 1,
        "head_checkpoint_sha256": candidate_head,
        "head_as_of": CANDIDATE_DAY.isoformat(),
        "pilot_manifest_sha256": PILOT_SHA,
        "previous_authority_state_sha256": authority_0_sha,
    }

    authority_1_path = tmp_path / "authority_1.json"
    authority_1_sha = write_json(
        authority_1_path,
        authority_1,
    )

    review = assess_protected_authority_transition(
        current_authority_state_path=authority_0_path,
        candidate_authority_state_path=authority_1_path,
        trusted_current_authority_state_sha256=authority_0_sha,
        expected_candidate_authority_state_sha256=authority_1_sha,
        protected_latest_authority_state_sha256=authority_0_sha,
        protected_latest_generation=0,
        reverified_authorization_request=reverified,
        expected_current_head_checkpoint_sha256=current_head,
        expected_candidate_head_checkpoint_sha256=candidate_head,
        expected_pilot_manifest_sha256=PILOT_SHA,
    )

    intent = prepare_authority_cas_intent(
        transition_review=review,
        trusted_transition_review_sha256=digest(review),
        protected_latest_authority_state_sha256=authority_0_sha,
        protected_latest_generation=0,
        expected_candidate_authority_state_sha256=authority_1_sha,
        expected_candidate_generation=1,
        expected_evidence_request_sha256=digest(reverified),
    )

    args = {
        **evidence_args,
        "current_authority_state_path": authority_0_path,
        "candidate_authority_state_path": authority_1_path,
        "trusted_current_authority_state_sha256": (
            authority_0_sha
        ),
        "expected_candidate_authority_state_sha256": (
            authority_1_sha
        ),
        "protected_latest_authority_state_sha256": (
            authority_0_sha
        ),
        "protected_latest_generation": 0,
        "authorization_request": authorization_request,
        "transition_review": review,
        "cas_intent": intent,
    }

    return {
        "args": args,
        "review": review,
        "intent": intent,
        "reverified": reverified,
        "authority_0_path": authority_0_path,
        "authority_1_path": authority_1_path,
        "authority_0_sha": authority_0_sha,
        "authority_1_sha": authority_1_sha,
        "authority_1": authority_1,
        "current_head": current_head,
        "candidate_head": candidate_head,
        "candidate_checkpoint": candidate_checkpoint,
        "candidate_snapshot": candidate_snapshot,
    }


def assess(case, **changes):
    return assess_authority_execution_boundary(
        **{
            **case["args"],
            **changes,
        }
    )


def forge_intent(case, forged_review):
    """Show that A6c.32 accepts a self-consistent claim.

    This does NOT authenticate evidence.
    """
    return prepare_authority_cas_intent(
        transition_review=forged_review,
        trusted_transition_review_sha256=(
            digest(forged_review)
        ),
        protected_latest_authority_state_sha256=(
            case["authority_0_sha"]
        ),
        protected_latest_generation=0,
        expected_candidate_authority_state_sha256=(
            case["authority_1_sha"]
        ),
        expected_candidate_generation=1,
        expected_evidence_request_sha256=(
            forged_review["evidence_request_sha256"]
        ),
    )


def test_valid_evidence_is_bound_without_execution(case):
    paths = (
        case["authority_0_path"],
        case["authority_1_path"],
        case["args"]["current_checkpoint_path"],
        case["candidate_checkpoint"],
        case["args"]["current_snapshot_dir"] / "market_data.db",
        case["candidate_snapshot"] / "market_data.db",
    )

    before = {
        str(path): sha256(path)
        for path in paths
    }

    result = assess(case)

    assert result["status"] == BOUND_STATUS
    assert result["market"] == "US"
    assert result["mode"] == "PILOT_ONLY"
    assert result["production_approved"] is False

    assert result[
        "current_authority_state_sha256"
    ] == case["authority_0_sha"]

    assert result[
        "candidate_authority_state_sha256"
    ] == case["authority_1_sha"]

    assert result["current_generation"] == 0
    assert result["candidate_generation"] == 1

    assert result[
        "current_head_checkpoint_sha256"
    ] == case["current_head"]

    assert result[
        "candidate_head_checkpoint_sha256"
    ] == case["candidate_head"]

    assert result[
        "evidence_request_sha256"
    ] == digest(case["reverified"])

    assert result[
        "transition_review_sha256"
    ] == digest(case["review"])

    assert result["operation_id"] == (
        case["intent"]["operation_id"]
    )

    assert result["cas_intent_sha256"] == (
        digest(case["intent"])
    )

    assert assess(case) == result

    for forbidden in (
        "authorized",
        "authority_approved",
        "signature",
        "committed",
        "production_enabled",
    ):
        assert forbidden not in result

    assert {
        str(path): sha256(path)
        for path in paths
    } == before


def test_forged_review_evidence_is_rejected(case):
    forged_review = {
        **case["review"],
        "evidence_request_sha256": "9" * 64,
    }

    forged_intent = forge_intent(
        case,
        forged_review,
    )

    assert forged_intent["status"] == (
        "EXTERNAL_ATOMIC_CAS_REQUIRED_NOT_EXECUTED"
    )

    with pytest.raises(ValueError):
        assess(
            case,
            transition_review=forged_review,
            cas_intent=forged_intent,
        )


def test_forged_review_checkpoint_is_rejected(case):
    forged_review = {
        **case["review"],
        "candidate_head_checkpoint_sha256": "7" * 64,
    }

    forged_intent = forge_intent(
        case,
        forged_review,
    )

    assert forged_intent["status"] == (
        "EXTERNAL_ATOMIC_CAS_REQUIRED_NOT_EXECUTED"
    )

    with pytest.raises(ValueError):
        assess(
            case,
            transition_review=forged_review,
            cas_intent=forged_intent,
        )


def test_altered_cas_operation_id_rejected(case):
    altered = {
        **case["intent"],
        "operation_id": "0" * 64,
    }

    with pytest.raises(ValueError):
        assess(case, cas_intent=altered)


def test_boolean_cas_generation_rejected(case):
    altered = {
        **case["intent"],
        "candidate_generation": True,
    }

    with pytest.raises(ValueError):
        assess(case, cas_intent=altered)


def test_injected_cas_approval_field_rejected(case):
    altered = {
        **case["intent"],
        "authority_approved": True,
    }

    with pytest.raises(ValueError):
        assess(case, cas_intent=altered)


def test_cas_executed_status_rejected(case):
    altered = {
        **case["intent"],
        "status": "ATOMIC_CAS_EXECUTED",
    }

    with pytest.raises(ValueError):
        assess(case, cas_intent=altered)


def test_forged_authorization_request_rejected(case):
    altered = {
        **case["args"]["authorization_request"],
        "candidate_snapshot_sha256": "0" * 64,
    }

    with pytest.raises(ValueError):
        assess(
            case,
            authorization_request=altered,
        )


def test_modified_candidate_sqlite_rejected(case):
    path = (
        case["candidate_snapshot"]
        / "market_data.db"
    )

    with path.open("ab") as stream:
        stream.write(b"UNAUTHORIZED_CHANGE")

    with pytest.raises(ValueError):
        assess(case)


def test_wrong_current_authority_pin_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            trusted_current_authority_state_sha256=(
                "0" * 64
            ),
        )


def test_wrong_candidate_authority_pin_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            expected_candidate_authority_state_sha256=(
                "0" * 64
            ),
        )


def test_stale_protected_floor_sha_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            protected_latest_authority_state_sha256=(
                case["authority_1_sha"]
            ),
        )


def test_stale_protected_floor_generation_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            protected_latest_generation=1,
        )


def test_boolean_protected_floor_generation_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            protected_latest_generation=False,
        )


def test_wrong_current_checkpoint_pin_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            trusted_current_head_sha256="0" * 64,
        )


def test_wrong_candidate_checkpoint_pin_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            expected_candidate_sha256="0" * 64,
        )


def test_wrong_pilot_manifest_pin_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            expected_pilot_manifest_sha256="0" * 64,
        )


def test_candidate_date_below_minimum_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            min_candidate_as_of=date(2026, 11, 4),
        )


def test_wrong_current_predecessor_pin_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            expected_current_predecessor_sha256="0" * 64,
        )


def test_symlinked_candidate_snapshot_rejected(
    case, tmp_path
):
    link = tmp_path / "linked_snapshot"

    link.symlink_to(
        case["candidate_snapshot"],
        target_is_directory=True,
    )

    with pytest.raises(ValueError):
        assess(case, candidate_snapshot_dir=link)


def test_symlinked_candidate_authority_rejected(
    case, tmp_path
):
    link = tmp_path / "linked_authority.json"

    link.symlink_to(
        case["authority_1_path"]
    )

    with pytest.raises(ValueError):
        assess(
            case,
            candidate_authority_state_path=link,
        )


def test_modified_candidate_authority_rejected(case):
    altered = {
        **case["authority_1"],
        "production_approved": True,
    }

    modified_sha = write_json(
        case["authority_1_path"],
        altered,
    )

    with pytest.raises(ValueError):
        assess(
            case,
            expected_candidate_authority_state_sha256=(
                modified_sha
            ),
        )
