"""Offline tests for persisted eligibility reporting."""

import sqlite3
from datetime import date

import pytest

from src.calculation.engine import DataQualityError
from src.data import batch_reporting


AS_OF = date(2026, 10, 14)


def test_reports_pass_and_filter_fail(monkeypatch, tmp_path):
    from src.data.eligibility import EligibilityResult

    statuses = {
        "AAPL": "PASS",
        "IBIO": "FILTER_FAIL",
    }

    monkeypatch.setattr(
        batch_reporting,
        "load_bars",
        lambda db, symbol: [symbol],
    )
    monkeypatch.setattr(
        batch_reporting,
        "validate_recent_sessions",
        lambda bars, **kwargs: None,
    )
    monkeypatch.setattr(
        batch_reporting,
        "check_eligibility",
        lambda bars, **kwargs: EligibilityResult(
            status=statuses[bars[0]],
            last_close=None,
            adv90_usd=None,
            reason="Simulated",
        ),
    )

    result = batch_reporting.report_stored_eligibility(
        tmp_path / "unused.db",
        ["aapl", "IBIO", "AAPL"],
        as_of=AS_OF,
    )

    assert result.counts == {
        "PASS": 1,
        "FILTER_FAIL": 1,
        "DATA_INCOMPLETE": 0,
    }
    assert result.by_symbol == {
        "AAPL": "PASS",
        "IBIO": "FILTER_FAIL",
    }


def test_missing_sessions_are_data_incomplete(monkeypatch, tmp_path):
    monkeypatch.setattr(
        batch_reporting,
        "load_bars",
        lambda db, symbol: [],
    )

    def missing_sessions(bars, **kwargs):
        raise DataQualityError("Missing required sessions")

    monkeypatch.setattr(
        batch_reporting,
        "validate_recent_sessions",
        missing_sessions,
    )

    result = batch_reporting.report_stored_eligibility(
        tmp_path / "unused.db",
        ["FCBM"],
        as_of=AS_OF,
    )

    assert result.counts["DATA_INCOMPLETE"] == 1
    assert result.by_symbol["FCBM"] == "DATA_INCOMPLETE"


def test_sqlite_errors_are_not_silenced(monkeypatch, tmp_path):
    def broken_storage(db, symbol):
        raise sqlite3.OperationalError("Database locked")

    monkeypatch.setattr(
        batch_reporting,
        "load_bars",
        broken_storage,
    )

    with pytest.raises(sqlite3.OperationalError, match="locked"):
        batch_reporting.report_stored_eligibility(
            tmp_path / "unused.db",
            ["AAPL"],
            as_of=AS_OF,
        )


def test_rejects_empty_symbol(tmp_path):
    with pytest.raises(ValueError, match="Empty symbol"):
        batch_reporting.report_stored_eligibility(
            tmp_path / "unused.db",
            ["AAPL", " "],
            as_of=AS_OF,
        )
