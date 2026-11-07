"""A6c.22 offline operational readiness contracts."""

import hashlib
import json
from datetime import date, datetime, timezone

import pytest

from src.data.daily_operations_policy import (
    evaluate_daily_preflight,
)


WINTER_READY = datetime(
    2026, 11, 3, 23, 30, tzinfo=timezone.utc
)

SUMMER_READY = datetime(
    2026, 7, 15, 22, 30, tzinfo=timezone.utc
)


@pytest.fixture
def pilot(tmp_path):
    config_path = tmp_path / "us.json"
    manifest_path = tmp_path / "pilot_manifest.json"

    config = {
        "market": "US",
        "timezone": "America/New_York",
        "status": "BOOTSTRAP_ONLY",
        "publication_enabled": False,
        "vcp_production_enabled": False,
    }

    manifest = {
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "symbols": ["GOOGL", "NIO", "OPEN"],
    }

    config_path.write_text(
        json.dumps(config),
        encoding="utf-8",
    )

    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    digest = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()

    return {
        "config_path": config_path,
        "manifest_path": manifest_path,
        "expected_manifest_sha256": digest,
        "at": WINTER_READY,
    }


def evaluate(pilot, **overrides):
    args = dict(pilot)
    args.update(overrides)

    return evaluate_daily_preflight(**args)


def rewrite_manifest(pilot, content):
    path = pilot["manifest_path"]

    path.write_text(
        json.dumps(content, indent=2) + "\n",
        encoding="utf-8",
    )

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_regular_winter_session_ready(pilot):
    result = evaluate(pilot)

    assert result.decision == "READY"
    assert result.as_of == date(2026, 11, 3)
    assert result.symbols == ("GOOGL", "NIO", "OPEN")
    assert result.reason


def test_summer_daylight_saving_ready(pilot):
    result = evaluate(pilot, at=SUMMER_READY)

    assert result.decision == "READY"
    assert result.as_of == date(2026, 7, 15)


def test_before_ny_18_window_is_skipped(pilot):
    # 22:59 UTC = 17:59 New York standard time.
    at = datetime(
        2026, 11, 3, 22, 59,
        tzinfo=timezone.utc,
    )

    result = evaluate(pilot, at=at)

    assert result.decision == "SKIP_EARLY"
    assert result.as_of is None


def test_weekend_has_no_session(pilot):
    at = datetime(
        2026, 11, 7, 23, 30,
        tzinfo=timezone.utc,
    )

    result = evaluate(pilot, at=at)

    assert result.decision == "SKIP_NO_SESSION"
    assert result.as_of is None


def test_thanksgiving_holiday_is_skipped(pilot):
    at = datetime(
        2026, 11, 26, 23, 30,
        tzinfo=timezone.utc,
    )

    result = evaluate(pilot, at=at)

    assert result.decision == "SKIP_NO_SESSION"
    assert result.as_of is None


def test_post_thanksgiving_early_close(pilot):
    # Friday after Thanksgiving: shortened NYSE session.
    # 23:30 UTC = 18:30 EST, safely after the close.
    at = datetime(
        2026, 11, 27, 23, 30,
        tzinfo=timezone.utc,
    )

    result = evaluate(pilot, at=at)

    assert result.decision == "READY"
    assert result.as_of == date(2026, 11, 27)


def test_manifest_tampering_rejected(pilot):
    # Keep the previously reviewed SHA-256 unchanged.
    original_digest = pilot["expected_manifest_sha256"]

    rewrite_manifest(
        pilot,
        {
            "market": "US",
            "mode": "PILOT_ONLY",
            "production_approved": False,
            "symbols": ["GOOGL", "NIO", "TSLA"],
        },
    )

    assert pilot["expected_manifest_sha256"] == original_digest

    with pytest.raises(ValueError):
        evaluate(pilot)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "PRODUCTION"),
        ("publication_enabled", True),
        ("vcp_production_enabled", True),
    ],
)
def test_unsafe_config_rejected(pilot, field, value):
    path = pilot["config_path"]
    config = json.loads(path.read_text(encoding="utf-8"))

    config[field] = value
    path.write_text(
        json.dumps(config),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        evaluate(pilot)


def test_manifest_cannot_claim_production_approval(pilot):
    manifest = {
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": True,
        "symbols": ["GOOGL", "NIO"],
    }

    digest = rewrite_manifest(pilot, manifest)

    with pytest.raises(ValueError):
        evaluate(
            pilot,
            expected_manifest_sha256=digest,
        )


def test_more_than_25_pilot_symbols_rejected(pilot):
    manifest = {
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "symbols": [
            f"SYM{i:03d}" for i in range(26)
        ],
    }

    digest = rewrite_manifest(pilot, manifest)

    with pytest.raises(ValueError):
        evaluate(
            pilot,
            expected_manifest_sha256=digest,
        )


def test_duplicate_symbols_rejected(pilot):
    manifest = {
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "symbols": ["GOOGL", "NIO", "GOOGL"],
    }

    digest = rewrite_manifest(pilot, manifest)

    with pytest.raises(ValueError):
        evaluate(
            pilot,
            expected_manifest_sha256=digest,
        )


def test_blank_symbol_rejected(pilot):
    manifest = {
        "market": "US",
        "mode": "PILOT_ONLY",
        "production_approved": False,
        "symbols": ["GOOGL", "  "],
    }

    digest = rewrite_manifest(pilot, manifest)

    with pytest.raises(ValueError):
        evaluate(
            pilot,
            expected_manifest_sha256=digest,
        )


def test_production_manifest_mode_rejected(pilot):
    manifest = {
        "market": "US",
        "mode": "PRODUCTION",
        "production_approved": False,
        "symbols": ["GOOGL"],
    }

    digest = rewrite_manifest(pilot, manifest)

    with pytest.raises(ValueError):
        evaluate(
            pilot,
            expected_manifest_sha256=digest,
        )


def test_naive_datetime_rejected(pilot):
    with pytest.raises(ValueError):
        evaluate(
            pilot,
            at=datetime(2026, 11, 3, 23, 30),
        )
