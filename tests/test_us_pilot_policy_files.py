"""Pinned US pilot manifest and operations policy contracts."""

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.data.daily_operations_policy import (
    evaluate_daily_preflight,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/us_pilot_manifest.json"
OPERATIONS = ROOT / "config/us_daily_operations.json"
US_CONFIG = ROOT / "config/us.json"

EXPECTED_SHA256 = (
    "0b35135a9e55f9ff974dcab795f9ba52"
    "d8522b8fa50a033bc340d74acccffebd"
)

EXPECTED_SYMBOLS = (
    "GOOGL", "AMZN", "META", "TSLA", "NFLX",
    "COIN", "UBER", "HOOD", "PFE", "T",
    "KO", "BAC", "NIO", "LCID", "PTON",
    "OPEN", "FUBO", "BB", "NOK", "ACHR",
    "JOBY", "RGTI", "KOSS", "CRSP", "IONQ",
)

AT = datetime(
    2026, 11, 3, 23, 30,
    tzinfo=timezone.utc,
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def pinned_sha():
    return read_json(OPERATIONS)["expected_manifest_sha256"]


def test_pilot_contains_exactly_25_reviewed_symbols():
    manifest = read_json(MANIFEST)

    assert manifest["market"] == "US"
    assert manifest["mode"] == "PILOT_ONLY"
    assert manifest["production_approved"] is False
    assert tuple(manifest["symbols"]) == EXPECTED_SYMBOLS


def test_manifest_digest_matches_independent_pin():
    operations = read_json(OPERATIONS)

    assert operations["manifest_path"] == (
        "config/us_pilot_manifest.json"
    )

    assert operations["expected_manifest_sha256"] == (
        EXPECTED_SHA256
    )

    actual = hashlib.sha256(
        MANIFEST.read_bytes()
    ).hexdigest()

    assert actual == EXPECTED_SHA256


def test_operational_execution_stays_disabled():
    operations = read_json(OPERATIONS)

    assert operations["market"] == "US"
    assert operations["mode"] == "PILOT_ONLY"
    assert operations["timezone"] == "America/New_York"

    assert operations["not_before_local"] == "18:00"
    assert operations[
        "minimum_close_delay_minutes"
    ] == 120

    assert operations["live_provider_enabled"] is False
    assert operations["scheduled_execution_enabled"] is False
    assert operations["publication_enabled"] is False


def test_pinned_manifest_offline_preflight_ready():
    result = evaluate_daily_preflight(
        config_path=US_CONFIG,
        manifest_path=MANIFEST,
        expected_manifest_sha256=pinned_sha(),
        at=AT,
    )

    assert result.decision == "READY"
    assert result.as_of == date(2026, 11, 3)
    assert result.symbols == EXPECTED_SYMBOLS


def test_tampered_manifest_fails_closed(tmp_path):
    manifest = read_json(MANIFEST)
    manifest["symbols"][0] = "TSLA"

    tampered = tmp_path / "tampered_manifest.json"
    tampered.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="SHA-256"):
        evaluate_daily_preflight(
            config_path=US_CONFIG,
            manifest_path=tampered,
            expected_manifest_sha256=pinned_sha(),
            at=AT,
        )


def test_unsafe_us_config_fails_closed(tmp_path):
    config = read_json(US_CONFIG)
    config["publication_enabled"] = True

    unsafe = tmp_path / "unsafe_us.json"
    unsafe.write_text(
        json.dumps(config),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        evaluate_daily_preflight(
            config_path=unsafe,
            manifest_path=MANIFEST,
            expected_manifest_sha256=pinned_sha(),
            at=AT,
        )
