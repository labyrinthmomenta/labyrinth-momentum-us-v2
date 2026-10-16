"""A5n: frozen user export, independent MIC mapping and no production promotion."""
from hashlib import sha256
import csv
import io
from pathlib import Path
from zipfile import ZipFile

import pytest

from src.data.universe import a5n_tradingview_crosswalk as mod


def entry(sym,mic="XNAS",decision="INCLUDE",reason="EXPLICIT_COMMON_NAME_CANDIDATE"):
    return {"source":"nasdaqlisted" if mic=="XNAS" else "otherlisted",
            "symbol":sym,"mic":mic,"decision":decision,
            "reason":reason,"production_eligible":False}


def tv(sym,exchange="NASDAQ",cfi="ESVUFR"):
    return {"Symbol":sym,"Exchange":exchange,"Description":sym,
            "CFI classification":cfi,"ISIN":"US123","FIGI":"BBG1","CUSIP":"123",
            "Average volume, 90 days":"1000"}


def meta():
    return {"sha256":"b"*64,"rows":3,"columns":31,
            "duplicate_nonkey_headers":{"Sector":2}}


def test_exact_preferred_display_and_xase_scope_separate():
    a4=[entry("AAPL"),entry("JPM$M","XNYS","EXCLUDE","NON_COMMON_INSTRUMENT_NAME"),
        entry("AIM","XASE"),entry("LIEN","XNAS","REVIEW_REQUIRED","SPAC_BDC_OR_FINANCIAL_REVIEW")]
    rows=[tv("AAPL"),tv("JPM/PM","NYSE","EPNRCR"),tv("NOTIN","NYSE")]
    s,x=mod.compare(a4,rows,meta())
    assert s["exact_ticker_MIC_matches"]==1
    assert s["preferred_display_candidates"]==1
    assert s["tv_only_unresolved"]==1
    assert s["official_only_three_MIC"]==2
    assert s["A4_XASE_no_TV_counterpart"]==1
    assert s["production_approvals"]==s["security_id_approvals"]==0
    assert x["preferred_format_candidates"][0]["identity_approved"] is False


def test_no_auto_alias_nyse_american_as_nyse():
    s,x=mod.compare([entry("AIM","XASE")],[tv("AIM","NYSE")],meta())
    assert s["exact_ticker_MIC_matches"]==0
    assert s["tv_only_unresolved"]==1
    assert s["official_only_three_MIC"]==1


def test_slash_preferred_only_guarded_not_plain_slash_replacement():
    a4=[entry("T$C","XNYS","EXCLUDE"),entry("TPC","XNYS"),
        entry("JPM$M","XNYS","EXCLUDE")]
    s,x=mod.compare(a4,[tv("T/PC","NYSE","EPVGFR"),tv("JPM/PM","NYSE","EPVRFR")],meta())
    assert [r["a4_symbol"] for r in x["preferred_format_candidates"]]==["T$C","JPM$M"]
    assert any(r["symbol"]=="TPC" for r in x["official_only"])


def test_cfi_contradictions_review_only_even_provisional_include():
    a4=[entry("GAB","XNYS"),entry("TVC","XNYS")]
    s,x=mod.compare(a4,[tv("GAB","NYSE","CICJLS"),tv("TVC","NYSE","EPVGFR")],meta())
    assert s["provisional_include_CFI_disagreement_review"]==2
    assert s["CFI_disagreement_prefixes"]=={"CI":1,"EP":1}
    assert all(r["production_eligible"] is False for r in x["priority_review"])


def test_duplicate_display_collapsing_to_same_listing_fails_closed():
    a4=[entry("JPM$M","XNYS","EXCLUDE")]
    with pytest.raises(mod.SourceError,match="collapse"):
        mod.compare(a4,[tv("JPM$M","NYSE"),tv("JPM/PM","NYSE")],meta())


def test_duplicated_sector_field_is_preserved_not_overwritten(tmp_path):
    fields=["Symbol","Description","Exchange","CFI classification",
            "ISIN","FIGI","CUSIP","Average volume, 90 days","Sector","Sector"]
    p=tmp_path/"test.csv"
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f)
        w.writerow(fields)
        w.writerow(["AAPL","Apple","NASDAQ","ESVUFR","US1","B1","C1","100","A","B"])
    digest=sha256(p.read_bytes()).hexdigest()
    x,m=mod.load_csv(p,expected_sha=digest)
    assert len(x)==1 and m["duplicate_nonkey_headers"]=={"Sector":2}
    with pytest.raises(mod.SourceError,match="tampered"):
        mod.load_csv(p,expected_sha="0"*64)


def test_original_user_export_cannot_be_silently_modified(tmp_path):
    p=tmp_path/"test.csv"
    p.write_text("Symbol\nNVIDIA\n")
    with pytest.raises(mod.SourceError):
        mod.load_csv(p)


def test_frozen_official_zip_hash_is_mandatory(tmp_path):
    p=tmp_path/"official.zip"
    with ZipFile(p,"w") as z:
        z.writestr("directory-review/review.json","{}")
    with pytest.raises(mod.SourceError,match="SHA256"):
        mod.load_a4(p)


def test_official_crosswalk_issuer_cik_and_security_id_are_never_inferred():
    s,x=mod.compare([entry("AAPL")],[tv("AAPL")],meta())
    assert x["matches"][0]["identity_approved"] is False
    assert x["matches"][0]["production_eligible"] is False
    assert s["gate_connected_to_production"] is False
