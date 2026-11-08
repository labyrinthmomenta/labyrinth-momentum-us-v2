"""Fail-closed validation of a pinned remote recovery reference.

The trusted reference digest, trusted checkpoint head,
and pilot manifest digest must be supplied independently.

This module:
- Does not obtain its own trust pins from the reference.
- Does not perform network access.
- Does not authorize production or live operations.
- Does not establish a mutable latest-head authority.

Rollback protection is relative to the independently
provided checkpoint head and minimum session date.
"""

from datetime import date
import hashlib
import hmac
import json
from pathlib import Path
import re


SCHEMA_VERSION = 1
MAX_REFERENCE_BYTES = 32768

SHA256_PATTERN = re.compile(
    r"[0-9a-f]{64}",
    re.ASCII,
)

REQUIRED_FIELDS = frozenset({
    "schema_version",
    "market",
    "mode",
    "approval_status",
    "production_approved",
    "as_of",
    "bundle_sha256",
    "object_key",
    "anchor_sha256",
    "checkpoint_sha256",
    "pilot_manifest_sha256",
    "previous_checkpoint_sha256",
})


def _validate_sha256(value, field):
    """Require a canonical lowercase SHA-256 value."""
    if (
        not isinstance(value, str)
        or SHA256_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(
            f"Invalid SHA-256 value: {field}"
        )

    return value


def _unique_json_keys(pairs):
    """Reject duplicate keys rather than accepting the last."""
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(
                f"Duplicate remote reference key: {key}"
            )
        result[key] = value

    return result


def _parse_canonical_date(value):
    """Accept only YYYY-MM-DD with a valid calendar date."""
    if not isinstance(value, str):
        raise ValueError(
            "Reference as_of must be a string"
        )

    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            "Invalid reference as_of date"
        ) from exc

    if parsed.isoformat() != value:
        raise ValueError(
            "Reference date must use YYYY-MM-DD"
        )

    return parsed


def load_pinned_remote_recovery_reference(
    *,
    reference_path,
    trusted_reference_sha256,
    trusted_head_checkpoint_sha256,
    expected_pilot_manifest_sha256,
    min_as_of: date,
) -> dict:
    """Load an independently pinned offline recovery reference.

    Rejects an untrusted reference, a checkpoint that
    differs from the independently pinned head, and a
    checkpoint older than the required minimum session.

    Successful validation confirms the reference contract,
    not the contents of any remotely stored ZIP.
    """

    # Validate externally supplied trust inputs first.
    trusted_reference = _validate_sha256(
        trusted_reference_sha256,
        "trusted_reference_sha256",
    )

    trusted_head = _validate_sha256(
        trusted_head_checkpoint_sha256,
        "trusted_head_checkpoint_sha256",
    )

    trusted_pilot = _validate_sha256(
        expected_pilot_manifest_sha256,
        "expected_pilot_manifest_sha256",
    )

    if type(min_as_of) is not date:
        raise ValueError(
            "min_as_of must be a date"
        )

    path = Path(reference_path)

    if path.is_symlink():
        raise ValueError(
            "Symlinked remote references are forbidden"
        )

    if not path.is_file():
        raise FileNotFoundError(path)

    # Bound the input size before interpreting JSON.
    if (
        path.stat().st_size <= 0
        or path.stat().st_size > MAX_REFERENCE_BYTES
    ):
        raise ValueError(
            "Invalid remote reference file size"
        )

    raw = path.read_bytes()

    if not raw or len(raw) > MAX_REFERENCE_BYTES:
        raise ValueError(
            "Invalid remote reference file size"
        )

    actual_sha256 = hashlib.sha256(raw).hexdigest()

    if not hmac.compare_digest(
        actual_sha256,
        trusted_reference,
    ):
        raise ValueError(
            "Independent remote reference SHA-256 mismatch"
        )

    try:
        reference = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_json_keys,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Invalid remote reference JSON"
        ) from exc

    if not isinstance(reference, dict):
        raise ValueError(
            "Remote reference must be a JSON object"
        )

    if set(reference) != REQUIRED_FIELDS:
        raise ValueError(
            "Unexpected remote reference schema"
        )

    if (
        type(reference["schema_version"]) is not int
        or reference["schema_version"] != SCHEMA_VERSION
    ):
        raise ValueError(
            "Unsupported remote reference schema version"
        )

    if reference["market"] != "US":
        raise ValueError(
            "Remote reference market must be US"
        )

    if reference["mode"] != "PILOT_ONLY":
        raise ValueError(
            "Remote reference must be PILOT_ONLY"
        )

    if (
        reference["approval_status"]
        != "OFFLINE_CANDIDATE"
    ):
        raise ValueError(
            "Remote reference approval status rejected"
        )

    if reference["production_approved"] is not False:
        raise ValueError(
            "Production approval is not permitted"
        )

    reference_date = _parse_canonical_date(
        reference["as_of"]
    )

    if reference_date < min_as_of:
        raise ValueError(
            "Remote recovery reference is older "
            "than the minimum required session"
        )

    bundle_sha256 = _validate_sha256(
        reference["bundle_sha256"],
        "bundle_sha256",
    )

    _validate_sha256(
        reference["anchor_sha256"],
        "anchor_sha256",
    )

    checkpoint_sha256 = _validate_sha256(
        reference["checkpoint_sha256"],
        "checkpoint_sha256",
    )

    pilot_sha256 = _validate_sha256(
        reference["pilot_manifest_sha256"],
        "pilot_manifest_sha256",
    )

    previous_checkpoint = reference[
        "previous_checkpoint_sha256"
    ]

    if previous_checkpoint is not None:
        _validate_sha256(
            previous_checkpoint,
            "previous_checkpoint_sha256",
        )

        if hmac.compare_digest(
            previous_checkpoint,
            checkpoint_sha256,
        ):
            raise ValueError(
                "Checkpoint cannot reference itself"
            )

    expected_object_key = (
        f"sha256/{bundle_sha256}.zip"
    )

    if reference["object_key"] != expected_object_key:
        raise ValueError(
            "Remote object key does not match "
            "the pinned bundle SHA-256"
        )

    if not hmac.compare_digest(
        checkpoint_sha256,
        trusted_head,
    ):
        raise ValueError(
            "Remote checkpoint does not match "
            "the independently trusted head"
        )

    if not hmac.compare_digest(
        pilot_sha256,
        trusted_pilot,
    ):
        raise ValueError(
            "Remote reference pilot manifest "
            "SHA-256 mismatch"
        )

    # Recheck source bytes to detect simple changes
    # during validation. This does not eliminate all
    # concurrent filesystem races.
    if path.is_symlink():
        raise ValueError(
            "Remote reference changed to a symlink"
        )

    if not hmac.compare_digest(
        hashlib.sha256(path.read_bytes()).hexdigest(),
        trusted_reference,
    ):
        raise ValueError(
            "Remote reference changed during validation"
        )

    return reference
