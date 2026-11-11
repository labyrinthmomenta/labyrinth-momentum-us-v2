"""A6c.34: protected authority decision-request contract.

Tests validate a deterministic, untrusted request
envelope. No actual authority decision is issued.

All trust pins and UTC timestamps are caller-provided.
Real external authentication, clock trust, replay
protection, and atomic CAS are outside this module.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from threading import Lock

import pytest

from src.data.protected_authority_decision_request import (
    prepare_protected_authority_decision_request,
)


CURRENT_STATE = "a" * 64
CANDIDATE_STATE = "b" * 64
CURRENT_HEAD = "c" * 64
CANDIDATE_HEAD = "d" * 64
PILOT_SHA = "e" * 64
EVIDENCE_SHA = "f" * 64
REVIEW_SHA = "1" * 64

NONCE = "0123456789abcdef0123456789abcdef"

ISSUED_AT = "2026-11-10T18:00:00Z"
EXPIRES_AT = "2026-11-10T18:05:00Z"
CHECKED_AT = "2026-11-10T18:01:00Z"

STATUS = (
    "EXTERNAL_AUTHORITY_DECISION_REQUIRED_NOT_GRANTED"
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


def operation_payload():
    return {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "expected_authority_state_sha256": (
            CURRENT_STATE
        ),
        "expected_generation": 0,
        "candidate_authority_state_sha256": (
            CANDIDATE_STATE
        ),
        "candidate_generation": 1,
        "evidence_request_sha256": EVIDENCE_SHA,
        "transition_review_sha256": REVIEW_SHA,
    }


@pytest.fixture
def case():
    operation_id = digest(
        operation_payload()
    )

    cas = {
        "status": (
            "EXTERNAL_ATOMIC_CAS_REQUIRED_NOT_EXECUTED"
        ),
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "expected_authority_state_sha256": (
            CURRENT_STATE
        ),
        "expected_generation": 0,
        "candidate_authority_state_sha256": (
            CANDIDATE_STATE
        ),
        "candidate_generation": 1,
        "current_head_checkpoint_sha256": (
            CURRENT_HEAD
        ),
        "candidate_head_checkpoint_sha256": (
            CANDIDATE_HEAD
        ),
        "pilot_manifest_sha256": PILOT_SHA,
        "evidence_request_sha256": EVIDENCE_SHA,
        "transition_review_sha256": REVIEW_SHA,
        "operation_id": operation_id,
    }

    boundary = {
        "status": (
            "EVIDENCE_BOUND_EXTERNAL_CAS_REQUIRED_NOT_EXECUTED"
        ),
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "current_authority_state_sha256": (
            CURRENT_STATE
        ),
        "candidate_authority_state_sha256": (
            CANDIDATE_STATE
        ),
        "current_generation": 0,
        "candidate_generation": 1,
        "current_head_checkpoint_sha256": (
            CURRENT_HEAD
        ),
        "candidate_head_checkpoint_sha256": (
            CANDIDATE_HEAD
        ),
        "pilot_manifest_sha256": PILOT_SHA,
        "evidence_request_sha256": EVIDENCE_SHA,
        "transition_review_sha256": REVIEW_SHA,
        "operation_id": operation_id,
        "cas_intent_sha256": digest(cas),
    }

    args = {
        "execution_boundary_result": boundary,
        "cas_intent": cas,
        "trusted_execution_boundary_sha256": (
            digest(boundary)
        ),
        "trusted_cas_intent_sha256": digest(cas),
        "expected_operation_id": operation_id,
        "protected_latest_authority_state_sha256": (
            CURRENT_STATE
        ),
        "protected_latest_generation": 0,
        "nonce": NONCE,
        "issued_at": ISSUED_AT,
        "expires_at": EXPIRES_AT,
        "checked_at": CHECKED_AT,
    }

    return {
        "args": args,
        "boundary": boundary,
        "cas": cas,
        "operation_id": operation_id,
    }


def prepare(case, **changes):
    return prepare_protected_authority_decision_request(
        **{
            **case["args"],
            **changes,
        }
    )


def reseal(case, cas_changes=None, boundary_changes=None):
    """Rehash self-consistent forged inputs.

    Rehashing is NOT authentication.
    """
    cas = {
        **case["cas"],
        **(cas_changes or {}),
    }

    boundary = {
        **case["boundary"],
        **(boundary_changes or {}),
        "cas_intent_sha256": digest(cas),
    }

    return {
        **case["args"],
        "cas_intent": cas,
        "execution_boundary_result": boundary,
        "trusted_cas_intent_sha256": digest(cas),
        "trusted_execution_boundary_sha256": (
            digest(boundary)
        ),
    }


class SimulatedRequestLedger:
    """Test-only replay detector; no authority decision."""

    def __init__(self):
        self.lock = Lock()
        self.seen = set()

    def register(self, request):
        with self.lock:
            identifier = request["decision_request_id"]

            if identifier in self.seen:
                return "SIMULATED_REPLAY_CONFLICT"

            self.seen.add(identifier)
            return "SIMULATED_REQUEST_RECORDED"


def test_valid_request_deterministic_and_not_granted(case):
    before_boundary = canonical(case["boundary"])
    before_cas = canonical(case["cas"])

    result = prepare(case)

    assert result["status"] == STATUS
    assert result["schema_version"] == 1
    assert result["market"] == "US"
    assert result["mode"] == "PILOT_ONLY"
    assert result["production_approved"] is False

    assert result["operation_id"] == (
        case["operation_id"]
    )

    assert result[
        "expected_authority_state_sha256"
    ] == CURRENT_STATE

    assert result["expected_generation"] == 0

    assert result[
        "candidate_authority_state_sha256"
    ] == CANDIDATE_STATE

    assert result["candidate_generation"] == 1

    assert result[
        "evidence_request_sha256"
    ] == EVIDENCE_SHA

    assert result[
        "transition_review_sha256"
    ] == REVIEW_SHA

    assert result["cas_intent_sha256"] == (
        digest(case["cas"])
    )

    assert result["execution_boundary_sha256"] == (
        digest(case["boundary"])
    )

    assert result["nonce"] == NONCE
    assert result["issued_at"] == ISSUED_AT
    assert result["expires_at"] == EXPIRES_AT

    identity_payload = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "operation_id": case["operation_id"],
        "expected_authority_state_sha256": (
            CURRENT_STATE
        ),
        "expected_generation": 0,
        "candidate_authority_state_sha256": (
            CANDIDATE_STATE
        ),
        "candidate_generation": 1,
        "evidence_request_sha256": EVIDENCE_SHA,
        "transition_review_sha256": REVIEW_SHA,
        "cas_intent_sha256": digest(case["cas"]),
        "execution_boundary_sha256": (
            digest(case["boundary"])
        ),
        "nonce": NONCE,
        "issued_at": ISSUED_AT,
        "expires_at": EXPIRES_AT,
    }

    assert result["decision_request_id"] == (
        digest(identity_payload)
    )

    assert prepare(case) == result

    assert canonical(case["boundary"]) == before_boundary
    assert canonical(case["cas"]) == before_cas

    for forbidden in (
        "authorized",
        "approved",
        "authority_approved",
        "signature",
        "committed",
        "production_enabled",
    ):
        assert forbidden not in result


def test_wrong_boundary_pin_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            trusted_execution_boundary_sha256=(
                "0" * 64
            ),
        )


def test_wrong_cas_pin_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            trusted_cas_intent_sha256="0" * 64,
        )


def test_wrong_operation_pin_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            expected_operation_id="0" * 64,
        )


def test_boundary_cas_digest_mismatch_rejected(case):
    args = reseal(
        case,
        boundary_changes={
            "cas_intent_sha256": "9" * 64,
        },
    )

    # Explicitly override the reseal helper's
    # computed CAS digest to create the mismatch.
    altered_boundary = {
        **args["execution_boundary_result"],
        "cas_intent_sha256": "9" * 64,
    }

    args["execution_boundary_result"] = (
        altered_boundary
    )

    args["trusted_execution_boundary_sha256"] = (
        digest(altered_boundary)
    )

    with pytest.raises(ValueError):
        prepare_protected_authority_decision_request(
            **args
        )


def test_rehashed_forged_operation_id_rejected(case):
    forged_id = "9" * 64

    args = reseal(
        case,
        cas_changes={"operation_id": forged_id},
        boundary_changes={"operation_id": forged_id},
    )

    args["expected_operation_id"] = forged_id

    with pytest.raises(ValueError):
        prepare_protected_authority_decision_request(
            **args
        )


def test_rehashed_current_state_mismatch_rejected(case):
    args = reseal(
        case,
        cas_changes={
            "expected_authority_state_sha256": (
                "8" * 64
            )
        },
    )

    with pytest.raises(ValueError):
        prepare_protected_authority_decision_request(
            **args
        )


def test_rehashed_candidate_generation_mismatch_rejected(case):
    args = reseal(
        case,
        cas_changes={"candidate_generation": 2},
    )

    with pytest.raises(ValueError):
        prepare_protected_authority_decision_request(
            **args
        )


def test_injected_boundary_approval_rejected(case):
    args = reseal(
        case,
        boundary_changes={
            "authority_approved": True,
        },
    )

    with pytest.raises(ValueError):
        prepare_protected_authority_decision_request(
            **args
        )


def test_injected_cas_approval_rejected(case):
    args = reseal(
        case,
        cas_changes={
            "signature": "FAKE_SIGNATURE",
        },
    )

    with pytest.raises(ValueError):
        prepare_protected_authority_decision_request(
            **args
        )


def test_invalid_boundary_status_rejected(case):
    args = reseal(
        case,
        boundary_changes={
            "status": "AUTHORIZED",
        },
    )

    with pytest.raises(ValueError):
        prepare_protected_authority_decision_request(
            **args
        )


def test_invalid_cas_status_rejected(case):
    args = reseal(
        case,
        cas_changes={
            "status": "CAS_COMMITTED",
        },
    )

    with pytest.raises(ValueError):
        prepare_protected_authority_decision_request(
            **args
        )


def test_boolean_boundary_generation_rejected(case):
    args = reseal(
        case,
        boundary_changes={
            "current_generation": False,
        },
    )

    with pytest.raises(ValueError):
        prepare_protected_authority_decision_request(
            **args
        )


def test_boolean_cas_generation_rejected(case):
    args = reseal(
        case,
        cas_changes={"expected_generation": False},
    )

    with pytest.raises(ValueError):
        prepare_protected_authority_decision_request(
            **args
        )


def test_generation_jump_rejected(case):
    args = reseal(
        case,
        cas_changes={"candidate_generation": 2},
        boundary_changes={"candidate_generation": 2},
    )

    with pytest.raises(ValueError):
        prepare_protected_authority_decision_request(
            **args
        )


def test_checkpoint_head_binding_mismatch_rejected(case):
    args = reseal(
        case,
        cas_changes={
            "candidate_head_checkpoint_sha256": (
                "7" * 64
            )
        },
    )

    with pytest.raises(ValueError):
        prepare_protected_authority_decision_request(
            **args
        )


def test_malformed_nonce_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            nonce="ABCDEF",
        )


def test_zero_nonce_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            nonce="0" * 32,
        )


def test_expired_request_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            checked_at="2026-11-10T18:05:00Z",
        )


def test_future_issued_request_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            checked_at="2026-11-10T17:59:59Z",
        )


def test_excessive_validity_window_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            expires_at="2026-11-10T18:05:01Z",
        )


def test_noncanonical_timestamp_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            issued_at="2026-11-10T18:00:00+00:00",
        )


def test_nonce_changes_request_identity(case):
    first = prepare(case)

    alternate = prepare(
        case,
        nonce="abcdef0123456789abcdef0123456789",
    )

    assert first["status"] == STATUS
    assert alternate["status"] == STATUS

    assert first["operation_id"] == (
        alternate["operation_id"]
    )

    assert first["decision_request_id"] != (
        alternate["decision_request_id"]
    )

    # The same request is reproducible.
    # Determinism is NOT replay prevention.
    assert prepare(case) == first


def test_simulated_single_use_request_ledger(case):
    request = prepare(case)

    ledger = SimulatedRequestLedger()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                ledger.register,
                (request, request),
            )
        )

    assert sorted(outcomes) == [
        "SIMULATED_REPLAY_CONFLICT",
        "SIMULATED_REQUEST_RECORDED",
    ]

    assert len(ledger.seen) == 1

    # The actual function has no durable ledger.
    # No decision, authorization or CAS occurred.
    assert prepare(case) == request
    assert request["status"] == STATUS
