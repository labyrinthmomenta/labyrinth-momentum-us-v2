"""A6c.38: real PostgreSQL transaction integration tests.

This module tests a disposable transaction MODEL, not
the production authority implementation.

Local environments without an explicitly enabled
integration backend SKIP these tests.

CI must set:
    A6C38_PG_INTEGRATION=1
    A6C38_PG_DSN=<disposable PostgreSQL DSN>

The CI database must never be production.

No external authorization, signature, trusted clock,
production head mutation or real authority is created.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
import threading
import uuid

import pytest


ENABLED = (
    os.environ.get("A6C38_PG_INTEGRATION") == "1"
)

pytestmark = pytest.mark.skipif(
    not ENABLED,
    reason=(
        "Real PostgreSQL integration requires "
        "an explicitly enabled disposable CI backend"
    ),
)

if ENABLED:
    import psycopg
    from psycopg import sql
else:
    psycopg = None
    sql = None


A = "a" * 64
B = "b" * 64
C = "c" * 64

H0 = "d" * 64
H1 = "e" * 64
PILOT = "f" * 64

NOW = "2026-11-11T19:00:00Z"
ISSUED = "2026-11-11T18:59:00Z"
EXPIRES = "2026-11-11T19:05:00Z"


class LostResponse(Exception):
    """Simulated lost client response AFTER commit."""


def digest(value):
    raw = (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ) + "\n"
    ).encode("utf-8")

    return hashlib.sha256(raw).hexdigest()


def timestamp(value):
    return datetime.strptime(
        value,
        "%Y-%m-%dT%H:%M:%SZ",
    ).replace(tzinfo=timezone.utc)


def request(
    stream,
    tag,
    nonce_number,
    candidate=B,
    issued=ISSUED,
    expires=EXPIRES,
):
    identity = {
        "stream": stream,
        "expected_state": A,
        "expected_generation": 0,
        "expected_head": H0,
        "pilot_sha": PILOT,
        "candidate_state": candidate,
        "candidate_generation": 1,
        "candidate_head": H1,
        "tag": tag,
    }

    operation_id = digest(identity)

    payload = {
        **identity,
        "operation_id": operation_id,
        "nonce": f"{nonce_number:032x}",
        "issued_at": issued,
        "expires_at": expires,
    }

    return {
        **payload,
        "request_id": digest(payload),
    }


def open_connection(dsn, schema=None):
    conn = psycopg.connect(
        dsn,
        autocommit=True,
        connect_timeout=5,
    )

    if schema is not None:
        conn.execute(
            sql.SQL("SET search_path TO {}").format(
                sql.Identifier(schema)
            )
        )

    return conn


@pytest.fixture
def backend():
    if not ENABLED:
        pytest.skip("PostgreSQL not enabled")

    dsn = os.environ.get("A6C38_PG_DSN")

    if not dsn:
        pytest.fail(
            "PostgreSQL integration enabled "
            "without an explicit disposable DSN"
        )

    # This is only a CI-created disposable schema.
    schema = "a6c38_" + uuid.uuid4().hex

    with open_connection(dsn) as conn:
        conn.execute(
            sql.SQL("CREATE SCHEMA {}").format(
                sql.Identifier(schema)
            )
        )

    try:
        with open_connection(dsn, schema) as conn:
            conn.execute("""
                CREATE TABLE heads (
                    stream TEXT PRIMARY KEY,
                    state_sha TEXT NOT NULL,
                    generation INTEGER NOT NULL
                        CHECK (generation >= 0),
                    head_sha TEXT NOT NULL,
                    pilot_sha TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE receipts (
                    operation_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE,
                    nonce TEXT NOT NULL UNIQUE,
                    payload_sha TEXT NOT NULL,
                    stream TEXT NOT NULL,
                    before_sha TEXT NOT NULL,
                    after_sha TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    receipt_sha TEXT NOT NULL
                )
            """)

            for stream in (
                "happy",
                "stale",
                "fault",
                "race",
                "expiry",
                "nonce_left",
                "nonce_right",
            ):
                conn.execute(
                    """
                    INSERT INTO heads
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (stream, A, 0, H0, PILOT),
                )

        yield dsn, schema

    finally:
        with open_connection(dsn) as conn:
            conn.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(
                    sql.Identifier(schema)
                )
            )


