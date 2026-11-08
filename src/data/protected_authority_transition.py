"""Read-only protected authority-state transition assessment.

Checks that a proposed successor authority state:
- Links to the independently pinned current state.
- Is based on the latest caller-supplied protected floor.
- Advances generation by exactly one.
- Advances the checkpoint date.
- Uses the independently pinned checkpoint heads.
- Matches the claimed reverified evidence request.

The protected floor is supplied by the caller.
This module cannot authenticate its origin or freshness.

It does NOT:
- Independently reverify SQLite evidence.
- Authenticate the claimed reverified request.
- Sign, approve, or commit a transition.
- Provide protected storage or compare-and-swap.
- Establish durable anti-rollback protection.
- Enable production or publication.

Success means REVIEW_REQUIRED, not authorization.
"""

from datetime import date
import hashlib
import hmac
import re
from pathlib import Path

from src.data.trusted_head_authority import (
    MAX_GENERATION,
    _canonical_bytes,
    _check_date,
    _check_sha256,
    _read_pinned_authority_state,
    _sha256_file,
)


REQUEST_FIELDS = frozenset({
    "status",
    "market",
    "mode",
    "production_approved",
    "previous_authority_state_sha256",
    "current_head_checkpoint_sha256",
    "candidate_head_checkpoint_sha256",
    "current_generation",
    "requested_generation",
    "current_as_of",
    "candidate_as_of",
    "pilot_manifest_sha256",
    "candidate_snapshot_id",
    "candidate_snapshot_sha256",
    "proposal_sha256",
})

SNAPSHOT_ID_PATTERN = re.compile(
    r"us_pilot_([0-9]{4}-[0-9]{2}-[0-9]{2})_"
    r"[0-9]+_v[0-9]+",
    re.ASCII,
)


def _same_hash(left, right):
    return hmac.compare_digest(left, right)


def _check_generation(value, label):
    if (
        type(value) is not int
        or not 0 <= value <= MAX_GENERATION
    ):
        raise ValueError(
            f"Invalid authority generation: {label}"
        )

    return value


def _check_request(request):
    """Validate a claimed reverified-evidence request.

    This checks the claim's structure; it does NOT
    authenticate the preceding evidence verification.
    """

    if (
        type(request) is not dict
        or set(request) != REQUEST_FIELDS
    ):
        raise ValueError(
            "Invalid reverified request schema"
        )

    if (
        request["status"]
        != "EVIDENCE_REVERIFIED_AUTHORIZATION_REQUIRED"
        or request["market"] != "US"
        or request["mode"] != "PILOT_ONLY"
        or request["production_approved"] is not False
    ):
        raise ValueError(
            "Reverified request safety policy rejected"
        )

    for field in (
        "previous_authority_state_sha256",
        "current_head_checkpoint_sha256",
        "candidate_head_checkpoint_sha256",
        "pilot_manifest_sha256",
        "candidate_snapshot_sha256",
        "proposal_sha256",
    ):
        _check_sha256(request[field], field)

    _check_generation(
        request["current_generation"],
        "current_generation",
    )

    _check_generation(
        request["requested_generation"],
        "requested_generation",
    )

    current_day = _check_date(
        request["current_as_of"],
        "current_as_of",
    )

    candidate_day = _check_date(
        request["candidate_as_of"],
        "candidate_as_of",
    )

    if candidate_day <= current_day:
        raise ValueError(
            "Reverified request does not advance the date"
        )

    snapshot_id = request["candidate_snapshot_id"]

    if not isinstance(snapshot_id, str):
        raise ValueError(
            "Invalid candidate snapshot identifier"
        )

    match = SNAPSHOT_ID_PATTERN.fullmatch(
        snapshot_id
    )

    if (
        match is None
        or match.group(1) != candidate_day.isoformat()
    ):
        raise ValueError(
            "Candidate snapshot identifier/date mismatch"
        )

    # Canonical serialization rejects unsupported values
    # and gives the complete request a stable identity.
    try:
        request_bytes = _canonical_bytes(request)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Invalid reverified request content"
        ) from exc

    return request_bytes


def _check_file_paths(current_path, candidate_path):
    current = Path(current_path)
    candidate = Path(candidate_path)

    if current.is_symlink() or candidate.is_symlink():
        raise ValueError(
            "Symlinked authority states are forbidden"
        )

    if (
        current.absolute() == candidate.absolute()
        or current.resolve() == candidate.resolve()
    ):
        raise ValueError(
            "Current and candidate authority states "
            "must be distinct"
        )

    return current, candidate


def _check_unchanged(path, expected_sha, label):
    if path.is_symlink():
        raise ValueError(
            f"{label} authority state became a symlink"
        )

    if not _same_hash(
        _sha256_file(path),
        expected_sha,
    ):
        raise ValueError(
            f"{label} authority state changed "
            "during assessment"
        )


