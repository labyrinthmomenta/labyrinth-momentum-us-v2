"""A5e: capture post-election 10-Q/10-K filing evidence for 16 frozen BDC candidates.

A filing's cover-page title/ticker/exchange and issuer BDC wording are *signals*
for human review, not authoritative security_id mapping, active regulatory
status, point-in-time availability, or production approval.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, date
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
import unicodedata

from .a5c_edgar_pilot import CUTOFF
from .a5d_election_documents import (
    A5C_REPORT_SHA256, load_frozen_elections, fetch_document,
    A5dEvidenceError,
)
from .sec_capture import validate_user_agent

A5D_REPORT_SHA256 = "b1a5b4ecdca3572ecd84baef85b5e9ec3ae47c422ec39ad6491c7cf89a2d11da"
ELECTION_ISSUERS = 16
MAX_FINANCIAL_BYTES = 64 * 1024 * 1024  # Some genuine inline-XBRL 10-Qs exceed 20 MiB
INTER_REQUEST_SECONDS = 0.75
FINANCIAL_FORMS = ("10-Q", "10-K")
EVENT_FORMS = ("8-K", "8-K/A")
SAFE_FILENAME = re.compile(r"[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._-]+)*")
ACC_RE = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}")


class A5eEvidenceError(ValueError):
    pass


class _HtmlBody(HTMLParser):
    """Small standard-library parser that preserves cover-page table rows."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks = []
        self.rows = []
        self._skip = 0
        self._in_row = 0
        self._row = []
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "tr":
            self._in_row += 1
            if self._in_row == 1:
                self._row = []
    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag == "tr" and self._in_row:
            self._in_row -= 1
            if not self._in_row:
                row = _compact(" ".join(self._row))
                if row:
                    self.rows.append(row)
    def handle_data(self, data):
        if not self._skip:
            self.chunks.append(data)
            if self._in_row:
                self._row.append(data)


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", unescape(value))).strip()


def _filing_url(cik: str, accession: str, filename: str) -> str:
    if (not re.fullmatch(r"[0-9]{10}", cik) or int(cik) <= 0
            or not isinstance(accession, str) or not ACC_RE.fullmatch(accession)
            or not isinstance(filename, str) or not SAFE_FILENAME.fullmatch(filename)
            or any(x in (".", "..") for x in filename.split("/"))):
        raise A5eEvidenceError("Invalid SEC filing document locator")
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{filename}")


def _full_recent_filings(raw: bytes, cik: str) -> list[dict]:
    """Read the full, frozen 303-issuer SEC recent metadata array."""
    source = json.loads(raw.decode("utf-8-sig"))
    if f"{int(source['cik']):010d}" != cik:
        raise A5eEvidenceError("SEC issuer does not match expected CIK")
    recent = source["filings"]["recent"]
    keys = ("form", "filingDate", "accessionNumber", "primaryDocument")
    if any(not isinstance(recent.get(k), list) for k in keys):
        raise A5eEvidenceError("SEC filing metadata columns missing")
    n = len(recent["form"])
    if any(len(recent[k]) != n for k in keys):
        raise A5eEvidenceError("SEC filing metadata is not aligned")
    result = []
    for i in range(n):
        form = recent["form"][i]
        if form not in FINANCIAL_FORMS + EVENT_FORMS + ("N-54C", "N-54C/A"):
            continue
        when = date.fromisoformat(recent["filingDate"][i])
        if when > CUTOFF:
            continue
        result.append({
            "form": form, "filing_date": when.isoformat(),
            "accession": recent["accessionNumber"][i],
            "document_url": _filing_url(cik, recent["accessionNumber"][i],
                                        recent["primaryDocument"][i]),
        })
    return sorted(result, key=lambda v: (v["filing_date"], v["accession"]), reverse=True)


