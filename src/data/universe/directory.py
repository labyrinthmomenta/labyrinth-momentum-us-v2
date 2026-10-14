from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

POLICY_VERSION = "common-stock-directory-review-v2"
HEADERS = {
    "nasdaqlisted": ("Symbol", "Security Name", "Market Category", "Test Issue",
                     "Financial Status", "Round Lot Size", "ETF", "NextShares"),
    "otherlisted": ("ACT Symbol", "Security Name", "Exchange", "CQS Symbol",
                    "ETF", "Round Lot Size", "Test Issue", "NASDAQ Symbol"),
}


class DirectoryError(ValueError):
    pass


@dataclass(frozen=True)
class Directory:
    source: str
    sha256: str
    created_at: datetime
    retrieved_at: datetime
    rows: tuple[dict[str, str], ...]


def parse_directory(raw: bytes, source: str, *, retrieved_at: datetime,
                    max_age: timedelta = timedelta(days=4)) -> Directory:
    """Strict source validation. Four-day age is an audit tolerance, not a calendar."""
    if source not in HEADERS:
        raise DirectoryError("Unsupported source")
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise DirectoryError("retrieved_at must be timezone aware")
    if max_age <= timedelta(0):
        raise DirectoryError("max_age must be positive")
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeError as exc:
        raise DirectoryError("Invalid UTF-8") from exc
    if len(lines) < 3 or tuple(lines[0].split("|")) != HEADERS[source]:
        raise DirectoryError("Unexpected header (HTML, schema change or empty response)")
    footer = lines[-1].split("|")
    # Official otherlisted captures use six trailing pipes (seven fields),
    # while the data header has eight fields. Both known footer layouts are
    # accepted; nonempty trailing fields and arbitrary widths remain invalid.
    footer_widths = {8} if source == "nasdaqlisted" else {7, 8}
    if len(footer) not in footer_widths or any(footer[1:]):
        raise DirectoryError("Invalid footer columns")
    match = re.fullmatch(r"File Creation Time: (\d{8})(\d{2}):?(\d{2})", footer[0])
    if not match:
        raise DirectoryError("Missing or malformed creation footer")
    try:
        created = datetime.strptime("".join(match.groups()), "%m%d%Y%H%M").replace(
            tzinfo=ZoneInfo("America/New_York"))
    except ValueError as exc:
        raise DirectoryError("Invalid creation date") from exc
    age = retrieved_at - created
    if age < -timedelta(minutes=5) or age > max_age:
        raise DirectoryError("Stale or future source creation time")
    rows, symbols = [], set()
    for values in csv.reader(lines[1:-1], delimiter="|"):
        if len(values) != len(HEADERS[source]):
            raise DirectoryError("Malformed row width")
        row = dict(zip(HEADERS[source], values))
        symbol = values[0]
        if not symbol or symbol != symbol.strip() or not row["Security Name"].strip():
            raise DirectoryError("Missing or malformed symbol/name")
        if symbol in symbols:
            raise DirectoryError(f"Duplicate symbol: {symbol}")
        symbols.add(symbol)
        for flag in ("ETF", "Test Issue") + (("NextShares",) if source == "nasdaqlisted" else ()):
            if row[flag] not in {"Y", "N"}:
                raise DirectoryError(f"Unknown {flag} value")
        if not row["Round Lot Size"].isdigit() or int(row["Round Lot Size"]) <= 0:
            raise DirectoryError("Invalid round lot size")
        if source == "nasdaqlisted" and (row["Market Category"] not in {"Q", "G", "S"}
                or row["Financial Status"] not in set("NDEQGHJK")):
            raise DirectoryError("Unknown Nasdaq category/status")
        rows.append(row)
    if not rows:
        raise DirectoryError("Empty directory")
    return Directory(source, hashlib.sha256(raw).hexdigest(), created, retrieved_at, tuple(rows))


