"""A5m SEC/Nasdaq independent crosswalk: strict identity, distinct SPAC instruments."""
from collections import Counter
from hashlib import sha256
from pathlib import Path

import pytest

from src.data.universe import a5m_exchange_class_crosswalk as m


def snapshot():
    cases = {
        "AACI": ("Armada Acquisition Corp. III - Class A Ordinary Share", "XNAS"),
        "AACIU": ("Armada Acquisition Corp. III - Units", "XNAS"),
        "AACIW": ("Armada Acquisition Corp. III - Warrant", "XNAS"),
        "ADAC": ("American Drive Acquisition Company - Class A Ordinary Shares", "XNAS"),
        "ADACU": ("American Drive Acquisition Company - Units", "XNAS"),
        "ADACW": ("American Drive Acquisition Company - Warrant", "XNAS"),
        "ASPC": ("A SPAC III Acquisition Corp. - Class A Ordinary Shares", "XNAS"),
        "ASPCU": ("A SPAC III Acquisition Corp. - Unit", "XNAS"),
        "ASPCR": ("A SPAC III Acquisition Corp. - Right", "XNAS"),
        "ARR": ("ARMOUR Residential REIT, Inc.", "XNYS"),
        "RHP": ("Ryman Hospitality Properties, Inc. (REIT)", "XNYS"),
        "WPC": ("W. P. Carey Inc. REIT", "XNYS"),
        "CCD": ("Calamos Dynamic Convertible & Income Fund - Closed End Fund", "XNAS"),
        "CGO": ("Calamos Global Total Return Fund - Closed End Fund", "XNAS"),
        "CSQ": ("Calamos Strategic Total Return Fund - Closed End Fund", "XNAS"),
    }
    rowlist, raw = [], {"nasdaqlisted": {}, "otherlisted": {}}
    review, excluded = 0, 0
    original_names = set(m.MAIN_CLASSES) | m.FUND_SYMBOLS
    for ticker, (name, mic) in cases.items():
        source = "nasdaqlisted" if mic == "XNAS" else "otherlisted"
        fin = "D" if ticker.startswith("ASPC") else "N"
        evidence = ({
            "Symbol": ticker, "Security Name": name, "Market Category": "S",
            "Test Issue": "N", "Financial Status": fin, "Round Lot Size": "100",
            "ETF": "N", "NextShares": "N",
        } if mic == "XNAS" else {
            "ACT Symbol": ticker, "Security Name": name, "Exchange": "N",
            "CQS Symbol": ticker, "ETF": "N", "Round Lot Size": "100",
            "Test Issue": "N", "NASDAQ Symbol": ticker,
        })
        raw[source][ticker] = evidence
        decision = "REVIEW_REQUIRED" if ticker in original_names else "EXCLUDE"
        if decision == "REVIEW_REQUIRED":
            review += 1
        else:
            excluded += 1
        rowlist.append({
            "source": source, "symbol": ticker, "name": name, "mic": mic,
            "evidence": evidence, "decision": decision,
            "reason": ("NON_COMMON_INSTRUMENT_NAME" if decision == "EXCLUDE" else
                       "SPAC_BDC_OR_FINANCIAL_REVIEW"),
            "production_eligible": False,
        })
    for i in range(1010 - review):
        t = f"REVIEW{i:05d}"
        ev = {"Symbol": t, "Security Name": "Example Common", "Market Category": "Q",
              "Test Issue": "N", "Financial Status": "N", "Round Lot Size": "100",
              "ETF": "N", "NextShares": "N"}
        raw["nasdaqlisted"][t] = ev
        rowlist.append({"source": "nasdaqlisted", "symbol": t, "mic": "XNAS",
                        "name": ev["Security Name"], "evidence": ev,
                        "decision": "REVIEW_REQUIRED", "reason": "TYPE_UNCONFIRMED",
                        "production_eligible": False})
    for i in range(7721 - excluded):
        t = f"EXCLUDE{i:05d}"
        ev = {"Symbol": t, "Security Name": "Example ETF", "Market Category": "G",
              "Test Issue": "N", "Financial Status": "N", "Round Lot Size": "100",
              "ETF": "Y", "NextShares": "N"}
        raw["nasdaqlisted"][t] = ev
        rowlist.append({"source": "nasdaqlisted", "symbol": t, "mic": "XNAS",
                        "name": ev["Security Name"], "evidence": ev,
                        "decision": "EXCLUDE", "reason": "FUND_FLAG",
                        "production_eligible": False})
    for i in range(4556):
        t = f"INCLUDE{i:05d}"
        ev = {"Symbol": t, "Security Name": "Example Common Stock", "Market Category": "G",
              "Test Issue": "N", "Financial Status": "N", "Round Lot Size": "100",
              "ETF": "N", "NextShares": "N"}
        raw["nasdaqlisted"][t] = ev
        rowlist.append({"source": "nasdaqlisted", "symbol": t, "mic": "XNAS",
                        "name": ev["Security Name"], "evidence": ev,
                        "decision": "INCLUDE", "reason": "COMMON_STOCK_NAME",
                        "production_eligible": False})
    assert len(rowlist) == 13287
    sources = [{
        "source": source,
        "sha256": (m.NASDAQ_SHA if source == "nasdaqlisted" else m.OTHERLISTED_SHA),
        "created_at": "2026-10-14T15:41:00-04:00",
        "retrieved_at": "2026-10-14T20:06:28+00:00",
    } for source in raw]
    a4 = {
        "status": "REVIEW_ONLY", "production_eligible": False,
        "total": 13287, "counts": dict(m.EXPECTED_A4),
        "rows": rowlist, "sources": sources,
    }
    a5l_rows = []
    for ticker in (*m.MAIN_CLASSES, *sorted(m.FUND_SYMBOLS)):
        row = next(r for r in rowlist if r["symbol"] == ticker)
        is_fund = ticker in m.FUND_SYMBOLS
        a5l_rows.append({
            "ticker": ticker, "mic": row["mic"], "cik": "0000123456",
            "a4_security_name": row["name"],
            "official_directory_sha256": (
                m.NASDAQ_SHA if row["source"] == "nasdaqlisted" else m.OTHERLISTED_SHA),
            "source_retrieved_at": "2026-10-15T15:00:00+00:00",
            "sec_primary_sha256": "a"*64, "filing_date": "2026-08-09",
            "sec_form": "N-CSRS" if is_fund else "10-Q",
            "class_evidence": (
                "SEC_N_CSRS_FUND_ISSUER_REPORT_NOT_LISTED_CLASS" if is_fund else
                "SEC_SECTION_12B_CLASS_ROW_CANDIDATE"),
            "same_row_candidates": ([] if is_fund else [{
                "main_class_wording": m.MAIN_CLASSES[ticker],
                "ticker_cell": ticker, "share_class_approved": False,
                "security_id": None,
            }]),
            "listed_class_approved": False, "security_id": None,
            "a4_decision_unchanged": "REVIEW_REQUIRED",
            "production_eligible": False,
        })
    a5l = {
        "status": "SEC_LISTED_CLASS_ROWS_REVIEW_ONLY",
        "version": "a5l-sec-listed-class-evidence-v1",
        "as_of": "2026-10-14",
        "source_count": 9, "same_row_class_candidates": 6,
        "production_eligible": False, "production_approvals": 0,
        "final_security_type_approvals": 0, "final_security_class_approvals": 0,
        "records": a5l_rows,
    }
    return a4, a5l, raw


