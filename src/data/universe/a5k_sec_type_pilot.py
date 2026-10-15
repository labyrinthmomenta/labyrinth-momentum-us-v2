"""A5k evidence pilot: official SEC issuer filing metadata and dated document bytes.

Only 9 representative issuers chosen *from frozen A5j review rows*. The
pilot suggests questions for human/security-master review; it CANNOT
classify a security or authorize any addition to the US universe.
"""
from __future__ import annotations

import argparse
from datetime import date,datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import time
from urllib.request import Request,build_opener

from .a5f_corporate_events import _plain_text
from .a5g_exhibit_merger_evidence import validate_archive_url
from .a5h_remaining_exhibits import parse_submissions_timeline
from .sec_capture import NoRedirect,validate_user_agent
from .a5k_full_release import _frozen_json,A5J_TRIAGE_SHA

AS_OF=date(2026,10,14)
SEC_SUBMISSIONS="https://data.sec.gov/submissions/"
MAX_SUBMISSION=12*1024*1024
MAX_PRIMARY=64*1024*1024
DELAY=0.8

# Frozen A5j symbols, SEC CIK candidates and investigation categories.
# No SEC CIK is treated as a security_id.
PILOT={
    "AACI":("0002092897","SPAC_OR_BLANK_CHECK"),
    "ADAC":("0002083002","SPAC_OR_BLANK_CHECK"),
    "ASPC":("0001890361","SPAC_OR_BLANK_CHECK"),
    "ARR":("0001428205","REIT_VS_FUND"),
    "RHP":("0001040829","REIT_VS_FUND"),
    "WPC":("0001025378","REIT_VS_FUND"),
    "CCD":("0001602584","CLOSED_END_FUND_VS_BDC"),
    "CGO":("0001285650","CLOSED_END_FUND_VS_BDC"),
    "CSQ":("0001275214","CLOSED_END_FUND_VS_BDC"),
}
FORM_ALLOW={
    "SPAC_OR_BLANK_CHECK":{"10-K","10-Q","S-1","S-1/A","8-K"},
    "REIT_VS_FUND":{"10-K","10-Q"},
    "CLOSED_END_FUND_VS_BDC":{"N-CSR","N-CSRS","N-2","N-2/A","N-CEN","10-K","10-Q"},
}


class OfficialTypeError(ValueError):
    pass


def _submissions_url(cik:str)->str:
    if cik not in {val[0] for val in PILOT.values()}:
        raise OfficialTypeError("CIK not in frozen pilot")
    return SEC_SUBMISSIONS+f"CIK{cik}.json"


