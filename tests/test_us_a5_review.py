"""A5 is deliberately fail-closed; source hashes and evidence are immutable."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import pytest

from src.data.universe.a5_review import (
    A4_HASHES, A4_COUNTS, _read_raw, variants_for_review,
    triage_evidence, evaluate_a5, reconstruct_a4,
)
from src.data.universe.sec import SecExchangeSnapshot


def test_exchange_class_symbol_format_candidates_are_not_identity_assignments():
    assert variants_for_review("BRK.B") == ("BRK-B",)
    assert variants_for_review("BAC$L") == ("BAC-PL",)
    assert variants_for_review("GS$D") == ("GS-PD",)
    assert variants_for_review("ASBH") == ()
    assert variants_for_review("EX.A$B") == ("EX-A$B", "EX.A-PB")


@pytest.mark.parametrize("reason,requirement", [
    ("FINANCIAL_STATUS_REVIEW", "NASDAQ_FINANCIAL_STATUS_RESOLUTION"),
    ("FUND_NAME_REQUIRES_TYPE_EVIDENCE", "OFFICIAL_REIT_VS_FUND_SECURITY_TYPE"),
    ("SPAC_BDC_OR_FINANCIAL_REVIEW", "SPAC_BDC_EXPLICIT_SCOPE_DECISION"),
    ("TYPE_UNCONFIRMED", "OFFICIAL_SECURITY_TYPE"),
    ("UNKNOWN_EXCHANGE_CODE", "TXSE_VENUE_SCOPE_POLICY"),
])
def test_reason_specific_evidence_is_required(reason, requirement):
    assert requirement in triage_evidence(reason)


def test_official_source_hash_rejects_modified_input(tmp_path):
    (tmp_path / ("nasdaqlisted-" + A4_HASHES["nasdaqlisted"] + ".txt")).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        _read_raw(tmp_path, "nasdaqlisted", A4_HASHES["nasdaqlisted"])


def test_missing_frozen_capture_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError):
        reconstruct_a4(tmp_path / "directory", tmp_path / "sec", tmp_path / "review.json")


def test_incomplete_review_fails_closed():
    sec = SecExchangeSnapshot(sha256=A4_HASHES["sec"],
                              retrieved_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
                              companies=())
    with pytest.raises(ValueError, match="complete"):
        evaluate_a5({"status": "REVIEW_ONLY", "production_eligible": False,
                     "total": 13287, "rows": []}, sec)


def test_production_eligible_directory_report_fails_closed():
    sec = SecExchangeSnapshot(sha256=A4_HASHES["sec"],
                              retrieved_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
                              companies=())
    with pytest.raises(ValueError):
        evaluate_a5({"status": "REVIEW_ONLY", "production_eligible": True,
                     "total": 0, "rows": []}, sec)


def test_a5_does_not_change_a4_baseline_counts():
    assert A4_COUNTS == {"INCLUDE": 4556, "EXCLUDE": 7721,
                         "REVIEW_REQUIRED": 1010}
    assert sum(A4_COUNTS.values()) == 13287
