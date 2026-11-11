"""Read-only, local authority-verification preconditions.

Reconstructs a claimed decision request using actual
checkpoint and SQLite evidence through the existing
authority execution-boundary assessment.

Separately checks caller-provided references for:
- Current authority-state identity and generation.
- Current checkpoint-head identity.
- Pilot manifest identity.
- Decision-request identity.
- Request validity at a supplied UTC check time.

Security limitations:
- Caller-provided references are NOT authenticated.
- The check time is NOT an independently trusted clock.
- The protected authority floor is NOT read from an
  independently controlled durable authority.
- Nonce uniqueness is NOT checked against a durable
  registry.
- Double reverification is NOT an atomic transaction.
- No authorization, signature, real CAS or mutation
  is performed.
- Production and publication are NOT enabled.

A successful result is LOCAL PRECHECK ONLY.
"""

import hashlib
import hmac
import json

from src.data.authority_execution_boundary import (
    assess_authority_execution_boundary,
)

from src.data.protected_authority_decision_request import (
    prepare_protected_authority_decision_request,
    _check_generation,
    _check_sha256,
    _check_utc,
    _check_validity,
)


STATUS = (
    "LOCAL_PRECHECK_PASSED_EXTERNAL_AUTHORITY_REQUIRED"
)

CONTEXT_FIELDS = frozenset({
    "current_checkpoint_path",
    "current_snapshot_dir",
    "candidate_checkpoint_path",
    "candidate_snapshot_dir",
    "trusted_current_head_sha256",
    "expected_candidate_sha256",
    "expected_pilot_manifest_sha256",
    "required_symbols",
    "min_candidate_as_of",
    "expected_current_predecessor_sha256",
    "current_authority_state_path",
    "candidate_authority_state_path",
    "trusted_current_authority_state_sha256",
    "expected_candidate_authority_state_sha256",
    "protected_latest_authority_state_sha256",
    "protected_latest_generation",
    "authorization_request",
    "transition_review",
    "cas_intent",
})

DECISION_FIELDS = frozenset({
    "status",
    "schema_version",
    "market",
    "mode",
    "production_approved",
    "operation_id",
    "expected_authority_state_sha256",
    "expected_generation",
    "candidate_authority_state_sha256",
    "candidate_generation",
    "evidence_request_sha256",
    "transition_review_sha256",
    "cas_intent_sha256",
    "execution_boundary_sha256",
    "nonce",
    "issued_at",
    "expires_at",
    "decision_request_id",
})


def _canonical_bytes(value, label):
    """Deterministic, type-sensitive dictionary identity."""

    if type(value) is not dict:
        raise ValueError(
            f"{label} must be a plain dictionary"
        )

    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ) + "\n"
        ).encode("utf-8")

    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid {label} serialization"
        ) from exc


def _digest(value, label):
    return hashlib.sha256(
        _canonical_bytes(value, label)
    ).hexdigest()


def _require_identical(supplied, expected, label):
    """Reject extra, missing, changed or mistyped values."""

    supplied_raw = _canonical_bytes(
        supplied,
        label,
    )

    expected_raw = _canonical_bytes(
        expected,
        f"reconstructed {label}",
    )

    if not hmac.compare_digest(
        supplied_raw,
        expected_raw,
    ):
        raise ValueError(
            f"{label} differs from independently "
            "reconstructed evidence"
        )


def _require_sha_match(left, right, label):
    """Check canonical SHA-256 values before comparing."""

    checked_left = _check_sha256(
        left,
        f"{label}: left",
    )

    checked_right = _check_sha256(
        right,
        f"{label}: right",
    )

    if not hmac.compare_digest(
        checked_left,
        checked_right,
    ):
        raise ValueError(
            f"{label} SHA-256 mismatch"
        )


def _check_context(context):
    """Require the exact supported execution contract."""

    if (
        type(context) is not dict
        or set(context) != CONTEXT_FIELDS
    ):
        raise ValueError(
            "Invalid execution context schema"
        )

    return context