def parse_submission(raw:bytes,*,cik:str,category:str,at:datetime)->dict:
    if at.tzinfo is None or at.utcoffset() is None:
        raise OfficialTypeError("SEC metadata retrieval timestamp naive")
    if not 25<=len(raw)<=MAX_SUBMISSION:
        raise OfficialTypeError("Invalid/oversize SEC submissions bytes")
    try:
        x=json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError,ValueError) as exc:
        raise OfficialTypeError("SEC submissions source not valid JSON") from exc
    sec_cik=x.get("cik") if isinstance(x,dict) else None
    if (type(sec_cik) not in (int,str)
            or not str(sec_cik).isascii() or not str(sec_cik).isdecimal()
            or f"{int(sec_cik):010d}"!=cik):
        raise OfficialTypeError("SEC issuer CIK mismatch")
    forms=x.get("filings")
    if not isinstance(forms,dict) or not isinstance(forms.get("recent"),dict):
        raise OfficialTypeError("SEC filings.recent absent")
    data=forms["recent"]
    cols=("form","filingDate","accessionNumber","primaryDocument")
    if any(not isinstance(data.get(c),list) for c in cols):
        raise OfficialTypeError("SEC recent filing columns invalid")
    if len({len(data[c]) for c in cols})!=1:
        raise OfficialTypeError("SEC recent filing columns misaligned")
    if not isinstance(forms.get("files"),list):
        raise OfficialTypeError("SEC older-history inventory unavailable")
    choices=[]
    for index in range(len(data["form"])):
        form,day,accession,doc=(data[k][index] for k in cols)
        if not isinstance(form,str) or not isinstance(day,str):
            raise OfficialTypeError("SEC filing form/date invalid")
        try:
            d=date.fromisoformat(day)
        except ValueError as exc:
            raise OfficialTypeError("SEC invalid filing date") from exc
        if d>AS_OF or form not in FORM_ALLOW[category]:
            continue
        if not isinstance(accession,str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}",accession):
            raise OfficialTypeError("SEC accession malformed")
        if not isinstance(doc,str) or not re.fullmatch(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*",doc):
            raise OfficialTypeError("SEC primary document path malformed")
        if any(part in (".","..") for part in doc.split("/")):
            raise OfficialTypeError("SEC primary document traversal")
        url=(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
             f"{accession.replace('-','')}/{doc}")
        validate_archive_url(url,cik=cik,accession=accession)
        choices.append({"form":form,"filing_date":day,
                        "accession":accession,"document_url":url})
    choices.sort(key=lambda y:(y["filing_date"],y["accession"]),reverse=True)
    return {
        "cik":cik,"name":x.get("name"),
        "metadata_sha256":sha256(raw).hexdigest(),
        "metadata_retrieved_at":at.isoformat(),
        "recent_forms_checked":len(data["form"]),
        "older_history_chunk_count_not_downloaded":len(forms["files"]),
        "candidate_filing":choices[0] if choices else None,
        "filing_candidates_count":len(choices),
        "candidate_document_class_approved":False,
    }


def inspect_primary(raw:bytes, *,category:str,ticker:str)->dict:
    if not isinstance(raw,bytes) or not 200<=len(raw)<=MAX_PRIMARY:
        raise OfficialTypeError("SEC primary filing empty or oversized")
    body=_plain_text(raw)
    if len(body)<300:
        raise OfficialTypeError("SEC primary document not meaningful")
    beginning=body[:60000].casefold()
    if "access denied" in beginning[:500] or "request rate threshold exceeded" in beginning[:500]:
        raise OfficialTypeError("SEC blocked document")
    patterns={
        "COMMON_STOCK_LANGUAGE":r"\bcommon (?:stock|shares?)\b",
        "PREFERRED_STOCK_LANGUAGE":r"\bpreferred (?:stock|shares?)\b",
        "UNIT_OR_WARRANT_LANGUAGE":r"\b(?:warrants?|units?)\b",
        "BLANK_CHECK_LANGUAGE":r"\b(?:blank check company|special purpose acquisition company)\b",
        "BDC_LANGUAGE":r"\bbusiness development company\b",
        "REIT_LANGUAGE":r"\breal estate investment trust\b",
        "CLOSED_END_FUND_LANGUAGE":r"\bclosed.end (?:management )?(?:investment company|fund)\b",
        "SECURITY_CLASS_TITLE":r"\b(?:title of each class|class of securities registered)\b",
    }
    clues={k:bool(re.search(pattern,beginning,re.I)) for k,pattern in patterns.items()}
    return {
        "source_sha256":sha256(raw).hexdigest(),
        "source_bytes":len(raw),
        "issuer_category_review":category,"ticker_candidate":ticker,
        "text_clues_not_security_type_proof":clues,
        "title_class_security_id_verified":False,
        "issuer_CIK_is_not_listed_security_id":True,
        "business_entity_legal_status_approved":False,
        "production_eligible":False,
    }


def fetch_sec(url:str,agent:str,*,limit:int)->bytes:
    if url.startswith(SEC_SUBMISSIONS):
        tail=url[len(SEC_SUBMISSIONS):]
        if not re.fullmatch(r"CIK[0-9]{10}\.json",tail) or tail[3:13] not in {c for c,_ in PILOT.values()}:
            raise OfficialTypeError("SEC submission URL not in permit list")
    else:
        m=re.fullmatch(r"https://www\.sec\.gov/Archives/edgar/data/(\d+)/(\d{18})/([A-Za-z0-9._/-]+)",url)
        if not m or not any(int(m[1])==int(c) for c,_ in PILOT.values()):
            raise OfficialTypeError("SEC primary URL not allow-listed")
        if any(part in ("..",".") for part in m[3].split("/")):
            raise OfficialTypeError("Path traversal attempt")
    req=Request(url,headers={"User-Agent":validate_user_agent(agent),
                             "Accept":"application/json,text/html,text/plain",
                             "Accept-Encoding":"identity"})
    with build_opener(NoRedirect()).open(req,timeout=45) as resp:
        if resp.geturl()!=url:
            raise OfficialTypeError("SEC redirect not trusted")
        raw=resp.read(limit+1)
    if len(raw)>limit:
        raise OfficialTypeError("SEC document too large")
    return raw


def run_pilot(a5j:Path,out:Path,*,agent:str,fetcher=fetch_sec,
              clock=lambda:datetime.now(timezone.utc),pause=time.sleep)->dict:
    validate_user_agent(agent)
    j=_frozen_json(a5j/"a5j-type-evidence-triage.json",A5J_TRIAGE_SHA)
    if (j.get("status")!="CLASSIFICATION_EVIDENCE_TRIAGE_REVIEW_ONLY"
            or j.get("production_eligible") is not False
            or j.get("total_review_records")!=1010
            or len(j.get("triage_rows",[]))!=1010):
        raise OfficialTypeError("Unverified A5j source")
    bysymbol={r["symbol"]:r for r in j["triage_rows"] if r["symbol"] in PILOT}
    if len(bysymbol)!=len(PILOT):
        raise OfficialTypeError("All nine original Nasdaq/SEC pilot symbols required")
    out.mkdir(parents=True,exist_ok=False)
    records=[]
    calls=0
    for ticker,(cik,category) in PILOT.items():
        previous=bysymbol[ticker]
        if (previous["issuer_cik_candidate"]!=cik
                or previous["a5i_decision"]!="REVIEW_REQUIRED"
                or previous.get("release_hold") is not True
                or previous["production_eligible"] is not False):
            raise OfficialTypeError("SEC issuer pilot CIK or review hold changed")
        x={"ticker":ticker,"cik":cik,"category_for_manual_review":category,
           "status":"SEC_SOURCES_NOT_YET_VALIDATED",
           "production_eligible":False,
           "source_security_identity_approved":False,
           "issuer_legal_type_approved":False,
           "as_of":AS_OF.isoformat(),
           "primary_source":None,
           "error":None}
        try:
            if calls:pause(DELAY)
            calls+=1
            source_url=_submissions_url(cik)
            meta_raw=fetcher(source_url,agent,limit=MAX_SUBMISSION)
            parsed=parse_submission(meta_raw,cik=cik,category=category,at=clock())
            name=f"{ticker}-submissions-{parsed['metadata_sha256']}.json"
            (out/name).write_bytes(meta_raw)
            x.update(status="SEC_METADATA_CAPTURED_REVIEW_ONLY",
                     metadata=parsed,metadata_raw_filename=name,metadata_source=source_url)
            chosen=parsed["candidate_filing"]
            if chosen:
                pause(DELAY)
                calls+=1
                raw=fetcher(chosen["document_url"],agent,limit=MAX_PRIMARY)
                snapshot=inspect_primary(raw,category=category,ticker=ticker)
                name=(f"{ticker}-{chosen['accession']}-"
                      f"{snapshot['source_sha256']}.source")
                (out/name).write_bytes(raw)
                x.update(status="SEC_ISSUER_FILING_CAPTURED_REVIEW_ONLY",
                         primary_source=chosen,primary_observation=snapshot,
                         primary_retrieved_at=clock().isoformat(),
                         primary_raw_filename=name)
            else:
                x.update(status="NO_ELIGIBLE_RECENT_FILING_REVIEW_REQUIRED")
        except (OSError,ValueError,TypeError,TimeoutError) as exc:
            x["error"]=f"{type(exc).__name__}: {exc}"[:230]
            x["status"]="SOURCE_PARTIAL_OR_UNVERIFIED"
        records.append(x)
    full=sum(x["status"]=="SEC_ISSUER_FILING_CAPTURED_REVIEW_ONLY" for x in records)
    report={
        "status":"OFFICIAL_SEC_PILOT_REVIEW_ONLY" if full==len(PILOT) else
                 "OFFICIAL_SEC_PILOT_PARTIAL_REVIEW_ONLY",
        "as_of":AS_OF.isoformat(),"pilot_size":len(PILOT),
        "official_issuer_submissions_verified":sum(
            bool(x.get("metadata")) for x in records),
        "official_primary_filings_verified":full,
        "missing_recent_form_or_source":len(records)-full,
        "categories":dict(sorted({category:sum(
            x["category_for_manual_review"]==category for x in records)
            for category in FORM_ALLOW}.items())),
        "sec_issuer_legal_status_approved":0,"listed_security_id_approved":0,
        "instrument_type_decisions_completed":0,
        "as_of_historic_known_at_proven":False,
        "production_eligible":False,
        "error_records":[{"ticker":x["ticker"],"status":x["status"],"error":x["error"]}
                         for x in records if x["status"] in
                         ("SOURCE_PARTIAL_OR_UNVERIFIED","NO_ELIGIBLE_RECENT_FILING_REVIEW_REQUIRED")],
        "records":records,
    }
    (out/"a5k-sec-pilot-evidence.json").write_text(json.dumps(
        report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="records"},
                     ensure_ascii=False,indent=2))
    return report


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a5j",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        x=run_pilot(args.a5j,args.output,agent=os.environ.get("SEC_USER_AGENT",""))
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(f"A5K_PILOT_BLOCKED: {type(exc).__name__}: {exc}")
        return 2
    # A partial pilot is still a faithful audit result, not successful
    # classification. The report must mark all missing cases.
    return 0 if x["status"]=="OFFICIAL_SEC_PILOT_REVIEW_ONLY" else 2


if __name__=="__main__":
    raise SystemExit(main())
