"""Offline contracts for exclusive daily ingestion locking."""

import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.data.daily_ingestion_runner import run_daily_ingestion
from src.data.daily_run_lock import (
    DailyRunAlreadyActiveError,
    hold_daily_ingestion_lock,
)


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "pilot.db"
    path.touch()
    return path


def test_lock_acquired_and_reusable(database):
    expected = Path(
        str(database.resolve()) + ".daily.lock"
    )

    with hold_daily_ingestion_lock(database) as lock_path:
        assert lock_path == expected
        assert lock_path.is_file()

    # The file may remain; the OS lock must be released.
    with hold_daily_ingestion_lock(database):
        pass


def test_second_holder_is_rejected(database):
    with hold_daily_ingestion_lock(database):
        with pytest.raises(DailyRunAlreadyActiveError):
            with hold_daily_ingestion_lock(database):
                pass

    # First holder has exited: acquisition now succeeds.
    with hold_daily_ingestion_lock(database):
        pass


def test_independent_databases_do_not_conflict(
    database, tmp_path
):
    second_db = tmp_path / "second.db"
    second_db.touch()

    with hold_daily_ingestion_lock(database):
        with hold_daily_ingestion_lock(second_db):
            pass


def test_exception_releases_lock(database):
    with pytest.raises(RuntimeError):
        with hold_daily_ingestion_lock(database):
            raise RuntimeError("Simulated interrupted run")

    with hold_daily_ingestion_lock(database):
        pass


def test_stale_lock_file_does_not_block(database):
    lock_path = Path(
        str(database.resolve()) + ".daily.lock"
    )

    lock_path.write_text(
        "Previous process has exited",
        encoding="utf-8",
    )

    with hold_daily_ingestion_lock(database):
        assert lock_path.is_file()

    assert lock_path.read_text(
        encoding="utf-8"
    ) == "Previous process has exited"


def test_separate_process_cannot_acquire_held_lock(database):
    child_code = """
import sys
from pathlib import Path
from src.data.daily_run_lock import (
    DailyRunAlreadyActiveError,
    hold_daily_ingestion_lock,
)

try:
    with hold_daily_ingestion_lock(Path(sys.argv[1])):
        print("ACQUIRED")
except DailyRunAlreadyActiveError:
    print("LOCKED")
"""

    repo_root = Path(__file__).resolve().parents[1]

    with hold_daily_ingestion_lock(database):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                child_code,
                str(database),
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )

    assert result.stdout.strip() == "LOCKED"


def test_runner_rejects_active_lock_before_ingestion(
    database, tmp_path, monkeypatch
):
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

    report = tmp_path / "daily_report.json"

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Ingestion must not start with lock held"
        )

    import src.data.daily_ingestion_runner as runner

    monkeypatch.setattr(
        runner,
        "make_incremental_history_fetcher",
        forbidden,
    )

    with hold_daily_ingestion_lock(database):
        with pytest.raises(DailyRunAlreadyActiveError):
            run_daily_ingestion(
                db_path=database,
                config_path=config,
                report_path=report,
                symbols=["AAPL"],
                full_start=date(2025, 7, 1),
                provider=forbidden,
                at=datetime(
                    2026, 11, 3, 20, 0,
                    tzinfo=timezone.utc,
                ),
            )

    assert not report.exists()
