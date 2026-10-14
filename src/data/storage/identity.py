from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, 1):
        conn.close()
        raise ValueError("Unsupported identity schema version")
    if version == 0:
        try:
            conn.executescript("BEGIN IMMEDIATE;\n" + Path(__file__).with_name("schema.sql").read_text()
                               + "\nPRAGMA user_version=1;\nCOMMIT;")
        except Exception:
            conn.rollback()
            conn.close()
            raise
    return conn


def add_identifier(conn: sqlite3.Connection, *, security_id: int, namespace: str,
                   value: str, valid_from: date, valid_to: date | None,
                   known_at: datetime, evidence: str) -> int:
    """Explicit evidence only; directory names never create/merge identities here."""
    if known_at.tzinfo is None or known_at.utcoffset() is None:
        raise ValueError("known_at must be timezone aware")
    cursor = conn.execute(
        "INSERT INTO identifiers(security_id,namespace,value,valid_from,valid_to,known_at,evidence) VALUES(?,?,?,?,?,?,?)",
        (security_id, namespace, value, valid_from.isoformat(),
         valid_to.isoformat() if valid_to else None, known_at.isoformat(), evidence))
    return cursor.lastrowid


def resolve_identifier(conn: sqlite3.Connection, namespace: str, value: str,
                       as_of: date) -> int | None:
    rows = conn.execute(
        "SELECT security_id FROM identifiers WHERE namespace=? AND value=? AND valid_from<=? AND (valid_to IS NULL OR valid_to>?)",
        (namespace, value, as_of.isoformat(), as_of.isoformat())).fetchall()
    if len(rows) > 1:
        raise ValueError("Ambiguous identifier")
    return rows[0][0] if rows else None
