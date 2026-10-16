"""A5s evaluate original SEC N-CEN issuer type + Part D.1 securities.

All "classification_proposal" entries are OFFLINE review suggestions, NOT
source A4 decision changes. Explicit BDC eligibility remains open; a closed
end management registration label alone does not override BDC policy.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from .a5f_corporate_events import _plain_text
from .a5o_sec_cfi_exceptions import CI,TVC,TARGET

RECEIPTS_SHA="c4649f4502e5d6ca81267ce1e3bd8c878c396bff655b9f57c5a5d5e6c312e149"
VERSION="a5s-original-sec-fund-partD-review-v1"
START=re.compile(r"N-CEN\s*:\s*Part D:\s*Additional Questions",re.I)
RECORD=re.compile(r"Security Issued by Registrants Record:\s*([0-9]+)",re.I)
END=re.compile(r"\bItem D\.2\b",re.I)
FORM_N2=re.compile(r"Form N-2 Filer\s*\(Closed-End Investment Company\)",re.I)
SHARE_CLASS=re.compile(r"Type of security\s+(.*?)\s+Title of class",re.I|re.S)
EXCHANGE=re.compile(r"Exchange where listed\s+(.*?)\s+Ticker symbol\s+(\S+)",re.I|re.S)
NYSE=re.compile(r"^NEW YORK STOCK EXCHANGE(?:, INC\.?)?$",re.I)
PARRS=re.compile(r"Putable Automatic Rate Reset Securities.{0,70}PARRS.{0,120}exchange symbols.{0,35}\bTVC\b.{0,35}\bTVE\b",re.I|re.S)
BOND=re.compile(r"TVA Bonds are traded in the public bond markets",re.I)


class PrimaryReviewError(ValueError):
    pass


def parse_ncen(raw:bytes,*,ticker:str)->dict:
    if ticker not in CI or not 200<len(raw)<=22*1024*1024:
        raise PrimaryReviewError("SEC fund primary data invalid")
    text=_plain_text(raw)
    if "FORM N-CEN" not in text[:5000].upper():
        raise PrimaryReviewError("Source not SEC N-CEN")
    header=text[:5000]
    n2=bool(FORM_N2.search(header))
    start=START.search(text)
    if not start:raise PrimaryReviewError("SEC N-CEN Part D absent")
    remainder=text[start.end():]
    end=END.search(remainder)
    if not end:raise PrimaryReviewError("SEC N-CEN Item D.2 end absent")
    part=remainder[:end.start()]
    spans=list(RECORD.finditer(part))
    if not spans:raise PrimaryReviewError("SEC N-CEN no Part D.1 issuer securities")
    securities=[]
    for i,m in enumerate(spans):
        chunk=part[m.end():spans[i+1].start() if i+1<len(spans) else len(part)]
        cls=SHARE_CLASS.search(chunk)
        market=EXCHANGE.search(chunk)
        if not cls or not market:
            raise PrimaryReviewError("Part D securities record incomplete")
        kind=" ".join(cls.group(1).split())
        exch=" ".join(market.group(1).split())
        symbol=market.group(2).strip()
        securities.append({"SEC_record":int(m.group(1)),
                           "SEC_type_of_security":kind[:80],
                           "SEC_exchange_reported":exch[:100],
                           "SEC_ticker_reported":symbol[:35]})
    matched=[r for r in securities
             if r["SEC_ticker_reported"]==ticker and r["SEC_type_of_security"].casefold()=="common stock"]
    matched_nyse=[r for r in matched if NYSE.fullmatch(r["SEC_exchange_reported"])]
    if len(matched_nyse)>1:
        raise PrimaryReviewError("Multiple SEC N-CEN same ticker/NYSE common rows")
    if not n2:
        tier="FILER_N2_CLOSED_END_NOT_CONFIRMED"
    elif len(matched_nyse)==1:
        tier="SEC_NCEN_N2_EXACT_NYSE_COMMON_TICKER"
    elif matched:
        tier="SEC_NCEN_N2_TICKER_MATCH_VENUE_DISCREPANCY"
    else:
        tier="SEC_NCEN_N2_ISSUER_ONLY_TICKER_DISCREPANCY"
    return {
        "SEC_NCEN_filer_Form_N2_closed_end":n2,
        "SEC_D1_reported_securities":securities,
        "SEC_exact_NYSE_common_ticker_row":len(matched_nyse)==1,
        "evidence_tier":tier,
        "registered_fund_CEF_policy_candidate":n2,
        "BDC_election_or_absence_independently_proven":False,
        "final_issuer_legal_type_approved":False,
        "security_id_verified":False,
        "production_eligible":False,
    }


def parse_tvc(raw:bytes)->dict:
    text=_plain_text(raw)
    if "FORM 10-K" not in text[:15000].upper():
        raise PrimaryReviewError("TVC original not SEC Form 10-K")
    bond=bool(BOND.search(text))
    parrs=bool(PARRS.search(text))
    return {
        "TVC_issuer_SEC_10K_PARRS_NYSE_symbol_evidence":parrs,
        "TVC_issuer_bond_market_language":bond,
        "security_type_candidate":"DEBT_PARRS_NOT_COMMON_SHARE" if bond and parrs else "UNRESOLVED",
        "type_decision_final_approved":False,
        "security_id_verified":False,"production_eligible":False,
    }


def summarize(src:Path)->dict:
    raw=(src/"a5s-original-primary-receipts.json").read_bytes()
    if sha256(raw).hexdigest()!=RECEIPTS_SHA:
        raise PrimaryReviewError("Original SEC 21-document receipt SHA mismatch")
    receipt=json.loads(raw)
    if (receipt.get("status")!="SEC_ORIGINAL_21_COMPLETE_REVIEW_ONLY"
            or receipt.get("source_bytes_verified")!=21
            or len(receipt.get("documents",[]))!=21
            or {r["ticker"] for r in receipt["documents"]}!=set(TARGET)
            or receipt.get("production_eligible") is not False):
        raise PrimaryReviewError("Original SEC source coverage incomplete")
    evaluated=[]
    for x in receipt["documents"]:
        if x["status"]!="PRIMARY_BYTES_CAPTURED_REVIEW_ONLY" or x["production_eligible"] is not False:
            raise PrimaryReviewError("Original SEC primary not verified")
        rawfile=(src/x["raw_filename"]).read_bytes()
        if sha256(rawfile).hexdigest()!=x["raw_sha256"] or len(rawfile)!=x["raw_bytes"]:
            raise PrimaryReviewError("Original SEC primary checksum or size mismatch")
        if x["filing"]["filing_date"]>"2026-10-14":
            raise PrimaryReviewError("Future SEC source rejected")
        result=parse_tvc(rawfile) if x["ticker"]==TVC else parse_ncen(rawfile,ticker=x["ticker"])
        tier=("SEC_TVC_10K_EXCHANGE_TRADED_DEBT_CANDIDATE"
              if x["ticker"]==TVC and result["security_type_candidate"]=="DEBT_PARRS_NOT_COMMON_SHARE"
              else result.get("evidence_tier"))
        evaluated.append({
            "ticker":x["ticker"],"source_filing":x["filing"],
            "source_sha256":x["raw_sha256"],
            "retrieved_at":x["retrieved_at"],
            "issuer_CIK_candidate_not_security_id":x["cik"],
            "source_evidence_tier":tier,
            "original_A4_decision":"INCLUDE",
            "policy_proposal":"EXCLUDE_CEF_IF_NON_BDC_STATUS_VALIDATED" if x["ticker"]!=TVC else
                 "EXCLUDE_DEBT_AFTER_INDEPENDENT_SECURITY_MASTER_REVIEW",
            "policy_satisfied_for_production":False,
            "security_id_verified":False,
            "BDC_status_verified":False,
            "production_eligible":False,
            "observations":result,
        })
    cnt={}
    for x in evaluated:
        tier=x["source_evidence_tier"]
        cnt[tier]=cnt.get(tier,0)+1
    if len(evaluated)!=21:
        raise PrimaryReviewError("21 SEC originals required")
    return {
        "status":"SEC_PRIMARY_CLASSIFICATION_EVIDENCE_REVIEW_ONLY",
        "version":VERSION,"SEC_as_of":"2026-10-14",
        "original_receipts_sha256":RECEIPTS_SHA,
        "SEC_primary_sources_verified":21,
        "issuer_closed_end_form_N2_evidence_count":sum(
            bool(x["observations"].get("SEC_NCEN_filer_Form_N2_closed_end")) for x in evaluated),
        "SEC_exact_NYSE_common_class_candidates":sum(
            bool(x["observations"].get("SEC_exact_NYSE_common_ticker_row")) for x in evaluated),
        "evidence_tiers":cnt,"legal_scope_decisions_finalized":0,
        "source_A4_decisions_modified":0,"listed_security_id_approvals":0,
        "production_approvals":0,"production_eligible":False,
        "rows":evaluated,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sec-originals",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    try:
        s=summarize(args.sec_originals)
        args.output.mkdir(parents=True,exist_ok=False)
        (args.output/"a5s-sec-classification-proposals.json").write_text(
            json.dumps(s,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
        print(json.dumps({k:v for k,v in s.items() if k!="rows"},indent=2))
        return 0
    except (ValueError,TypeError,OSError,KeyError) as e:
        print("A5S_REVIEW_FAIL_CLOSED",e)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
