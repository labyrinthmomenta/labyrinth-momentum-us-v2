"""A5h: finish SEC exhibit downloads and LIEN/REFI regulatory filing timeline.

Outputs are dated evidence and review cues, not merger closing, live BDC,
share-class, trading-universe or production eligibility determinations.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import time
from urllib.request import Request, build_opener

from .a5g_exhibit_merger_evidence import (
    inspect_exhibit, parse_filing_index, validate_archive_url,
    A5gEvidenceError, MAX_EXHIBIT_BYTES,
)
from .a5f_corporate_events import _plain_text
from .sec_capture import NoRedirect, validate_user_agent

A5G_REPORT_SHA256 = "58ed3bee2f66e14bbc6930747569388b1b28f127927a6125377b3cf6cda184f5"
A5G_INDEXES = 34
A5G_EXHIBITS = 46
A5G_VERIFIED_EXHIBITS = 17
EXPECTED_REMAINING = 29
LIEN_CIK = "0001843162"
REFI_CIK = "0001867949"
AS_OF = date(2026, 10, 14)
MERGER_START = date(2026, 6, 17)
PAUSE_SECONDS = 0.75
MAX_SUBMISSIONS_BYTES = 12 * 1024 * 1024
MAX_REGISTRATION_BYTES = 32 * 1024 * 1024
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/"
PRIORITY_FORMS = frozenset({
    "N-14", "N-14/A", "N-14 8C", "N-14 8C/A",
    "EFFECT", "DEFM14A", "DEF14A", "DEFA14A", "PRE14A",
    "N-54A", "N-54C", "8-K", "8-K/A", "425",
})


class A5hEvidenceError(ValueError):
    pass


def load_a5g(root: Path) -> tuple[list[dict], dict]:
    source = (root / "a5g-exhibits-and-merger.json").read_bytes()
    if sha256(source).hexdigest() != A5G_REPORT_SHA256:
        raise A5hEvidenceError("Frozen A5g report SHA256 mismatch")
    doc = json.loads(source.decode("utf-8"))
    if (doc.get("status") != "INDEXES_CAPTURED_REVIEW_ONLY"
            or doc.get("production_eligible") is not False
            or doc.get("official_indexes_verified") != A5G_INDEXES
            or doc.get("exhibits_discovered") != A5G_EXHIBITS
            or doc.get("priority_text_exhibits_verified") != A5G_VERIFIED_EXHIBITS
            or doc.get("still_metadata_only_exhibits") != EXPECTED_REMAINING
            or doc.get("merger_closed_confirmed") is not False
            or doc.get("production_approved") != 0
            or doc.get("human_review_complete") is not False
            or doc.get("index_source_errors")):
        raise A5hEvidenceError("A5g report not complete/review-only")
    filings = doc.get("filing_records")
    if not isinstance(filings, list) or len(filings) != A5G_INDEXES:
        raise A5hEvidenceError("A5g filing records missing")
    missing, verified, total = [], 0, 0
    seen = set()
    for record in filings:
        cik, accession = record["cik"], record["accession"]
        if (cik, accession) in seen or not record.get("index_source_verified"):
            raise A5hEvidenceError("Duplicate or unverified SEC filing index")
        seen.add((cik, accession))
        if record.get("production_eligible") is not False:
            raise A5hEvidenceError("Source filing unexpectedly approved")
        digest = record["index_sha256"]
        index_raw = (root / f"{accession}-index-{digest}.htm").read_bytes()
        if sha256(index_raw).hexdigest() != digest:
            raise A5hEvidenceError("Original SEC filing index SHA mismatch")
        from_index = parse_filing_index(index_raw, cik=cik, accession=accession)
        exhibits = record["index_exhibits"]
        if [(e["url"], e["type"]) for e in from_index] != [
                (e["url"], e["type"]) for e in exhibits]:
            raise A5hEvidenceError("Index EX-* entries changed from original SEC HTML")
        total += len(exhibits)
        for e in exhibits:
            validate_archive_url(e["url"], cik=cik, accession=accession)
            if "review_evidence" in e:
                evidence = e["review_evidence"]
                if evidence["status"] != "TEXT_CAPTURED_REVIEW_REQUIRED":
                    raise A5hEvidenceError("A5g exhibit previously rejected")
                raw = (root / evidence["saved_filename"]).read_bytes()
                if sha256(raw).hexdigest() != evidence["sha256"] or len(raw) != evidence["bytes"]:
                    raise A5hEvidenceError("Original SEC exhibit SHA/size mismatch")
                verified += 1
        for entry in record["unreviewed_exhibits"]:
            url = validate_archive_url(entry["url"], cik=cik, accession=accession)
            exhibit = [e for e in exhibits if e["url"] == url
                       and e["type"] == entry["type"] and "review_evidence" not in e]
            if len(exhibit) != 1 or not exhibit[0].get("text_candidate"):
                raise A5hEvidenceError("Unreviewed SEC exhibit does not match official index")
            if url in {e["url"] for e in missing}:
                raise A5hEvidenceError("Duplicate unreviewed SEC source URL")
            missing.append({
                "cik": cik, "accession": accession, "filing_date": record["filing_date"],
                "ticker_candidates": record["ticker_candidates"],
                "type": entry["type"], "url": url,
                "index_sha256": digest,
                "source_a5g_sha256": A5G_REPORT_SHA256,
                "production_eligible": False,
            })
    if len(missing) != EXPECTED_REMAINING or total != A5G_EXHIBITS or verified != A5G_VERIFIED_EXHIBITS:
        raise A5hEvidenceError("Frozen A5g full exhibit inventory mismatch")
    return missing, {
        "a5g_report_sha256": A5G_REPORT_SHA256,
        "verified_source_indexes": A5G_INDEXES,
        "previously_verified_exhibits": verified,
        "remaining_verified_index_entries": len(missing),
        "listed_source_as_of": AS_OF.isoformat(),
    }


def submissions_url(cik: str) -> str:
    if cik not in (LIEN_CIK, REFI_CIK):
        raise A5hEvidenceError("Unapproved merger issuer CIK")
    return f"{SEC_SUBMISSIONS_URL}CIK{cik}.json"


def parse_submissions_timeline(raw: bytes, *, cik: str, retrieved_at: datetime) -> dict:
    submissions_url(cik)
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise A5hEvidenceError("Missing SEC retrieval timezone")
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_SUBMISSIONS_BYTES:
        raise A5hEvidenceError("SEC submissions response empty or oversized")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise A5hEvidenceError("Malformed SEC submissions JSON") from exc
    if not isinstance(data, dict) or str(data.get("cik")) != str(int(cik)):
        raise A5hEvidenceError("SEC submissions filer identity mismatch")
    forms = data.get("filings")
    if not isinstance(forms, dict) or not isinstance(forms.get("recent"), dict):
        raise A5hEvidenceError("SEC filings.recent missing")
    recent = forms["recent"]
    cols = ("form", "filingDate", "accessionNumber", "primaryDocument")
    if any(not isinstance(recent.get(c), list) for c in cols):
        raise A5hEvidenceError("Missing SEC filing array columns")
    n = len(recent["form"])
    if not all(len(recent[c]) == n for c in cols):
        raise A5hEvidenceError("Misaligned SEC filing columns")
    older = forms.get("files")
    if not isinstance(older, list):
        raise A5hEvidenceError("SEC submissions history descriptor missing")
    filings = []
    for i in range(n):
        typ, day, accession, doc = (recent[c][i] for c in cols)
        if not isinstance(typ, str) or not isinstance(day, str):
            raise A5hEvidenceError("Malformed SEC form/date")
        try:
            d = date.fromisoformat(day)
        except ValueError as exc:
            raise A5hEvidenceError("Malformed filingDate") from exc
        if d > AS_OF or d < MERGER_START or typ not in PRIORITY_FORMS:
            continue
        if not isinstance(accession, str) or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
            raise A5hEvidenceError("Malformed SEC accession")
        if not isinstance(doc, str):
            raise A5hEvidenceError("SEC primaryDocument invalid")
        safe_doc = bool(re.fullmatch(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*", doc)
                        and all(part not in (".", "..") for part in doc.split("/")))
        document_url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                        f"{accession.replace('-', '')}/{doc}") if safe_doc else None
        if not safe_doc and doc:
            raise A5hEvidenceError("Unsafe SEC primaryDocument")
        if document_url:
            validate_archive_url(document_url, cik=cik, accession=accession)
        filings.append({
            "form": typ, "filing_date": day, "accession": accession,
            "primary_document_url": document_url,
            "primary_filing_document_read": False,
            "security_id_approved": False,
            "merger_closed": False,
        })
    filings.sort(key=lambda x: (x["filing_date"], x["accession"]), reverse=True)
    return {
        "cik": cik, "sec_filer_name": data.get("name"),
        "retrieved_at": retrieved_at.isoformat(),
        "sha256": sha256(raw).hexdigest(),
        "older_submissions_history_file_count": len(older),
        "older_submissions_history_not_downloaded": bool(older),
        "cutoff_as_of": AS_OF.isoformat(), "filings": filings,
        "n14_filings": sum(f["form"].startswith("N-14") for f in filings),
        "effect_filings": sum(f["form"] == "EFFECT" for f in filings),
        "definitive_proxy_form_candidates": sum(f["form"].startswith("DEF") for f in filings),
        "n54a_observed_window": sum(f["form"] == "N-54A" for f in filings),
        "n54c_observed_window": sum(f["form"] == "N-54C" for f in filings),
        "source_is_point_in_time_proof": False,
        "voting_outcome_verified": False,
        "merger_closing_verified": False,
        "current_bdc_status_approved": False,
        "security_identity_approved": False,
    }


def retrieve_official(url: str, agent: str, *, max_bytes: int) -> bytes:
    if url.startswith(SEC_SUBMISSIONS_URL):
        target = url[len(SEC_SUBMISSIONS_URL):]
        if not re.fullmatch(r"CIK(?:0001843162|0001867949)\.json", target):
            raise A5hEvidenceError("Unapproved SEC submissions endpoint")
    else:
        from .a5g_exhibit_merger_evidence import SEC_ARCHIVE_RE
        match = SEC_ARCHIVE_RE.fullmatch(url)
        if not match or any(part in (".", "..") for part in match.group(3).split("/")):
            raise A5hEvidenceError("Unapproved SEC Archives URL")
    req = Request(url, headers={"User-Agent": validate_user_agent(agent),
                                "Accept": "application/json,text/html,text/plain",
                                "Accept-Encoding": "identity"})
    with build_opener(NoRedirect()).open(req, timeout=35) as response:
        if response.geturl() != url:
            raise A5hEvidenceError("SEC request redirected to unapproved source")
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise A5hEvidenceError("SEC data exceeded bounded source limit")
    return raw


def inspect_registration(raw: bytes) -> dict:
    if not isinstance(raw, bytes) or not 200 <= len(raw) <= MAX_REGISTRATION_BYTES:
        raise A5hEvidenceError("N-14/proxy source empty/oversized")
    text = _plain_text(raw)
    if len(text) < 300 or not re.search(r"\b(?:form\s*n\s*-?\s*14|proxy statement)\b", text, re.I):
        raise A5hEvidenceError("Expected SEC registration/proxy document not verified")
    clues = {
        "N14_REGISTRATION_LANGUAGE": bool(re.search(r"registration statement", text, re.I)),
        "JOINT_PROXY": bool(re.search(r"joint proxy statement", text, re.I)),
        "PRELIMINARY_LANGUAGE": bool(re.search(r"\bpreliminary\b", text[:15000], re.I)),
        "STOCKHOLDER_VOTE_REFERENCED": bool(re.search(r"stockholders?\s+(?:will be asked|are asked)\s+to\s+vote", text, re.I)),
        "MERGER_WORDING": bool(re.search(r"merger agreement|proposed merger", text, re.I)),
    }
    return {
        "sha256": sha256(raw).hexdigest(), "bytes": len(raw),
        "source_text_clues_for_human_review": clues,
        "voting_result_verified": False, "merger_completion_verified": False,
        "security_id_approved": False, "production_eligible": False,
    }


def audit(a5g: Path, out: Path, *, agent: str, fetcher=retrieve_official,
          clock=lambda: datetime.now(timezone.utc), pause=time.sleep) -> dict:
    validate_user_agent(agent)
    missing, provenance = load_a5g(a5g)
    out.mkdir(parents=True, exist_ok=False)
    evidence, errors = [], []
    requests_sent = 0

    def fetch_one(url: str, max_bytes: int) -> bytes:
        nonlocal requests_sent
        if requests_sent:
            pause(PAUSE_SECONDS)
        requests_sent += 1
        return fetcher(url, agent, max_bytes=max_bytes)

    for exhibit in missing:
        try:
            raw = fetch_one(exhibit["url"], MAX_EXHIBIT_BYTES)
            inspected = inspect_exhibit(raw, doc_type=exhibit["type"])
            retrieved = clock()
            if retrieved.tzinfo is None or retrieved.utcoffset() is None:
                raise A5hEvidenceError("SEC retrieval clock has no timezone")
            filename = (f"{exhibit['accession']}-"
                        f"{exhibit['url'].rsplit('/',1)[-1]}-{inspected['sha256']}.html")
            (out / filename).write_bytes(raw)
            evidence.append({
                **exhibit, **inspected, "status": "SEC_EXHIBIT_TEXT_REVIEW_REQUIRED",
                "retrieved_at": retrieved.isoformat(), "saved_filename": filename,
                "merger_or_listed_class_change_approved": False,
            })
        except (ValueError, OSError, TimeoutError) as exc:
            errors.append({
                "accession": exhibit["accession"], "source": exhibit["url"],
                "error": f"{type(exc).__name__}: {exc}"[:240],
            })
            evidence.append({**exhibit, "status": "EXHIBIT_SOURCE_UNVERIFIED",
                             "production_eligible": False})
        if len(errors) >= 3:
            break

    timelines = []
    registration_documents = []
    if not errors:
        for cik in (LIEN_CIK, REFI_CIK):
            url = submissions_url(cik)
            try:
                raw = fetch_one(url, MAX_SUBMISSIONS_BYTES)
                at = clock()
                timeline = parse_submissions_timeline(raw, cik=cik, retrieved_at=at)
                name = f"CIK{cik}-submissions-{timeline['sha256']}.json"
                (out / name).write_bytes(raw)
                timeline["original_file"] = name
                timelines.append(timeline)
            except (ValueError, OSError, TimeoutError) as exc:
                errors.append({"cik": cik, "source": url,
                               "error": f"{type(exc).__name__}: {exc}"[:240]})
    # Capture the most recent LIEN N-14 (only as text evidence).
    if not errors:
        lien = next(v for v in timelines if v["cik"] == LIEN_CIK)
        n14 = next((f for f in lien["filings"]
                    if f["form"].startswith("N-14") and f["primary_document_url"]), None)
        if n14:
            try:
                raw = fetch_one(n14["primary_document_url"], MAX_REGISTRATION_BYTES)
                evidence = inspect_registration(raw)
                at = clock()
                file = (f"LIEN-N14-{n14['accession']}-{evidence['sha256']}.html")
                (out / file).write_bytes(raw)
                registration_documents.append({
                    "cik": LIEN_CIK, **n14, **evidence, "original_file": file,
                    "retrieved_at": at.isoformat(),
                    "status": "N14_PRIMARY_DOC_REVIEW_ONLY",
                })
            except (ValueError, OSError, TimeoutError) as exc:
                errors.append({
                    "cik": LIEN_CIK, "source": n14["primary_document_url"],
                    "error": f"{type(exc).__name__}: {exc}"[:240],
                })
    # Never derive closing, active BDC or share-class status from form presence.
    success = (not errors and len(evidence) == EXPECTED_REMAINING
               and all(e["status"] == "SEC_EXHIBIT_TEXT_REVIEW_REQUIRED"
                       for e in evidence)
               and len(timelines) == 2
               and len(registration_documents) == 1)
    report = {
        "status": "DOCUMENTS_CAPTURED_REVIEW_ONLY" if success else "PARTIAL_REVIEW_ONLY",
        "provenance": provenance, "production_eligible": False,
        "exhibits_target": EXPECTED_REMAINING,
        "exhibits_verified": sum(e["status"] == "SEC_EXHIBIT_TEXT_REVIEW_REQUIRED"
                                for e in evidence),
        "merger_issuer_timelines_verified": len(timelines),
        "LIEN_N14_document_verified": len(registration_documents),
        "errors": errors,
        "merger_closed_confirmed": False, "voting_result_confirmed": False,
        "EFFECT_is_not_merger_closing": True,
        "point_in_time_known_at_not_established": True,
        "n54c_absence_proven": False,
        "issuer_bdc_approved": 0, "security_id_approved": 0,
        "production_approved": 0, "human_review_complete": False,
        "unreviewed_legal_conclusions": True,
        "exhibit_evidence": evidence,
        "issuer_timelines": timelines,
        "registration_docs": registration_documents,
    }
    (out / "a5h-exhibits-and-timeline.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("exhibit_evidence", "issuer_timelines",
                                   "registration_docs", "errors")},
                     indent=2, ensure_ascii=False))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a5g-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(args.a5g_artifact, args.output,
                       agent=os.environ.get("SEC_USER_AGENT", ""))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"A5H_BLOCKED: {exc}")
        return 2
    return 0 if result["status"] == "DOCUMENTS_CAPTURED_REVIEW_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
