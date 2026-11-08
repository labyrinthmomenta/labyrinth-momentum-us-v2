"""A6c.29: offline trusted-head transition request contract.

A verified snapshot proposal is NOT an authorization.
These tests use synthetic authority-state pins and do not
perform signing, trusted-head updates or publication.
"""

import hashlib
import json

import pytest

from src.data.trusted_head_authority import (
    prepare_trusted_head_advancement_request,
)


HEAD = "a" * 64
CANDIDATE = "b" * 64
PILOT = "c" * 64
SNAPSHOT = "d" * 64


def canonical_bytes(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ) + "\n"
    ).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def case(tmp_path):
    authority_state = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "generation": 0,
        "head_checkpoint_sha256": HEAD,
        "head_as_of": "2026-11-02",
        "pilot_manifest_sha256": PILOT,
        "previous_authority_state_sha256": None,
    }

    proposal = {
        "status": "VERIFIED_SNAPSHOT_PROPOSAL_ONLY",
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "previous_checkpoint_sha256": HEAD,
        "candidate_checkpoint_sha256": CANDIDATE,
        "previous_as_of": "2026-11-02",
        "candidate_as_of": "2026-11-03",
        "pilot_manifest_sha256": PILOT,
        "candidate_snapshot_id": (
            "us_pilot_2026-11-03_8475_v1"
        ),
        "candidate_snapshot_sha256": SNAPSHOT,
    }

    path = tmp_path / "authority_state.json"
    raw = canonical_bytes(authority_state)

    path.write_bytes(raw)

    return {
        "path": path,
        "state": authority_state,
        "state_sha": digest(raw),
        "proposal": proposal,
    }


def prepare(case, **overrides):
    args = {
        "authority_state_path": case["path"],
        "trusted_authority_state_sha256": (
            case["state_sha"]
        ),
        "verified_snapshot_proposal": (
            case["proposal"]
        ),
        "expected_current_head_sha256": HEAD,
        "expected_pilot_manifest_sha256": PILOT,
    }

    args.update(overrides)

    return prepare_trusted_head_advancement_request(
        **args
    )


def rewrite_state(case, **changes):
    state = {**case["state"], **changes}
    raw = canonical_bytes(state)

    case["path"].write_bytes(raw)
    case["state_sha"] = digest(raw)


def test_valid_request_requires_authorization(case):
    before = case["path"].read_bytes()

    result = prepare(case)

    assert result["status"] == "AUTHORIZATION_REQUIRED"
    assert result["production_approved"] is False
    assert result["market"] == "US"
    assert result["mode"] == "PILOT_ONLY"

    assert result[
        "previous_authority_state_sha256"
    ] == case["state_sha"]

    assert result[
        "current_head_checkpoint_sha256"
    ] == HEAD

    assert result[
        "candidate_head_checkpoint_sha256"
    ] == CANDIDATE

    assert result["current_generation"] == 0
    assert result["requested_generation"] == 1

    assert result["current_as_of"] == "2026-11-02"
    assert result["candidate_as_of"] == "2026-11-03"

    assert result["pilot_manifest_sha256"] == PILOT
    assert result["candidate_snapshot_sha256"] == SNAPSHOT

    assert result["proposal_sha256"] == digest(
        canonical_bytes(case["proposal"])
    )

    assert case["path"].read_bytes() == before
    assert prepare(case) == result


def test_wrong_authority_state_pin_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            trusted_authority_state_sha256="0" * 64,
        )


def test_wrong_independent_current_head_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            expected_current_head_sha256="0" * 64,
        )


def test_wrong_proposal_predecessor_rejected(case):
    case["proposal"]["previous_checkpoint_sha256"] = (
        "1" * 64
    )

    with pytest.raises(ValueError):
        prepare(case)


def test_metadata_only_proposal_rejected(case):
    case["proposal"]["status"] = (
        "VALIDATED_PROPOSAL_ONLY"
    )

    with pytest.raises(ValueError):
        prepare(case)


def test_production_claim_rejected(case):
    case["proposal"]["production_approved"] = True

    with pytest.raises(ValueError):
        prepare(case)


@pytest.mark.parametrize(
    "candidate_date",
    ["2026-11-02", "2026-11-01"],
)
def test_nonforward_candidate_rejected(
    case, candidate_date
):
    case["proposal"]["candidate_as_of"] = (
        candidate_date
    )

    with pytest.raises(ValueError):
        prepare(case)


def test_wrong_pilot_manifest_rejected(case):
    with pytest.raises(ValueError):
        prepare(
            case,
            expected_pilot_manifest_sha256="0" * 64,
        )


def test_boolean_generation_rejected(case):
    rewrite_state(case, generation=True)

    with pytest.raises(ValueError):
        prepare(case)


def test_duplicate_authority_json_keys_rejected(case):
    raw = case["path"].read_bytes()

    assert b'"generation":0' in raw

    raw = raw.replace(
        b'"generation":0',
        b'"generation":0,"generation":0',
        1,
    )

    case["path"].write_bytes(raw)
    case["state_sha"] = digest(raw)

    with pytest.raises(ValueError):
        prepare(case)


def test_symlinked_authority_state_rejected(
    case, tmp_path
):
    link = tmp_path / "state-link.json"
    link.symlink_to(case["path"])

    with pytest.raises(
        (ValueError, FileNotFoundError)
    ):
        prepare(
            case,
            authority_state_path=link,
        )


def test_missing_authority_state_rejected(
    case, tmp_path
):
    with pytest.raises(
        (ValueError, FileNotFoundError)
    ):
        prepare(
            case,
            authority_state_path=(
                tmp_path / "missing_state.json"
            ),
        )


def test_snapshot_id_date_mismatch_rejected(case):
    case["proposal"]["candidate_snapshot_id"] = (
        "us_pilot_2026-11-02_8475_v1"
    )

    with pytest.raises(ValueError):
        prepare(case)


def test_unexpected_proposal_field_rejected(case):
    case["proposal"]["authority_approved"] = True

    with pytest.raises(ValueError):
        prepare(case)
