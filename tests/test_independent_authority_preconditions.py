"""A6c.35: authority verification preconditions.

Real temporary SQLite and authority states are used
to reconstruct the entire evidence and decision chain.

The tested function does not:
- Authenticate the source of caller-supplied references.
- Obtain a protected state from an external authority.
- Obtain an independently trusted current UTC clock.
- Maintain a durable nonce/replay ledger.
- Grant authorization or perform atomic CAS.

Success is LOCAL PRECHECK ONLY.
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
from src.data.protected_authority_decision_request import (
    prepare_protected_authority_decision_request,
)
from src.data.independent_authority_preconditions import (
    assess_independent_authority_preconditions,
)


SYMBOLS = ("GOOGL", "NIO")
PILOT_SHA = "1" * 64

CURRENT = date(2026, 11, 2)
CANDIDATE = date(2026, 11, 3)

# Fixed synthetic UTC test clock.
ISSUED = "2026-11-10T18:00:00Z"
EXPIRES = "2026-11-10T18:05:00Z"
CHECKED = "2026-11-10T18:01:00Z"

NONCE = "0123456789abcdef0123456789abcdef"

STATUS = (
    "LOCAL_PRECHECK_PASSED_EXTERNAL_AUTHORITY_REQUIRED"
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


def make_database(path, as_of):
    rows = [
        ("GOOGL", "2026-11-02", 101.0, 1000000.0),
        ("NIO", "2026-11-02", 5.5, 2000000.0),
    ]

    if as_of == CANDIDATE:
        rows += [
            ("GOOGL", "2026-11-03", 102.0, 1100000.0),
            ("NIO", "2026-11-03", 5.7, 2200000.0),
        ]

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
            rows,
        )

        db.executemany(
            "INSERT INTO download_status VALUES (?, ?, ?)",
            [
                (
                    "GOOGL",
                    "SUCCESS",
                    as_of.isoformat(),
                ),
                (
                    "NIO",
                    "SUCCESS",
                    as_of.isoformat(),
                ),
            ],
        )

        db.commit()


@pytest.fixture
def case(tmp_path):
    db0 = tmp_path / "current.db"
    db1 = tmp_path / "candidate.db"

    make_database(db0, CURRENT)
    make_database(db1, CANDIDATE)

    snapshot0 = create_sqlite_snapshot(
        source_db=db0,
        snapshot_root=tmp_path / "snapshots",
        snapshot_id="us_pilot_2026-11-02_2_v1",
    )

    checkpoint0 = write_snapshot_checkpoint(
        snapshot_dir=snapshot0,
        checkpoint_path=tmp_path / "checkpoint_0.json",
        as_of=CURRENT,
        pilot_manifest_sha256=PILOT_SHA,
        required_symbols=SYMBOLS,
        previous_checkpoint_sha256=None,
    )

    head0 = sha256(checkpoint0)

    snapshot1 = create_sqlite_snapshot(
        source_db=db1,
        snapshot_root=tmp_path / "snapshots",
        snapshot_id="us_pilot_2026-11-03_4_v1",
    )

    checkpoint1 = write_snapshot_checkpoint(
        snapshot_dir=snapshot1,
        checkpoint_path=tmp_path / "checkpoint_1.json",
        as_of=CANDIDATE,
        pilot_manifest_sha256=PILOT_SHA,
        required_symbols=SYMBOLS,
        previous_checkpoint_sha256=head0,
    )

    head1 = sha256(checkpoint1)

    evidence_args = {
        "current_checkpoint_path": checkpoint0,
        "current_snapshot_dir": snapshot0,
        "candidate_checkpoint_path": checkpoint1,
        "candidate_snapshot_dir": snapshot1,
        "trusted_current_head_sha256": head0,
        "expected_candidate_sha256": head1,
        "expected_pilot_manifest_sha256": PILOT_SHA,
        "required_symbols": SYMBOLS,
        "min_candidate_as_of": CANDIDATE,
        "expected_current_predecessor_sha256": None,
    }

    proposal = assess_verified_snapshot_advance(
        **evidence_args
    )

    authority0 = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "generation": 0,
        "head_checkpoint_sha256": head0,
        "head_as_of": CURRENT.isoformat(),
        "pilot_manifest_sha256": PILOT_SHA,
        "previous_authority_state_sha256": None,
    }

    authority0_path = tmp_path / "authority_0.json"
    authority0_sha = write_json(
        authority0_path,
        authority0,
    )

    authorization = (
        prepare_trusted_head_advancement_request(
            authority_state_path=authority0_path,
            trusted_authority_state_sha256=authority0_sha,
            verified_snapshot_proposal=proposal,
            expected_current_head_sha256=head0,
            expected_pilot_manifest_sha256=PILOT_SHA,
        )
    )

    evidence = reverify_authority_evidence(
        authority_state_path=authority0_path,
        trusted_authority_state_sha256=authority0_sha,
        authorization_request=authorization,
        **evidence_args,
    )

    authority1 = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "generation": 1,
        "head_checkpoint_sha256": head1,
        "head_as_of": CANDIDATE.isoformat(),
        "pilot_manifest_sha256": PILOT_SHA,
        "previous_authority_state_sha256": authority0_sha,
    }

    authority1_path = tmp_path / "authority_1.json"
    authority1_sha = write_json(
        authority1_path,
        authority1,
    )

    review = assess_protected_authority_transition(
        current_authority_state_path=authority0_path,
        candidate_authority_state_path=authority1_path,
        trusted_current_authority_state_sha256=authority0_sha,
        expected_candidate_authority_state_sha256=authority1_sha,
        protected_latest_authority_state_sha256=authority0_sha,
        protected_latest_generation=0,
        reverified_authorization_request=evidence,
        expected_current_head_checkpoint_sha256=head0,
        expected_candidate_head_checkpoint_sha256=head1,
        expected_pilot_manifest_sha256=PILOT_SHA,
    )

    cas = prepare_authority_cas_intent(
        transition_review=review,
        trusted_transition_review_sha256=digest(review),
        protected_latest_authority_state_sha256=authority0_sha,
        protected_latest_generation=0,
        expected_candidate_authority_state_sha256=authority1_sha,
        expected_candidate_generation=1,
        expected_evidence_request_sha256=digest(evidence),
    )

    context = {
        **evidence_args,
        "current_authority_state_path": authority0_path,
        "candidate_authority_state_path": authority1_path,
        "trusted_current_authority_state_sha256": (
            authority0_sha
        ),
        "expected_candidate_authority_state_sha256": (
            authority1_sha
        ),
        "protected_latest_authority_state_sha256": (
            authority0_sha
        ),
        "protected_latest_generation": 0,
        "authorization_request": authorization,
        "transition_review": review,
        "cas_intent": cas,
    }

    boundary = assess_authority_execution_boundary(
        **context
    )

    decision = prepare_protected_authority_decision_request(
        execution_boundary_result=boundary,
        cas_intent=cas,
        trusted_execution_boundary_sha256=(
            digest(boundary)
        ),
        trusted_cas_intent_sha256=digest(cas),
        expected_operation_id=cas["operation_id"],
        protected_latest_authority_state_sha256=(
            authority0_sha
        ),
        protected_latest_generation=0,
        nonce=NONCE,
        issued_at=ISSUED,
        expires_at=EXPIRES,
        checked_at=CHECKED,
    )

    args = {
        "execution_context": context,
        "decision_request": decision,
        "expected_decision_request_sha256": (
            digest(decision)
        ),
        "reference_authority_state_sha256": (
            authority0_sha
        ),
        "reference_generation": 0,
        "reference_current_head_checkpoint_sha256": (
            head0
        ),
        "reference_pilot_manifest_sha256": PILOT_SHA,
        "reference_checked_at": CHECKED,
    }

    return {
        "args": args,
        "context": context,
        "decision": decision,
        "review": review,
        "cas": cas,
        "boundary": boundary,
        "authority0_sha": authority0_sha,
        "authority1_sha": authority1_sha,
        "authority0_path": authority0_path,
        "authority1_path": authority1_path,
        "head0": head0,
        "head1": head1,
        "checkpoint0": checkpoint0,
        "checkpoint1": checkpoint1,
        "snapshot0": snapshot0,
        "snapshot1": snapshot1,
    }


def assess(case, **changes):
    return assess_independent_authority_preconditions(
        **{
            **case["args"],
            **changes,
        }
    )


def changed_context(case, **changes):
    return {
        **case["context"],
        **changes,
    }


def changed_decision(case, **changes):
    return {
        **case["decision"],
        **changes,
    }


def test_valid_precheck_is_deterministic_and_read_only(case):
    paths = (
        case["authority0_path"],
        case["authority1_path"],
        case["checkpoint0"],
        case["checkpoint1"],
        case["snapshot0"] / "market_data.db",
        case["snapshot1"] / "market_data.db",
    )

    before = {
        str(path): sha256(path)
        for path in paths
    }

    result = assess(case)

    assert result["status"] == STATUS
    assert result["market"] == "US"
    assert result["mode"] == "PILOT_ONLY"
    assert result["production_approved"] is False

    assert result["decision_request_id"] == (
        case["decision"]["decision_request_id"]
    )

    assert result["decision_request_sha256"] == (
        digest(case["decision"])
    )

    assert result["operation_id"] == (
        case["cas"]["operation_id"]
    )

    assert result["execution_boundary_sha256"] == (
        digest(case["boundary"])
    )

    assert result["cas_intent_sha256"] == (
        digest(case["cas"])
    )

    assert result[
        "expected_authority_state_sha256"
    ] == case["authority0_sha"]

    assert result["expected_generation"] == 0

    assert result[
        "candidate_authority_state_sha256"
    ] == case["authority1_sha"]

    assert result["candidate_generation"] == 1

    assert result["reference_checked_at"] == CHECKED

    assert assess(case) == result

    assert {
        str(path): sha256(path)
        for path in paths
    } == before

    for forbidden in (
        "authorized",
        "approved",
        "authority_approved",
        "signature",
        "committed",
        "production_enabled",
    ):
        assert forbidden not in result


def test_wrong_decision_request_sha_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            expected_decision_request_sha256="0" * 64,
        )


def test_wrong_reference_authority_state_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            reference_authority_state_sha256="0" * 64,
        )


def test_wrong_reference_generation_rejected(case):
    with pytest.raises(ValueError):
        assess(case, reference_generation=1)


def test_boolean_reference_generation_rejected(case):
    with pytest.raises(ValueError):
        assess(case, reference_generation=False)


def test_wrong_reference_head_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            reference_current_head_checkpoint_sha256=(
                "0" * 64
            ),
        )


def test_wrong_reference_pilot_manifest_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            reference_pilot_manifest_sha256="0" * 64,
        )


def test_expired_at_reference_time_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            reference_checked_at=EXPIRES,
        )


def test_future_issued_at_reference_time_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            reference_checked_at="2026-11-10T17:59:59Z",
        )


def test_noncanonical_reference_time_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            reference_checked_at=(
                "2026-11-10T18:01:00+00:00"
            ),
        )


def test_modified_decision_request_id_rejected(case):
    modified = changed_decision(
        case,
        decision_request_id="0" * 64,
    )

    with pytest.raises(ValueError):
        assess(
            case,
            decision_request=modified,
            expected_decision_request_sha256=(
                digest(modified)
            ),
        )


def test_injected_decision_approval_rejected(case):
    modified = changed_decision(
        case,
        authority_approved=True,
    )

    with pytest.raises(ValueError):
        assess(
            case,
            decision_request=modified,
            expected_decision_request_sha256=(
                digest(modified)
            ),
        )


def test_boolean_decision_generation_rejected(case):
    modified = changed_decision(
        case,
        candidate_generation=True,
    )

    with pytest.raises(ValueError):
        assess(
            case,
            decision_request=modified,
            expected_decision_request_sha256=(
                digest(modified)
            ),
        )


def test_modified_nonce_without_identity_rejected(case):
    modified = changed_decision(
        case,
        nonce="abcdef0123456789abcdef0123456789",
    )

    with pytest.raises(ValueError):
        assess(
            case,
            decision_request=modified,
            expected_decision_request_sha256=(
                digest(modified)
            ),
        )


def test_modified_issued_at_without_identity_rejected(case):
    modified = changed_decision(
        case,
        issued_at="2026-11-10T18:00:01Z",
    )

    with pytest.raises(ValueError):
        assess(
            case,
            decision_request=modified,
            expected_decision_request_sha256=(
                digest(modified)
            ),
        )


def test_modified_expiry_without_identity_rejected(case):
    modified = changed_decision(
        case,
        expires_at="2026-11-10T18:04:59Z",
    )

    with pytest.raises(ValueError):
        assess(
            case,
            decision_request=modified,
            expected_decision_request_sha256=(
                digest(modified)
            ),
        )


def test_wrong_decision_operation_id_rejected(case):
    modified = changed_decision(
        case,
        operation_id="0" * 64,
    )

    with pytest.raises(ValueError):
        assess(
            case,
            decision_request=modified,
            expected_decision_request_sha256=(
                digest(modified)
            ),
        )


def test_self_consistent_forged_provenance_rejected(case):
    """Rehashing all claims cannot replace SQLite proof."""

    forged_evidence_sha = "9" * 64

    forged_review = {
        **case["review"],
        "evidence_request_sha256": forged_evidence_sha,
    }

    forged_cas = prepare_authority_cas_intent(
        transition_review=forged_review,
        trusted_transition_review_sha256=(
            digest(forged_review)
        ),
        protected_latest_authority_state_sha256=(
            case["authority0_sha"]
        ),
        protected_latest_generation=0,
        expected_candidate_authority_state_sha256=(
            case["authority1_sha"]
        ),
        expected_candidate_generation=1,
        expected_evidence_request_sha256=(
            forged_evidence_sha
        ),
    )

    forged_boundary = {
        **case["boundary"],
        "evidence_request_sha256": forged_evidence_sha,
        "transition_review_sha256": (
            digest(forged_review)
        ),
        "operation_id": forged_cas["operation_id"],
        "cas_intent_sha256": digest(forged_cas),
    }

    forged_decision = (
        prepare_protected_authority_decision_request(
            execution_boundary_result=forged_boundary,
            cas_intent=forged_cas,
            trusted_execution_boundary_sha256=(
                digest(forged_boundary)
            ),
            trusted_cas_intent_sha256=(
                digest(forged_cas)
            ),
            expected_operation_id=(
                forged_cas["operation_id"]
            ),
            protected_latest_authority_state_sha256=(
                case["authority0_sha"]
            ),
            protected_latest_generation=0,
            nonce=NONCE,
            issued_at=ISSUED,
            expires_at=EXPIRES,
            checked_at=CHECKED,
        )
    )

    assert forged_decision["status"] == (
        "EXTERNAL_AUTHORITY_DECISION_REQUIRED_NOT_GRANTED"
    )

    with pytest.raises(ValueError):
        assess(
            case,
            execution_context=changed_context(
                case,
                transition_review=forged_review,
                cas_intent=forged_cas,
            ),
            decision_request=forged_decision,
            expected_decision_request_sha256=(
                digest(forged_decision)
            ),
        )


def test_stale_execution_context_floor_sha_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            execution_context=changed_context(
                case,
                protected_latest_authority_state_sha256=(
                    case["authority1_sha"]
                ),
            ),
        )


def test_stale_execution_context_generation_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            execution_context=changed_context(
                case,
                protected_latest_generation=1,
            ),
        )


def test_forged_authorization_request_rejected(case):
    forged_request = {
        **case["context"]["authorization_request"],
        "candidate_snapshot_sha256": "0" * 64,
    }

    with pytest.raises(ValueError):
        assess(
            case,
            execution_context=changed_context(
                case,
                authorization_request=forged_request,
            ),
        )


def test_modified_candidate_sqlite_rejected(case):
    path = case["snapshot1"] / "market_data.db"

    with path.open("ab") as stream:
        stream.write(b"UNAUTHORIZED_SQLITE_CHANGE")

    with pytest.raises(ValueError):
        assess(case)


def test_symlinked_candidate_snapshot_rejected(
    case, tmp_path
):
    link = tmp_path / "candidate_link"

    link.symlink_to(
        case["snapshot1"],
        target_is_directory=True,
    )

    with pytest.raises(ValueError):
        assess(
            case,
            execution_context=changed_context(
                case,
                candidate_snapshot_dir=link,
            ),
        )


def test_unexpected_execution_context_field_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            execution_context=changed_context(
                case,
                authority_approved=True,
            ),
        )


def test_missing_execution_context_field_rejected(case):
    incomplete = dict(case["context"])
    incomplete.pop("candidate_snapshot_dir")

    with pytest.raises(ValueError):
        assess(
            case,
            execution_context=incomplete,
        )


def test_repeated_precheck_does_not_claim_replay_protection(
    case,
):
    first = assess(case)
    second = assess(case)

    # Without an independently maintained durable
    # ledger, both local assessments remain possible.
    assert first == second
    assert first["status"] == STATUS
    assert first["production_approved"] is False
    assert "authorized" not in first
    assert "committed" not in first
