"""A6c.31: offline protected authority transition contract.

Tests model independently supplied protected-head pins.
They do not implement a durable trust store, signing,
authorization, compare-and-swap or publication.

A reverified-evidence status is modeled as an input claim.
It must never authorize a transition by itself.
"""

import hashlib
import json

import pytest

from src.data.protected_authority_transition import (
    assess_protected_authority_transition,
)


HEAD = "a" * 64
CANDIDATE_HEAD = "b" * 64
PILOT = "c" * 64
SNAPSHOT = "d" * 64
PROPOSAL = "e" * 64


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


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256(path):
    return sha256_bytes(path.read_bytes())


def write_json(path, value):
    path.write_bytes(canonical_bytes(value))
    return sha256(path)


@pytest.fixture
def case(tmp_path):
    current = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "generation": 0,
        "head_checkpoint_sha256": HEAD,
        "head_as_of": "2026-11-02",
        "pilot_manifest_sha256": PILOT,
        "previous_authority_state_sha256": None,
    }

    current_path = tmp_path / "current_authority.json"
    current_sha = write_json(current_path, current)

    candidate = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "generation": 1,
        "head_checkpoint_sha256": CANDIDATE_HEAD,
        "head_as_of": "2026-11-03",
        "pilot_manifest_sha256": PILOT,
        "previous_authority_state_sha256": current_sha,
    }

    candidate_path = tmp_path / "candidate_authority.json"
    candidate_sha = write_json(
        candidate_path,
        candidate,
    )

    # This is a synthetic, unauthenticated input claim.
    # A real authority must independently authenticate
    # its evidence before any protected-state mutation.
    request = {
        "status": (
            "EVIDENCE_REVERIFIED_AUTHORIZATION_REQUIRED"
        ),
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "previous_authority_state_sha256": (
            current_sha
        ),
        "current_head_checkpoint_sha256": HEAD,
        "candidate_head_checkpoint_sha256": (
            CANDIDATE_HEAD
        ),
        "current_generation": 0,
        "requested_generation": 1,
        "current_as_of": "2026-11-02",
        "candidate_as_of": "2026-11-03",
        "pilot_manifest_sha256": PILOT,
        "candidate_snapshot_id": (
            "us_pilot_2026-11-03_8475_v1"
        ),
        "candidate_snapshot_sha256": SNAPSHOT,
        "proposal_sha256": PROPOSAL,
    }

    return {
        "current_path": current_path,
        "current": current,
        "current_sha": current_sha,
        "candidate_path": candidate_path,
        "candidate": candidate,
        "candidate_sha": candidate_sha,
        "request": request,
    }


def assess(case, **overrides):
    args = {
        "current_authority_state_path": (
            case["current_path"]
        ),
        "candidate_authority_state_path": (
            case["candidate_path"]
        ),
        "trusted_current_authority_state_sha256": (
            case["current_sha"]
        ),
        "expected_candidate_authority_state_sha256": (
            case["candidate_sha"]
        ),
        "protected_latest_authority_state_sha256": (
            case["current_sha"]
        ),
        "protected_latest_generation": 0,
        "reverified_authorization_request": (
            case["request"]
        ),
        "expected_current_head_checkpoint_sha256": HEAD,
        "expected_candidate_head_checkpoint_sha256": (
            CANDIDATE_HEAD
        ),
        "expected_pilot_manifest_sha256": PILOT,
    }

    args.update(overrides)

    return assess_protected_authority_transition(
        **args
    )


def change_candidate(case, **changes):
    candidate = {
        **case["candidate"],
        **changes,
    }

    case["candidate"] = candidate
    case["candidate_sha"] = write_json(
        case["candidate_path"],
        candidate,
    )


def test_valid_transition_stays_review_only(case):
    paths = (
        case["current_path"],
        case["candidate_path"],
    )

    before = {
        str(path): sha256(path)
        for path in paths
    }

    result = assess(case)

    assert result["status"] == (
        "AUTHORITY_STATE_TRANSITION_REVIEW_REQUIRED"
    )

    assert result["market"] == "US"
    assert result["mode"] == "PILOT_ONLY"
    assert result["production_approved"] is False

    assert result[
        "current_authority_state_sha256"
    ] == case["current_sha"]

    assert result[
        "candidate_authority_state_sha256"
    ] == case["candidate_sha"]

    assert result["current_generation"] == 0
    assert result["candidate_generation"] == 1

    assert result[
        "current_head_checkpoint_sha256"
    ] == HEAD

    assert result[
        "candidate_head_checkpoint_sha256"
    ] == CANDIDATE_HEAD

    assert result["current_as_of"] == "2026-11-02"
    assert result["candidate_as_of"] == "2026-11-03"

    assert result["pilot_manifest_sha256"] == PILOT

    assert result["evidence_request_sha256"] == (
        sha256_bytes(
            canonical_bytes(case["request"])
        )
    )

    assert "signature" not in result
    assert "authorized" not in result
    assert "authority_approved" not in result

    assert assess(case) == result

    assert {
        str(path): sha256(path)
        for path in paths
    } == before


