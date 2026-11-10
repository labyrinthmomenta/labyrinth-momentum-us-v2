"""Offline authority-side evidence and CAS-intent binding.

Reconstructs the complete proposed transition from:
- Independently pinned checkpoints and real SQLite.
- Independently pinned current authority state.
- A separately pinned candidate authority state.
- A caller-supplied protected latest-state reference.

It compares supplied authorization requests, reviews,
and CAS intents with freshly reconstructed results.

This module does NOT:
- Authenticate the provenance of caller-supplied pins.
- Authenticate an external protected-state service.
- Guarantee atomic filesystem or database snapshots.
- Sign or authorize any transition.
- Execute compare-and-swap.
- Persist or update the trusted authority head.
- Provide durable replay or anti-rollback protection.
- Enable live ingestion, production or publication.

Success means evidence is bound to a nonexecuted
CAS intent. External authorization remains required.
"""

from datetime import date
import hashlib
import hmac
import json

from src.data.authority_evidence_reverification import (
    reverify_authority_evidence,
)
from src.data.protected_authority_transition import (
    assess_protected_authority_transition,
)
from src.data.authority_cas_intent import (
    prepare_authority_cas_intent,
)


BOUND_STATUS = (
    "EVIDENCE_BOUND_EXTERNAL_CAS_REQUIRED_NOT_EXECUTED"
)


def _canonical_dict_bytes(value, label):
    """Type-sensitive, deterministic dictionary encoding.

    Python dictionary equality is not sufficient:
    the boolean True compares equal to integer 1.

    The JSON representation distinguishes these types.
    """

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
        _canonical_dict_bytes(value, label)
    ).hexdigest()


def _require_identical(supplied, expected, label):
    """Reject missing, added, modified or mistyped fields."""

    supplied_bytes = _canonical_dict_bytes(
        supplied,
        label,
    )

    expected_bytes = _canonical_dict_bytes(
        expected,
        f"reconstructed {label}",
    )

    if not hmac.compare_digest(
        supplied_bytes,
        expected_bytes,
    ):
        raise ValueError(
            f"{label} does not match "
            "independently reconstructed evidence"
        )


