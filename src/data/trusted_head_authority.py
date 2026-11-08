"""Offline trusted-head advancement request preparation.

A verified snapshot proposal may be used to PREPARE
an authorization request, never to authorize itself.

This module:
- Verifies the pinned authority-state file.
- Checks its generation, head, date and policy.
- Validates the supplied proposal's strict contract.
- Requires forward date and matching predecessor.
- Produces a deterministic authorization request.

This module does NOT:
- Verify SQLite itself or authenticate the caller's
  claim that the proposal was previously verified.
- Sign an authorization request.
- Implement an external trust authority.
- Persist or update a trusted head.
- Provide durable anti-rollback protection.
- Enable production or publication.
"""

from datetime import date
import hashlib
import hmac
import json
from pathlib import Path
import re


MAX_STATE_BYTES = 32768
MAX_GENERATION = (2**63) - 2

SHA256_PATTERN = re.compile(
    r"[0-9a-f]{64}",
    re.ASCII,
)

SNAPSHOT_ID_PATTERN = re.compile(
    r"us_pilot_([0-9]{4}-[0-9]{2}-[0-9]{2})_"
    r"[0-9]+_v[0-9]+",
    re.ASCII,
)

AUTHORITY_FIELDS = frozenset({
    "schema_version",
    "market",
    "mode",
    "production_approved",
    "generation",
    "head_checkpoint_sha256",
    "head_as_of",
    "pilot_manifest_sha256",
    "previous_authority_state_sha256",
})

PROPOSAL_FIELDS = frozenset({
    "status",
    "market",
    "mode",
    "production_approved",
    "previous_checkpoint_sha256",
    "candidate_checkpoint_sha256",
    "previous_as_of",
    "candidate_as_of",
    "pilot_manifest_sha256",
    "candidate_snapshot_id",
    "candidate_snapshot_sha256",
})


def _check_sha256(value, label):
    if (
        not isinstance(value, str)
        or SHA256_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(
            f"Invalid SHA-256: {label}"
        )

    return value


def _check_date(value, label):
    if not isinstance(value, str):
        raise ValueError(
            f"{label} must be a date string"
        )

    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"Invalid date: {label}"
        ) from exc

    if result.isoformat() != value:
        raise ValueError(
            f"Noncanonical date: {label}"
        )

    return result


def _unique_json_keys(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(
                f"Duplicate authority-state field: {key}"
            )

        result[key] = value

    return result


def _canonical_bytes(value):
    """Deterministic request/proposal serialization."""
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ) + "\n"
    ).encode("utf-8")


def _sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()

    with Path(path).open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _read_pinned_authority_state(
    path,
    trusted_sha256,
):
    """Read one independently pinned local state file."""

    state_path = Path(path)

    if state_path.is_symlink():
        raise ValueError(
            "Symlinked authority state is forbidden"
        )

    if not state_path.is_file():
        raise FileNotFoundError(state_path)

    size = state_path.stat().st_size

    if not 0 < size <= MAX_STATE_BYTES:
        raise ValueError(
            "Authority state has invalid size"
        )

    raw = state_path.read_bytes()

    if not 0 < len(raw) <= MAX_STATE_BYTES:
        raise ValueError(
            "Authority state has invalid size"
        )

    if not hmac.compare_digest(
        _sha256_bytes(raw),
        trusted_sha256,
    ):
        raise ValueError(
            "Independent authority-state SHA-256 mismatch"
        )

    try:
        state = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_json_keys,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Invalid authority-state JSON"
        ) from exc

    if (
        not isinstance(state, dict)
        or set(state) != AUTHORITY_FIELDS
    ):
        raise ValueError(
            "Invalid authority-state schema"
        )

    if (
        type(state["schema_version"]) is not int
        or state["schema_version"] != 1
        or state["market"] != "US"
        or state["mode"] != "PILOT_ONLY"
        or state["production_approved"] is not False
    ):
        raise ValueError(
            "Authority-state safety policy rejected"
        )

    generation = state["generation"]

    if (
        type(generation) is not int
        or not 0 <= generation <= MAX_GENERATION
    ):
        raise ValueError(
            "Invalid authority-state generation"
        )

    _check_sha256(
        state["head_checkpoint_sha256"],
        "head_checkpoint_sha256",
    )

    _check_sha256(
        state["pilot_manifest_sha256"],
        "pilot_manifest_sha256",
    )

    _check_date(
        state["head_as_of"],
        "head_as_of",
    )

    predecessor = state[
        "previous_authority_state_sha256"
    ]

    if generation == 0:
        if predecessor is not None:
            raise ValueError(
                "Genesis authority state must have "
                "no predecessor"
            )
    else:
        _check_sha256(
            predecessor,
            "previous_authority_state_sha256",
        )

    # Recheck after parsing to detect simple changes
    # during validation. This is not an atomic read
    # or a substitute for protected storage.
    if (
        state_path.is_symlink()
        or not hmac.compare_digest(
            _sha256_file(state_path),
            trusted_sha256,
        )
    ):
        raise ValueError(
            "Authority state changed during validation"
        )

    return state