def _check_decision(decision):
    """Reject undocumented authority or approval fields."""

    if (
        type(decision) is not dict
        or set(decision) != DECISION_FIELDS
    ):
        raise ValueError(
            "Invalid decision request schema"
        )

    if (
        decision["status"] != (
            "EXTERNAL_AUTHORITY_DECISION_REQUIRED_NOT_GRANTED"
        )
        or decision["schema_version"] != 1
        or type(decision["schema_version"]) is not int
        or decision["market"] != "US"
        or decision["mode"] != "PILOT_ONLY"
        or decision["production_approved"] is not False
    ):
        raise ValueError(
            "Decision request safety policy rejected"
        )

    _check_sha256(
        decision["decision_request_id"],
        "decision_request_id",
    )

    _check_sha256(
        decision["operation_id"],
        "operation_id",
    )

    _check_generation(
        decision["expected_generation"],
        "decision expected_generation",
    )

    _check_generation(
        decision["candidate_generation"],
        "decision candidate_generation",
    )

    if (
        decision["candidate_generation"]
        != decision["expected_generation"] + 1
    ):
        raise ValueError(
            "Decision generation must advance by one"
        )

    return decision


def _reconstruct_boundary(context):
    """Recheck actual file-backed evidence and CAS binding."""

    result = assess_authority_execution_boundary(
        **context
    )

    if (
        result["status"] != (
            "EVIDENCE_BOUND_EXTERNAL_CAS_REQUIRED_NOT_EXECUTED"
        )
        or result["market"] != "US"
        or result["mode"] != "PILOT_ONLY"
        or result["production_approved"] is not False
    ):
        raise ValueError(
            "Execution boundary did not pass "
            "the required safety conditions"
        )

    return result


def _reconstruct_decision(
    *,
    boundary,
    context,
    supplied_decision,
    reference_state_sha,
    reference_generation,
    reference_checked_at,
):
    """Reconstruct the decision using freshly bound data.

    Nonce and issuance/expiry timestamps are taken from
    the supplied request, then validated and bound.
    They are not trusted authority observations.
    """

    cas = context["cas_intent"]

    return prepare_protected_authority_decision_request(
        execution_boundary_result=boundary,
        cas_intent=cas,
        trusted_execution_boundary_sha256=(
            _digest(
                boundary,
                "reconstructed execution boundary",
            )
        ),
        trusted_cas_intent_sha256=(
            _digest(
                cas,
                "reconstructed CAS intent",
            )
        ),
        expected_operation_id=(
            boundary["operation_id"]
        ),
        protected_latest_authority_state_sha256=(
            reference_state_sha
        ),
        protected_latest_generation=(
            reference_generation
        ),
        nonce=supplied_decision["nonce"],
        issued_at=supplied_decision["issued_at"],
        expires_at=supplied_decision["expires_at"],
        checked_at=reference_checked_at,
    )