def classify(row: dict[str, str], source: str) -> dict:
    """Directory-only proposal. INCLUDE is a candidate, never an identity approval."""
    symbol = row["Symbol" if source == "nasdaqlisted" else "ACT Symbol"]
    mic = "XNAS" if source == "nasdaqlisted" else {"N": "XNYS", "A": "XASE"}.get(row["Exchange"])
    name = row["Security Name"]
    text = name.casefold()
    decision, reason = "REVIEW_REQUIRED", "TYPE_UNCONFIRMED"
    if row["Test Issue"] == "Y":
        decision, reason = "EXCLUDE", "TEST_ISSUE"
    elif row["ETF"] == "Y" or row.get("NextShares") == "Y":
        decision, reason = "EXCLUDE", "FUND_FLAG"
    elif mic is None:
        if row.get("Exchange") in {"P", "Z", "V"}:
            decision, reason = "EXCLUDE", "VENUE_OUT_OF_SCOPE"
        else:
            decision, reason = "REVIEW_REQUIRED", "UNKNOWN_EXCHANGE_CODE"
    elif re.search(r"\bwhen[ -](issued|distributed)\b", text):
        decision, reason = "EXCLUDE", "WHEN_ISSUED_OR_DISTRIBUTED"
    elif re.search(r"\b(preferred|preference|warrants?|rights?|units?|notes?|debentures?|bonds?|etn|etf)\b", text):
        decision, reason = "EXCLUDE", "NON_COMMON_INSTRUMENT_NAME"
    elif re.search(r"\b(depositary|depository|adrs?|adss?)\b", text):
        decision, reason = "EXCLUDE", "DEPOSITARY_RECEIPT_NAME"
    elif re.search(r"\b(funds?|portfolio|income trust)\b", text):
        decision, reason = "REVIEW_REQUIRED", "FUND_NAME_REQUIRES_TYPE_EVIDENCE"
    elif re.search(r"\b(acquisition|spac|capital corp|capital corporation|capital ltd|finance corporation|investment|business development|bdc)\b", text):
        decision, reason = "REVIEW_REQUIRED", "SPAC_BDC_OR_FINANCIAL_REVIEW"
    elif row.get("Financial Status", "N") != "N":
        decision, reason = "REVIEW_REQUIRED", "FINANCIAL_STATUS_REVIEW"
    elif re.search(r"\b(common stock|common shares?|ordinary shares?)\b", text):
        decision, reason = "INCLUDE", "EXPLICIT_COMMON_NAME_CANDIDATE"
    return {"source": source, "symbol": symbol, "name": name, "mic": mic,
            "decision": decision, "reason": reason, "evidence": dict(row),
            "policy_version": POLICY_VERSION, "production_eligible": False}


def review_pair(nasdaq: Directory, other: Directory) -> dict:
    if (nasdaq.source, other.source) != ("nasdaqlisted", "otherlisted"):
        raise DirectoryError("Both official directories required in source order")
    if nasdaq.created_at.date() != other.created_at.date():
        raise DirectoryError("Source creation dates disagree")
    rows = [classify(row, d.source) for d in (nasdaq, other) for row in d.rows]
    # Cross-directory symbol collisions require evidence; never merge on ticker.
    symbols: dict[str, list[dict]] = {}
    for row in rows:
        symbols.setdefault(row["symbol"], []).append(row)
    for group in symbols.values():
        if len(group) > 1:
            for row in group:
                row.update(decision="REVIEW_REQUIRED", reason="CROSS_SOURCE_SYMBOL_COLLISION")
    counts = {key: sum(r["decision"] == key for r in rows)
              for key in ("INCLUDE", "EXCLUDE", "REVIEW_REQUIRED")}
    return {"status": "REVIEW_ONLY", "policy_version": POLICY_VERSION,
            "production_eligible": False, "total": len(rows), "counts": counts,
            "sources": [{"source": d.source, "sha256": d.sha256,
                         "created_at": d.created_at.isoformat(),
                         "retrieved_at": d.retrieved_at.isoformat()} for d in (nasdaq, other)],
            "rows": rows}
