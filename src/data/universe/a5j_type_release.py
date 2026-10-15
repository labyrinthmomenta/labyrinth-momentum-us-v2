"""A5j: source-pinned instrument-type triage and DENY-ONLY offline release gate.

This is an evidence inventory and release-gate *prototype*, not production
integration. It must not grant any approval. A verified issuer SEC CIK is not
a listed security identity; a missing SEC mutual-fund ticker is not proof of
common stock; a 10-Q row is supporting evidence, not a release authorization.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

from .a5i_decision_ledger import A4_NASDAQ_HASH, A5_INSTRUMENT_HASH, REASONS

VERSION = "a5j-type-review-release-deny-v1"
A5I_SHA = "306be7c6293649b367caa999fa374c1fcd7f7caa41af6f9f3bef58b95387922a"
A5B_SHA = "8268c9368d1a25cad184ad79434d69d328fca550ad1a265ff224497783ff85d7"
A5E_SHA = "a58638402bbdc59b7afb2de3dfe439c6672cc0a1ede40fb59bd8a283aea7612f"
SEC_MF_SHA = "6a98923d0aad49aa386be6423892f19d489047a9041ef09c81af89302d599efc"
EXPECTED = 1010
EXPECTED_BDC = 16
REQUIRED_A5I_STATUS = "EVIDENCE_LEDGER_REVIEW_ONLY"
HEX = re.compile(r"[0-9a-f]{64}")
HEX_CIK = re.compile(r"[0-9]{10}")
EVIDENCE_GATES = {
    "FINANCIAL_STATUS_REVIEW": (
        "NASDAQ_FINANCIAL_STATUS_RESOLUTION", "OFFICIAL_SECURITY_CLASS_TITLE",
        "ISSUER_ID_TO_LISTED_SECURITY_CROSSCHECK", "KNOWN_AT_EFFECTIVE_AT"),
    "FUND_NAME_REQUIRES_TYPE_EVIDENCE": (
        "OFFICIAL_OPEN_VS_CLOSED_END_FUND_OR_REIT_TYPE", "SEC_EDGAR_N2_OR_10K",
        "LISTED_SECURITY_CLASS", "KNOWN_AT_EFFECTIVE_AT"),
    "SPAC_BDC_OR_FINANCIAL_REVIEW": (
        "SEC_S1_SPAC_VS_BDC_FILINGS", "N54A_N54C_STATUS_TIMELINE_WHEN_BDC",
        "UNIT_COMMON_WARRANT_CLASS", "APPROVED_SCOPE_POLICY", "KNOWN_AT_EFFECTIVE_AT"),
    "TYPE_UNCONFIRMED": (
        "OFFICIAL_LISTED_SECURITY_TYPE", "CLASS_AND_TRADING_SYMBOL",
        "KNOWN_AT_EFFECTIVE_AT"),
    "UNKNOWN_EXCHANGE_CODE": (
        "OFFICIAL_VENUE_MIC_AND_SOURCE_SCOPE", "EXPLICIT_TXSE_SCOPE_APPROVAL",
        "KNOWN_AT_EFFECTIVE_AT"),
}


class A5jEvidenceError(ValueError):
    pass


def _frozen(path: Path, digest: str) -> dict:
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != digest:
        raise A5jEvidenceError(f"Frozen source SHA256 mismatch: {path.name}")
    source = json.loads(raw.decode("utf-8"))
    if not isinstance(source, dict):
        raise A5jEvidenceError(f"Frozen source root is not an object: {path.name}")
    return source


def _valid_timestamp(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw)
    if dt.utcoffset() is None:
        raise A5jEvidenceError("SEC evidence timestamp must be timezone-aware")
    return dt


def _key_a5i(r: dict) -> tuple[str, str, str, str]:
    return (r["listing_source"], r["symbol"], r["mic"] or "",
            r["source_listing_sha256"])


def _key_fund(r: dict) -> tuple[str, str, str]:
    return (r["ticker"], r["mic"] or "", r["a4_listing_source_sha256"])


def read_sources(a5i_path: Path, a5b_path: Path, a5e_path: Path) -> tuple[dict,dict,dict]:
    i = _frozen(a5i_path / "a5i-decision-ledger.json", A5I_SHA)
    b = _frozen(a5b_path / "report" / "full-fund-evidence.json", A5B_SHA)
    e = _frozen(a5e_path / "a5e-financial-evidence.json", A5E_SHA)
    if (i.get("version") != "a5i-evidence-ledger-review-v1"
            or i.get("status") != REQUIRED_A5I_STATUS
            or i.get("as_of") != "2026-10-14"
            or i.get("production_eligible") is not False
            or i.get("production_approvals") != 0 or i.get("auto_promoted") != 0
            or i.get("source_failures") != []
            or i.get("a5_review_total") != EXPECTED
            or i.get("still_review_required") != EXPECTED
            or i.get("human_review_complete") is not False
            or i.get("sources", {}).get("a5_review_sha256") != A5_INSTRUMENT_HASH):
        raise A5jEvidenceError("A5i predecessor is not a full unapproved source")
    if (b.get("status") != "REVIEW_ONLY"
            or b.get("production_eligible") is not False
            or b.get("instrument_review_total") != EXPECTED
            or b.get("sec_fund_source_sha256") != SEC_MF_SHA
            or b.get("approved_instruments") != 0
            or b.get("fund_ticker_match_status_counts") !=
               {"NOT_IN_SEC_FUND_TICKER_FILE": EXPECTED}
            or b.get("not_in_sec_fund_registry_is_not_proof_of_common_stock") is not True):
        raise A5jEvidenceError("A5b fund registry is unverified or incorrectly promoted")
    _valid_timestamp(b["sec_fund_retrieved_at"])
    if (e.get("status") != "SOURCE_CAPTURED_REVIEW_ONLY"
            or e.get("production_eligible") is not False
            or e.get("issuer_total") != EXPECTED_BDC
            or e.get("financial_documents_captured") != EXPECTED_BDC
            or e.get("source_failures") or e.get("production_approvals") != 0
            or e.get("bdc_issuer_status_approvals") != 0
            or e.get("security_class_approvals") != 0):
        raise A5jEvidenceError("A5e 16 SEC 10-Q documents not complete/review-only")
    if (len(i.get("a5_instrument_review_ledger", [])) != EXPECTED
            or len(b.get("review_entries", [])) != EXPECTED
            or len(e.get("findings", [])) != EXPECTED_BDC):
        raise A5jEvidenceError("Source row populations incomplete")
    overlays = i.get("merger_company_evidence_overlays", [])
    if (len(overlays) != 2
            or {o.get("symbol") for o in overlays} != {"LIEN","REFI"}
            or any(o.get("explicit_release_hold") is not True
                   or o.get("production_eligible") is not False
                   or o.get("merger_completion") != "NOT_ESTABLISHED" for o in overlays)
            or i.get("REFI_separate_corporate_event_hold") is not True):
        raise A5jEvidenceError("LIEN/REFI pending corporate-event holds missing")
    return i,b,e


def build_triage(i: dict, b: dict, e: dict, *, financial_raw_directory: Path | None = None) -> dict:
    """Join official records by ticker + MIC + actual pinned listing-source SHA."""
    fund = {}
    for r in b["review_entries"]:
        key = _key_fund(r)
        if key in fund:
            raise A5jEvidenceError("Duplicate A5b fund ticker/MIC/listing source")
        if (r.get("classification_decision") != "REVIEW_REQUIRED"
                or r.get("approved_security_id") is not None
                or r.get("production_eligible") is not False
                or r.get("sec_fund_status") != "NOT_IN_SEC_FUND_TICKER_FILE"
                or r.get("fund_class_candidates") != []
                or r.get("fund_registry_source_sha256") != SEC_MF_SHA
                or r.get("original_review_reason") not in REASONS):
            raise A5jEvidenceError("A5b row type/match/source decision changed")
        fund[key] = r
    bdc={}
    for r in e["findings"]:
        ticker=r.get("tickers")
        observation=r.get("latest_financial_observation",{})
        if (not isinstance(ticker,list) or len(ticker)!=1
                or ticker[0] in bdc or not HEX_CIK.fullmatch(r.get("cik",""))
                or r.get("production_eligible") is not False
                or r.get("issuer_bdc_status") != "REVIEW_REQUIRED"
                or r.get("listed_security_class_status") != "REVIEW_REQUIRED"
                or r.get("post_financial_events_checked") is not False
                or r.get("n54c_absence_proven") is not False
                or observation.get("status") != "FINANCIAL_DOCUMENT_REVIEW_EVIDENCE"
                or observation.get("issuer_bdc_status_approved") is not False
                or observation.get("listed_security_class_approved") is not False
                or not observation.get("listed_security_row_candidates")
                or observation["listed_security_row_candidates"][0].get("ticker") != ticker[0]
                or observation["listed_security_row_candidates"][0].get("row_evidence_present") is not True):
            raise A5jEvidenceError("A5e common stock candidate source incomplete")
        latest=r["latest_financial"]
        if (latest.get("form") != "10-Q"
                or date.fromisoformat(latest["filing_date"]) > date(2026,10,14)):
            raise A5jEvidenceError("A5e financial filing outside as-of window")
        digest=observation.get("sha256")
        if not isinstance(digest,str) or not HEX.fullmatch(digest):
            raise A5jEvidenceError("Malformed A5e raw SEC source digest")
        if financial_raw_directory is not None:
            filename=f"CIK{r['cik']}-{latest['accession']}-{digest}.html"
            raw=(financial_raw_directory/filename).read_bytes()
            if sha256(raw).hexdigest()!=digest or len(raw)!=observation.get("bytes"):
                raise A5jEvidenceError("A5e SEC 10-Q source bytes not intact")
        _valid_timestamp(observation["retrieved_at"])
        bdc[ticker[0]]=r

    counts=Counter()
    clues=Counter()
    missing_sec_cik=Counter()
    output=[]
    used=set()
    for r in i["a5_instrument_review_ledger"]:
        key=(r["symbol"],r["mic"] or "",r["source_listing_sha256"])
        original=_key_a5i(r)
        if original in used:
            raise A5jEvidenceError("Duplicate A5i listing security candidate")
        used.add(original)
        f=fund.pop(key,None)
        reason=r["original_a5_reason"]
        if (f is None or f["original_review_reason"]!=reason
                or r["a5i_decision"]!="REVIEW_REQUIRED"
                or r["original_a5_decision"]!="REVIEW_REQUIRED"
                or r["production_eligible"] is not False
                or r["listed_security_class_approved"] is not False
                or r["issuer_legal_status_approved"] is not False
                or reason not in REASONS
                or r.get("issuer_cik_candidate") != f.get("a5_issuer_cik_candidate")
                or r.get("source_sec_sha256") != b["a4_sec_company_source_sha256"]
                or not HEX.fullmatch(r["source_listing_sha256"])):
            raise A5jEvidenceError("A5i and A5b sources disagree on ticker/type/CIK")
        is_bdc=r["symbol"] in bdc
        sec=bdc.get(r["symbol"])
        if is_bdc and (reason!="SPAC_BDC_OR_FINANCIAL_REVIEW"
                       or sec["cik"]!=r["issuer_cik_candidate"]
                       or r["mic"]!="XNAS" and r["mic"]!="XNYS"):
            raise A5jEvidenceError("Issuer BDC 10-Q cannot be assigned to listed ticker")
        flags=f.get("directory_name_clues")
        if not isinstance(flags,list) or any(not isinstance(x,str) for x in flags):
            raise A5jEvidenceError("Nasdaq directory name-clue schema invalid")
        counts[reason]+=1
        clues.update(flags)
        if not r["issuer_cik_candidate"]:
            missing_sec_cik[reason]+=1
        caution=["SEC_MF_NO_MATCH_IS_NOT_TYPE_PROOF"]
        if is_bdc:
            caution.extend(["SEC_10Q_BDC_ISSUER_EVIDENCE_NOT_LEGAL_STATUS_APPROVAL",
                            "SEC_10Q_CLASS_ROW_CANDIDATE_NOT_SECURITY_ID"])
        if r["symbol"]=="LIEN":
            caution.append("UNRESOLVED_LIEN_REFI_MERGER")
        output.append({
            "listing_source":r["listing_source"],"symbol":r["symbol"],
            "mic":r["mic"],"issuer_cik_candidate":r["issuer_cik_candidate"],
            "a5_original_reason":reason,"a5i_decision":"REVIEW_REQUIRED",
            "directory_name_clues_nonexclusive":flags,
            "sec_mutual_fund_ticker_match":"NOT_IN_SEC_FUND_TICKER_FILE",
            "evidence_tier":(
                "SEC_10Q_ISSUER_PLUS_LISTED_CLASS_CANDIDATE" if is_bdc else
                "SEC_ISSUER_CIK_ONLY" if r["issuer_cik_candidate"] else
                "OFFICIAL_LISTING_ONLY_NO_EXACT_SEC_ISSUER"
            ),
            "sec_10q_accession":sec["latest_financial"]["accession"] if is_bdc else None,
            "sec_10q_sha256":sec["latest_financial_observation"]["sha256"] if is_bdc else None,
            "caution_flags":caution,
            "evidence_needed":list(EVIDENCE_GATES[reason]),
            "source_listing_sha256":r["source_listing_sha256"],
            "source_sec_company_sha256":r["source_sec_sha256"],
            "source_sec_fund_sha256":SEC_MF_SHA,
            "separate_security_id":None,
            "human_type_review_approved":False,
            "issuer_bdc_current_status_approved":False,
            "as_of":"2026-10-14","known_at_established":False,
            "release_hold":True,"production_eligible":False,
        })
    if fund or len(output)!=EXPECTED or counts!=Counter(REASONS) or len(bdc)!=EXPECTED_BDC:
        raise A5jEvidenceError("A5j source population or review reason distribution changed")
    if {r["symbol"] for r in output if r["sec_10q_accession"]}!=set(bdc):
        raise A5jEvidenceError("A5e CIK/type evidence missing from mapped review")
    return {
        "status":"CLASSIFICATION_EVIDENCE_TRIAGE_REVIEW_ONLY",
        "version":VERSION,"as_of":"2026-10-14",
        "known_at_established":False,"production_eligible":False,
        "sources":{"a5i_ledger_sha256":A5I_SHA,"a5b_sec_fund_review_sha256":A5B_SHA,
                   "a5e_sec_10q_review_sha256":A5E_SHA,
                   "a5b_sec_fund_registry_sha256":SEC_MF_SHA},
        "total_review_records":EXPECTED,
        "review_by_reason":dict(sorted(counts.items())),
        "name_clues_nonexclusive":dict(sorted(clues.items())),
        "no_exact_sec_issuer_by_reason":dict(sorted(missing_sec_cik.items())),
        "sec_10q_bdc_issuer_class_candidates":EXPECTED_BDC,
        "sec_mf_nonmatches_not_exclusions":EXPECTED,
        "approved_security_ids":0,"promoted_instruments":0,
        "provisional_include_refi_separate_hold":True,
        "manual_review_complete":False,
        "triage_rows":output,
    }


def simulate_release_deny_only(a5j: dict, a5i: dict) -> dict:
    """Never permit publication. This is NOT wired into a production runner."""
    if (a5j.get("status")!="CLASSIFICATION_EVIDENCE_TRIAGE_REVIEW_ONLY"
            or a5j.get("version")!=VERSION
            or a5j.get("total_review_records")!=EXPECTED
            or a5j.get("production_eligible") is not False
            or a5j.get("approved_security_ids")!=0
            or a5j.get("promoted_instruments")!=0
            or a5j.get("provisional_include_refi_separate_hold") is not True
            or len(a5j.get("triage_rows",[]))!=EXPECTED):
        raise A5jEvidenceError("Input triage not eligible for isolated gate simulation")
    held=set()
    records=[]
    for r in a5j["triage_rows"]:
        key=(r["listing_source"],r["symbol"],r["mic"])
        if key in held or r.get("production_eligible") is not False or r.get("release_hold") is not True or r.get("known_at_established") is not False or r.get("separate_security_id") is not None:
            raise A5jEvidenceError("A5j review hold was tampered with")
        held.add(key)
        records.append({"listing_source":r["listing_source"],"symbol":r["symbol"],"mic":r["mic"],
                        "decision":"DENY","reason":"REVIEW_REQUIRED_UNAPPROVED_SECURITY_TYPE"})
    overlays=a5i.get("merger_company_evidence_overlays",[])
    if {o.get("symbol") for o in overlays}!={"LIEN","REFI"}:
        raise A5jEvidenceError("LIEN and REFI overlay missing")
    for o in overlays:
        if o.get("explicit_release_hold") is not True or o.get("production_eligible") is not False:
            raise A5jEvidenceError("Corporate event hold has been tampered with")
        if o["symbol"]=="REFI":
            key=("nasdaqlisted","REFI",o["mic"])
            if key in held or o.get("a4_original_decision")!="INCLUDE":
                raise A5jEvidenceError("REFI original provisional INCLUDE and distinct hold invalid")
            records.append({"listing_source":"nasdaqlisted","symbol":"REFI","mic":o["mic"],
                            "decision":"DENY","reason":"PROVISIONAL_INCLUDE_CORPORATE_EVENT_HOLD"})
    if len(records)!=EXPECTED+1:
        raise A5jEvidenceError("Gate candidate inventory unexpectedly changed")
    return {
        "status":"OFFLINE_RELEASE_SIMULATION_DENY_ALL",
        "version":VERSION,"as_of":"2026-10-14","connected_to_production":False,
        "independent_approval_verification_implemented":False,
        "candidate_count":len(records),"allowed_count":0,"denied_count":len(records),
        "other_4555_provisional_includes_evaluated":False,
        "global_release_permission":"DENY",
        "release_records":records,
    }


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a5i-artifact",type=Path,required=True)
    p.add_argument("--a5b-artifact",type=Path,required=True)
    p.add_argument("--a5e-artifact",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        i,b,e=read_sources(args.a5i_artifact,args.a5b_artifact,args.a5e_artifact)
        review=build_triage(i,b,e,financial_raw_directory=args.a5e_artifact)
        gate=simulate_release_deny_only(review,i)
        args.output.mkdir(parents=True,exist_ok=False)
        for name,payload in (("a5j-type-evidence-triage.json",review),
                             ("a5j-release-gate-simulation.json",gate)):
            (args.output/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        result={k:v for k,v in review.items() if k!="triage_rows"}
        result["release_gate_simulation"]={k:v for k,v in gate.items() if k!="release_records"}
        (args.output/"a5j-summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(f"A5J_BLOCKED: {type(exc).__name__}: {exc}")
        return 2


if __name__=="__main__":
    raise SystemExit(main())
