from datetime import date, datetime, timezone
import sqlite3

import pytest

from src.data.storage.identity import connect, add_identifier, resolve_identifier


@pytest.fixture
def db():
    conn = connect()
    conn.execute("INSERT INTO issuers VALUES(1,'Example issuer','0000000001','synthetic fixture')")
    conn.executemany("INSERT INTO securities VALUES(?,1,?,'COMMON','fixture')", [(1, "A"), (2, "B")])
    conn.commit()
    yield conn
    conn.close()


def identifier(db, sec=1, start="2020-01-01", end=None, value="EXAM"):
    return add_identifier(db, security_id=sec, namespace="ticker:XNAS", value=value,
                          valid_from=date.fromisoformat(start), valid_to=date.fromisoformat(end) if end else None,
                          known_at=datetime(2026, 10, 14, tzinfo=timezone.utc), evidence="synthetic")


def test_distinct_classes_same_issuer_and_ticker_reuse(db):
    identifier(db, end="2026-01-01")
    identifier(db, sec=2, start="2026-01-01")
    assert resolve_identifier(db, "ticker:XNAS", "EXAM", date(2025, 12, 31)) == 1
    assert resolve_identifier(db, "ticker:XNAS", "EXAM", date(2026, 1, 1)) == 2
    assert resolve_identifier(db, "ticker:XNAS", "MISSING", date(2026, 1, 1)) is None


def test_symbol_change_preserves_security_with_explicit_evidence(db):
    identifier(db, end="2026-01-01")
    identifier(db, start="2026-01-01", value="NEW")
    assert resolve_identifier(db, "ticker:XNAS", "NEW", date(2026, 1, 1)) == 1


def test_overlap_insert_and_update_rejected(db):
    identifier(db, end="2026-01-01")
    with pytest.raises(sqlite3.IntegrityError, match="overlap"):
        identifier(db, sec=2, start="2025-01-01")
    second = identifier(db, sec=2, start="2026-01-01")
    with pytest.raises(sqlite3.IntegrityError, match="overlap"):
        db.execute("UPDATE identifiers SET valid_from='2025-01-01' WHERE identifier_id=?", (second,))


def test_identity_requires_foreign_key_and_evidence(db):
    with pytest.raises(sqlite3.IntegrityError):
        identifier(db, sec=999)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO securities(share_class,instrument_type,evidence) VALUES('A','COMMON','')")


def test_transaction_rollback_preserves_identity(db):
    with pytest.raises(sqlite3.IntegrityError):
        with db:
            identifier(db)
            identifier(db, sec=2)
    assert db.execute("SELECT count(*) FROM identifiers").fetchone()[0] == 0


def test_listing_interval_overlap(db):
    db.execute("INSERT INTO listings VALUES(1,1,'XNAS','USD','2020-01-01',NULL,'fixture')")
    with pytest.raises(sqlite3.IntegrityError, match="overlap"):
        db.execute("INSERT INTO listings VALUES(2,1,'XNAS','USD','2025-01-01',NULL,'fixture')")


def test_invalid_interval_and_invalid_date(db):
    with pytest.raises(sqlite3.IntegrityError):
        identifier(db, start="2026-01-01", end="2025-01-01")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO listings VALUES(1,1,'XNAS','USD','2026-02-30',NULL,'fixture')")


def test_migration_idempotent_and_future_schema_rejected(tmp_path):
    path = tmp_path / "identity.db"
    conn = connect(path)
    conn.close()
    conn = connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    conn.execute("PRAGMA user_version=99")
    conn.close()
    with pytest.raises(ValueError):
        connect(path)
