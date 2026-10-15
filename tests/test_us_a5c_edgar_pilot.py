"""Synthetic SEC EDGAR filing evidence tests, no exchange or instrument approval."""
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from src.data.universe import a5c_edgar_pilot as mod

NOW = datetime(2026, 10, 15, 7, 25, tzinfo=timezone.utc)
CIK = "0001287750"


def submission(cik=1287750, *, extra_files=None, forms=None):
    if forms is None:
        forms = [
            ("N-54A", "0001287750-22-000001", "2022-04-02", "n54a.htm"),
            ("N-54C", "0001287750-26-000002", "2026-10-15", "n54c.htm"),
            ("10-K", "0001287750-26-000003", "2026-02-10", "annual.htm"),
            ("S-1", "0001287750-24-000004", "2024-01-02", "s1.htm"),
        ]
    return json.dumps({
        "cik": cik, "name": "Example BDC Corp.", "tickers": ["TEST"],
        "exchanges": ["Nasdaq"],
        "filings": {
            "recent": {
                "form": [f[0] for f in forms],
                "accessionNumber": [f[1] for f in forms],
                "filingDate": [f[2] for f in forms],
                "primaryDocument": [f[3] for f in forms],
            },
            "files": [] if extra_files is None else extra_files,
        },
    }).encode()


def a5_queue():
    rows = [{"symbol": f"BDC{i:03d}", "name": f"BDC Example {i}",
             "original_reason": mod.TARGET_REASON,
             "security_type_approved": False, "production_eligible": False,
             "issuer_match_candidate": {
                 "cik_candidate": f"{i+1000:010d}" if i < 304 else None}}
            for i in range(307)]
    rows.extend({"symbol": f"F{i:03d}", "name": f"Other{i}",
                 "original_reason": "TYPE_UNCONFIRMED",
                 "production_eligible": False}
                for i in range(703))
    return rows


def test_parse_recent_forms_is_not_active_bdc_status():
    result = mod.parse_submissions(submission(), expected_cik=CIK, fetched_at=NOW)
    assert result.cik == CIK
    assert result.history_complete is True
    assert result.sha256 == sha256(submission()).hexdigest()
    assert [x.form for x in result.filings] == ["10-K", "S-1", "N-54A"]
    assert all(x.filing_date <= "2026-10-14" for x in result.filings)
    assert result.filings[0].document_url == (
        "https://www.sec.gov/Archives/edgar/data/1287750/"
        "000128775026000003/annual.htm")


def test_history_overflow_is_explicit_incomplete():
    extra = [{"name": "CIK0001287750-submissions-001.json",
              "filingFrom": "2002-01-01", "filingTo": "2020-12-31", "filingCount": 1200}]
    snap = mod.parse_submissions(submission(extra_files=extra),
                                 expected_cik=CIK, fetched_at=NOW)
    assert not snap.history_complete
    assert len(snap.historical_files) == 1


@pytest.mark.parametrize("payload", [
    b"<html>Not JSON</html>",
    b"[]",
    submission(cik=17),
    json.dumps({"cik":1287750,"name":"X","filings":{"recent":{},"files":[]}}).encode(),
    json.dumps({"cik":1287750,"name":"X","filings":{
        "recent":{"form":["10-K"],"accessionNumber":[],"filingDate":["2026-01-01"],
                  "primaryDocument":["annual.htm"]},"files":[]}}).encode(),
    submission(forms=[("10-K","bad","2026-01-01","a.htm")]),
    submission(forms=[("10-K","0001287750-26-000001","2026-17-01","a.htm")]),
])
def test_bad_sec_submissions_rejected(payload):
    with pytest.raises(mod.EdgarEvidenceError):
        mod.parse_submissions(payload, expected_cik=CIK, fetched_at=NOW)


def test_no_wrong_cik_and_naive_timestamp():
    with pytest.raises(mod.EdgarEvidenceError):
        mod.source_url("not-cik")
    with pytest.raises(mod.EdgarEvidenceError):
        mod.parse_submissions(submission(), expected_cik=CIK,
                              fetched_at=NOW.replace(tzinfo=None))


def test_frozen_queue_integrity_and_selected_cik(monkeypatch, tmp_path):
    data = json.dumps(a5_queue()).encode()
    f = tmp_path / "instrument-review.json"
    f.write_bytes(data)
    monkeypatch.setattr(mod, "EXPECTED_A5_QUEUE_SHA256", sha256(data).hexdigest())
    selected, coverage = mod.load_frozen_candidates(f, limit=5)
    assert len(selected) == 5
    assert coverage["total_review_rows"] == 307
    assert coverage["unique_cik_candidates"] == 304
    assert len(coverage["no_cik_candidate_tickers"]) == 3
    assert coverage["not_selected_issuer_count"] == 299
    f.write_bytes(data + b"\n")
    with pytest.raises(mod.EdgarEvidenceError, match="SHA"):
        mod.load_frozen_candidates(f, limit=5)


def test_pilot_does_not_approve_and_preserves_raw_hashes(monkeypatch, tmp_path):
    data = json.dumps(a5_queue()).encode()
    f = tmp_path / "instrument-review.json"
    f.write_bytes(data)
    monkeypatch.setattr(mod, "EXPECTED_A5_QUEUE_SHA256", sha256(data).hexdigest())

    def fetch_for(cik, agent):
        return submission(cik=int(cik))
    report = mod.run_pilot(f, tmp_path / "edgar", user_agent="Labyrinth Contact test@example.com",
                           limit=2, fetcher=fetch_for, clock=lambda: NOW, pause=lambda _: None)
    assert report["status"] == "CAPTURE_VALIDATED_REVIEW_ONLY"
    assert report["successful_cik_count"] == 2 and report["auto_approved_instruments"] == 0
    assert all(x["security_type_conclusion"] == "REVIEW_REQUIRED"
               and x["production_eligible"] is False
               for x in report["selected_evidence"])
    assert len(list((tmp_path / "edgar").glob("CIK*.json"))) == 2


def test_partial_errors_are_exposed_not_counted_as_absence(monkeypatch, tmp_path):
    data = json.dumps(a5_queue()).encode()
    f = tmp_path / "instrument-review.json"
    f.write_bytes(data)
    monkeypatch.setattr(mod, "EXPECTED_A5_QUEUE_SHA256", sha256(data).hexdigest())
    def fail(cik, agent):
        raise OSError("HTTP 403")
    report = mod.run_pilot(f, tmp_path / "edgar", user_agent="Labyrinth Contact test@example.com",
                           limit=1, fetcher=fail, clock=lambda: NOW, pause=lambda _: None)
    assert report["status"] == "PARTIAL_SOURCE_FAILURE"
    assert report["successful_cik_count"] == 0
    assert report["failed_cik_count"] == 1
    assert report["auto_approved_instruments"] == 0


def test_nested_sec_document_paths_are_allowed_but_traversal_is_never_linked():
    forms = [
        ("10-K", "0001287750-26-000003", "2026-02-10", "xslF345X03/primary_doc.xml"),
        ("N-54A", "0001287750-22-000001", "2022-04-02", "../../other.htm"),
    ]
    out = mod.parse_submissions(submission(forms=forms), expected_cik=CIK, fetched_at=NOW)
    assert out.filings[0].document_url.endswith("xslF345X03/primary_doc.xml")
    assert out.filings[1].document_url is None
