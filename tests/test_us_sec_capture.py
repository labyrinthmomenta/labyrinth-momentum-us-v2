"""Synthetic only: SEC capture receipt integrity and offline reconciliation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from src.data.universe.sec import SecSnapshotError
from src.data.universe.sec_capture import (
    SEC_SOURCE_URL, capture_sec, validate_user_agent,
)
from src.data.universe.sec_review import (
    load_verified_sec_capture, build_audit_summary,
)
from src.data.universe.sec import enrich_review_with_sec

NOW = datetime(2026, 10, 14, 16, tzinfo=timezone.utc)
UA = "LabyrinthMomentumUSV2 research@example.org"


def payload(rows=None):
    if rows is None:
        rows = [[1652044, "Alphabet Inc.", "GOOG", "Nasdaq"]]
    return json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
                       "data": rows}).encode()


def successful_capture(tmp_path, content=None):
    destination = tmp_path / "sec"
    raw = payload() if content is None else content
    report = capture_sec(destination, user_agent=UA,
                         fetcher=lambda url, agent: raw,
                         clock=lambda: NOW)
    return destination, report


def test_offline_capture_has_verified_hash_receipt_and_no_eligibility(tmp_path):
    location, report = successful_capture(tmp_path)
    receipt = report["receipt"]
    assert report["status"] == "CAPTURE_VALIDATED"
    assert report["production_eligible"] is False
    assert receipt["source_url"] == SEC_SOURCE_URL
    assert receipt["sha256"] == hashlib.sha256(payload()).hexdigest()
    assert receipt["rows"] == 1 and receipt["validated"] is True
    snap = load_verified_sec_capture(location / "capture.json")
    assert snap.sha256 == receipt["sha256"]
    assert snap.companies[0].cik == "0001652044"


@pytest.mark.parametrize("agent", ["", "my-app", "app\ncontact@example.org", None, "x" * 221])
def test_sec_contact_header_required(agent):
    with pytest.raises(SecSnapshotError):
        validate_user_agent(agent)


def test_capture_failure_keeps_receipt_but_no_success_status(tmp_path):
    location, report = successful_capture(tmp_path, b"<html>access denied</html>")
    assert report["status"] == "SOURCE_REJECTED"
    assert report["receipt"]["validated"] is False
    with pytest.raises(SecSnapshotError):
        load_verified_sec_capture(location / "capture.json")


def test_capture_fails_closed_on_network_exception(tmp_path):
    def error(url, agent):
        raise OSError("blocked by host")
    out = capture_sec(tmp_path / "sec", user_agent=UA, fetcher=error)
    assert out["status"] == "SOURCE_REJECTED"
    assert out["receipt"] is None


def test_capture_does_not_overwrite_a_previous_run(tmp_path):
    successful_capture(tmp_path)
    with pytest.raises(FileExistsError):
        successful_capture(tmp_path)


def test_capture_tampering_is_detected(tmp_path):
    loc, report = successful_capture(tmp_path)
    Path(report["receipt"]["path"]).write_bytes(payload([[200, "Changed", "CHNG", "Nasdaq"]]))
    with pytest.raises(SecSnapshotError, match="checksum"):
        load_verified_sec_capture(loc / "capture.json")


@pytest.mark.parametrize("correction", [
    {"source_url": "https://unknown.invalid/companies.json"},
    {"validated": False},
    {"rows": 99},
])
def test_capture_receipt_manipulations_are_rejected(tmp_path, correction):
    location, report = successful_capture(tmp_path)
    report["receipt"].update(correction)
    (location / "capture.json").write_text(json.dumps(report))
    with pytest.raises(SecSnapshotError):
        load_verified_sec_capture(location / "capture.json")


def test_reconciliation_counts_do_not_change_directory_eligibility(tmp_path):
    location, _ = successful_capture(tmp_path)
    snap = load_verified_sec_capture(location / "capture.json")
    row = {"source": "nasdaqlisted", "symbol": "GOOG", "mic": "XNAS",
           "decision": "REVIEW_REQUIRED", "reason": "TYPE_UNCONFIRMED",
           "production_eligible": False}
    input_report = {"status": "REVIEW_ONLY", "production_eligible": False,
                    "counts": {"INCLUDE": 0, "EXCLUDE": 0, "REVIEW_REQUIRED": 1},
                    "sources": [{"source": "nasdaqlisted", "sha256": "synthetic"}],
                    "rows": [row]}
    report = enrich_review_with_sec(input_report, snap)
    summary = build_audit_summary(report)
    assert summary["directory_total"] == 1
    assert summary["a1_same_total"] is False
    assert summary["a1_snapshot_identity_proven"] is False
    assert summary["sec_match_counts"]["SEC_CIK_CANDIDATE"] == 1
    assert not report["production_eligible"] and not report["rows"][0]["production_eligible"]
    assert input_report["rows"][0].get("issuer_match") is None


def test_reconciliation_fails_on_truncated_match_summary():
    with pytest.raises(SecSnapshotError, match="incomplete"):
        build_audit_summary({"rows": [{}], "counts": {},
                             "sec_enrichment": {"match_counts": {
                                 "SEC_CIK_CANDIDATE": 0, "SEC_NOT_FOUND": 0,
                                 "SEC_IDENTITY_AMBIGUOUS": 0}}})
