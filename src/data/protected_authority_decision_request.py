"""Read-only external authority decision-request preparation.

This module constructs a deterministic request envelope
bound to a claimed execution-boundary result and a
claimed, nonexecuted CAS intent.

It checks:
- Exact schemas and safety statuses.
- Complete SHA-256 identity pins.
- CAS operation identity.
- Authority-state and checkpoint-head bindings.
- One-generation advancement.
- Caller-supplied protected-state reference.
- Canonical UTC timestamps and a bounded validity
  interval.
- A caller-supplied 128-bit nonce.

It does NOT:
- Authenticate the origin of the supplied evidence.
- Authenticate the protected-state reference.
- Establish an independently trusted clock.
- Generate a cryptographically random nonce.
- Maintain a durable single-use/replay ledger.
- Approve, reject or sign a real authority decision.
- Execute an atomic compare-and-swap transaction.
- Change trusted-head or production state.

A successful result remains an untrusted request
envelope requiring independent external authorization.
"""

from datetime import datetime
import hashlib
import hmac
import json
import re

from src.data.trusted_head_authority import (
    MAX_GENERATION,
)


STATUS = (
    "EXTERNAL_AUTHORITY_DECISION_REQUIRED_NOT_GRANTED"
)

BOUNDARY_STATUS = (
    "EVIDENCE_BOUND_EXTERNAL_CAS_REQUIRED_NOT_EXECUTED"
)

CAS_STATUS = (
    "EXTERNAL_ATOMIC_CAS_REQUIRED_NOT_EXECUTED"
)

MAX_VALIDITY_SECONDS = 300

SHA256_PATTERN = re.compile(
    r"[0-9a-f]{64}",
    re.ASCII,
)

NONCE_PATTERN = re.compile(
    r"[0-9a-f]{32}",
    re.ASCII,
)

UTC_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
    re.ASCII,
)

CAS_FIELDS = frozenset({
    "status",
    "market",
    "mode",
    "production_approved",
    "expected_authority_state_sha256",
    "expected_generation",
    "candidate_authority_state_sha256",
    "candidate_generation",
    "current_head_checkpoint_sha256",
    "candidate_head_checkpoint_sha256",
    "pilot_manifest_sha256",
    "evidence_request_sha256",
    "transition_review_sha256",
    "operation_id",
})

BOUNDARY_FIELDS = frozenset({
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
    "pilot_manifest_sha256",
    "evidence_request_sha256",
    "transition_review_sha256",
    "operation_id",
    "cas_intent_sha256",
})

# Corresponding CAS-intent and execution-boundary
# fields must be exactly identical.
SHARED_FIELDS = (
    (
        "expected_authority_state_sha256",
        "current_authority_state_sha256",
    ),
    (
        "expected_generation",
        "current_generation",
    ),
    (
        "candidate_authority_state_sha256",
        "candidate_authority_state_sha256",
    ),
    (
        "candidate_generation",
        "candidate_generation",
    ),
    (
        "current_head_checkpoint_sha256",
        "current_head_checkpoint_sha256",
    ),
    (
        "candidate_head_checkpoint_sha256",
        "candidate_head_checkpoint_sha256",
    ),
    (
        "pilot_manifest_sha256",
        "pilot_manifest_sha256",
    ),
    (
        "evidence_request_sha256",
        "evidence_request_sha256",
    ),
    (
        "transition_review_sha256",
        "transition_review_sha256",
    ),
    (
        "operation_id",
        "operation_id",
    ),
)


def _canonical_bytes(value):
    """Canonical JSON with type-sensitive identity."""

    if type(value) is not dict:
        raise ValueError(
            "Decision contract requires a plain dictionary"
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
            "Invalid decision contract serialization"
        ) from exc


def _digest(value):
    return hashlib.sha256(
        _canonical_bytes(value)
    ).hexdigest()


