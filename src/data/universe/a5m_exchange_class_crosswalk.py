"""A5m: exchange-directory instrument families + SEC class evidence crosswalk.

Two independently sourced evidence surfaces are tied by ticker/MIC:
- Official 2026-10-14 Nasdaq Trader nasdaqlisted/otherlisted directories
- Frozen A5l original-SEC 12(b) listed-class evidence (nine issuers)

Nasdaq 'Security Name' is NOT a permanent listed-security identifier;
'otherlisted' is Nasdaq's report of NYSE listings, not a NYSE-issued
security master; issuer SEC CIK is not security_id. No automatic approvals.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re

VERSION = "a5m-exchange-class-crosswalk-review-v1"
AS_OF = "2026-10-14"
A4_SHA = "5c7e7080ef6a19dc17d771b830a6d5667b31ea0d8a209d0471c3f5c9f3df9c2d"
A5L_SHA = "cf342e3f17ba5d600f3bcfd0ed958976ef97272fe8b2749582a2a21093475992"
NASDAQ_SHA = "2dc5b607a42c3eefe9cf6f7d6e681c30b8fb55bb51ae04d998cdf51af02d6694"
OTHERLISTED_SHA = "12deeb989a1b515304eda04318a0af1db127ff6340d1055329c62d9a5cbcde28"
EXPECTED_A4 = {"INCLUDE": 4556, "EXCLUDE": 7721, "REVIEW_REQUIRED": 1010}
SPAC_FAMILIES = {
    "AACI": {"AACIU": "UNIT", "AACIW": "WARRANT"},
    "ADAC": {"ADACU": "UNIT", "ADACW": "WARRANT"},
    "ASPC": {"ASPCU": "UNIT", "ASPCR": "RIGHT"},
}
MAIN_CLASSES = {
    "AACI": "CLASS_A_ORDINARY_SHARES",
    "ADAC": "CLASS_A_ORDINARY_SHARES",
    "ASPC": "CLASS_A_ORDINARY_SHARES",
    "ARR": "COMMON_STOCK", "RHP": "COMMON_STOCK", "WPC": "COMMON_STOCK",
}
FUND_SYMBOLS = frozenset({"CCD", "CGO", "CSQ"})
FUND_SOURCE_FORM = "N-CSRS"
OTHERLISTED_EXCHANGE = {"N": "XNYS"}
NAME_CLASS = {
    "UNIT": re.compile(r"\bunits?\b", re.I),
    "WARRANT": re.compile(r"\bwarrants?\b", re.I),
    "RIGHT": re.compile(r"\brights?\b", re.I),
}
NASDAQ_FIELDS = ("Symbol", "Security Name", "Market Category", "Test Issue",
                 "Financial Status", "Round Lot Size", "ETF", "NextShares")
OTHER_FIELDS = ("ACT Symbol", "Security Name", "Exchange", "CQS Symbol",
                "ETF", "Round Lot Size", "Test Issue", "NASDAQ Symbol")


class A5mSourceError(ValueError):
    pass


def _load_json(path: Path, expected_sha: str) -> dict:
    body = path.read_bytes()
    if sha256(body).hexdigest() != expected_sha:
        raise A5mSourceError(f"Frozen source hash mismatch: {path.name}")
    result = json.loads(body.decode("utf-8"))
    if not isinstance(result, dict):
        raise A5mSourceError(f"Unexpected JSON root in {path.name}")
    return result


def _load_directory(path: Path, digest: str, source: str) -> dict[str, dict]:
    body = path.read_bytes()
    if sha256(body).hexdigest() != digest:
        raise A5mSourceError(f"Official Nasdaq source checksum mismatch: {source}")
    lines = body.decode("utf-8-sig").splitlines()
    fields = NASDAQ_FIELDS if source == "nasdaqlisted" else OTHER_FIELDS
    if not lines or tuple(lines[0].split("|")) != fields:
        raise A5mSourceError(f"Unexpected official Nasdaq directory fields: {source}")
    symbols = {}
    for line in lines[1:]:
        if line.startswith("File Creation Time:"):
            continue
        if not line.strip():
            continue
        values = line.split("|")
        if len(values) != len(fields):
            raise A5mSourceError(f"Unexpected Nasdaq field count: {source}")
        item = dict(zip(fields, values))
        symbol = item["Symbol" if source == "nasdaqlisted" else "ACT Symbol"]
        if not symbol or symbol in symbols:
            raise A5mSourceError(f"Empty/duplicate Nasdaq symbol in {source}")
        symbols[symbol] = item
    return symbols


def _directory_receipts(a4: dict) -> dict:
    observed = {}
    for receipt in a4.get("sources", []):
        name, digest = receipt.get("source"), receipt.get("sha256")
        if name not in ("nasdaqlisted", "otherlisted") or name in observed:
            raise A5mSourceError("Unexpected or duplicate Nasdaq A4 source")
        expected = NASDAQ_SHA if name == "nasdaqlisted" else OTHERLISTED_SHA
        if digest != expected:
            raise A5mSourceError("Nasdaq source receipt SHA mismatch")
        # Retrieval date is provenance, NOT SEC filing known_at.
        captured = datetime.fromisoformat(receipt["retrieved_at"])
        if captured.utcoffset() is None or captured.date().isoformat() not in (
                "2026-10-14", "2026-10-15"):
            raise A5mSourceError("Missing/incorrect source retrieval timestamp")
        observed[name] = {
            "sha256": digest, "created_at": receipt["created_at"],
            "retrieved_at": receipt["retrieved_at"],
        }
    if len(observed) != 2:
        raise A5mSourceError("Missing dated official Nasdaq source receipt")
    return observed


def _row_key(row: dict) -> tuple[str, str, str]:
    return row["source"], row["symbol"], row["mic"]


def crosswalk(a4_root: Path, a5l_root: Path) -> dict:
    a4 = _load_json(a4_root/"directory-review"/"review.json", A4_SHA)
    a5l = _load_json(a5l_root/"a5l-listed-class-evidence.json", A5L_SHA)
    if (a4.get("status") != "REVIEW_ONLY"
            or a4.get("production_eligible") is not False
            or a4.get("total") != 13287
            or a4.get("counts") != EXPECTED_A4
            or len(a4.get("rows", [])) != 13287):
        raise A5mSourceError("A4 directory was not frozen review-only")
    if (a5l.get("status") != "SEC_LISTED_CLASS_ROWS_REVIEW_ONLY"
            or a5l.get("version") != "a5l-sec-listed-class-evidence-v1"
            or a5l.get("as_of") != AS_OF
            or a5l.get("source_count") != 9
            or a5l.get("same_row_class_candidates") != 6
            or len(a5l.get("records", [])) != 9
            or a5l.get("production_eligible") is not False
            or a5l.get("production_approvals") != 0
            or a5l.get("final_security_type_approvals") != 0
            or a5l.get("final_security_class_approvals") != 0):
        raise A5mSourceError("A5l SEC class proof has been modified/promoted")
    receipts = _directory_receipts(a4)
    listing_data = {
        "nasdaqlisted": _load_directory(
            a4_root/"nasdaq-capture"/f"nasdaqlisted-{NASDAQ_SHA}.txt",
            NASDAQ_SHA, "nasdaqlisted"),
        "otherlisted": _load_directory(
            a4_root/"nasdaq-capture"/f"otherlisted-{OTHERLISTED_SHA}.txt",
            OTHERLISTED_SHA, "otherlisted"),
    }
    observed_keys = set()
    a4_by_ticker = {}
    decision_count = Counter()
    for row in a4["rows"]:
        if row.get("production_eligible") is not False or row.get("decision") not in EXPECTED_A4:
            raise A5mSourceError("A4 row has unsupported decision or production approval")
        key = _row_key(row)
        if key in observed_keys:
            raise A5mSourceError("Duplicate directory security candidate")
        observed_keys.add(key)
        source, symbol, mic = key
        original = listing_data.get(source, {}).get(symbol)
        if original is None or row["evidence"] != original or row["name"] != original["Security Name"]:
            raise A5mSourceError("A4 evidence not equal to raw Nasdaq directory bytes")
        expected_mic = "XNAS" if source == "nasdaqlisted" else OTHERLISTED_EXCHANGE.get(
            original["Exchange"])
        # Other exchanges outside the 3-venue scope may have mic=None.
        if expected_mic != mic and not (
                source == "otherlisted" and original["Exchange"] == "A"
                and mic == "XASE"):
            if not (expected_mic is None and mic is None):
                raise A5mSourceError("Nasdaq source Exchange/MIC mismatch")
        decision_count[row["decision"]] += 1
        if symbol in MAIN_CLASSES or symbol in FUND_SYMBOLS or any(
                symbol in fam for fam in SPAC_FAMILIES.values()):
            if symbol in a4_by_ticker:
                raise A5mSourceError("Ambiguous cross-market target symbol")
            a4_by_ticker[symbol] = row
    if decision_count != Counter(EXPECTED_A4):
        raise A5mSourceError("A4 original source decision distribution changed")
    expected = set(MAIN_CLASSES) | FUND_SYMBOLS | {
        sibling for family in SPAC_FAMILIES.values() for sibling in family
    }
    if set(a4_by_ticker) != expected or len(a4_by_ticker) != 15:
        raise A5mSourceError("One of 15 exchange identity candidates missing")

    previous = {}
    for proof in a5l["records"]:
        ticker = proof["ticker"]
        if ticker in previous:
            raise A5mSourceError("Duplicate SEC class proof ticker")
        previous[ticker] = proof
    if set(previous) != set(MAIN_CLASSES) | FUND_SYMBOLS:
        raise A5mSourceError("Frozen SEC main/fund sample population modified")
    main_records = []
    for ticker in list(MAIN_CLASSES) + sorted(FUND_SYMBOLS):
        row, proof = a4_by_ticker[ticker], previous[ticker]
        if (row["decision"] != "REVIEW_REQUIRED" or
                proof.get("production_eligible") is not False or
                proof.get("a4_decision_unchanged") != "REVIEW_REQUIRED" or
                proof.get("ticker") != ticker or
                proof.get("mic") != row["mic"] or
                proof.get("a4_security_name") != row["name"] or
                proof.get("official_directory_sha256") !=
                (NASDAQ_SHA if row["source"] == "nasdaqlisted" else OTHERLISTED_SHA) or
                proof.get("listed_class_approved") is not False or
                proof.get("security_id") is not None):
            raise A5mSourceError("Exchange vs SEC listing crosswalk invalid")
        if ticker in MAIN_CLASSES:
            candidates = proof["same_row_candidates"]
            if (len(candidates) != 1 or
                    proof["class_evidence"] != "SEC_SECTION_12B_CLASS_ROW_CANDIDATE" or
                    candidates[0]["main_class_wording"] != MAIN_CLASSES[ticker] or
                    candidates[0]["ticker_cell"] != ticker or
                    candidates[0]["share_class_approved"] is not False or
                    candidates[0]["security_id"] is not None):
                raise A5mSourceError("SEC ticker-cell class candidate missing/wrong")
            sec_class = candidates[0]["main_class_wording"]
            if ticker in SPAC_FAMILIES and not re.search(
                    r"\bClass\s+A\s+Ordinary\s+Shares?\b", row["name"], re.I):
                raise A5mSourceError("Nasdaq security name conflicts with SEC Class A")
        else:
            if (proof["class_evidence"] !=
                    "SEC_N_CSRS_FUND_ISSUER_REPORT_NOT_LISTED_CLASS" or
                    proof["sec_form"] != "N-CSRS" or
                    not re.search(r"\bClosed\s+End\s+Fund\b", row["name"], re.I) or
                    proof.get("same_row_candidates") != []):
                raise A5mSourceError("Closed-end fund SEC source cannot infer listing class")
            sec_class = None
        if row["source"] == "otherlisted":
            exchange_code = row["evidence"]["Exchange"]
            if exchange_code != "N":
                raise A5mSourceError("Three NYSE issuer records need Exchange=N")
            financial_code = None
        else:
            financial_code = row["evidence"]["Financial Status"]
            if financial_code not in ("N", "D"):
                raise A5mSourceError("Unexpected Nasdaq status for sample")
        status_flag = (
            "NASDAQ_DEFICIENT_LISTING_STANDARD_REVIEW"
            if financial_code == "D" else
            "FINANCIAL_CODE_N_SOURCE_ONLY" if financial_code == "N" else
            "NOT_IN_OTHERLISTED_DIRECTORY"
        )
        main_records.append({
            "ticker": ticker, "mic": row["mic"], "source": row["source"],
            "source_exchange_name": row["name"],
            "exchange_code": (
                row["evidence"].get("Exchange") if row["source"] == "otherlisted"
                else None),
            "nasdaq_financial_status_code": financial_code,
            "financial_status_review": status_flag,
            "sec_issuer_cik_candidate": proof["cik"],
            "sec_primary_source_sha256": proof["sec_primary_sha256"],
            "sec_original_filing_date": proof["filing_date"],
            "sec_class_row_evidence": sec_class,
            "SEC_section12b_title_row_count": len(proof["same_row_candidates"]),
            "directory_closed_end_fund_label": ticker in FUND_SYMBOLS,
            "market_class_candidate_source_disagreement": False,
            "listed_security_id": None,
            "class_final_approved": False,
            "issuer_type_final_approved": False,
            "production_eligible": False,
            "original_A4_decision": row["decision"],
        })

    siblings = []
    for parent, family in SPAC_FAMILIES.items():
        par = a4_by_ticker[parent]
        label_root = par["name"].rsplit(" - ", 1)[0]
        for symbol, kind in family.items():
            row = a4_by_ticker[symbol]
            if (row["source"] != "nasdaqlisted" or row["mic"] != "XNAS" or
                    row["name"].rsplit(" - ", 1)[0] != label_root or
                    row["decision"] != "EXCLUDE" or
                    row["reason"] != "NON_COMMON_INSTRUMENT_NAME" or
                    not NAME_CLASS[kind].search(row["name"].rsplit(" - ", 1)[-1])):
                raise A5mSourceError("SPAC sibling unit/warrant/right proof inconsistent")
            siblings.append({
                "related_common_ticker": parent,
                "ticker": symbol, "mic": "XNAS",
                "nasdaq_security_name": row["name"],
                "directory_class_wording": kind,
                "nasdaq_financial_status_code": row["evidence"]["Financial Status"],
                "source_name_root_equal": True,
                "same_security_id_as_parent": False,
                "independent_security_id_established": False,
                "original_A4_decision": "EXCLUDE",
                "original_A4_reason": "NON_COMMON_INSTRUMENT_NAME",
                "production_eligible": False,
                "review_status": "EXCLUDED_AS_NON_COMMON_BY_A4_REVIEW_ONLY",
            })
    if len(siblings) != 6:
        raise A5mSourceError("Six SPAC sibling symbols not reconciled")

    main_by = {x["ticker"]: x for x in main_records}
    risk = sorted(x["ticker"] for x in main_records if
                  x["nasdaq_financial_status_code"] == "D")
    if risk != ["ASPC"]:
        raise A5mSourceError("Nasdaq D status sample unexpectedly changed")

    return {
        "status": "OFFICIAL_EXCHANGE_CLASS_CROSSWALK_REVIEW_ONLY",
        "version": VERSION, "as_of": AS_OF,
        "source_sha256": {
            "A4_listing_review": A4_SHA, "A5l_SEC_class_review": A5L_SHA,
            "nasdaqlisted": NASDAQ_SHA, "otherlisted": OTHERLISTED_SHA,
        },
        "nasdaq_capture_receipts": receipts,
        "full_A4_rows_integrity_checked": 13287,
        "prior_A4_decisions_unchanged": EXPECTED_A4,
        "main_tickers_crosschecked": 9,
        "SEC_same_ticker_class_row_with_exchange_title": 6,
        "issuer_fund_report_not_listing_class": 3,
        "separate_SPAC_unit_warrant_right_symbols": 6,
        "nasdaq_financial_status_D_review_tickers": risk,
        "candidate_review_required": 9,
        "sibling_non_common_exclusions_unchanged": 6,
        "main_and_siblings_security_id_approvals": 0,
        "production_approvals": 0,
        "independent_NYSE_security_master_verified": False,
        "listed_security_id_established": False,
        "known_at_for_SEC_documents_established": False,
        "published_to_runtime": False,
        "production_eligible": False,
        "main_security_candidates": main_records,
        "SPAC_sibling_separate_instruments": siblings,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a4", required=True, type=Path)
    ap.add_argument("--a5l", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    try:
        review = crosswalk(args.a4, args.a5l)
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output/"a5m-exchange-class-crosswalk.json").write_text(
            json.dumps(review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        summary = {k: v for k, v in review.items()
                   if k not in ("main_security_candidates",
                                "SPAC_sibling_separate_instruments")}
        (args.output/"a5m-summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"A5M_BLOCKED: {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
