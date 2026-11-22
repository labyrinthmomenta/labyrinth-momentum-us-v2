"""Fail-closed target guard for disposable PostgreSQL CI tests.

TEST FIXTURE SAFETY ONLY.

This guard prevents ordinary accidental use of a
non-CI connection target.

Environment variables can be spoofed, so this does
NOT authenticate an external authority or establish
a production trust boundary.

Never use this module to grant trading authorization.
"""

from collections.abc import Mapping


EXPECTED_DSN = (
    "host=127.0.0.1 "
    "port=5432 "
    "dbname=ci_authority "
    "user=ci_authority "
    "password=ci_only_disposable_312 "
    "connect_timeout=5"
)

EXPECTED_ENV = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_REPOSITORY": (
        "labyrinthmomenta/labyrinth-momentum-us-v2"
    ),
    "GITHUB_WORKFLOW": (
        "Authority PostgreSQL integration (disposable)"
    ),
    "A6C38_PG_INTEGRATION": "1",
}


def require_disposable_ci_dsn(environment):
    """Accept only the known disposable CI target.

    This deliberately uses an exact-match contract.
    It is not a general PostgreSQL DSN parser.

    Caller environment values are not cryptographic
    identity evidence.
    """

    if not isinstance(environment, Mapping):
        raise ValueError(
            "Disposable PostgreSQL CI environment required"
        )

    for name, expected in EXPECTED_ENV.items():
        if environment.get(name) != expected:
            raise ValueError(
                "Disposable PostgreSQL CI context rejected"
            )

    dsn = environment.get("A6C38_PG_DSN")

    if type(dsn) is not str or dsn != EXPECTED_DSN:
        raise ValueError(
            "Non-disposable PostgreSQL target rejected"
        )

    return dsn
