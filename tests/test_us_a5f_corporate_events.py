"""A5f offline SEC 8-K evidence tests; no legal or production conclusions."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from src.data.universe import a5f_corporate_events as mod

NOW = datetime(2026, 10, 15, 14, tzinfo=timezone.utc)
SEC_8K = b"""<html><body><h2>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</h2>
<h2>FORM 8-K</h2><p>CURRENT REPORT Pursuant to Section 13 or 15(d)</p>
<h3>Item 1.01 Entry into a Material Definitive Agreement</h3>
<p>The Company has not entered into a merger agreement. We may consider an
acquisition in the future, but no transaction has been consummated.</p>
<h3>Item 2.02 Results of Operations and Financial Condition</h3>
<p>Quarterly results were published as a separate press release.</p>
<h3>Item 9.01 Financial Statements and Exhibits</h3>
<p>See exhibits for information. The registrant has made no determination
that any share class or trading symbol will change.</p></body></html>"""
CUTOFF = "2026-10-14"


def _fixture(tmp_path, monkeypatch):
    counts = [4,2,5,3,1,4,4,0,2,0,2,1,3,2,6,1]
    assert sum(counts) == 40
    issuers = []
    for i, n in enumerate(counts):
        cik = f"{100000+i:010d}"
        acc = f"{100000+i:010d}-26-000001"
        body = f"<h2>FORM 10-Q</h2><p>Report for {cik}</p>".encode()
        digest = sha256(body).hexdigest()
        (tmp_path / f"CIK{cik}-{acc}-{digest}.html").write_bytes(body)
        event_rows = []
        for j in range(n):
            eacc = f"{100000+i:010d}-26-{j+10:06d}"
            url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                   f"{eacc.replace('-', '')}/event{j}.htm")
            event_rows.append({
                "form": "8-K", "filing_date": "2026-10-12",
                "accession": eacc, "document_url": url,
            })
        issuers.append({
            "cik": cik, "tickers": [f"X{i:02d}"],
            "source_submissions_sha256": "abc",
            "latest_financial": {"form": "10-Q", "filing_date": "2026-08-01",
                                 "accession": acc},
            "latest_financial_observation": {
                "status": "FINANCIAL_DOCUMENT_REVIEW_EVIDENCE",
                "issuer_bdc_status_approved": False,
                "listed_security_class_approved": False,
                "sha256": digest, "bytes": len(body),
            },
            "post_financial_8k_metadata": event_rows,
            "n54c_metadata_seen": [],
            "historical_files_not_downloaded": [],
            "issuer_bdc_status": "REVIEW_REQUIRED",
            "listed_security_class_status": "REVIEW_REQUIRED",
            "post_financial_events_checked": False,
            "n54c_absence_proven": False, "production_eligible": False,
        })
    summary = {
        "status": "SOURCE_CAPTURED_REVIEW_ONLY", "production_eligible": False,
        "issuer_total": 16, "financial_documents_captured": 16,
        "production_approvals": 0, "source_failures": [], "findings": issuers,
    }
    raw = json.dumps(summary).encode()
    (tmp_path / "a5e-financial-evidence.json").write_bytes(raw)
    monkeypatch.setattr(mod, "A5E_REPORT_SHA256", sha256(raw).hexdigest())
    return issuers


def test_no_event_conclusion_from_negated_merger_language():
    out = mod.analyze_eight_k(SEC_8K)
    assert out["sec_8k_primary_text_signal"] is True
    assert "MERGER_OR_ACQUISITION_LANGUAGE" in out["risk_language_review_snippets"]
    assert out["item_headings_observed"] == ["1.01", "2.02", "9.01"]
    assert out["item_review_labels"]["1.01"] == "MATERIAL_AGREEMENT_REVIEW"
    assert out["event_occurred_confirmed"] is False
    assert out["ticker_class_or_listing_approved"] is False
    assert out["production_eligible"] is False


def test_suspicious_item_and_bdc_withdrawal_language_still_unapproved():
    html = (b"<html><body>FORM 8-K " + b"<p>ordinary SEC report content</p>"*15 +
            b"<h3>Item 3.01 Notice of Delisting</h3>"
            b"<p>The Company may discuss withdrawing its election to be a business"
            b" development company. This is hypothetical.</p></body></html>")
    x = mod.analyze_eight_k(html)
    assert x["manual_review_priority"] == "HIGH"
    assert x["item_review_labels"]["3.01"] == "LISTING_COMPLIANCE_REVIEW"
    assert "BDC_ELECTION_OR_WITHDRAWAL_LANGUAGE" in x["risk_language_review_snippets"]
    assert not x["event_occurred_confirmed"]


def test_html_access_denied_is_not_8k():
    with pytest.raises(mod.A5fEvidenceError, match="resemble"):
        mod.analyze_eight_k(b"<html>Access Denied</html>" * 20)


def test_size_and_type_validation():
    with pytest.raises(mod.A5fEvidenceError):
        mod.analyze_eight_k(b"x" * (mod.MAX_EVENT_BYTES + 1))
    with pytest.raises(mod.A5fEvidenceError):
        mod.analyze_eight_k(b"")


@pytest.mark.parametrize("url", [
    "https://elsewhere.example.com/Archives/edgar/data/1321741/000132174126000001/x.htm",
    "http://www.sec.gov/Archives/edgar/data/1321741/000132174126000001/x.htm",
    "https://www.sec.gov/Archives/edgar/data/1321741/000132174126000001/../bad.htm",
    "https://www.sec.gov/Archives/edgar/data/1321741/000132174126000001/x.htm?download=1",
])
def test_event_url_allowlist_rejects_bad_sources_without_network(url):
    with pytest.raises(mod.A5fEvidenceError):
        mod.fetch_event(url, "Project email@example.org")


def test_frozen_40_event_queue_recovered_and_hashed(monkeypatch, tmp_path):
    _fixture(tmp_path, monkeypatch)
    events, prov = mod.load_frozen_queue(tmp_path)
    assert len(events) == 40
    assert prov["issuer_count"] == 16
    assert prov["financial_raw_sha256_checks"] == 16
    assert prov["n54c_separate_evidence_gate"] == "NOT_PROVEN_ABSENT"
    assert all(x["form"] == "8-K" for x in events)


def test_queue_tampering_is_blocked(monkeypatch, tmp_path):
    rows = _fixture(tmp_path, monkeypatch)
    report = tmp_path / "a5e-financial-evidence.json"
    report.write_bytes(report.read_bytes() + b"\n")
    with pytest.raises(mod.A5fEvidenceError, match="checksum"):
        mod.load_frozen_queue(tmp_path)


def test_source_financial_document_tampering_is_blocked(monkeypatch, tmp_path):
    rows = _fixture(tmp_path, monkeypatch)
    x = rows[0]
    digest = x["latest_financial_observation"]["sha256"]
    path = tmp_path / f"CIK{x['cik']}-{x['latest_financial']['accession']}-{digest}.html"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(mod.A5fEvidenceError, match="checksum"):
        mod.load_frozen_queue(tmp_path)


def test_missing_one_event_is_not_silently_accepted(monkeypatch, tmp_path):
    rows = _fixture(tmp_path, monkeypatch)
    rows[0]["post_financial_8k_metadata"].pop()
    raw = json.dumps({"status": "SOURCE_CAPTURED_REVIEW_ONLY",
                      "production_eligible": False, "issuer_total": 16,
                      "financial_documents_captured": 16, "production_approvals": 0,
                      "source_failures": [], "findings": rows}).encode()
    (tmp_path / "a5e-financial-evidence.json").write_bytes(raw)
    monkeypatch.setattr(mod, "A5E_REPORT_SHA256", sha256(raw).hexdigest())
    with pytest.raises(mod.A5fEvidenceError, match="incomplete"):
        mod.load_frozen_queue(tmp_path)


def test_bad_sec_metadata_url_does_not_become_trusted(monkeypatch, tmp_path):
    rows = _fixture(tmp_path, monkeypatch)
    rows[0]["post_financial_8k_metadata"][0]["document_url"] = (
        "https://www.sec.gov/Archives/edgar/data/100000/000010000026000010/../evil.htm")
    raw = json.dumps({"status": "SOURCE_CAPTURED_REVIEW_ONLY",
                      "production_eligible": False, "issuer_total": 16,
                      "financial_documents_captured": 16, "production_approvals": 0,
                      "source_failures": [], "findings": rows}).encode()
    (tmp_path / "a5e-financial-evidence.json").write_bytes(raw)
    monkeypatch.setattr(mod, "A5E_REPORT_SHA256", sha256(raw).hexdigest())
    with pytest.raises(mod.A5fEvidenceError):
        mod.load_frozen_queue(tmp_path)


def test_all_40_documents_review_only_and_preserved(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    report = mod.run_audit(
        tmp_path, tmp_path/"events", agent="Labyrinth Research research@example.org",
        fetcher=lambda url, agent: SEC_8K, clock=lambda: NOW,
        pause=lambda seconds: None,
    )
    assert report["status"] == "ALL_SOURCES_CAPTURED_REVIEW_ONLY"
    assert report["expected_event_filings"] == 40
    assert report["primary_documents_verified"] == 40
    assert not report["human_review_complete"]
    assert report["issuer_current_bdc_approvals"] == 0
    assert report["production_approvals"] == 0
    assert all(x["status"] == "SEC_8K_PRIMARY_TEXT_REVIEW_CANDIDATE"
               and x["production_eligible"] is False for x in report["findings"])
    assert len(list((tmp_path/"events").glob("CIK*.html"))) == 40


def test_blocked_SEC_document_is_reported_not_called_safe(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    def denied(url, agent):
        raise OSError("403 forbidden")
    report = mod.run_audit(
        tmp_path, tmp_path/"failed", agent="Labyrinth Research research@example.org",
        fetcher=denied, clock=lambda: NOW, pause=lambda seconds: None,
    )
    assert report["status"] == "PARTIAL_SOURCES_REVIEW_ONLY"
    assert report["primary_documents_verified"] == 0
    assert len(report["source_failures"]) == 3
    assert report["production_approvals"] == 0
