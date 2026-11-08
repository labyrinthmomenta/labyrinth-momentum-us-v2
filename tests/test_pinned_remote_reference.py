"""A6c.26: externally pinned offline recovery reference.

These tests do not access a real cloud service or
authorize production execution.
"""

from datetime import date
import hashlib
import json

import pytest

from src.data.pinned_remote_reference import (
    load_pinned_remote_recovery_reference,
)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def case(tmp_path):
    bundle = sha256(b"offline-bundle")
    anchor = sha256(b"offline-anchor")
    checkpoint = sha256(b"offline-checkpoint")
    pilot = sha256(b"offline-pilot")

    reference = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "approval_status": "OFFLINE_CANDIDATE",
        "production_approved": False,
        "as_of": "2026-11-02",
        "bundle_sha256": bundle,
        "object_key": f"sha256/{bundle}.zip",
        "anchor_sha256": anchor,
        "checkpoint_sha256": checkpoint,
        "pilot_manifest_sha256": pilot,
        "previous_checkpoint_sha256": None,
    }

    path = tmp_path / "reference.json"

    raw = (
        json.dumps(
            reference,
            sort_keys=True,
            indent=2,
        ) + "\n"
    ).encode("utf-8")

    path.write_bytes(raw)

    return {
        "path": path,
        "reference": reference,
        "trusted_sha256": sha256(raw),
        "head": checkpoint,
        "pilot": pilot,
        "bundle": bundle,
    }


def load(case, **overrides):
    args = {
        "reference_path": case["path"],
        "trusted_reference_sha256": (
            case["trusted_sha256"]
        ),
        "trusted_head_checkpoint_sha256": (
            case["head"]
        ),
        "expected_pilot_manifest_sha256": (
            case["pilot"]
        ),
        "min_as_of": date(2026, 11, 2),
    }

    args.update(overrides)

    return load_pinned_remote_recovery_reference(**args)


def rewrite(case, reference):
    raw = (
        json.dumps(
            reference,
            sort_keys=True,
            indent=2,
        ) + "\n"
    ).encode("utf-8")

    case["path"].write_bytes(raw)

    return sha256(raw)


def test_valid_offline_reference_is_accepted(case):
    result = load(case)

    assert result == case["reference"]
    assert result["production_approved"] is False
    assert result["approval_status"] == (
        "OFFLINE_CANDIDATE"
    )
    assert result["checkpoint_sha256"] == case["head"]
    assert result["bundle_sha256"] == case["bundle"]


def test_wrong_independent_reference_pin_rejected(case):
    with pytest.raises(ValueError):
        load(
            case,
            trusted_reference_sha256="0" * 64,
        )


def test_modified_reference_rejected(case):
    with case["path"].open("ab") as output:
        output.write(b" ")

    with pytest.raises(ValueError):
        load(case)


def test_different_checkpoint_head_rejected(case):
    with pytest.raises(ValueError):
        load(
            case,
            trusted_head_checkpoint_sha256=(
                sha256(b"another-checkpoint")
            ),
        )


def test_stale_reference_date_rejected(case):
    with pytest.raises(ValueError):
        load(
            case,
            min_as_of=date(2026, 11, 3),
        )


def test_production_approval_claim_rejected(case):
    modified = dict(case["reference"])
    modified["production_approved"] = True

    updated_pin = rewrite(case, modified)

    with pytest.raises(ValueError):
        load(
            case,
            trusted_reference_sha256=updated_pin,
        )


def test_wrong_content_address_rejected(case):
    modified = dict(case["reference"])
    modified["object_key"] = (
        "sha256/" + "0" * 64 + ".zip"
    )

    updated_pin = rewrite(case, modified)

    with pytest.raises(ValueError):
        load(
            case,
            trusted_reference_sha256=updated_pin,
        )


def test_duplicate_json_keys_rejected(case):
    raw = case["path"].read_bytes()

    assert b'"schema_version": 1' in raw

    raw = raw.replace(
        b'"schema_version": 1',
        (
            b'"schema_version": 1, '
            b'"schema_version": 1'
        ),
        1,
    )

    case["path"].write_bytes(raw)

    with pytest.raises(ValueError):
        load(
            case,
            trusted_reference_sha256=sha256(raw),
        )


def test_symlinked_reference_rejected(case, tmp_path):
    link = tmp_path / "reference-link.json"
    link.symlink_to(case["path"])

    with pytest.raises(ValueError):
        load(case, reference_path=link)


def test_unexpected_reference_field_rejected(case):
    modified = dict(case["reference"])
    modified["production_override"] = True

    updated_pin = rewrite(case, modified)

    with pytest.raises(ValueError):
        load(
            case,
            trusted_reference_sha256=updated_pin,
        )


def test_wrong_pilot_manifest_pin_rejected(case):
    with pytest.raises(ValueError):
        load(
            case,
            expected_pilot_manifest_sha256=(
                sha256(b"untrusted-pilot")
            ),
        )
