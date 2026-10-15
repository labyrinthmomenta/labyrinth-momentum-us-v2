"""SEC A5h evidence is not proof of a completed LIEN/REFI merger."""
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from src.data.universe import a5h_remaining_exhibits as mod

NOW = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
EXHIBIT = (b"<html><body>EX-99.1 Quarterly Financial Results. "
           b"This statement discusses a possible merger subject to approvals. "
           b"No merger closing has been announced in this document. "
           b"This announcement includes forward looking statements.</body></html>")
N14 = (b"<html><body><h1>FORM N-14 REGISTRATION STATEMENT</h1>"
       b"<h3>PRELIMINARY JOINT PROXY STATEMENT / PROSPECTUS</h3>"
       + b"<p>LIEN and REFI shareholders will be asked to vote on the proposed "
       b"merger agreement, subject to SEC effectiveness and other conditions.</p>" * 7
       + b"</body></html>")


def SEC_json(cik: str, *, past=True, history=False) -> bytes:
    events = [
        ("N-14 8C/A", "2026-09-22", "0001140361-26-037360", "proxy/n14.htm"),
        ("EFFECT", "2026-09-30", "9999999995-26-003107", "primary_doc.xml"),
        ("8-K", "2026-10-01", "0001213900-26-103456", "8k.htm"),
        ("DEFM14A", "2026-10-16", "0001213900-26-111111", "definitive.htm"),
    ] if past else []
    return json.dumps({
        "cik": int(cik), "name": "Example SEC filer",
        "filings": {
            "recent": {
                "form": [x[0] for x in events],
                "filingDate": [x[1] for x in events],
                "accessionNumber": [x[2] for x in events],
                "primaryDocument": [x[3] for x in events],
            },
            "files": ([{"name":"CIK0001843162-submissions-001.json"}] if history else []),
        }
    }).encode()


def fake_missing():
    return [{
        "cik": mod.LIEN_CIK,
        "accession": f"0001213900-26-{i+800000:06d}",
        "filing_date": "2026-09-01",
        "ticker_candidates": ["LIEN"],
        "type": "EX-99.1",
        "url": (f"https://www.sec.gov/Archives/edgar/data/1843162/"
                f"000121390026{i+800000:06d}/report.htm"),
        "index_sha256": "0" * 64,
        "production_eligible": False,
    } for i in range(29)]


def test_only_two_merger_issuer_CIKs_accepted():
    assert mod.submissions_url(mod.LIEN_CIK).endswith("CIK0001843162.json")
    assert mod.submissions_url(mod.REFI_CIK).endswith("CIK0001867949.json")
    with pytest.raises(mod.A5hEvidenceError):
        mod.submissions_url("0001287750")


def test_timeline_preserves_effect_as_not_closing_and_excludes_future():
    data = SEC_json(mod.LIEN_CIK, history=True)
    output = mod.parse_submissions_timeline(data, cik=mod.LIEN_CIK, retrieved_at=NOW)
    assert output["n14_filings"] == 1
    assert output["effect_filings"] == 1
    assert len(output["filings"]) == 3
    assert output["older_submissions_history_not_downloaded"] is True
    assert not output["merger_closing_verified"]
    assert not output["voting_outcome_verified"]
    assert not output["security_identity_approved"]


def test_sec_submission_wrong_cik_schema_or_missing_timezone_rejected():
    with pytest.raises(mod.A5hEvidenceError, match="identity"):
        mod.parse_submissions_timeline(SEC_json(mod.LIEN_CIK),
                                       cik=mod.REFI_CIK, retrieved_at=NOW)
    with pytest.raises(mod.A5hEvidenceError, match="timezone"):
        mod.parse_submissions_timeline(SEC_json(mod.LIEN_CIK),
                                       cik=mod.LIEN_CIK, retrieved_at=NOW.replace(tzinfo=None))
    with pytest.raises(mod.A5hEvidenceError, match="JSON"):
        mod.parse_submissions_timeline(b"<html>Access Denied</html>",
                                       cik=mod.LIEN_CIK, retrieved_at=NOW)


def test_sec_timeline_rejects_path_traversal():
    obj = json.loads(SEC_json(mod.LIEN_CIK))
    obj["filings"]["recent"]["primaryDocument"][0] = "../wrong.htm"
    with pytest.raises(mod.A5hEvidenceError, match="Unsafe"):
        mod.parse_submissions_timeline(json.dumps(obj).encode(),
                                       cik=mod.LIEN_CIK, retrieved_at=NOW)


def test_registration_preliminary_proxy_is_review_only():
    result = mod.inspect_registration(N14)
    assert result["source_text_clues_for_human_review"]["JOINT_PROXY"]
    assert result["source_text_clues_for_human_review"]["PRELIMINARY_LANGUAGE"]
    assert result["merger_completion_verified"] is False
    assert result["security_id_approved"] is False
    with pytest.raises(mod.A5hEvidenceError):
        mod.inspect_registration(b"<html>Access Denied</html>" * 40)


@pytest.mark.parametrize("url", [
    "https://data.sec.gov/submissions/CIK0009999999.json",
    "http://data.sec.gov/submissions/CIK0001843162.json",
    "https://evil.example.com/submissions/CIK0001843162.json",
    "https://www.sec.gov/Archives/edgar/data/1843162/000121390026088673/../bad.htm",
])
def test_network_source_allowlist_rejects_untrusted_paths(url):
    with pytest.raises(mod.A5hEvidenceError):
        mod.retrieve_official(url, "Research researcher@example.org", max_bytes=10000)


def test_missing_frozen_a5g_report_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        mod.load_a5g(tmp_path)


def test_29_source_pipeline_without_any_production_decision(monkeypatch, tmp_path):
    def fake_load(_):
        return fake_missing(), {"a5g_report_sha256": mod.A5G_REPORT_SHA256,
                                "verified_source_indexes": 34}
    monkeypatch.setattr(mod, "load_a5g", fake_load)
    def fetch(url, agent, *, max_bytes):
        if url.endswith(".json"):
            return SEC_json(mod.LIEN_CIK if "1843162" in url else mod.REFI_CIK)
        if "proxy/n14.htm" in url:
            return N14
        return EXHIBIT
    report = mod.audit(tmp_path, tmp_path / "a5h", agent="Research tester@example.org",
                       fetcher=fetch, clock=lambda:NOW, pause=lambda _ :None)
    assert report["status"] == "DOCUMENTS_CAPTURED_REVIEW_ONLY"
    assert report["exhibits_verified"] == 29
    assert report["merger_issuer_timelines_verified"] == 2
    assert report["LIEN_N14_document_verified"] == 1
    assert report["merger_closed_confirmed"] is False
    assert report["production_approved"] == 0
    assert not report["human_review_complete"]
    assert all(x["event_closing_confirmed"] is False for x in report["exhibit_evidence"])


def test_partial_denied_sec_source_remains_review_not_success(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "load_a5g", lambda _: (fake_missing(), {}))
    def denied(url, agent, *, max_bytes):
        raise OSError("403 SEC blocked")
    report = mod.audit(tmp_path, tmp_path/"blocked", agent="Research tester@example.org",
                       fetcher=denied, clock=lambda: NOW, pause=lambda _ :None)
    assert report["status"] == "PARTIAL_REVIEW_ONLY"
    assert report["exhibits_verified"] == 0
    assert report["production_approved"] == 0
    assert len(report["errors"]) == 3
