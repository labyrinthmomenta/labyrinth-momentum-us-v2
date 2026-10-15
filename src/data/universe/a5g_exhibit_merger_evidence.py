"""A5g — SEC original exhibit index and merger evidence, REVIEW_ONLY.

Frozen input: A5f's 40 original SEC 8-K documents. Retrieve *official*
filing-detail indexes for every Item 9.01 filing, then text exhibits for
five prioritized accessions and LIEN's earlier 2026-06-18 merger agreement.
A filing, agreement or text hit NEVER proves closing or share-class change.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
from urllib.request import Request, build_opener

from .a5c_edgar_pilot import CUTOFF
from .a5f_corporate_events import _plain_text
from .sec_capture import NoRedirect, validate_user_agent

A5F_SHA256 = "c5b91a0c0b886b2baf19dfc9c5891de9465b846ae9ef0055eeffcca869512b70"
EXPECTED_8K = 40
EXPECTED_ITEM901 = 33
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_EXHIBIT_BYTES = 8 * 1024 * 1024
PAUSE_SECONDS = 0.75
PRIORITY_CASES = {
    "0001213900-26-088673": "LIEN_PROPOSED_MERGER_UPDATE",
    "0001213900-26-108523": "SAR_ITEM_1_01",
    "0001193125-26-378418": "PNNT_ITEM_1_01",
    "0001437749-26-029978": "HRZN_ITEM_1_01",
    "0001193125-26-385210": "OBDC_ITEM_1_01",
}
HISTORIC_LIEN_MERGER = {
    "cik": "0001843162",
    "accession": "0001213900-26-069853",
    "filing_date": "2026-06-18",
    "case": "LIEN_REFI_2026_06_SIGNED_AGREEMENT",
}
SEC_ARCHIVE_RE = re.compile(
    r"https://www\.sec\.gov/Archives/edgar/data/([1-9][0-9]*)/"
    r"([0-9]{18})/([A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*)"
)
EXHIBIT_TYPE_RE = re.compile(r"EX-[0-9]{1,3}(?:\.[0-9A-Za-z.-]+)?")
FILING_ACC_RE = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}")


class A5gEvidenceError(ValueError):
    pass


def validate_archive_url(url: str, *, cik: str, accession: str) -> str:
    if (not isinstance(cik, str) or not re.fullmatch(r"[0-9]{10}", cik)
            or not FILING_ACC_RE.fullmatch(accession)):
        raise A5gEvidenceError("Bad CIK or SEC filing accession")
    match = SEC_ARCHIVE_RE.fullmatch(url)
    if (not match or int(match.group(1)) != int(cik)
            or match.group(2) != accession.replace("-", "")
            or any(p in (".", "..") for p in match.group(3).split("/"))):
        raise A5gEvidenceError("Unsafe or incorrect SEC source location")
    return url


def filing_index_url(cik: str, accession: str) -> str:
    name = f"{accession}-index.htm"
    return validate_archive_url(
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession.replace('-', '')}/{name}", cik=cik, accession=accession)


def file_url(cik: str, accession: str, filename: str) -> str:
    if (not isinstance(filename, str)
            or not re.fullmatch(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*", filename)
            or any(p in (".", "..") for p in filename.split("/"))):
        raise A5gEvidenceError("Unsafe SEC index document filename")
    return validate_archive_url(
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession.replace('-', '')}/{filename}",
        cik=cik, accession=accession)


class FilingIndexHTML(HTMLParser):
    """Read only SEC Document Format Files tables and their structured rows."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_document_table = False
        self.in_row = False
        self.in_cell = False
        self.rows: list[list[dict]] = []
        self.cells: list[dict] = []
        self.fragments: list[str] = []
        self.cell_href: str | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and not self.in_document_table:
            if ("document format files" in attrs.get("summary", "").lower()
                    or "tablefile" in attrs.get("class", "").lower()):
                self.in_document_table = True
        elif tag == "tr" and self.in_document_table:
            self.in_row = True
            self.cells = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.fragments = []
            self.cell_href = None
        elif tag == "a" and self.in_cell:
            self.cell_href = attrs.get("href")

    def handle_data(self, text):
        if self.in_cell:
            self.fragments.append(text)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_cell:
            self.cells.append({"text": " ".join(" ".join(self.fragments).split()),
                               "href": self.cell_href})
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.cells:
                self.rows.append(self.cells)
            self.in_row = False
        elif tag == "table" and self.in_document_table:
            self.in_document_table = False


