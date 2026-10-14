"""Reconcile an immutable SEC capture with an existing provisional directory review."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .sec import SecSnapshotError, enrich_review_with_sec, parse_sec_exchange_snapshot
from .sec_capture import SEC_SOURCE_URL


def load_verified_sec_capture(capture_report_path: Path):
    """Read only successful capture receipts; reject altered bytes or metadata."""
    result = json.loads(capture_report_path.read_text(encoding="utf-8"))
    receipt = result.get("receipt")
    if (result.get("status") != "CAPTURE_VALIDATED"
            or result.get("production_eligible") is not False
            or not isinstance(receipt, dict)
            or receipt.get("validated") is not True
            or receipt.get("source_url") != SEC_SOURCE_URL):
        raise SecSnapshotError("SEC capture receipt is missing, rejected or unapproved")
    retrieved_at = datetime.fromisoformat(receipt["retrieved_at"])
    path = Path(receipt["path"])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt["sha256"]:
        raise SecSnapshotError("SEC capture checksum mismatch")
    sec = parse_sec_exchange_snapshot(raw, retrieved_at=retrieved_at)
    if receipt.get("rows") != len(sec.companies):
        raise SecSnapshotError("SEC capture row count mismatch")
    return sec


def build_audit_summary(report: dict) -> dict:
    """Never describe unmatched SEC tickers as delisted or approve candidates."""
    rows = report["rows"]
    match_counts = report["sec_enrichment"]["match_counts"]
    if sum(match_counts.values()) != len(rows):
        raise SecSnapshotError("SEC reconciliation incomplete")
    return {
        "status": "REVIEW_ONLY",
        "production_eligible": False,
        "directory_total": len(rows),
        "directory_counts_after_sec": report["counts"],
        "sec_match_counts": match_counts,
        "sec_source_sha256": report["sec_enrichment"]["sha256"],
        "sec_retrieved_at": report["sec_enrichment"]["retrieved_at"],
        "directory_sources": report.get("sources", []),
        "a1_reference_snapshot": {
            "date": "2026-10-14",
            "total": 13287,
            "include_candidates": 4556,
            "exclude": 7721,
            "review_required": 1010,
        },
        "a1_same_total": len(rows) == 13287,
        "a1_snapshot_identity_proven": False,
        "note": "Reference A1 counts are not current SEC coverage; compare source hashes and"
                " timestamps before drawing snapshot conclusions. SEC data cannot approve a security.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sec-capture", type=Path, required=True,
                        help="Path to validated SEC capture.json; never raw JSON alone")
    parser.add_argument("--review-json", type=Path, required=True,
                        help="Complete directory review.json (not the summary audit JSON)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        sec = load_verified_sec_capture(args.sec_capture)
        review = json.loads(args.review_json.read_text(encoding="utf-8"))
        report = enrich_review_with_sec(review, sec)
        summary = build_audit_summary(report)
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "sec-review.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (args.output / "sec-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"SEC_REVIEW_BLOCKED: {exc}")
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
