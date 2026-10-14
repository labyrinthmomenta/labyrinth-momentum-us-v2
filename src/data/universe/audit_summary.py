"""Offline evidence-only audit: compare official Nasdaq bytes with saved A1 hashes."""
from collections import Counter
from pathlib import Path
import argparse
import json


def build_audit(original, enriched, a1):
    if (original.get("status") != "REVIEW_ONLY"
            or enriched.get("status") != "REVIEW_ONLY"
            or original.get("production_eligible") is not False
            or enriched.get("production_eligible") is not False):
        raise ValueError("Must have non-production review inputs")
    prior, latest = original.get("rows"), enriched.get("rows")
    if not isinstance(prior, list) or not isinstance(latest, list) or len(prior) != len(latest):
        raise ValueError("Different or missing review row counts")
    matrix, reasons = Counter(), Counter()
    for old, new in zip(prior, latest):
        if (old["source"], old["symbol"], old["mic"]) != (new["source"], new["symbol"], new["mic"]):
            raise ValueError("Issuer enrichment changed directory row identity/order")
        if old["production_eligible"] is not False or new["production_eligible"] is not False:
            raise ValueError("A production-eligible row was detected")
        match = new.get("issuer_match", {}).get("status")
        if match not in {"SEC_CIK_CANDIDATE", "SEC_NOT_FOUND", "SEC_IDENTITY_AMBIGUOUS"}:
            raise ValueError("Incomplete SEC status")
        matrix[(old["decision"], match)] += 1
        if old["decision"] == "REVIEW_REQUIRED":
            reasons[(old["reason"], match)] += 1
    sources = {r["source"]: r["sha256"] for r in original["sources"]}
    expected = {r["source"]: r["sha256"] for r in a1["sources"]}
    if set(sources) != {"nasdaqlisted", "otherlisted"} or set(expected) != set(sources):
        raise ValueError("Expected complete official directory pair")
    if sum(original["counts"].values()) != len(prior):
        raise ValueError("Source classification count mismatch")
    identical = sources == expected
    if identical and (len(prior) != a1["total"] or original["counts"] != a1["counts"]):
        raise ValueError("A1 hash matches but counts differ")
    kinds = ("INCLUDE", "EXCLUDE", "REVIEW_REQUIRED")
    states = ("SEC_CIK_CANDIDATE", "SEC_NOT_FOUND", "SEC_IDENTITY_AMBIGUOUS")
    result = {
        "status": "REVIEW_ONLY", "production_eligible": False,
        "a1_byte_identical": identical,
        "a1_reference_total": a1["total"], "a1_sha256": expected,
        "observed_total": len(prior), "observed_sha256": sources,
        "observed_counts": original["counts"],
        "directory_sources": original["sources"],
        "sec_sha256": enriched["sec_enrichment"]["sha256"],
        "sec_retrieved_at": enriched["sec_enrichment"]["retrieved_at"],
        "sec_company_rows": enriched["sec_enrichment"]["rows"],
        "sec_match_by_initial_decision": {
            kind: {state: matrix[(kind, state)] for state in states} for kind in kinds},
        "sec_match_by_initial_review_reason": {
            reason: {state: reasons[(reason, state)] for state in states}
            for reason in sorted({key[0] for key in reasons})},
        "sample_unmatched_nonexcluded": [
            {"symbol": old["symbol"], "mic": old["mic"], "reason": old["reason"]}
            for old, new in zip(prior, latest)
            if old["decision"] != "EXCLUDE"
            and new["issuer_match"]["status"] == "SEC_NOT_FOUND"
        ][:15],
        "sample_ambiguous_nonexcluded": [
            {"symbol": old["symbol"], "mic": old["mic"], "reason": old["reason"]}
            for old, new in zip(prior, latest)
            if old["decision"] != "EXCLUDE"
            and new["issuer_match"]["status"] == "SEC_IDENTITY_AMBIGUOUS"
        ][:15],
        "limitations": [
            "SEC CIK only suggests an issuer, not a security/share class.",
            "SEC is not authoritative proof of type or inclusion.",
            "Equal counts do not prove identical snapshots; compare source SHA256.",
            "No price/volume calculation, production universe, or publication.",
        ],
    }
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory-review", type=Path, required=True)
    p.add_argument("--sec-review", type=Path, required=True)
    p.add_argument("--a1-baseline", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        data = [json.loads(path.read_text(encoding="utf-8")) for path in (
            args.directory_review, args.sec_review, args.a1_baseline)]
        result = build_audit(*data)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"A4_AUDIT_BLOCKED: {exc}")
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
