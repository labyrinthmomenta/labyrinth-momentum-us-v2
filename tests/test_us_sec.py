"""Offline synthetic SEC fixtures: issuer identity is never a security approval."""
from datetime import datetime, timezone
import json

import pytest

from src.data.universe.sec import (
    SecSnapshotError, parse_sec_exchange_snapshot, enrich_review_with_sec,
)
from src.data.universe.triage import triage_record

NOW = datetime(2026, 10, 14, 16, tzinfo=timezone.utc)


def sec_payload(rows):
    return json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
                       "data": rows}).encode()


def report_rows(*rows):
    entries = [{"source": "nasdaqlisted", "symbol": symbol, "mic": mic,
                "decision": decision, "reason": reason, "production_eligible": False}
               for symbol, mic, decision, reason in rows]
    return {"status": "REVIEW_ONLY", "production_eligible": False,
            "counts": {key: sum(x["decision"] == key for x in entries)
                       for key in ("INCLUDE", "EXCLUDE", "REVIEW_REQUIRED")},
            "rows": entries}


def test_two_share_classes_have_same_cik_not_same_security():
    snap = parse_sec_exchange_snapshot(sec_payload([
        [1652044, "Alphabet Inc.", "GOOG", "Nasdaq"],
        [1652044, "Alphabet Inc.", "GOOGL", "Nasdaq"],
    ]), retrieved_at=NOW)
    out = enrich_review_with_sec(report_rows(
        ("GOOG", "XNAS", "REVIEW_REQUIRED", "TYPE_UNCONFIRMED"),
        ("GOOGL", "XNAS", "INCLUDE", "EXPLICIT_COMMON_NAME_CANDIDATE")), snap)
    assert [r["issuer_match"]["issuer_cik"] for r in out["rows"]] == ["0001652044"] * 2
    assert out["rows"][0]["symbol"] != out["rows"][1]["symbol"]
    assert [r["decision"] for r in out["rows"]] == ["REVIEW_REQUIRED", "INCLUDE"]
    assert all(not r["production_eligible"] for r in out["rows"])
    assert out["sec_enrichment"]["issuer_identity_approved"] is False


def test_no_sec_match_is_not_delisting_or_scope_exclusion():
    snap = parse_sec_exchange_snapshot(sec_payload([
        [320193, "Apple Inc.", "AAPL", "NYSE"],
    ]), retrieved_at=NOW)
    out = enrich_review_with_sec(report_rows(
        ("AAPL", "XNAS", "INCLUDE", "EXPLICIT_COMMON_NAME_CANDIDATE"),
        ("MISSING", "XNYS", "REVIEW_REQUIRED", "TYPE_UNCONFIRMED")), snap)
    assert [r["issuer_match"]["status"] for r in out["rows"]] == ["SEC_NOT_FOUND"] * 2
    assert out["counts"]["INCLUDE"] == 1


def test_ambiguous_sec_issuers_quarantine_candidate():
    snap = parse_sec_exchange_snapshot(sec_payload([
        [100, "One", "FOO", "Nasdaq"], [200, "Two", "FOO", "Nasdaq"],
    ]), retrieved_at=NOW)
    out = enrich_review_with_sec(report_rows(
        ("FOO", "XNAS", "INCLUDE", "EXPLICIT_COMMON_NAME_CANDIDATE")), snap)
    row = out["rows"][0]
    assert row["decision"] == "REVIEW_REQUIRED" and row["reason"] == "SEC_IDENTITY_AMBIGUOUS"
    assert row["directory_decision_before_sec"] == "INCLUDE"
    assert row["issuer_match"]["candidate_ciks"] == ["0000000100", "0000000200"]
    assert row["triage"]["priority"] == 1
    assert out["counts"] == {"INCLUDE": 0, "EXCLUDE": 0, "REVIEW_REQUIRED": 1}


def test_excluded_instrument_cannot_be_resurrected_by_sec():
    snap = parse_sec_exchange_snapshot(sec_payload([
        [100, "Fund issuer", "ETFQ", "Nasdaq"],
        [200, "Other issuer", "ETFQ", "Nasdaq"],
    ]), retrieved_at=NOW)
    row = enrich_review_with_sec(report_rows(
        ("ETFQ", "XNAS", "EXCLUDE", "FUND_FLAG")), snap)["rows"][0]
    assert row["decision"] == "EXCLUDE" and row["triage"]["status"] == "OUT_OF_SCOPE"