def _reconstruct_chain(
    *,
    current_checkpoint_path,
    current_snapshot_dir,
    candidate_checkpoint_path,
    candidate_snapshot_dir,
    trusted_current_head_sha256,
    expected_candidate_sha256,
    expected_pilot_manifest_sha256,
    required_symbols,
    min_candidate_as_of,
    expected_current_predecessor_sha256,
    current_authority_state_path,
    candidate_authority_state_path,
    trusted_current_authority_state_sha256,
    expected_candidate_authority_state_sha256,
    protected_latest_authority_state_sha256,
    protected_latest_generation,
    authorization_request,
):
    """Rebuild the actual evidence, review and CAS intent.

    All objects returned here are newly reconstructed.
    Supplied transition-review and CAS-intent claims are
    never used as evidence.
    """

    # Stage 1:
    # Reverify the real SQLite files and checkpoints,
    # not a claimed verification status.
    reverified = reverify_authority_evidence(
        authority_state_path=(
            current_authority_state_path
        ),
        trusted_authority_state_sha256=(
            trusted_current_authority_state_sha256
        ),
        authorization_request=authorization_request,
        current_checkpoint_path=(
            current_checkpoint_path
        ),
        current_snapshot_dir=(
            current_snapshot_dir
        ),
        candidate_checkpoint_path=(
            candidate_checkpoint_path
        ),
        candidate_snapshot_dir=(
            candidate_snapshot_dir
        ),
        trusted_current_head_sha256=(
            trusted_current_head_sha256
        ),
        expected_candidate_sha256=(
            expected_candidate_sha256
        ),
        expected_pilot_manifest_sha256=(
            expected_pilot_manifest_sha256
        ),
        required_symbols=required_symbols,
        min_candidate_as_of=min_candidate_as_of,
        expected_current_predecessor_sha256=(
            expected_current_predecessor_sha256
        ),
    )

    if reverified["status"] != (
        "EVIDENCE_REVERIFIED_AUTHORIZATION_REQUIRED"
    ):
        raise ValueError(
            "SQLite evidence was not reverified"
        )

    if reverified["production_approved"] is not False:
        raise ValueError(
            "Production approval is forbidden"
        )

    evidence_sha = _digest(
        reverified,
        "reverified evidence",
    )

    # Stage 2:
    # Reassess actual authority-state files,
    # including predecessor and protected floor.
    review = assess_protected_authority_transition(
        current_authority_state_path=(
            current_authority_state_path
        ),
        candidate_authority_state_path=(
            candidate_authority_state_path
        ),
        trusted_current_authority_state_sha256=(
            trusted_current_authority_state_sha256
        ),
        expected_candidate_authority_state_sha256=(
            expected_candidate_authority_state_sha256
        ),
        protected_latest_authority_state_sha256=(
            protected_latest_authority_state_sha256
        ),
        protected_latest_generation=(
            protected_latest_generation
        ),
        reverified_authorization_request=reverified,
        expected_current_head_checkpoint_sha256=(
            trusted_current_head_sha256
        ),
        expected_candidate_head_checkpoint_sha256=(
            expected_candidate_sha256
        ),
        expected_pilot_manifest_sha256=(
            expected_pilot_manifest_sha256
        ),
    )

    if review["status"] != (
        "AUTHORITY_STATE_TRANSITION_REVIEW_REQUIRED"
    ):
        raise ValueError(
            "Authority-state transition was not reviewed"
        )

    if review["production_approved"] is not False:
        raise ValueError(
            "Authority review claims production approval"
        )

    if not hmac.compare_digest(
        review["evidence_request_sha256"],
        evidence_sha,
    ):
        raise ValueError(
            "Authority review is not bound "
            "to freshly reverified evidence"
        )

    review_sha = _digest(
        review,
        "reconstructed transition review",
    )

    # Stage 3:
    # Reconstruct CAS preconditions and operation ID.
    intent = prepare_authority_cas_intent(
        transition_review=review,
        trusted_transition_review_sha256=review_sha,
        protected_latest_authority_state_sha256=(
            protected_latest_authority_state_sha256
        ),
        protected_latest_generation=(
            protected_latest_generation
        ),
        expected_candidate_authority_state_sha256=(
            expected_candidate_authority_state_sha256
        ),
        expected_candidate_generation=(
            review["candidate_generation"]
        ),
        expected_evidence_request_sha256=evidence_sha,
    )

    if intent["status"] != (
        "EXTERNAL_ATOMIC_CAS_REQUIRED_NOT_EXECUTED"
    ):
        raise ValueError(
            "Unexpected external CAS intent status"
        )

    if intent["production_approved"] is not False:
        raise ValueError(
            "CAS intent claims production approval"
        )

    if not hmac.compare_digest(
        intent["transition_review_sha256"],
        review_sha,
    ):
        raise ValueError(
            "CAS intent is not bound to "
            "the reconstructed transition review"
        )

    if not hmac.compare_digest(
        intent["evidence_request_sha256"],
        evidence_sha,
    ):
        raise ValueError(
            "CAS intent is not bound to "
            "the reconstructed evidence request"
        )

    return reverified, review, intent


