"""Offline contracts for durable daily ingestion audit reports."""

import json
from datetime import date, datetime, timezone

import pytest

from src.data.batch_ingestion import BatchResult
from src.data.daily_batch_orchestrator import DailyBatchResult
from src.data.daily_run_report import write_daily_run_report
from src.data.ingestion_runner import IngestionResult


AS_OF = date(2026, 11, 2)
GENERATED_AT = datetime(
    2026, 11, 3, 10, 30,
    tzinfo=timezone.utc,
)


def success(symbol):
    return IngestionResult(
        symbol=symbol,
        status="SUCCESS",
        eligibility="PASS",
        rows=338,
        reason="Validated and stored",
    )


def skipped(symbol):
    return IngestionResult(
        symbol=symbol,
        status="SKIPPED",
        eligibility=None,
        rows=0,
        reason="Previously completed",
    )


def rate_limited(symbol):
    return IngestionResult(
        symbol=symbol,
        status="FAILED",
        eligibility=None,
        rows=0,
        reason="Yahoo rate limited",
        error_category="RATE_LIMIT_ERROR",
        retryable=False,
    )


def interrupted_result():
    batch = BatchResult(
        results=(
            success("GOOGL"),
            rate_limited("NIO"),
        ),
        requested=3,
        stopped_early=True,
        unprocessed_symbols=("OPEN",),
    )

    return DailyBatchResult(
        batch_results=(batch,),
        requested=3,
        stopped_early=True,
        unprocessed_symbols=("OPEN",),
    )


def completed_result():
    batch = BatchResult(
        results=(
            skipped("AAPL"),
            skipped("MSFT"),
        ),
        requested=2,
    )

    return DailyBatchResult(
        batch_results=(batch,),
        requested=2,
    )


def test_interrupted_run_report_is_persisted(tmp_path):
    path = tmp_path / "reports" / "run_001.json"

    output = write_daily_run_report(
        interrupted_result(),
        as_of=AS_OF,
        report_path=path,
        generated_at=GENERATED_AT,
    )

    assert output == path
    assert path.is_file()

    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["schema_version"] == 1
    assert report["market"] == "US"
    assert report["as_of"] == "2026-11-02"
    assert report["generated_at_utc"] == (
        "2026-11-03T10:30:00+00:00"
    )

    assert report["run_status"] == "INTERRUPTED"

    summary = report["summary"]

    assert summary["requested"] == 3
    assert summary["attempted"] == 2
    assert summary["unprocessed"] == 1

    assert summary["counts"] == {
        "SUCCESS": 1,
        "SKIPPED": 0,
        "FAILED": 1,
    }

    assert summary["error_categories"] == {
        "RATE_LIMIT_ERROR": 1,
    }

    assert report["unprocessed_symbols"] == ["OPEN"]

    assert [item["symbol"] for item in report["results"]] == [
        "GOOGL",
        "NIO",
    ]


def test_completed_skip_only_report(tmp_path):
    path = tmp_path / "completed.json"

    write_daily_run_report(
        completed_result(),
        as_of=AS_OF,
        report_path=path,
        generated_at=GENERATED_AT,
    )

    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["run_status"] == "COMPLETED"

    assert report["summary"]["counts"] == {
        "SUCCESS": 0,
        "SKIPPED": 2,
        "FAILED": 0,
    }

    assert report["summary"]["attempted"] == 2
    assert report["summary"]["unprocessed"] == 0

    # Skipped symbols do not carry eligibility
    # in the existing BatchResult interface.
    assert report["summary"][
        "eligibility_counts_new_successes"
    ] == {
        "PASS": 0,
        "FILTER_FAIL": 0,
        "DATA_INCOMPLETE": 0,
    }


def test_existing_report_is_not_overwritten(tmp_path):
    path = tmp_path / "existing.json"
    path.write_text(
        '{"protected": true}',
        encoding="utf-8",
    )

    original = path.read_bytes()

    with pytest.raises(FileExistsError):
        write_daily_run_report(
            completed_result(),
            as_of=AS_OF,
            report_path=path,
            generated_at=GENERATED_AT,
        )

    assert path.read_bytes() == original


def test_naive_report_timestamp_rejected(tmp_path):
    path = tmp_path / "invalid.json"

    with pytest.raises(ValueError):
        write_daily_run_report(
            completed_result(),
            as_of=AS_OF,
            report_path=path,
            generated_at=datetime(2026, 11, 3, 10, 30),
        )

    assert not path.exists()


def test_inconsistent_result_counts_rejected(tmp_path):
    path = tmp_path / "inconsistent.json"

    batch = BatchResult(
        results=(skipped("AAPL"),),
        requested=1,
    )

    # Deliberately inconsistent: three requested,
    # one attempted, but no unprocessed symbols.
    inconsistent = DailyBatchResult(
        batch_results=(batch,),
        requested=3,
        stopped_early=False,
        unprocessed_symbols=(),
    )

    with pytest.raises(ValueError):
        write_daily_run_report(
            inconsistent,
            as_of=AS_OF,
            report_path=path,
            generated_at=GENERATED_AT,
        )

    assert not path.exists()
