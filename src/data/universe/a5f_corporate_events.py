"""A5f: non-production review of 40 real SEC 8-K corporate-event filings.

This is a provenance/audit tool, not an event classifier. Item headings and
keywords identify passages for human review, not outcomes or legal states.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone, date
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
import unicodedata
from urllib.request import Request, build_opener

from .a5c_edgar_pilot import CUTOFF
from .a5e_financial_evidence import _filing_url
from .sec_capture import NoRedirect, validate_user_agent

A5E_REPORT_SHA256 = "a58638402bbdc59b7afb2de3dfe439c6672cc0a1ede40fb59bd8a283aea7612f"
EXPECTED_ISSUERS = 16
EXPECTED_8K_FILINGS = 40
MAX_EVENT_BYTES = 16 * 1024 * 1024
INTER_REQUEST_SECONDS = 0.75

# These are agenda labels for manual review, NEVER event classifications.
WATCH_PATTERNS = {
    "MERGER_OR_ACQUISITION_LANGUAGE": r"\b(?:merger|merge(?:d|s)?|business combination|acquisition|reorganization)\b",
    "LISTING_OR_DELISTING_LANGUAGE": r"\b(?:delist(?:ed|ing)?|notice of noncompliance|trading suspension|transfer of listing|exchange listing)\b",
    "TICKER_OR_SHARE_CLASS_LANGUAGE": r"\b(?:ticker symbol|trading symbol|share class|class of common|reclassification|stock split|reverse split)\b",
    "CHARTER_OR_GOVERNANCE_LANGUAGE": r"\b(?:articles of incorporation|certificate of incorporation|bylaws|by-laws|charter amendment)\b",
    "BDC_ELECTION_OR_WITHDRAWAL_LANGUAGE": r"\b(?:n-54c|withdrawal of (?:its |the )?election|cease(?:d)? to be (?:regulated|treated) as a business development company)\b",
}
ITEM_LABELS = {
    "1.01": "MATERIAL_AGREEMENT_REVIEW",
    "2.01": "ACQUISITION_OR_DISPOSITION_REVIEW",
    "3.01": "LISTING_COMPLIANCE_REVIEW",
    "5.03": "CHARTER_BYLAWS_REVIEW",
    "8.01": "OTHER_EVENT_REVIEW",
    "2.02": "RESULTS_ANNOUNCEMENT_REVIEW",
    "7.01": "REGULATION_FD_DISCLOSURE_REVIEW",
    "9.01": "EXHIBITS_REFERENCE_REVIEW",
}


class A5fEvidenceError(ValueError):
    pass


class _BodyText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skipping += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skipping:
            self.skipping -= 1

    def handle_data(self, text):
        if not self.skipping:
            self.parts.append(text)


def _plain_text(raw: bytes) -> str:
    decoded = raw.decode("utf-8", errors="replace")
    if decoded.count("\ufffd") > max(1, len(decoded) // 20):
        decoded = raw.decode("latin-1", errors="replace")
    parser = _BodyText()
    parser.feed(decoded)
    result = " ".join(parser.parts)
    result = unicodedata.normalize("NFKC", unescape(result))
    return re.sub(r"\s+", " ", result).strip()


def analyze_eight_k(raw: bytes) -> dict:
    """Extract *candidate* SEC item headings and limited review snippets."""
    if not isinstance(raw, bytes) or not 80 <= len(raw) <= MAX_EVENT_BYTES:
        raise A5fEvidenceError("SEC 8-K primary document empty/oversized")
    plain = _plain_text(raw)
    text_lower = plain.casefold()
    if (len(plain) < 200 or not (
        re.search(r"\bform\s*8\s*[- ]\s*k\b", text_lower)
        or ("current report" in text_lower
            and "securities and exchange commission" in text_lower)
    )):
        raise A5fEvidenceError("Source does not resemble SEC 8-K primary report")
    found_items = sorted(set(re.findall(
        r"\bitem\s+([1-9]\.[0-9]{2})\b", text_lower[:250000]
    )))
    review_items = sorted(set(i for i in found_items if i in ITEM_LABELS))
    signal_snippets = {}
    for key, pattern in WATCH_PATTERNS.items():
        matches = list(re.finditer(pattern, text_lower, re.IGNORECASE))
        if matches:
            signal_snippets[key] = [
                plain[max(0, m.start() - 100):min(len(plain), m.end() + 180)]
                for m in matches[:2]
            ]
    high_priority_item = any(i in ("2.01", "3.01", "5.03") for i in review_items)
    high_priority_words = any(
        k in signal_snippets for k in (
            "LISTING_OR_DELISTING_LANGUAGE", "TICKER_OR_SHARE_CLASS_LANGUAGE",
            "BDC_ELECTION_OR_WITHDRAWAL_LANGUAGE"
        )
    )
    return {
        "sha256": sha256(raw).hexdigest(),
        "document_bytes": len(raw),
        "sec_8k_primary_text_signal": True,
        "item_headings_observed": found_items,
        "item_review_labels": {i: ITEM_LABELS[i] for i in review_items},
        "risk_language_review_snippets": signal_snippets,
        "manual_review_priority": "HIGH" if high_priority_item or high_priority_words else "NORMAL",
        "important_limitation": (
            "Boilerplate, negation, forward-looking language, exhibits and "
            "quoted text can trigger signals; none prove an event occurred."
        ),
        "event_occurred_confirmed": False,
        "current_bdc_legal_status_approved": False,
        "ticker_class_or_listing_approved": False,
        "production_eligible": False,
    }


def load_frozen_queue(a5e_path: Path) -> tuple[list[dict], dict]:
    raw = (a5e_path / "a5e-financial-evidence.json").read_bytes()
    if sha256(raw).hexdigest() != A5E_REPORT_SHA256:
        raise A5fEvidenceError("Frozen A5e evidence report checksum mismatch")
    payload = json.loads(raw.decode("utf-8"))
    if (payload.get("status") != "SOURCE_CAPTURED_REVIEW_ONLY"
            or payload.get("production_eligible") is not False
            or payload.get("issuer_total") != EXPECTED_ISSUERS
            or payload.get("financial_documents_captured") != EXPECTED_ISSUERS
            or payload.get("production_approvals") != 0
            or payload.get("source_failures")):
        raise A5fEvidenceError("A5e source receipt is not complete/review only")
    rows = payload.get("findings")
    if not isinstance(rows, list) or len(rows) != EXPECTED_ISSUERS:
        raise A5fEvidenceError("Missing original A5e issuer rows")
    seen_cik = set()
    selected = []
    counts = Counter()
    for row in rows:
        cik = row["cik"]
        if cik in seen_cik or not re.fullmatch(r"0[0-9]{9}|[1-9][0-9]{9}", cik):
            raise A5fEvidenceError("Invalid/duplicate issuer")
        seen_cik.add(cik)
        if (row.get("production_eligible") is not False
                or row.get("post_financial_events_checked") is not False
                or row.get("n54c_absence_proven") is not False
                or row.get("issuer_bdc_status") != "REVIEW_REQUIRED"
                or row.get("listed_security_class_status") != "REVIEW_REQUIRED"):
            raise A5fEvidenceError("A5e issuer previously approved")
        latest = row["latest_financial"]
        observed = row["latest_financial_observation"]
        if (observed.get("status") != "FINANCIAL_DOCUMENT_REVIEW_EVIDENCE"
                or observed.get("issuer_bdc_status_approved") is not False
                or observed.get("listed_security_class_approved") is not False):
            raise A5fEvidenceError("Unverified A5e financial filing")
        digest = observed["sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise A5fEvidenceError("Invalid financial evidence digest")
        filename = f"CIK{cik}-{latest['accession']}-{digest}.html"
        financial_raw = (a5e_path / filename).read_bytes()
        if sha256(financial_raw).hexdigest() != digest or len(financial_raw) != observed["bytes"]:
            raise A5fEvidenceError("A5e financial raw source checksum/size mismatch")
        if row.get("n54c_metadata_seen"):
            raise A5fEvidenceError("N-54C metadata requires separate review before A5f")
        if row.get("historical_files_not_downloaded"):
            raise A5fEvidenceError("Old SEC submission history is incomplete")
        tickers = row["tickers"]
        if not isinstance(tickers, list) or not tickers:
            raise A5fEvidenceError("Missing listing ticker candidates")
        try:
            financial_date = date.fromisoformat(latest["filing_date"])
        except (TypeError, ValueError) as exc:
            raise A5fEvidenceError("Invalid financial filing date") from exc
        events = row["post_financial_8k_metadata"]
        if not isinstance(events, list):
            raise A5fEvidenceError("Missing 8-K records")
        for ev in events:
            if ev["form"] not in {"8-K", "8-K/A"}:
                raise A5fEvidenceError("Unsupported SEC corporate event type")
            event_date = date.fromisoformat(ev["filing_date"])
            if not financial_date <= event_date <= CUTOFF:
                raise A5fEvidenceError("Event outside report-to-as-of date range")
            event_url = _filing_url(cik, ev["accession"],
                                    ev["document_url"].rsplit("/", 1)[-1])
            # This branch covers ordinary filenames; for safe subdirectories,
            # validate exact origin/accession and disallow traversal explicitly.
            prefix = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                      f"{ev['accession'].replace('-', '')}/")
            if not ev["document_url"].startswith(prefix):
                raise A5fEvidenceError("SEC event document CIK/accession source mismatch")
            relative = ev["document_url"][len(prefix):]
            if (not re.fullmatch(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*", relative)
                    or any(x in (".", "..") for x in relative.split("/"))):
                raise A5fEvidenceError("SEC event document path unsafe")
            if relative != ev["document_url"].rsplit("/", 1)[-1]:
                event_url = ev["document_url"]
            event = {"cik": cik, "ticker_candidates": tickers,
                     "source_submissions_sha256": row["source_submissions_sha256"],
                     "latest_10q_accession": latest["accession"],
                     "form": ev["form"], "filing_date": ev["filing_date"],
                     "accession": ev["accession"], "document_url": event_url}
            selected.append(event)
            counts[cik] += 1
    unique_keys = {(x["cik"], x["accession"]) for x in selected}
    if len(unique_keys) != len(selected) or len(selected) != EXPECTED_8K_FILINGS:
        raise A5fEvidenceError("A5e SEC event queue incomplete/duplicated")
    return selected, {
        "a5e_report_sha256": A5E_REPORT_SHA256,
        "issuer_count": EXPECTED_ISSUERS,
        "filings_to_review": len(selected),
        "source_as_of": CUTOFF.isoformat(),
        "source_counts_by_issuer": dict(sorted(counts.items())),
        "financial_raw_sha256_checks": EXPECTED_ISSUERS,
        "n54c_separate_evidence_gate": "NOT_PROVEN_ABSENT",
    }


def fetch_event(url: str, agent: str) -> bytes:
    if not re.fullmatch(
        r"https://www\.sec\.gov/Archives/edgar/data/[1-9][0-9]*/[0-9]{18}/"
        r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*", url
    ):
        raise A5fEvidenceError("Event document URL not on SEC allow-list")
    rest = url.split("/Archives/edgar/data/", 1)[1]
    if any(part in (".", "..") for part in rest.split("/")):
        raise A5fEvidenceError("SEC path traversal")
    request = Request(url, headers={
        "User-Agent": validate_user_agent(agent),
        "Accept": "text/html,text/plain",
        "Accept-Encoding": "identity",
    })
    with build_opener(NoRedirect()).open(request, timeout=35) as response:
        if response.geturl() != url:
            raise A5fEvidenceError("Unapproved SEC redirect")
        raw = response.read(MAX_EVENT_BYTES + 1)
    if len(raw) > MAX_EVENT_BYTES:
        raise A5fEvidenceError("SEC 8-K document exceeds size cap")
    return raw


def run_audit(a5e_path: Path, output: Path, *, agent: str, fetcher=fetch_event,
              clock=lambda: datetime.now(timezone.utc),
              pause=time.sleep) -> dict:
    validate_user_agent(agent)
    events, provenance = load_frozen_queue(a5e_path)
    output.mkdir(parents=True, exist_ok=False)
    findings, errors = [], []
    consecutive_source_errors = 0
    for i, record in enumerate(events):
        if i:
            pause(INTER_REQUEST_SECONDS)
        try:
            raw = fetcher(record["document_url"], agent)
            result = analyze_eight_k(raw)
            retrieved = clock()
            if retrieved.tzinfo is None or retrieved.utcoffset() is None:
                raise A5fEvidenceError("SEC retrieval timestamp is not timezone-aware")
            name = f"CIK{record['cik']}-{record['accession']}-{result['sha256']}.html"
            (output / name).write_bytes(raw)
            evidence = {**record, **result,
                        "status": "SEC_8K_PRIMARY_TEXT_REVIEW_CANDIDATE",
                        "retrieved_at": retrieved.isoformat(),
                        "raw_artifact_filename": name,
                        "post_financial_events_checked": False}
            consecutive_source_errors = 0
        except (OSError, ValueError, TimeoutError) as exc:
            errors.append({"cik": record["cik"], "accession": record["accession"],
                           "error": f"{type(exc).__name__}: {exc}"[:220]})
            evidence = {**record, "status": "SEC_8K_DOCUMENT_UNVERIFIED",
                        "post_financial_events_checked": False,
                        "production_eligible": False}
            consecutive_source_errors += 1
        findings.append(evidence)
        if consecutive_source_errors >= 3:
            break
    keywords = Counter()
    items = Counter()
    priorities = Counter()
    for f in findings:
        if f["status"] != "SEC_8K_PRIMARY_TEXT_REVIEW_CANDIDATE":
            continue
        keywords.update(f["risk_language_review_snippets"].keys())
        items.update(f["item_review_labels"].keys())
        priorities.update([f["manual_review_priority"]])
    success = not errors and len(findings) == EXPECTED_8K_FILINGS
    report = {
        "status": "ALL_SOURCES_CAPTURED_REVIEW_ONLY" if success else "PARTIAL_SOURCES_REVIEW_ONLY",
        "production_eligible": False,
        "provenance": provenance,
        "expected_event_filings": EXPECTED_8K_FILINGS,
        "primary_documents_verified": sum(
            x["status"] == "SEC_8K_PRIMARY_TEXT_REVIEW_CANDIDATE" for x in findings),
        "source_failures": errors,
        "sec_form_items_observed": dict(sorted(items.items())),
        "risk_language_mention_counts": dict(sorted(keywords.items())),
        "review_priority_counts": dict(sorted(priorities.items())),
        "event_occurred_confirmed": 0,
        "issuer_current_bdc_approvals": 0,
        "security_class_approvals": 0,
        "production_approvals": 0,
        "n54c_absence_proven": False,
        "human_review_complete": False,
        "findings": findings,
    }
    (output / "a5f-8k-evidence.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in {"findings", "source_failures"}}, indent=2, ensure_ascii=False))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a5e-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run_audit(args.a5e_artifact, args.output,
                           agent=os.environ.get("SEC_USER_AGENT", ""))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"A5F_BLOCKED: {exc}")
        return 2
    return 0 if report["status"] == "ALL_SOURCES_CAPTURED_REVIEW_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