def assess_protected_authority_transition(
    *,
    current_authority_state_path,
    candidate_authority_state_path,
    trusted_current_authority_state_sha256,
    expected_candidate_authority_state_sha256,
    protected_latest_authority_state_sha256,
    protected_latest_generation,
    reverified_authorization_request,
    expected_current_head_checkpoint_sha256,
    expected_candidate_head_checkpoint_sha256,
    expected_pilot_manifest_sha256,
) -> dict:
    """Assess a one-generation transition without applying it.

    All protected pins and independent SHA-256 values
    must originate from an authority outside this function.

    A matching caller-supplied floor is a necessary
    condition, but cannot itself prove freshness
    or durable anti-rollback protection.

    Returns AUTHORITY_STATE_TRANSITION_REVIEW_REQUIRED.
    """

    current_sha = _check_sha256(
        trusted_current_authority_state_sha256,
        "trusted_current_authority_state_sha256",
    )

    candidate_sha = _check_sha256(
        expected_candidate_authority_state_sha256,
        "expected_candidate_authority_state_sha256",
    )

    floor_sha = _check_sha256(
        protected_latest_authority_state_sha256,
        "protected_latest_authority_state_sha256",
    )

    floor_generation = _check_generation(
        protected_latest_generation,
        "protected_latest_generation",
    )

    current_head = _check_sha256(
        expected_current_head_checkpoint_sha256,
        "expected_current_head_checkpoint_sha256",
    )

    candidate_head = _check_sha256(
        expected_candidate_head_checkpoint_sha256,
        "expected_candidate_head_checkpoint_sha256",
    )

    pilot_sha = _check_sha256(
        expected_pilot_manifest_sha256,
        "expected_pilot_manifest_sha256",
    )

    # Stage 1: reject stale protected-floor references.
    # This only checks the floor provided by the caller;
    # its real provenance must be enforced externally.
    if not _same_hash(floor_sha, current_sha):
        raise ValueError(
            "Protected latest authority-state SHA-256 "
            "does not match current state"
        )

    if _same_hash(candidate_sha, current_sha):
        raise ValueError(
            "Candidate cannot reuse the current state"
        )

    if _same_hash(candidate_head, current_head):
        raise ValueError(
            "Candidate checkpoint head must advance"
        )

    current_path, candidate_path = _check_file_paths(
        current_authority_state_path,
        candidate_authority_state_path,
    )

    # Stage 2: verify the exact independently pinned
    # authority-state files using the established
    # strict JSON, type and integrity validator.
    current = _read_pinned_authority_state(
        current_path,
        current_sha,
    )

    candidate = _read_pinned_authority_state(
        candidate_path,
        candidate_sha,
    )

    if current["generation"] != floor_generation:
        raise ValueError(
            "Current generation is below or inconsistent "
            "with protected latest generation"
        )

    if candidate["generation"] != (
        current["generation"] + 1
    ):
        raise ValueError(
            "Authority generation must advance by exactly one"
        )

    if not _same_hash(
        candidate["previous_authority_state_sha256"],
        current_sha,
    ):
        raise ValueError(
            "Candidate authority predecessor mismatch"
        )

    if not _same_hash(
        current["head_checkpoint_sha256"],
        current_head,
    ):
        raise ValueError(
            "Current checkpoint head pin mismatch"
        )

    if not _same_hash(
        candidate["head_checkpoint_sha256"],
        candidate_head,
    ):
        raise ValueError(
            "Candidate checkpoint head pin mismatch"
        )

    if (
        not _same_hash(
            current["pilot_manifest_sha256"],
            pilot_sha,
        )
        or not _same_hash(
            candidate["pilot_manifest_sha256"],
            pilot_sha,
        )
    ):
        raise ValueError(
            "Authority pilot manifest mismatch"
        )

    current_day = _check_date(
        current["head_as_of"],
        "current.head_as_of",
    )

    candidate_day = _check_date(
        candidate["head_as_of"],
        "candidate.head_as_of",
    )

    if candidate_day <= current_day:
        raise ValueError(
            "Candidate authority date must move forward"
        )

    # Stage 3: check the full claimed reverified
    # request contract against the pinned state files.
    request = reverified_authorization_request

    request_bytes = _check_request(request)

    expected_fields = {
        "status": (
            "EVIDENCE_REVERIFIED_AUTHORIZATION_REQUIRED"
        ),
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "previous_authority_state_sha256": (
            current_sha
        ),
        "current_head_checkpoint_sha256": (
            current_head
        ),
        "candidate_head_checkpoint_sha256": (
            candidate_head
        ),
        "current_generation": (
            current["generation"]
        ),
        "requested_generation": (
            candidate["generation"]
        ),
        "current_as_of": (
            current_day.isoformat()
        ),
        "candidate_as_of": (
            candidate_day.isoformat()
        ),
        "pilot_manifest_sha256": pilot_sha,
    }

    for field, expected in expected_fields.items():
        actual = request[field]

        # Explicit types prevent True == 1 from
        # allowing a forged generation value.
        if (
            type(actual) is not type(expected)
            or actual != expected
        ):
            raise ValueError(
                f"Reverified request/state mismatch: {field}"
            )

    # Stage 4: check the pinned authority files once
    # more before returning the review-only result.
    #
    # These rechecks detect simple file changes but
    # do not provide atomicity across multiple files.
    _check_unchanged(
        current_path,
        current_sha,
        "Current",
    )

    _check_unchanged(
        candidate_path,
        candidate_sha,
        "Candidate",
    )

    request_sha = hashlib.sha256(
        request_bytes
    ).hexdigest()

    # No trusted-state mutation or authorization.
    return {
        "status": (
            "AUTHORITY_STATE_TRANSITION_REVIEW_REQUIRED"
        ),
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "current_authority_state_sha256": (
            current_sha
        ),
        "candidate_authority_state_sha256": (
            candidate_sha
        ),
        "current_generation": (
            current["generation"]
        ),
        "candidate_generation": (
            candidate["generation"]
        ),
        "current_head_checkpoint_sha256": (
            current_head
        ),
        "candidate_head_checkpoint_sha256": (
            candidate_head
        ),
        "current_as_of": (
            current_day.isoformat()
        ),
        "candidate_as_of": (
            candidate_day.isoformat()
        ),
        "pilot_manifest_sha256": (
            pilot_sha
        ),
        "evidence_request_sha256": (
            request_sha
        ),
    }