def assess_authority_execution_boundary(
    *,
    current_checkpoint_path,
    current_snapshot_dir,
    candidate_checkpoint_path,
    candidate_snapshot_dir,
    trusted_current_head_sha256,
    expected_candidate_sha256,
    expected_pilot_manifest_sha256,
    required_symbols,
    min_candidate_as_of: date,
    current_authority_state_path,
    candidate_authority_state_path,
    trusted_current_authority_state_sha256,
    expected_candidate_authority_state_sha256,
    protected_latest_authority_state_sha256,
    protected_latest_generation,
    authorization_request,
    transition_review,
    cas_intent,
    expected_current_predecessor_sha256=None,
) -> dict:
    """Bind a supplied CAS intent to real evidence, read-only.

    The independent trust pins must come from an
    appropriately protected and authenticated source.

    A matching caller-provided protected floor does not
    prove that it is still the latest floor.

    The function never performs a CAS transaction.
    """

    # Preserve the original caller inputs. Detect
    # malformed dictionaries before file access.
    supplied_request_bytes = _canonical_dict_bytes(
        authorization_request,
        "authorization request",
    )

    supplied_review_bytes = _canonical_dict_bytes(
        transition_review,
        "transition review",
    )

    supplied_intent_bytes = _canonical_dict_bytes(
        cas_intent,
        "CAS intent",
    )

    if cas_intent.get("status") != (
        "EXTERNAL_ATOMIC_CAS_REQUIRED_NOT_EXECUTED"
    ):
        raise ValueError(
            "CAS intent must remain unexecuted"
        )

    if cas_intent.get("production_approved") is not False:
        raise ValueError(
            "Production approval is forbidden"
        )

    arguments = {
        "current_checkpoint_path": current_checkpoint_path,
        "current_snapshot_dir": current_snapshot_dir,
        "candidate_checkpoint_path": candidate_checkpoint_path,
        "candidate_snapshot_dir": candidate_snapshot_dir,
        "trusted_current_head_sha256": (
            trusted_current_head_sha256
        ),
        "expected_candidate_sha256": (
            expected_candidate_sha256
        ),
        "expected_pilot_manifest_sha256": (
            expected_pilot_manifest_sha256
        ),
        "required_symbols": required_symbols,
        "min_candidate_as_of": min_candidate_as_of,
        "expected_current_predecessor_sha256": (
            expected_current_predecessor_sha256
        ),
        "current_authority_state_path": (
            current_authority_state_path
        ),
        "candidate_authority_state_path": (
            candidate_authority_state_path
        ),
        "trusted_current_authority_state_sha256": (
            trusted_current_authority_state_sha256
        ),
        "expected_candidate_authority_state_sha256": (
            expected_candidate_authority_state_sha256
        ),
        "protected_latest_authority_state_sha256": (
            protected_latest_authority_state_sha256
        ),
        "protected_latest_generation": (
            protected_latest_generation
        ),
        "authorization_request": authorization_request,
    }

    # First independent reconstruction.
    first_evidence, first_review, first_intent = (
        _reconstruct_chain(**arguments)
    )

    _require_identical(
        transition_review,
        first_review,
        "transition review",
    )

    _require_identical(
        cas_intent,
        first_intent,
        "CAS intent",
    )

    # A second independent reconstruction detects
    # some file mutations occurring during the first
    # pass. It does NOT establish an atomic snapshot.
    second_evidence, second_review, second_intent = (
        _reconstruct_chain(**arguments)
    )

    for label, first, second in (
        (
            "reverified evidence",
            first_evidence,
            second_evidence,
        ),
        (
            "transition review",
            first_review,
            second_review,
        ),
        (
            "CAS intent",
            first_intent,
            second_intent,
        ),
    ):
        _require_identical(
            first,
            second,
            label,
        )

    _require_identical(
        transition_review,
        second_review,
        "transition review",
    )

    _require_identical(
        cas_intent,
        second_intent,
        "CAS intent",
    )

    # Detect changes to supplied dictionaries during
    # reconstruction. External protected-state freshness
    # must still be enforced by the actual authority.
    if (
        _canonical_dict_bytes(
            authorization_request,
            "authorization request",
        ) != supplied_request_bytes
        or _canonical_dict_bytes(
            transition_review,
            "transition review",
        ) != supplied_review_bytes
        or _canonical_dict_bytes(
            cas_intent,
            "CAS intent",
        ) != supplied_intent_bytes
    ):
        raise ValueError(
            "Supplied evidence or intent changed "
            "during execution-boundary assessment"
        )

    # Read-only result: no approval, signing, mutation
    # or external CAS operation is performed.
    return {
        "status": BOUND_STATUS,
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "current_authority_state_sha256": (
            second_review[
                "current_authority_state_sha256"
            ]
        ),
        "candidate_authority_state_sha256": (
            second_review[
                "candidate_authority_state_sha256"
            ]
        ),
        "current_generation": (
            second_review["current_generation"]
        ),
        "candidate_generation": (
            second_review["candidate_generation"]
        ),
        "current_head_checkpoint_sha256": (
            second_review[
                "current_head_checkpoint_sha256"
            ]
        ),
        "candidate_head_checkpoint_sha256": (
            second_review[
                "candidate_head_checkpoint_sha256"
            ]
        ),
        "pilot_manifest_sha256": (
            second_review["pilot_manifest_sha256"]
        ),
        "evidence_request_sha256": _digest(
            second_evidence,
            "final reverified evidence",
        ),
        "transition_review_sha256": _digest(
            second_review,
            "final transition review",
        ),
        "operation_id": second_intent["operation_id"],
        "cas_intent_sha256": _digest(
            second_intent,
            "final CAS intent",
        ),
    }
