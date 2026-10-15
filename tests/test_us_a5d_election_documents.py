"""A5d synthetic checks: SEC N-54A content, chronology and frozen-source gates."""
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from src.data.universe import a5d_election_documents as mod

NOW = datetime(2026, 10, 15, 11, 25, tzinfo=timezone.utc)
ELECTION = b"""<html><head><title>Form N-54A</title></head><body>
FORM N-54A NOTIFICATION OF ELECTION TO BE SUBJECT TO SECTIONS 55
THROUGH 65 OF THE INVESTMENT COMPANY ACT OF 1940
The undersigned business development company hereby elects to be
subject to sections 55 through 65 of the Investment Company Act.
</body></html>"""


def sec_recent(cik=1321741):
    return json.dumps({
        "cik": cik, "name": "Example BDC, Inc.", "filings": {
            "recent": {
                "form": ["N-54A", "N-54C", "10-K", "N-54A/A"],
                "accessionNumber": [
                    "0000950133-05-001383", "0000950133-26-000002",
                    "0000950133-25-000001", "0000950133-24-000001"],
                "filingDate": ["2005-03-31", "2026-10-15", "2025-03-01", "2024-01-12"],
                "primaryDocument": [
                    "w0719154nv54a.htm", "n54c.htm", "annual.htm", "sub/n54aa.htm"],
            },
            "files": [],
        },
    }).encode()


def write_fixture(tmp_path, monkeypatch):
    expected_cik = "0001321741"
    raw = sec_recent()
    digest = sha256(raw).hexdigest()
    (tmp_path / f"CIK{expected_cik}-{digest}.json").write_bytes(raw)
    entries = [{
        "cik": expected_cik, "directory_tickers": ["GAIN"],
        "sec_sha256": digest, "sec_filer_name": "Example BDC, Inc.",
        "retrieved_at": NOW.isoformat(), "older_history_files_not_downloaded": [],
        "form_types_found_in_recent_window": ["N-54A", "10-K"],
        "production_eligible": False, "cik_to_listed_security_approved": False,
    }]
    report = {"status": "CAPTURE_VALIDATED_REVIEW_ONLY",
              "production_eligible": False, "successful_cik_count": 1,
              "failed_cik_count": 0, "auto_approved_instruments": 0,
              "selected_evidence": entries}
    payload = json.dumps(report).encode()
    (tmp_path / "edgar-pilot.json").write_bytes(payload)
    monkeypatch.setattr(mod, "A5C_REPORT_SHA256", sha256(payload).hexdigest())
    monkeypatch.setattr(mod, "EXPECTED_A5C_ISSUERS", 1)
    monkeypatch.setattr(mod, "EXPECTED_ELECTION_ISSUERS", 1)
    return digest


def test_sec_html_election_text_signals_are_not_current_approval():
    result = mod.inspect_document(ELECTION)
    assert result["n54a_text_consistent"] is True
    assert result["sha256"] == sha256(ELECTION).hexdigest()
    assert result["form_text_signals"]["business_development_company_phrase"]


def test_html_denial_does_not_count_as_election():
    assert not mod.inspect_document(b"<html>Access Denied</html>")["n54a_text_consistent"]
    assert not mod.inspect_document(b"<h1>FORM N-54C</h1>Business development company withdraws election")["n54a_text_consistent"]


def test_full_recent_array_has_both_original_and_amendment_but_no_future_withdrawal():
    records = mod.form_records(sec_recent(), "0001321741")
    assert [r["form"] for r in records] == ["N-54A", "N-54A/A"]
    assert records[1]["url"].endswith("sub/n54aa.htm")
    assert not any(r["form"] == "N-54C" for r in records)


def test_unsafe_filing_url_is_rejected_not_fetched():
    with pytest.raises(mod.A5dEvidenceError, match="URL"):
        mod.fetch_document("https://other.example.com/Archives/edgar/data/1/123/a.htm",
                           "FundEvidence research@example.com")
    with pytest.raises(mod.A5dEvidenceError, match="URL"):
        mod.fetch_document("https://www.sec.gov/Archives/edgar/data/1/123/../bad.htm",
                           "FundEvidence research@example.com")


def test_unsafe_relative_primary_document_blocks_metadata():
    altered = json.loads(sec_recent())
    altered["filings"]["recent"]["primaryDocument"][0] = "../../secret.html"
    with pytest.raises(mod.A5dEvidenceError, match="Unsafe"):
        mod.form_records(json.dumps(altered).encode(), "0001321741")


def test_complete_verified_election_capture_still_unapproved(tmp_path, monkeypatch):
    write_fixture(tmp_path, monkeypatch)
    captured = mod.run_audit(tmp_path, tmp_path / "verified", agent="Research research@example.org",
                             fetcher=lambda u, a: ELECTION,
                             clock=lambda: NOW, pause=lambda _: None)
    assert captured["status"] == "DOCUMENT_EVIDENCE_CAPTURED_REVIEW_ONLY"
    assert captured["verified_n54a_primary_documents"] == 2
    assert captured["current_bdc_status_approved"] == 0
    assert captured["security_share_class_approved"] == 0
    assert captured["production_approved"] == 0
    assert not captured["findings"][0]["withdrawal_absence_proven"]
    assert captured["findings"][0]["current_bdc_status"] == "UNDETERMINED"
    assert len(list((tmp_path / "verified").glob("CIK*.html"))) == 2


def test_content_denied_fails_closed(tmp_path, monkeypatch):
    write_fixture(tmp_path, monkeypatch)
    out = mod.run_audit(tmp_path, tmp_path / "denied", agent="Research research@example.org",
                        fetcher=lambda u, a: b"<html>Rate threshold exceeded</html>",
                        clock=lambda: NOW, pause=lambda _: None)
    assert out["status"] == "PARTIAL_DOCUMENT_EVIDENCE_REVIEW_ONLY"
    assert out["verified_n54a_primary_documents"] == 0
    assert out["document_fetch_failures"] == 2
    assert out["production_approved"] == 0


def test_raw_submission_mutation_detected(tmp_path, monkeypatch):
    digest = write_fixture(tmp_path, monkeypatch)
    file = tmp_path / f"CIK0001321741-{digest}.json"
    file.write_bytes(sec_recent() + b"\n")
    with pytest.raises(mod.A5dEvidenceError, match="checksum"):
        mod.load_frozen_elections(tmp_path)


def test_full_report_snapshot_mutation_detected(tmp_path, monkeypatch):
    write_fixture(tmp_path, monkeypatch)
    with (tmp_path / "edgar-pilot.json").open("a") as fh:
        fh.write("\n")
    with pytest.raises(mod.A5dEvidenceError, match="SHA"):
        mod.load_frozen_elections(tmp_path)