def test_exact_15_crosswalk_and_six_spac_siblings(monkeypatch, tmp_path):
    a4, sec, directories = snapshot()
    monkeypatch.setattr(m, "_load_json", lambda path, digest:
                        a4 if path.name == "review.json" else sec)
    monkeypatch.setattr(m, "_load_directory", lambda path, digest, source:
                        directories[source])
    result = m.crosswalk(tmp_path, tmp_path)
    assert result["status"] == "OFFICIAL_EXCHANGE_CLASS_CROSSWALK_REVIEW_ONLY"
    assert result["full_A4_rows_integrity_checked"] == 13287
    assert result["main_tickers_crosschecked"] == 9
    assert result["separate_SPAC_unit_warrant_right_symbols"] == 6
    assert result["SEC_same_ticker_class_row_with_exchange_title"] == 6
    assert result["nasdaq_financial_status_D_review_tickers"] == ["ASPC"]
    assert result["main_and_siblings_security_id_approvals"] == 0
    assert result["production_approvals"] == 0
    assert not result["published_to_runtime"]
    assert {x["ticker"] for x in result["SPAC_sibling_separate_instruments"]} == {
        "AACIU", "AACIW", "ADACU", "ADACW", "ASPCU", "ASPCR",
    }
    assert all(x["original_A4_decision"] == "EXCLUDE" for x in
               result["SPAC_sibling_separate_instruments"])
    assert all(x["same_security_id_as_parent_proven"] is False for x in
               result["SPAC_sibling_separate_instruments"])


