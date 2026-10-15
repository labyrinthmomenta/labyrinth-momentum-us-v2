"""A5i review only: evidence integrity and provisional REFI release hold."""
from datetime import datetime, timezone
import pytest
from src.data.universe import a5i_decision_ledger as mod

NOW = datetime(2026, 10, 15, 15, 30, tzinfo=timezone.utc)
AGENT = "Labyrinth Research researcher@example.org"
EFFECT = (b'<?xml version="1.0"?><edgarSubmission><form>EFFECT</form>'
          b'<notice>Notice of Effectiveness for Registration Statement</notice>'
          b'</edgarSubmission>')
SEC_10Q = (b"<html><body><h1>FORM 10-Q</h1>"
           b"<p>QUARTERLY REPORT PURSUANT TO SECTION 13</p>"
           b"<table><tr><th>Class</th><th>Symbol</th><th>Exchange</th></tr>"
           b"<tr><td>Common Stock</td><td>REFI</td>"
           b"<td>Nasdaq Global Market</td></tr></table>"
           b"<p>We intend to elect BDC status before a proposed merger.</p>"
           + b"<p>Additional financial report content.</p>" * 30
           + b"</body></html>")


def a5_review():
    items = []
    for reason, count in mod.REASONS.items():
        for n in range(count):
            symbol = "LIEN" if reason == "SPAC_BDC_OR_FINANCIAL_REVIEW" and n == 0 else f"X{len(items):05d}"
            items.append({
                "source":"nasdaqlisted", "symbol":symbol, "mic":"XNAS",
                "original_decision":"REVIEW_REQUIRED", "original_reason":reason,
                "security_type_approved":False, "production_eligible":False,
                "listing_evidence_sha256":mod.A4_NASDAQ_HASH,
                "sec_evidence_sha256":"a"*64,
                "issuer_match_candidate":{"cik_candidate":"0001843162" if symbol=="LIEN" else None},
            })
    return items


def test_1010_held_without_refi_automatic_inclusion():
    result=mod.build_review_ledger(a5_review())
    assert len(result)==1010
    assert all(r["a5i_decision"]=="REVIEW_REQUIRED" and r["production_eligible"] is False for r in result)
    assert not any(r["symbol"]=="REFI" for r in result)
    assert any("LIEN_REFI_MERGER_PENDING_FACTUAL_REVIEW" in r["review_flags"] for r in result)
    assert sum(r["scope_decision_proposed"]=="OUT_OF_SCOPE_TXSE" for r in result)==10


def test_effect_xml_is_not_merger_closing():
    result=mod.inspect_effect(EFFECT)
    assert result["text_effectiveness_signal"]
    assert result["registration_effectiveness_only"]
    assert result["merger_closing_verified"] is False
    assert result["production_eligible"] is False


@pytest.mark.parametrize("raw", [
    b"<html>Access Denied</html>"*4,
    b"<?xml version='1.0'?><edgarSubmission>invalid",
    b"<!DOCTYPE note><note>effectiveness</note>",
    b"",b"<x>unrelated text</x>"*10,
])
def test_non_effect_sources_fail_closed(raw):
    with pytest.raises(mod.DecisionLedgerError):
        mod.inspect_effect(raw)


def loaded():
    rows={
        "LIEN":{"symbol":"LIEN","name":"Chicago Atlantic BDC Common Stock",
                "mic":"XNAS","decision":"REVIEW_REQUIRED","production_eligible":False},
        "REFI":{"symbol":"REFI","name":"Chicago Atlantic REFI Common Stock",
                "mic":"XNAS","decision":"INCLUDE","production_eligible":False},
    }
    effect={"form":"EFFECT","accession":mod.EFFECT_ACC,"filing_date":"2026-09-30",
            "primary_document_url":(
                "https://www.sec.gov/Archives/edgar/data/1843162/"
                "999999999526003107/xslEFFECTX01/primary_doc.xml")}
    return {"a4_rows":rows,"a5_reviews":a5_review(),"effect":effect,
            "a5h":{},"timelines":{}}


def test_complete_mock_capture_preserves_independent_issuer_and_security_states(monkeypatch,tmp_path):
    monkeypatch.setattr(mod,"load_sources",lambda *args:loaded())
    def fetch(url,agent,*,cap,cik,accession):
        return EFFECT if accession==mod.EFFECT_ACC else SEC_10Q
    result=mod.run(tmp_path,tmp_path,tmp_path,tmp_path/"ok",
                   agent=AGENT,fetcher=fetch,clock=lambda:NOW)
    assert result["status"]=="EVIDENCE_LEDGER_REVIEW_ONLY"
    assert result["still_review_required"]==1010
    assert result["REFI_separate_corporate_event_hold"]
    assert result["production_approvals"]==0
    refi=next(x for x in result["merger_company_evidence_overlays"] if x["symbol"]=="REFI")
    assert refi["a4_original_decision"]=="INCLUDE" and refi["explicit_release_hold"]
    assert refi["merger_completion"]=="NOT_ESTABLISHED"
    assert len(list((tmp_path/"ok").glob("*.source")))==2


def test_sec_denial_is_partial_never_auto_approved(monkeypatch,tmp_path):
    monkeypatch.setattr(mod,"load_sources",lambda *args:loaded())
    def denied(*a,**k):raise OSError("SEC temporarily inaccessible")
    result=mod.run(tmp_path,tmp_path,tmp_path,tmp_path/"partial",
                   agent=AGENT,fetcher=denied,clock=lambda:NOW)
    assert result["status"]=="EVIDENCE_LEDGER_PARTIAL_REVIEW_ONLY"
    assert len(result["source_failures"])==2
    assert result["production_approvals"]==0
    assert result["REFI_separate_corporate_event_hold"]


def test_missing_frozen_source_blocks_audit(tmp_path):
    with pytest.raises(FileNotFoundError):
        mod.load_sources(tmp_path,tmp_path,tmp_path)


def test_sec_cross_issuer_url_refused():
    with pytest.raises(Exception):
        mod.fetch_sec_file(
            "https://www.sec.gov/Archives/edgar/data/1843162/999999999526003107/../bad.xml",
            AGENT,cap=1000,cik=mod.LIEN_CIK,accession=mod.EFFECT_ACC)