def load_inputs(a5c: Path, a5d: Path) -> tuple[list[dict], dict]:
    """Validate both immutable source artifacts and all 17 original filings."""
    cohort, provenance = load_frozen_elections(a5c)
    raw_report = (a5d / "a5d-election-evidence.json").read_bytes()
    if sha256(raw_report).hexdigest() != A5D_REPORT_SHA256:
        raise A5eEvidenceError("Frozen A5d audit checksum mismatch")
    report = json.loads(raw_report.decode("utf-8"))
    if (report.get("status") != "DOCUMENT_EVIDENCE_CAPTURED_REVIEW_ONLY"
            or report.get("production_eligible") is not False
            or report.get("original_cohort_issuers") != ELECTION_ISSUERS
            or report.get("verified_n54a_primary_documents") != 17
            or report.get("document_fetch_failures") != 0
            or report.get("production_approved") != 0):
        raise A5eEvidenceError("A5d SEC election evidence incomplete")
    a5d_rows = report.get("findings")
    if not isinstance(a5d_rows, list) or len(a5d_rows) != ELECTION_ISSUERS:
        raise A5eEvidenceError("Incomplete A5d issuer cohort")
    by_cik = {e["cik"]: e for e in a5d_rows}
    if len(by_cik) != ELECTION_ISSUERS:
        raise A5eEvidenceError("Duplicate A5d issuer")
    selected = []
    for issuer in cohort:
        cik = issuer["cik"]
        evidence = by_cik.get(cik)
        if not evidence or evidence.get("production_eligible") is not False:
            raise A5eEvidenceError("Original election evidence row missing/approved")
        if (evidence["submissions_sha256"] != issuer["submissions_sha256"]
                or evidence["ticker_candidates"] != issuer["ticker_candidates"]):
            raise A5eEvidenceError("Election issuer/source mismatch")
        verified = evidence.get("election_filings", [])
        if not verified or any(x["status"] != "FORM_TEXT_SIGNAL_VERIFIED" for x in verified):
            raise A5eEvidenceError("Original N-54A document not verified")
        for filing in verified:
            filename = (f"CIK{cik}-{filing['accession']}-{filing['sha256']}.html")
            if sha256((a5d / filename).read_bytes()).hexdigest() != filing["sha256"]:
                raise A5eEvidenceError("Original N-54A document checksum mismatch")
        file = a5c / f"CIK{cik}-{issuer['submissions_sha256']}.json"
        raw = file.read_bytes()
        if sha256(raw).hexdigest() != issuer["submissions_sha256"]:
            raise A5eEvidenceError("SEC company submissions checksum mismatch")
        recent = _full_recent_filings(raw, cik)
        finances = [f for f in recent if f["form"] in FINANCIAL_FORMS]
        if not finances:
            raise A5eEvidenceError(f"No pre-cutoff 10-Q/10-K for {cik}")
        latest = finances[0]
        changes = [f for f in recent
                   if f["form"] in EVENT_FORMS and f["filing_date"] >= latest["filing_date"]]
        withdrawals = [f for f in recent if f["form"].startswith("N-54C")]
        selected.append({
            "cik": cik, "tickers": issuer["ticker_candidates"],
            "issuer_name": issuer["filer_name"],
            "original_election_accessions": [f["accession"] for f in verified],
            "latest_financial": latest,
            "post_financial_8k_metadata": changes,
            "n54c_metadata_seen": withdrawals,
            "historical_files_not_downloaded": issuer["historical_files_not_downloaded"],
            "source_submissions_sha256": issuer["submissions_sha256"],
            "source_submissions_retrieved_at": issuer["submissions_retrieved_at"],
        })
    return selected, {
        "a5c_report_sha256": A5C_REPORT_SHA256,
        "a5d_report_sha256": A5D_REPORT_SHA256,
        "selection_as_of_date": CUTOFF.isoformat(),
        "issuers": len(selected), "source_provenance": provenance,
    }


