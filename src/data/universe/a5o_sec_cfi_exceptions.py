"""A5o SEC evidence queue for 21 TradingView CFI vs provisional A4 INCLUDE conflicts.

SEC filer and filings are issuer-level evidence only: N-CSR/N-CSRS/N-CEN
can support investment-company review; N-2 absence in recent filings
cannot prove no historical registration. No security ID/type/production
approval, no portfolio or publisher integration.
"""
import argparse
from datetime import date,datetime,timezone
from hashlib import sha256
import json,os
from pathlib import Path
import time
from urllib.request import Request,build_opener
from .sec_capture import NoRedirect,validate_user_agent

A4_SHA="5c7e7080ef6a19dc17d771b830a6d5667b31ea0d8a209d0471c3f5c9f3df9c2d"
SEC_SHA="c90bb2d57bb62fae8171abf37b7eb040917f9fb6b5238e6d5dc028baaec318e5"
TV_SHA="df1a21bb55222b6fe480db22aa0ea22e50ad1995562597fef476a18fe2ba17fc"
AS_OF=date(2026,10,14)
CI="BSTZ GAB GAM TYG BCX BOE GUT ETO VKQ GGT ETX MPV GRX JHS GGZ JHI ECAT MCI BTX BMEZ".split()
TVC="TVC"
TARGET=tuple(CI+[TVC])
FUND_FORMS={"N-CSR","N-CSRS","N-CEN","N-2","N-2/A","N-1A","N-1A/A","497","485BPOS"}
OTHER_FORMS={"10-K","10-Q","8-K","S-1","424B2","424B5","25"}
MAX_SUBMISSION=12*1024*1024
VERSION="a5o-critical-CFI-official-issuer-evidence-v1"


class EvidenceError(ValueError):pass


def source(path,digest):
    b=path.read_bytes()
    if sha256(b).hexdigest()!=digest:raise EvidenceError("Frozen official source SHA changed")
    return json.loads(b)


def issuer_index(a4,sec):
    if (a4.get("total")!=13287 or
        a4.get("counts")!={"INCLUDE":4556,"EXCLUDE":7721,"REVIEW_REQUIRED":1010} or
        a4.get("production_eligible") is not False):
        raise EvidenceError("Frozen A4 universe decisions changed")
    records={}
    for row in a4["rows"]:
        s=row["symbol"]
        if s in TARGET:
            if s in records or row["mic"]!="XNYS" or row["decision"]!="INCLUDE":
                raise EvidenceError("21 targeted symbols must be unique provisional XNYS INCLUDE")
            records[s]=row
    if set(records)!=set(TARGET):raise EvidenceError("One target absent from original A4")
    if sec.get("fields")!=["cik","name","ticker","exchange"]:
        raise EvidenceError("Unexpected original SEC company ticker data")
    cross={}
    for cik,name,symbol,ex in sec["data"]:
        if symbol in TARGET:
            if symbol in cross or ex!="NYSE" or type(cik) is not int:
                raise EvidenceError("Duplicate/untrusted SEC issuer candidate")
            cross[symbol]={"cik":f"{cik:010d}","issuer_name":name}
    if set(cross)!=set(TARGET):raise EvidenceError("SEC ticker-exchange crosswalk incomplete")
    return records,cross


def inspect_submissions(raw,cik):
    if not raw or len(raw)>MAX_SUBMISSION:raise EvidenceError("SEC source missing/oversized")
    j=json.loads(raw)
    c=j.get("cik")
    if type(c) not in (str,int) or not str(c).isascii() or not str(c).isdigit() or f"{int(c):010d}"!=cik:
        raise EvidenceError("SEC submissions issuer CIK mismatch")
    filings=j.get("filings",{})
    recent=filings.get("recent",{})
    cols=["form","filingDate","accessionNumber"]
    if any(not isinstance(recent.get(k),list) for k in cols):
        raise EvidenceError("SEC recent filing arrays absent")
    if len({len(recent[k]) for k in cols})!=1:
        raise EvidenceError("SEC recent filing columns unaligned")
    observations=[]
    for form,day,acc in zip(*(recent[k] for k in cols)):
        if not isinstance(form,str) or not isinstance(day,str) or not isinstance(acc,str):
            raise EvidenceError("SEC form/date/accession malformed")
        d=date.fromisoformat(day)
        if d<=AS_OF and form in FUND_FORMS|OTHER_FORMS:
            observations.append({"form":form,"filing_date":day,"accession":acc})
    observations.sort(key=lambda x:(x["filing_date"],x["accession"]),reverse=True)
    return {"form_evidence":observations[:18],
            "registered_fund_form_seen_in_recent":any(f["form"] in FUND_FORMS for f in observations),
            "historic_filing_chunks_not_fetched":len(filings.get("files",[])),
            "historic_N2_absence_proven":False,
            "sec_submissions_sha256":sha256(raw).hexdigest(),
            "issuer_type_approved":False}


