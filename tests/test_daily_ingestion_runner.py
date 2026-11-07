"""Safety and integration contracts for the daily US pilot runner."""

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.data import daily_ingestion_runner as runner
from src.data.batch_ingestion import BatchResult
from src.data.daily_batch_orchestrator import DailyBatchResult
from src.data.ingestion_runner import IngestionResult


AT = datetime(2026, 11, 2, 23, 30, tzinfo=timezone.utc)
AS_OF = date(2026, 11, 2)
FULL_START = date(2025, 7, 1)


def offline_provider(symbol, *, start, end):
    raise AssertionError("Unexpected provider request")


@pytest.fixture
def pilot(tmp_path):
    db = tmp_path / "pilot.db"
    db.touch()

    config = tmp_path / "us.json"
    config.write_text(
        json.dumps({
            "market": "US",
            "timezone": "America/New_York",
            "status": "BOOTSTRAP_ONLY",
            "publication_enabled": False,
            "vcp_production_enabled": False,
        }),
        encoding="utf-8",
    )

    return {
        "db_path": db,
        "config_path": config,
        "report_path": tmp_path / "report.json",
    }


def execute(pilot, **overrides):
    params = {
        **pilot,
        "symbols": ["GOOGL", "NIO"],
        "at": AT,
        "full_start": FULL_START,
        "provider": offline_provider,
        "batch_size": 5,
    }
    params.update(overrides)
    return runner.run_daily_ingestion(**params)


def test_connects_all_four_components(monkeypatch, pilot):
    events = []

    def fake_clock(*, at, settlement_delay_minutes):
        events.append("session_clock")
        assert at == AT
        assert settlement_delay_minutes == 60
        return AS_OF

    def fake_incremental(db_path, **kwargs):
        events.append("incremental_fetcher")
        assert Path(db_path) == pilot["db_path"]
        assert kwargs["as_of"] == AS_OF
        assert kwargs["full_start"] == FULL_START
        assert kwargs["overlap_sessions"] == 30
        assert kwargs["provider"] is offline_provider
        return offline_provider

    def skipped(symbol):
        return IngestionResult(
            symbol=symbol,
            status="SKIPPED",
            eligibility=None,
            rows=0,
            reason="Previously completed",
        )

    batch_result = DailyBatchResult(
        batch_results=(
            BatchResult(
                results=(skipped("GOOGL"), skipped("NIO")),
                requested=2,
            ),
        ),
        requested=2,
    )

    def fake_batches(db_path, symbols, **kwargs):
        events.append("batch_orchestrator")
        assert Path(db_path) == pilot["db_path"]
        assert tuple(symbols) == ("GOOGL", "NIO")
        assert kwargs["as_of"] == AS_OF
        assert kwargs["fetcher"] is offline_provider
        assert kwargs["batch_size"] == 5
        assert kwargs["force"] is False
        return batch_result

    def fake_report(result, *, as_of, report_path, **kwargs):
        events.append("audit_report")
        assert result is batch_result
        assert as_of == AS_OF
        assert Path(report_path) == pilot["report_path"]
        return Path(report_path)

    monkeypatch.setattr(
        runner, "resolve_ingestion_session", fake_clock
    )
    monkeypatch.setattr(
        runner, "make_incremental_history_fetcher",
        fake_incremental,
    )
    monkeypatch.setattr(
        runner, "run_daily_batches", fake_batches
    )
    monkeypatch.setattr(
        runner, "write_daily_run_report", fake_report
    )

    outcome = execute(
        pilot,
        symbols=[" googl ", "NIO", "googl"],
    )

    assert events == [
        "session_clock",
        "incremental_fetcher",
        "batch_orchestrator",
        "audit_report",
    ]
    assert outcome.as_of == AS_OF
    assert outcome.report_path == pilot["report_path"]
    assert outcome.result is batch_result


@pytest.mark.parametrize(
    "field, invalid_value",
    [
        ("status", "PRODUCTION"),
        ("publication_enabled", True),
        ("vcp_production_enabled", True),
    ],
)
def test_unsafe_config_rejected(
    pilot, field, invalid_value
):
    config_path = pilot["config_path"]
    config = json.loads(config_path.read_text())
    config[field] = invalid_value
    config_path.write_text(json.dumps(config))

    with pytest.raises(ValueError):
        execute(pilot)

    assert not pilot["report_path"].exists()


def test_explicit_provider_is_required(pilot):
    with pytest.raises(ValueError):
        execute(pilot, provider=None)


def test_existing_report_blocks_run(pilot):
    path = pilot["report_path"]
    path.write_text('{"protected": true}')
    original = path.read_bytes()

    with pytest.raises(FileExistsError):
        execute(pilot)

    assert path.read_bytes() == original


def test_more_than_25_symbols_rejected(pilot):
    symbols = [f"SYM{i:03d}" for i in range(26)]

    with pytest.raises(ValueError):
        execute(pilot, symbols=symbols)


def test_missing_database_rejected(pilot):
    missing = pilot["db_path"].with_name("missing.db")

    with pytest.raises(FileNotFoundError):
        execute(pilot, db_path=missing)

    assert not missing.exists()


def test_naive_datetime_rejected(pilot):
    with pytest.raises(ValueError):
        execute(
            pilot,
            at=datetime(2026, 11, 3, 20, 0),
        )


@pytest.mark.parametrize(
    "symbols",
    [
        [],
        ["AAPL", "   "],
    ],
)
def test_empty_or_blank_universe_rejected(
    pilot, symbols
):
    with pytest.raises(ValueError):
        execute(pilot, symbols=symbols)
