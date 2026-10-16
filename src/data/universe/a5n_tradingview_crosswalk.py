"""A5n: optional user-export TradingView to A4 official directory comparison.

No TradingView raw data stored in git or fetched from private endpoints.
Offline CLI accepts a user-owned CSV and immutable A4 Actions ZIP.
TradingView is current 2026-10-16 export, A4 as-of 2026-10-14; never
claim mismatches indicate errors, delisting, or securities approval.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import re
from zipfile import ZipFile

A4_SHA = "5c7e7080ef6a19dc17d771b830a6d5667b31ea0d8a209d0471c3f5c9f3df9c2d"
TV_SHA = "df1a21bb55222b6fe480db22aa0ea22e50ad1995562597fef476a18fe2ba17fc"
VERSION = "a5n-tv-nasdaq-evidence-review-v1"
COUNTS = {"INCLUDE":4556, "EXCLUDE":7721, "REVIEW_REQUIRED":1010}
REQUIRED = {"Symbol", "Description", "Exchange", "CFI classification",
            "ISIN", "FIGI", "CUSIP", "Average volume, 90 days"}
PREF = re.compile(r"^([A-Z][A-Z0-9.]*)/P([A-Z])$")


class SourceError(ValueError):
    pass


def load_a4(path: Path) -> list[dict]:
    if path.stat().st_size > 50_000_000:
        raise SourceError("A4 archive outside trusted size cap")
    with ZipFile(path) as z:
        name="directory-review/review.json"
        if name not in z.namelist() or z.getinfo(name).file_size > 20_000_000:
            raise SourceError("Frozen A4 review source missing/oversized")
        raw=z.read(name)
    if sha256(raw).hexdigest()!=A4_SHA:
        raise SourceError("Frozen 2026-10-14 A4 SHA256 mismatch")
    obj=json.loads(raw)
    if (obj.get("status")!="REVIEW_ONLY"
            or obj.get("production_eligible") is not False
            or obj.get("total")!=13287 or obj.get("counts")!=COUNTS
            or len(obj.get("rows",[]))!=13287):
        raise SourceError("A4 source decisions not frozen REVIEW_ONLY")
    counts=Counter()
    identities=set()
    for row in obj["rows"]:
        if row.get("production_eligible") is not False or row.get("decision") not in COUNTS:
            raise SourceError("Unapproved original A4 row changed")
        k=(row["source"],row["symbol"],row.get("mic"))
        if k in identities:
            raise SourceError("Duplicate A4 listing/source identity")
        identities.add(k)
        counts[row["decision"]]+=1
    if counts!=Counter(COUNTS):
        raise SourceError("Official A4 decision count drift")
    return obj["rows"]


def load_csv(path: Path, *, expected_sha: str=TV_SHA) -> tuple[list[dict], dict]:
    if path.stat().st_size > 25_000_000:
        raise SourceError("TradingView user export exceeds limit")
    raw=path.read_bytes()
    digest=sha256(raw).hexdigest()
    if digest!=expected_sha or b"\0" in raw:
        raise SourceError("Untrusted/tampered original TradingView export bytes")
    reader=csv.reader(io.StringIO(raw.decode("utf-8-sig"),newline=""))
    header=next(reader)
    if not REQUIRED.issubset(header) or any(header.count(k)!=1 for k in REQUIRED):
        raise SourceError("Missing/duplicated required CSV column")
    indices={name:header.index(name) for name in REQUIRED}
    duplicate={k:c for k,c in Counter(header).items() if c>1}
    rows=[]
    seen=set()
    for i,parts in enumerate(reader,2):
        if len(parts)!=len(header):
            raise SourceError(f"CSV row {i} field count mismatch")
        r={name:parts[idx] for name,idx in indices.items()}
        if not r["Symbol"] or r["Symbol"] in seen:
            raise SourceError("TV blank/duplicate ticker")
        seen.add(r["Symbol"])
        rows.append(r)
    return rows,{"sha256":digest,"rows":len(rows),"columns":len(header),
                 "duplicate_nonkey_headers":duplicate}


def compare(a4: list[dict], tv: list[dict], meta: dict) -> tuple[dict,dict]:
    official={}
    for r in a4:
        if r.get("mic") not in ("XNAS","XNYS","XASE"):
            continue
        key=(r["symbol"],r["mic"])
        if key in official:
            raise SourceError("Ambiguous official ticker+MIC")
        official[key]=r
    exchanges=Counter()
    matches=[]
    format_candidates=[]
    tv_only=[]
    priority=[]
    paired=set()
    for r in tv:
        exchange=r["Exchange"]
        exchanges[exchange]+=1
        mic={"NASDAQ":"XNAS","NYSE":"XNYS"}.get(exchange)
        if mic is None:
            continue    # XASE, OTC, NYSE Arca, CBOE never guessed
        raw_sym=r["Symbol"]
        key=(raw_sym,mic)
        orig=official.get(key)
        candidate=False
        if orig is None and mic=="XNYS":
            m=PREF.fullmatch(raw_sym)
            if m:
                alt=(m.group(1)+"$"+m.group(2),"XNYS")
                orig=official.get(alt)
                if orig is not None:
                    key=alt
                    candidate=True
        if orig is None:
            tv_only.append({"tv_symbol":raw_sym,"exchange":exchange,
                            "tv_description":r["Description"],
                            "review_reason":"MISSING_FROM_A4_OR_TIME_MISMATCH"})
            continue
        if key in paired:
            raise SourceError("Two TV symbols collapse into one listed candidate")
        paired.add(key)
        cfi=r["CFI classification"].strip().upper()
        flags=[]
        if orig["decision"]=="INCLUDE" and cfi.startswith("CI"):
            flags.append("COLLECTIVE_INVESTMENT_CFI_CLUE")
        if orig["decision"]=="INCLUDE" and cfi.startswith("EP"):
            flags.append("PREFERRED_EQUITY_CFI_CLUE")
        record={"tv_symbol":raw_sym,"a4_symbol":orig["symbol"],
                "mic":mic,"a4_decision":orig["decision"],
                "a4_reason":orig["reason"],
                "mapping":"PREFERRED_DISPLAY_CANDIDATE_NOT_IDENTITY_APPROVAL" if candidate else "EXACT_TICKER_MIC",
                "cfi":cfi,"flags":flags,"identity_approved":False,
                "production_eligible":False}
        matches.append(record)
        if candidate:
            format_candidates.append(record)
        if flags:
            priority.append(record)
    official_only=[{"symbol":v["symbol"],"mic":v["mic"],
                    "a4_decision":v["decision"],
                    "reason":"XASE_NOT_PRESENT_IN_EXPORT" if v["mic"]=="XASE"
                            else "A4_ONLY_COVERAGE_OR_DATE_MISMATCH"}
                   for key,v in official.items() if key not in paired]
    tv_regulated=exchanges["NASDAQ"]+exchanges["NYSE"]
    if (tv_regulated != len(matches)+len(tv_only)
            or len(official)!=len(matches)+len(official_only)):
        raise SourceError("Source coverage reconciliation failed")
    return {
        "status":"INDEPENDENT_TV_COMPARISON_REVIEW_ONLY",
        "policy_version":VERSION,
        "a4_as_of":"2026-10-14",
        "tv_file_date":"2026-10-16",
        "known_at_2026_10_14_proven":False,
        "source_sha256":{"A4":A4_SHA,"TradingView_CSV":meta["sha256"]},
        "tv_rows":meta["rows"],"tv_columns":meta["columns"],
        "duplicate_nonkey_headers":meta["duplicate_nonkey_headers"],
        "tv_exchange_counts":dict(exchanges),
        "tv_nasdaq_nyse_rows":tv_regulated,
        "a4_XNAS_XNYS_XASE_rows":len(official),
        "exact_ticker_MIC_matches":len(matches)-len(format_candidates),
        "preferred_display_candidates":len(format_candidates),
        "tv_only_unresolved":len(tv_only),
        "official_only_three_MIC":len(official_only),
        "A4_XASE_no_TV_counterpart":sum(v["mic"]=="XASE" for v in official_only),
        "provisional_include_CFI_disagreement_review":len(priority),
        "CFI_disagreement_prefixes":dict(Counter(x["cfi"][:2] for x in priority)),
        "security_id_approvals":0,"production_approvals":0,
        "gate_connected_to_production":False,"production_eligible":False,
    },{"matches":matches,"preferred_format_candidates":format_candidates,
       "tv_only":tv_only,"official_only":official_only,
       "priority_review":priority}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--user-tradingview-csv",type=Path,required=True)
    p.add_argument("--official-a4-zip",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        rows,metadata=load_csv(args.user_tradingview_csv)
        a4=load_a4(args.official_a4_zip)
        report,tables=compare(a4,rows,metadata)
        args.output.mkdir(parents=True,exist_ok=False)
        (args.output/"a5n-summary.json").write_text(
            json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        for name,records in tables.items():
            (args.output/f"{name}.json").write_text(
                json.dumps(records,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(f"A5N_FAIL_CLOSED: {exc}")
        return 2


if __name__=="__main__":
    raise SystemExit(main())
