"""Offline SEC issuer identity candidates, not security classification or approval."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json

from .triage import triage_record

SEC_FIELDS = ("cik", "name", "ticker", "exchange")
EXCHANGE_TO_MIC = {"nasdaq": "XNAS", "nyse": "XNYS", "nyse american": "XASE"}
MAX_SEC_BYTES = 20 * 1024 * 1024


class SecSnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class SecCompany:
    cik: str
    name: str
    ticker: str
    exchange: str
    mic: str | None


@dataclass(frozen=True)
class SecExchangeSnapshot:
    sha256: str
    retrieved_at: datetime
    companies: tuple[SecCompany, ...]


def parse_sec_exchange_snapshot(raw: bytes, *, retrieved_at: datetime) -> SecExchangeSnapshot:
    """Strict parsing of supplied SEC JSON bytes. No network or guessed effective dates."""
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise SecSnapshotError("SEC retrieved_at must be timezone aware")
    if len(raw) > MAX_SEC_BYTES:
        raise SecSnapshotError("SEC snapshot exceeds size limit")
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise SecSnapshotError("Invalid SEC JSON") from exc
    if not isinstance(payload, dict) or payload.get("fields") != list(SEC_FIELDS):
        raise SecSnapshotError("Unexpected SEC fields/schema")
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise SecSnapshotError("SEC data must be a nonempty list")
    companies, seen = [], set()
    for values in data:
        if not isinstance(values, list) or len(values) != len(SEC_FIELDS):
            raise SecSnapshotError("Malformed SEC row")
        cik, name, ticker, exchange = values
        if type(cik) is int and cik > 0:
            cik_number = cik
        elif isinstance(cik, str) and cik.isascii() and cik.isdecimal() and cik:
            cik_number = int(cik)
        else:
            raise SecSnapshotError("Invalid SEC CIK")
        if not 1 <= cik_number <= 9999999999:
            raise SecSnapshotError("SEC CIK out of range")
        if any(not isinstance(x, str) or not x.strip() or x != x.strip()
               for x in (name, ticker, exchange)):
            raise SecSnapshotError("Malformed SEC company, ticker or exchange")
        key = (cik_number, ticker, exchange)
        if key in seen:
            raise SecSnapshotError("Duplicate SEC CIK/ticker/exchange")
        seen.add(key)
        companies.append(SecCompany(f"{cik_number:010d}", name, ticker, exchange,
                                    EXCHANGE_TO_MIC.get(exchange.casefold())))
    return SecExchangeSnapshot(hashlib.sha256(raw).hexdigest(), retrieved_at,
                               tuple(companies))


def enrich_review_with_sec(review: dict, sec: SecExchangeSnapshot) -> dict:
    """Attach issuer candidates. Ambiguity quarantines; no identities are written."""
    if review.get("status") != "REVIEW_ONLY" or review.get("production_eligible") is not False:
        raise SecSnapshotError("Only provisional directory reviews may be enriched")
    if not isinstance(review.get("rows"), list):
        raise SecSnapshotError("Review rows missing")
    lookup: dict[tuple[str, str], list[SecCompany]] = {}
    for company in sec.companies:
        if company.mic is not None:
            lookup.setdefault((company.ticker, company.mic), []).append(company)
    result = deepcopy(review)
    match_counts = {"SEC_CIK_CANDIDATE": 0, "SEC_NOT_FOUND": 0, "SEC_IDENTITY_AMBIGUOUS": 0}
    for row in result["rows"]:
        if row.get("production_eligible") is not False or row.get("decision") not in {
                "INCLUDE", "EXCLUDE", "REVIEW_REQUIRED"}:
            raise SecSnapshotError("Invalid/unapproved directory row")
        ticker, mic = row.get("symbol"), row.get("mic")
        matches = lookup.get((ticker, mic), []) if isinstance(ticker, str) and isinstance(mic, str) else []
        if not matches:
            evidence = {"status": "SEC_NOT_FOUND"}
        elif len(matches) == 1:
            company = matches[0]
            evidence = {"status": "SEC_CIK_CANDIDATE", "issuer_cik": company.cik,
                        "sec_company_name": company.name, "sec_ticker": company.ticker,
                        "sec_exchange": company.exchange}
        else:
            evidence = {"status": "SEC_IDENTITY_AMBIGUOUS",
                        "candidate_ciks": sorted({company.cik for company in matches})}
            if row["decision"] != "EXCLUDE":
                row["directory_decision_before_sec"] = row["decision"]
                row["directory_reason_before_sec"] = row["reason"]
                row["decision"], row["reason"] = "REVIEW_REQUIRED", "SEC_IDENTITY_AMBIGUOUS"
        row["issuer_match"] = evidence
        row["triage"] = triage_record(row)
        row["production_eligible"] = False
        match_counts[evidence["status"]] += 1
    result["counts"] = {key: sum(r["decision"] == key for r in result["rows"])
                        for key in ("INCLUDE", "EXCLUDE", "REVIEW_REQUIRED")}
    result["sec_enrichment"] = {"status": "CANDIDATES_ONLY", "sha256": sec.sha256,
                                "retrieved_at": sec.retrieved_at.isoformat(),
                                "rows": len(sec.companies), "match_counts": match_counts,
                                "issuer_identity_approved": False}
    result["production_eligible"] = False
    return result
