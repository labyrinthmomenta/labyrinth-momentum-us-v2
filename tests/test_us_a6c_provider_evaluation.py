"""A6c: vendor claims are not independent feed proofs; demo stays excluded."""
from datetime import date,datetime,timezone
from hashlib import sha256
import json
import pytest

from src.data import us_provider_evaluation as p
from src.data import us_eodhd_demo_probe as demo


def sample_raw():
    return json.dumps([
        {"date":"2026-10-12","open":200.0,"high":203.0,
         "low":199.0,"close":201.0,"adjusted_close":198.1,
         "volume":120000},
        {"date":"2026-10-13","open":201.0,"high":204.0,
         "low":200.0,"close":202.0,"adjusted_close":199.1,
         "volume":113000},
        {"date":"2026-10-14","open":202.0,"high":205.0,
         "low":201.0,"close":203.0,"adjusted_close":200.1,
         "volume":111000},
    ]).encode()


def test_vendor_registry_no_unverified_licensing_or_status_promotion():
    r=p.registry()
    assert r["shortlist"]==["TIINGO","MASSIVE"]
    assert not r["actual_market_feed_selected"]
    assert not r["paid_account_or_vendor_entitlement_verified"]
    assert not r["official_US_exchange_calendar_verified"]
    assert r["publication_permission"]=="DENY"
    assert len(r["vendors"])==4
    assert r["vendors"]["EODHD"]["provisional_role"]=="SCHEMA_CONNECTIVITY_DEMO_ONLY"
    assert r["vendors"]["ALPACA"]["provisional_role"]=="SIP_PAID_CROSSCHECK_CANDIDATE"


def test_eodhd_doc_price_volume_mismatch_always_blocks_tradability():
    raw=sample_raw()
    s=p.inspect_eodhd_demo(raw,ticker="AAPL.US",
                           window_from=date(2026,10,1),
                           window_to=date(2026,10,14))
    assert s["source_original_SHA256"]==sha256(raw).hexdigest()
    assert s["rows_checked"]==3
    assert s["raw_close_times_volume_liquidity"]=="BLOCKED_INCOMPATIBLE_ADJUSTMENT_BASES"
    assert not s["technical_or_total_return_indicators_calculated"]
    assert s["canonical_market_price_bars_imported"]==0
    assert s["publication_permission"]=="DENY"


@pytest.mark.parametrize("problem",["duplicate","reversed","missing_adjusted","zero_volume_missing",
                                    "bad_currency_unknown","wrong_ohlc","after_asof"])
def test_bad_demo_input_cannot_enter_marketdata_contract(problem):
    arr=json.loads(sample_raw())
    if problem=="duplicate":arr[1]["date"]=arr[0]["date"]
    if problem=="reversed":arr.reverse()
    if problem=="missing_adjusted":del arr[1]["adjusted_close"]
    if problem=="zero_volume_missing":arr[1]["volume"]=None
    if problem=="bad_currency_unknown":arr[2]["adjusted_close"]=float("nan")
    if problem=="wrong_ohlc":arr[2]["low"]=206
    if problem=="after_asof":arr[2]["date"]="2026-10-15"
    with pytest.raises(p.VendorEvidenceError):
        p.inspect_eodhd_demo(json.dumps(arr).encode(),ticker="AAPL.US",
                             window_from=date(2026,10,1),
                             window_to=date(2026,10,14))


def test_non_demo_symbols_and_invalid_window_refused():
    with pytest.raises(p.VendorEvidenceError):
        p.inspect_eodhd_demo(sample_raw(),ticker="MSFT.US",
                             window_from=date(2026,10,1),
                             window_to=date(2026,10,14))
    with pytest.raises(p.VendorEvidenceError):
        p.inspect_eodhd_demo(sample_raw(),ticker="AAPL.US",
                             window_from=date(2026,10,15),
                             window_to=date(2026,10,14))


def test_tiingo_raw_adj_and_actions_fields_present_but_not_approved():
    r=[{"date":"2026-10-14","open":100,"high":101,"low":98,
        "close":100,"volume":15203,"adjOpen":95,"adjHigh":96,"adjLow":93,
        "adjClose":95,"adjVolume":15300,"divCash":0.2,"splitFactor":1}]
    result=p.assess_tiingo_schema(json.dumps(r).encode())
    assert result["raw_and_adjusted_fields_present"]
    assert result["dividends_and_splits_present"]
    assert not result["raw_price_times_raw_volume_live_tradability_approved"]
    assert result["publication_permission"]=="DENY"
    del r[0]["adjVolume"]
    with pytest.raises(p.VendorEvidenceError,match="fields"):
        p.assess_tiingo_schema(json.dumps(r).encode())


def test_demo_probe_success_has_true_response_sha_but_no_vendor_status_promotion():
    report=demo.probe(fetcher=lambda ticker:sample_raw(),
                      clock=lambda:datetime(2026,10,16,12,0,tzinfo=timezone.utc))
    assert report["status"]=="EODHD_PUBLIC_DEMO_SCHEMA_PROBED"
    assert report["original_demo_responses_schema_checked"]==2
    assert report["real_market_data_ingested_into_US_system"]==0
    assert report["downloaded_vendor_rows_saved_or_redistributed"] is False
    assert report["publication_permission"]=="DENY"
    assert all(x["source_original_SHA256"]==sha256(sample_raw()).hexdigest()
               for x in report["demo_observations"])


def test_demo_fetch_unavailable_is_not_reported_as_verified():
    def blocked(ticker):
        raise OSError("API demo blocked HTTP 403")
    report=demo.probe(fetcher=blocked)
    assert report["status"]=="EODHD_PUBLIC_DEMO_UNVERIFIED_OR_PARTIAL"
    assert report["original_demo_responses_schema_checked"]==0
    assert report["publication_permission"]=="DENY"
    assert "HTTP 403" in report["demo_observations"][0]["error"]


def test_one_demo_vendor_response_missing_is_not_full_pilot():
    def partly(ticker):
        if ticker=="TSLA.US":raise TimeoutError("timeout")
        return sample_raw()
    report=demo.probe(fetcher=partly)
    assert report["original_demo_responses_schema_checked"]==1
    assert report["status"]=="EODHD_PUBLIC_DEMO_UNVERIFIED_OR_PARTIAL"
    assert not report["vendor_licensed_or_approved"]


def test_demo_cli_restricts_writes_to_ephemeral_us_staging(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv",["probe","--output","../bist-momentum-v2"])
    assert demo.main()==2
    monkeypatch.setattr("sys.argv",["probe","--output","runtime/us_v2_staging/a6c"])
    monkeypatch.setattr(demo,"read_demo",lambda symbol: sample_raw())
    assert demo.main()==0
    out=tmp_path/"runtime/us_v2_staging/a6c/a6c-public-demo-vendor-probe.json"
    report=json.loads(out.read_text())
    assert report["original_demo_responses_schema_checked"]==2
    assert report["real_market_data_ingested_into_US_system"]==0
    with pytest.raises(Exception):
        # No re-running over the same artifact directory.
        assert demo.main()==0
