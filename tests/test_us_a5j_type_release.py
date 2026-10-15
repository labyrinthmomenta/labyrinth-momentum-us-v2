"""A5j regression: source-pinned 1010 instruments and DENY-only release gate."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from src.data.universe import a5j_type_release as mod

TS="2026-10-15T09:00:00+00:00"
REASONS=mod.REASONS


def fixture():
    rows=[]
    fund=[]
    q=[]
    chosen=0
    for reason,count in REASONS.items():
        for ix in range(count):
            sym=("LIEN" if reason=="SPAC_BDC_OR_FINANCIAL_REVIEW" and ix==0
                 else f"S{len(rows):04d}")
            cik=f"{2000000+len(rows):010d}"
            if reason=="SPAC_BDC_OR_FINANCIAL_REVIEW" and chosen<16:
                chosen+=1
                evidence_cik=cik
                q.append({
                    "cik":cik,"tickers":[sym],
                    "latest_financial":{"form":"10-Q","filing_date":"2026-08-07",
                                        "accession":f"0001193125-26-{len(rows):06d}"},
                    "latest_financial_observation":{
                        "status":"FINANCIAL_DOCUMENT_REVIEW_EVIDENCE",
                        "issuer_bdc_status_approved":False,
                        "listed_security_class_approved":False,
                        "listed_security_row_candidates":[{
                            "ticker":sym,"row_evidence_present":True,
                            "share_class_approved":False,"security_id":None}],
                        "sha256":"a"*64,"retrieved_at":TS,"bytes":500,
                    },
                    "post_financial_events_checked":False,
                    "n54c_absence_proven":False,
                    "issuer_bdc_status":"REVIEW_REQUIRED",
                    "listed_security_class_status":"REVIEW_REQUIRED",
                    "production_eligible":False,
                })
            row={"listing_source":"nasdaqlisted","symbol":sym,"mic":"XNAS",
                 "source_listing_sha256":mod.A4_NASDAQ_HASH,
                 "source_sec_sha256":"b"*64,
                 "issuer_cik_candidate":cik,
                 "original_a5_reason":reason,"a5i_decision":"REVIEW_REQUIRED",
                 "original_a5_decision":"REVIEW_REQUIRED",
                 "production_eligible":False,
                 "listed_security_class_approved":False,
                 "issuer_legal_status_approved":False}
            rows.append(row)
            fund.append({
                "ticker":sym,"mic":"XNAS","original_review_reason":reason,
                "a4_listing_source_sha256":mod.A4_NASDAQ_HASH,
                "sec_fund_status":"NOT_IN_SEC_FUND_TICKER_FILE",
                "fund_class_candidates":[],"classification_decision":"REVIEW_REQUIRED",
                "approved_security_id":None,"production_eligible":False,
                "fund_registry_source_sha256":mod.SEC_MF_SHA,
                "a5_issuer_cik_candidate":cik,
                "directory_name_clues":["BDC_WORDING"] if sym=="LIEN" else [],
            })
    assert len(rows)==len(fund)==1010 and len(q)==16
    i={
        "version":"a5i-evidence-ledger-review-v1",
        "status":"EVIDENCE_LEDGER_REVIEW_ONLY","as_of":"2026-10-14",
        "production_eligible":False,"production_approvals":0,"auto_promoted":0,
        "source_failures":[],"a5_review_total":1010,"still_review_required":1010,
        "human_review_complete":False,
        "sources":{"a5_review_sha256":mod.A5_INSTRUMENT_HASH},
        "a5_instrument_review_ledger":rows,
        "REFI_separate_corporate_event_hold":True,
        "merger_company_evidence_overlays":[
            {"symbol":"LIEN","explicit_release_hold":True,
             "production_eligible":False,"merger_completion":"NOT_ESTABLISHED",
             "a4_original_decision":"REVIEW_REQUIRED","mic":"XNAS"},
            {"symbol":"REFI","explicit_release_hold":True,
             "production_eligible":False,"merger_completion":"NOT_ESTABLISHED",
             "a4_original_decision":"INCLUDE","mic":"XNAS"},
        ],
    }
    b={
        "status":"REVIEW_ONLY","production_eligible":False,
        "instrument_review_total":1010,
        "sec_fund_source_sha256":mod.SEC_MF_SHA,"approved_instruments":0,
        "fund_ticker_match_status_counts":{"NOT_IN_SEC_FUND_TICKER_FILE":1010},
        "not_in_sec_fund_registry_is_not_proof_of_common_stock":True,
        "sec_fund_retrieved_at":TS,"a4_sec_company_source_sha256":"b"*64,
        "review_entries":fund,
    }
    e={
        "status":"SOURCE_CAPTURED_REVIEW_ONLY","production_eligible":False,
        "issuer_total":16,"financial_documents_captured":16,
        "source_failures":[],"production_approvals":0,
        "bdc_issuer_status_approvals":0,"security_class_approvals":0,
        "findings":q,
    }
    return i,b,e


def test_join_1010_plus_16_verified_sec_proposals_and_no_promotions():
    i,b,e=fixture()
    result=mod.build_triage(i,b,e)
    assert result["total_review_records"]==1010
    assert result["review_by_reason"]==REASONS
    assert result["sec_10q_bdc_issuer_class_candidates"]==16
    assert result["sec_mf_nonmatches_not_exclusions"]==1010
    assert result["promoted_instruments"]==result["approved_security_ids"]==0
    assert sum(r["evidence_tier"]=="SEC_10Q_ISSUER_PLUS_LISTED_CLASS_CANDIDATE"
               for r in result["triage_rows"])==16
    assert all(r["release_hold"] and not r["production_eligible"] for r in result["triage_rows"])
    assert all("SEC_MF_NO_MATCH_IS_NOT_TYPE_PROOF" in r["caution_flags"]
               for r in result["triage_rows"])


def test_release_gate_blocks_1010_and_provisional_refi_separately():
    i,b,e=fixture()
    result=mod.simulate_release_deny_only(mod.build_triage(i,b,e),i)
    assert result["global_release_permission"]=="DENY"
    assert result["candidate_count"]==result["denied_count"]==1011
    assert result["allowed_count"]==0
    assert not result["connected_to_production"]
    assert result["independent_approval_verification_implemented"] is False
    assert not result["other_4555_provisional_includes_evaluated"]
    refi=[r for r in result["release_records"] if r["symbol"]=="REFI"]
    assert len(refi)==1 and refi[0]["reason"]=="PROVISIONAL_INCLUDE_CORPORATE_EVENT_HOLD"


def test_original_review_reason_mutation_fails_closed():
    i,b,e=fixture()
    i["a5_instrument_review_ledger"][0]["original_a5_reason"]="UNKNOWN_INSTRUMENT_TYPE"
    with pytest.raises(mod.A5jEvidenceError):
        mod.build_triage(i,b,e)


def test_wrong_issuer_CIK_crosswalk_blocks_security_identity():
    i,b,e=fixture()
    e["findings"][0]["cik"]="0001999999"
    with pytest.raises(mod.A5jEvidenceError, match="Issuer"):
        mod.build_triage(i,b,e)


def test_spoofed_fund_match_without_corresponding_evidence_is_rejected():
    i,b,e=fixture()
    b["review_entries"][0]["sec_fund_status"]="SEC_FUND_CLASS_CANDIDATE"
    with pytest.raises(mod.A5jEvidenceError,match="source"):
        mod.build_triage(i,b,e)


def test_unverified_trading_class_is_not_promoted():
    i,b,e=fixture()
    e["findings"][0]["latest_financial_observation"]["listed_security_row_candidates"][0]["row_evidence_present"]=False
    with pytest.raises(mod.A5jEvidenceError,match="source"):
        mod.build_triage(i,b,e)


def test_missing_one_registered_10Q_filer_is_not_silently_ignored():
    i,b,e=fixture()
    e["findings"].pop()
    with pytest.raises(mod.A5jEvidenceError):
        mod.build_triage(i,b,e)


def test_reordered_fund_source_is_keyed_by_ticker_mic_and_provenance():
    i,b,e=fixture()
    b["review_entries"].reverse()
    assert mod.build_triage(i,b,e)["total_review_records"]==1010


def test_false_approval_tampering_causes_gate_failure():
    i,b,e=fixture()
    triage=mod.build_triage(i,b,e)
    triage["triage_rows"][0]["release_hold"]=False
    with pytest.raises(mod.A5jEvidenceError):
        mod.simulate_release_deny_only(triage,i)


def test_forged_refi_include_without_hold_is_blocked():
    i,b,e=fixture()
    i["merger_company_evidence_overlays"][1]["explicit_release_hold"]=False
    with pytest.raises(mod.A5jEvidenceError):
        mod.simulate_release_deny_only(mod.build_triage(i,b,e),i)


def test_invalid_or_missing_frozen_source_does_not_supply_approval(tmp_path):
    with pytest.raises(FileNotFoundError):
        mod.read_sources(tmp_path,tmp_path,tmp_path)


def test_valid_timezone_is_required_and_date_only_is_not_point_in_time_proof():
    with pytest.raises(mod.A5jEvidenceError):
        mod._valid_timestamp("2026-10-14T12:00:00")
    assert mod._valid_timestamp(TS).utcoffset() is not None
