"""A5d: verify actual SEC N-54A election document contents for the 16 frozen A5c issuers.

Evidence-only: a filed election notification and a text signal do not prove
present BDC status, current share class, or production trading eligibility.
The original A4/A5 lists, BIST production and pricing layers stay unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone, date
from hashlib import sha256
from html import unescape
import json
from pathlib import Path
import re
import time
import unicodedata
from urllib.request import Request, build_opener

from .a5c_edgar_pilot import parse_submissions, CUTOFF
from .sec_capture import NoRedirect, validate_user_agent

A5C_REPORT_SHA256 = "38b3773641c5e104ae6da7aaf19f32682b3aef66b6d0d4bb8fedeb9d3aa186ea"
EXPECTED_A5C_ISSUERS = 303
EXPECTED_ELECTION_ISSUERS = 16
MAX_DOCUMENT_BYTES = 3 * 1024 * 1024
INTER_REQUEST_SECONDS = 0.75
PRIMARY_FORMS = frozenset({"N-54A", "N-54A/A", "N-54C", "N-54C/A"})


class A5dEvidenceError(ValueError):
    pass


def form_records(raw: bytes, cik: str) -> list[dict]:
    """Complete SEC recent array, not A5c's first 60 report rows."""
    obj = json.loads(raw.decode("utf-8-sig"))
    recent = obj["filings"]["recent"]
    keys = ("form", "accessionNumber", "filingDate", "primaryDocument")
    if any(not isinstance(recent.get(k), list) for k in keys):
        raise A5dEvidenceError("Incomplete SEC filing arrays")
    n = len(recent["form"])
    if any(len(recent[k]) != n for k in keys):
        raise A5dEvidenceError("Misaligned SEC filing arrays")
    result = []
    for i in range(n):
        form, accession, day, filename = (recent[k][i] for k in keys)
        if form not in PRIMARY_FORMS:
            continue
        if (not isinstance(day, str) or not isinstance(accession, str)
                or not isinstance(filename, str)):
            raise A5dEvidenceError("Malformed election filing")
        try:
            when = date.fromisoformat(day)
        except ValueError as exc:
            raise A5dEvidenceError("Invalid filing date") from exc
        if when > CUTOFF:
            continue
        if not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
            raise A5dEvidenceError("Invalid accession")
        if not re.fullmatch(r"[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._-]+)*", filename) or any(
            part in (".", "..") for part in filename.split("/")
        ):
            raise A5dEvidenceError("Unsafe SEC primary document path")
        url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
               f"{accession.replace('-', '')}/{filename}")
        result.append({"form": form, "accession": accession, "filing_date": day,
                       "primary_document": filename, "url": url})
    return sorted(result, key=lambda row: (row["filing_date"], row["accession"]))


def inspect_document(raw: bytes) -> dict:
    """Only inspect document type signals; never infer a legal status or share class."""
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_DOCUMENT_BYTES:
        raise A5dEvidenceError("SEC document missing or oversized")
    decoded = raw.decode("utf-8", errors="replace")
    if decoded.count("\ufffd") > len(decoded) // 20:
        decoded = raw.decode("latin-1", errors="replace")
    decoded = unescape(decoded)
    decoded = re.sub(r"(?is)<(?:script|style)\b[^>]*>.*?</(?:script|style)>", " ", decoded)
    plain = re.sub(r"(?s)<[^>]+>", " ", decoded)
    plain = unicodedata.normalize("NFKC", unescape(plain))
    plain = re.sub(r"\s+", " ", plain).casefold()
    detected = {
        "form_n54a_heading": bool(re.search(r"\bform\s*n[\s-]*54a\b", plain)),
        "election_notice": bool("election" in plain and re.search(r"\bsections?\s+5[45]\b", plain)),
        "business_development_company_phrase": "business development company" in plain,
        "investment_company_act": "investment company act" in plain,
        "withdrawal_phrase": "withdraw" in plain and "election" in plain,
    }
    n54a_consistent = bool(detected["form_n54a_heading"] and
                           detected["election_notice"] and
                           detected["business_development_company_phrase"] and
                           detected["investment_company_act"])
    return {"form_text_signals": detected, "n54a_text_consistent": n54a_consistent,
            "document_bytes": len(raw), "sha256": sha256(raw).hexdigest()}


