"""Review a locally available SEC file; does not fetch SEC or publish results."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .sec import enrich_review_with_sec, parse_sec_exchange_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sec-json", type=Path, required=True)
    parser.add_argument("--review-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sec = parse_sec_exchange_snapshot(args.sec_json.read_bytes(),
                                      retrieved_at=datetime.now(timezone.utc))
    report = enrich_review_with_sec(
        json.loads(args.review_json.read_text(encoding="utf-8")), sec)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "sec-review.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "counts": report["counts"],
                      "sec_enrichment": report["sec_enrichment"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
