"""Fail-closed validation of the initial US pilot trust anchor.

An OFFLINE_CANDIDATE anchor is not an approval to run
automated ingestion or publish production results.

The trusted anchor digest must come from an independent
authorized source, not from the anchor being inspected.
"""

from datetime import date
import hashlib
import hmac
import json
from pathlib import Path
import re


SCHEMA_VERSION = 1
MAX_ANCHOR_BYTES = 32768

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
SNAPSHOT_ID_PATTERN = re.compile(
    r"us_pilot_\d{4}-\d{2}-\d{2}_[0-9]+_v[0-9]+"
)
CHECKPOINT_FILE_PATTERN = re.compile(
    r"us_pilot_\d{4}-\d{2}-\d{2}_checkpoint_v[0-9]+\.json"
)

REQUIRED_FIELDS = {
    "schema_version",
    "market",
    "mode",
    "approval_status",
    "production_approved",
    "checkpoint_file",
    "checkpoint_sha256",
    "snapshot_id",
    "snapshot_sha256",
    "pilot_manifest_sha256",
    "as_of",
    "previous_checkpoint_sha256",
}


def _check_sha256(value, field):
    if (
        not isinstance(value, str)
        or SHA256_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(
            f"Invalid SHA-256 value: {field}"
        )


def _unique_json_keys(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(
                f"Duplicate trust anchor key: {key}"
            )
        result[key] = value

    return result


def _parse_date(value):
    if not isinstance(value, str):
        raise ValueError(
            "Trust anchor as_of must be a string"
        )

    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            "Invalid trust anchor as_of date"
        ) from exc

    if parsed.isoformat() != value:
        raise ValueError(
            "Trust anchor date must use YYYY-MM-DD"
        )

    return parsed


def load_bootstrap_checkpoint_anchor(
    *,
    anchor_path: str | Path,
    trusted_anchor_sha256: str,
    min_as_of: date | None = None,
) -> dict:
    """Validate a pinned, offline-only genesis checkpoint anchor.

    Never derives trusted_anchor_sha256 from anchor_path.
    Never approves production or scheduled execution.
    """
    _check_sha256(
        trusted_anchor_sha256,
        "trusted_anchor_sha256",
    )

    if min_as_of is not None and type(min_as_of) is not date:
        raise ValueError(
            "min_as_of must be a date or None"
        )

    path = Path(anchor_path)

    if path.is_symlink():
        raise ValueError(
            "Trust anchor symlinks are not permitted"
        )

    if not path.is_file():
        raise FileNotFoundError(path)

    raw = path.read_bytes()

    if not raw or len(raw) > MAX_ANCHOR_BYTES:
        raise ValueError(
            "Invalid trust anchor file size"
        )

    actual_sha256 = hashlib.sha256(raw).hexdigest()

    if not hmac.compare_digest(
        actual_sha256,
        trusted_anchor_sha256,
    ):
        raise ValueError(
            "Independent trust anchor SHA-256 mismatch"
        )

    anchor = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_json_keys,
    )

    if (
        not isinstance(anchor, dict)
        or set(anchor) != REQUIRED_FIELDS
    ):
        raise ValueError(
            "Unexpected trust anchor schema"
        )

    if (
        type(anchor["schema_version"]) is not int
        or anchor["schema_version"] != SCHEMA_VERSION
        or anchor["market"] != "US"
        or anchor["mode"] != "PILOT_ONLY"
        or anchor["approval_status"] != "OFFLINE_CANDIDATE"
        or anchor["production_approved"] is not False
    ):
        raise ValueError(
            "Bootstrap safety policy rejected"
        )

    # This module validates only the first checkpoint.
    # Later checkpoints will use a separate chain policy.
    if anchor["previous_checkpoint_sha256"] is not None:
        raise ValueError(
            "Bootstrap checkpoint cannot have a predecessor"
        )

    for field in (
        "checkpoint_sha256",
        "snapshot_sha256",
        "pilot_manifest_sha256",
    ):
        _check_sha256(anchor[field], field)

    checkpoint_file = anchor["checkpoint_file"]
    snapshot_id = anchor["snapshot_id"]

    if (
        not isinstance(checkpoint_file, str)
        or CHECKPOINT_FILE_PATTERN.fullmatch(
            checkpoint_file
        ) is None
    ):
        raise ValueError(
            "Unsafe checkpoint file name"
        )

    if (
        not isinstance(snapshot_id, str)
        or SNAPSHOT_ID_PATTERN.fullmatch(
            snapshot_id
        ) is None
    ):
        raise ValueError(
            "Invalid bootstrap snapshot ID"
        )

    checkpoint_date = _parse_date(anchor["as_of"])

    if (
        min_as_of is not None
        and checkpoint_date < min_as_of
    ):
        raise ValueError(
            "Bootstrap checkpoint is older than "
            "the required minimum session"
        )

    # Prevent a well-formed but internally inconsistent
    # anchor from mixing different checkpoint dates.
    expected_file_prefix = (
        f"us_pilot_{checkpoint_date.isoformat()}_checkpoint_v"
    )
    expected_id_prefix = (
        f"us_pilot_{checkpoint_date.isoformat()}_"
    )

    if not checkpoint_file.startswith(
        expected_file_prefix
    ):
        raise ValueError(
            "Checkpoint filename/date mismatch"
        )

    if not snapshot_id.startswith(
        expected_id_prefix
    ):
        raise ValueError(
            "Snapshot ID/date mismatch"
        )

    # Detect modification during inspection.
    with path.open("rb") as stream:
        final_digest = hashlib.sha256()

        for chunk in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            final_digest.update(chunk)

    if not hmac.compare_digest(
        final_digest.hexdigest(),
        trusted_anchor_sha256,
    ):
        raise ValueError(
            "Trust anchor changed during verification"
        )

    return anchor