def inspect_financial(raw: bytes, *, expected_tickers: list[str]) -> dict:
    """Identify text evidence; never treat a word match as legal final status."""
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_FINANCIAL_BYTES:
        raise A5eEvidenceError("Empty or oversized SEC financial filing")
    decoded = raw.decode("utf-8", errors="replace")
    if decoded.count("\ufffd") > max(1, len(decoded) // 20):
        decoded = raw.decode("latin-1", errors="replace")
    html = _HtmlBody()
    html.feed(decoded)
    plain = _compact(" ".join(html.chunks))
    lower = plain.casefold()
    form_present = bool(re.search(r"\bform\s+10[\s-]*[qk]\b", lower)
                        or "quarterly report pursuant" in lower
                        or "annual report pursuant" in lower)
    if not form_present or len(plain) < 600:
        raise A5eEvidenceError("SEC document does not resemble a 10-Q/10-K")
    matches = list(re.finditer(r"\bbusiness development compan(?:y|ies)\b", lower))
    bdc_contexts = [plain[max(0, m.start()-220):m.end()+220] for m in matches[:12]]
    election_regex = re.compile(
        r"(?:elect(?:ed|s)?\s+to\s+be\s+regulated\s+as|"
        r"regulat(?:ed|ion)\s+as|"
        r"operat(?:e|es|ing)\s+as)\s+(?:an?\s+)?business\s+development\s+company",
        re.IGNORECASE)
    bdc_statement_candidates = [
        ctx[:500] for ctx in bdc_contexts if election_regex.search(ctx)
    ][:3]
    # Row-level *supporting* evidence only. A valid security class may be split
    # across table rows or embedded inline XBRL; no automatic negative decision.
    top_rows = html.rows[:300]
    securities = []
    for ticker in expected_tickers:
        if not isinstance(ticker, str) or not re.fullmatch(r"[A-Za-z0-9.$^-]{1,18}", ticker):
            raise A5eEvidenceError("Unsafe expected listing ticker")
        hits = [row[:600] for row in top_rows
                if re.search(r"(?<![A-Z0-9])" + re.escape(ticker.upper())
                             + r"(?![A-Z0-9])", row.upper())
                and ("common stock" in row.casefold() or "common shares" in row.casefold())
                and any(x in row.casefold() for x in ("nasdaq", "new york stock exchange",
                                                      "nyse", "american"))]
        securities.append({
            "ticker": ticker,
            "section_12b_row_candidates": hits[:4],
            "row_evidence_present": bool(hits),
            "share_class_approved": False,
            "security_id": None,
        })
    return {
        "source_sha256": sha256(raw).hexdigest(),
        "source_bytes": len(raw),
        "financial_form_text_present": form_present,
        "bdc_phrase_occurrences": len(matches),
        "bdc_status_sentence_candidates": bdc_statement_candidates,
        "bdc_issuer_status": "REQUIRES_HUMAN_FILING_REVIEW",
        "listed_security_row_candidates": securities,
        "security_type_status": "REVIEW_REQUIRED",
        "production_eligible": False,
    }


def fetch_financial(url: str, agent: str) -> bytes:
    # Reuse SEC archive URL allow-list from A5d; enlarge size cap for 10-Q/10-K.
    if not re.fullmatch(
        r"https://www\.sec\.gov/Archives/edgar/data/[1-9][0-9]*/[0-9]{18}/"
        r"[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._-]+)*", url):
        raise A5eEvidenceError("SEC financial source URL is not approved")
    # Never send even a nominally approved SEC URL containing path traversal.
    relative_path = url.split("/Archives/edgar/data/", 1)[1] if "/Archives/edgar/data/" in url else ""
    if any(segment in (".", "..") for segment in relative_path.split("/")):
        raise A5eEvidenceError("SEC financial path traversal rejected")
    from urllib.request import Request, build_opener
    from .sec_capture import NoRedirect
    request = Request(url, headers={"User-Agent": validate_user_agent(agent),
                                    "Accept": "text/html,text/plain",
                                    "Accept-Encoding": "identity"})
    with build_opener(NoRedirect()).open(request, timeout=35) as response:
        if response.geturl() != url:
            raise A5eEvidenceError("SEC response changed source URL")
        raw = response.read(MAX_FINANCIAL_BYTES + 1)
    if len(raw) > MAX_FINANCIAL_BYTES:
        raise A5eEvidenceError("SEC financial filing too large")
    return raw


def run_a5e(a5c: Path, a5d: Path, output: Path, *, agent: str,
            fetcher=fetch_financial,
            clock=lambda: datetime.now(timezone.utc),
            pause=time.sleep) -> dict:
    validate_user_agent(agent)
    selected, provenance = load_inputs(a5c, a5d)
    output.mkdir(parents=True, exist_ok=False)
    findings, failures = [], []
    for i, issuer in enumerate(selected):
        if i:
            pause(INTER_REQUEST_SECONDS)
        target = issuer["latest_financial"]
        try:
            raw = fetcher(target["document_url"], agent)
            evidence = inspect_financial(raw, expected_tickers=issuer["tickers"])
            observed_at = clock()
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise A5eEvidenceError("SEC retrieval timestamp must be timezone aware")
            stored = f"CIK{issuer['cik']}-{target['accession']}-{evidence['source_sha256']}.html"
            (output / stored).write_bytes(raw)
            observation = {"status": "FINANCIAL_DOCUMENT_REVIEW_EVIDENCE",
                           "retrieved_at": observed_at.isoformat(),
                           "sha256": evidence["source_sha256"],
                           "bytes": evidence["source_bytes"],
                           "bdc_phrase_occurrences": evidence["bdc_phrase_occurrences"],
                           "bdc_status_sentence_candidates": evidence["bdc_status_sentence_candidates"],
                           "listed_security_row_candidates": evidence["listed_security_row_candidates"],
                           "issuer_bdc_status_approved": False,
                           "listed_security_class_approved": False}
        except (OSError, ValueError, TimeoutError) as exc:
            failures.append({"cik": issuer["cik"],
                             "accession": target["accession"],
                             "error": f"{type(exc).__name__}: {exc}"[:200]})
            observation = {"status": "DOCUMENT_UNVERIFIED",
                           "issuer_bdc_status_approved": False,
                           "listed_security_class_approved": False}
        findings.append({**issuer, "latest_financial_observation": observation,
                         "post_financial_events_checked": False,
                         "n54c_absence_proven": False,
                         "issuer_bdc_status": "REVIEW_REQUIRED",
                         "listed_security_class_status": "REVIEW_REQUIRED",
                         "production_eligible": False})
    result = {
        "status": "SOURCE_CAPTURED_REVIEW_ONLY" if not failures else "PARTIAL_SOURCE_FAILURE",
        "production_eligible": False,
        "provenance": provenance,
        "issuer_total": len(selected),
        "financial_documents_captured": len(selected)-len(failures),
        "source_failures": failures,
        "row_level_security_evidence_candidates": sum(
            bool(entry["row_evidence_present"])
            for f in findings
            for entry in f["latest_financial_observation"].get(
                "listed_security_row_candidates", [])),
        "bdc_issuer_status_approvals": 0,
        "security_class_approvals": 0,
        "production_approvals": 0,
        "findings": findings,
    }
    (output / "a5e-financial-evidence.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("findings","source_failures")},
                     ensure_ascii=False, indent=2))
    return result


def main():
    import os
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a5c-artifact", type=Path, required=True)
    p.add_argument("--a5d-artifact", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        result = run_a5e(args.a5c_artifact, args.a5d_artifact, args.output,
                         agent=os.environ.get("SEC_USER_AGENT", ""))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"A5E_BLOCKED: {exc}")
        return 2
    return 0 if result["status"] == "SOURCE_CAPTURED_REVIEW_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
