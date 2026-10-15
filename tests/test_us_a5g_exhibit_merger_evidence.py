"""A5g SEC exhibit inventory, source validation and non-conclusive merger evidence."""
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from src.data.universe import a5g_exhibit_merger_evidence as mod

NOW = datetime(2026, 10, 15, 12, 45, tzinfo=timezone.utc)
CIK = "0001843162"
ACC = "0001213900-26-088673"
FAKE_EXHIBIT = (b"<html><body>EXHIBIT 2.1 AGREEMENT AND PLAN OF MERGER "
                b"this proposed merger is subject to shareholder approval. "
                b"The parties anticipate closing if required conditions are met. "
                b"This document does not establish a completed merger.</body></html>")


def index_html(accession: str, rows: list[tuple[str, str, str, str, str]]) -> bytes:
    parts = [
        "<html><body><h2>Filing Detail</h2>",
        f"<p>SEC Accession No. {accession}</p><h3>Document Format Files</h3>",
        '<table class="tableFile" summary="Document Format Files">',
        "<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>",
    ]
    for seq, desc, filename, typ, size in rows:
        parts.append(
            f"<tr><td>{seq}</td><td>{desc}</td>"
            f'<td><a href="/Archives/edgar/data/1843162/'
            f'{accession.replace("-", "")}/{filename}">{filename}</a></td>'
            f"<td>{typ}</td><td>{size}</td></tr>"
        )
    return ("".join(parts) + "</table></body></html>").encode()


def make_a5f(tmp_path, monkeypatch):
    # Complete 40 original filings with 33 Item 9.01. Include all five
    # actual priority accessions and a non-9.01 group of seven.
    priority = [
        ("0001843162", "0001213900-26-088673", "LIEN"),
        ("0001377936", "0001213900-26-108523", "SAR"),
        ("0001383414", "0001193125-26-378418", "PNNT"),
        ("0001487428", "0001437749-26-029978", "HRZN"),
        ("0001655888", "0001193125-26-385210", "OBDC"),
    ]
    items = priority[:]
    for i in range(35):
        items.append((f"{800000+i:010d}",f"{800000+i:010d}-26-{i+100:06d}",f"X{i:02d}"))
    rows = []
    for i, (cik, accession, ticker) in enumerate(items):
        filename = f"event{i}.htm"
        url = mod.file_url(cik, accession, filename)
        body = f"<html><body><h1>FORM 8-K {i}</h1>SEC Test</body></html>".encode()
        digest = sha256(body).hexdigest()
        name = f"CIK{cik}-{accession}-{digest}.html"
        (tmp_path/name).write_bytes(body)
        rows.append({
            "cik": cik, "accession": accession,
            "ticker_candidates": [ticker], "document_url": url,
            "form": "8-K", "filing_date": "2026-09-09",
            "item_headings_observed": ["9.01"] if i < 33 else ["2.02"],
            "raw_artifact_filename": name, "sha256": digest,
            "document_bytes": len(body), "event_occurred_confirmed": False,
            "post_financial_events_checked": False,
            "status": "SEC_8K_PRIMARY_TEXT_REVIEW_CANDIDATE",
            "production_eligible": False,
        })
    raw = json.dumps({
        "status": "ALL_SOURCES_CAPTURED_REVIEW_ONLY",
        "production_eligible": False, "expected_event_filings": 40,
        "primary_documents_verified": 40, "source_failures": [],
        "event_occurred_confirmed": 0, "production_approvals": 0,
        "human_review_complete": False, "findings": rows,
    }).encode()
    (tmp_path/"a5f-8k-evidence.json").write_bytes(raw)
    monkeypatch.setattr(mod, "A5F_SHA256", sha256(raw).hexdigest())
    return rows


def test_filing_detail_exhibits_are_verified_from_structured_table():
    raw = index_html(ACC, [
        ("1", "CURRENT REPORT", "current.htm", "8-K", "30000"),
        ("2", "MERGER AGREEMENT", "merger.htm", "EX-2.1", "90000"),
        ("3", "JOINT PRESS RELEASE", "release.htm", "EX-99.1", "5000"),
        ("4", "XBRL", "xbrl.xml", "EX-101.INS", "40000"),
        ("5", "GRAPHIC", "chart.jpg", "GRAPHIC", "12345"),
    ])
    entries = mod.parse_filing_index(raw, cik=CIK, accession=ACC)
    assert [entry["type"] for entry in entries] == ["EX-2.1", "EX-99.1"]
    assert all(entry["url"].startswith("https://www.sec.gov/Archives/edgar/data/")
               for entry in entries)
    assert all(entry["security_identity_approved"] is False for entry in entries)


def test_sec_filing_detail_error_html_or_wrong_accession_rejected():
    with pytest.raises(mod.A5gEvidenceError):
        mod.parse_filing_index(b"<html>Access Denied</html>" * 30,
                               cik=CIK, accession=ACC)
    raw = index_html("0001213900-26-123456", [
        ("1", "EXHIBIT", "ex99.htm", "EX-99.1", "500")])
    with pytest.raises(mod.A5gEvidenceError):
        mod.parse_filing_index(raw, cik=CIK, accession=ACC)


