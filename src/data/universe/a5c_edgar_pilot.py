"""Evidence-only SEC EDGAR Submissions API pilot for A5 SPAC/BDC/financial review.

CIK identifies a filer, not a listed security. Filing metadata identifies
documents, not the factual content or effectiveness of a legal election.
Do not classify, approve, publish or change the authoritative universe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, build_opener
import argparse
import json
import os
import re
import time

from .sec_capture import NoRedirect, validate_user_agent

SUBMISSION_BASE = "https://data.sec.gov/submissions/"
EXPECTED_A5_QUEUE_SHA256 = "ea4a8e3112e3e30d9c3e67fc33fac86a3a6aa3fcf2f58391ecc50896ba3bdb37"
EXPECTED_A5_ROWS = 1010
TARGET_REASON = "SPAC_BDC_OR_FINANCIAL_REVIEW"
TARGET_ROWS = 307
CUTOFF = date(2026, 10, 14)
MAX_SUBMISSION_BYTES = 12 * 1024 * 1024
INTER_REQUEST_SECONDS = 0.75
DOCUMENT_FORMS = frozenset({
    "N-54A", "N-54C", "S-1", "S-1/A", "N-2", "N-2/A",
    "10-K", "10-K/A", "10-Q", "8-K", "8-K/A",
})


class EdgarEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class Filing:
    form: str
    accession: str
    filing_date: str
    document_url: str | None


@dataclass(frozen=True)
class Submissions:
    cik: str
    filer_name: str
    sha256: str
    fetched_at: str
    history_complete: bool
    filings: tuple[Filing, ...]
    historical_files: tuple[str, ...]


def source_url(cik: str) -> str:
    if not isinstance(cik, str) or not re.fullmatch(r"[0-9]{10}", cik) or int(cik) < 1:
        raise EdgarEvidenceError("Invalid 10-digit CIK")
    return SUBMISSION_BASE + f"CIK{cik}.json"


def parse_submissions(raw: bytes, *, expected_cik: str, fetched_at: datetime) -> Submissions:
    source_url(expected_cik)
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise EdgarEvidenceError("Timezone-aware SEC retrieval time required")
    if len(raw) > MAX_SUBMISSION_BYTES:
        raise EdgarEvidenceError("SEC submissions data exceeds limit")
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise EdgarEvidenceError("SEC submissions response is not JSON") from exc
    if not isinstance(payload, dict):
        raise EdgarEvidenceError("SEC submissions expected JSON object")
    raw_cik = payload.get("cik")
    if isinstance(raw_cik, bool) or not isinstance(raw_cik, (int, str)):
        raise EdgarEvidenceError("SEC submissions CIK missing")
    if not str(raw_cik).isascii() or not str(raw_cik).isdecimal():
        raise EdgarEvidenceError("SEC submissions CIK invalid")
    if f"{int(raw_cik):010d}" != expected_cik:
        raise EdgarEvidenceError("SEC returned different filer CIK")
    filer = payload.get("name")
    if not isinstance(filer, str) or not filer.strip():
        raise EdgarEvidenceError("SEC filer name missing")
    section = payload.get("filings")
    if not isinstance(section, dict) or not isinstance(section.get("recent"), dict):
        raise EdgarEvidenceError("SEC filings.recent missing")
    recent = section["recent"]
    cols = ("form", "accessionNumber", "filingDate", "primaryDocument")
    if any(not isinstance(recent.get(k), list) for k in cols):
        raise EdgarEvidenceError("SEC filing arrays missing")
    n = len(recent["form"])
    if any(len(recent[k]) != n for k in cols):
        raise EdgarEvidenceError("SEC filing arrays not aligned")
    extras = section.get("files")
    if not isinstance(extras, list):
        raise EdgarEvidenceError("SEC filings.files must be list")
    previous = []
    for meta in extras:
        if (not isinstance(meta, dict)
                or not isinstance(meta.get("name"), str)
                or not re.fullmatch(r"CIK[0-9]{10}-submissions-[0-9]{3}.json", meta["name"])):
            raise EdgarEvidenceError("SEC history file metadata invalid")
        previous.append(meta["name"])
    records = []
    for i in range(n):
        form, accession, day, doc = (recent[k][i] for k in cols)
        if not isinstance(form, str) or not isinstance(day, str):
            raise EdgarEvidenceError("SEC filing form/date malformed")
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
            raise EdgarEvidenceError("SEC filing date malformed")
        try:
            filed = date.fromisoformat(day)
        except ValueError as exc:
            raise EdgarEvidenceError("Invalid SEC filing date") from exc
        if (not isinstance(accession, str)
                or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession)):
            raise EdgarEvidenceError("SEC accession invalid")
        if not isinstance(doc, str):
            raise EdgarEvidenceError("SEC primary document malformed")
        if doc and not re.fullmatch(r"[a-zA-Z0-9._-]+", doc):
            raise EdgarEvidenceError("SEC primary document path unsafe")
        if form in DOCUMENT_FORMS and filed <= CUTOFF:
            path = (f"https://www.sec.gov/Archives/edgar/data/{int(expected_cik)}/"
                    f"{accession.replace('-', '')}/{doc}") if doc else None
            records.append(Filing(form, accession, day, path))
    records.sort(key=lambda f: (f.filing_date, f.accession), reverse=True)
    return Submissions(expected_cik, filer, sha256(raw).hexdigest(),
                       fetched_at.isoformat(), not bool(previous),
                       tuple(records), tuple(previous))


def load_frozen_candidates(path: Path, *, limit: int) -> tuple[list[dict], dict]:
    if not 1 <= limit <= TARGET_ROWS:
        raise EdgarEvidenceError("Invalid EDGAR pilot limit")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != EXPECTED_A5_QUEUE_SHA256:
        raise EdgarEvidenceError("Frozen A5 instrument review SHA mismatch")
    rows = json.loads(raw.decode("utf-8"))
    if not isinstance(rows, list) or len(rows) != EXPECTED_A5_ROWS:
        raise EdgarEvidenceError("Expected all A5 review rows")
    targets = [r for r in rows if r.get("original_reason") == TARGET_REASON]
    if len(targets) != TARGET_ROWS:
        raise EdgarEvidenceError("Expected precisely 307 original financial reviews")
    for row in targets:
        if (row.get("production_eligible") is not False
                or row.get("security_type_approved") is not False):
            raise EdgarEvidenceError("Source row is production approved")
    with_cik = {}
    no_cik = []
    for row in targets:
        proposal = row.get("issuer_match_candidate") or {}
        cik = proposal.get("cik_candidate")
        if cik is None:
            no_cik.append(row["symbol"])
            continue
        source_url(cik)
        with_cik.setdefault(cik, []).append(row["symbol"])
    if len(with_cik) + len(no_cik) < 1:
        raise EdgarEvidenceError("No SEC candidates")
    # Select BDC-named / acquisition-named issuers first. Name-only hints
    # prioritize evidence collection; never decide legal/instrument type.
    def priority(item):
        cik, symbols = item
        names = " ".join(row["name"].lower() for row in targets
                         if row["symbol"] in symbols)
        return (0 if "bdc" in names or "business development" in names else
                1 if "acquisition" in names else 2, cik)
    selected = sorted(with_cik.items(), key=priority)[:limit]
    return [{"cik": cik, "tickers": symbols} for cik, symbols in selected], {
        "total_review_rows": len(targets), "unique_cik_candidates": len(with_cik),
        "no_cik_candidate_tickers": no_cik, "pilot_selected_issuers": len(selected),
        "not_selected_issuer_count": len(with_cik) - len(selected)}


def fetch_one(cik: str, agent: str) -> bytes:
    url = source_url(cik)
    req = Request(url, headers={"User-Agent": validate_user_agent(agent),
                                "Accept": "application/json",
                                "Accept-Encoding": "identity"})
    with build_opener(NoRedirect()).open(req, timeout=25) as resp:
        if resp.geturl() != url:
            raise EdgarEvidenceError("SEC response URL mismatch")
        raw = resp.read(MAX_SUBMISSION_BYTES + 1)
    if len(raw) > MAX_SUBMISSION_BYTES:
        raise EdgarEvidenceError("SEC response exceeds size cap")
    return raw


def run_pilot(queue: Path, out: Path, *, user_agent: str, limit: int = 20,
              fetcher=fetch_one, clock=lambda: datetime.now(timezone.utc),
              pause=time.sleep) -> dict:
    validate_user_agent(user_agent)
    selected, coverage = load_frozen_candidates(queue, limit=limit)
    out.mkdir(parents=True, exist_ok=False)
    entries = []
    failures = []
    for index, item in enumerate(selected):
        cik = item["cik"]
        if index:
            pause(INTER_REQUEST_SECONDS)
        try:
            raw = fetcher(cik, user_agent)
            snap = parse_submissions(raw, expected_cik=cik, fetched_at=clock())
            forms = sorted(set(f.form for f in snap.filings))
            entries.append({
                "cik": cik, "directory_tickers": item["tickers"],
                "sec_filer_name": snap.filer_name,
                "sec_source_url": source_url(cik), "sec_sha256": snap.sha256,
                "retrieved_at": snap.fetched_at,
                "recent_window_exhaustive": snap.history_complete,
                "older_history_files_not_downloaded": list(snap.historical_files),
                "form_types_found_in_recent_window": forms,
                "filings": [vars(f) for f in snap.filings[:60]],
                "issuer_type_conclusion": "REQUIRES_DOCUMENT_REVIEW",
                "security_type_conclusion": "REVIEW_REQUIRED",
                "cik_to_listed_security_approved": False,
                "production_eligible": False,
            })
            (out / f"CIK{cik}-{snap.sha256}.json").write_bytes(raw)
        except (ValueError, OSError, TimeoutError) as exc:
            failures.append({"cik": cik, "error": f"{type(exc).__name__}: {exc}"})
    report = {"status": "CAPTURE_VALIDATED_REVIEW_ONLY" if not failures else "PARTIAL_SOURCE_FAILURE",
              "production_eligible": False,
              "a5_queue_sha256": EXPECTED_A5_QUEUE_SHA256, "a5_as_of": CUTOFF.isoformat(),
              "sec_collection_date_is_not_a5_point_in_time": True,
              "coverage": coverage, "successful_cik_count": len(entries),
              "failed_cik_count": len(failures), "failed_sources": failures,
              "selected_evidence": entries, "auto_approved_instruments": 0}
    (out / "edgar-pilot.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in {"selected_evidence", "failed_sources"}}, indent=2))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a5-instrument-review", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--limit", type=int, default=20)
    args = p.parse_args()
    try:
        report = run_pilot(args.a5_instrument_review, args.output,
                           user_agent=os.environ.get("SEC_USER_AGENT", ""),
                           limit=args.limit)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"EDGAR_PILOT_BLOCKED: {exc}")
        return 2
    return 0 if report["status"] == "CAPTURE_VALIDATED_REVIEW_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
