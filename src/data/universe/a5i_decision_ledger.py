"""A5i — immutable SEC/Nasdaq review ledger and LIEN/REFI merger evidence.

This module does not edit the A4 universe or production eligibility. A4
INCLUDE is provisional; 2026-10-14 is the directory as-of, not a claim that
2026-10-15 SEC retrieval was known in the earlier snapshot.
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
from xml.etree import ElementTree

from .a5g_exhibit_merger_evidence import validate_archive_url
from .a5h_remaining_exhibits import (
    AS_OF, LIEN_CIK, REFI_CIK, parse_submissions_timeline,
    A5hEvidenceError,
)
from .a5e_financial_evidence import inspect_financial
from .sec_capture import NoRedirect, validate_user_agent

POLICY_VERSION = "a5i-evidence-ledger-review-v1"
A4_REVIEW_HASH = "5c7e7080ef6a19dc17d771b830a6d5667b31ea0d8a209d0471c3f5c9f3df9c2d"
A4_NASDAQ_HASH = "2dc5b607a42c3eefe9cf6f7d6e681c30b8fb55bb51ae04d998cdf51af02d6694"
A5_INSTRUMENT_HASH = "ea4a8e3112e3e30d9c3e67fc33fac86a3a6aa3fcf2f58391ecc50896ba3bdb37"
A5H_REPORT_HASH = "7cee3b11745081f31774bb28f9949c769f583c688cc63941b52ca9ee6966c571"
EXPECTED_TOTAL = 13287
EXPECTED_REVIEW = 1010
COUNTS = {"INCLUDE": 4556, "EXCLUDE": 7721, "REVIEW_REQUIRED": 1010}
REASONS = {
    "FINANCIAL_STATUS_REVIEW": 268,
    "FUND_NAME_REQUIRES_TYPE_EVIDENCE": 297,
    "SPAC_BDC_OR_FINANCIAL_REVIEW": 307,
    "TYPE_UNCONFIRMED": 128,
    "UNKNOWN_EXCHANGE_CODE": 10,
}
MERGER_AS_OF = "2026-10-14"
EFFECT_CIK = LIEN_CIK
EFFECT_ACC = "9999999995-26-003107"
EFFECT_FORM = "EFFECT"
REFI_Q_CIK = REFI_CIK
REFI_Q_ACC = "0001193125-26-343398"
REFI_Q_DATE = "2026-08-10"  # metadata must be independently checked, not used for decisions
REFI_Q_URL = (
    "https://www.sec.gov/Archives/edgar/data/1867949/"
    "000119312526343398/refi-20260630.htm"
)
MAX_EFFECT_BYTES = 3 * 1024 * 1024
MAX_10Q_BYTES = 64 * 1024 * 1024


class DecisionLedgerError(ValueError):
    pass


def _sha_file(path: Path, expected: str) -> bytes:
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise DecisionLedgerError(f"Frozen SHA mismatch: {path.name}")
    return raw


def load_sources(a4: Path, a5: Path, a5h: Path) -> dict:
    rows = json.loads(_sha_file(a4 / "directory-review" / "review.json",
                                A4_REVIEW_HASH).decode("utf-8"))
    if (rows.get("total") != EXPECTED_TOTAL
            or rows.get("counts") != COUNTS
            or rows.get("production_eligible") is not False
            or len(rows.get("rows", [])) != EXPECTED_TOTAL):
        raise DecisionLedgerError("A4 official review counts or source status changed")
    source_file = a4 / "nasdaq-capture" / f"nasdaqlisted-{A4_NASDAQ_HASH}.txt"
    listing = _sha_file(source_file, A4_NASDAQ_HASH).decode("utf-8-sig")
    lines = listing.splitlines()
    if not lines or not lines[0].startswith("Symbol|Security Name|"):
        raise DecisionLedgerError("Unexpected official Nasdaq directory layout")
    official = {}
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) < 2:
            continue
        if parts[0] in ("LIEN", "REFI"):
            if parts[0] in official:
                raise DecisionLedgerError("Duplicate official listing")
            official[parts[0]] = parts[1]
    source_rows = {r["symbol"]: r for r in rows["rows"]
                   if r.get("symbol") in ("LIEN", "REFI")}
    if (set(official) != {"LIEN", "REFI"}
            or set(source_rows) != set(official)):
        raise DecisionLedgerError("Official Nasdaq LIEN/REFI evidence missing")
    for symbol, listing_name in official.items():
        original = source_rows[symbol]
        if (original["name"] != listing_name
                or original["mic"] != "XNAS"
                or original["source"] != "nasdaqlisted"
                or original["production_eligible"] is not False):
            raise DecisionLedgerError("SEC/Nasdaq security name mapping changed")
    if (source_rows["LIEN"]["decision"] != "REVIEW_REQUIRED"
            or source_rows["REFI"]["decision"] != "INCLUDE"):
        raise DecisionLedgerError("Original frozen A4 source decisions changed")

    review = json.loads(_sha_file(a5 / "instrument-review.json",
                                 A5_INSTRUMENT_HASH).decode("utf-8"))
    if len(review) != EXPECTED_REVIEW:
        raise DecisionLedgerError("Incomplete original A5 instrument review")
    if Counter(r.get("original_reason") for r in review) != Counter(REASONS):
        raise DecisionLedgerError("A5 reason distribution was changed")
    seen = set()
    for r in review:
        key = (r["source"], r["symbol"], r["mic"])
        if (key in seen
                or r.get("original_decision") != "REVIEW_REQUIRED"
                or r.get("security_type_approved") is not False
                or r.get("production_eligible") is not False):
            raise DecisionLedgerError("A5 source row already promoted/duplicated")
        seen.add(key)
    if (not any(r["symbol"] == "LIEN" for r in review)
            or any(r["symbol"] == "REFI" for r in review)):
        raise DecisionLedgerError("Unexpected LIEN/REFI A5 source review membership")
    a5h_raw = _sha_file(a5h / "a5h-exhibits-and-timeline.json", A5H_REPORT_HASH)
    report = json.loads(a5h_raw)
    if (report.get("status") != "DOCUMENTS_CAPTURED_REVIEW_ONLY"
            or report.get("production_eligible") is not False
            or report.get("exhibits_verified") != 29
            or report.get("merger_issuer_timelines_verified") != 2
            or report.get("LIEN_N14_document_verified") != 1
            or report.get("errors")
            or report.get("merger_closed_confirmed") is not False
            or report.get("voting_result_confirmed") is not False
            or report.get("production_approved") != 0):
        raise DecisionLedgerError("A5h incomplete source receipt")
    timemap = {}
    for t in report["issuer_timelines"]:
        cik = t["cik"]
        if cik in timemap or cik not in (LIEN_CIK, REFI_CIK):
            raise DecisionLedgerError("Wrong or duplicate SEC merger filer")
        sec_raw = _sha_file(a5h / t["original_file"], t["sha256"])
        snap = parse_submissions_timeline(
            sec_raw, cik=cik, retrieved_at=datetime.fromisoformat(t["retrieved_at"]))
        if [(f["form"], f["accession"]) for f in snap["filings"]] != [
                (f["form"], f["accession"]) for f in t["filings"]]:
            raise DecisionLedgerError("SEC issuer filing chronology changed")
        timemap[cik] = t
    if set(timemap) != {LIEN_CIK, REFI_CIK}:
        raise DecisionLedgerError("Missing one SEC filer identity")
    proxy = report["registration_docs"][0]
    if (proxy["cik"] != LIEN_CIK
            or proxy.get("status") != "N14_PRIMARY_DOC_REVIEW_ONLY"
            or proxy["merger_completion_verified"] is not False):
        raise DecisionLedgerError("N-14 review source inconsistent")
    _sha_file(a5h / proxy["original_file"], proxy["sha256"])
    effect_candidates = [
        f for f in timemap[LIEN_CIK]["filings"]
        if f["form"] == EFFECT_FORM and f["accession"] == EFFECT_ACC]
    if len(effect_candidates) != 1 or effect_candidates[0]["filing_date"] != "2026-09-30":
        raise DecisionLedgerError("SEC LIEN EFFECT source metadata changed")
    return {"a4_rows": source_rows, "a5_reviews": review, "a5h": report,
            "timelines": timemap, "effect": effect_candidates[0]}


def fetch_sec_file(url: str, agent: str, *, cap: int, cik: str, accession: str) -> bytes:
    validate_archive_url(url, cik=cik, accession=accession)
    req = Request(url, headers={"User-Agent": validate_user_agent(agent),
                                "Accept": "text/html,text/xml,application/xml",
                                "Accept-Encoding": "identity"})
    with build_opener(NoRedirect()).open(req, timeout=40) as res:
        if res.geturl() != url:
            raise DecisionLedgerError("SEC source redirected")
        raw = res.read(cap + 1)
    if not raw or len(raw) > cap:
        raise DecisionLedgerError("SEC original document missing/oversized")
    return raw


def inspect_effect(raw: bytes) -> dict:
    """EFFECT XML attests to source content only; NOT merger effective time."""
    if not isinstance(raw, bytes) or not 35 <= len(raw) <= MAX_EFFECT_BYTES:
        raise DecisionLedgerError("Empty/oversized SEC EFFECT XML")
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise DecisionLedgerError("XML DTD/entity not allowed")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise DecisionLedgerError("SEC EFFECT XML parse rejected") from exc
    plain = " ".join(" ".join(root.itertext()).split()).casefold()
    if not plain or "effect" not in plain:
        raise DecisionLedgerError("SEC EFFECT XML does not state effectiveness")
    return {"sha256": sha256(raw).hexdigest(), "bytes": len(raw),
            "xml_root": root.tag, "text_effectiveness_signal": True,
            "registration_effectiveness_only": True,
            "merger_closing_verified": False, "share_class_approved": False,
            "production_eligible": False}


def build_review_ledger(review: list[dict]) -> list[dict]:
    """Preserve A5 decisions; signal new investigation without auto promotion."""
    output = []
    for r in review:
        is_txse = r["original_reason"] == "UNKNOWN_EXCHANGE_CODE"
        is_lien = r["symbol"] == "LIEN"
        output.append({
            "policy_version": POLICY_VERSION,
            "as_of": MERGER_AS_OF,
            "listing_source": r["source"],
            "symbol": r["symbol"], "mic": r["mic"],
            "issuer_cik_candidate": (r.get("issuer_match_candidate") or {}).get("cik_candidate"),
            "original_a5_decision": "REVIEW_REQUIRED",
            "original_a5_reason": r["original_reason"],
            "a5i_decision": "REVIEW_REQUIRED",
            "scope_decision_proposed": "OUT_OF_SCOPE_TXSE" if is_txse else None,
            "review_flags": (["LIEN_REFI_MERGER_PENDING_FACTUAL_REVIEW"]
                             if is_lien else []),
            "issuer_legal_status_approved": False,
            "listed_security_class_approved": False,
            "source_listing_sha256": r["listing_evidence_sha256"],
            "source_sec_sha256": r["sec_evidence_sha256"],
            "production_eligible": False,
            "evidence_gates": (
                ["CORPORATE_EVENT_OUTCOME", "N54A_N54C_LEGAL_STATUS",
                 "LISTED_SECURITY_ID", "POINT_IN_TIME_KNOWN_AT", "POLICY_APPROVAL"]
                if is_lien else
                ["SOURCE_SCOPE_APPROVAL"] if is_txse else
                ["OFFICIAL_SECURITY_TYPE", "SHARE_CLASS", "POINT_IN_TIME_KNOWN_AT",
                 "POLICY_APPROVAL"]
            ),
        })
    return output


def run(a4: Path, a5: Path, a5h: Path, out: Path, *, agent: str,
        fetcher=fetch_sec_file, clock=lambda: datetime.now(timezone.utc)) -> dict:
    validate_user_agent(agent)
    inputs = load_sources(a4, a5, a5h)
    out.mkdir(parents=True, exist_ok=False)
    docs = []
    errors = []
    effect = inputs["effect"]
    sources = [
        {"label": "LIEN_SEC_EFFECT_XML", "url": effect["primary_document_url"],
         "cik": LIEN_CIK, "accession": EFFECT_ACC, "cap": MAX_EFFECT_BYTES},
        {"label": "REFI_SEC_10Q_CLASS", "url": REFI_Q_URL, "cik": REFI_CIK,
         "accession": REFI_Q_ACC, "cap": MAX_10Q_BYTES},
    ]
    for item in sources:
        try:
            raw = fetcher(item["url"], agent, cap=item["cap"], cik=item["cik"],
                          accession=item["accession"])
            if item["label"] == "LIEN_SEC_EFFECT_XML":
                # Preserve the official SEC response for audit even if its
                # format is unexpected. Unverified bytes never gain approval.
                (out / f"QUARANTINE_EFFECT_{sha256(raw).hexdigest()}.source").write_bytes(raw)
                inspected = inspect_effect(raw)
            else:
                inspected = inspect_financial(raw, expected_tickers=["REFI"])
                if not inspected["listed_security_row_candidates"][0]["row_evidence_present"]:
                    raise DecisionLedgerError("REFI 10-Q missing Nasdaq common stock ticker row")
            at = clock()
            if at.tzinfo is None or at.utcoffset() is None:
                raise DecisionLedgerError("Source retrieved_at lacks timezone")
            filename = f"{item['label']}-{inspected['source_sha256'] if 'source_sha256' in inspected else inspected['sha256']}.source"
            (out / filename).write_bytes(raw)
            docs.append({"label": item["label"], "url": item["url"],
                         "cik": item["cik"], "accession": item["accession"],
                         "retrieved_at": at.isoformat(),
                         "raw_file": filename, "status": "SOURCE_CAPTURED_REVIEW_ONLY",
                         "signals": inspected, "production_eligible": False})
        except (ValueError, OSError, TimeoutError) as exc:
            errors.append({"label": item["label"], "url": item["url"],
                           "error": f"{type(exc).__name__}: {exc}"[:220]})
            docs.append({"label": item["label"], "url": item["url"],
                         "status": "SOURCE_NOT_VERIFIED", "production_eligible": False})
    review_ledger = build_review_ledger(inputs["a5_reviews"])
    refi_listing = inputs["a4_rows"]["REFI"]
    standalone_merger_ledger = [
        {"symbol": symbol, "cik": cik, "as_of": MERGER_AS_OF,
         "policy_version": POLICY_VERSION, "mic": inputs["a4_rows"][symbol]["mic"],
         "a4_original_decision": inputs["a4_rows"][symbol]["decision"],
         "evidence_overlay": "HOLD_FOR_CORPORATE_EVENT_AND_STATUS_REVIEW",
         "issuer_legal_status": "NOT_APPROVED",
         "share_class_security_id": "NOT_APPROVED",
         "voting_result": "NOT_ESTABLISHED",
         "merger_completion": "NOT_ESTABLISHED",
         "n54a_bdc_election": "NOT_ESTABLISHED" if symbol == "REFI" else "HISTORICAL_ELECTION_REVIEW_ONLY",
         "listing_name": inputs["a4_rows"][symbol]["name"],
         "listed_common_stock_candidate": True,
         "source_evidence": ["A4_NASDAQ_DIRECTORY", "A5H_SEC_SUBMISSIONS",
                             "A5H_N14_PROXY"] + (
                                 ["A5I_REFI_10Q" if any(d["label"] == "REFI_SEC_10Q_CLASS"
                                   and d["status"] == "SOURCE_CAPTURED_REVIEW_ONLY"
                                   for d in docs) else "REFI_10Q_SOURCE_UNVERIFIED"]
                                 if symbol == "REFI" else ["A5D_N54A", "A5E_10Q"]),
         "known_at_2026_10_14_established": False,
         "production_eligible": False,
         "explicit_release_hold": True}
        for symbol, cik in (("LIEN", LIEN_CIK), ("REFI", REFI_CIK))
    ]
    ledger = {
        "status": "EVIDENCE_LEDGER_REVIEW_ONLY" if not errors else "EVIDENCE_LEDGER_PARTIAL_REVIEW_ONLY",
        "version": POLICY_VERSION, "as_of": MERGER_AS_OF,
        "sources": {
            "a4_directory_sha256": A4_REVIEW_HASH,
            "a4_nasdaq_sha256": A4_NASDAQ_HASH,
            "a5_review_sha256": A5_INSTRUMENT_HASH,
            "a5h_report_sha256": A5H_REPORT_HASH,
        },
        "original_a4_counts_unchanged": COUNTS,
        "a5_review_total": EXPECTED_REVIEW,
        "a5_review_counts": dict(sorted(Counter(
            r["original_a5_reason"] for r in review_ledger).items())),
        "still_review_required": len(review_ledger),
        "txse_scope_exclusion_proposals_not_approved": 10,
        "REFI_is_original_provisional_include_not_in_1010": True,
        "REFI_separate_corporate_event_hold": True,
        "auto_promoted": 0, "issuer_bdc_approvals": 0,
        "share_class_security_id_approvals": 0, "production_eligible": False,
        "production_approvals": 0, "source_failures": errors,
        "extra_sec_document_evidence": docs,
        "merger_company_evidence_overlays": standalone_merger_ledger,
        "a5_instrument_review_ledger": review_ledger,
        "human_review_complete": False,
    }
    (out / "a5i-decision-ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {k: v for k, v in ledger.items()
               if k not in {"a5_instrument_review_ledger",
                            "extra_sec_document_evidence", "merger_company_evidence_overlays"}}
    (out / "a5i-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return ledger


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a4-artifact", type=Path, required=True)
    p.add_argument("--a5-artifact", type=Path, required=True)
    p.add_argument("--a5h-artifact", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        result = run(args.a4_artifact, args.a5_artifact, args.a5h_artifact, args.output,
                     agent=os.environ.get("SEC_USER_AGENT", ""))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"A5I_BLOCKED: {exc}")
        return 2
    return 0 if result["status"] == "EVIDENCE_LEDGER_REVIEW_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