def parse_filing_index(raw: bytes, *, cik: str, accession: str) -> list[dict]:
    if not isinstance(raw, bytes) or not 200 <= len(raw) <= MAX_INDEX_BYTES:
        raise A5gEvidenceError("SEC filing detail HTML absent/oversized")
    html = raw.decode("utf-8", errors="replace")
    flat = " ".join(unescape(re.sub(r"<[^>]*>", " ", html)).split())
    if (not re.search(r"\bFiling Detail\b", flat, re.I)
            or accession not in flat
            or "Document Format Files" not in flat):
        raise A5gEvidenceError("SEC filing detail identity/source not verified")
    parser = FilingIndexHTML()
    parser.feed(html)
    entries, unique = [], set()
    for cells in parser.rows:
        if len(cells) < 5:
            continue
        doc_type = cells[3]["text"].upper()
        if not EXHIBIT_TYPE_RE.fullmatch(doc_type) or doc_type.startswith("EX-101"):
            continue
        # Use SEC document anchor, but reconstruct and validate fixed SEC URL
        # rather than following potentially arbitrary hrefs.
        linked = cells[2]["href"]
        if not linked:
            raise A5gEvidenceError("Official SEC exhibit row has no document link")
        if "?" in linked or "#" in linked or "%" in linked or "\\" in linked:
            raise A5gEvidenceError("Unexpected SEC exhibit hyperlink")
        filename = linked.rsplit("/", 1)[-1]
        if filename in unique:
            raise A5gEvidenceError("Duplicate exhibit filename in SEC index")
        unique.add(filename)
        url = file_url(cik, accession, filename)
        if (linked.startswith("http") and linked != url):
            raise A5gEvidenceError("Unexpected external SEC exhibit anchor")
        if linked.startswith("/Archives/") and not url.endswith(linked.split("/")[-1]):
            raise A5gEvidenceError("Unexpected exhibit anchor path")
        entries.append({
            "seq": cells[0]["text"],
            "description": cells[1]["text"][:350],
            "filename": filename,
            "type": doc_type,
            "url": url,
            "declared_size": cells[4]["text"],
            "text_candidate": filename.lower().endswith((".htm", ".html", ".txt")),
            "security_identity_approved": False,
        })
    return entries


def inspect_exhibit(raw: bytes, *, doc_type: str) -> dict:
    if not isinstance(raw, bytes) or not 80 <= len(raw) <= MAX_EXHIBIT_BYTES:
        raise A5gEvidenceError("SEC exhibit empty or oversized")
    content = _plain_text(raw)
    if len(content) < 80 or re.search(
        r"^(?:access denied|request rate threshold exceeded|forbidden|error\s*403)\b",
        content[:160].casefold()
    ):
        raise A5gEvidenceError("SEC exhibit text not validated")
    phrases = {
        "AGREEMENT_AND_PLAN_OF_MERGER": bool(re.search(
            r"\bagreement and plan of merger\b", content, re.I)),
        "PROPOSED_MERGER": bool(re.search(
            r"\b(?:proposed merger|subject to (?:stockholder|shareholder) approval)\b",
            content, re.I)),
        "CLOSING_LANGUAGE_NEEDS_CONTEXT": bool(re.search(
            r"\b(?:completion of the merger|closing of the merger|effective time)\b",
            content, re.I)),
        "LISTING_CHANGE_WORDING": bool(re.search(
            r"\b(?:delisting|trading symbol change|new ticker symbol)\b", content, re.I)),
    }
    return {
        "sha256": sha256(raw).hexdigest(), "bytes": len(raw),
        "filing_type": doc_type,
        "text_evidence_clues_not_event_facts": phrases,
        "preview_for_manual_review": content[:450],
        "event_closing_confirmed": False,
        "security_identity_change_confirmed": False,
        "production_eligible": False,
    }


