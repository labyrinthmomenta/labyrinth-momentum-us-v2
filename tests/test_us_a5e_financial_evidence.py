"""A5e evidence-only tests: legal issuer status must not become security approval."""
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from src.data.universe import a5e_financial_evidence as mod

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
CIK = "0001321741"
HTML = b"""<html><body><h1>FORM 10-Q</h1>
<p>QUARTERLY REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES EXCHANGE ACT</p>
<table><tr><th>Title of each class</th><th>Trading Symbol</th>
<th>Name of exchange on which registered</th></tr>
<tr><td>Common Stock, par value $0.001</td><td>GAIN</td>
<td>Nasdaq Global Select Market</td></tr>
<tr><td>6.25% Notes due 2029</td><td>GAINZ</td><td>Nasdaq</td></tr>
</table>
<p>We are a business development company that has elected to be regulated as a
business development company under the Investment Company Act of 1940.</p>
<p>Regulations and risk factors are described throughout this document
and should be reviewed against our current securities reports.</p>
</body></html>"""


def original_sec_json():
    filings = [
        ("10-K", "2026-03-01", "0001321741-26-000001", "annual.htm"),
        ("10-Q", "2026-08-06", "0001321741-26-000002", "quarterly.htm"),
        ("8-K", "2026-08-10", "0001321741-26-000003", "event.htm"),
        ("10-Q", "2026-10-15", "0001321741-26-000004", "future.htm"),
        ("N-54C", "2026-10-15", "0001321741-26-000005", "future-election.htm"),
    ]
    return json.dumps({
        "cik": 1321741,
        "filings": {"recent": {
            "form": [x[0] for x in filings],
            "filingDate": [x[1] for x in filings],
            "accessionNumber": [x[2] for x in filings],
            "primaryDocument": [x[3] for x in filings],
        }},
    }).encode()


def test_latest_asof_filing_chosen_and_future_forms_excluded():
    docs = mod._full_recent_filings(original_sec_json(), CIK)
    assert [(x["form"], x["filing_date"]) for x in docs] == [
        ("8-K", "2026-08-10"), ("10-Q", "2026-08-06"), ("10-K", "2026-03-01")]
    assert docs[1]["document_url"].endswith("/000132174126000002/quarterly.htm")


def test_traversal_rejected_in_source_locator():
    with pytest.raises(mod.A5eEvidenceError):
        mod._filing_url(CIK, "0001321741-26-000001", "../wrong.htm")


def test_financial_document_yields_advisory_bdc_and_share_row_signals():
    r = mod.inspect_financial(HTML, expected_tickers=["GAIN","GAINZ"])
    assert r["financial_form_text_present"]
    assert r["bdc_phrase_occurrences"] > 0
    assert len(r["bdc_status_sentence_candidates"]) >= 1
    assert r["listed_security_row_candidates"][0]["row_evidence_present"]
    assert not r["listed_security_row_candidates"][1]["row_evidence_present"]
    assert all(x["share_class_approved"] is False for x in r["listed_security_row_candidates"])
    assert r["production_eligible"] is False and r["security_type_status"] == "REVIEW_REQUIRED"


def test_different_issuers_ticker_not_accidentally_matched():
    x = mod.inspect_financial(HTML, expected_tickers=["GAI", "OTHER"])
    assert not any(v["row_evidence_present"] for v in x["listed_security_row_candidates"])


def test_fake_sec_access_denied_html_fails_closed():
    with pytest.raises(mod.A5eEvidenceError, match="resemble"):
        mod.inspect_financial(b"<html><body>Access Denied</body></html>",
                              expected_tickers=["GAIN"])


def test_substantive_report_without_bdc_phrase_does_not_certify_non_bdc():
    html = b"<h1>FORM 10-Q</h1>" + b"<p>Ordinary report text.</p>" * 90
    r = mod.inspect_financial(html, expected_tickers=["FAKE"])
    assert not r["bdc_status_sentence_candidates"]
    assert r["bdc_issuer_status"] == "REQUIRES_HUMAN_FILING_REVIEW"
    assert not r["production_eligible"]


def test_expected_ticker_validation():
    with pytest.raises(mod.A5eEvidenceError, match="Unsafe"):
        mod.inspect_financial(HTML, expected_tickers=["../GAIN"])


@pytest.mark.parametrize("bad", [
    "https://untrusted.example.net/Archives/edgar/data/1321741/000132174126000001/doc.htm",
    "https://www.sec.gov/Archives/edgar/data/1321741/000132174126000001/../doc.htm",
    "https://www.sec.gov/Archives/edgar/data/1321741/000132174126000001/doc.htm?q=evil",
])
def test_external_or_malformed_archive_urls_rejected(bad):
    with pytest.raises(mod.A5eEvidenceError):
        mod.fetch_financial(bad, "Research research@example.org")


def test_evidence_only_and_partial_failure(monkeypatch, tmp_path):
    record = {
        "cik": CIK, "tickers": ["GAIN"], "issuer_name": "Example",
        "latest_financial": {"form":"10-Q","accession":"0001321741-26-000002",
                             "filing_date":"2026-08-06",
                             "document_url":"https://www.sec.gov/Archives/edgar/data/1321741/000132174126000002/quarterly.htm"},
        "post_financial_8k_metadata": [{"form":"8-K","filing_date":"2026-08-10"}],
        "n54c_metadata_seen":[],
        "historical_files_not_downloaded": [],
    }
    monkeypatch.setattr(mod,"load_inputs",
                        lambda a,b: ([record],{"a5c_report_sha256":"test",
                                                "a5d_report_sha256":"test"}))
    out = mod.run_a5e(tmp_path, tmp_path, tmp_path/"ok",
                       agent="Research research@example.org",
                       fetcher=lambda url, agent:HTML,
                       clock=lambda: NOW, pause=lambda _: None)
    assert out["status"] == "SOURCE_CAPTURED_REVIEW_ONLY"
    assert out["financial_documents_captured"] == 1
    assert out["production_approvals"] == 0
    assert not out["findings"][0]["post_financial_events_checked"]
    assert out["findings"][0]["issuer_bdc_status"] == "REVIEW_REQUIRED"
    raw = list((tmp_path/"ok").glob("CIK*.html"))
    assert len(raw) == 1 and sha256(raw[0].read_bytes()).hexdigest() == sha256(HTML).hexdigest()
    fail = mod.run_a5e(tmp_path,tmp_path,tmp_path/"fail",
                        agent="Research research@example.org",
                        fetcher=lambda url,agent: (_ for _ in ()).throw(OSError("SEC inaccessible")),
                        clock=lambda:NOW,pause=lambda _:None)
    assert fail["status"] == "PARTIAL_SOURCE_FAILURE"
    assert fail["production_approvals"] == 0


def test_valid_report_without_a5d_and_a5c_artifacts_not_trusted(tmp_path):
    with pytest.raises(FileNotFoundError):
        mod.load_inputs(tmp_path/"a5c", tmp_path/"a5d")