def test_unknown_sec_venue_and_punctuation_are_not_normalized():
    snap = parse_sec_exchange_snapshot(sec_payload([
        [500, "Example", "BRK-B", "NYSE"],
        [600, "Other", "ABC", "NYSE Arca"],
    ]), retrieved_at=NOW)
    assert snap.companies[1].mic is None
    out = enrich_review_with_sec(report_rows(
        ("BRK.B", "XNYS", "REVIEW_REQUIRED", "TYPE_UNCONFIRMED"),
        ("ABC", "XNYS", "INCLUDE", "EXPLICIT_COMMON_NAME_CANDIDATE")), snap)
    assert all(r["issuer_match"]["status"] == "SEC_NOT_FOUND" for r in out["rows"])


@pytest.mark.parametrize("raw", [
    b"<html>blocked</html>",
    b"{}",
    sec_payload([]),
    sec_payload([[True, "Bad", "X", "Nasdaq"]]),
    sec_payload([[0, "Bad", "X", "Nasdaq"]]),
    sec_payload([[100, "Bad", " X", "Nasdaq"]]),
    sec_payload([[100, "Bad", "X", "Nasdaq"], [100, "Bad", "X", "Nasdaq"]]),
    json.dumps({"fields": ["ticker", "cik", "exchange", "name"], "data": []}).encode(),
])
def test_sec_bad_payload_rejected(raw):
    with pytest.raises(SecSnapshotError):
        parse_sec_exchange_snapshot(raw, retrieved_at=NOW)


def test_naive_retrieval_time_and_preapproved_input_rejected():
    raw = sec_payload([[100, "Company", "X", "Nasdaq"]])
    with pytest.raises(SecSnapshotError):
        parse_sec_exchange_snapshot(raw, retrieved_at=NOW.replace(tzinfo=None))
    snap = parse_sec_exchange_snapshot(raw, retrieved_at=NOW)
    with pytest.raises(SecSnapshotError):
        enrich_review_with_sec({"status": "APPROVED", "production_eligible": True,
                                "rows": []}, snap)
    with pytest.raises(SecSnapshotError):
        enrich_review_with_sec({"status": "REVIEW_ONLY", "production_eligible": False,
                                "rows": [{"decision": "INCLUDE",
                                          "production_eligible": True}]}, snap)


@pytest.mark.parametrize("reason,required", [
    ("UNKNOWN_EXCHANGE_CODE", "OFFICIAL_VENUE_MAPPING"),
    ("FUND_NAME_REQUIRES_TYPE_EVIDENCE", "FUND_VS_COMMON_REIT_EVIDENCE"),
    ("SPAC_BDC_OR_FINANCIAL_REVIEW", "SPAC_BDC_POLICY_DECISION"),
    ("FINANCIAL_STATUS_REVIEW", "EXCHANGE_FINANCIAL_STATUS"),
])
def test_triage_requests_type_evidence(reason, required):
    triage = triage_record({"decision": "REVIEW_REQUIRED", "reason": reason})
    assert triage["status"] == "EVIDENCE_REQUIRED"
    assert required in triage["required_evidence"]


def test_include_stays_provisional_and_needs_evidence():
    triage = triage_record({"decision": "INCLUDE",
                            "reason": "EXPLICIT_COMMON_NAME_CANDIDATE"})
    assert triage["status"] == "PROVISIONAL_ONLY"
    assert "SHARE_CLASS" in triage["required_evidence"]


def test_official_sec_null_exchange_is_unmapped_evidence_not_rejection():
    snap = parse_sec_exchange_snapshot(sec_payload([
        [2156068, "InoBat B.V.", "INBT", None],
    ]), retrieved_at=NOW)
    assert snap.companies[0].exchange is None
    assert snap.companies[0].mic is None
    out = enrich_review_with_sec(report_rows(
        ("INBT", "XNAS", "REVIEW_REQUIRED", "TYPE_UNCONFIRMED")), snap)
    assert out["rows"][0]["issuer_match"]["status"] == "SEC_NOT_FOUND"
    assert out["rows"][0]["production_eligible"] is False