def run(a4_root,out,agent,fetcher=None,pause=time.sleep):
    validate_user_agent(agent)
    a4=source(a4_root/"directory-review/review.json",A4_SHA)
    sec=source(a4_root/"sec-capture"/f"company_tickers_exchange-{SEC_SHA}.json",SEC_SHA)
    listings,issuers=issuer_index(a4,sec)
    out.mkdir(parents=True,exist_ok=False)
    results=[]
    for ix,sym in enumerate(TARGET):
        if ix:pause(0.85)
        cik=issuers[sym]["cik"]
        url=f"https://data.sec.gov/submissions/CIK{cik}.json"
        row={"ticker":sym,"source_A4_decision":"INCLUDE",
             "tv_cfi_prefix":"EP" if sym==TVC else "CI",
             "official_cik_candidate":cik,
             "official_source_sha256":SEC_SHA,
             "tv_csv_source_sha256":TV_SHA,
             "investigation":"PREFERRED_OR_DEBT_CFI" if sym==TVC else "COLLECTIVE_INVESTMENT_CFI",
             "status":"SOURCE_NOT_VERIFIED","release_hold_proposed":True,
             "production_eligible":False,"issuer_type_approved":False,
             "listed_security_id_approved":False,
             "known_at_2026_10_14_proven":False}
        try:
            if fetcher is None:
                req=Request(url,headers={"User-Agent":agent,
                    "Accept":"application/json","Accept-Encoding":"identity"})
                with build_opener(NoRedirect()).open(req,timeout=45) as response:
                    if response.geturl()!=url:raise EvidenceError("SEC submissions redirected")
                    raw=response.read(MAX_SUBMISSION+1)
            else:raw=fetcher(url)
            evidence=inspect_submissions(raw,cik)
            name=f"CIK{cik}-{evidence['sec_submissions_sha256']}.json"
            (out/name).write_bytes(raw)
            row.update(status="SEC_ISSUER_FORMS_CAPTURED_REVIEW_ONLY",
                       official_sec_submissions_url=url,sec_source_file=name,
                       retrieved_at=datetime.now(timezone.utc).isoformat(),
                       **evidence)
        except (OSError,ValueError,TimeoutError,TypeError) as ex:
            row["error"]=f"{type(ex).__name__}: {ex}"[:200]
        results.append(row)
    reviewed=sum(x["status"]=="SEC_ISSUER_FORMS_CAPTURED_REVIEW_ONLY" for x in results)
    report={"version":VERSION,"as_of":AS_OF.isoformat(),
            "status":"ISSUER_EVIDENCE_REVIEW_ONLY" if reviewed==21 else "PARTIAL_SOURCE_REVIEW_ONLY",
            "issuer_candidates":21,"sources_verified":reviewed,
            "fund_form_seen_count":sum(x.get("registered_fund_form_seen_in_recent",False) for x in results),
            "SEC_historic_chunks_incomplete":sum(x.get("historic_filing_chunks_not_fetched",0) for x in results),
            "classification_decisions_closed":0,
            "production_approvals":0,"production_eligible":False,"rows":results}
    (out/"a5o-official-issuer-forms.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="rows"},indent=2))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a4",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    try:
        r=run(args.a4,args.output,os.getenv("SEC_USER_AGENT",""))
        return 0 if r["status"]=="ISSUER_EVIDENCE_REVIEW_ONLY" else 2
    except (ValueError,OSError,TypeError,KeyError) as ex:
        print("A5O_FAIL_CLOSED:",ex);return 2


if __name__=="__main__":raise SystemExit(main())
