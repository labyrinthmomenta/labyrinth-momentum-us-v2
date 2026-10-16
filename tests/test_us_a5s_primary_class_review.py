"""A5s: SEC original N-CEN Part D.1 issuer/security-class and TVC bond safeguards."""
import json
from hashlib import sha256
import pytest
from src.data.universe import a5s_primary_class_review as m
from src.data.universe.a5o_sec_cfi_exceptions import CI,TVC


def ncen(ticker="BSTZ", *, exchange="NEW YORK STOCK EXCHANGE, INC.", type="Common stock"):
    return (f"<html><body><h1>FORM N-CEN</h1>"
      f"<p>Filer Investment Company Type Form N-2 Filer (Closed-End Investment Company)</p>"
      f"<h1>N-CEN:Part D: Additional Questions</h1>"
      f"<h4>Item D.1. Securities issued by Registrant.</h4>"
      f"<table><tr><td>Security Issued by Registrants Record: 1</td></tr>"
      f"<tr><td>Type of security</td><td>{type}</td></tr>"
      f"<tr><td>Title of class</td><td>Test Trust</td></tr>"
      f"<tr><td>Common Record:1</td></tr>"
      f"<tr><td>Exchange where listed</td><td>{exchange}</td></tr>"
      f"<tr><td>Ticker symbol</td><td>{ticker}</td></tr></table>"
      f"<h4>Item D.2. Rights offerings.</h4></body></html>").encode()


def tvc():
    return (b"<html><h1>FORM 10-K</h1><p>TVA Bonds are traded in the public bond markets "
      b"and are listed on the New York Stock Exchange.</p>"
      b"<p>TVA's Putable Automatic Rate Reset Securities (\"PARRS\") "
      b"are traded on the NYSE under the exchange symbols \"TVC\" and \"TVE.\"</p>"
      b"</html>")


def test_ncen_matching_fund_is_cef_issuer_and_exact_common_class_only():
    q=m.parse_ncen(ncen(),ticker="BSTZ")
    assert q["SEC_NCEN_filer_Form_N2_closed_end"] is True
    assert q["SEC_exact_NYSE_common_ticker_row"] is True
    assert q["evidence_tier"]=="SEC_NCEN_N2_EXACT_NYSE_COMMON_TICKER"
    assert q["BDC_election_or_absence_independently_proven"] is False
    assert q["security_id_verified"] is False


def test_ticker_mismatch_not_silently_approved():
    q=m.parse_ncen(ncen("XTYGX"),ticker="TYG")
    assert q["evidence_tier"]=="SEC_NCEN_N2_ISSUER_ONLY_TICKER_DISCREPANCY"
    assert not q["SEC_exact_NYSE_common_ticker_row"]


def test_trading_venue_mismatch_kept_separate():
    q=m.parse_ncen(ncen("JHS",exchange="ARCA DARK"),ticker="JHS")
    assert q["evidence_tier"]=="SEC_NCEN_N2_TICKER_MATCH_VENUE_DISCREPANCY"


def test_preferred_and_common_stock_share_class_not_conflated():
    q=m.parse_ncen(ncen(type="Preferred stock"),ticker="BSTZ")
    assert q["evidence_tier"]=="SEC_NCEN_N2_ISSUER_ONLY_TICKER_DISCREPANCY"


def test_bond_is_not_an_ordinary_share():
    v=m.parse_tvc(tvc())
    assert v["security_type_candidate"]=="DEBT_PARRS_NOT_COMMON_SHARE"
    assert v["production_eligible"] is False


def test_invalid_primary_document_must_fail_closed():
    with pytest.raises(m.PrimaryReviewError):
        m.parse_ncen(b"not a legitimate SEC source"*20,ticker="BSTZ")


def test_synthetic_21_originals_no_approval(tmp_path,monkeypatch):
    records=[]
    for i,ticker in enumerate(list(CI)+[TVC]):
        if ticker==TVC:raw=tvc()
        else:raw=ncen("XTYGX" if ticker=="TYG" else ticker,
                      exchange="ARCA DARK" if ticker in ("JHS","JHI") else "NEW YORK STOCK EXCHANGE, INC.")
        digest=sha256(raw).hexdigest()
        fn=f"{ticker}-{digest}.source"
        (tmp_path/fn).write_bytes(raw)
        records.append({"ticker":ticker,"cik":f"{i+100:010d}",
                        "status":"PRIMARY_BYTES_CAPTURED_REVIEW_ONLY",
                        "production_eligible":False,"raw_filename":fn,
                        "raw_sha256":digest,"raw_bytes":len(raw),
                        "retrieved_at":"2026-10-16T12:00:00+00:00",
                        "filing":{"filing_date":"2026-03-15" if ticker!=TVC else "2025-11-13"}})
    report={"status":"SEC_ORIGINAL_21_COMPLETE_REVIEW_ONLY",
            "source_bytes_verified":21,"production_eligible":False,
            "documents":records}
    raw=json.dumps(report).encode()
    (tmp_path/"a5s-original-primary-receipts.json").write_bytes(raw)
    monkeypatch.setattr(m,"RECEIPTS_SHA",sha256(raw).hexdigest())
    out=m.summarize(tmp_path)
    assert out["SEC_primary_sources_verified"]==21
    assert out["issuer_closed_end_form_N2_evidence_count"]==20
    assert out["SEC_exact_NYSE_common_class_candidates"]==17
    assert out["evidence_tiers"]["SEC_NCEN_N2_TICKER_MATCH_VENUE_DISCREPANCY"]==2
    assert out["evidence_tiers"]["SEC_NCEN_N2_ISSUER_ONLY_TICKER_DISCREPANCY"]==1
    assert out["evidence_tiers"]["SEC_TVC_10K_EXCHANGE_TRADED_DEBT_CANDIDATE"]==1
    assert out["production_approvals"]==out["legal_scope_decisions_finalized"]==0


def test_sha_receipt_tampering_must_fail(tmp_path):
    (tmp_path/"a5s-original-primary-receipts.json").write_text("{}")
    with pytest.raises(m.PrimaryReviewError):
        m.summarize(tmp_path)
