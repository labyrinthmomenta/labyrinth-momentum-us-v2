"""A5s controlled capture of original SEC N-CEN / 10-K source documents.

Start from SHA-pinned A5o SEC issuer submissions bytes. Capture precisely
one latest pre-as-of N-CEN per 20 fund candidates and one TVC 10-K.
Source filing_date != retrieved_at != effective_at != known_at.
No original form interpreted as independent traded-security approval.
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

from .a5o_sec_cfi_exceptions import CI,TVC,TARGET
from .sec_capture import NoRedirect,validate_user_agent

A5O_SHA="a7661fc8a154028b7b7a519f9fa89575472198cbc6a0054f27f31c704ccbe8f6"
AS_OF=date(2026,10,14)
MAX_RAW=22*1024*1024
MAX_META=12*1024*1024
ACC=re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}")
DOC=re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*")


class CaptureError(ValueError):
    pass


def latest_form(raw:bytes,*,cik:str,ticker:str)->dict:
    if not 50<=len(raw)<=MAX_META:
        raise CaptureError("SEC issuer metadata empty or oversized")
    x=json.loads(raw)
    c=x.get("cik")
    if type(c) not in (str,int) or not str(c).isascii() or not str(c).isdecimal() or f"{int(c):010d}"!=cik:
        raise CaptureError("SEC metadata CIK mismatch")
    recent=x.get("filings",{}).get("recent",{})
    cols=("form","filingDate","accessionNumber","primaryDocument")
    if any(type(recent.get(k)) is not list for k in cols):
        raise CaptureError("Missing original SEC submissions columns")
    if len({len(recent[k]) for k in cols})!=1:
        raise CaptureError("SEC submissions columns misaligned")
    form="10-K" if ticker==TVC else "N-CEN"
    options=[]
    for f,dt,a,name in zip(*(recent[c] for c in cols)):
        if type(f)!=str or type(dt)!=str:
            raise CaptureError("Bad SEC date/form")
        d=date.fromisoformat(dt)
        if f!=form or d>AS_OF:continue
        if not isinstance(a,str) or not ACC.fullmatch(a) or not isinstance(name,str) or not DOC.fullmatch(name):
            raise CaptureError("Bad SEC accession/filename")
        if any(k in (".","..") for k in name.split("/")):
            raise CaptureError("SEC path traversal")
        options.append({"form":form,"filing_date":dt,
                        "accession":a,"primary_doc_name":name,
                        "url":f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a.replace('-','')}/{name}"})
    options.sort(key=lambda y:(y["filing_date"],y["accession"]),reverse=True)
    if not options:
        raise CaptureError("No accessible pre-as-of SEC primary metadata; older history unresolved")
    return options[0]


def fetch_sec(url:str,agent:str,*,limit=MAX_RAW)->bytes:
    # Constructed only by latest_form(); independent URL and path allow-list.
    m=re.fullmatch(r"https://www\.sec\.gov/Archives/edgar/data/([0-9]+)/([0-9]{18})/([A-Za-z0-9._/-]+)",url)
    if not m or any(p in (".","..") for p in m.group(3).split("/")):
        raise CaptureError("SEC primary URL outside allow-list")
    request=Request(url,headers={
        "User-Agent":validate_user_agent(agent),
        "Accept":"text/html,text/xml,application/xml,text/plain",
        "Accept-Encoding":"identity",
    })
    with build_opener(NoRedirect()).open(request,timeout=55) as response:
        if response.geturl()!=url:
            raise CaptureError("SEC source redirect not allowed")
        raw=response.read(limit+1)
    if not 150<=len(raw)<=limit or b"access denied" in raw[:1000].lower():
        raise CaptureError("SEC source inaccessible/oversized/blocked")
    return raw


def capture(original_folder:Path,out:Path,*,agent:str,fetcher=fetch_sec,pause=time.sleep)->dict:
    validate_user_agent(agent)
    report_bytes=(original_folder/"a5o-official-issuer-forms.json").read_bytes()
    if sha256(report_bytes).hexdigest()!=A5O_SHA:
        raise CaptureError("A5o source inventory SHA mismatch")
    report=json.loads(report_bytes)
    if (report.get("status")!="ISSUER_EVIDENCE_REVIEW_ONLY"
        or report.get("sources_verified")!=21
        or report.get("production_approvals")!=0
        or len(report.get("rows",[]))!=21
        or {x["ticker"] for x in report["rows"]}!=set(TARGET)):
        raise CaptureError("Unverified A5o source inventory")
    out.mkdir(parents=True,exist_ok=False)
    rows=[]
    for i,r in enumerate(report["rows"]):
        sym=r["ticker"];cik=r["official_cik_candidate"]
        item={"ticker":sym,"cik":cik,"status":"SOURCE_UNVERIFIED",
              "original_A4_decision":"INCLUDE",
              "source_A5o_sha256":A5O_SHA,
              "production_eligible":False,"security_id_approved":False,
              "legal_type_approved":False,"known_at_as_of_proven":False}
        try:
            metadata=(original_folder/r["sec_source_file"]).read_bytes()
            if sha256(metadata).hexdigest()!=r["sec_submissions_sha256"]:
                raise CaptureError("SEC original issuer submissions source hash mismatch")
            filing=latest_form(metadata,cik=cik,ticker=sym)
            if i:pause(.85)
            raw=fetcher(filing["url"],agent)
            now=datetime.now(timezone.utc)
            digest=sha256(raw).hexdigest()
            name=f"{sym}-{filing['accession']}-{digest}.source"
            (out/name).write_bytes(raw)
            item.update(status="PRIMARY_BYTES_CAPTURED_REVIEW_ONLY",
                        filing=filing,raw_sha256=digest,raw_bytes=len(raw),
                        retrieved_at=now.isoformat(),raw_filename=name)
        except (ValueError,OSError,TypeError,KeyError,TimeoutError) as error:
            item["error"]=f"{type(error).__name__}: {error}"[:250]
        rows.append(item)
    verified=sum(x["status"]=="PRIMARY_BYTES_CAPTURED_REVIEW_ONLY" for x in rows)
    result={"status":"SEC_ORIGINAL_21_COMPLETE_REVIEW_ONLY" if verified==21 else "SEC_ORIGINAL_PARTIAL_REVIEW_ONLY",
            "as_of":AS_OF.isoformat(),"source_sha256":A5O_SHA,
            "sources_expected":21,"source_bytes_verified":verified,
            "type_decisions_finalized":0,"independent_security_ids_approved":0,
            "production_approvals":0,"production_eligible":False,
            "documents":rows}
    (out/"a5s-original-primary-receipts.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="documents"},indent=2))
    return result


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a5o",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        result=capture(args.a5o,args.output,agent=os.getenv("SEC_USER_AGENT",""))
        return 0 if result["source_bytes_verified"]==21 else 2
    except (OSError,ValueError,TypeError,KeyError) as e:
        print("A5S_SOURCE_CAPTURE_DENY:",e);return 2


if __name__=="__main__":
    raise SystemExit(main())