def test_untrusted_exhibit_anchor_and_path_traversal_not_accepted():
    html = index_html(ACC, [("1", "E", "ex99.htm", "EX-99.1", "1000")])
    malicious = html.replace(b"/Archives/edgar/data/1843162/000121390026088673/ex99.htm",
                             b"https://evil.test/ex99.htm")
    with pytest.raises(mod.A5gEvidenceError):
        mod.parse_filing_index(malicious, cik=CIK, accession=ACC)
    with pytest.raises(mod.A5gEvidenceError):
        mod.file_url(CIK, ACC, "../traversal.htm")
    with pytest.raises(mod.A5gEvidenceError):
        mod.validate_archive_url(
            "https://www.sec.gov/Archives/edgar/data/1843162/000121390026088673/../x.htm",
            cik=CIK, accession=ACC,
        )


def test_merger_agreement_wording_is_not_merger_closing():
    evidence = mod.inspect_exhibit(FAKE_EXHIBIT, doc_type="EX-2.1")
    assert evidence["text_evidence_clues_not_event_facts"]["AGREEMENT_AND_PLAN_OF_MERGER"]
    assert evidence["text_evidence_clues_not_event_facts"]["PROPOSED_MERGER"]
    assert evidence["event_closing_confirmed"] is False
    assert evidence["security_identity_change_confirmed"] is False


def test_html_denial_is_not_verified_as_exhibit():
    with pytest.raises(mod.A5gEvidenceError):
        mod.inspect_exhibit(b"<html>Access Denied</html>" * 80, doc_type="EX-99.1")


def test_a5f_input_requires_byte_for_byte_40_documents(tmp_path, monkeypatch):
    rows = make_a5f(tmp_path, monkeypatch)
    queue, evidence = mod.load_a5f(tmp_path)
    assert len(queue) == 33
    assert evidence["all_a5f_original_8k_reverified"] == 40
    assert {x["accession"] for x in queue}.issuperset(mod.PRIORITY_CASES)
    actual = tmp_path/rows[0]["raw_artifact_filename"]
    actual.write_bytes(actual.read_bytes() + b"!")
    with pytest.raises(mod.A5gEvidenceError, match="Tampered"):
        mod.load_a5f(tmp_path)


def test_missing_frozen_9_01_filing_is_fail_closed(tmp_path, monkeypatch):
    rows = make_a5f(tmp_path, monkeypatch)
    rows[0]["item_headings_observed"] = ["2.02"]
    raw = json.dumps({
        "status": "ALL_SOURCES_CAPTURED_REVIEW_ONLY",
        "production_eligible": False, "expected_event_filings": 40,
        "primary_documents_verified": 40, "source_failures": [],
        "event_occurred_confirmed": 0, "production_approvals": 0,
        "human_review_complete": False, "findings": rows,
    }).encode()
    (tmp_path/"a5f-8k-evidence.json").write_bytes(raw)
    monkeypatch.setattr(mod, "A5F_SHA256", sha256(raw).hexdigest())
    with pytest.raises(mod.A5gEvidenceError, match="population"):
        mod.load_a5f(tmp_path)


def test_live_pipeline_mock_index_and_selected_exhibits_no_approvals(tmp_path, monkeypatch):
    make_a5f(tmp_path, monkeypatch)
    calls = []
    def fetch(url, agent, *, size_cap):
        calls.append(url)
        if url.endswith("-index.htm"):
            accession = url.rsplit("/", 1)[-1].replace("-index.htm", "")
            return index_html(accession, [
                ("1", "CURRENT REPORT", "8k.htm", "8-K", "1000"),
                ("2", "Merger or press statement", "e.htm", "EX-99.1", "1200"),
            ])
        return FAKE_EXHIBIT
    result = mod.run_audit(
        tmp_path, tmp_path/"audit", agent="Labyrinth Research lab@example.com",
        fetcher=fetch, clock=lambda: NOW, pause=lambda _: None,
    )
    assert result["status"] == "INDEXES_CAPTURED_REVIEW_ONLY"
    assert result["official_indexes_verified"] == 34  # 33 + one historical
    assert result["exhibits_discovered"] == 34
    assert result["priority_text_exhibits_verified"] == 6
    assert result["still_metadata_only_exhibits"] == 28
    assert not result["merger_closed_confirmed"]
    assert not result["human_review_complete"]
    assert result["production_approved"] == 0
    assert len([x for x in calls if x.endswith("-index.htm")]) == 34


def test_source_access_failure_is_not_silent_approval(tmp_path, monkeypatch):
    make_a5f(tmp_path, monkeypatch)
    def blocked(url, agent, *, size_cap):
        raise OSError("SEC rate limited")
    result = mod.run_audit(
        tmp_path, tmp_path/"blocked", agent="Research test@example.com",
        fetcher=blocked, clock=lambda: NOW, pause=lambda _: None,
    )
    assert result["status"] == "PARTIAL_CAPTURE_REVIEW_ONLY"
    assert len(result["index_source_errors"]) == 3
    assert result["official_indexes_verified"] == 0
    assert result["production_approved"] == 0
