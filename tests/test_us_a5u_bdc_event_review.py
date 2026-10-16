"""A5u verified source chains, exact event identities and guarded statuses."""
from hashlib import sha256
import json
import pytest

from src.data.universe import a5u_bdc_event_review as a


def fixture(tmp_path,monkeypatch):
    d=tmp_path/"a5d";e=tmp_path/"a5e";d.mkdir();e.mkdir()
    elections=[];financial=[]
    for i in range(16):
        cik=f"{1321741+i:010d}"
        sym="LIEN" if i==15 else f"BD{i:02d}"
        forms=[]
        for j in range(2 if i==0 else 1):
            acc=f"0001193125-25-{100000+i*2+j:06d}"
            raw=b"<html><h1>FORM N-54A</h1><p>SEC business development company original election</p></html>"
            dg=sha256(raw).hexdigest()
            (d/f"CIK{cik}-{acc}-{dg}.html").write_bytes(raw)
            forms.append({
                "status":"FORM_TEXT_SIGNAL_VERIFIED","n54a_text_consistent":True,
                "filing_date":"2025-09-12","accession":acc,
                "sha256":dg,"document_bytes":len(raw),
            })
        elections.append({"cik":cik,"election_filings":forms,
                          "current_bdc_status":"UNDETERMINED",
                          "withdrawal_absence_proven":False,
                          "production_eligible":False})
        events=[]
        for n in range(3 if i<8 else 2):
            acc=f"0001193125-26-{200000+i*3+n:06d}"
            events.append({"form":"8-K","filing_date":"2026-09-10",
                           "accession":acc,
                           "document_url":f"https://www.sec.gov/Archives/edgar/data/"
                                          f"{int(cik)}/{acc.replace('-','')}/event.htm"})
        financial.append({
            "cik":cik,"tickers":[sym],"issuer_name":f"TEST_{sym}",
            "original_election_accessions":[x["accession"] for x in forms],
            "latest_financial":{"form":"10-Q","filing_date":"2026-08-07"},
            "n54c_metadata_seen":[],"post_financial_8k_metadata":events,
            "post_financial_events_checked":False,
            "n54c_absence_proven":False,
            "issuer_bdc_status":"REVIEW_REQUIRED",
            "historical_files_not_downloaded":[],
            "production_eligible":False,
        })
    r_d={"status":"DOCUMENT_EVIDENCE_CAPTURED_REVIEW_ONLY",
         "original_cohort_issuers":16,"verified_n54a_primary_documents":17,
         "document_fetch_failures":0,"production_approved":0,
         "not_proof_of_no_n54c":True,"findings":elections}
    r_e={"status":"SOURCE_CAPTURED_REVIEW_ONLY","issuer_total":16,
         "financial_documents_captured":16,"production_eligible":False,
         "bdc_issuer_status_approvals":0,"production_approvals":0,
         "findings":financial}
    bd=json.dumps(r_d).encode();be=json.dumps(r_e).encode()
    (d/"a5d-election-evidence.json").write_bytes(bd)
    (e/"a5e-financial-evidence.json").write_bytes(be)
    monkeypatch.setattr(a,"A5D_SHA",sha256(bd).hexdigest())
    monkeypatch.setattr(a,"A5E_SHA",sha256(be).hexdigest())
    return e,d


def fake_event(url,agent):
    return (b"<html><h1>FORM 8-K</h1><h2>CURRENT REPORT</h2>"
            b"<p>Item 1.01 Entry Into a Material Definitive Agreement</p>"
            b"<p>Reported potential merger subject to voting and additional approval.</p>"
            b"<p>Item 9.01 Financial Statements and Exhibits</p>"
            b"<p>This filing contains additional issuer reporting disclosure "
            b"and forward-looking statement context for testing only.</p>"
            b"</html>")


def test_frozen_40_events_and_17_elections_are_verified(tmp_path,monkeypatch):
    e,d=fixture(tmp_path,monkeypatch)
    source=a._verify_elections(a.read_pinned(d,"a5d-election-evidence.json",a.A5D_SHA),d)
    records=a._verify_a5e(a.read_pinned(e,"a5e-financial-evidence.json",a.A5E_SHA),source)
    assert len(records)==16
    assert sum(len(x["post_financial_8k_metadata"]) for x in records)==40
    out=a.run(e,d,tmp_path/"out","LabyrinthMomentum SourceReviewer test@example.com",
              fetcher=fake_event,pause=lambda s:None)
    assert out["original_8K_primary_documents_verified"]==40
    assert out["N54A_original_primary_files_reverified"]==17
    assert out["N54C_current_absence_proven"] is False
    assert out["independent_current_BDC_status_approvals"]==0
    assert out["candidate_ALLOW"]==0
    assert out["SEC_8K_exhibit_document_reviews_completed"]==0
    assert all(not x["BDC_current_legal_status_verified"] for x in out["issuers"])


