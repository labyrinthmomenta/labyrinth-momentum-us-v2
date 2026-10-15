"""SEC fund class registry evidence, not an instrument-type approval.

SEC company_tickers_mf.json maps fund registrant CIK, series ID, class ID and
ticker. It is not a full listed-security master and is not point-in-time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener
import argparse
import hashlib
import json
import re

from .sec_capture import NoRedirect, validate_user_agent

SOURCE = "https://www.sec.gov/files/company_tickers_mf.json"
FIELDS = ["cik", "seriesId", "classId", "symbol"]
MAX_BYTES = 25 * 1024 * 1024


class FundEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class FundClass:
    cik: str
    series_id: str
    class_id: str
    ticker: str


@dataclass(frozen=True)
class FundSnapshot:
    sha256: str
    retrieved_at: datetime
    classes: tuple[FundClass, ...]


def parse_funds(raw: bytes, retrieved_at: datetime) -> FundSnapshot:
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise FundEvidenceError("retrieved_at must be timezone-aware")
    if len(raw) > MAX_BYTES:
        raise FundEvidenceError("SEC fund source oversized")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise FundEvidenceError("Malformed SEC fund JSON") from exc
    if not isinstance(data, dict) or data.get("fields") != FIELDS:
        raise FundEvidenceError("Unexpected SEC fund JSON schema")
    rows = data.get("data")
    if not isinstance(rows, list) or not rows:
        raise FundEvidenceError("SEC fund data missing or empty")
    classes, seen = [], set()
    for row in rows:
        if not isinstance(row, list) or len(row) != 4:
            raise FundEvidenceError("SEC fund row invalid")
        cik, series, klass, symbol = row
        if type(cik) is int and cik > 0:
            num = cik
        elif isinstance(cik, str) and cik.isascii() and cik.isdecimal() and cik:
            num = int(cik)
        else:
            raise FundEvidenceError("SEC fund CIK invalid")
        if not 1 <= num <= 9999999999:
            raise FundEvidenceError("SEC fund CIK outside range")
        if (not isinstance(series, str) or not re.fullmatch(r"S[0-9]{9}", series)
                or not isinstance(klass, str) or not re.fullmatch(r"C[0-9]{9}", klass)
                or not isinstance(symbol, str) or symbol != symbol.strip()):
            raise FundEvidenceError("SEC fund class/series/ticker invalid")
        key = (num, series, klass, symbol)
        if key in seen:
            raise FundEvidenceError("Duplicate SEC fund record")
        seen.add(key)
        classes.append(FundClass(f"{num:010d}", series, klass, symbol))
    return FundSnapshot(hashlib.sha256(raw).hexdigest(), retrieved_at, tuple(classes))


def fetch_funds(agent: str) -> bytes:
    agent = validate_user_agent(agent)
    req = Request(SOURCE, headers={"User-Agent": agent, "Accept": "application/json",
                                   "Accept-Encoding": "identity"})
    with build_opener(NoRedirect()).open(req, timeout=30) as response:
        if response.geturl() != SOURCE:
            raise FundEvidenceError("Unexpected redirect/source location")
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise FundEvidenceError("Fund response over size cap")
    return raw


def capture_funds(output: Path, user_agent: str, *, fetcher=fetch_funds,
                  clock=lambda: datetime.now(timezone.utc)) -> dict:
    validate_user_agent(user_agent)
    output.mkdir(parents=True, exist_ok=False)
    receipt = None
    errors = []
    try:
        raw = fetcher(user_agent)
        timestamp = clock()
        digest = hashlib.sha256(raw).hexdigest()
        (output / f"company_tickers_mf-{digest}.json").write_bytes(raw)
        receipt = {"url": SOURCE, "sha256": digest,
                   "retrieved_at": timestamp.isoformat(), "validated": False}
        parsed = parse_funds(raw, timestamp)
        receipt.update(validated=True, classes=len(parsed.classes),
                       classes_without_ticker=sum(not item.ticker for item in parsed.classes))
    except (OSError, ValueError, TimeoutError) as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    result = {"status": "CAPTURE_VALIDATED" if not errors else "SOURCE_REJECTED",
              "production_eligible": False, "receipt": receipt, "errors": errors}
    (output / "capture.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def load_funds(folder: Path) -> FundSnapshot:
    metadata = json.loads((folder / "capture.json").read_text())
    receipt = metadata.get("receipt") or {}
    if (metadata.get("status") != "CAPTURE_VALIDATED"
            or metadata.get("production_eligible") is not False
            or receipt.get("validated") is not True or receipt.get("url") != SOURCE):
        raise FundEvidenceError("Unapproved SEC fund source")
    digest = receipt["sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise FundEvidenceError("Malformed SEC fund SHA")
    raw = (folder / f"company_tickers_mf-{digest}.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise FundEvidenceError("SEC fund capture SHA mismatch")
    parsed = parse_funds(raw, datetime.fromisoformat(receipt["retrieved_at"]))
    if (receipt["classes"] != len(parsed.classes)
            or receipt.get("classes_without_ticker") != sum(not x.ticker for x in parsed.classes)):
        raise FundEvidenceError("SEC fund count mismatch")
    return parsed


def main() -> int:
    import os
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        result = capture_funds(args.output, os.environ.get("SEC_USER_AGENT", ""))
    except (ValueError, OSError) as exc:
        print(f"FUND_CAPTURE_BLOCKED: {exc}")
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "CAPTURE_VALIDATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
