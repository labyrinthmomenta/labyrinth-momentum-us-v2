"""Read-only preparation of an external atomic CAS intent.

This module validates a claimed authority transition
review against caller-supplied independent reference
values and produces a deterministic operation identity.

It does NOT:
- Authenticate the origin of the transition review.
- Independently reverify SQLite or checkpoint evidence.
- Authenticate the protected state reference.
- Execute a compare-and-swap operation.
- Update any authority state.
- Sign or authorize a transition.
- Provide durable replay or anti-rollback protection.
- Enable production or publication.

The resulting intent is NOT an authorization.
"""

import hashlib
import hmac

from src.data.trusted_head_authority import (
    MAX_GENERATION,
    _canonical_bytes,
    _check_date,
    _check_sha256,
)


REVIEW_FIELDS = frozenset({
    "status",
    "market",
    "mode",
    "production_approved",
    "current_authority_state_sha256",
    "candidate_authority_state_sha256",
    "current_generation",
    "candidate_generation",
    "current_head_checkpoint_sha256",
    "candidate_head_checkpoint_sha256",
    "current_as_of",
    "candidate_as_of",
    "pilot_manifest_sha256",
    "evidence_request_sha256",
})


def _check_generation(value, label):
    """Reject bool and out-of-range generation values."""

    if (
        type(value) is not int
        or not 0 <= value <= MAX_GENERATION
    ):
        raise ValueError(
            f"Invalid authority generation: {label}"
        )

    return value


def _same_sha256(left, right):
    return hmac.compare_digest(left, right)


def _sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def _validate_transition_review(review):
    """Validate exact structure, types and transition rules.

    This validation does not authenticate the review's
    source or prove that evidence was independently
    verified in an earlier stage.
    """

    if (
        type(review) is not dict
        or set(review) != REVIEW_FIELDS
    ):
        raise ValueError(
            "Invalid transition review schema"
        )

    if (
        review["status"]
        != "AUTHORITY_STATE_TRANSITION_REVIEW_REQUIRED"
        or review["market"] != "US"
        or review["mode"] != "PILOT_ONLY"
        or review["production_approved"] is not False
    ):
        raise ValueError(
            "Transition review safety policy rejected"
        )

    for field in (
        "current_authority_state_sha256",
        "candidate_authority_state_sha256",
        "current_head_checkpoint_sha256",
        "candidate_head_checkpoint_sha256",
        "pilot_manifest_sha256",
        "evidence_request_sha256",
    ):
        _check_sha256(review[field], field)

    current_generation = _check_generation(
        review["current_generation"],
        "current_generation",
    )

    candidate_generation = _check_generation(
        review["candidate_generation"],
        "candidate_generation",
    )

    if candidate_generation != current_generation + 1:
        raise ValueError(
            "CAS candidate generation must advance "
            "by exactly one"
        )

    current_date = _check_date(
        review["current_as_of"],
        "current_as_of",
    )

    candidate_date = _check_date(
        review["candidate_as_of"],
        "candidate_as_of",
    )

    if candidate_date <= current_date:
        raise ValueError(
            "CAS candidate checkpoint date "
            "must move forward"
        )

    if _same_sha256(
        review["current_authority_state_sha256"],
        review["candidate_authority_state_sha256"],
    ):
        raise ValueError(
            "CAS candidate cannot reuse "
            "the current authority state"
        )

    if _same_sha256(
        review["current_head_checkpoint_sha256"],
        review["candidate_head_checkpoint_sha256"],
    ):
        raise ValueError(
            "CAS candidate cannot reuse "
            "the current checkpoint head"
        )

    # The canonical representation is deterministic.
    # It is an identity, not a signature.
    try:
        raw = _canonical_bytes(review)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Invalid transition review serialization"
        ) from exc

    return raw


