"""A5p: point-in-time conservative ticker/MIC coverage reconciliation.

TradingView 2026-10-16 user-export-derived discrepancies are *not*
NYSE American data, official delist decisions, or production additions.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

VERSION="a5p-dated-mic-exceptions-v1"
A4_SHA="5c7e7080ef6a19dc17d771b830a6d5667b31ea0d8a209d0471c3f5c9f3df9c2d"
TV_SHA="df1a21bb55222b6fe480db22aa0ea22e50ad1995562597fef476a18fe2ba17fc"
TV_ONLY={"NASDAQ":["BMMX","AMRO","IAM"],
         "NYSE":["DCOM/P","TFIN/P","ETI/P","TY/P"]}
OFFICIAL_ONLY_INCLUDE={"XNAS":["EFTY","HCHL","MCTA","OST","SVA"],
                       "XNYS":["TAP.A"]}
DECISIONS={"INCLUDE":4556,"EXCLUDE":7721,"REVIEW_REQUIRED":1010}
EXPECTED_TV_ONLY=7
XASE_TOTAL=314
XASE_DECISIONS={"INCLUDE":225,"EXCLUDE":53,"REVIEW_REQUIRED":36}

class SourceError(ValueError):pass


def reconcile(a4):
    if (a4.get("total")!=13287 or a4.get("counts")!=DECISIONS or
            a4.get("production_eligible") is not False or
            len(a4.get("rows",[]))!=13287):
        raise SourceError("Original 14-Oct official directory decisions altered")
    sym={}
    for row in a4["rows"]:
        key=(row["symbol"],row["mic"])
        if key in sym:raise SourceError("Official ticker+MIC duplicated")
        sym[key]=row
    out=[]
    for exch,names in TV_ONLY.items():
        mic="XNAS" if exch=="NASDAQ" else "XNYS"
        for code in names:
            if (code,mic) in sym:
                raise SourceError("TV-only symbol is present in 14-Oct official directory")
            out.append({"tv_symbol":code,"tv_exchange":exch,
                        "mic":mic,"status":"OFFICIAL_14OCT_ABSENT_REVIEW_ONLY",
                        "date_difference_days":2,"error_proven":False,
                        "delisting_proven":False,"production_eligible":False})
    source_only=[]
    for mic,names in OFFICIAL_ONLY_INCLUDE.items():
        for code in names:
            row=sym.get((code,mic))
            if row is None or row["decision"]!="INCLUDE" or row["production_eligible"] is not False:
                raise SourceError("One prior provisional INCLUDE changed")
            source_only.append({"symbol":code,"mic":mic,
                                "official_directory_name":row["name"],
                                "decision":"INCLUDE_PROVISIONAL",
                                "tv_missing_status":"SOURCE_COVERAGE_OR_DATE_REVIEW",
                                "permanent_security_id":None,
                                "production_eligible":False})
    xase=[x for x in a4["rows"] if x["mic"]=="XASE"]
    if len(xase)!=XASE_TOTAL or Counter(x["decision"] for x in xase)!=Counter(XASE_DECISIONS):
        raise SourceError("314 XASE records or original decisions changed")
    if len(out)!=EXPECTED_TV_ONLY or len(source_only)!=6:
        raise SourceError("Expected 7+6 exceptions missing")
    return {
        "status":"COVERAGE_AND_TIME_REVIEW_ONLY",
        "version":VERSION,"official_as_of":"2026-10-14",
        "tradingview_filename_date":"2026-10-16",
        "exact_known_at_for_TV_export":False,
        "sources":{"A4_sha256":A4_SHA,"TradingView_CSV_sha256":TV_SHA},
        "tv_only_unresolved":len(out),
        "official_only_provisional_includes":len(source_only),
        "XASE_no_TradingView_exchange_label":len(xase),
        "XASE_original_decisions":dict(Counter(x["decision"] for x in xase)),
        "NYSE_Arca_is_not_XASE":True,
        "auto_promoted":0,"auto_excluded":0,
        "production_approvals":0,"production_eligible":False,
        "tv_only_details":out,"official_only_include_details":source_only,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a4-review",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        raw=args.a4_review.read_bytes()
        if sha256(raw).hexdigest()!=A4_SHA:raise SourceError("A4 SHA256 mismatch")
        result=reconcile(json.loads(raw))
        args.output.mkdir(parents=True,exist_ok=False)
        (args.output/"a5p-dated-symbol-coverage.json").write_text(
            json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
        print(json.dumps({k:v for k,v in result.items() if not k.endswith("_details")},
                         ensure_ascii=False,indent=2))
        return 0
    except (ValueError,OSError,KeyError,TypeError) as e:
        print("A5P_FAIL_CLOSED",str(e));return 2


if __name__=="__main__":raise SystemExit(main())