@pytest.mark.parametrize("mutation", [
    "turn_unit_into_review", "forge_warrant_name", "mislabel_spac_financial",
    "alter_NYSE_exchange", "invent_security_id", "change_SEC_class",
    "tamper_directory_row",
])
def test_identity_status_or_share_class_mismatch_fail_closed(monkeypatch, tmp_path, mutation):
    a4, sec, dirs = snapshot()
    bysym = {r["symbol"]: r for r in a4["rows"]}
    secs = {r["ticker"]: r for r in sec["records"]}
    if mutation == "turn_unit_into_review":
        bysym["AACIU"]["decision"] = "REVIEW_REQUIRED"
    elif mutation == "forge_warrant_name":
        bysym["AACIW"]["name"] = "Armada Acquisition Corp. III - Ordinary Share"
        dirs["nasdaqlisted"]["AACIW"]["Security Name"] = bysym["AACIW"]["name"]
    elif mutation == "mislabel_spac_financial":
        dirs["nasdaqlisted"]["ASPC"]["Financial Status"] = "N"
        bysym["ASPC"]["evidence"]["Financial Status"] = "N"
    elif mutation == "alter_NYSE_exchange":
        dirs["otherlisted"]["ARR"]["Exchange"] = "P"
        bysym["ARR"]["evidence"]["Exchange"] = "P"
    elif mutation == "invent_security_id":
        secs["AACI"]["security_id"] = "FORGED"
    elif mutation == "change_SEC_class":
        secs["ADAC"]["same_row_candidates"][0]["main_class_wording"] = "COMMON_STOCK"
    elif mutation == "tamper_directory_row":
        dirs["nasdaqlisted"]["AACI"]["Security Name"] = "Forged Company"
    monkeypatch.setattr(m, "_load_json", lambda path, digest:
                        a4 if path.name == "review.json" else sec)
    monkeypatch.setattr(m, "_load_directory", lambda path, digest, source:
                        dirs[source])
    with pytest.raises(m.A5mSourceError):
        m.crosswalk(tmp_path, tmp_path)


def test_official_directory_sha_tamper_rejected(tmp_path):
    raw = ("|".join(m.NASDAQ_FIELDS) + "\n" +
           "AACI|Armada Acquisition - Class A Ordinary Shares|G|N|N|100|N|N\n" +
           "File Creation Time: 1014202615:41|||||||\n").encode()
    path = tmp_path/"test.txt"
    path.write_bytes(raw)
    assert "AACI" in m._load_directory(path, sha256(raw).hexdigest(), "nasdaqlisted")
    path.write_bytes(raw + b"x")
    with pytest.raises(m.A5mSourceError, match="checksum"):
        m._load_directory(path, sha256(raw).hexdigest(), "nasdaqlisted")


def test_directory_duplicate_symbol_or_corrupted_field_layout_rejected(tmp_path):
    header = "|".join(m.NASDAQ_FIELDS) + "\n"
    line = "AACI|Armada - Class A Ordinary Shares|G|N|N|100|N|N\n"
    p = tmp_path/"directory.txt"
    data = (header+line+line).encode()
    p.write_bytes(data)
    with pytest.raises(m.A5mSourceError, match="duplicate"):
        m._load_directory(p, sha256(data).hexdigest(), "nasdaqlisted")
    data = (header+"AACI|Broken|G|N\n").encode()
    p.write_bytes(data)
    with pytest.raises(m.A5mSourceError, match="field count"):
        m._load_directory(p, sha256(data).hexdigest(), "nasdaqlisted")


def test_missing_source_receipt_is_not_known_at_evidence():
    a4, _, _ = snapshot()
    a4["sources"].pop()
    with pytest.raises(m.A5mSourceError):
        m._directory_receipts(a4)
