"""A6c.23: pinned bootstrap checkpoint trust contracts."""

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from src.data.checkpoint_anchor import (
    load_bootstrap_checkpoint_anchor,
)


ROOT = Path(__file__).resolve().parents[1]
ANCHOR = ROOT / "config/us_bootstrap_checkpoint.json"

PIN = (
    "e1fb800922d2f4de88f93c442b36d8e"
    "20c7f850f8879310820bbc1128464a155"
)

CHECKPOINT_PIN = (
    "71aa27cb1bdc93ba0f7890dd4a6e511e"
    "b859002f70ad9ae2349f8c3a1f17444c"
)


def load(path=ANCHOR, *, trusted_sha=PIN, minimum=None):
    return load_bootstrap_checkpoint_anchor(
        anchor_path=path,
        trusted_anchor_sha256=trusted_sha,
        min_as_of=minimum,
    )


def edited_anchor(tmp_path, field, value):
    content = json.loads(ANCHOR.read_text())
    content[field] = value
    path = tmp_path / "modified_anchor.json"

    raw = (
        json.dumps(content, indent=2) + "\n"
    ).encode("utf-8")

    path.write_bytes(raw)

    return path, hashlib.sha256(raw).hexdigest()


def test_original_anchor_matches_independent_pin():
    assert hashlib.sha256(
        ANCHOR.read_bytes()
    ).hexdigest() == PIN

    result = load()

    assert result["checkpoint_sha256"] == CHECKPOINT_PIN
    assert result["approval_status"] == "OFFLINE_CANDIDATE"
    assert result["production_approved"] is False
    assert result["as_of"] == "2026-11-02"


def test_modified_anchor_rejected_by_original_pin(tmp_path):
    path, _ = edited_anchor(
        tmp_path,
        "checkpoint_sha256",
        "0" * 64,
    )

    with pytest.raises(ValueError):
        load(path)


def test_wrong_external_anchor_pin_rejected():
    with pytest.raises(ValueError):
        load(trusted_sha="0" * 64)


def test_rehashed_production_flag_still_rejected(tmp_path):
    path, digest = edited_anchor(
        tmp_path,
        "production_approved",
        True,
    )

    with pytest.raises(ValueError):
        load(path, trusted_sha=digest)


def test_rehashed_approval_claim_still_rejected(tmp_path):
    path, digest = edited_anchor(
        tmp_path,
        "approval_status",
        "APPROVED",
    )

    with pytest.raises(ValueError):
        load(path, trusted_sha=digest)


def test_rehashed_predecessor_rejected_for_genesis(tmp_path):
    path, digest = edited_anchor(
        tmp_path,
        "previous_checkpoint_sha256",
        "b" * 64,
    )

    with pytest.raises(ValueError):
        load(path, trusted_sha=digest)


def test_unexpected_anchor_schema_rejected(tmp_path):
    path, digest = edited_anchor(
        tmp_path,
        "scheduled_execution_enabled",
        True,
    )

    with pytest.raises(ValueError):
        load(path, trusted_sha=digest)


def test_old_bootstrap_rejected_for_new_minimum_date():
    with pytest.raises(ValueError):
        load(minimum=date(2026, 11, 3))


def test_checkpoint_path_traversal_rejected(tmp_path):
    path, digest = edited_anchor(
        tmp_path,
        "checkpoint_file",
        "../other_checkpoint.json",
    )

    with pytest.raises(ValueError):
        load(path, trusted_sha=digest)
