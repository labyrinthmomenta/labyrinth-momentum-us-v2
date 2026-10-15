"""A5k: nine official SEC issuer type candidates, never instrument approvals."""
from datetime import datetime, timezone
import json
from hashlib import sha256

import pytest

from src.data.universe import a5k_sec_type_pilot as mod

NOW=datetime(2026,10,15,16,0,tzinfo=timezone.utc)
BODY=(b"<html><body><h1>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</h1>"
      b"<h2>Form 10-Q</h2><p>Common Stock Class A; "
      b"This document mentions a blank check company, business development company, "
      b"real estate investment trust and closed-end investment company as examples."
      b"These statements alone do not determine the listed security type.</p>"
      + b"<p>Issuer 2026 financial statements and accompanying notes.</p>"*5
      + b"</body></html>")


def subs(cik,form="10-Q",day="2026-08-10",filename="report.htm"):
    return json.dumps({
        "cik":int(cik),"name":"SEC sample issuer",
        "filings":{"recent":{
            "form":[form,"10-Q"],"filingDate":[day,"2026-10-15"],
            "accessionNumber":["0001193125-26-123456","0001193125-26-123457"],
            "primaryDocument":[filename,"future.htm"],
        },"files":[]}
    }).encode()


def test_sec_submission_parse_rejects_future_and_corrects_zero_padding():
    cik=mod.PILOT["ARR"][0]
    result=mod.parse_submission(subs(cik),cik=cik,category="REIT_VS_FUND",at=NOW)
    assert result["candidate_filing"]["filing_date"]=="2026-08-10"
    assert result["filing_candidates_count"]==1
    assert result["candidate_document_class_approved"] is False


@pytest.mark.parametrize("file", ["../evil.htm","https://other.test/a.htm","bad?query.htm"])
def test_untrusted_sec_primary_document_path_rejected(file):
    cik=mod.PILOT["ADAC"][0]
    with pytest.raises(mod.OfficialTypeError):
        mod.parse_submission(subs(cik,form="S-1",filename=file),
                             cik=cik,category="SPAC_OR_BLANK_CHECK",at=NOW)


def test_wrong_company_cik_rejected_before_primary_filing_link():
    cik=mod.PILOT["CGO"][0]
    wrong=mod.PILOT["ARR"][0]
    with pytest.raises(mod.OfficialTypeError,match="CIK"):
        mod.parse_submission(subs(wrong,form="N-CSR"),
                             cik=cik,category="CLOSED_END_FUND_VS_BDC",at=NOW)


def test_sec_filing_wording_does_not_prove_a_security_class():
    z=mod.inspect_primary(BODY,category="SPAC_OR_BLANK_CHECK",ticker="ADAC")
    assert z["text_clues_not_security_type_proof"]["COMMON_STOCK_LANGUAGE"]
    assert z["text_clues_not_security_type_proof"]["BLANK_CHECK_LANGUAGE"]
    assert z["text_clues_not_security_type_proof"]["BDC_LANGUAGE"]
    assert z["title_class_security_id_verified"] is False
    assert z["business_entity_legal_status_approved"] is False
    assert z["production_eligible"] is False


def test_9_issuer_pilot_all_official_metadata_but_no_approval(monkeypatch,tmp_path):
    source_rows=[
        {"symbol":sym,"issuer_cik_candidate":cik,
         "a5i_decision":"REVIEW_REQUIRED","release_hold":True,
         "production_eligible":False}
        for sym,(cik,group) in mod.PILOT.items()]
    monkeypatch.setattr(mod,"_frozen_json",lambda *args:{
        "status":"CLASSIFICATION_EVIDENCE_TRIAGE_REVIEW_ONLY",
        "production_eligible":False,"total_review_records":1010,
        "triage_rows":source_rows + [{"symbol":f"OTHER{x}"} for x in range(1001)]})
    def fetch(url,agent,*,limit):
        if url.endswith(".json"):
            cik=url.split("CIK")[-1].removesuffix(".json")
            cat=next(t for c,t in mod.PILOT.values() if c==cik)
            form=("S-1" if cat=="SPAC_OR_BLANK_CHECK" else
                  "N-CSR" if cat=="CLOSED_END_FUND_VS_BDC" else "10-Q")
            return subs(cik,form=form)
        return BODY
    result=mod.run_pilot(tmp_path,tmp_path/"out",agent="Example SEC contact@example.org",
                         fetcher=fetch,clock=lambda:NOW,pause=lambda _:None)
    assert result["status"]=="OFFICIAL_SEC_PILOT_REVIEW_ONLY"
    assert result["official_primary_filings_verified"]==9
    assert result["listed_security_id_approved"]==0
    assert result["instrument_type_decisions_completed"]==0
    assert sum(x["production_eligible"] for x in result["records"])==0


