"""A6c: provider capabilities and strict EOD schema assessment (NOT a price feed).

PIT review only: no credential storage, no production bars, no current
stock universe IDs, no pricing ingestion. Expose adjustment incompatibility
explicitly instead of multiplying mismatched share-volume and prices.
Vendor descriptions are documentation claims, NOT independently tested
full-universe capabilities, licensed entitlements, or approved sources.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import math

VERSION="a6c-us-marketdata-provider-evaluation-v1"
VENDORS={
    "TIINGO":{
        "api_token_required":True,
        "vendor_documentation":"https://www.tiingo.com/documentation/end-of-day",
        "daily_data":"Raw OHLCV, adjusted OHLCV, divCash and splitFactor",
        "testing_status":"SCHEMA_UNIT_TESTS_ONLY_NO_TOKEN",
        "risk":"Raw/adjusted price-volume parity, universe coverage and correction backfill require proof",
        "provisional_role":"FULL_US_PILOT_SHORTLIST",
    },
    "MASSIVE":{
        "api_token_required":True,
        "vendor_documentation":"https://massive.com/stocks",
        "daily_data":"SIP-wide daily aggregates; split adjusted default / unadjusted selectable",
        "testing_status":"DOCS_ONLY_NO_TOKEN",
        "risk":"Historical split adjustment is not dividend adjustment; total return needs actions/reconciliation",
        "provisional_role":"FULL_US_PILOT_SHORTLIST",
    },
    "ALPACA":{
        "api_token_required":True,
        "vendor_documentation":"https://docs.alpaca.markets/us/reference/stockbars",
        "daily_data":"Raw, split, dividend, spin-off, all (feed=IEX or SIP)",
        "testing_status":"DOCS_ONLY_NO_TOKEN",
        "risk":"IEX-only feed not representative of consolidated US share volume; paid SIP entitlement needs verification",
        "provisional_role":"SIP_PAID_CROSSCHECK_CANDIDATE",
    },
    "EODHD":{
        "api_token_required":False,
        "vendor_documentation":"https://eodhd.com/financial-apis/api-for-historical-data-and-volumes",
        "daily_data":"Raw/as-traded OHLC, split+dividend adjusted_close, split-adjusted volume",
        "testing_status":"PUBLIC_DEMO_ONLY_NOT_PRODUCTION",
        "risk":"Raw close and split-adjusted volume cannot be multiplied for historical dollar volume",
        "provisional_role":"SCHEMA_CONNECTIVITY_DEMO_ONLY",
    },
}


class VendorEvidenceError(ValueError):
    pass


def registry()->dict:
    return {
        "status":"PUBLIC_DOCS_EVALUATION_NOT_PRODUCTION_APPROVAL",
        "version":VERSION,
        "shortlist":["TIINGO","MASSIVE"],
        "candidate_comparison_only":["ALPACA","EODHD"],
        "currency":"USD",
        "listing_identity_approved":False,
        "legal_terms_redistribution_and_retention_approved":False,
        "paid_account_or_vendor_entitlement_verified":False,
        "actual_market_feed_selected":False,
        "official_US_exchange_calendar_verified":False,
        "publication_permission":"DENY",
        "vendors":VENDORS,
    }


@dataclass(frozen=True)
class DemonstrationBar:
    session_date:date
    raw_open:float
    raw_high:float
    raw_low:float
    raw_close:float
    adjusted_close:float
    split_adjusted_volume:int


def _number(value, *,zero:bool=False)->bool:
    return (type(value) in (int,float)
            and math.isfinite(value)
            and (value>=0 if zero else value>0))


def _parse_demo_rows(payload:bytes)->list[DemonstrationBar]:
    if not isinstance(payload,bytes) or len(payload)>4_000_000 or len(payload)<10:
        raise VendorEvidenceError("Unexpected EODHD DEMO response length")
    try:
        raw=json.loads(payload)
    except (UnicodeDecodeError,ValueError) as exc:
        raise VendorEvidenceError("EODHD demo did not return JSON") from exc
    if not isinstance(raw,list) or len(raw)>5000 or not raw:
        raise VendorEvidenceError("EODHD demo JSON array unavailable/invalid")
    out=[]
    last_date=None
    for r in raw:
        if not isinstance(r,dict):
            raise VendorEvidenceError("Malformed EODHD daily observation")
        required=("date","open","high","low","close","adjusted_close","volume")
        if any(k not in r for k in required):
            raise VendorEvidenceError("Missing EODHD adjustment or OHLCV field")
        try:
            d=date.fromisoformat(r["date"])
        except (ValueError,TypeError):
            raise VendorEvidenceError("Invalid exchange local date")
        if last_date is not None and d<=last_date:
            raise VendorEvidenceError("Duplicate/unordered historical US bar")
        last_date=d
        if not all(_number(r[k]) for k in ("open","high","low","close","adjusted_close")):
            raise VendorEvidenceError("Non-finite or negative EOD prices")
        if type(r["volume"]) is not int or r["volume"]<0:
            raise VendorEvidenceError("Noninteger/negative split-adjusted volume")
        if (r["high"]<max(r["open"],r["close"],r["low"])
            or r["low"]>min(r["open"],r["close"],r["high"])):
            raise VendorEvidenceError("OHLC bounds inconsistent")
        out.append(DemonstrationBar(
            session_date=d,raw_open=r["open"],raw_high=r["high"],
            raw_low=r["low"],raw_close=r["close"],
            adjusted_close=r["adjusted_close"],
            split_adjusted_volume=r["volume"]))
    return out


def inspect_eodhd_demo(payload:bytes,*,ticker:str,window_from:date,window_to:date)->dict:
    if ticker not in ("AAPL.US","TSLA.US","AMZN.US"):
        raise VendorEvidenceError("Only EODHD officially documented demo symbols permitted")
    if not isinstance(window_from,date) or not isinstance(window_to,date) or window_from>window_to:
        raise VendorEvidenceError("Malformed bounded EODHD history window")
    rows=_parse_demo_rows(payload)
    if rows[0].session_date<window_from or rows[-1].session_date>window_to:
        raise VendorEvidenceError("Demo API ignored user supplied as-of date limits")
    return {
        "status":"EODHD_REAL_DEMO_PAYLOAD_SCHEMA_CHECK_ONLY",
        "vendor":"EODHD","ticker":ticker,"from":window_from.isoformat(),
        "to":window_to.isoformat(),
        "source_original_SHA256":sha256(payload).hexdigest(),
        "bytes_received":len(payload),"rows_checked":len(rows),
        "first_date":rows[0].session_date.isoformat(),
        "last_date":rows[-1].session_date.isoformat(),
        "eodhd_raw_ohlc":True,
        "eodhd_adjusted_close_is_split_and_dividend_adjusted":True,
        "eodhd_daily_volume_is_split_adjusted":True,
        "raw_close_times_volume_liquidity": "BLOCKED_INCOMPATIBLE_ADJUSTMENT_BASES",
        "alternate_split_adjusted_price_source_verified":False,
        "official_calendar_parity_verified":False,
        "provider_identity_or_licence_approved":False,
        "data_adjustment_revision_history_verified":False,
        "canonical_market_price_bars_imported":0,
        "technical_or_total_return_indicators_calculated":False,
        "production_eligible":False,
        "publication_permission":"DENY",
    }


def assess_tiingo_schema(payload:bytes)->dict:
    """Tiingo documented raw/adjusted fields, no actual provider authorization.

    Both price and volume bases are NOT interchangeable for the
    dollar-volume formula without independent action-parity proof.
    """
    if not isinstance(payload,bytes) or len(payload)>4_000_000:
        raise VendorEvidenceError("Tiingo source outside bounded payload")
    try:raw=json.loads(payload)
    except (ValueError,UnicodeDecodeError) as err:
        raise VendorEvidenceError("Invalid Tiingo JSON") from err
    if not isinstance(raw,list) or not raw:
        raise VendorEvidenceError("Tiingo price rows missing")
    required=frozenset({
        "date","open","high","low","close","volume",
        "adjOpen","adjHigh","adjLow","adjClose","adjVolume",
        "divCash","splitFactor",
    })
    for r in raw:
        if not isinstance(r,dict) or not required.issubset(r):
            raise VendorEvidenceError("Missing Tiingo raw/adjusted action fields")
        if (not all(_number(r[k]) for k in ("open","high","low","close",
                                           "adjOpen","adjHigh","adjLow","adjClose","splitFactor"))
            or not all(_number(r[k],zero=True)
                       for k in ("volume","adjVolume","divCash"))):
            raise VendorEvidenceError("Non-finite Tiingo price or action")
    return {
        "status":"TIINGO_DOCUMENTED_SCHEMA_ONLY_NO_LIVE_ENTITLEMENT",
        "rows_checked":len(raw),
        "raw_and_adjusted_fields_present":True,
        "dividends_and_splits_present":True,
        "calendar_parity_verified":False,
        "corporate_action_adjustment_parity_verified":False,
        "raw_price_times_raw_volume_live_tradability_approved":False,
        "provider_feed_selected":False,
        "publication_permission":"DENY",
    }
