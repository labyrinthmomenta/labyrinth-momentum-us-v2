"""Offline authority-side checkpoint evidence reverification.

Independently reconstructs a trusted-head advancement
request from real current/candidate SQLite snapshots
and independently pinned checkpoint/authority-state files.

This module does NOT:
- Authenticate who supplied the independent pins.
- Sign or authorize an advancement.
- Persist or update a trusted head.
- Provide durable anti-rollback protection.
- Enable live ingestion or publication.

Success means evidence was reverified and authorization
is STILL required.
"""

from datetime import date
import hmac
import json

from src.data.trusted_head_authority import (
    prepare_trusted_head_advancement_request,
)
from src.data.verified_snapshot_advancement import (
    assess_verified_snapshot_advance,
)


def _canonical_request_bytes(value):
    """Encode values with type-sensitive JSON representation.

    Python dict equality considers True equal to 1.
    Comparing canonical JSON bytes does not.
    """

    if type(value) is not dict:
        raise ValueError(
            "Authorization request must be a plain dictionary"
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
            "Invalid authorization request content"
        ) from exc


def reverify_authority_evidence(
    *,
    authority_state_path,
    trusted_authority_state_sha256,
    authorization_request,
    current_checkpoint_path,
    current_snapshot_dir,
    candidate_checkpoint_path,
    candidate_snapshot_dir,
    trusted_current_head_sha256,
    expected_candidate_sha256,
    expected_pilot_manifest_sha256,
    required_symbols,
    min_candidate_as_of: date,
    expected_current_predecessor_sha256=None,
) -> dict:
    """Reverify actual evidence and compare the entire request.

    All independent SHA-256 pins must be supplied by the
    caller from an appropriately trusted source.

    The incoming request itself is NOT accepted as
    evidence that SQLite or checkpoint verification
    previously happened.

    Returns EVIDENCE_REVERIFIED_AUTHORIZATION_REQUIRED.
    It does not grant authorization.
    """

    # Validate basic request structure before touching
    # the SQLite files or the authority state.
    supplied_bytes = _canonical_request_bytes(
        authorization_request
    )

    if authorization_request.get("status") != (
        "AUTHORIZATION_REQUIRED"
    ):
        raise ValueError(
            "Request is not awaiting authorization"
        )

    if authorization_request.get(
        "production_approved"
    ) is not False:
        raise ValueError(
            "Production approval is forbidden"
        )

    evidence_args = {
        "current_checkpoint_path": (
            current_checkpoint_path
        ),
        "current_snapshot_dir": (
            current_snapshot_dir
        ),
        "candidate_checkpoint_path": (
            candidate_checkpoint_path
        ),
        "candidate_snapshot_dir": (
            candidate_snapshot_dir
        ),
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
    }

    # Stage 1:
    # Ignore the request's claimed snapshot metadata.
    # Reverify actual checkpoints and their SQLite files.
    actual_proposal = assess_verified_snapshot_advance(
        **evidence_args
    )

    if actual_proposal["status"] != (
        "VERIFIED_SNAPSHOT_PROPOSAL_ONLY"
    ):
        raise ValueError(
            "Underlying snapshot evidence is not verified"
        )

    if actual_proposal["production_approved"] is not False:
        raise ValueError(
            "Underlying evidence claims production approval"
        )

    # Stage 2:
    # Recompute the complete authorization request
    # using the independently pinned authority state
    # AND the freshly verified SQLite evidence.
    expected_request = (
        prepare_trusted_head_advancement_request(
            authority_state_path=authority_state_path,
            trusted_authority_state_sha256=(
                trusted_authority_state_sha256
            ),
            verified_snapshot_proposal=actual_proposal,
            expected_current_head_sha256=(
                trusted_current_head_sha256
            ),
            expected_pilot_manifest_sha256=(
                expected_pilot_manifest_sha256
            ),
        )
    )

    if expected_request["status"] != (
        "AUTHORIZATION_REQUIRED"
    ):
        raise ValueError(
            "Unexpected authority request state"
        )

    if expected_request["production_approved"] is not False:
        raise ValueError(
            "Production approval is forbidden"
        )

    # Stage 3:
    # Compare the complete deterministic request,
    # not just a small set of selected fields.
    #
    # Exact key sets block injected approval fields.
    # JSON bytes preserve important type distinctions,
    # including True versus integer 1.
    if set(authorization_request) != set(
        expected_request
    ):
        raise ValueError(
            "Authorization request schema mismatch"
        )

    expected_bytes = _canonical_request_bytes(
        expected_request
    )

    if not hmac.compare_digest(
        supplied_bytes,
        expected_bytes,
    ):
        raise ValueError(
            "Authorization request differs from "
            "independently reverified evidence"
        )

    # Stage 4:
    # Repeat the file-backed verification after the
    # authority-state check to detect changes occurring
    # during request preparation.
    #
    # This does not give atomic transaction isolation
    # across separate filesystems or establish a
    # durable external trust authority.
    final_proposal = assess_verified_snapshot_advance(
        **evidence_args
    )

    if not hmac.compare_digest(
        _canonical_request_bytes(actual_proposal),
        _canonical_request_bytes(final_proposal),
    ):
        raise ValueError(
            "Snapshot evidence changed during "
            "authority reverification"
        )

    # Revalidate the authority-state pin after
    # rechecking the snapshot evidence.
    final_request = (
        prepare_trusted_head_advancement_request(
            authority_state_path=authority_state_path,
            trusted_authority_state_sha256=(
                trusted_authority_state_sha256
            ),
            verified_snapshot_proposal=final_proposal,
            expected_current_head_sha256=(
                trusted_current_head_sha256
            ),
            expected_pilot_manifest_sha256=(
                expected_pilot_manifest_sha256
            ),
        )
    )

    if not hmac.compare_digest(
        _canonical_request_bytes(final_request),
        expected_bytes,
    ):
        raise ValueError(
            "Authority state or verified proposal "
            "changed during reverification"
        )

    # No approval, signature, file write,
    # trusted-head update or publication.
    return {
        **final_request,
        "status": (
            "EVIDENCE_REVERIFIED_AUTHORIZATION_REQUIRED"
        ),
        "production_approved": False,
    }