def test_lack_of_trusted_recent_filing_keeps_incomplete_source_status(monkeypatch,tmp_path):
    rows=[{"symbol":sym,"issuer_cik_candidate":cik,
           "a5i_decision":"REVIEW_REQUIRED","release_hold":True,
           "production_eligible":False} for sym,(cik,_) in mod.PILOT.items()]
    monkeypatch.setattr(mod,"_frozen_json",lambda *args:{
        "status":"CLASSIFICATION_EVIDENCE_TRIAGE_REVIEW_ONLY",
        "production_eligible":False,"total_review_records":1010,
        "triage_rows":rows+[{"symbol":f"X{n}"} for n in range(1001)]})
    def fetch(url,agent,*,limit):
        if url.endswith(".json"):
            cik=url.split("CIK")[-1].removesuffix(".json")
            return subs(cik,form="10-K",day="2026-10-15")
        return BODY
    result=mod.run_pilot(tmp_path,tmp_path/"out",agent="Example contact@example.org",
                         fetcher=fetch,clock=lambda:NOW,pause=lambda _:None)
    assert result["status"]=="OFFICIAL_SEC_PILOT_PARTIAL_REVIEW_ONLY"
    assert result["listed_security_id_approved"]==0


def test_untrusted_data_sec_org_target_refused_without_network():
    with pytest.raises(mod.OfficialTypeError):
        mod.fetch_sec("https://data.sec.gov/submissions/CIK0000000001.json",
                      "Example contact@example.org",limit=1024)


def test_10q_adds_cautious_section_12b_same_row_candidate_no_release(monkeypatch,tmp_path):
    rows=[{"symbol":sym,"issuer_cik_candidate":cik,"a5i_decision":"REVIEW_REQUIRED",
           "release_hold":True,"production_eligible":False}
          for sym,(cik,_) in mod.PILOT.items()]
    monkeypatch.setattr(mod,"_frozen_json",lambda *args:{
        "status":"CLASSIFICATION_EVIDENCE_TRIAGE_REVIEW_ONLY",
        "production_eligible":False,"total_review_records":1010,
        "triage_rows":rows+[{"symbol":f"ELSE{i}"} for i in range(1001)]})
    doc=(b"<html><body><h2>FORM 10-Q</h2><p>Quarterly Report Pursuant to SEC rules.</p>"
         b"<table><tr><td>Common Stock $0.01 par value</td><td>ARR</td>"
         b"<td>New York Stock Exchange</td></tr></table>"
         + b"<p>Quarterly financial statements SEC issuer report.</p>"*18
         + b"</body></html>")
    def fetch(url,agent,*,limit):
        if url.endswith(".json"):
            cik=url.split("CIK")[-1].removesuffix(".json")
            category=next(cat for c,cat in mod.PILOT.values() if c==cik)
            form=("S-1" if category=="SPAC_OR_BLANK_CHECK" else
                  "N-CSR" if category=="CLOSED_END_FUND_VS_BDC" else "10-Q")
            return subs(cik,form=form)
        return doc
    result=mod.run_pilot(tmp_path,tmp_path/"row",agent="SEC Research lab@example.org",
                         fetcher=fetch,clock=lambda:NOW,pause=lambda _:None)
    arr=next(r for r in result["records"] if r["ticker"]=="ARR")
    row=arr["primary_observation"]["section12b_same_row_common_stock_candidate"]
    assert row["row_present"] is True
    assert row["security_id_approved"] is False
    assert result["listed_security_id_approved"]==0
