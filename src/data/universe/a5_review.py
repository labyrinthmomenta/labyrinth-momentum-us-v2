"""A5: fail-closed, evidence-linked review of the frozen A4 official sources.

No issuer/security IDs, approved instrument decisions, tradability or publication.
Run only on the full A4 source artifact, not a current/mixed snapshot.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path

from .capture import URLS
from .directory import parse_directory, review_pair
from .sec import parse_sec_exchange_snapshot
from .sec_capture import SEC_SOURCE_URL

A4_HASHES = {
    "nasdaqlisted": "2dc5b607a42c3eefe9cf6f7d6e681c30b8fb55bb51ae04d998cdf51af02d6694",
    "otherlisted": "12deeb989a1b515304eda04318a0af1db127ff6340d1055329c62d9a5cbcde28",
    "sec": "c90bb2d57bb62fae8171abf37b7eb040917f9fb6b5238e6d5dc028baaec318e5",
}
A4_COUNTS = {"INCLUDE": 4556, "EXCLUDE": 7721, "REVIEW_REQUIRED": 1010}
OFFICIAL = {
    "nasdaq_definitions": "https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs",
    "nasdaq_txse_announcement": "https://www.nasdaqtrader.com/TraderNews.aspx?id=DTN2026-10",
    "txse_id_codes": "https://www.txse.com/regulations/id-codes",
    "sec_ticker_exchange": SEC_SOURCE_URL,
    "nyse_security_master": "https://www.nyse.com/market-data/reference",
}


def _read_raw(folder: Path, name: str, expected: str) -> bytes:
    path = folder / f"{name}-{expected}.txt"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"Raw official source checksum mismatch: {name}")
    return raw


def reconstruct_a4(directory_capture: Path, sec_capture: Path, a4_review: Path):
    """Ignore nonportable absolute receipt paths; use pinned hashes inside artifact."""
    cap = json.loads((directory_capture / "capture.json").read_text(encoding="utf-8"))
    if cap.get("status") != "CAPTURE_VALIDATED" or cap.get("production_eligible") is not False:
        raise ValueError("Nasdaq capture is not validated")
    directories = []
    receipts = {x["source"]: x for x in cap.get("receipts", [])}
    if set(receipts) != {"nasdaqlisted", "otherlisted"}:
        raise ValueError("Nasdaq official pair incomplete")
    for name in ("nasdaqlisted", "otherlisted"):
        r = receipts[name]
        if r.get("url") != URLS[name] or r.get("sha256") != A4_HASHES[name]:
            raise ValueError("Unexpected Nasdaq source URL or snapshot SHA")
        ts = datetime.fromisoformat(r["retrieved_at"])
        directories.append(parse_directory(_read_raw(directory_capture, name, A4_HASHES[name]),
                                           name, retrieved_at=ts))
    report = review_pair(*directories)
    stored = json.loads(a4_review.read_text(encoding="utf-8"))
    if (report["total"] != 13287 or report["counts"] != A4_COUNTS
            or stored.get("counts") != report["counts"]
            or stored.get("sources") != report["sources"]
            or stored.get("status") != "REVIEW_ONLY"):
        raise ValueError("A4 directory review metadata diverged")
    fields = ("source", "symbol", "name", "mic", "decision", "reason", "production_eligible")
    if len(stored.get("rows", [])) != len(report["rows"]) or any(
            tuple(a[x] for x in fields) != tuple(b[x] for x in fields)
            for a, b in zip(stored["rows"], report["rows"])):
        raise ValueError("A4 directory review rows diverged from official bytes")

    s = json.loads((sec_capture / "capture.json").read_text(encoding="utf-8"))
    receipt = s.get("receipt") or {}
    if (s.get("status") != "CAPTURE_VALIDATED" or s.get("production_eligible") is not False
            or receipt.get("validated") is not True
            or receipt.get("source_url") != SEC_SOURCE_URL
            or receipt.get("sha256") != A4_HASHES["sec"]):
        raise ValueError("SEC source receipt is rejected or has unexpected snapshot SHA")
    path = sec_capture / f"company_tickers_exchange-{A4_HASHES['sec']}.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != A4_HASHES["sec"]:
        raise ValueError("SEC raw bytes differ from receipt")
    sec = parse_sec_exchange_snapshot(raw,
                                       retrieved_at=datetime.fromisoformat(receipt["retrieved_at"]))
    if len(sec.companies) != receipt.get("rows") or len(sec.companies) != 10451:
        raise ValueError("SEC row count mismatch")
    return report, sec


def variants_for_review(symbol: str) -> tuple[str, ...]:
    """Only *suggest* exact format variants; no automatic namespace normalization."""
    values = []
    if "." in symbol:
        values.append(symbol.replace(".", "-"))
    if "$" in symbol:
        values.append(symbol.replace("$", "-P"))
    return tuple(dict.fromkeys(x for x in values if x != symbol))


def triage_evidence(reason: str) -> list[str]:
    table = {
        "FINANCIAL_STATUS_REVIEW": ["NASDAQ_FINANCIAL_STATUS_RESOLUTION", "SECURITY_TYPE_AND_CLASS"],
        "FUND_NAME_REQUIRES_TYPE_EVIDENCE": ["OFFICIAL_REIT_VS_FUND_SECURITY_TYPE", "SHARE_CLASS"],
        "SPAC_BDC_OR_FINANCIAL_REVIEW": ["SPAC_BDC_EXPLICIT_SCOPE_DECISION", "OFFICIAL_SECURITY_TYPE"],
        "TYPE_UNCONFIRMED": ["OFFICIAL_SECURITY_TYPE", "SHARE_CLASS"],
        "UNKNOWN_EXCHANGE_CODE": ["NASDAQ_TXSE_F_CODE", "TXSE_VENUE_SCOPE_POLICY"],
    }
    return table.get(reason, ["OFFICIAL_SECURITY_TYPE", "LISTING_IDENTITY"])


def evaluate_a5(review: dict, sec) -> dict:
    """Separate verified venue, tentative issuer link and unresolved security type."""
    if (review.get("status") != "REVIEW_ONLY" or review.get("production_eligible") is not False
            or review.get("total") != len(review.get("rows", []))):
        raise ValueError("Only complete provisional directory reviews accepted")
    by_ticker = defaultdict(list)
    for company in sec.companies:
        by_ticker[company.ticker].append(company)
    venue_rows, type_rows = [], []
    for row in review["rows"]:
        if row.get("production_eligible") is not False:
            raise ValueError("Forbidden production-approved row")
        symbol, mic, decision, reason = (row[k] for k in ("symbol", "mic", "decision", "reason"))
        exchange = row["evidence"].get("Exchange") if row["source"] == "otherlisted" else None
        matches = by_ticker.get(symbol, [])
        exact = [x for x in matches if x.mic == mic and mic is not None]
        if decision == "REVIEW_REQUIRED":
            txse = reason == "UNKNOWN_EXCHANGE_CODE" and exchange == "F"
            type_rows.append({
                "source": row["source"], "symbol": symbol, "mic": mic,
                "original_reason": reason, "original_decision": decision,
                "evidence_needed": triage_evidence(reason),
                "a5_proposed_scope": "OUT_OF_SCOPE_TXSE" if txse else "HOLD_FOR_TYPE_EVIDENCE",
                "production_eligible": False,
                "listing_evidence_sha256": A4_HASHES[row["source"]],
                "sec_evidence_sha256": A4_HASHES["sec"],
            })
        if decision == "EXCLUDE" or len(exact) == 1:
            continue
        if len(exact) > 1:
            raise ValueError(f"Unexpected multiple exact issuer candidates for {symbol}")
        if mic == "XASE" and exchange == "A":
            nyse = [x for x in matches if x.exchange == "NYSE"]
            label = "XASE_VENUE_VERIFIED_SEC_NYSE_LABEL" if len(nyse) == 1 else "XASE_VENUE_VERIFIED_ISSUER_UNRESOLVED"
            proposals = [{"sec_ticker": x.ticker, "cik_candidate": x.cik,
                          "sec_exchange_label": x.exchange} for x in nyse]
        elif mic == "XNYS" and exchange == "N":
            variants = [
                {"sec_ticker": x.ticker, "cik_candidate": x.cik, "sec_exchange_label": x.exchange}
                for v in variants_for_review(symbol)
                for x in by_ticker.get(v, []) if x.exchange == "NYSE"
            ]
            proposals = list({(x["sec_ticker"], x["cik_candidate"]): x for x in variants}.values())
            label = ("XNYS_SYMBOL_FORMAT_CANDIDATE_REVIEW"
                     if len(proposals) == 1 else "XNYS_ISSUER_UNRESOLVED")
        elif mic == "XNAS":
            label, proposals = "XNAS_SEC_NOT_FOUND", []
        elif exchange == "F" and mic is None:
            label = "TXSE_F_VERIFIED_OUT_OF_SCOPE"
            proposals = [{"sec_ticker": x.ticker, "cik_candidate": x.cik,
                          "sec_exchange_label": x.exchange}
                         for x in matches if x.exchange == "TXSE"]
        else:
            label, proposals = "UNKNOWN_VENUE_NEEDS_EVIDENCE", []
        venue_rows.append({
            "source": row["source"], "symbol": symbol, "name": row["name"], "mic": mic,
            "exchange_code": exchange, "original_decision": decision, "reason": reason,
            "a5_venue_finding": label,
            "possible_sec_issuer_links": proposals,
            "issuer_match_approved": False, "security_type_approved": False,
            "production_eligible": False,
            "listing_evidence_sha256": A4_HASHES[row["source"]],
            "sec_evidence_sha256": A4_HASHES["sec"],
        })
    venue_counts = Counter(x["a5_venue_finding"] for x in venue_rows)
    original_reviews = Counter(x["original_reason"] for x in type_rows)
    if (len(venue_rows) != 309 or len(type_rows) != 1010
            or sum(venue_counts.values()) != 309
            or original_reviews != Counter({
                "FINANCIAL_STATUS_REVIEW": 268, "FUND_NAME_REQUIRES_TYPE_EVIDENCE": 297,
                "SPAC_BDC_OR_FINANCIAL_REVIEW": 307, "TYPE_UNCONFIRMED": 128,
                "UNKNOWN_EXCHANGE_CODE": 10})):
        raise ValueError("A4 coverage mismatch; no partial/changed audit allowed")
    if venue_counts != Counter({
        "XASE_VENUE_VERIFIED_SEC_NYSE_LABEL": 261,
        "XNYS_SYMBOL_FORMAT_CANDIDATE_REVIEW": 31,
        "XNYS_ISSUER_UNRESOLVED": 1,
        "XNAS_SEC_NOT_FOUND": 6,
        "TXSE_F_VERIFIED_OUT_OF_SCOPE": 10,
    }):
        raise ValueError("A4 venue findings deviate from expected input; investigate before audit")
    return {
        "status": "REVIEW_ONLY",
        "production_eligible": False,
        "a4_baseline": {"directory_total": 13287, "counts": A4_COUNTS, "sha256": A4_HASHES,
                        "sec_rows": len(sec.companies), "sec_retrieved_at": sec.retrieved_at.isoformat()},
        "venue_exception_total": len(venue_rows), "venue_findings": dict(sorted(venue_counts.items())),
        "instrument_review_total": len(type_rows),
        "instrument_review_reasons": dict(sorted(original_reviews.items())),
        "a5_proposed_txse_scope_exclusions": 10,
        "unresolved_instrument_type_reviews": 1000,
        "approved_security_ids": 0, "approved_issuer_matches": 0,
        "official_reference_urls": OFFICIAL,
        "venue_exceptions": venue_rows,
        "instrument_reviews": type_rows,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a4-artifact-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        a4 = args.a4_artifact_dir
        directory, sec = reconstruct_a4(
            a4 / "nasdaq-capture", a4 / "sec-capture", a4 / "directory-review" / "review.json")
        result = evaluate_a5(directory, sec)
        args.output.mkdir(parents=True, exist_ok=False)
        for name, data in (("summary", {k: v for k, v in result.items()
                                      if k not in ("venue_exceptions", "instrument_reviews")}),
                           ("venue-exceptions", result["venue_exceptions"]),
                           ("instrument-review", result["instrument_reviews"])):
            (args.output / f"{name}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"A5_EVIDENCE_BLOCKED: {exc}")
        return 2
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("venue_exceptions", "instrument_reviews")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
