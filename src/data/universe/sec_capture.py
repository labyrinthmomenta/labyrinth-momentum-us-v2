"""Explicit, bounded capture of the SEC issuer ticker-exchange reference file.

Never publishes a universe, chooses securities or writes issuer identities.
SEC requires an identifying User-Agent with a contact email. Set SEC_USER_AGENT.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .sec import MAX_SEC_BYTES, SecSnapshotError, parse_sec_exchange_snapshot

SEC_SOURCE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SecSnapshotError("SEC redirect is not approved for this capture")


def validate_user_agent(value: str) -> str:
    if (not isinstance(value, str) or not 8 <= len(value) <= 220
            or "@" not in value or any(c in value for c in "\r\n")
            or value == value.strip() == ""):
        raise SecSnapshotError("SEC_USER_AGENT must identify a contact email")
    return value


def fetch_sec(url: str, user_agent: str) -> bytes:
    """One official HTTPS request only; no retries, redirects or fallback sites."""
    if url != SEC_SOURCE_URL:
        raise SecSnapshotError("Unapproved SEC source")
    agent = validate_user_agent(user_agent)
    request = Request(url, headers={"User-Agent": agent,
                                    "Accept": "application/json",
                                    "Accept-Encoding": "identity"})
    with build_opener(NoRedirect()).open(request, timeout=30) as response:
        if response.geturl() != SEC_SOURCE_URL:
            raise SecSnapshotError("Unexpected SEC response URL")
        raw = response.read(MAX_SEC_BYTES + 1)
    if len(raw) > MAX_SEC_BYTES:
        raise SecSnapshotError("SEC download exceeds size limit")
    return raw


def capture_sec(output: Path, *, user_agent: str, fetcher=fetch_sec,
                clock=lambda: datetime.now(timezone.utc)) -> dict:
    """Save hash-addressed bytes and receipt; invalid input never produces success."""
    validate_user_agent(user_agent)
    output.mkdir(parents=True, exist_ok=False)
    errors: list[str] = []
    receipt = None
    try:
        raw = fetcher(SEC_SOURCE_URL, user_agent)
        retrieved_at = clock()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise SecSnapshotError("Capture timestamp is not timezone aware")
        digest = hashlib.sha256(raw).hexdigest()
        path = output / f"company_tickers_exchange-{digest}.json"
        path.write_bytes(raw)
        receipt = {"source_url": SEC_SOURCE_URL, "path": str(path.resolve()),
                   "sha256": digest, "retrieved_at": retrieved_at.isoformat(),
                   "validated": False}
        sec = parse_sec_exchange_snapshot(raw, retrieved_at=retrieved_at)
        receipt["validated"] = True
        receipt["rows"] = len(sec.companies)
    except (OSError, ValueError, TimeoutError) as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    report = {"status": "SOURCE_REJECTED" if errors else "CAPTURE_VALIDATED",
              "production_eligible": False, "receipt": receipt, "errors": errors}
    (output / "capture.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = capture_sec(args.output, user_agent=os.environ.get("SEC_USER_AGENT", ""))
    except (ValueError, OSError) as exc:
        print(f"SEC_CAPTURE_BLOCKED: {exc}")
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "CAPTURE_VALIDATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
