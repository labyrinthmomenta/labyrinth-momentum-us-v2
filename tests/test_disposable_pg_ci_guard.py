"""Offline tests for disposable PostgreSQL CI safeguards."""

import pytest

from src.data.disposable_pg_ci_guard import (
    EXPECTED_DSN,
    EXPECTED_ENV,
    require_disposable_ci_dsn,
)


def valid_environment():
    return {
        **EXPECTED_ENV,
        "A6C38_PG_DSN": EXPECTED_DSN,
    }


def rejected(environment):
    with pytest.raises(ValueError):
        require_disposable_ci_dsn(environment)


def test_01_known_disposable_target_accepted():
    environment = valid_environment()
    assert require_disposable_ci_dsn(
        environment
    ) == EXPECTED_DSN


def test_02_non_github_actions_rejected():
    environment = valid_environment()
    environment["GITHUB_ACTIONS"] = "false"
    rejected(environment)


def test_03_wrong_repository_rejected():
    environment = valid_environment()
    environment["GITHUB_REPOSITORY"] = (
        "someone-else/another-repository"
    )
    rejected(environment)


def test_04_wrong_workflow_rejected():
    environment = valid_environment()
    environment["GITHUB_WORKFLOW"] = (
        "Offline core validation"
    )
    rejected(environment)


def test_05_disabled_integration_rejected():
    environment = valid_environment()
    environment["A6C38_PG_INTEGRATION"] = "0"
    rejected(environment)


def test_06_remote_host_rejected():
    environment = valid_environment()
    environment["A6C38_PG_DSN"] = (
        EXPECTED_DSN.replace(
            "host=127.0.0.1",
            "host=database.example.invalid",
        )
    )
    rejected(environment)


def test_07_other_database_rejected():
    environment = valid_environment()
    environment["A6C38_PG_DSN"] = (
        EXPECTED_DSN.replace(
            "dbname=ci_authority",
            "dbname=production",
        )
    )
    rejected(environment)


def test_08_other_database_user_rejected():
    environment = valid_environment()
    environment["A6C38_PG_DSN"] = (
        EXPECTED_DSN.replace(
            "user=ci_authority",
            "user=production_owner",
        )
    )
    rejected(environment)


def test_09_additional_connection_option_rejected():
    environment = valid_environment()
    environment["A6C38_PG_DSN"] = (
        EXPECTED_DSN
        + " options=-csearch_path=public"
    )
    rejected(environment)


def test_10_missing_dsn_rejected():
    environment = valid_environment()
    del environment["A6C38_PG_DSN"]
    rejected(environment)
