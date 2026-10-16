"""A5u: SEC original post-financial 8-K and election-history evidence replay.

For 16 BDC candidate issuers, validate frozen A5e/A5d receipts,
17 N-54A original source documents, and capture 40 primary 8-K forms.
Inspect event subjects as *review signals*. Neither absence of a
withdrawal in captured metadata nor a keyword scan establishes current
BDC legal status or corporate transaction completion.

US V2 only; no publication, pricing, tradability, or production wiring.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import time
from urllib.request import Request, build_opener

from .a5f_corporate_events import _plain_text
from .sec_capture import NoRedirect, validate_user_agent

A5E_SHA="a58638402bbdc59b7afb2de3dfe439c6672cc0a1ede40fb59bd8a283aea7612f"
A5D_SHA="b1a5b4ecdca3572ecd84baef85b5e9ec3ae47c422ec39ad6491c7cf89a2d11da"
VERSION="a5u-post-financial-40-8k-review-only-v1"
CUTOFF=date(2026,10,14)
EXPECTED_ISSUERS=16
EXPECTED_ELECTIONS=17
EXPECTED_EVENTS=40
MAX_PRIMARY=28*1024*1024
ITEM=re.compile(r"\bItems?\s+([1-9]\.[0-9]{2})\b",re.I)
KEYWORDS={
    "CORPORATE_ACTION_WORDING":r"\b(?:merger|merging|business combination|consolidation|reorganization|acquisition|sale of substantially all|share exchange)\b",
    "LISTING_OR_TICKER_WORDING":r"\b(?:delisting|delisted|nasdaq listing|NYSE listing|change of ticker|stock split|reverse split|exchange listing)\b",
    "BDC_ELECTION_WORDING":r"\b(?:N-54C|withdrawal of election|business development company|investment company act of 1940)\b",
    "SECURITY_ISSUANCE_WORDING":r"\b(?:issuance|redemption|tender offer|conversion|preferred stock|warrants?|common stock)\b",
}
URL=re.compile(r"https://www\.sec\.gov/Archives/edgar/data/([1-9][0-9]*)/([0-9]{18})/([A-Za-z0-9._/-]+)")


class A5uEvidenceError(ValueError):
    pass


def read_pinned(root:Path,name:str,sha:str)->dict:
    raw=(root/name).read_bytes()
    if sha256(raw).hexdigest()!=sha:
        raise A5uEvidenceError(f"Original SEC source receipt SHA256 mismatch: {name}")
    x=json.loads(raw)
    if not isinstance(x,dict):
        raise A5uEvidenceError("Original source report must be JSON object")
    return x


def _verify_elections(d:dict,root:Path)->dict:
    if (d.get("status")!="DOCUMENT_EVIDENCE_CAPTURED_REVIEW_ONLY"
        or d.get("original_cohort_issuers")!=EXPECTED_ISSUERS
        or d.get("verified_n54a_primary_documents")!=EXPECTED_ELECTIONS
        or d.get("document_fetch_failures")!=0
        or d.get("production_approved")!=0
        or d.get("not_proof_of_no_n54c") is not True
        or len(d.get("findings",[]))!=EXPECTED_ISSUERS):
        raise A5uEvidenceError("Original N-54A cohort not verified/fail closed")
    people={}
    count=0
    for r in d["findings"]:
        cik=r["cik"]
        if (cik in people or not re.fullmatch(r"[0-9]{10}",cik)
            or r["current_bdc_status"]!="UNDETERMINED"
            or r["withdrawal_absence_proven"] is not False
            or r["production_eligible"] is not False):
            raise A5uEvidenceError("BDC election report contains unsupported current status")
        elections=r["election_filings"]
        if not elections:raise A5uEvidenceError("Original N-54A election primary missing")
        for e in elections:
            if (e["status"]!="FORM_TEXT_SIGNAL_VERIFIED"
                or e["n54a_text_consistent"] is not True
                or date.fromisoformat(e["filing_date"])>CUTOFF):
                raise A5uEvidenceError("Invalid original N-54A primary content")
            name=f"CIK{cik}-{e['accession']}-{e['sha256']}.html"
            content=(root/name).read_bytes()
            if sha256(content).hexdigest()!=e["sha256"] or len(content)!=e["document_bytes"]:
                raise A5uEvidenceError("Original N-54A SHA256/byte count mismatch")
            count+=1
        people[cik]=r
    if count!=EXPECTED_ELECTIONS:
        raise A5uEvidenceError("Expected precisely 17 original N-54A source documents")
    return people


def _verify_a5e(e:dict,elections:dict)->list[dict]:
    if (e.get("status")!="SOURCE_CAPTURED_REVIEW_ONLY"
        or e.get("issuer_total")!=EXPECTED_ISSUERS
        or e.get("financial_documents_captured")!=EXPECTED_ISSUERS
        or e.get("production_eligible") is not False
        or e.get("bdc_issuer_status_approvals")!=0
        or e.get("production_approvals")!=0
        or len(e.get("findings",[]))!=EXPECTED_ISSUERS):
        raise A5uEvidenceError("A5e frozen financial filing report incomplete")
    seen=set()
    total=0
    records=[]
    eventkeys=set()
    for x in e["findings"]:
        cik=x["cik"]
        if cik in seen or cik not in elections:
            raise A5uEvidenceError("SEC issuer CIK not in original election cohort")
        seen.add(cik)
        orig=elections[cik]
        if (x["original_election_accessions"] != [v["accession"] for v in orig["election_filings"]]
            or x["production_eligible"] is not False
            or x["n54c_absence_proven"] is not False
            or x["post_financial_events_checked"] is not False
            or x["issuer_bdc_status"]!="REVIEW_REQUIRED"
            or x["latest_financial"]["filing_date"]>CUTOFF.isoformat()
            or x["n54c_metadata_seen"]!=[]):
            raise A5uEvidenceError("BDC issuer status/event evidence has changed")
        latest=date.fromisoformat(x["latest_financial"]["filing_date"])
        for ev in x["post_financial_8k_metadata"]:
            if ev.get("form") not in ("8-K","8-K/A"):
                raise A5uEvidenceError("Non-8K SEC event in 8-K source queue")
            dated=date.fromisoformat(ev["filing_date"])
            if dated<latest or dated>CUTOFF:
                raise A5uEvidenceError("8-K event date outside original review window")
            url=ev.get("document_url")
            parsed=URL.fullmatch(url) if isinstance(url,str) else None
            if (not parsed or int(parsed.group(1))!=int(cik)
                or parsed.group(2)!=ev["accession"].replace("-","")
                or any(seg in (".","..") for seg in parsed.group(3).split("/"))):
                raise A5uEvidenceError("8-K official Archives URL/accession/issuer mismatch")
            key=(cik,ev["accession"])
            if key in eventkeys:raise A5uEvidenceError("Repeated SEC event source accession")
            eventkeys.add(key)
            total+=1
        records.append(x)
    if total!=EXPECTED_EVENTS or len(seen)!=EXPECTED_ISSUERS:
        raise A5uEvidenceError("SEC 40-event/16-issuer source inventory changed")
    return records


def fetch_8k(url:str,agent:str)->bytes:
    if not URL.fullmatch(url):
        raise A5uEvidenceError("Only SEC Archives official 8-K document URL allowed")
    req=Request(url,headers={"User-Agent":validate_user_agent(agent),
        "Accept":"text/html,application/xml,text/plain",
        "Accept-Encoding":"identity"})
    with build_opener(NoRedirect()).open(req,timeout=55) as response:
        if response.geturl()!=url:
            raise A5uEvidenceError("SEC event source redirected")
        body=response.read(MAX_PRIMARY+1)
    if not 250<=len(body)<=MAX_PRIMARY:
        raise A5uEvidenceError("SEC 8-K source empty/oversized")
    if b"access denied" in body[:1000].lower() or b"request rate threshold exceeded" in body[:1000].lower():
        raise A5uEvidenceError("SEC blocked source; no cache substitution")
    return body


def inspect_8k(raw:bytes)->dict:
    if not isinstance(raw,bytes) or not 250<=len(raw)<=MAX_PRIMARY:
        raise A5uEvidenceError("Invalid SEC primary event bytes")
    body=_plain_text(raw)
    if len(body)<200 or not re.search(r"\b(?:FORM\s+8[\s-]?K|CURRENT REPORT)\b",body[:100000],re.I):
        raise A5uEvidenceError("SEC event primary is not recognizably 8-K")
    item_codes=sorted(set(ITEM.findall(body[:400000])))
    signals={}
    contexts={}
    for category,pattern in KEYWORDS.items():
        matches=list(re.finditer(pattern,body,re.I))[:3]
        signals[category]=bool(matches)
        contexts[category]=[body[max(0,m.start()-70):m.end()+140].strip()[:240] for m in matches]
    priority=(
        "CORPORATE_ACTION_OR_LISTING_HUMAN_REVIEW"
        if signals["CORPORATE_ACTION_WORDING"] or signals["LISTING_OR_TICKER_WORDING"]
        else "OTHER_8K_CONTENT_HUMAN_REVIEW"
    )
    return {
        "SEC_form_content_8k_recognized":True,
        "SEC_item_numbers_observed":item_codes,
        "keyword_signals_not_legal_findings":signals,
        "bounded_keyword_contexts_for_manual_review":contexts,
        "triage_priority":priority,
        "all_exhibits_reviewed":False,
        "transaction_closed_or_BDC_current_status_proven":False,
        "independent_security_ID_verified":False,
        "human_event_review_approved":False,
    }


def run(a5e:Path,a5d:Path,out:Path,agent:str,*,fetcher=fetch_8k,pause=time.sleep,
        clock=lambda:datetime.now(timezone.utc))->dict:
    validate_user_agent(agent)
    election=_verify_elections(read_pinned(a5d,"a5d-election-evidence.json",A5D_SHA),a5d)
    companies=_verify_a5e(read_pinned(a5e,"a5e-financial-evidence.json",A5E_SHA),election)
    out.mkdir(parents=True,exist_ok=False)
    results=[]
    calls=0
    for x in companies:
        sym=x["tickers"][0]
        src=election[x["cik"]]
        events=[]
        for metadata in x["post_financial_8k_metadata"]:
            item={"form":metadata["form"],"filing_date":metadata["filing_date"],
                  "accession":metadata["accession"],"document_url":metadata["document_url"],
                  "source_status":"NOT_YET_VERIFIED"}
            if calls:pause(.85)
            calls+=1
            try:
                body=fetcher(metadata["document_url"],agent)
                evidence=inspect_8k(body)
                now=clock()
                if now.tzinfo is None or now.utcoffset() is None:
                    raise A5uEvidenceError("Timezone-aware original source retrieval mandatory")
                digest=sha256(body).hexdigest()
                filename=f"{sym}-{metadata['accession']}-{digest}.html"
                (out/filename).write_bytes(body)
                item.update(source_status="ORIGINAL_SEC_8K_CAPTURED_REVIEW_ONLY",
                            original_sha256=digest,original_bytes=len(body),
                            original_source_file=filename,retrieved_at=now.isoformat(),
                            **evidence)
            except (ValueError,OSError,KeyError,TypeError,TimeoutError) as err:
                item["source_error"]=f"{type(err).__name__}: {err}"[:230]
            events.append(item)
        results.append({
            "ticker":sym,"cik":x["cik"],"issuer_name":x["issuer_name"],
            "latest_financial":x["latest_financial"],
            "N54A_original_elections":list(src["election_filings"]),
            "N54C_forms_in_2026_10_15_submission_recent":len(x["n54c_metadata_seen"]),
            "N54C_absence_proven":False,
            "BDC_current_legal_status_verified":False,
            "N54A_filing_does_not_prove_current_status":True,
            "SEC_historical_files_pending":x["historical_files_not_downloaded"],
            "post_financial_events":events,
            "all_event_exhibits_reviewed":False,
            "LIEN_REFI_merger_hold":sym=="LIEN",
            "reviewer_approval":False,"security_id_approved":False,
            "production_eligible":False,
        })
    verified=sum(e["source_status"]=="ORIGINAL_SEC_8K_CAPTURED_REVIEW_ONLY"
                 for x in results for e in x["post_financial_events"])
    signal_counts=Counter()
    for x in results:
        for e in x["post_financial_events"]:
            if e["source_status"]=="ORIGINAL_SEC_8K_CAPTURED_REVIEW_ONLY":
                signal_counts[e["triage_priority"]]+=1
    report={
        "status":"OFFICIAL_SEC_EVENT_SOURCES_CAPTURED_REVIEW_ONLY" if verified==40 else "SEC_EVENT_SOURCES_PARTIAL_BLOCKED",
        "version":VERSION,"as_of":CUTOFF.isoformat(),
        "a5e_source_sha256":A5E_SHA,"a5d_source_sha256":A5D_SHA,
        "official_BDC_candidate_issuers":EXPECTED_ISSUERS,
        "N54A_original_primary_files_reverified":EXPECTED_ELECTIONS,
        "N54C_metadata_in_frozen_recent":0,
        "N54C_current_absence_proven":False,
        "post_financial_SEC_8K_metadata_expected":40,
        "original_8K_primary_documents_verified":verified,
        "post_financial_event_primary_sources_still_missing":40-verified,
        "SEC_8K_primary_keyword_priority_counts":dict(signal_counts),
        "SEC_8K_exhibit_document_reviews_completed":0,
        "independent_current_BDC_status_approvals":0,
        "independent_reviewer_approvals":0,
        "independent_listed_security_id_approvals":0,
        "LIEN_REFI_corporate_event_hold":True,
        "candidate_ALLOW":0,"US_production_ready":False,
        "production_eligible":False,"issuers":results,
    }
    (out/"a5u-sec-40-event-review.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="issuers"},indent=2))
    return report


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a5e",type=Path,required=True)
    p.add_argument("--a5d",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        report=run(a.a5e,a.a5d,a.output,os.environ.get("SEC_USER_AGENT",""))
        return 0 if report["original_8K_primary_documents_verified"]==40 else 2
    except (ValueError,OSError,TypeError,KeyError) as exc:
        print("A5U_DENY_INCOMPLETE",type(exc).__name__,str(exc))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
