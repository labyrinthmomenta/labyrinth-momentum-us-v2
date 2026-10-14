from copy import deepcopy
import pytest

from src.data.universe.audit_summary import build_audit


def fixture():
    srcs = [{"source": "nasdaqlisted", "sha256": "a"},
            {"source": "otherlisted", "sha256": "b"}]
    rows = [{"source": "nasdaqlisted", "symbol": "A", "mic": "XNAS",
             "decision": "INCLUDE", "reason": "EXPLICIT_COMMON_NAME_CANDIDATE",
             "production_eligible": False},
            {"source": "otherlisted", "symbol": "B", "mic": "XNYS",
             "decision": "REVIEW_REQUIRED", "reason": "TYPE_UNCONFIRMED",
             "production_eligible": False}]
    original = {"status": "REVIEW_ONLY", "production_eligible": False, "rows": rows,
                "sources": srcs, "counts": {"INCLUDE": 1, "EXCLUDE": 0, "REVIEW_REQUIRED": 1}}
    enriched = deepcopy(original)
    enriched["rows"][0]["issuer_match"] = {"status": "SEC_CIK_CANDIDATE"}
    enriched["rows"][1]["issuer_match"] = {"status": "SEC_NOT_FOUND"}
    enriched["sec_enrichment"] = {"sha256": "sec-sha",
                                    "retrieved_at": "2026-10-14T12:00:00+00:00",
                                    "rows": 100}
    baseline = {"sources": srcs, "total": 2, "counts": deepcopy(original["counts"])}
    return original, enriched, baseline


def test_hash_identical_and_matrix_counts():
    a, b, c = fixture()
    result = build_audit(a, b, c)
    assert result["a1_byte_identical"] is True
    assert result["sec_match_by_initial_decision"]["INCLUDE"]["SEC_CIK_CANDIDATE"] == 1
    assert result["sec_match_by_initial_decision"]["REVIEW_REQUIRED"]["SEC_NOT_FOUND"] == 1
    assert result["production_eligible"] is False


def test_matching_counts_alone_do_not_mean_same_raw_snapshot():
    a, b, c = fixture()
    a["sources"][0]["sha256"] = "new"
    assert build_audit(a, b, c)["a1_byte_identical"] is False


def test_source_hash_consistency_rejects_baseline_mismatch():
    a, b, c = fixture()
    c["counts"] = {"INCLUDE": 0, "EXCLUDE": 1, "REVIEW_REQUIRED": 1}
    with pytest.raises(ValueError, match="hash matches"):
        build_audit(a, b, c)


def test_reject_row_order_swap():
    a, b, c = fixture()
    b["rows"].reverse()
    with pytest.raises(ValueError, match="identity/order"):
        build_audit(a, b, c)


def test_reject_unapproved_or_incomplete_rows():
    a, b, c = fixture()
    b["rows"][0]["production_eligible"] = True
    with pytest.raises(ValueError, match="production"):
        build_audit(a, b, c)
    b["rows"][0]["production_eligible"] = False
    del b["rows"][0]["issuer_match"]
    with pytest.raises(ValueError, match="Incomplete"):
        build_audit(a, b, c)
