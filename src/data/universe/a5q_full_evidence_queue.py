"""A5q: frozen 13,287-listing decision queue with A5o and A5p source holds.

No class approval, no automatic inclusion/exclusion: source evidence
never implies production eligibility. Record both provisional decisions
and separate risks; source SHA pinning is mandatory.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

A5K_SHA="e31bcca870189207e9273eea6ba4e48a55949e78822d2b7e8feb7fb3fc851a76"
A5O_SHA="a7661fc8a154028b7b7a519f9fa89575472198cbc6a0054f27f31c704ccbe8f6"
A5P_SHA="7ecb753fcc71db88bb99bdf3130d1e9ebd4aaecadaa0332eb05ebc8213d5d93e"
VERSION="a5q-source-evidence-queue-v1"
A4_TOTAL=13287
BASE_COUNTS={"INCLUDE":4556,"REVIEW_REQUIRED":1010,"EXCLUDE":7721}


class LedgerError(ValueError):pass


def load(path,expected):
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=expected:raise LedgerError("Frozen JSON input SHA mismatch")
    r=json.loads(raw)
    if not isinstance(r,dict):raise LedgerError("Expected JSON object")
    return r


def make_queue(a5k,a5o,a5p):
    if (a5k.get("status")!="FULL_UNIVERSE_SOURCE_REPLAY_DENY_ONLY"
        or a5k.get("all_source_listings_checked")!=A4_TOTAL
        or a5k.get("original_a4_counts")!=BASE_COUNTS
        or a5k.get("candidate_DENY")!=5566
        or a5k.get("candidate_ALLOW")!=0
        or a5k.get("connected_to_production") is not False
        or len(a5k.get("review_records",[]))!=A4_TOTAL):
        raise LedgerError("A5k base release gate no longer DENY-only")
    if (a5o.get("status")!="ISSUER_EVIDENCE_REVIEW_ONLY"
        or a5o.get("sources_verified")!=21
        or a5o.get("fund_form_seen_count")!=20
        or a5o.get("classification_decisions_closed")!=0
        or a5o.get("production_approvals")!=0
        or len(a5o.get("rows",[]))!=21):
        raise LedgerError("SEC 21-issuer evidence incomplete/approved")
    if (a5p.get("status")!="COVERAGE_AND_TIME_REVIEW_ONLY"
        or a5p.get("tv_only_unresolved")!=7
        or a5p.get("official_only_provisional_includes")!=6
        or a5p.get("XASE_no_TradingView_exchange_label")!=314
        or a5p.get("production_approvals")!=0):
        raise LedgerError("A5p coverage source drift")
    exceptions=set()
    for r in a5o["rows"]:
        if (r["status"]!="SEC_ISSUER_FORMS_CAPTURED_REVIEW_ONLY"
            or r["source_A4_decision"]!="INCLUDE"
            or r["production_eligible"] is not False
            or r["issuer_type_approved"] is not False
            or r["listed_security_id_approved"] is not False):
            raise LedgerError("A5o row promoted/unverified")
        sym=r["ticker"]
        if sym in exceptions:raise LedgerError("Duplicate SEC CFI review")
        exceptions.add(sym)
    official_only=set()
    for r in a5p["official_only_include_details"]:
        key=(r["symbol"],r["mic"])
        if key in official_only or r["decision"]!="INCLUDE_PROVISIONAL":
            raise LedgerError("A5p duplicate/altered source-only include")
        official_only.add(key)
    rows=[]
    seen=set()
    dispositions=Counter()
    flags=Counter()
    for row in a5k["review_records"]:
        key=(row["source"],row["symbol"],row["mic"])
        if key in seen:raise LedgerError("Duplicate security source row")
        seen.add(key)
        symbol=row["symbol"]
        original=row["original_a4_decision"]
        old_gate=row["release_result"]
        if row["release_eligible"] is not False or original not in BASE_COUNTS:
            raise LedgerError("A5k row attempted release")
        if (original=="EXCLUDE") != (old_gate=="EXCLUDED_BY_ORIGINAL_A4_NEVER_RELEASED"):
            raise LedgerError("A5k original exclusion changed")
        is_sec_conflict=symbol in exceptions
        if is_sec_conflict and (original!="INCLUDE" or row["mic"]!="XNYS"):
            raise LedgerError("SEC type anomaly not provisional XNYS")
        is_source_only=(symbol,row["mic"]) in official_only
        if is_source_only and original!="INCLUDE":
            raise LedgerError("Source-only ticker changed")
        risk=[]
        if original=="INCLUDE":
            risk.append("PROVISIONAL_TYPE_OR_SHARE_CLASS_NOT_APPROVED")
        elif original=="REVIEW_REQUIRED":
            risk.append("ORIGINAL_SECURITY_TYPE_REVIEW_REQUIRED")
        else:
            risk.append("ORIGINAL_EXCLUDE_PRESERVED")
        if is_sec_conflict:risk.append("SEC_FUND_OR_PREFERRED_ISSUER_FORM_REVIEW")
        if is_source_only:risk.append("MISSING_FROM_TRADINGVIEW_EXPORT_REVIEW")
        if row["mic"]=="XASE":risk.append("NYSE_AMERICAN_TV_COVERAGE_GAP")
        if symbol in ("LIEN","REFI"):risk.append("UNRESOLVED_LIEN_REFI_CORPORATE_EVENT")
        dispositions[original]+=1
        flags.update(risk)
        rows.append({
            "ticker":symbol,"source":row["source"],"mic":row["mic"],
            "official_name":row["name"],"original_a4_decision":original,
            "original_a4_reason":row["original_a4_reason"],
            "decision":"EXCLUDE_ORIGINAL_RETAINED" if original=="EXCLUDE" else "DENY_PENDING_EVIDENCE_AND_APPROVAL",
            "review_flags":risk,"issuer_CIK_not_security_id":True,
            "security_id_approved":False,"independent_reviewer_approved":False,
            "listed_class_approved":False,"point_in_time_known_at_approved":False,
            "production_eligible":False,"source_as_of":"2026-10-14",
        })
    if (len(rows)!=A4_TOTAL or dispositions!=Counter(BASE_COUNTS)
        or flags["SEC_FUND_OR_PREFERRED_ISSUER_FORM_REVIEW"]!=21
        or flags["MISSING_FROM_TRADINGVIEW_EXPORT_REVIEW"]!=6
        or flags["NYSE_AMERICAN_TV_COVERAGE_GAP"]!=314
        or flags["UNRESOLVED_LIEN_REFI_CORPORATE_EVENT"]!=2):
        raise LedgerError("Source population/corporate risk queue mismatch")
    return {
        "status":"A5Q_ALL_SOURCE_DECISIONS_REVIEW_ONLY",
        "version":VERSION,"as_of":"2026-10-14",
        "source_sha256":{"a5k":A5K_SHA,"a5o":A5O_SHA,"a5p":A5P_SHA},
        "source_records":A4_TOTAL,
        "provisional_include":4556,"review_required":1010,"excluded_original":7721,
        "new_sec_issuer_conflict_overlays":21,
        "new_tv_source_coverage_overlays":6,
        "XASE_coverage_gap":314,
        "corporate_event_holds_LIEN_REFI":2,
        "official_decisions_modified":0,"manual_type_approvals":0,
        "independent_security_id_approvals":0,
        "candidate_DENY":5566,"candidate_ALLOW":0,
        "production_eligible":False,"production_gate_connected":False,
        "review_flags_total":dict(flags),"queue":rows,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a5k",type=Path,required=True)
    p.add_argument("--a5o",type=Path,required=True)
    p.add_argument("--a5p",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        o=make_queue(load(args.a5k,A5K_SHA),load(args.a5o,A5O_SHA),load(args.a5p,A5P_SHA))
        args.output.mkdir(parents=True,exist_ok=False)
        (args.output/"a5q-evidence-decision-queue.json").write_text(json.dumps(o,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
        print(json.dumps({k:v for k,v in o.items() if k!="queue"},ensure_ascii=False,indent=2))
        return 0
    except (ValueError,OSError,KeyError,TypeError) as e:
        print("A5Q_FAIL_CLOSED:",e);return 2

if __name__=="__main__":raise SystemExit(main())
