"""Offline assessment of US pilot checkpoint advancement.

Validates independently pinned current and candidate
checkpoint metadata and their predecessor relationship.

This module does NOT:
- Verify the underlying SQLite snapshot contents.
- Update a trusted checkpoint head.
- Establish an external trust authority.
- Authorize live ingestion or production publication.

A successful result is a proposal, not an approval.
"""

from collections.abc import Sequence
from datetime import date
import hashlib
import hmac
import json
from pathlib import Path
import re


SCHEMA_VERSION = 1
MAX_CHECKPOINT_BYTES = 32768

SHA256_PATTERN = re.compile(
    r"[0-9a-f]{64}",
    re.ASCII,
)

SYMBOL_PATTERN = re.compile(
    r"[A-Z][A-Z0-9.-]{0,14}",
    re.ASCII,
)

SNAPSHOT_ID_PATTERN = re.compile(
    r"us_pilot_(\d{4}-\d{2}-\d{2})_[0-9]+_v[0-9]+",
    re.ASCII,
)

REQUIRED_FIELDS = frozenset({
    "schema_version",
    "market",
    "mode",
    "production_approved",
    "as_of",
    "pilot_manifest_sha256",
    "required_symbols",
    "previous_checkpoint_sha256",
    "snapshot_id",
    "snapshot_sha256",
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


def _check_symbols(symbols):
    if (
        isinstance(symbols, (str, bytes))
        or not isinstance(symbols, Sequence)
        or not 1 <= len(symbols) <= 25
    ):
        raise ValueError(
            "Required symbols must contain 1 to 25 entries"
        )

    checked = []

    for symbol in symbols:
        if (
            not isinstance(symbol, str)
            or SYMBOL_PATTERN.fullmatch(symbol) is None
            or symbol in checked
        ):
            raise ValueError(
                f"Invalid or duplicate symbol: {symbol!r}"
            )

        checked.append(symbol)

    return tuple(checked)


def _unique_json_keys(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(
                f"Duplicate checkpoint field: {key}"
            )

        result[key] = value

    return result


def _parse_date(value, label):
    if not isinstance(value, str):
        raise ValueError(
            f"{label} must be a date string"
        )

    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"Invalid checkpoint date: {label}"
        ) from exc

    if parsed.isoformat() != value:
        raise ValueError(
            f"Noncanonical checkpoint date: {label}"
        )

    return parsed


def _sha256_file(path):
    digest = hashlib.sha256()

    with Path(path).open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _read_pinned_checkpoint(
    *,
    path,
    expected_sha256,
    label,
    expected_symbols,
    expected_pilot_sha256,
):
    """Read and validate a checkpoint without modifying it."""

    checkpoint_path = Path(path)

    if checkpoint_path.is_symlink():
        raise ValueError(
            f"Symlinked {label} checkpoint is forbidden"
        )

    if not checkpoint_path.is_file():
        raise FileNotFoundError(checkpoint_path)

    size = checkpoint_path.stat().st_size

    if not 0 < size <= MAX_CHECKPOINT_BYTES:
        raise ValueError(
            f"Invalid {label} checkpoint size"
        )

    raw = checkpoint_path.read_bytes()

    if not 0 < len(raw) <= MAX_CHECKPOINT_BYTES:
        raise ValueError(
            f"Invalid {label} checkpoint size"
        )

    actual_sha256 = hashlib.sha256(raw).hexdigest()

    if not hmac.compare_digest(
        actual_sha256,
        expected_sha256,
    ):
        raise ValueError(
            f"Independent {label} checkpoint SHA-256 mismatch"
        )

    try:
        checkpoint = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_json_keys,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Invalid {label} checkpoint JSON"
        ) from exc

    if (
        not isinstance(checkpoint, dict)
        or set(checkpoint) != REQUIRED_FIELDS
    ):
        raise ValueError(
            f"Invalid {label} checkpoint schema"
        )

    if (
        type(checkpoint["schema_version"]) is not int
        or checkpoint["schema_version"] != SCHEMA_VERSION
        or checkpoint["market"] != "US"
        or checkpoint["mode"] != "PILOT_ONLY"
        or checkpoint["production_approved"] is not False
    ):
        raise ValueError(
            f"{label} checkpoint safety policy rejected"
        )

    as_of = _parse_date(
        checkpoint["as_of"],
        f"{label}.as_of",
    )

    if checkpoint["required_symbols"] != list(
        expected_symbols
    ):
        raise ValueError(
            f"{label} checkpoint symbol universe mismatch"
        )

    pilot_sha256 = _check_sha256(
        checkpoint["pilot_manifest_sha256"],
        f"{label}.pilot_manifest_sha256",
    )

    if not hmac.compare_digest(
        pilot_sha256,
        expected_pilot_sha256,
    ):
        raise ValueError(
            f"{label} checkpoint pilot manifest mismatch"
        )

    snapshot_sha256 = _check_sha256(
        checkpoint["snapshot_sha256"],
        f"{label}.snapshot_sha256",
    )

    snapshot_id = checkpoint["snapshot_id"]

    if not isinstance(snapshot_id, str):
        raise ValueError(
            f"Invalid {label} snapshot ID"
        )

    match = SNAPSHOT_ID_PATTERN.fullmatch(
        snapshot_id
    )

    if match is None:
        raise ValueError(
            f"Invalid {label} snapshot ID"
        )

    # The session embedded in the snapshot identifier
    # must agree with the checkpoint date.
    if match.group(1) != as_of.isoformat():
        raise ValueError(
            f"{label} snapshot ID/session mismatch"
        )

    previous = checkpoint[
        "previous_checkpoint_sha256"
    ]

    if previous is not None:
        _check_sha256(
            previous,
            f"{label}.previous_checkpoint_sha256",
        )

        if hmac.compare_digest(
            previous,
            expected_sha256,
        ):
            raise ValueError(
                f"{label} checkpoint cannot link to itself"
            )

    # Detect simple modifications during validation.
    # This is not a full defense against concurrent
    # filesystem replacement.
    if checkpoint_path.is_symlink():
        raise ValueError(
            f"{label} checkpoint changed to a symlink"
        )

    if not hmac.compare_digest(
        _sha256_file(checkpoint_path),
        expected_sha256,
    ):
        raise ValueError(
            f"{label} checkpoint changed during validation"
        )

    return checkpoint, as_of, snapshot_sha256


def assess_checkpoint_advance(
    *,
    current_checkpoint_path,
    candidate_checkpoint_path,
    trusted_current_head_sha256,
    expected_candidate_sha256,
    expected_pilot_manifest_sha256,
    required_symbols,
    min_candidate_as_of: date,
) -> dict:
    """Assess a forward checkpoint transition, without committing it.

    Both checkpoint file digests are externally supplied.
    The candidate must link directly to the trusted head.

    Successful assessment returns VALIDATED_PROPOSAL_ONLY.
    It does not create a new trusted checkpoint head.
    """

    current_head = _check_sha256(
        trusted_current_head_sha256,
        "trusted_current_head_sha256",
    )

    candidate_sha256 = _check_sha256(
        expected_candidate_sha256,
        "expected_candidate_sha256",
    )

    pilot_sha256 = _check_sha256(
        expected_pilot_manifest_sha256,
        "expected_pilot_manifest_sha256",
    )

    symbols = _check_symbols(required_symbols)

    if type(min_candidate_as_of) is not date:
        raise ValueError(
            "min_candidate_as_of must be a date"
        )

    if hmac.compare_digest(
        current_head,
        candidate_sha256,
    ):
        raise ValueError(
            "Candidate checkpoint must differ from current head"
        )

    current_path = Path(current_checkpoint_path)
    candidate_path = Path(candidate_checkpoint_path)

    if current_path == candidate_path:
        raise ValueError(
            "Current and candidate paths must differ"
        )

    current, current_date, current_snapshot_sha = (
        _read_pinned_checkpoint(
            path=current_path,
            expected_sha256=current_head,
            label="current",
            expected_symbols=symbols,
            expected_pilot_sha256=pilot_sha256,
        )
    )

    candidate, candidate_date, candidate_snapshot_sha = (
        _read_pinned_checkpoint(
            path=candidate_path,
            expected_sha256=candidate_sha256,
            label="candidate",
            expected_symbols=symbols,
            expected_pilot_sha256=pilot_sha256,
        )
    )

    if not hmac.compare_digest(
        candidate["previous_checkpoint_sha256"]
        if candidate["previous_checkpoint_sha256"] is not None
        else "",
        current_head,
    ):
        raise ValueError(
            "Candidate checkpoint predecessor mismatch"
        )

    if candidate_date <= current_date:
        raise ValueError(
            "Checkpoint advancement must move forward in time"
        )

    if candidate_date < min_candidate_as_of:
        raise ValueError(
            "Candidate checkpoint is older than required minimum"
        )

    if (
        candidate["snapshot_id"]
        == current["snapshot_id"]
    ):
        raise ValueError(
            "Candidate reuses the current snapshot ID"
        )

    if hmac.compare_digest(
        candidate_snapshot_sha,
        current_snapshot_sha,
    ):
        raise ValueError(
            "Candidate reuses the current snapshot SHA-256"
        )

    # Recheck independently pinned files before
    # returning the proposal.
    for path, expected, label in (
        (current_path, current_head, "current"),
        (candidate_path, candidate_sha256, "candidate"),
    ):
        if path.is_symlink() or not hmac.compare_digest(
            _sha256_file(path),
            expected,
        ):
            raise ValueError(
                f"{label} checkpoint changed during assessment"
            )

    return {
        "status": "VALIDATED_PROPOSAL_ONLY",
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "previous_checkpoint_sha256": current_head,
        "candidate_checkpoint_sha256": candidate_sha256,
        "previous_as_of": current_date.isoformat(),
        "candidate_as_of": candidate_date.isoformat(),
        "pilot_manifest_sha256": pilot_sha256,
        "candidate_snapshot_id": candidate["snapshot_id"],
        "candidate_snapshot_sha256": candidate_snapshot_sha,
    }
