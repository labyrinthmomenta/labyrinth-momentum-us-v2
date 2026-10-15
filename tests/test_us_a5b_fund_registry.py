"""Synthetic SEC fund series/class tests; no type approval or investment decisions."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import pytest

from src.data.universe.a5_review import A4_HASHES
from src.data.universe.fund_registry import (
    FundEvidenceError, parse_funds, capture_funds, load_funds, SOURCE,
)
from src.data.universe.a5b_fund_review import enrich_fund_queue, name_clues

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)
AGENT = "LabyrinthMomentumUSV2 audit audit@example.com"


def raw(rows=None):
    if rows is None:
        rows = [[1287750, "S000001234", "C000001234", "ARCC"]]
    return json.dumps({"fields": ["cik", "seriesId", "classId", "symbol"],
                       "data": rows}).encode()


def fixture_rows():
    reasons = {
        "FINANCIAL_STATUS_REVIEW": 268,
        "FUND_NAME_REQUIRES_TYPE_EVIDENCE": 297,
        "SPAC_BDC_OR_FINANCIAL_REVIEW": 307,
        "TYPE_UNCONFIRMED": 128,
        "UNKNOWN_EXCHANGE_CODE": 10,
    }
    results = []
    for reason, count in reasons.items():
        for n in range(count):
            ticker = "ARCC" if reason == "FUND_NAME_REQUIRES_TYPE_EVIDENCE" and n == 0 else f"X{len(results):05d}"
            results.append({
                "source": "nasdaqlisted", "symbol": ticker, "name": "Example Common Stock",
                "mic": "XNAS", "original_reason": reason,
                "production_eligible": False, "security_type_approved": False,
                "listing_evidence_sha256": A4_HASHES["nasdaqlisted"],
                "sec_evidence_sha256": A4_HASHES["sec"],
                "issuer_match_candidate": {"cik_candidate": "0001287750"},
            })
    return results


def test_parse_SEC_fund_class_schema_and_cik_padding():
    snap = parse_funds(raw(), NOW)
    assert snap.classes[0].cik == "0001287750"
    assert snap.classes[0].series_id == "S000001234"
    assert snap.sha256 == hashlib.sha256(raw()).hexdigest()


@pytest.mark.parametrize("data", [
    b"<html>denied</html>",
    b"{}",
    json.dumps({"fields": ["symbol", "classId", "seriesId", "cik"], "data": [[1, 2, 3, 4]]}).encode(),
    raw([]),
    raw([[True, "S000001234", "C000001234", "X"]]),
    raw([[123, None, "C000001234", "X"]]),
    raw([[123, "S000001234", "C123", "X"]]),
    raw([[123, "S000001234", "C000001234", "X"], [123, "S000001234", "C000001234", "X"]]),
])
def test_reject_malformed_fund_file(data):
    with pytest.raises(FundEvidenceError):
        parse_funds(data, NOW)


def test_reject_naive_source_time():
    with pytest.raises(FundEvidenceError, match="timezone-aware"):
        parse_funds(raw(), NOW.replace(tzinfo=None))


def test_capture_sha_roundtrip_and_failed_source(tmp_path):
    output = tmp_path / "capture"
    res = capture_funds(output, AGENT, fetcher=lambda agent: raw(), clock=lambda: NOW)
    assert res["status"] == "CAPTURE_VALIDATED" and not res["production_eligible"]
    assert load_funds(output).sha256 == res["receipt"]["sha256"]
    with pytest.raises(FileExistsError):
        capture_funds(output, AGENT, fetcher=lambda agent: raw())
    bad = capture_funds(tmp_path / "fail", AGENT, fetcher=lambda agent: b"<html>blocked", clock=lambda: NOW)
    assert bad["status"] == "SOURCE_REJECTED"
    with pytest.raises(FundEvidenceError):
        load_funds(tmp_path / "fail")


def test_fund_receipt_tampering_fails(tmp_path):
    output = tmp_path / "capture"
    res = capture_funds(output, AGENT, fetcher=lambda agent: raw(), clock=lambda: NOW)
    (output / f"company_tickers_mf-{res['receipt']['sha256']}.json").write_bytes(raw([
        [1287750, "S000009999", "C000009999", "ARCC"]]))
    with pytest.raises(FundEvidenceError, match="SHA"):
        load_funds(output)


def test_all_1010_remain_review_required():
    snap = parse_funds(raw(), NOW)
    output = enrich_fund_queue(fixture_rows(), snap)
    assert output["instrument_review_total"] == 1010
    assert output["fund_ticker_match_status_counts"]["SEC_FUND_CLASS_CANDIDATE"] == 1
    assert output["fund_ticker_match_status_counts"]["NOT_IN_SEC_FUND_TICKER_FILE"] == 1009
    assert output["approved_instruments"] == 0
    assert all(row["classification_decision"] == "REVIEW_REQUIRED"
               and row["production_eligible"] is False
               for row in output["review_entries"])


def test_two_series_ticker_collision_is_review_not_assumed_unique():
    snap = parse_funds(raw([
        [1287750, "S000001234", "C000001234", "ARCC"],
        [2287750, "S000002345", "C000002345", "ARCC"],
    ]), NOW)
    o = enrich_fund_queue(fixture_rows(), snap)
    found = next(x for x in o["review_entries"] if x["ticker"] == "ARCC")
    assert found["sec_fund_status"] == "MULTIPLE_SEC_FUND_CLASSES_REVIEW"
    assert len(found["fund_class_candidates"]) == 2


def test_name_clues_are_nonexclusive_and_never_type_approval():
    flags = name_clues("Some Acquisition Trust - Common Stock")
    assert set(flags) == {"ACQUISITION_WORDING", "TRUST_WORDING", "COMMON_STOCK_WORDING"}


def test_reject_missing_or_altered_a5_queue():
    snap = parse_funds(raw(), NOW)
    with pytest.raises(ValueError, match="complete"):
        enrich_fund_queue(fixture_rows()[:-1], snap)
    records = fixture_rows()
    records[0]["production_eligible"] = True
    with pytest.raises(ValueError):
        enrich_fund_queue(records, snap)


def test_sec_optional_empty_fund_ticker_is_retained_but_not_matchable():
    payload = raw([[2078265, "S000108971", "C000280065", ""]])
    snap = parse_funds(payload, NOW)
    assert len(snap.classes) == 1
    assert snap.classes[0].ticker == ""
    output = enrich_fund_queue(fixture_rows(), snap)
    assert output["fund_ticker_match_status_counts"] == {
        "NOT_IN_SEC_FUND_TICKER_FILE": 1010,
    }