def _validate_verified_proposal(proposal):
    """Validate the structure of a claimed verified proposal.

    This is contract checking, not independent proof
    that a SQLite snapshot was previously verified.
    """

    if (
        not isinstance(proposal, dict)
        or set(proposal) != PROPOSAL_FIELDS
    ):
        raise ValueError(
            "Invalid verified proposal schema"
        )

    if (
        proposal["status"]
        != "VERIFIED_SNAPSHOT_PROPOSAL_ONLY"
        or proposal["market"] != "US"
        or proposal["mode"] != "PILOT_ONLY"
        or proposal["production_approved"] is not False
    ):
        raise ValueError(
            "Verified proposal safety policy rejected"
        )

    for key in (
        "previous_checkpoint_sha256",
        "candidate_checkpoint_sha256",
        "pilot_manifest_sha256",
        "candidate_snapshot_sha256",
    ):
        _check_sha256(
            proposal[key],
            key,
        )

    previous_date = _check_date(
        proposal["previous_as_of"],
        "previous_as_of",
    )

    candidate_date = _check_date(
        proposal["candidate_as_of"],
        "candidate_as_of",
    )

    if candidate_date <= previous_date:
        raise ValueError(
            "Candidate must advance the checkpoint date"
        )

    if hmac.compare_digest(
        proposal["previous_checkpoint_sha256"],
        proposal["candidate_checkpoint_sha256"],
    ):
        raise ValueError(
            "Candidate cannot reuse the current head"
        )

    snapshot_id = proposal[
        "candidate_snapshot_id"
    ]

    if not isinstance(snapshot_id, str):
        raise ValueError(
            "Invalid candidate snapshot ID"
        )

    match = SNAPSHOT_ID_PATTERN.fullmatch(
        snapshot_id
    )

    if match is None:
        raise ValueError(
            "Invalid candidate snapshot ID"
        )

    if match.group(1) != candidate_date.isoformat():
        raise ValueError(
            "Candidate snapshot ID/date mismatch"
        )

    return previous_date, candidate_date


def prepare_trusted_head_advancement_request(
    *,
    authority_state_path,
    trusted_authority_state_sha256,
    verified_snapshot_proposal,
    expected_current_head_sha256,
    expected_pilot_manifest_sha256,
) -> dict:
    """Prepare a deterministic, unauthorized head-change request.

    The trusted authority-state SHA-256 and current head
    must be independently supplied by the caller.

    The returned dictionary has status
    AUTHORIZATION_REQUIRED. It is not an approval,
    a signature or a persisted state transition.
    """

    trusted_state_sha = _check_sha256(
        trusted_authority_state_sha256,
        "trusted_authority_state_sha256",
    )

    expected_head = _check_sha256(
        expected_current_head_sha256,
        "expected_current_head_sha256",
    )

    expected_pilot = _check_sha256(
        expected_pilot_manifest_sha256,
        "expected_pilot_manifest_sha256",
    )

    state = _read_pinned_authority_state(
        authority_state_path,
        trusted_state_sha,
    )

    previous_date, candidate_date = (
        _validate_verified_proposal(
            verified_snapshot_proposal
        )
    )

    if not hmac.compare_digest(
        state["head_checkpoint_sha256"],
        expected_head,
    ):
        raise ValueError(
            "Independent current head mismatch"
        )

    if not hmac.compare_digest(
        state["pilot_manifest_sha256"],
        expected_pilot,
    ):
        raise ValueError(
            "Authority-state pilot manifest mismatch"
        )

    if not hmac.compare_digest(
        verified_snapshot_proposal[
            "pilot_manifest_sha256"
        ],
        expected_pilot,
    ):
        raise ValueError(
            "Proposal pilot manifest mismatch"
        )

    if not hmac.compare_digest(
        verified_snapshot_proposal[
            "previous_checkpoint_sha256"
        ],
        expected_head,
    ):
        raise ValueError(
            "Proposal predecessor does not match trusted head"
        )

    if state["head_as_of"] != previous_date.isoformat():
        raise ValueError(
            "Proposal previous date does not match "
            "authority-state head date"
        )

    if candidate_date <= _check_date(
        state["head_as_of"],
        "head_as_of",
    ):
        raise ValueError(
            "Candidate is not newer than authority head"
        )

    # This digest gives the proposed payload a stable
    # identity, but does NOT authenticate its source.
    proposal_sha = _sha256_bytes(
        _canonical_bytes(
            verified_snapshot_proposal
        )
    )

    # Final integrity check before returning the
    # request. No file is written or modified.
    state_path = Path(authority_state_path)

    if (
        state_path.is_symlink()
        or not hmac.compare_digest(
            _sha256_file(state_path),
            trusted_state_sha,
        )
    ):
        raise ValueError(
            "Authority state changed during request preparation"
        )

    return {
        "status": "AUTHORIZATION_REQUIRED",
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "previous_authority_state_sha256": (
            trusted_state_sha
        ),
        "current_head_checkpoint_sha256": (
            expected_head
        ),
        "candidate_head_checkpoint_sha256": (
            verified_snapshot_proposal[
                "candidate_checkpoint_sha256"
            ]
        ),
        "current_generation": state["generation"],
        "requested_generation": (
            state["generation"] + 1
        ),
        "current_as_of": state["head_as_of"],
        "candidate_as_of": (
            candidate_date.isoformat()
        ),
        "pilot_manifest_sha256": expected_pilot,
        "candidate_snapshot_id": (
            verified_snapshot_proposal[
                "candidate_snapshot_id"
            ]
        ),
        "candidate_snapshot_sha256": (
            verified_snapshot_proposal[
                "candidate_snapshot_sha256"
            ]
        ),
        "proposal_sha256": proposal_sha,
    }
