"""A6c.27: offline checkpoint transition proposal tests.

These tests validate metadata and independently supplied
pins. They do not verify actual SQLite snapshots, update
a trusted head, or authorize production.
"""

from datetime import date
import hashlib
import json

import pytest

from src.data.trusted_checkpoint_advancement import (
    assess_checkpoint_advance,
)


SYMBOLS = ("GOOGL", "AMZN")
PILOT_SHA = hashlib.sha256(b"pilot-manifest").hexdigest()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    raw = (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
        ) + "\n"
    ).encode("utf-8")

    path.write_bytes(raw)
    return digest(raw)


@pytest.fixture
def case(tmp_path):
    current = {
        "schema_version": 1,
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "as_of": "2026-11-02",
        "pilot_manifest_sha256": PILOT_SHA,
        "required_symbols": list(SYMBOLS),
        "previous_checkpoint_sha256": None,
        "snapshot_id": "us_pilot_2026-11-02_2_v1",
        "snapshot_sha256": digest(b"original-snapshot"),
    }

    current_path = tmp_path / "current.json"
    head = write_json(current_path, current)

    candidate = {
        **current,
        "as_of": "2026-11-03",
        "previous_checkpoint_sha256": head,
        "snapshot_id": "us_pilot_2026-11-03_2_v1",
        "snapshot_sha256": digest(b"new-snapshot"),
    }

    candidate_path = tmp_path / "candidate.json"
    candidate_sha = write_json(
        candidate_path, candidate
    )

    return {
        "current": current,
        "current_path": current_path,
        "head": head,
        "candidate": candidate,
        "candidate_path": candidate_path,
        "candidate_sha": candidate_sha,
    }


def assess(case, **overrides):
    args = {
        "current_checkpoint_path": (
            case["current_path"]
        ),
        "candidate_checkpoint_path": (
            case["candidate_path"]
        ),
        "trusted_current_head_sha256": (
            case["head"]
        ),
        "expected_candidate_sha256": (
            case["candidate_sha"]
        ),
        "expected_pilot_manifest_sha256": PILOT_SHA,
        "required_symbols": SYMBOLS,
        "min_candidate_as_of": date(2026, 11, 3),
    }
    args.update(overrides)

    return assess_checkpoint_advance(**args)


def update_candidate(case, **changes):
    candidate = {
        **case["candidate"],
        **changes,
    }

    case["candidate_sha"] = write_json(
        case["candidate_path"],
        candidate,
    )


def test_valid_forward_proposal_accepted(case):
    result = assess(case)

    assert result["status"] == (
        "VALIDATED_PROPOSAL_ONLY"
    )
    assert result["previous_checkpoint_sha256"] == (
        case["head"]
    )
    assert result["candidate_checkpoint_sha256"] == (
        case["candidate_sha"]
    )
    assert result["previous_as_of"] == "2026-11-02"
    assert result["candidate_as_of"] == "2026-11-03"
    assert result["pilot_manifest_sha256"] == PILOT_SHA
    assert result["production_approved"] is False


def test_wrong_independent_current_head_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            trusted_current_head_sha256="0" * 64,
        )


def test_wrong_candidate_pin_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            expected_candidate_sha256="0" * 64,
        )


def test_candidate_predecessor_mismatch_rejected(case):
    update_candidate(
        case,
        previous_checkpoint_sha256="1" * 64,
    )

    with pytest.raises(ValueError):
        assess(case)


def test_same_day_advance_rejected(case):
    update_candidate(case, as_of="2026-11-02")

    with pytest.raises(ValueError):
        assess(
            case,
            min_candidate_as_of=date(2026, 11, 2),
        )


def test_backward_date_rejected(case):
    update_candidate(case, as_of="2026-11-01")

    with pytest.raises(ValueError):
        assess(
            case,
            min_candidate_as_of=date(2026, 11, 1),
        )


def test_candidate_below_minimum_date_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            min_candidate_as_of=date(2026, 11, 4),
        )


def test_wrong_pilot_manifest_pin_rejected(case):
    with pytest.raises(ValueError):
        assess(
            case,
            expected_pilot_manifest_sha256="2" * 64,
        )


def test_symbol_universe_change_rejected(case):
    update_candidate(
        case,
        required_symbols=["GOOGL", "TSLA"],
    )

    with pytest.raises(ValueError):
        assess(case)


def test_production_claim_rejected_even_if_rehashed(case):
    update_candidate(
        case,
        production_approved=True,
    )

    with pytest.raises(ValueError):
        assess(case)


def test_symlinked_current_checkpoint_rejected(
    case, tmp_path
):
    link = tmp_path / "current-link.json"
    link.symlink_to(case["current_path"])

    with pytest.raises(ValueError):
        assess(
            case,
            current_checkpoint_path=link,
        )


def test_duplicate_checkpoint_keys_rejected(case):
    raw = case["candidate_path"].read_bytes()

    assert b'"schema_version": 1' in raw

    raw = raw.replace(
        b'"schema_version": 1',
        (
            b'"schema_version": 1, '
            b'"schema_version": 1'
        ),
        1,
    )

    case["candidate_path"].write_bytes(raw)
    case["candidate_sha"] = digest(raw)

    with pytest.raises(ValueError):
        assess(case)


def test_unexpected_candidate_field_rejected(case):
    update_candidate(
        case,
        production_override=True,
    )

    with pytest.raises(ValueError):
        assess(case)


def test_reused_snapshot_cannot_advance_head(case):
    update_candidate(
        case,
        snapshot_id=case["current"]["snapshot_id"],
        snapshot_sha256=(
            case["current"]["snapshot_sha256"]
        ),
    )

    with pytest.raises(ValueError):
        assess(case)