def load_frozen_elections(source: Path) -> tuple[list[dict], dict]:
    """Verify the exact 303-CIK A5c report and all raw SEC submission hashes."""
    encoded = (source / "edgar-pilot.json").read_bytes()
    if sha256(encoded).hexdigest() != A5C_REPORT_SHA256:
        raise A5dEvidenceError("Frozen A5c report SHA mismatch")
    obj = json.loads(encoded.decode("utf-8"))
    if (obj.get("status") != "CAPTURE_VALIDATED_REVIEW_ONLY"
            or obj.get("production_eligible") is not False
            or obj.get("successful_cik_count") != EXPECTED_A5C_ISSUERS
            or obj.get("failed_cik_count") != 0
            or obj.get("auto_approved_instruments") != 0):
        raise A5dEvidenceError("A5c receipt not complete/approved for review")
    rows = obj.get("selected_evidence")
    if not isinstance(rows, list) or len(rows) != EXPECTED_A5C_ISSUERS:
        raise A5dEvidenceError("Incomplete A5c issuer sources")
    selection = []
    for item in rows:
        if (item.get("production_eligible") is not False
                or item.get("cik_to_listed_security_approved") is not False):
            raise A5dEvidenceError("Unexpected approved A5c issuer")
        if "N-54A" not in item.get("form_types_found_in_recent_window", []):
            continue
        cik, digest = item["cik"], item["sec_sha256"]
        if not re.fullmatch(r"[0-9]{10}", cik) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise A5dEvidenceError("Invalid SEC source identity/hash")
        raw = (source / f"CIK{cik}-{digest}.json").read_bytes()
        if sha256(raw).hexdigest() != digest:
            raise A5dEvidenceError("Stored SEC JSON checksum mismatch")
        snap = parse_submissions(
            raw, expected_cik=cik,
            fetched_at=datetime.fromisoformat(item["retrieved_at"]))
        if snap.sha256 != digest or snap.filer_name != item["sec_filer_name"]:
            raise A5dEvidenceError("Frozen SEC filer identity mismatch")
        filings = form_records(raw, cik)
        elections = [e for e in filings if e["form"] in ("N-54A", "N-54A/A")]
        if not elections:
            raise A5dEvidenceError("Missing original N-54A in full SEC recent")
        if bool(item["older_history_files_not_downloaded"]) != bool(snap.historical_files):
            raise A5dEvidenceError("SEC historical source metadata disagreement")
        selection.append({
            "cik": cik, "ticker_candidates": item["directory_tickers"],
            "filer_name": snap.filer_name, "submissions_sha256": digest,
            "submissions_retrieved_at": item["retrieved_at"],
            "historical_files_not_downloaded": list(snap.historical_files),
            "filings": filings,
        })
    if len(selection) != EXPECTED_ELECTION_ISSUERS or len({x["cik"] for x in selection}) != len(selection):
        raise A5dEvidenceError("Unexpected N-54A issuer cohort size")
    return sorted(selection, key=lambda x: x["cik"]), {
        "a5c_report_sha256": A5C_REPORT_SHA256,
        "a5c_source_issuers": EXPECTED_A5C_ISSUERS,
        "n54a_issuer_candidates": len(selection),
        "incomplete_history_for_election_issuers": sum(
            bool(x["historical_files_not_downloaded"]) for x in selection),
    }


def fetch_document(url: str, agent: str) -> bytes:
    if not re.fullmatch(
        r"https://www\.sec\.gov/Archives/edgar/data/[1-9][0-9]*/[0-9]{18}/"
        r"[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._-]+)*", url
    ):
        raise A5dEvidenceError("Unapproved SEC document URL")
    req = Request(url, headers={"User-Agent": validate_user_agent(agent),
                                "Accept": "text/html,text/plain",
                                "Accept-Encoding": "identity"})
    with build_opener(NoRedirect()).open(req, timeout=25) as response:
        if response.geturl() != url:
            raise A5dEvidenceError("Redirect not approved")
        raw = response.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise A5dEvidenceError("SEC document exceeds size limit")
    return raw


