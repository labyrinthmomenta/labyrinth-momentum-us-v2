"""A6c: optional read-only EODHD public-DEMO *connectivity* probe.

Only publicly documented DEMO symbols; no vendor API key or purchased
entitlement. Never saves or republishes raw paid / market-data rows.
No real OHLCV is imported into US momentum/FIP, DB, or publication.
"""
from __future__ import annotations

import argparse
from datetime import date,datetime,timezone
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler,Request,build_opener

from .us_provider_evaluation import (
    inspect_eodhd_demo,registry,VendorEvidenceError,
)

START=date(2025,8,1)
AS_OF=date(2026,10,14)
TICKERS=("AAPL.US","TSLA.US")
MAX_BYTES=4_000_000


class BlockRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        return None


def read_demo(ticker:str)->bytes:
    if ticker not in TICKERS:
        raise VendorEvidenceError("Only two explicitly documented EODHD public DEMO tickers")
    args=urlencode({
        "api_token":"demo","from":START.isoformat(),
        "to":AS_OF.isoformat(),"period":"d","fmt":"json",
    })
    url=f"https://eodhd.com/api/eod/{ticker}?{args}"
    req=Request(url,headers={
        "User-Agent":"LabyrinthMomentumUSV2 A6c-public-demo-source-check",
        "Accept":"application/json","Accept-Encoding":"identity",
    })
    with build_opener(BlockRedirect()).open(req,timeout=35) as response:
        if response.geturl()!=url:
            raise VendorEvidenceError("Redirected DEMO price source; refused")
        raw=response.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES or not raw:
        raise VendorEvidenceError("Original DEMO source empty or too big")
    return raw


def probe(*,fetcher=read_demo,clock=lambda:datetime.now(timezone.utc))->dict:
    reports=[]
    for sym in TICKERS:
        item={"ticker":sym,"status":"DEMO_NOT_VERIFIED",
              "source_data_unapproved":True}
        try:
            raw=fetcher(sym)
            proof=inspect_eodhd_demo(raw,ticker=sym,window_from=START,window_to=AS_OF)
            now=clock()
            if not isinstance(now,datetime) or now.tzinfo is None or now.utcoffset() is None:
                raise VendorEvidenceError("Original demo retrieval time must be timezone aware")
            item.update(proof,retrieved_at=now.isoformat())
        except (OSError,ValueError,TypeError,TimeoutError) as e:
            item["error"]=f"{type(e).__name__}: {e}"[:220]
        reports.append(item)
    ok=sum(x["status"]=="EODHD_REAL_DEMO_PAYLOAD_SCHEMA_CHECK_ONLY" for x in reports)
    return {
        "status":"EODHD_PUBLIC_DEMO_SCHEMA_PROBED" if ok==len(TICKERS) else
                 "EODHD_PUBLIC_DEMO_UNVERIFIED_OR_PARTIAL",
        "as_of":AS_OF.isoformat(),
        "candidate_vendor_evaluated":"EODHD",
        "original_public_demo_requests_attempted":len(TICKERS),
        "original_demo_responses_schema_checked":ok,
        "real_market_data_ingested_into_US_system":0,
        "price_volume_basis_for_liquidity":"BLOCKED_RAW_PRICE_VS_SPLIT_ADJUSTED_VOLUME",
        "split_adjusted_OHLC_vendor_data_verified":False,
        "official_US_exchange_session_parity_verified":False,
        "current_symbol_to_independent_security_id_verified":False,
        "downloaded_vendor_rows_saved_or_redistributed":False,
        "trade_strategy_indicators_calculated":False,
        "vendor_licensed_or_approved":False,
        "publication_permission":"DENY",
        "production_eligible":False,
        "provider_market_evaluation":registry(),
        "demo_observations":reports,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    out=args.output
    if (out.is_absolute() or ".." in out.parts or
        not str(out).startswith("runtime/us_v2_staging/") or out.exists()):
        print("A6C_BLOCKED: only new temporary US staging output path")
        return 2
    report=probe()
    out.mkdir(parents=True,exist_ok=False)
    (out/"a6c-public-demo-vendor-probe.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",
        encoding="utf-8")
    print(json.dumps({
        "status":report["status"],
        "demo_requests":report["original_public_demo_requests_attempted"],
        "verified_schemas":report["original_demo_responses_schema_checked"],
        "production_approved":False,
        "publication_permission":"DENY",
    },indent=2))
    # The connectivity pilot must never masquerade as an approved production
    # price feed, including if the demo is blocked or rate-limited.
    return 0


if __name__=="__main__":
    raise SystemExit(main())
