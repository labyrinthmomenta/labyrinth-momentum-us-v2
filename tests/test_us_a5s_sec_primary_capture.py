"""A5s original SEC N-CEN and TVC 10-K: date, URL, CIK and evidence safety."""
import json
import pytest
from src.data.universe import a5s_sec_primary_capture as m


def meta(cik=1768666):
    return json.dumps({"cik":cik,"filings":{"recent":{
        "form":["N-CEN","N-CEN","10-K"],
        "filingDate":["2026-03-13","2026-10-15","2025-11-13"],
        "accessionNumber":["0001410368-26-025355","0001410368-26-999999",
                           "0001376986-25-000056"],
        "primaryDocument":["xslFormN-CEN_X01/primary_doc.xml",
                           "newer.xml","tve-20250930.htm"],
    }}}).encode()


def test_source_must_be_pre_asof_for_fund():
    r=m.latest_form(meta(),cik="0001768666",ticker="BSTZ")
    assert r["form"]=="N-CEN"
    assert r["filing_date"]=="2026-03-13"
    assert r["accession"]=="0001410368-26-025355"
    assert r["url"].endswith("/xslFormN-CEN_X01/primary_doc.xml")


def test_tvc_requires_issuer_cik_and_10k():
    r=m.latest_form(meta(1376986),cik="0001376986",ticker="TVC")
    assert r["form"]=="10-K"
    assert r["filing_date"]=="2025-11-13"


def test_fake_cik_and_traversal_rejected():
    with pytest.raises(m.CaptureError):
        m.latest_form(meta(),cik="0001768667",ticker="BSTZ")
    broken=json.loads(meta())
    broken["filings"]["recent"]["primaryDocument"][0]="../escape.xml"
    with pytest.raises(m.CaptureError):
        m.latest_form(json.dumps(broken).encode(),cik="0001768666",ticker="BSTZ")


def test_future_only_does_not_prove_type_absence():
    x=json.loads(meta())
    x["filings"]["recent"]["filingDate"]=["2026-10-15"]*3
    with pytest.raises(m.CaptureError,match="older history unresolved"):
        m.latest_form(json.dumps(x).encode(),cik="0001768666",ticker="BSTZ")


def test_missing_primary_metadata_never_makes_up_a_url():
    x=json.loads(meta())
    del x["filings"]["recent"]["primaryDocument"]
    with pytest.raises(m.CaptureError):
        m.latest_form(json.dumps(x).encode(),cik="0001768666",ticker="BSTZ")


def test_bounded_source_access_no_private_url():
    with pytest.raises(m.CaptureError):
        m.fetch_sec("https://bad.example.org/hello",agent="Labyrinth Audit reviewer reviewer@example.com")


def test_original_source_report_mutation_fails_closed(tmp_path):
    p=tmp_path/"a5o-official-issuer-forms.json"
    p.write_text("{}")
    with pytest.raises(m.CaptureError,match="SHA"):
        m.capture(tmp_path,tmp_path/"out",agent="Labyrinth Audit reviewer reviewer@example.com")
