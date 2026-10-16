"""A5t: SEC primary bytes and issuer/legal-status guardrails for US production."""
import json
from hashlib import sha256

import pytest

from src.data.universe import a5t_reit_bdc_identity_review as a


def create_sample(tmp_path,monkeypatch):
    bdc=tmp_path/"bdc";reit=tmp_path/"reit"
    bdc.mkdir();reit.mkdir()
    bdcrows=[]
    for i in range(16):
        ticker="LIEN" if i==15 else f"BD{i:02d}"
        cik=f"{1900000+i:010d}"
        acc=f"0001193125-26-{i+120000:06d}"
        raw=(f"<html><body>FORM 10-Q</body><p>Common Stock {ticker} "
             f"New York Stock Exchange</p></html>").encode()
        digest=sha256(raw).hexdigest()
        (bdc/f"CIK{cik}-{acc}-{digest}.html").write_bytes(raw)
        bdcrows.append({
            "cik":cik,"tickers":[ticker],"original_election_accessions":[f"0001111111-24-{i+100000:06d}"],
            "latest_financial":{"form":"10-Q","filing_date":"2026-08-01","accession":acc},
            "latest_financial_observation":{
                "sha256":digest,"bytes":len(raw),
                "retrieved_at":"2026-10-15T12:00:00+00:00",
                "issuer_bdc_status_approved":False,"listed_security_class_approved":False,
                "listed_security_row_candidates":[{"ticker":ticker,
                    "section_12b_row_candidates":[f"Common Stock {ticker} New York Stock Exchange"],
                    "row_evidence_present":True,"share_class_approved":False,
                    "security_id":None}],
            },
            "issuer_bdc_status":"REVIEW_REQUIRED",
            "listed_security_class_status":"REVIEW_REQUIRED",
            "post_financial_events_checked":False,
            "n54c_absence_proven":False,"historical_files_not_downloaded":[],
            "production_eligible":False,
        })
    e={"status":"SOURCE_CAPTURED_REVIEW_ONLY","production_eligible":False,
       "issuer_total":16,"financial_documents_captured":16,
       "row_level_security_evidence_candidates":16,
       "bdc_issuer_status_approvals":0,"security_class_approvals":0,
       "production_approvals":0,"findings":bdcrows}
    reitrows=[]
    for ticker in ("ARR","RHP","WPC"):
        accession="0001104659-26-123456"
        raw=(f"<html><body>Form 10-Q common stock {ticker} New York Stock Exchange</body></html>").encode()
        dg=sha256(raw).hexdigest()
        fn=f"{ticker}-{accession}-{dg}.source"
        (reit/fn).write_bytes(raw)
        reitrows.append({
            "ticker":ticker,"cik":"0001000001","category_for_manual_review":"REIT_VS_FUND",
            "source_security_identity_approved":False,
            "issuer_legal_type_approved":False,
            "production_eligible":False,
            "primary_source":{"form":"10-Q","filing_date":"2026-08-01",
                              "accession":accession},
            "primary_raw_filename":fn,
            "primary_retrieved_at":"2026-10-15T13:00:00+00:00",
            "primary_observation":{
                "source_sha256":dg,"source_bytes":len(raw),
                "text_clues_not_security_type_proof":{"REIT_LANGUAGE":True},
                "section12b_same_row_common_stock_candidate":{
                   "row_present":True,
                   "row_candidates":[f"Common Stock {ticker} New York Stock Exchange"],
                   "security_id_approved":False},
            },
        })
    # Include six irrelevant pilot entries — only three frozen REIT issuers are evaluated.
    for ticker in ("AACI","ADAC","ASPC","CCD","CGO","CSQ"):
        reitrows.append({"ticker":ticker})
    k={"status":"OFFICIAL_SEC_PILOT_REVIEW_ONLY",
       "official_primary_filings_verified":9,"production_eligible":False,
       "listed_security_id_approved":0,"records":reitrows}
    eb=json.dumps(e).encode()
    kb=json.dumps(k).encode()
    (bdc/"a5e-financial-evidence.json").write_bytes(eb)
    (reit/"a5k-sec-pilot-evidence.json").write_bytes(kb)
    monkeypatch.setattr(a,"A5E_SHA",sha256(eb).hexdigest())
    monkeypatch.setattr(a,"A5K_SHA",sha256(kb).hexdigest())
    return bdc,reit,e,k


def test_valid_19_sources_no_production_and_bdc_exception(monkeypatch,tmp_path):
    b,k,e,p=create_sample(tmp_path,monkeypatch)
    result=a.compile_evidence(b,k)
    assert result["original_SEC_common_ticker_venue_row_count"]==19
    assert result["BDC_election_issuer_candidates"]==16
    assert result["REIT_issuer_candidates"]==3
    assert result["review_queue_open"]==19
    assert result["final_security_classification_decisions_closed"]==0
    assert result["production_approvals"]==result["candidate_ALLOW"]==0
    assert not result["independent_US_production_deployed"]
    assert all(x["approval_status"]=="HOLD_SOURCE_EVIDENCE_AND_REVIEW"
               for x in result["records"])
    lien=next(x for x in result["records"] if x["ticker"]=="LIEN")
    assert "LIEN_REFI_MERGER_AND_REFI_BDC_ELECTION_UNRESOLVED" in lien["reason_not_finalized"]


def test_false_current_bdc_status_or_event_review_is_rejected(monkeypatch,tmp_path):
    b,k,e,p=create_sample(tmp_path,monkeypatch)
    e["findings"][0]["post_financial_events_checked"]=True
    eb=json.dumps(e).encode()
    (b/"a5e-financial-evidence.json").write_bytes(eb)
    monkeypatch.setattr(a,"A5E_SHA",sha256(eb).hexdigest())
    with pytest.raises(a.A5tSourceError,match="unsupported current"):
        a.compile_evidence(b,k)


def test_original_filing_sha_mutation_is_fatal(monkeypatch,tmp_path):
    b,k,e,p=create_sample(tmp_path,monkeypatch)
    f=e["findings"][0]
    n=f"CIK{f['cik']}-{f['latest_financial']['accession']}-{f['latest_financial_observation']['sha256']}.html"
    (b/n).write_bytes((b/n).read_bytes()+b"tamper")
    with pytest.raises(a.A5tSourceError,match="SEC 10-Q/10-K bytes"):
        a.compile_evidence(b,k)


def test_spoofed_reit_security_master_approval_is_rejected(monkeypatch,tmp_path):
    b,k,e,p=create_sample(tmp_path,monkeypatch)
    p["records"][0]["source_security_identity_approved"]=True
    raw=json.dumps(p).encode()
    (k/"a5k-sec-pilot-evidence.json").write_bytes(raw)
    monkeypatch.setattr(a,"A5K_SHA",sha256(raw).hexdigest())
    with pytest.raises(a.A5tSourceError,match="Missing REIT"):
        a.compile_evidence(b,k)


def test_untrusted_type_or_ticker_in_same_sec_row_fails_closed():
    with pytest.raises(a.A5tSourceError):
        a._exact_row("Preferred Stock, $1 ARR New York Stock Exchange","ARR")
    with pytest.raises(a.A5tSourceError):
        a._exact_row("Common Stock, $1 ARRP New York Stock Exchange","ARR")
    with pytest.raises(a.A5tSourceError):
        a._exact_row("Common Stock, $1 ARR Other Place","ARR")
