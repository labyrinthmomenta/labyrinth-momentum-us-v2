"""A5t: Source-pinned 16 BDC and 3 REIT SEC security-class verification.

Original SEC N-54A and 10-Q/10-K are evidence only. A filer CIK or
issuer self-description is not a verified independent listed security ID.
The US-v2 production namespace is reserved, but is NOT wired or deployed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

from .a5s_scope_policy import Evidence, review, POLICY_VERSION

A5E_SHA="a58638402bbdc59b7afb2de3dfe439c6672cc0a1ede40fb59bd8a283aea7612f"
A5K_SHA="e34c0fe0a2260a4d1a323591364ac9b509c1fc39ea49d9c9c40a4bc36c3d63ef"
SEC_AS_OF="2026-10-14"
VERSION="a5t-19-official-issuer-class-review-v1"
REIT_TICKERS=frozenset({"ARR","RHP","WPC"})
NON_COMMON_REVIEW=frozenset({"PREFERRED","WARRANT","UNIT","DEBT"})
MIC_RE=re.compile(r"(?i)\b(?:the )?nasdaq(?: stock market| global select market)?\b|\b(?:the )?new york stock exchange\b|\bNYSE\b")


class A5tSourceError(ValueError):
    pass


def _source(folder:Path,name:str,digest:str)->dict:
    raw=(folder/name).read_bytes()
    if sha256(raw).hexdigest()!=digest:
        raise A5tSourceError(f"Frozen official SEC review receipt modified: {name}")
    doc=json.loads(raw)
    if not isinstance(doc,dict):
        raise A5tSourceError("Source root is not JSON object")
    return doc


def _raw_verify(folder:Path,name:str,digest:str,expected_bytes:int)->bytes:
    f=folder/name
    if not f.is_file() or f.stat().st_size>64*1024*1024:
        raise A5tSourceError("SEC primary original missing or oversized")
    raw=f.read_bytes()
    if len(raw)!=expected_bytes or sha256(raw).hexdigest()!=digest:
        raise A5tSourceError("Original SEC 10-Q/10-K bytes do not match receipt")
    return raw


def _exact_row(s:str,ticker:str)->str:
    compact=" ".join(s.split())
    if not re.search(r"\bcommon\s+(?:stock|shares?)\b",compact,re.I):
        raise A5tSourceError(f"{ticker}: SEC row not common shares")
    if not re.search(r"(?<![A-Z0-9.])"+re.escape(ticker)+r"(?![A-Z0-9.])",compact,re.I):
        raise A5tSourceError(f"{ticker}: ticker not present in same SEC security row")
    if not MIC_RE.search(compact):
        raise A5tSourceError(f"{ticker}: no exchange in same SEC security row")
    return compact[:600]


def _bdc_candidates(e:dict,folder:Path)->list[dict]:
    if (e.get("status")!="SOURCE_CAPTURED_REVIEW_ONLY"
        or e.get("production_eligible") is not False
        or e.get("issuer_total")!=16
        or e.get("financial_documents_captured")!=16
        or e.get("row_level_security_evidence_candidates")!=16
        or e.get("bdc_issuer_status_approvals")!=0
        or e.get("security_class_approvals")!=0
        or e.get("production_approvals")!=0
        or len(e.get("findings",[]))!=16):
        raise A5tSourceError("A5e source cohort is not exact 16-issuer review-only proof")
    records=[]
    for x in e["findings"]:
        c=x["cik"]
        candidates=x["tickers"]
        filing=x["latest_financial"]
        obs=x["latest_financial_observation"]
        if (not isinstance(c,str) or not re.fullmatch(r"[0-9]{10}",c)
            or not isinstance(candidates,list) or len(candidates)!=1
            or x["issuer_bdc_status"]!="REVIEW_REQUIRED"
            or x["listed_security_class_status"]!="REVIEW_REQUIRED"
            or x["production_eligible"] is not False
            or x["post_financial_events_checked"] is not False
            or x["n54c_absence_proven"] is not False
            or len(x["original_election_accessions"])<1
            or filing["form"] not in ("10-Q","10-K")
            or filing["filing_date"]>SEC_AS_OF
            or obs["issuer_bdc_status_approved"] is not False
            or obs["listed_security_class_approved"] is not False):
            raise A5tSourceError("BDC issuer source claims unsupported current/approved status")
        ticker=candidates[0]
        proof=obs["listed_security_row_candidates"]
        if len(proof)!=1 or proof[0]["ticker"]!=ticker or proof[0]["row_evidence_present"] is not True or proof[0]["share_class_approved"] is not False or proof[0]["security_id"] is not None or len(proof[0]["section_12b_row_candidates"])!=1:
            raise A5tSourceError("Missing exact one BDC listed common class row candidate")
        row=_exact_row(proof[0]["section_12b_row_candidates"][0],ticker)
        rawfile=f"CIK{c}-{filing['accession']}-{obs['sha256']}.html"
        _raw_verify(folder,rawfile,obs["sha256"],obs["bytes"])
        legal="N54A_ELECTION_ORIGINAL_PRESENT_BUT_CURRENT_STATUS_UNVERIFIED"
        reasons=["N54C_WITHDRAWAL_ABSENCE_NOT_PROVEN",
                 "POST_FINANCIAL_EVENTS_NOT_DOCUMENT_REVIEWED",
                 "INDEPENDENT_LISTED_SECURITY_MASTER_MISSING",
                 "AUTHORIZED_REVIEWER_NOT_APPROVED"]
        if ticker=="LIEN":
            reasons.append("LIEN_REFI_MERGER_AND_REFI_BDC_ELECTION_UNRESOLVED")
        if x["historical_files_not_downloaded"]:
            reasons.append("SEC_OLDER_HISTORY_CHUNKS_NOT_REVIEWED")
        p=review(Evidence(ticker=ticker,mic="XNYS" if re.search(r"\bNYSE\b|New York Stock Exchange",row,re.I) else "XNAS",issuer_type="BDC",
               listed_class="COMMON_STOCK",issuer_status_verified=False,listed_class_verified=False))
        records.append({
            "ticker":ticker,"cik_issuer_candidate":c,"category":"BDC_ISSUER_CANDIDATE",
            "financial_filing":filing,"sec_original_source_sha256":obs["sha256"],
            "sec_primary_retrieved_at":obs["retrieved_at"],
            "n54a_election_accession_candidates":x["original_election_accessions"],
            "SEC_section12b_ticker_class_venue_candidate":row,
            "issuer_legal_status_evidence_tier":legal,
            "current_BDC_election_status_verified":False,
            "closed_end_fund_exclusion_overridden_by_evidence":False,
            "reason_not_finalized":reasons,
            "policy_suggestion":p["classification_proposal"],
            "approval_status":"HOLD_SOURCE_EVIDENCE_AND_REVIEW",
            "permanent_security_id":None,
            "independent_security_id_verified":False,
            "listed_class_independently_approved":False,
            "source_known_at_as_of_verified":False,
            "production_eligible":False,
        })
    return records


def _reit_candidates(k:dict,folder:Path)->list[dict]:
    if (k.get("status")!="OFFICIAL_SEC_PILOT_REVIEW_ONLY"
        or k.get("official_primary_filings_verified")!=9
        or k.get("production_eligible") is not False
        or k.get("listed_security_id_approved")!=0
        or len(k.get("records",[]))!=9):
        raise A5tSourceError("A5k original SEC pilot not complete review-only")
    records=[]
    for x in k["records"]:
        sym=x["ticker"]
        if sym not in REIT_TICKERS:continue
        obs=x["primary_observation"]
        same=obs["section12b_same_row_common_stock_candidate"]
        filing=x["primary_source"]
        if (x["category_for_manual_review"]!="REIT_VS_FUND"
            or x["source_security_identity_approved"] is not False
            or x["issuer_legal_type_approved"] is not False
            or x["production_eligible"] is not False
            or filing["form"] not in ("10-Q","10-K")
            or filing["filing_date"]>SEC_AS_OF
            or same["row_present"] is not True
            or same["security_id_approved"] is not False
            or len(same["row_candidates"])!=1
            or obs["text_clues_not_security_type_proof"]["REIT_LANGUAGE"] is not True):
            raise A5tSourceError("Missing REIT issuer and same-row title/venue hints")
        _raw_verify(folder,x["primary_raw_filename"],obs["source_sha256"],obs["source_bytes"])
        row=_exact_row(same["row_candidates"][0],sym)
        if not re.search(r"New York Stock Exchange",row,re.I):
            raise A5tSourceError("REIT SEC title row must show XNYS venue")
        p=review(Evidence(ticker=sym,mic="XNYS",issuer_type="REIT",
                          listed_class="COMMON_STOCK",
                          issuer_status_verified=False,listed_class_verified=False))
        records.append({
            "ticker":sym,"cik_issuer_candidate":x["cik"],"category":"REIT_ISSUER_CANDIDATE",
            "financial_filing":filing,"sec_original_source_sha256":obs["source_sha256"],
            "sec_primary_retrieved_at":x["primary_retrieved_at"],
            "SEC_section12b_ticker_class_venue_candidate":row,
            "issuer_legal_status_evidence_tier":"SEC_REIT_TEXT_CANDIDATE_NOT_INDEPENDENT_LEGAL_VERIFICATION",
            "current_REIT_issuer_status_verified":False,
            "reason_not_finalized":["REIT_LEGAL_STATUS_NOT_INDEPENDENTLY_VERIFIED",
                                    "NYSE_ORIGINAL_LISTED_SECURITY_MASTER_MISSING",
                                    "AUTHORIZED_REVIEWER_NOT_APPROVED"],
            "policy_suggestion":p["classification_proposal"],
            "approval_status":"HOLD_SOURCE_EVIDENCE_AND_REVIEW",
            "permanent_security_id":None,
            "independent_security_id_verified":False,
            "listed_class_independently_approved":False,
            "source_known_at_as_of_verified":False,
            "production_eligible":False,
        })
    if {r["ticker"] for r in records}!=REIT_TICKERS:
        raise A5tSourceError("Three original REIT issuer symbols missing")
    return records


def compile_evidence(a5e:Path,a5k:Path)->dict:
    b=_bdc_candidates(_source(a5e,"a5e-financial-evidence.json",A5E_SHA),a5e)
    r=_reit_candidates(_source(a5k,"a5k-sec-pilot-evidence.json",A5K_SHA),a5k)
    records=b+r
    if len(b)!=16 or len(r)!=3 or len({x["ticker"] for x in records})!=19:
        raise A5tSourceError("Missing/ambiguous frozen BDC or REIT security class records")
    return {
        "status":"US_V2_REIT_BDC_INDEPENDENT_VERIFICATION_QUEUE_REVIEW_ONLY",
        "version":VERSION,"as_of":SEC_AS_OF,
        "source_sha256":{"A5e_bdc_election_financial":A5E_SHA,
                          "A5k_REIT_SEC_primary":A5K_SHA},
        "us_v2_production_namespace":"labyrinth-momentum-us-v2",
        "independent_US_production_configured":False,
        "independent_US_production_deployed":False,
        "US_publisher_gate_connected":False,
        "issuer_legal_status_candidate_count":19,
        "original_SEC_common_ticker_venue_row_count":19,
        "BDC_election_issuer_candidates":len(b),
        "REIT_issuer_candidates":len(r),
        "independent_current_issuer_status_approved":0,
        "independent_listed_security_id_approved":0,
        "human_scope_security_review_approved":0,
        "source_PIT_known_at_approved":0,
        "final_security_classification_decisions_closed":0,
        "review_queue_open":19,
        "production_approvals":0,
        "candidate_ALLOW":0,
        "production_eligible":False,
        "records":records,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a5e",required=True,type=Path)
    p.add_argument("--a5k",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    try:
        obj=compile_evidence(args.a5e,args.a5k)
        args.output.mkdir(parents=True,exist_ok=False)
        (args.output/"a5t-reit-bdc-issuer-class-review.json").write_text(
            json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({k:v for k,v in obj.items() if k!="records"},indent=2))
        return 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(f"A5T_BLOCKED: {type(exc).__name__}: {exc}")
        return 2

if __name__=="__main__":
    raise SystemExit(main())