def run_audit(source: Path, output: Path, *, agent: str, fetcher=fetch_document,
              clock=lambda: datetime.now(timezone.utc), pause=time.sleep) -> dict:
    validate_user_agent(agent)
    cohort, provenance = load_frozen_elections(source)
    output.mkdir(parents=True, exist_ok=False)
    findings, failures = [], []
    failures_in_row = 0
    for i, row in enumerate(cohort):
        # A5d collects every original N-54A/A primary document. A5c supplies
        # full, pinned filing metadata. N-54C is only searched in submissions,
        # not treated as absent if history might be incomplete.
        all_elections = [f for f in row["filings"] if f["form"] in ("N-54A", "N-54A/A")]
        withdrawals = [f for f in row["filings"] if f["form"] in ("N-54C", "N-54C/A")]
        documents = []
        for j, form in enumerate(all_elections):
            if i or j:
                pause(INTER_REQUEST_SECONDS)
            try:
                raw = fetcher(form["url"], agent)
                evidence = inspect_document(raw)
                if not evidence["n54a_text_consistent"]:
                    raise A5dEvidenceError("SEC document lacks N-54A text signals")
                digest = evidence["sha256"]
                (output / f"CIK{row['cik']}-{form['accession']}-{digest}.html").write_bytes(raw)
                documents.append({**form, **evidence, "status": "FORM_TEXT_SIGNAL_VERIFIED",
                                  "source_retrieved_at": clock().isoformat()})
                failures_in_row = 0
            except (OSError, ValueError, TimeoutError) as exc:
                failures.append({"cik": row["cik"], "accession": form["accession"],
                                 "error_type": type(exc).__name__,
                                 "error": str(exc)[:180]})
                documents.append({**form, "status": "SOURCE_NOT_VERIFIED",
                                  "n54a_text_consistent": False})
                failures_in_row += 1
                # Stop instead of repeatedly requesting a blocked SEC endpoint.
                if failures_in_row >= 2:
                    break
        findings.append({
            **{k: v for k, v in row.items() if k != "filings"},
            "election_filings": documents,
            "withdrawal_filing_metadata_observed": withdrawals,
            "withdrawal_absence_proven": False,
            "current_bdc_status": "UNDETERMINED",
            "listed_security_share_class": "REVIEW_REQUIRED",
            "production_eligible": False,
        })
        if failures_in_row >= 2:
            break
    status = ("DOCUMENT_EVIDENCE_CAPTURED_REVIEW_ONLY"
              if len(findings) == EXPECTED_ELECTION_ISSUERS and not failures
              else "PARTIAL_DOCUMENT_EVIDENCE_REVIEW_ONLY")
    summary = {
        "status": status, "production_eligible": False,
        "provenance": provenance,
        "issuer_documents_attempted": len(findings),
        "original_cohort_issuers": EXPECTED_ELECTION_ISSUERS,
        "verified_n54a_primary_documents": sum(
            d["status"] == "FORM_TEXT_SIGNAL_VERIFIED"
            for e in findings for d in e["election_filings"]),
        "document_fetch_failures": len(failures),
        "n54c_forms_observed_in_16_filer_recent": sum(
            len(e["withdrawal_filing_metadata_observed"]) for e in findings),
        "not_proof_of_no_n54c": True,
        "current_bdc_status_approved": 0,
        "security_share_class_approved": 0,
        "production_approved": 0,
        "failures": failures,
        "findings": findings,
    }
    (output / "a5d-election-evidence.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in {"findings", "failures"}},
                     indent=2))
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a5c-artifact", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    import os
    try:
        result = run_audit(args.a5c_artifact, args.output,
                           agent=os.environ.get("SEC_USER_AGENT", ""))
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"A5D_BLOCKED: {exc}")
        return 2
    return 0 if result["status"] == "DOCUMENT_EVIDENCE_CAPTURED_REVIEW_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