def test_8k_keywords_are_only_review_signals():
    row=a.inspect_8k(fake_event(None,None))
    assert row["SEC_form_content_8k_recognized"] is True
    assert "1.01" in row["SEC_item_numbers_observed"]
    assert row["keyword_signals_not_legal_findings"]["CORPORATE_ACTION_WORDING"]
    assert row["triage_priority"]=="CORPORATE_ACTION_OR_LISTING_HUMAN_REVIEW"
    assert row["transaction_closed_or_BDC_current_status_proven"] is False
    assert row["all_exhibits_reviewed"] is False


def test_unverified_event_content_blocked():
    with pytest.raises(a.A5uEvidenceError):
        a.inspect_8k(b"<html>SEC FORM N-54A</html>"*30)


def test_conflicting_event_cik_blocked(tmp_path,monkeypatch):
    e,d=fixture(tmp_path,monkeypatch)
    p=e/"a5e-financial-evidence.json"
    report=json.loads(p.read_text())
    report["findings"][0]["post_financial_8k_metadata"][0]["document_url"]=(
        "https://www.sec.gov/Archives/edgar/data/9999999/"
        "000119312526200000/other.htm")
    raw=json.dumps(report).encode();p.write_bytes(raw)
    monkeypatch.setattr(a,"A5E_SHA",sha256(raw).hexdigest())
    elections=a._verify_elections(a.read_pinned(d,"a5d-election-evidence.json",a.A5D_SHA),d)
    with pytest.raises(a.A5uEvidenceError,match="URL/accession/issuer"):
        a._verify_a5e(a.read_pinned(e,"a5e-financial-evidence.json",a.A5E_SHA),elections)


def test_forged_current_bdc_status_rejected(tmp_path,monkeypatch):
    e,d=fixture(tmp_path,monkeypatch)
    p=d/"a5d-election-evidence.json"
    obj=json.loads(p.read_text())
    obj["findings"][0]["current_bdc_status"]="ACTIVE_CONFIRMED"
    raw=json.dumps(obj).encode();p.write_bytes(raw)
    monkeypatch.setattr(a,"A5D_SHA",sha256(raw).hexdigest())
    with pytest.raises(a.A5uEvidenceError,match="unsupported current status"):
        a._verify_elections(a.read_pinned(d,"a5d-election-evidence.json",a.A5D_SHA),d)


def test_original_n54a_checksum_integrity_is_enforced(tmp_path,monkeypatch):
    e,d=fixture(tmp_path,monkeypatch)
    p=next(d.glob("CIK*.html"))
    p.write_bytes(p.read_bytes()+b"tamper")
    with pytest.raises(a.A5uEvidenceError,match="N-54A SHA256"):
        a._verify_elections(a.read_pinned(d,"a5d-election-evidence.json",a.A5D_SHA),d)


def test_partial_fetch_does_not_claim_full_40(tmp_path,monkeypatch):
    e,d=fixture(tmp_path,monkeypatch)
    calls=0
    def flaky(url,agent):
        nonlocal calls
        calls+=1
        if calls==5:raise OSError("SEC 403")
        return fake_event(url,agent)
    out=a.run(e,d,tmp_path/"partial","LabyrinthMomentum SourceReviewer test@example.com",
              fetcher=flaky,pause=lambda s:None)
    assert out["status"]=="SEC_EVENT_SOURCES_PARTIAL_BLOCKED"
    assert out["original_8K_primary_documents_verified"]==39
    assert out["post_financial_event_primary_sources_still_missing"]==1
    assert out["candidate_ALLOW"]==0


def test_tampered_top_level_receipt_is_never_accepted(tmp_path):
    p=tmp_path/"a5d-election-evidence.json"
    p.write_text("{}")
    with pytest.raises(a.A5uEvidenceError,match="SHA256"):
        a.read_pinned(tmp_path,p.name,a.A5D_SHA)