def test_updated_protected_floor_blocks_stale_transition(case):
    # Simulate the external floor already advancing
    # to generation 1 / candidate state hash.
    #
    # The stale generation-0 current state must no
    # longer be a valid basis for another transition.
    with pytest.raises(ValueError):
        assess(
            case,
            protected_latest_authority_state_sha256=(
                case["candidate_sha"]
            ),
            protected_latest_generation=1,
        )


def test_protected_floor_generation_mismatch_rejected(case):
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


def test_wrong_current_state_pin_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            trusted_current_authority_state_sha256=(
                "0" * 64
            ),
        )


def test_wrong_candidate_state_pin_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            expected_candidate_authority_state_sha256=(
                "0" * 64
            ),
        )


def test_generation_jump_rejected(case):
    change_candidate(case, generation=2)

    with pytest.raises(ValueError):
        assess(case)


def test_candidate_generation_replay_rejected(case):
    change_candidate(case, generation=0)

    with pytest.raises(ValueError):
        assess(case)


def test_wrong_predecessor_state_sha_rejected(case):
    change_candidate(
        case,
        previous_authority_state_sha256="0" * 64,
    )

    with pytest.raises(ValueError):
        assess(case)


def test_wrong_candidate_head_rejected(case):
    change_candidate(
        case,
        head_checkpoint_sha256="f" * 64,
    )

    with pytest.raises(ValueError):
        assess(case)


def test_wrong_candidate_date_rejected(case):
    change_candidate(
        case,
        head_as_of="2026-11-04",
    )

    with pytest.raises(ValueError):
        assess(case)


def test_wrong_candidate_pilot_rejected(case):
    change_candidate(
        case,
        pilot_manifest_sha256="f" * 64,
    )

    with pytest.raises(ValueError):
        assess(case)


def test_unverified_request_status_rejected(case):
    modified = {
        **case["request"],
        "status": "AUTHORIZATION_REQUIRED",
    }

    with pytest.raises(ValueError):
        assess(
            case,
            reverified_authorization_request=modified,
        )


def test_boolean_requested_generation_rejected(case):
    modified = {
        **case["request"],
        "requested_generation": True,
    }

    with pytest.raises(ValueError):
        assess(
            case,
            reverified_authorization_request=modified,
        )


def test_injected_approval_request_rejected(case):
    modified = {
        **case["request"],
        "authority_approved": True,
    }

    with pytest.raises(ValueError):
        assess(
            case,
            reverified_authorization_request=modified,
        )


def test_candidate_production_claim_rejected(case):
    change_candidate(
        case,
        production_approved=True,
    )

    with pytest.raises(ValueError):
        assess(case)


def test_symlinked_candidate_state_rejected(case, tmp_path):
    link = tmp_path / "candidate_link.json"
    link.symlink_to(case["candidate_path"])

    with pytest.raises(
        (ValueError, FileNotFoundError)
    ):
        assess(
            case,
            candidate_authority_state_path=link,
        )


def test_duplicate_candidate_json_keys_rejected(case):
    raw = case["candidate_path"].read_bytes()

    assert b'"generation":1' in raw

    raw = raw.replace(
        b'"generation":1',
        b'"generation":1,"generation":1',
        1,
    )

    case["candidate_path"].write_bytes(raw)
    case["candidate_sha"] = sha256(
        case["candidate_path"]
    )

    with pytest.raises(ValueError):
        assess(case)


def test_missing_candidate_state_rejected(case, tmp_path):
    with pytest.raises(
        (ValueError, FileNotFoundError)
    ):
        assess(
            case,
            candidate_authority_state_path=(
                tmp_path / "missing_state.json"
            ),
        )


def test_wrong_current_head_pin_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            expected_current_head_checkpoint_sha256=(
                "0" * 64
            ),
        )


def test_wrong_pilot_manifest_pin_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            expected_pilot_manifest_sha256=(
                "0" * 64
            ),
        )