def assess_independent_authority_preconditions(
    *,
    execution_context,
    decision_request,
    expected_decision_request_sha256,
    reference_authority_state_sha256,
    reference_generation,
    reference_current_head_checkpoint_sha256,
    reference_pilot_manifest_sha256,
    reference_checked_at,
) -> dict:
    """Evaluate local preconditions without authorization.

    Independent references MUST be supplied by the
    caller. The function validates consistency, not
    the authenticity or freshness of those references.

    Any real authority must independently authenticate
    the protected floor, time and nonce before atomically
    considering a transition.
    """

    # Stage 1: reject unsupported inputs and types.
    context = _check_context(
        execution_context
    )

    decision = _check_decision(
        decision_request
    )

    decision_pin = _check_sha256(
        expected_decision_request_sha256,
        "expected_decision_request_sha256",
    )

    reference_state = _check_sha256(
        reference_authority_state_sha256,
        "reference_authority_state_sha256",
    )

    reference_gen = _check_generation(
        reference_generation,
        "reference_generation",
    )

    reference_head = _check_sha256(
        reference_current_head_checkpoint_sha256,
        "reference_current_head_checkpoint_sha256",
    )

    reference_pilot = _check_sha256(
        reference_pilot_manifest_sha256,
        "reference_pilot_manifest_sha256",
    )

    _check_utc(
        reference_checked_at,
        "reference_checked_at",
    )

    # Stage 2: full deterministic request identity.
    calculated_decision_sha = _digest(
        decision,
        "supplied decision request",
    )

    _require_sha_match(
        calculated_decision_sha,
        decision_pin,
        "Decision request",
    )

    # This checks the caller's supplied time only.
    # It is NOT a trusted or independently obtained UTC.
    _check_validity(
        nonce=decision["nonce"],
        issued_at=decision["issued_at"],
        expires_at=decision["expires_at"],
        checked_at=reference_checked_at,
    )

    # Stage 3: bind all supplied protected references
    # before expensive file-backed reverification.
    _require_sha_match(
        context[
            "trusted_current_authority_state_sha256"
        ],
        reference_state,
        "Current authority state",
    )

    _require_sha_match(
        context[
            "protected_latest_authority_state_sha256"
        ],
        reference_state,
        "Protected latest state",
    )

    context_generation = _check_generation(
        context["protected_latest_generation"],
        "context protected_latest_generation",
    )

    if context_generation != reference_gen:
        raise ValueError(
            "Protected latest generation mismatch"
        )

    if decision["expected_generation"] != reference_gen:
        raise ValueError(
            "Decision expected generation mismatch"
        )

    _require_sha_match(
        decision[
            "expected_authority_state_sha256"
        ],
        reference_state,
        "Decision expected authority state",
    )

    _require_sha_match(
        context["trusted_current_head_sha256"],
        reference_head,
        "Current checkpoint head",
    )

    _require_sha_match(
        context["expected_pilot_manifest_sha256"],
        reference_pilot,
        "Pilot manifest",
    )

    # Stage 4: independently redo the entire SQLite,
    # checkpoint, authority-state, review and CAS chain.
    first_boundary = _reconstruct_boundary(
        context
    )

    _require_sha_match(
        first_boundary[
            "current_authority_state_sha256"
        ],
        reference_state,
        "Reconstructed authority state",
    )

    if first_boundary["current_generation"] != (
        reference_gen
    ):
        raise ValueError(
            "Reconstructed generation mismatch"
        )

    _require_sha_match(
        first_boundary[
            "current_head_checkpoint_sha256"
        ],
        reference_head,
        "Reconstructed checkpoint head",
    )

    _require_sha_match(
        first_boundary["pilot_manifest_sha256"],
        reference_pilot,
        "Reconstructed pilot manifest",
    )

    # Stage 5: rebuild the COMPLETE decision request,
    # including operation, CAS/boundary identities,
    # nonce, issuance, expiry and request ID.
    first_decision = _reconstruct_decision(
        boundary=first_boundary,
        context=context,
        supplied_decision=decision,
        reference_state_sha=reference_state,
        reference_generation=reference_gen,
        reference_checked_at=reference_checked_at,
    )

    _require_identical(
        decision,
        first_decision,
        "Decision request",
    )

    _require_sha_match(
        _digest(
            first_decision,
            "first reconstructed decision",
        ),
        decision_pin,
        "Reconstructed decision",
    )

    # Stage 6: repeat reconstruction to detect some
    # file changes during the assessment.
    #
    # This does NOT provide an atomic snapshot or
    # a transactional protected-state lock.
    second_boundary = _reconstruct_boundary(
        context
    )

    _require_identical(
        first_boundary,
        second_boundary,
        "Repeated execution boundary",
    )

    second_decision = _reconstruct_decision(
        boundary=second_boundary,
        context=context,
        supplied_decision=decision,
        reference_state_sha=reference_state,
        reference_generation=reference_gen,
        reference_checked_at=reference_checked_at,
    )

    _require_identical(
        first_decision,
        second_decision,
        "Repeated decision request",
    )

    _require_identical(
        decision,
        second_decision,
        "Final decision request",
    )

    _require_sha_match(
        _digest(
            second_decision,
            "final reconstructed decision",
        ),
        decision_pin,
        "Final decision identity",
    )

    # Result is a local, unprivileged precheck.
    # No approval, signature, nonce ledger, external
    # protected read, state update or CAS execution.
    return {
        "status": STATUS,
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "decision_request_id": (
            second_decision["decision_request_id"]
        ),
        "decision_request_sha256": decision_pin,
        "operation_id": (
            second_boundary["operation_id"]
        ),
        "execution_boundary_sha256": (
            _digest(
                second_boundary,
                "final execution boundary",
            )
        ),
        "cas_intent_sha256": (
            _digest(
                context["cas_intent"],
                "final CAS intent",
            )
        ),
        "expected_authority_state_sha256": (
            reference_state
        ),
        "expected_generation": reference_gen,
        "candidate_authority_state_sha256": (
            second_boundary[
                "candidate_authority_state_sha256"
            ]
        ),
        "candidate_generation": (
            second_boundary["candidate_generation"]
        ),
        "current_head_checkpoint_sha256": (
            reference_head
        ),
        "pilot_manifest_sha256": (
            reference_pilot
        ),
        "evidence_request_sha256": (
            second_boundary["evidence_request_sha256"]
        ),
        "transition_review_sha256": (
            second_boundary["transition_review_sha256"]
        ),
        "reference_checked_at": reference_checked_at,
    }