def load_a5f(a5f_path: Path) -> tuple[list[dict], dict]:
    raw = (a5f_path / "a5f-8k-evidence.json").read_bytes()
    if sha256(raw).hexdigest() != A5F_SHA256:
        raise A5gEvidenceError("Frozen A5f audit SHA mismatch")
    doc = json.loads(raw.decode("utf-8"))
    if (doc.get("status") != "ALL_SOURCES_CAPTURED_REVIEW_ONLY"
            or doc.get("production_eligible") is not False
            or doc.get("expected_event_filings") != EXPECTED_8K
            or doc.get("primary_documents_verified") != EXPECTED_8K
            or doc.get("source_failures") != []
            or doc.get("event_occurred_confirmed") != 0
            or doc.get("production_approvals") != 0
            or doc.get("human_review_complete") is not False):
        raise A5gEvidenceError("A5f is not a complete review-only source")
    rows = doc.get("findings")
    if not isinstance(rows, list) or len(rows) != EXPECTED_8K:
        raise A5gEvidenceError("A5f filing inventory missing")
    to_index, accs, priority_seen = [], set(), set()
    for row in rows:
        if (row.get("status") != "SEC_8K_PRIMARY_TEXT_REVIEW_CANDIDATE"
                or row.get("production_eligible") is not False
                or row.get("event_occurred_confirmed") is not False
                or row.get("post_financial_events_checked") is not False):
            raise A5gEvidenceError("Unexpected A5f decision status")
        key = (row["cik"], row["accession"])
        if key in accs:
            raise A5gEvidenceError("Duplicate A5f filing accession")
        accs.add(key)
        digest = row["sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise A5gEvidenceError("Invalid original 8-K source checksum")
        original = (a5f_path / row["raw_artifact_filename"]).read_bytes()
        if sha256(original).hexdigest() != digest or len(original) != row["document_bytes"]:
            raise A5gEvidenceError("Tampered original A5f SEC document")
        validate_archive_url(row["document_url"], cik=row["cik"], accession=row["accession"])
        if date.fromisoformat(row["filing_date"]) > CUTOFF:
            raise A5gEvidenceError("Post-cutoff 8-K incorrectly included")
        if row["accession"] in PRIORITY_CASES:
            priority_seen.add(row["accession"])
        if "9.01" in row["item_headings_observed"]:
            to_index.append({
                "cik": row["cik"], "ticker_candidates": row["ticker_candidates"],
                "accession": row["accession"], "filing_date": row["filing_date"],
                "priority_case": PRIORITY_CASES.get(row["accession"]),
                "index_url": filing_index_url(row["cik"], row["accession"]),
                "source_primary_sha256": digest,
            })
    if len(to_index) != EXPECTED_ITEM901 or priority_seen != set(PRIORITY_CASES):
        raise A5gEvidenceError("Frozen A5f Item 9.01 / priority population changed")
    if not all(any(row["accession"] == x and row["priority_case"]
                   for row in to_index) for x in PRIORITY_CASES):
        raise A5gEvidenceError("Priority Item 9.01 filing missing")
    return to_index, {
        "a5f_source_sha256": A5F_SHA256,
        "review_as_of": CUTOFF.isoformat(),
        "all_a5f_original_8k_reverified": EXPECTED_8K,
        "item901_filing_indexes_to_fetch": EXPECTED_ITEM901,
        "priority_accessions": sorted(PRIORITY_CASES),
    }


def official_fetch(url: str, agent: str, *, size_cap: int) -> bytes:
    match = SEC_ARCHIVE_RE.fullmatch(url)
    if not match or any(part in (".", "..") for part in match.group(3).split("/")):
        raise A5gEvidenceError("Disallowed SEC file URL")
    request = Request(url, headers={
        "User-Agent": validate_user_agent(agent),
        "Accept": "text/html,text/plain",
        "Accept-Encoding": "identity",
    })
    with build_opener(NoRedirect()).open(request, timeout=35) as response:
        if response.geturl() != url:
            raise A5gEvidenceError("SEC source redirected")
        body = response.read(size_cap + 1)
    if len(body) > size_cap:
        raise A5gEvidenceError("SEC source exceeds strict size cap")
    return body


def run_audit(a5f: Path, output: Path, *, agent: str, fetcher=official_fetch,
              clock=lambda: datetime.now(timezone.utc), pause=time.sleep) -> dict:
    validate_user_agent(agent)
    filings, provenance = load_a5f(a5f)
    historic = {
        **HISTORIC_LIEN_MERGER,
        "index_url": filing_index_url(
            HISTORIC_LIEN_MERGER["cik"], HISTORIC_LIEN_MERGER["accession"]),
        "priority_case": HISTORIC_LIEN_MERGER["case"],
        "historical_pre_10q_checkpoint": True,
        "ticker_candidates": ["LIEN"],
    }
    queue = filings + [historic]
    output.mkdir(parents=True, exist_ok=False)
    records, failures = [], []
    exhibit_files_checked = 0
    for filing_index, filing in enumerate(queue):
        if filing_index:
            pause(PAUSE_SECONDS)
        response = {
            **filing,
            "index_source_verified": False, "index_exhibits": [],
            "indexed_exhibit_count": 0, "text_exhibits_verified": 0,
            "unreviewed_exhibits": [],
            "human_review_status": "REVIEW_REQUIRED",
            "merger_completion_confirmed": False,
            "ticker_change_confirmed": False, "production_eligible": False,
        }
        try:
            index_raw = fetcher(filing["index_url"], agent, size_cap=MAX_INDEX_BYTES)
            exhibits = parse_filing_index(index_raw, cik=filing["cik"],
                                           accession=filing["accession"])
            index_hash = sha256(index_raw).hexdigest()
            (output / f"{filing['accession']}-index-{index_hash}.htm").write_bytes(index_raw)
            response["index_source_verified"] = True
            response["index_sha256"] = index_hash
            response["index_retrieved_at"] = clock().isoformat()
            response["index_exhibits"] = exhibits
            response["indexed_exhibit_count"] = len(exhibits)
            priority = bool(filing.get("priority_case"))
            for exhib in exhibits:
                if not priority or not exhib["text_candidate"]:
                    response["unreviewed_exhibits"].append({
                        "type": exhib["type"], "url": exhib["url"],
                        "reason": ("METADATA_ONLY_NOT_PRIORITY" if not priority
                                   else "NON_TEXT_EXHIBIT_NOT_PARSED"),
                    })
                    continue
                pause(PAUSE_SECONDS)
                try:
                    raw = fetcher(exhib["url"], agent, size_cap=MAX_EXHIBIT_BYTES)
                    checked = inspect_exhibit(raw, doc_type=exhib["type"])
                    name = (f"{filing['accession']}-{exhib['filename'].replace('/','_')}-"
                            f"{checked['sha256']}.html")
                    (output / name).write_bytes(raw)
                    exhib["review_evidence"] = {
                        **checked, "retrieved_at": clock().isoformat(),
                        "saved_filename": name, "status": "TEXT_CAPTURED_REVIEW_REQUIRED",
                    }
                    response["text_exhibits_verified"] += 1
                    exhibit_files_checked += 1
                except (OSError, ValueError, TimeoutError) as exc:
                    failures.append({
                        "accession": filing["accession"], "file": exhib["filename"],
                        "error": f"{type(exc).__name__}: {exc}"[:220],
                    })
                    exhib["review_evidence"] = {"status": "SOURCE_NOT_VERIFIED",
                                                "production_eligible": False}
        except (OSError, ValueError, TimeoutError) as exc:
            failures.append({"accession": filing["accession"], "file": "FILING_INDEX",
                             "error": f"{type(exc).__name__}: {exc}"[:220]})
        records.append(response)
        if len(failures) >= 3:
            break
    complete = (len(records) == EXPECTED_ITEM901 + 1
                and not failures
                and all(row["index_source_verified"] for row in records))
    result = {
        "status": "INDEXES_CAPTURED_REVIEW_ONLY" if complete else "PARTIAL_CAPTURE_REVIEW_ONLY",
        "production_eligible": False, "source_provenance": provenance,
        "expected_9_01_indexes": EXPECTED_ITEM901, "historical_lien_merger_index": 1,
        "official_indexes_verified": sum(x["index_source_verified"] for x in records),
        "exhibits_discovered": sum(x["indexed_exhibit_count"] for x in records),
        "priority_text_exhibits_verified": exhibit_files_checked,
        "index_source_errors": failures,
        "still_metadata_only_exhibits": sum(len(x["unreviewed_exhibits"]) for x in records),
        "human_review_complete": False,
        "merger_closed_confirmed": False, "n54c_absence_proven": False,
        "issuer_bdc_status_approved": 0, "share_class_approved": 0,
        "production_approved": 0, "filing_records": records,
    }
    (output / "a5g-exhibits-and-merger.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in {"filing_records", "index_source_errors"}}, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a5f-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_audit(args.a5f_artifact, args.output,
                           agent=os.environ.get("SEC_USER_AGENT", ""))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"A5G_BLOCKED: {exc}")
        return 2
    return 0 if result["status"] == "INDEXES_CAPTURED_REVIEW_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
