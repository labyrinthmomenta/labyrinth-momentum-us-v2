"""A6c.32: read-only atomic CAS intent contract.

The intent builder MUST NOT execute an authority update.

The simulated protected store below is a test double,
not durable protected storage or an authorization service.

A locally supplied review hash does not authenticate
the review's provenance.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from threading import Lock

import pytest

from src.data.authority_cas_intent import (
    prepare_authority_cas_intent,
)


CURRENT_STATE = "a" * 64
CANDIDATE_STATE = "b" * 64

CURRENT_HEAD = "c" * 64
CANDIDATE_HEAD = "d" * 64

PILOT_SHA = "e" * 64
EVIDENCE_SHA = "f" * 64


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


def digest(value):
    return hashlib.sha256(
        canonical_bytes(value)
    ).hexdigest()


@pytest.fixture
def case():
    review = {
        "status": (
            "AUTHORITY_STATE_TRANSITION_REVIEW_REQUIRED"
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
        "current_as_of": "2026-11-02",
        "candidate_as_of": "2026-11-03",
        "pilot_manifest_sha256": PILOT_SHA,
        "evidence_request_sha256": EVIDENCE_SHA,
    }

    return {
        "review": review,
        "review_sha": digest(review),
    }


def prepare(case, review=None, **overrides):
    selected = (
        case["review"]
        if review is None
        else review
    )

    arguments = {
        "transition_review": selected,
        "trusted_transition_review_sha256": (
            digest(selected)
        ),
        "protected_latest_authority_state_sha256": (
            CURRENT_STATE
        ),
        "protected_latest_generation": 0,
        "expected_candidate_authority_state_sha256": (
            CANDIDATE_STATE
        ),
        "expected_candidate_generation": 1,
        "expected_evidence_request_sha256": (
            EVIDENCE_SHA
        ),
    }

    arguments.update(overrides)

    return prepare_authority_cas_intent(
        **arguments
    )


def modified(case, **changes):
    return {
        **case["review"],
        **changes,
    }


class SimulatedProtectedCAS:
    """Atomic test double; NOT an external authority."""

    def __init__(self, state_sha, generation):
        self.state_sha = state_sha
        self.generation = generation
        self.lock = Lock()

    def apply(self, intent):
        with self.lock:
            if (
                self.state_sha
                != intent["expected_authority_state_sha256"]
                or self.generation
                != intent["expected_generation"]
            ):
                return "CAS_CONFLICT"

            self.state_sha = intent[
                "candidate_authority_state_sha256"
            ]

            self.generation = intent[
                "candidate_generation"
            ]

            return "SIMULATED_COMMIT"


def test_valid_intent_is_deterministic_and_not_executed(case):
    before = canonical_bytes(case["review"])

    result = prepare(case)

    assert result["status"] == (
        "EXTERNAL_ATOMIC_CAS_REQUIRED_NOT_EXECUTED"
    )
    assert result["market"] == "US"
    assert result["mode"] == "PILOT_ONLY"
    assert result["production_approved"] is False

    assert result[
        "expected_authority_state_sha256"
    ] == CURRENT_STATE

    assert result["expected_generation"] == 0

    assert result[
        "candidate_authority_state_sha256"
    ] == CANDIDATE_STATE

    assert result["candidate_generation"] == 1

    assert result[
        "current_head_checkpoint_sha256"
    ] == CURRENT_HEAD

    assert result[
        "candidate_head_checkpoint_sha256"
    ] == CANDIDATE_HEAD

    assert result[
        "pilot_manifest_sha256"
    ] == PILOT_SHA

    assert result[
        "evidence_request_sha256"
    ] == EVIDENCE_SHA

    assert result[
        "transition_review_sha256"
    ] == case["review_sha"]

    operation_payload = {
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
        "transition_review_sha256": (
            case["review_sha"]
        ),
    }

    assert result["operation_id"] == digest(
        operation_payload
    )

    assert prepare(case) == result
    assert canonical_bytes(case["review"]) == before

    for forbidden in (
        "authorized",
        "authority_approved",
        "signature",
        "committed",
        "production_enabled",
    ):
        assert forbidden not in result


def test_wrong_review_pin_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            trusted_transition_review_sha256=(
                "0" * 64
            ),
        )


def test_stale_protected_sha_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            protected_latest_authority_state_sha256=(
                "0" * 64
            ),
        )


def test_stale_protected_generation_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            protected_latest_generation=1,
        )


def test_boolean_protected_generation_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            protected_latest_generation=False,
        )


def test_wrong_candidate_pin_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            expected_candidate_authority_state_sha256=(
                "0" * 64
            ),
        )


def test_wrong_candidate_generation_pin_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            expected_candidate_generation=2,
        )


def test_boolean_candidate_generation_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            expected_candidate_generation=True,
        )


def test_wrong_evidence_request_pin_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            expected_evidence_request_sha256=(
                "0" * 64
            ),
        )


def test_added_approval_field_rejected(case):
    review = modified(
        case,
        authority_approved=True,
    )

    with pytest.raises(ValueError):
        prepare(case, review=review)


def test_missing_review_field_rejected(case):
    review = dict(case["review"])
    del review["pilot_manifest_sha256"]

    with pytest.raises(ValueError):
        prepare(case, review=review)


def test_unreviewed_status_rejected(case):
    review = modified(
        case,
        status="EVIDENCE_REVERIFIED_AUTHORIZATION_REQUIRED",
    )

    with pytest.raises(ValueError):
        prepare(case, review=review)


def test_production_claim_rejected(case):
    review = modified(
        case,
        production_approved=True,
    )

    with pytest.raises(ValueError):
        prepare(case, review=review)


def test_boolean_review_generation_rejected(case):
    review = modified(
        case,
        current_generation=False,
    )

    with pytest.raises(ValueError):
        prepare(case, review=review)


def test_generation_jump_rejected(case):
    review = modified(
        case,
        candidate_generation=2,
    )

    with pytest.raises(ValueError):
        prepare(
            case,
            review=review,
            expected_candidate_generation=2,
        )


def test_generation_replay_rejected(case):
    review = modified(
        case,
        candidate_generation=0,
    )

    with pytest.raises(ValueError):
        prepare(
            case,
            review=review,
            expected_candidate_generation=0,
        )


def test_date_rollback_rejected(case):
    review = modified(
        case,
        candidate_as_of="2026-11-02",
    )

    with pytest.raises(ValueError):
        prepare(case, review=review)


def test_noncanonical_date_rejected(case):
    review = modified(
        case,
        candidate_as_of="2026-11-3",
    )

    with pytest.raises(ValueError):
        prepare(case, review=review)


def test_checkpoint_head_reuse_rejected(case):
    review = modified(
        case,
        candidate_head_checkpoint_sha256=(
            CURRENT_HEAD
        ),
    )

    with pytest.raises(ValueError):
        prepare(case, review=review)


def test_authority_state_reuse_rejected(case):
    review = modified(
        case,
        candidate_authority_state_sha256=(
            CURRENT_STATE
        ),
    )

    with pytest.raises(ValueError):
        prepare(
            case,
            review=review,
            expected_candidate_authority_state_sha256=(
                CURRENT_STATE
            ),
        )


def test_invalid_review_hash_field_rejected(case):
    review = modified(
        case,
        candidate_head_checkpoint_sha256=(
            "not-a-sha256"
        ),
    )

    with pytest.raises(ValueError):
        prepare(case, review=review)


def test_forged_review_is_not_authorization(case):
    # Deliberately forged evidence identity.
    # Self-consistent caller-provided pins cannot
    # prove that the review was really produced
    # by the independent verification pipeline.
    forged_evidence = "9" * 64

    review = modified(
        case,
        evidence_request_sha256=forged_evidence,
    )

    result = prepare(
        case,
        review=review,
        expected_evidence_request_sha256=(
            forged_evidence
        ),
    )

    assert result["status"] == (
        "EXTERNAL_ATOMIC_CAS_REQUIRED_NOT_EXECUTED"
    )

    assert result[
        "evidence_request_sha256"
    ] == forged_evidence

    assert result["production_approved"] is False

    assert "authorized" not in result
    assert "signature" not in result
    assert "committed" not in result


def test_replay_simulation_rejected_after_first_commit(case):
    intent = prepare(case)

    store = SimulatedProtectedCAS(
        CURRENT_STATE,
        0,
    )

    first = store.apply(intent)
    replay = store.apply(intent)

    assert first == "SIMULATED_COMMIT"
    assert replay == "CAS_CONFLICT"

    assert store.state_sha == CANDIDATE_STATE
    assert store.generation == 1

    # Intent preparation did not mutate the store.
    assert prepare(case) == intent


def test_competing_candidate_simulation_only_one_wins(case):
    first_intent = prepare(case)

    second_state = "8" * 64
    second_head = "7" * 64

    second_review = modified(
        case,
        candidate_authority_state_sha256=(
            second_state
        ),
        candidate_head_checkpoint_sha256=(
            second_head
        ),
    )

    second_intent = prepare(
        case,
        review=second_review,
        expected_candidate_authority_state_sha256=(
            second_state
        ),
    )

    assert (
        first_intent["operation_id"]
        != second_intent["operation_id"]
    )

    assert first_intent[
        "expected_authority_state_sha256"
    ] == second_intent[
        "expected_authority_state_sha256"
    ]

    store = SimulatedProtectedCAS(
        CURRENT_STATE,
        0,
    )

    # The lock belongs to the TEST DOUBLE.
    # The production module performs no atomic write.
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                store.apply,
                (first_intent, second_intent),
            )
        )

    assert sorted(outcomes) == [
        "CAS_CONFLICT",
        "SIMULATED_COMMIT",
    ]

    assert store.generation == 1
    assert store.state_sha in {
        CANDIDATE_STATE,
        second_state,
    }
