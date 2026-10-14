"""Capture the two official HTTPS directories into a new immutable run folder."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .directory import DirectoryError, parse_directory, review_pair

URLS = {source: f"https://www.nasdaqtrader.com/dynamic/SymDir/{source}.txt"
        for source in ("nasdaqlisted", "otherlisted")}
MAX_BYTES = 10 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DirectoryError("Unexpected redirect; source URL requires review")


def fetch(url: str) -> bytes:
    if url not in URLS.values():
        raise DirectoryError("Unapproved source URL")
    request = Request(url, headers={"User-Agent": "LabyrinthMomentumUSV2/0.1 (reference-data-audit)"})
    with build_opener(NoRedirect()).open(request, timeout=30) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise DirectoryError("Response exceeds capture limit")
    return raw


def capture_pair(output: Path, *, fetcher=fetch, clock=lambda: datetime.now(timezone.utc)) -> dict:
    """Never falls back to another provider; partial/invalid captures cannot pass."""
    output.mkdir(parents=True, exist_ok=False)
    directories, receipts, errors = [], [], []
    for source, url in URLS.items():
        try:
            raw = fetcher(url)
            retrieved = clock()
            digest = hashlib.sha256(raw).hexdigest()
            path = output / f"{source}-{digest}.txt"
            path.write_bytes(raw)
            receipt = {"source": source, "url": url, "path": str(path.resolve()),
                       "sha256": digest, "retrieved_at": retrieved.isoformat()}
            (output / f"{source}.json").write_text(json.dumps(receipt, indent=2) + "\n")
            receipts.append(receipt)
            directories.append(parse_directory(raw, source, retrieved_at=retrieved))
        except (OSError, ValueError) as exc:
            errors.append({"source": source, "error": str(exc)})
    if not errors:
        try:
            review_pair(*directories)
        except DirectoryError as exc:
            errors.append({"source": "pair", "error": str(exc)})
    result = {"status": "SOURCE_REJECTED" if errors else "CAPTURE_VALIDATED",
              "production_eligible": False, "receipts": receipts, "errors": errors}
    (output / "capture.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    result = capture_pair(parser.parse_args().output)
    print(json.dumps(result, indent=2))
    return 2 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