def read_state(backend, stream):
    dsn, schema = backend

    with open_connection(dsn, schema) as conn:
        head = conn.execute(
            """
            SELECT state_sha, generation,
                   head_sha, pilot_sha
            FROM heads
            WHERE stream = %s
            """,
            (stream,),
        ).fetchone()

        receipts = conn.execute(
            """
            SELECT operation_id, request_id,
                   nonce, receipt_sha
            FROM receipts
            WHERE stream = %s
            ORDER BY operation_id
            """,
            (stream,),
        ).fetchall()

    return head, receipts


def apply(
    backend,
    item,
    synthetic_now=NOW,
    inject_abort=False,
    lose_response=False,
    after_absent_receipt_lookup=None,
):
    """Perform a PostgreSQL test transaction.

    No caller authentication.
    No trusted clock.
    No authoritative evidence verification.
    No real external authority.
    """

    dsn, schema = backend

    with open_connection(dsn, schema) as conn:
        try:
            conn.execute("BEGIN")

            # Retrieving an existing record is allowed
            # only for exactly matching synthetic identity.
            stored = conn.execute(
                """
                SELECT operation_id, request_id,
                       nonce, payload_sha, receipt_sha
                FROM receipts
                WHERE operation_id = %s
                   OR request_id = %s
                   OR nonce = %s
                ORDER BY operation_id
                LIMIT 1
                """,
                (
                    item["operation_id"],
                    item["request_id"],
                    item["nonce"],
                ),
            ).fetchone()

            payload_sha = digest(item)

            if stored is not None:
                identity = (
                    item["operation_id"],
                    item["request_id"],
                    item["nonce"],
                    payload_sha,
                )

                if stored[:4] != identity:
                    conn.execute("ROLLBACK")
                    return "DENIED_REPLAY_CONFLICT", None

                conn.execute("COMMIT")
                return (
                    "SIMULATED_IDEMPOTENT_RETRY",
                    stored[4],
                )

            # Test-only synchronization hook.
            # Runs after an absent receipt lookup,
            # before the state row is locked.
            # No effect in ordinary model calls.
            if after_absent_receipt_lookup is not None:
                after_absent_receipt_lookup()

            # Caller-supplied synthetic time.
            # This deliberately does not claim
            # authority-controlled clock validity.
            valid = (
                timestamp(item["issued_at"])
                <= timestamp(synthetic_now)
                < timestamp(item["expires_at"])
            )

            if not valid:
                conn.execute("ROLLBACK")
                return "DENIED_TIME_WINDOW", None

            if (
                item["candidate_generation"]
                != item["expected_generation"] + 1
            ):
                conn.execute("ROLLBACK")
                return "DENIED_GENERATION", None

            # Row lock serializes competing updates to
            # this particular synthetic authority stream.
            head = conn.execute(
                """
                SELECT state_sha, generation,
                       head_sha, pilot_sha
                FROM heads
                WHERE stream = %s
                FOR UPDATE
                """,
                (item["stream"],),
            ).fetchone()

            expected = (
                item["expected_state"],
                item["expected_generation"],
                item["expected_head"],
                item["pilot_sha"],
            )

            if head != expected:
                # Another transaction may have committed
                # this exact request while we waited for
                # the stream's FOR UPDATE row lock.
                #
                # Under PostgreSQL READ COMMITTED, this
                # new statement sees that committed receipt.
                # Never infer idempotency from the head alone.
                committed = conn.execute(
                    """
                    SELECT operation_id, request_id,
                           nonce, payload_sha, receipt_sha
                    FROM receipts
                    WHERE operation_id = %s
                       OR request_id = %s
                       OR nonce = %s
                    ORDER BY operation_id
                    LIMIT 1
                    """,
                    (
                        item["operation_id"],
                        item["request_id"],
                        item["nonce"],
                    ),
                ).fetchone()

                if committed is not None:
                    identity = (
                        item["operation_id"],
                        item["request_id"],
                        item["nonce"],
                        payload_sha,
                    )

                    if committed[:4] == identity:
                        conn.execute("COMMIT")
                        return (
                            "SIMULATED_IDEMPOTENT_RETRY",
                            committed[4],
                        )

                    conn.execute("ROLLBACK")
                    return "DENIED_REPLAY_CONFLICT", None

                conn.execute("ROLLBACK")
                return "DENIED_STALE_STATE", None

            updated = conn.execute(
                """
                UPDATE heads
                SET state_sha = %s,
                    generation = %s,
                    head_sha = %s
                WHERE stream = %s
                  AND state_sha = %s
                  AND generation = %s
                  AND head_sha = %s
                  AND pilot_sha = %s
                """,
                (
                    item["candidate_state"],
                    item["candidate_generation"],
                    item["candidate_head"],
                    item["stream"],
                    *expected,
                ),
            )

            if updated.rowcount != 1:
                raise AssertionError(
                    "Conditional state update failed"
                )

            if inject_abort:
                raise RuntimeError(
                    "INJECTED_FAILURE_AFTER_STATE_UPDATE"
                )

            # SHA-256 identity, NOT a signed receipt.
            receipt_sha = digest({
                "operation_id": item["operation_id"],
                "request_id": item["request_id"],
                "payload_sha": payload_sha,
                "before_sha": item["expected_state"],
                "after_sha": item["candidate_state"],
                "generation": item["candidate_generation"],
            })

            conn.execute(
                """
                INSERT INTO receipts (
                    operation_id,
                    request_id,
                    nonce,
                    payload_sha,
                    stream,
                    before_sha,
                    after_sha,
                    generation,
                    receipt_sha
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    item["operation_id"],
                    item["request_id"],
                    item["nonce"],
                    payload_sha,
                    item["stream"],
                    item["expected_state"],
                    item["candidate_state"],
                    item["candidate_generation"],
                    receipt_sha,
                ),
            )

            conn.execute("COMMIT")

            if lose_response:
                raise LostResponse(
                    "SIMULATED_RESPONSE_LOST_AFTER_COMMIT"
                )

            return "SIMULATED_COMMITTED", receipt_sha

        except LostResponse:
            # The transaction ALREADY committed.
            raise

        except psycopg.errors.UniqueViolation:
            # The attempted state update is rolled
            # back together with the failed insert.
            conn.execute("ROLLBACK")
            return "DENIED_REPLAY_CONFLICT", None

        except BaseException:
            conn.execute("ROLLBACK")
            raise


def test_01_head_and_receipt_commit_together(backend):
    item = request("happy", "primary", 1)

    status, receipt = apply(backend, item)

    assert status == "SIMULATED_COMMITTED"
    assert isinstance(receipt, str)
    assert len(receipt) == 64

    head, receipts = read_state(backend, "happy")

    assert head == (B, 1, H1, PILOT)
    assert len(receipts) == 1


def test_02_identical_retry_is_idempotent(backend):
    item = request("happy", "primary", 2)

    first = apply(backend, item)
    second = apply(backend, item)

    assert first[0] == "SIMULATED_COMMITTED"
    assert second == (
        "SIMULATED_IDEMPOTENT_RETRY",
        first[1],
    )

    assert len(
        read_state(backend, "happy")[1]
    ) == 1


def test_03_nonce_conflict_rejected(backend):
    first = request("happy", "primary", 3)
    second = request(
        "happy", "different", 3, candidate=C
    )

    assert apply(backend, first)[0] == (
        "SIMULATED_COMMITTED"
    )

    assert apply(backend, second)[0] == (
        "DENIED_REPLAY_CONFLICT"
    )


def test_04_operation_identity_conflict_rejected(
    backend,
):
    first = request("happy", "primary", 4)
    second = request("happy", "primary", 5)

    assert first["operation_id"] == (
        second["operation_id"]
    )

    assert first["request_id"] != (
        second["request_id"]
    )

    assert apply(backend, first)[0] == (
        "SIMULATED_COMMITTED"
    )

    assert apply(backend, second)[0] == (
        "DENIED_REPLAY_CONFLICT"
    )


def test_05_stale_state_rejected(backend):
    first = request("stale", "first", 6)
    second = request(
        "stale", "second", 7, candidate=C
    )

    assert apply(backend, first)[0] == (
        "SIMULATED_COMMITTED"
    )

    assert apply(backend, second)[0] == (
        "DENIED_STALE_STATE"
    )

    head, receipts = read_state(backend, "stale")

    assert head == (B, 1, H1, PILOT)
    assert len(receipts) == 1


def test_06_injected_failure_rolls_back_everything(
    backend,
):
    item = request("fault", "fault", 8)

    with pytest.raises(
        RuntimeError,
        match="INJECTED_FAILURE_AFTER_STATE_UPDATE",
    ):
        apply(
            backend,
            item,
            inject_abort=True,
        )

    assert read_state(backend, "fault") == (
        (A, 0, H0, PILOT),
        [],
    )


def test_07_retry_after_rollback_commits_once(backend):
    item = request("fault", "fault", 9)

    with pytest.raises(RuntimeError):
        apply(
            backend,
            item,
            inject_abort=True,
        )

    assert apply(backend, item)[0] == (
        "SIMULATED_COMMITTED"
    )

    head, receipts = read_state(backend, "fault")

    assert head == (B, 1, H1, PILOT)
    assert len(receipts) == 1


def test_08_invalid_synthetic_time_rejected(backend):
    expired = request(
        "expiry",
        "expired",
        10,
        expires=NOW,
    )

    future = request(
        "expiry",
        "future",
        11,
        issued="2026-11-11T19:00:01Z",
    )

    assert apply(backend, expired)[0] == (
        "DENIED_TIME_WINDOW"
    )

    assert apply(backend, future)[0] == (
        "DENIED_TIME_WINDOW"
    )

    assert read_state(backend, "expiry") == (
        (A, 0, H0, PILOT),
        [],
    )


def test_09_concurrent_cas_has_one_winner(backend):
    barrier = threading.Barrier(2)

    def contender(item):
        barrier.wait(timeout=10)
        return apply(backend, item)[0]

    items = (
        request("race", "left", 12, candidate=B),
        request("race", "right", 13, candidate=C),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [
            pool.submit(contender, item)
            for item in items
        ]

        outcomes = [
            job.result(timeout=30)
            for job in jobs
        ]

    assert sorted(outcomes) == [
        "DENIED_STALE_STATE",
        "SIMULATED_COMMITTED",
    ]

    head, receipts = read_state(backend, "race")

    assert head[0] in (B, C)
    assert head[1] == 1
    assert len(receipts) == 1


def test_10_reopened_connection_finds_receipt(
    backend,
):
    item = request("happy", "primary", 14)

    first = apply(backend, item)

    assert first[0] == "SIMULATED_COMMITTED"

    # apply() creates a fresh PostgreSQL connection.
    assert apply(backend, item) == (
        "SIMULATED_IDEMPOTENT_RETRY",
        first[1],
    )


def test_11_lost_response_recovers_committed_result(
    backend,
):
    item = request("happy", "lost-response", 15)

    with pytest.raises(
        LostResponse,
        match="SIMULATED_RESPONSE_LOST_AFTER_COMMIT",
    ):
        apply(
            backend,
            item,
            lose_response=True,
        )

    head, receipts = read_state(backend, "happy")

    assert head == (B, 1, H1, PILOT)
    assert len(receipts) == 1

    result = apply(backend, item)

    assert result[0] == (
        "SIMULATED_IDEMPOTENT_RETRY"
    )

    assert result[1] == receipts[0][3]


def test_12_cross_stream_concurrent_nonce_collision(
    backend,
):
    barrier = threading.Barrier(2)

    items = (
        request("nonce_left", "left", 16),
        request(
            "nonce_right", "right", 16, candidate=C
        ),
    )

    assert items[0]["nonce"] == items[1]["nonce"]

    def contender(item):
        barrier.wait(timeout=10)
        return apply(backend, item)[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [
            pool.submit(contender, item)
            for item in items
        ]

        outcomes = [
            job.result(timeout=30)
            for job in jobs
        ]

    assert sorted(outcomes) == [
        "DENIED_REPLAY_CONFLICT",
        "SIMULATED_COMMITTED",
    ], outcomes

    left, left_receipts = read_state(
        backend, "nonce_left"
    )

    right, right_receipts = read_state(
        backend, "nonce_right"
    )

    assert len(left_receipts) + len(right_receipts) == 1

    assert sorted([left[1], right[1]]) == [0, 1]


def test_13_concurrent_identical_retry_is_idempotent(
    backend,
):
    """Two identical requests race after observing no receipt.

    Expected semantics:
    - One transaction commits.
    - The other retrieves the committed result.
    - Only one generation advancement exists.

    This is intentionally a TDD RED test.
    """

    item = request(
        "race",
        "identical-retry",
        17,
        candidate=B,
    )

    # Forces both transactions to finish their
    # initial receipt lookup before either proceeds
    # toward the state lock.
    gate = threading.Barrier(2)

    def contender():
        return apply(
            backend,
            item,
            after_absent_receipt_lookup=lambda: (
                gate.wait(timeout=10)
            ),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [
            pool.submit(contender)
            for _ in range(2)
        ]

        outcomes = [
            job.result(timeout=30)
            for job in jobs
        ]

    statuses = sorted(
        outcome[0]
        for outcome in outcomes
    )

    assert statuses == [
        "SIMULATED_COMMITTED",
        "SIMULATED_IDEMPOTENT_RETRY",
    ], outcomes

    # Both calls must refer to one committed result.
    assert outcomes[0][1] == outcomes[1][1]

    head, receipts = read_state(
        backend,
        "race",
    )

    assert head == (B, 1, H1, PILOT)
    assert len(receipts) == 1
