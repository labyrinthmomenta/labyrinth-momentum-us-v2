"""A5q: full review inventory preserves every frozen original decision."""
import pytest
from src.data.universe import a5q_full_evidence_queue as m

def fixtures():
    fund="BSTZ GAB GAM TYG BCX BOE GUT ETO VKQ GGT ETX MPV GRX JHS GGZ JHI ECAT MCI BTX BMEZ TVC".split()
    source=["EFTY","HCHL","MCTA","OST","SVA","TAP.A"]
    old=[]
    for decision,count in m.BASE_COUNTS.items():
        for i in range(count):
            sym=f"{decision[:1]}{i:05d}"
            mic="XNAS"
            if decision=="INCLUDE":
                if i<len(fund):sym=fund[i];mic="XNYS"
                elif i<len(fund)+len(source):sym=source[i-len(fund)];mic="XNYS" if sym=="TAP.A" else "XNAS"
                elif i==100:sym="REFI"
            if decision=="REVIEW_REQUIRED" and i==0:sym="LIEN"
            if 200<=i<514 and decision=="INCLUDE":mic="XASE"
            if decision=="REVIEW_REQUIRED" and 100<=i<136:mic="XASE"
            if decision=="EXCLUDE" and 100<=i<153:mic="XASE"
            old.append({
                "source":"nasdaqlisted" if mic=="XNAS" else "otherlisted",
                "symbol":sym,"mic":mic,"name":sym,
                "original_a4_decision":decision,
                "original_a4_reason":"SOURCE_REVIEW",
                "release_result":"EXCLUDED_BY_ORIGINAL_A4_NEVER_RELEASED" if decision=="EXCLUDE" else
                                 "DENY_OFFICIAL_SECURITY_TYPE_UNAPPROVED",
                "release_eligible":False,
            })
    # Reproduce exact 314 XASE by replacing a subset for synthetic coverage.
    a5k={"status":"FULL_UNIVERSE_SOURCE_REPLAY_DENY_ONLY",
         "all_source_listings_checked":13287,"original_a4_counts":m.BASE_COUNTS,
         "candidate_DENY":5566,"candidate_ALLOW":0,
         "connected_to_production":False,"review_records":old}
    a5o={"status":"ISSUER_EVIDENCE_REVIEW_ONLY",
         "sources_verified":21,"fund_form_seen_count":20,
         "classification_decisions_closed":0,"production_approvals":0,
         "rows":[{"ticker":s,"status":"SEC_ISSUER_FORMS_CAPTURED_REVIEW_ONLY",
                  "source_A4_decision":"INCLUDE","production_eligible":False,
                  "issuer_type_approved":False,"listed_security_id_approved":False}
                 for s in fund]}
    a5p={"status":"COVERAGE_AND_TIME_REVIEW_ONLY",
         "tv_only_unresolved":7,"official_only_provisional_includes":6,
         "XASE_no_TradingView_exchange_label":314,
         "production_approvals":0,"official_only_include_details":[
            {"symbol":s,"mic":"XNYS" if s=="TAP.A" else "XNAS",
             "decision":"INCLUDE_PROVISIONAL"} for s in source]}
    # Move XASE inclusion slice so total is 314: 225 include, 36 review, 53 exclude.
    for row in old:
        if row["mic"]=="XASE" and row["original_a4_decision"]=="INCLUDE" and row["symbol"]>= "I00425":
            row["mic"]="XNAS"
    return a5k,a5o,a5p

def test_13827_evidence_gate_all_denied():
    a,b,c=fixtures()
    # Synthetic fixture may have case-specific MIC counts; flag total still 314
    out=m.make_queue(a,b,c)
    assert out["source_records"]==13287
    assert out["candidate_DENY"]==5566 and out["candidate_ALLOW"]==0
    assert out["new_sec_issuer_conflict_overlays"]==21
    assert out["new_tv_source_coverage_overlays"]==6
    assert out["corporate_event_holds_LIEN_REFI"]==2
    assert all(not x["production_eligible"] for x in out["queue"])

def test_sec_approval_spoof_is_fatal():
    a,b,c=fixtures()
    b["rows"][0]["issuer_type_approved"]=True
    with pytest.raises(m.LedgerError):m.make_queue(a,b,c)

def test_untrusted_frozen_source_rejected(tmp_path):
    p=tmp_path/"a5o.json";p.write_text("{}")
    with pytest.raises(m.LedgerError):m.load(p,m.A5O_SHA)
