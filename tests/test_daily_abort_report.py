"""Offline contracts for unexpected daily ingestion failures."""

import json
from datetime import date, datetime, timezone

import pytest

from src.data.daily_run_report import write_aborted_run_report
from src.data.daily_run_lock import hold_daily_ingestion_lock
from src.data import daily_ingestion_runner as runner


AS_OF = date(2026, 11, 2)

GENERATED_AT = datetime(
    2026, 11, 3, 10, 30,
    tzinfo=timezone.utc,
)


def test_aborted_report_preserves_unknown_progress(tmp_path):
    path = tmp_path / "reports" / "aborted.json"

    result = write_aborted_run_report(
        as_of=AS_OF,
        report_path=path,
        symbols=("AAPL", "MSFT"),
        error=RuntimeError("Unexpected storage failure"),
        phase="BATCH_EXECUTION",
        generated_at=GENERATED_AT,
    )

    assert result == path
    assert path.is_file()

    report = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert report["schema_version"] == 1
    assert report["market"] == "US"
    assert report["as_of"] == "2026-11-02"
    assert report["run_status"] == "ABORTED"
    assert report["phase"] == "BATCH_EXECUTION"

    assert report["requested_symbols"] == [
        "AAPL", "MSFT"
    ]

    assert report["summary"]["requested"] == 2

    # Unexpected failures can occur after partial writes.
    # Never invent completion counts.
    assert report["summary"]["attempted"] is None
    assert report["summary"]["unprocessed"] is None
    assert report["summary"]["counts"] is None

    assert report["results"] is None
    assert report["unprocessed_symbols"] is None

    assert report["error"]["type"] == "RuntimeError"
    assert report["error"]["message"] == (
        "Unexpected storage failure"
    )


def test_aborted_report_cannot_overwrite_existing(tmp_path):
    path = tmp_path / "protected.json"
    path.write_text('{"protected": true}', encoding="utf-8")

    before = path.read_bytes()

    with pytest.raises(FileExistsError):
        write_aborted_run_report(
            as_of=AS_OF,
            report_path=path,
            symbols=("AAPL",),
            error=RuntimeError("Failure"),
            phase="BATCH_EXECUTION",
            generated_at=GENERATED_AT,
        )

    assert path.read_bytes() == before


def test_aborted_report_rejects_naive_datetime(tmp_path):
    path = tmp_path / "invalid.json"

    with pytest.raises(ValueError):
        write_aborted_run_report(
            as_of=AS_OF,
            report_path=path,
            symbols=("AAPL",),
            error=RuntimeError("Failure"),
            phase="BATCH_EXECUTION",
            generated_at=datetime(2026, 11, 3, 10, 30),
        )

    assert not path.exists()


def test_runner_records_abort_and_reraises(
    tmp_path, monkeypatch
):
    db = tmp_path / "pilot.db"
    db.touch()

    config = tmp_path / "us.json"
    config.write_text(
        json.dumps({
            "market": "US",
            "status": "BOOTSTRAP_ONLY",
            "publication_enabled": False,
            "vcp_production_enabled": False,
        }),
        encoding="utf-8",
    )

    report_path = tmp_path / "fatal_report.json"

    def offline_provider(symbol, *, start, end):
        raise AssertionError(
            "Provider must not be called"
        )

    def fake_fetcher(*args, **kwargs):
        return offline_provider

    def unexpected_batch_failure(*args, **kwargs):
        raise RuntimeError("Simulated fatal batch failure")

    monkeypatch.setattr(
        runner,
        "make_incremental_history_fetcher",
        fake_fetcher,
    )

    monkeypatch.setattr(
        runner,
        "run_daily_batches",
        unexpected_batch_failure,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated fatal batch failure",
    ):
        runner.run_daily_ingestion(
            db_path=db,
            config_path=config,
            report_path=report_path,
            symbols=["AAPL", "MSFT"],
            full_start=date(2025, 7, 1),
            provider=offline_provider,
            at=datetime(
                2026, 11, 3, 20, 0,
                tzinfo=timezone.utc,
            ),
        )

    assert report_path.is_file()

    report = json.loads(
        report_path.read_text(encoding="utf-8")
    )

    assert report["run_status"] == "ABORTED"
    assert report["as_of"] == "2026-11-02"
    assert report["requested_symbols"] == [
        "AAPL", "MSFT"
    ]

    assert report["summary"]["attempted"] is None
    assert report["error"]["type"] == "RuntimeError"

    # The failure must not leave an active lock.
    with hold_daily_ingestion_lock(db):
        pass