def prepare_authority_cas_intent(
    *,
    transition_review,
    trusted_transition_review_sha256,
    protected_latest_authority_state_sha256,
    protected_latest_generation,
    expected_candidate_authority_state_sha256,
    expected_candidate_generation,
    expected_evidence_request_sha256,
) -> dict:
    """Prepare a deterministic external CAS intent.

    The caller must supply independently trusted:
    - The review SHA-256.
    - The latest protected authority state SHA-256.
    - The latest protected generation.
    - The expected candidate state and generation.
    - The expected evidence request SHA-256.

    This function only compares the supplied values.

    It cannot determine whether the protected floor
    has changed since the caller obtained it.

    The actual authority must independently verify
    the evidence and atomically check the current
    protected state before committing anything.
    """

    review_sha = _check_sha256(
        trusted_transition_review_sha256,
        "trusted_transition_review_sha256",
    )

    protected_state_sha = _check_sha256(
        protected_latest_authority_state_sha256,
        "protected_latest_authority_state_sha256",
    )

    protected_generation = _check_generation(
        protected_latest_generation,
        "protected_latest_generation",
    )

    candidate_state_sha = _check_sha256(
        expected_candidate_authority_state_sha256,
        "expected_candidate_authority_state_sha256",
    )

    candidate_generation = _check_generation(
        expected_candidate_generation,
        "expected_candidate_generation",
    )

    evidence_sha = _check_sha256(
        expected_evidence_request_sha256,
        "expected_evidence_request_sha256",
    )

    # Stage 1: validate the entire claimed review.
    review_bytes = _validate_transition_review(
        transition_review
    )

    actual_review_sha = _sha256_bytes(
        review_bytes
    )

    if not _same_sha256(
        actual_review_sha,
        review_sha,
    ):
        raise ValueError(
            "Independent transition review "
            "SHA-256 mismatch"
        )

    # Stage 2: bind the CAS preconditions to the
    # caller-provided latest protected state.
    if not _same_sha256(
        transition_review[
            "current_authority_state_sha256"
        ],
        protected_state_sha,
    ):
        raise ValueError(
            "Protected latest authority state "
            "does not match transition review"
        )

    if (
        transition_review["current_generation"]
        != protected_generation
    ):
        raise ValueError(
            "Protected latest generation "
            "does not match transition review"
        )

    # Stage 3: bind the candidate state and
    # evidence identity to independent inputs.
    if not _same_sha256(
        transition_review[
            "candidate_authority_state_sha256"
        ],
        candidate_state_sha,
    ):
        raise ValueError(
            "Candidate authority state pin mismatch"
        )

    if (
        transition_review["candidate_generation"]
        != candidate_generation
    ):
        raise ValueError(
            "Candidate authority generation "
            "pin mismatch"
        )

    if not _same_sha256(
        transition_review[
            "evidence_request_sha256"
        ],
        evidence_sha,
    ):
        raise ValueError(
            "Evidence request pin mismatch"
        )

    if candidate_generation != (
        protected_generation + 1
    ):
        raise ValueError(
            "CAS generation preconditions "
            "must advance by exactly one"
        )

    if _same_sha256(
        protected_state_sha,
        candidate_state_sha,
    ):
        raise ValueError(
            "CAS cannot replace a state with itself"
        )

    # Stage 4: construct the exact operation payload.
    #
    # The operation ID includes both the expected
    # current state and the candidate identity.
    # Two competing candidates have different IDs,
    # even if they share the same precondition.
    operation_payload = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "expected_authority_state_sha256": (
            protected_state_sha
        ),
        "expected_generation": (
            protected_generation
        ),
        "candidate_authority_state_sha256": (
            candidate_state_sha
        ),
        "candidate_generation": (
            candidate_generation
        ),
        "evidence_request_sha256": (
            evidence_sha
        ),
        "transition_review_sha256": (
            review_sha
        ),
    }

    operation_id = _sha256_bytes(
        _canonical_bytes(operation_payload)
    )

    # The intent is returned without any side effect.
    #
    # An external authority still has to:
    # 1. Authenticate and reverify the evidence.
    # 2. Re-read its own protected current state.
    # 3. Check SHA + generation atomically.
    # 4. Persist only an authorized transition.
    # 5. Reject stale/replayed operations.
    #
    # None of those authority actions occurs here.
    return {
        "status": (
            "EXTERNAL_ATOMIC_CAS_REQUIRED_NOT_EXECUTED"
        ),
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "expected_authority_state_sha256": (
            protected_state_sha
        ),
        "expected_generation": (
            protected_generation
        ),
        "candidate_authority_state_sha256": (
            candidate_state_sha
        ),
        "candidate_generation": (
            candidate_generation
        ),
        "current_head_checkpoint_sha256": (
            transition_review[
                "current_head_checkpoint_sha256"
            ]
        ),
        "candidate_head_checkpoint_sha256": (
            transition_review[
                "candidate_head_checkpoint_sha256"
            ]
        ),
        "pilot_manifest_sha256": (
            transition_review[
                "pilot_manifest_sha256"
            ]
        ),
        "evidence_request_sha256": (
            evidence_sha
        ),
        "transition_review_sha256": (
            review_sha
        ),
        "operation_id": operation_id,
    }
