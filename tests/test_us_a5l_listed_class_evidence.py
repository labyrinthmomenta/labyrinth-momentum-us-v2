"""A5l: SEC 12(b) ticker-celled title, source forgery and fund-report safeguards."""
import json
from hashlib import sha256
from pathlib import Path

import pytest

from src.data.universe import a5l_listed_class_evidence as mod


def html(title, ticker, exchange):
    return (f"<html><body><h2>FORM 10-Q</h2>"
            f"<table><tr><th>Title of each class</th><th></th>"
            f"<th>Trading Symbol</th><th></th><th>Exchange</th></tr>"
            f"<tr><td>{title}</td><td>&#8203;</td><td>{ticker}</td><td></td>"
            f"<td>{exchange}</td></tr></table>"
            f"<p>Other filing facts that should not decide the security class.</p>"
            f"</body></html>").encode()


def test_ordinary_shares_and_separate_unit_warning_in_exact_ticker_cell():
    raw=html("Class A ordinary shares, included as part of the units",
             "AACI","The Nasdaq Stock Market LLC")
    found=mod.extract_security_rows(raw,ticker="AACI",mic="XNAS")
    assert len(found)==1
    assert found[0]["main_class_wording"]=="CLASS_A_ORDINARY_SHARES"
    assert found[0]["qualifier_mentions_units"] is True
    assert found[0]["ticker_cell"]=="AACI"
    assert found[0]["security_id"] is None
    assert found[0]["share_class_approved"] is False


def test_common_stock_matches_only_exact_ticker_not_preferred_series():
    raw=(b"<html><body><table>"
         b"<tr><td>Preferred Stock Series C</td><td></td>"
         b"<td>ARR-PRC</td><td></td><td>New York Stock Exchange</td></tr>"
         b"<tr><td>Common Stock, $0.001 par value</td><td></td>"
         b"<td>ARR</td><td></td><td>New York Stock Exchange</td></tr>"
         b"</table></body></html>")
    x=mod.extract_security_rows(raw,ticker="ARR",mic="XNYS")
    assert len(x)==1 and x[0]["main_class_wording"]=="COMMON_STOCK"
    assert x[0]["ticker_cell"]=="ARR"


def test_other_ticker_and_wrong_exchange_are_rejected():
    x=html("Class A ordinary shares","AACIU","Nasdaq")
    assert mod.extract_security_rows(x,ticker="AACI",mic="XNAS")==[]
    x=html("Class A ordinary shares","AACI","NYSE")
    assert mod.extract_security_rows(x,ticker="AACI",mic="XNAS")==[]


def test_class_text_in_disconnected_row_not_counted():
    raw=(b"<html><table><tr><td>Class A ordinary shares</td></tr>"
         b"<tr><td>AACI</td><td>The Nasdaq Stock Market LLC</td></tr>"
         b"</table><p>Unrelated SEC reporting content.</p>"*6+b"</html>")
    assert mod.extract_security_rows(raw,ticker="AACI",mic="XNAS")==[]


def test_invalid_source_and_ticker_fail_closed():
    with pytest.raises(mod.SourceError):
        mod.extract_security_rows(b"Access Denied"*30,ticker="AACI",mic="XNAS")
    with pytest.raises(mod.SourceError):
        mod.extract_security_rows(html("Common Stock","ARR","NYSE"),
                                  ticker="../ARR",mic="XNYS")


