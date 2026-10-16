"""A5o: 21 source exceptions, SEC time and identity gates."""
from hashlib import sha256
import json
import pytest
from src.data.universe import a5o_sec_cfi_exceptions as m

def sources():
    listings=[{"symbol":sym,"decision":"INCLUDE","mic":"XNYS"} for sym in m.TARGET]
    sec={"fields":["cik","name","ticker","exchange"],
         "data":[[100000+i,"Company",sym,"NYSE"] for i,sym in enumerate(m.TARGET)]}
    return {"total":13287,"counts":{"INCLUDE":4556,"EXCLUDE":7721,"REVIEW_REQUIRED":1010},
            "production_eligible":False,"rows":listings},sec

def test_all_21_require_same_symbol_and_mic():
    a,s=sources();listing,issuer=m.issuer_index(a,s)
    assert len(issuer)==len(listing)==21
    assert set(m.CI)|{m.TVC}==set(listing)

@pytest.mark.parametrize("invalid",["wrong_mic","promoted","duplicate","missing_cik"])
def test_issuer_crosswalk_must_be_exact(invalid):
    a,s=sources()
    if invalid=="wrong_mic":a["rows"][0]["mic"]="XNAS"
    if invalid=="promoted":a["rows"][0]["decision"]="EXCLUDE"
    if invalid=="duplicate":a["rows"].append(a["rows"][0])
    if invalid=="missing_cik":s["data"].pop()
    with pytest.raises(m.EvidenceError):m.issuer_index(a,s)

def submission(cik):
    return json.dumps({"cik":int(cik),"filings":{
        "recent":{"form":["N-CSR","N-2","N-54A"],
                  "filingDate":["2026-09-19","2026-10-15","2026-01-07"],
                  "accessionNumber":["0000012345-26-000001","0000012345-26-000002",
                                     "0000012345-26-000003"]},
        "files":[{"name":"CIKtest-older.json"}]}}).encode()

def test_asof_excludes_future_filing_and_not_claim_history_absence():
    cik="0000100000"
    out=m.inspect_submissions(submission(cik),cik)
    assert [x["form"] for x in out["form_evidence"]]==["N-CSR"]
    assert out["registered_fund_form_seen_in_recent"] is True
    assert out["historic_filing_chunks_not_fetched"]==1
    assert out["historic_N2_absence_proven"] is False
    assert out["issuer_type_approved"] is False

def test_wrong_cik_is_rejected():
    with pytest.raises(m.EvidenceError,match="CIK"):
        m.inspect_submissions(submission("0000100000"),"0000100001")

def test_source_tamper_without_receipt_is_fatal(tmp_path):
    p=tmp_path/"sec.json";p.write_text("{}")
    with pytest.raises(m.EvidenceError):
        m.source(p,m.SEC_SHA)