def _check_sha256(value, label):
    if (
        type(value) is not str
        or SHA256_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(
            f"Invalid SHA-256: {label}"
        )

    return value


def _check_generation(value, label):
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


def _check_schema(value, required, label):
    if (
        type(value) is not dict
        or set(value) != required
    ):
        raise ValueError(
            f"Invalid {label} schema"
        )

    return value


def _check_utc(value, label):
    """Require exact UTC seconds, without offset variants."""

    if (
        type(value) is not str
        or UTC_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(
            f"Invalid canonical UTC timestamp: {label}"
        )

    try:
        parsed = datetime.strptime(
            value,
            "%Y-%m-%dT%H:%M:%SZ",
        )
    except ValueError as exc:
        raise ValueError(
            f"Invalid UTC timestamp: {label}"
        ) from exc

    # Reject noncanonical date/time encodings.
    if (
        parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
        != value
    ):
        raise ValueError(
            f"Noncanonical UTC timestamp: {label}"
        )

    # Both values are interpreted in UTC, not in
    # the local timezone. This function does not
    # establish whether the supplied clock is trusted.
    return parsed


def _check_validity(
    *,
    nonce,
    issued_at,
    expires_at,
    checked_at,
):
    if (
        type(nonce) is not str
        or NONCE_PATTERN.fullmatch(nonce) is None
        or nonce == "0" * 32
    ):
        raise ValueError(
            "Invalid 128-bit request nonce"
        )

    issued = _check_utc(
        issued_at,
        "issued_at",
    )

    expires = _check_utc(
        expires_at,
        "expires_at",
    )

    checked = _check_utc(
        checked_at,
        "checked_at",
    )

    interval = (
        expires - issued
    ).total_seconds()

    if not (
        0 < interval <= MAX_VALIDITY_SECONDS
    ):
        raise ValueError(
            "Invalid decision request validity interval"
        )

    if not (
        issued <= checked < expires
    ):
        raise ValueError(
            "Decision request is not valid "
            "at the supplied check time"
        )


def _check_cas_intent(cas):
    _check_schema(
        cas,
        CAS_FIELDS,
        "CAS intent",
    )

    if (
        cas["status"] != CAS_STATUS
        or cas["market"] != "US"
        or cas["mode"] != "PILOT_ONLY"
        or cas["production_approved"] is not False
    ):
        raise ValueError(
            "CAS intent safety policy rejected"
        )

    for field in (
        "expected_authority_state_sha256",
        "candidate_authority_state_sha256",
        "current_head_checkpoint_sha256",
        "candidate_head_checkpoint_sha256",
        "pilot_manifest_sha256",
        "evidence_request_sha256",
        "transition_review_sha256",
        "operation_id",
    ):
        _check_sha256(cas[field], field)

    current = _check_generation(
        cas["expected_generation"],
        "expected_generation",
    )

    candidate = _check_generation(
        cas["candidate_generation"],
        "candidate_generation",
    )

    if candidate != current + 1:
        raise ValueError(
            "CAS generation must advance by exactly one"
        )

    if _same_sha256(
        cas["expected_authority_state_sha256"],
        cas["candidate_authority_state_sha256"],
    ):
        raise ValueError(
            "CAS candidate reuses current authority state"
        )

    if _same_sha256(
        cas["current_head_checkpoint_sha256"],
        cas["candidate_head_checkpoint_sha256"],
    ):
        raise ValueError(
            "CAS candidate reuses current checkpoint head"
        )

    # Rebuild the exact A6c.32 operation identity.
    operation_payload = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "expected_authority_state_sha256": (
            cas["expected_authority_state_sha256"]
        ),
        "expected_generation": (
            current
        ),
        "candidate_authority_state_sha256": (
            cas["candidate_authority_state_sha256"]
        ),
        "candidate_generation": (
            candidate
        ),
        "evidence_request_sha256": (
            cas["evidence_request_sha256"]
        ),
        "transition_review_sha256": (
            cas["transition_review_sha256"]
        ),
    }

    calculated_id = _digest(
        operation_payload
    )

    if not _same_sha256(
        calculated_id,
        cas["operation_id"],
    ):
        raise ValueError(
            "CAS operation identity mismatch"
        )


def _check_boundary(boundary):
    _check_schema(
        boundary,
        BOUNDARY_FIELDS,
        "execution boundary",
    )

    if (
        boundary["status"] != BOUNDARY_STATUS
        or boundary["market"] != "US"
        or boundary["mode"] != "PILOT_ONLY"
        or boundary["production_approved"] is not False
    ):
        raise ValueError(
            "Execution boundary safety policy rejected"
        )

    for field in (
        "current_authority_state_sha256",
        "candidate_authority_state_sha256",
        "current_head_checkpoint_sha256",
        "candidate_head_checkpoint_sha256",
        "pilot_manifest_sha256",
        "evidence_request_sha256",
        "transition_review_sha256",
        "operation_id",
        "cas_intent_sha256",
    ):
        _check_sha256(
            boundary[field],
            field,
        )

    current = _check_generation(
        boundary["current_generation"],
        "current_generation",
    )

    candidate = _check_generation(
        boundary["candidate_generation"],
        "candidate_generation",
    )

    if candidate != current + 1:
        raise ValueError(
            "Execution boundary generation "
            "must advance by exactly one"
        )


def prepare_protected_authority_decision_request(
    *,
    execution_boundary_result,
    cas_intent,
    trusted_execution_boundary_sha256,
    trusted_cas_intent_sha256,
    expected_operation_id,
    protected_latest_authority_state_sha256,
    protected_latest_generation,
    nonce,
    issued_at,
    expires_at,
    checked_at,
) -> dict:
    """Build an ungranted decision request, without I/O.

    Pins, nonce and timestamps are provided by the
    caller. Matching them cannot authenticate their
    source or establish protected-state freshness.

    The actual authority must independently validate
    the evidence, secure time, uniqueness and atomic
    CAS preconditions before any authorization.
    """

    boundary_pin = _check_sha256(
        trusted_execution_boundary_sha256,
        "trusted_execution_boundary_sha256",
    )

    cas_pin = _check_sha256(
        trusted_cas_intent_sha256,
        "trusted_cas_intent_sha256",
    )

    operation_pin = _check_sha256(
        expected_operation_id,
        "expected_operation_id",
    )

    protected_pin = _check_sha256(
        protected_latest_authority_state_sha256,
        "protected_latest_authority_state_sha256",
    )

    protected_generation = _check_generation(
        protected_latest_generation,
        "protected_latest_generation",
    )

    # Validate schemas before relying on any fields.
    _check_cas_intent(
        cas_intent
    )

    _check_boundary(
        execution_boundary_result
    )

    # Verify the canonical identity of both entire
    # dictionaries, not just selected fields.
    calculated_cas_sha = _digest(
        cas_intent
    )

    calculated_boundary_sha = _digest(
        execution_boundary_result
    )

    if not _same_sha256(
        calculated_cas_sha,
        cas_pin,
    ):
        raise ValueError(
            "Independent CAS intent SHA-256 mismatch"
        )

    if not _same_sha256(
        calculated_boundary_sha,
        boundary_pin,
    ):
        raise ValueError(
            "Independent execution boundary "
            "SHA-256 mismatch"
        )

    if not _same_sha256(
        execution_boundary_result[
            "cas_intent_sha256"
        ],
        calculated_cas_sha,
    ):
        raise ValueError(
            "Execution boundary does not bind "
            "the supplied CAS intent"
        )

    # Canonical JSON comparison preserves type
    # distinctions such as True versus integer 1.
    for cas_field, boundary_field in SHARED_FIELDS:
        if _canonical_bytes({
            "value": cas_intent[cas_field]
        }) != _canonical_bytes({
            "value": (
                execution_boundary_result[
                    boundary_field
                ]
            )
        }):
            raise ValueError(
                "CAS intent / execution boundary "
                f"mismatch: {cas_field}"
            )

    # Bind to the caller-provided protected floor.
    if not _same_sha256(
        cas_intent[
            "expected_authority_state_sha256"
        ],
        protected_pin,
    ):
        raise ValueError(
            "Protected latest state SHA-256 mismatch"
        )

    if (
        cas_intent["expected_generation"]
        != protected_generation
    ):
        raise ValueError(
            "Protected latest generation mismatch"
        )

    if not _same_sha256(
        cas_intent["operation_id"],
        operation_pin,
    ):
        raise ValueError(
            "Expected CAS operation ID mismatch"
        )

    # A time-valid request is still not authorized.
    _check_validity(
        nonce=nonce,
        issued_at=issued_at,
        expires_at=expires_at,
        checked_at=checked_at,
    )

    # The decision-request ID is a deterministic
    # content identity, NOT a cryptographic signature.
    identity_payload = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "operation_id": operation_pin,
        "expected_authority_state_sha256": (
            protected_pin
        ),
        "expected_generation": (
            protected_generation
        ),
        "candidate_authority_state_sha256": (
            cas_intent[
                "candidate_authority_state_sha256"
            ]
        ),
        "candidate_generation": (
            cas_intent["candidate_generation"]
        ),
        "evidence_request_sha256": (
            cas_intent["evidence_request_sha256"]
        ),
        "transition_review_sha256": (
            cas_intent["transition_review_sha256"]
        ),
        "cas_intent_sha256": (
            calculated_cas_sha
        ),
        "execution_boundary_sha256": (
            calculated_boundary_sha
        ),
        "nonce": nonce,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }

    decision_request_id = _digest(
        identity_payload
    )

    # No signing, approval, replay-ledger entry,
    # authority-state mutation or CAS execution.
    return {
        "status": STATUS,
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "operation_id": operation_pin,
        "expected_authority_state_sha256": (
            protected_pin
        ),
        "expected_generation": (
            protected_generation
        ),
        "candidate_authority_state_sha256": (
            cas_intent[
                "candidate_authority_state_sha256"
            ]
        ),
        "candidate_generation": (
            cas_intent["candidate_generation"]
        ),
        "evidence_request_sha256": (
            cas_intent["evidence_request_sha256"]
        ),
        "transition_review_sha256": (
            cas_intent["transition_review_sha256"]
        ),
        "cas_intent_sha256": (
            calculated_cas_sha
        ),
        "execution_boundary_sha256": (
            calculated_boundary_sha
        ),
        "nonce": nonce,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "decision_request_id": decision_request_id,
    }