def synthetic_source(tmp_path:Path,monkeypatch):
    sec=tmp_path/"sec"
    full=tmp_path/"full"
    sec.mkdir()
    full.mkdir()
    pilot=[]
    universe=[]
    for idx,(symbol,(cik,group)) in enumerate(mod.PILOT.items()):
        mic=mod.KNOWN_MIC[group]
        is_spac=group=="SPAC_OR_BLANK_CHECK"
        is_fund=group=="CLOSED_END_FUND_VS_BDC"
        typ=("Class A ordinary shares, included as part of units" if is_spac else
             "Common Stock")
        if is_fund:
            raw=(f"<html><body><h1>{symbol} fund filing N-CSRS</h1>"
                 f"<p>SEC reporting of a closed-end investment company.</p>"
                 + "<p>Quarterly investment holdings described.</p>"*12
                 + "</body></html>").encode()
            form="N-CSRS"
        else:
            raw=html(typ,symbol,
                     "The Nasdaq Stock Market LLC" if is_spac
                     else "New York Stock Exchange")
            form="10-Q"
        accession=f"0001193125-26-{idx+10:06d}"
        file=f"{symbol}-{accession}-{sha256(raw).hexdigest()}.source"
        (sec/file).write_bytes(raw)
        meta_raw=json.dumps({"cik":int(cik),"issuer":symbol}).encode()
        metadata_name=f"{symbol}-submissions-{sha256(meta_raw).hexdigest()}.json"
        (sec/metadata_name).write_bytes(meta_raw)
        filing={"form":form,"filing_date":"2026-08-10","accession":accession,
                "document_url":f"https://www.sec.gov/Archives/edgar/data/"
                               f"{int(cik)}/{accession.replace('-','')}/primary.htm"}
        pilot.append({
            "ticker":symbol,"cik":cik,"category_for_manual_review":group,
            "status":"SEC_ISSUER_FILING_CAPTURED_REVIEW_ONLY",
            "production_eligible":False,"source_security_identity_approved":False,
            "metadata":{"candidate_filing":filing,
                        "metadata_sha256":sha256(meta_raw).hexdigest()},
            "metadata_raw_filename":metadata_name,
            "primary_source":filing,
            "primary_raw_filename":file,
            "primary_observation":{
                "source_sha256":sha256(raw).hexdigest(),"source_bytes":len(raw),
                "title_class_security_id_verified":False},
            "primary_retrieved_at":"2026-10-15T15:00:00+00:00",
        })
        src="nasdaqlisted" if mic=="XNAS" else "otherlisted"
        universe.append({
            "source":src,"symbol":symbol,"mic":mic,"name":symbol+" Test",
            "original_a4_decision":"REVIEW_REQUIRED",
            "release_result":"DENY_OFFICIAL_SECURITY_TYPE_UNAPPROVED",
            "release_eligible":False,"listing_source_sha256":mod.SOURCE_SHAS[src],
        })
    pilot_json={
        "status":"OFFICIAL_SEC_PILOT_REVIEW_ONLY","pilot_size":9,
        "official_primary_filings_verified":9,
        "listed_security_id_approved":0,
        "instrument_type_decisions_completed":0,
        "production_eligible":False,"records":pilot,
    }
    universe_json={
        "status":"FULL_UNIVERSE_SOURCE_REPLAY_DENY_ONLY",
        "candidate_DENY":5566,"candidate_ALLOW":0,
        "all_source_listings_checked":13287,
        "connected_to_production":False,
        "review_records":universe+[{"symbol":f"OTHER{i}","mic":"XNAS"} for i in range(13278)],
    }
    p=json.dumps(pilot_json).encode()
    u=json.dumps(universe_json).encode()
    (sec/"a5k-sec-pilot-evidence.json").write_bytes(p)
    (full/"a5k-full-universe-deny.json").write_bytes(u)
    monkeypatch.setattr(mod,"A5K_PILOT_SHA",sha256(p).hexdigest())
    monkeypatch.setattr(mod,"A5K_UNIVERSE_SHA",sha256(u).hexdigest())
    return sec,full,pilot_json


def test_pinned_9_filing_evidence_and_13k_prior_decisions(monkeypatch,tmp_path):
    sec,full,_=synthetic_source(tmp_path,monkeypatch)
    r=mod.build(sec,full)
    assert r["status"]=="SEC_LISTED_CLASS_ROWS_REVIEW_ONLY"
    assert r["same_row_class_candidates"]==6
    assert r["class_wording_counts"]=={
        "CLASS_A_ORDINARY_SHARES":3,"COMMON_STOCK":3,
        "N_CSRS_ISSUER_REPORT_ONLY":3}
    assert r["fund_issuer_only_not_security_id"]==3
    assert r["review_required"]==9
    assert r["production_approvals"]==r["final_security_class_approvals"]==0
    assert all(x["production_eligible"] is False for x in r["records"])


def test_sec_original_document_tampered_fails_closed(monkeypatch,tmp_path):
    sec,full,p=synthetic_source(tmp_path,monkeypatch)
    original=sec/p["records"][0]["primary_raw_filename"]
    original.write_bytes(original.read_bytes()+b".")
    with pytest.raises(mod.SourceError,match="checksum"):
        mod.build(sec,full)


def test_forged_listing_approval_fails_closed(monkeypatch,tmp_path):
    sec,full,p=synthetic_source(tmp_path,monkeypatch)
    src=full/"a5k-full-universe-deny.json"
    d=json.loads(src.read_text())
    d["review_records"][0]["release_eligible"]=True
    raw=json.dumps(d).encode()
    src.write_bytes(raw)
    monkeypatch.setattr(mod,"A5K_UNIVERSE_SHA",sha256(raw).hexdigest())
    with pytest.raises(mod.SourceError):
        mod.build(sec,full)


def test_unpinned_missing_a5k_pilot_is_not_reconstructed(tmp_path):
    with pytest.raises(FileNotFoundError):
        mod.build(tmp_path,tmp_path)
