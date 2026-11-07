"""A6c.22: mandatory daily-runner authorization contracts."""

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import src.data.daily_ingestion_runner as runner
from src.data.batch_ingestion import BatchResult
from src.data.daily_batch_orchestrator import DailyBatchResult
from src.data.ingestion_runner import IngestionResult


ROOT = Path(__file__).resolve().parents[1]
US_CONFIG = ROOT / "config/us.json"
OPERATIONS = ROOT / "config/us_daily_operations.json"

READY_AT = datetime(
    2026, 11, 3, 23, 30,
    tzinfo=timezone.utc,
)


@pytest.fixture
def pilot(tmp_path):
    db = tmp_path / "pilot.db"
    db.touch()

    return {
        "db_path": db,
        "config_path": US_CONFIG,
        "report_path": tmp_path / "report.json",
        "full_start": date(2025, 7, 1),
        "provider": offline_provider,
        "symbols": ["GOOGL", "NIO"],
        "at": READY_AT,
        "batch_size": 2,
    }


def offline_provider(symbol, *, start, end):
    raise AssertionError(
        "Offline test must not request market data"
    )


def forbid_ingestion(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Ingestion started without authorization"
        )

    monkeypatch.setattr(
        runner,
        "make_incremental_history_fetcher",
        forbidden,
    )


def test_approved_subset_reaches_ingestion(pilot, monkeypatch):
    calls = []

    def fake_fetcher(db_path, **kwargs):
        calls.append("fetcher")
        return offline_provider

    def skipped(symbol):
        return IngestionResult(
            symbol=symbol,
            status="SKIPPED",
            eligibility=None,
            rows=0,
            reason="Previously completed",
        )

    result = DailyBatchResult(
        batch_results=(
            BatchResult(
                results=(
                    skipped("GOOGL"),
                    skipped("NIO"),
                ),
                requested=2,
            ),
        ),
        requested=2,
    )

    def fake_batches(db_path, symbols, **kwargs):
        calls.append("batches")
        assert tuple(symbols) == ("GOOGL", "NIO")
        assert kwargs["as_of"] == date(2026, 11, 3)
        return result

    def fake_report(*args, **kwargs):
        calls.append("report")
        return Path(kwargs["report_path"])

    monkeypatch.setattr(
        runner,
        "make_incremental_history_fetcher",
        fake_fetcher,
    )
    monkeypatch.setattr(
        runner,
        "run_daily_batches",
        fake_batches,
    )
    monkeypatch.setattr(
        runner,
        "write_daily_run_report",
        fake_report,
    )

    outcome = runner.run_daily_ingestion(**pilot)

    assert outcome.decision == "READY"
    assert outcome.as_of == date(2026, 11, 3)
    assert outcome.result is result
    assert calls == ["fetcher", "batches", "report"]


def test_symbol_outside_manifest_rejected(pilot, monkeypatch):
    forbid_ingestion(monkeypatch)

    pilot["symbols"] = ["GOOGL", "AAPL"]

    with pytest.raises(ValueError):
        runner.run_daily_ingestion(**pilot)

    assert not pilot["report_path"].exists()


@pytest.mark.parametrize(
    "at,expected_decision",
    [
        (
            datetime(
                2026, 11, 3, 22, 59,
                tzinfo=timezone.utc,
            ),
            "SKIP_EARLY",
        ),
        (
            datetime(
                2026, 11, 7, 23, 30,
                tzinfo=timezone.utc,
            ),
            "SKIP_NO_SESSION",
        ),
    ],
)
def test_ineligible_session_never_ingests(
    pilot, monkeypatch, at, expected_decision
):
    forbid_ingestion(monkeypatch)

    outcome = runner.run_daily_ingestion(
        **{**pilot, "at": at}
    )

    assert outcome.decision == expected_decision
    assert outcome.as_of is None
    assert outcome.result is None
    assert outcome.report_path is None
    assert not pilot["report_path"].exists()


def test_pinned_manifest_hash_mismatch_rejected(
    pilot, monkeypatch, tmp_path
):
    forbid_ingestion(monkeypatch)

    operations = json.loads(
        OPERATIONS.read_text(encoding="utf-8")
    )

    operations["expected_manifest_sha256"] = "0" * 64

    modified = tmp_path / "operations.json"
    modified.write_text(
        json.dumps(operations),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        runner,
        "OPERATIONS_CONFIG_PATH",
        modified,
    )

    with pytest.raises(ValueError):
        runner.run_daily_ingestion(**pilot)

    assert not pilot["report_path"].exists()


@pytest.mark.parametrize(
    "field",
    [
        "live_provider_enabled",
        "scheduled_execution_enabled",
        "publication_enabled",
    ],
)
def test_disabled_operations_flags_are_enforced(
    pilot, monkeypatch, tmp_path, field
):
    forbid_ingestion(monkeypatch)

    operations = json.loads(
        OPERATIONS.read_text(encoding="utf-8")
    )

    operations[field] = True

    modified = tmp_path / f"{field}.json"
    modified.write_text(
        json.dumps(operations),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        runner,
        "OPERATIONS_CONFIG_PATH",
        modified,
    )

    with pytest.raises(ValueError):
        runner.run_daily_ingestion(**pilot)

    assert not pilot["report_path"].exists()


def test_missing_operations_config_fails_closed(
    pilot, monkeypatch, tmp_path
):
    forbid_ingestion(monkeypatch)

    missing = tmp_path / "missing_operations.json"

    monkeypatch.setattr(
        runner,
        "OPERATIONS_CONFIG_PATH",
        missing,
    )

    with pytest.raises(FileNotFoundError):
        runner.run_daily_ingestion(**pilot)

    assert not missing.exists()


def test_manifest_path_cannot_be_redirected(
    pilot, monkeypatch, tmp_path
):
    forbid_ingestion(monkeypatch)

    operations = json.loads(
        OPERATIONS.read_text(encoding="utf-8")
    )

    operations["manifest_path"] = (
        "../../unapproved_manifest.json"
    )

    modified = tmp_path / "redirected_operations.json"
    modified.write_text(
        json.dumps(operations),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        runner,
        "OPERATIONS_CONFIG_PATH",
        modified,
    )

    with pytest.raises(ValueError):
        runner.run_daily_ingestion(**pilot)

    assert not pilot["report_path"].exists()
