"""Offline review of captured official payloads; never publishes or assigns IDs."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from .directory import DirectoryError, parse_directory, review_pair


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # A fresh directory prevents failed runs leaving old CSVs beside new metadata.
    args.output.mkdir(parents=True, exist_ok=False)
    sources, captures, errors = [], [], []
    for source in ("nasdaqlisted", "otherlisted"):
        try:
            meta = json.loads((args.raw_dir / f"{source}.json").read_text())
            raw = Path(meta["path"]).read_bytes()
            import hashlib
            if hashlib.sha256(raw).hexdigest() != meta["sha256"]:
                raise DirectoryError("Capture checksum mismatch")
            captures.append(meta)
            sources.append(parse_directory(raw, source, retrieved_at=datetime.fromisoformat(meta["retrieved_at"])))
        except (OSError, ValueError, KeyError) as exc:
            errors.append({"source": source, "error": str(exc)})
    if not errors:
        try:
            report = review_pair(*sources)
        except DirectoryError as exc:
            errors.append({"source": "pair", "error": str(exc)})
    if errors:
        report = {"status": "SOURCE_REJECTED", "production_eligible": False,
                  "counts": None, "errors": errors}
    report["captures"] = captures
    (args.output / "review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if not errors:
        with (args.output / "review.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["source", "symbol", "name", "mic", "decision", "reason"], extrasaction="ignore")
            writer.writeheader()
            writer.writerows(report["rows"])
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False, indent=2))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
