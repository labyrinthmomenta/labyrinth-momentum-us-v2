"""A5b: compare provisional A5 reviews with *separate* SEC fund class registry.

No automatic inclusion/exclusion, security_id linking, or historical classification.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import json

from .a5_review import A4_HASHES
from .fund_registry import load_funds

REASONS = {
    "FINANCIAL_STATUS_REVIEW": 268,
    "FUND_NAME_REQUIRES_TYPE_EVIDENCE": 297,
    "SPAC_BDC_OR_FINANCIAL_REVIEW": 307,
    "TYPE_UNCONFIRMED": 128,
    "UNKNOWN_EXCHANGE_CODE": 10,
}


def name_clues(name: str) -> list[str]:
    """Non-exclusive directory display-name cues, never legal type evidence."""
    lower = name.casefold()
    patterns = [
        ("EXPLICIT_CLOSED_END_FUND", "closed end fund"),
        ("COMMON_STOCK_WORDING", "common stock"),
        ("COMMON_SHARES_WORDING", "common share"),
        ("REIT_WORDING", "reit"),
        ("ACQUISITION_WORDING", "acquisition"),
        ("BDC_WORDING", " bdc"),
        ("TRUST_WORDING", "trust"),
    ]
    return [key for key, phrase in patterns if phrase in lower]


def enrich_fund_queue(instrument_review: list[dict], snapshot) -> dict:
    if len(instrument_review) != 1010:
        raise ValueError("Only complete frozen A5 queue is valid")
    lookup = defaultdict(list)
    for item in snapshot.classes:
        lookup[item.ticker].append(item)
    counts, by_reason, clues, entries = Counter(), defaultdict(Counter), Counter(), []
    original_reasons = Counter()
    for row in instrument_review:
        reason = row.get("original_reason")
        if (reason not in REASONS or row.get("production_eligible") is not False
                or row.get("security_type_approved") is not False
                or row.get("listing_evidence_sha256") != A4_HASHES.get(row.get("source"))
                or row.get("sec_evidence_sha256") != A4_HASHES["sec"]):
            raise ValueError("Unapproved, altered or unsupported A5 row")
        original_reasons[reason] += 1
        ticker, name = row["symbol"], row["name"]
        if not isinstance(ticker, str) or not isinstance(name, str):
            raise ValueError("A5 record missing ticker/name")
        matching = lookup.get(ticker, [])
        if not matching:
            status = "NOT_IN_SEC_FUND_TICKER_FILE"
        elif len(matching) == 1:
            status = "SEC_FUND_CLASS_CANDIDATE"
        else:
            status = "MULTIPLE_SEC_FUND_CLASSES_REVIEW"
        flags = name_clues(name)
        counts[status] += 1
        by_reason[reason][status] += 1
        clues.update(flags)
        entries.append({
            "ticker": ticker, "security_name": name, "original_review_reason": reason,
            "mic": row["mic"], "directory_name_clues": flags,
            "sec_fund_status": status,
            "fund_class_candidates": [
                {"registrant_cik": x.cik, "series_id": x.series_id,
                 "class_id": x.class_id, "ticker": x.ticker}
                for x in matching
            ],
            "a5_issuer_cik_candidate": row.get("issuer_match_candidate", {}).get("cik_candidate"),
            "fund_registry_source_sha256": snapshot.sha256,
            "a4_listing_source_sha256": row["listing_evidence_sha256"],
            "fund_evidence_retrieved_at": snapshot.retrieved_at.isoformat(),
            "classification_decision": "REVIEW_REQUIRED",
            "approved_security_id": None, "production_eligible": False,
            "next_evidence_needed": (
                ["VERIFY_SERIES_CLASS_AND_LISTED_INSTRUMENT", "AS_OF_SOURCE_DATE"]
                if matching else ["OTHER_OFFICIAL_SECURITY_TYPE_EVIDENCE", "SEC_EDGAR_FILINGS_AS_OF_DATE"]
            ),
        })
    if original_reasons != Counter(REASONS):
        raise ValueError("A5 instrument type reason counts differ from frozen audit")
    return {
        "status": "REVIEW_ONLY", "production_eligible": False,
        "instrument_review_total": len(entries),
        "sec_fund_rows": len(snapshot.classes),
        "sec_fund_source_sha256": snapshot.sha256,
        "sec_fund_retrieved_at": snapshot.retrieved_at.isoformat(),
        "a4_sec_company_source_sha256": A4_HASHES["sec"],
        "fund_ticker_match_status_counts": dict(sorted(counts.items())),
        "fund_ticker_match_by_a5_reason": {
            reason: dict(sorted(by_reason[reason].items())) for reason in sorted(REASONS)},
        "directory_name_clues_nonexclusive": dict(sorted(clues.items())),
        "approved_instruments": 0,
        "not_in_sec_fund_registry_is_not_proof_of_common_stock": True,
        "review_entries": entries,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a5-instrument-review", type=Path, required=True)
    p.add_argument("--sec-fund-capture", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        rows = json.loads(args.a5_instrument_review.read_text(encoding="utf-8"))
        fund = load_funds(args.sec_fund_capture)
        output = enrich_fund_queue(rows, fund)
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "full-fund-evidence.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary = {k: v for k, v in output.items() if k != "review_entries"}
        (args.output / "fund-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"A5B_FUND_REVIEW_BLOCKED: {exc}")
        return 2
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
